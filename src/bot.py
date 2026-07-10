import json
import logging
import os
import sys
import time
from urllib.parse import urlencode, urlparse, urlunparse

import requests

from scraper import MercadoLivreScraper
from storage import load_sent_ids, save_sent_ids
from telegram_sender import TelegramSender
from utils import format_price
from whatsapp_sender import WhatsAppSender

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def make_affiliate_url(clean_url: str, affiliate_tag: str) -> str:
    if not affiliate_tag:
        return clean_url

    parsed = urlparse(clean_url)
    params = {}

    if affiliate_tag.startswith("matt:"):
        parts = affiliate_tag.split(":")
        if len(parts) >= 3:
            params["matt_word"] = parts[1]
            params["matt_tool"] = parts[2]
    else:
        params["tag"] = affiliate_tag

    existing = parsed.query
    new_query = urlencode(params)
    query = f"{existing}&{new_query}" if existing else new_query

    return urlunparse(parsed._replace(query=query))


def _fetch_dashboard_config(dashboard_url: str, api_key: str):
    try:
        resp = requests.get(
            f"{dashboard_url.rstrip('/')}/api/config",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("Falha ao buscar config da dashboard: %s", e)
        return None


def _init_dashboard_run(dashboard_url: str, api_key: str):
    try:
        resp = requests.post(
            f"{dashboard_url.rstrip('/')}/api/runs/init",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("run_id")
    except Exception as e:
        logger.warning("Falha ao iniciar run na dashboard: %s", e)
        return None


def _report_dashboard_run(dashboard_url: str, api_key: str, run_id: int,
                          status: str, offers_found: int, offers_sent: int,
                          offers_new: int, error_message: str = None,
                          logs: list = None, sent_offers: list = None):
    try:
        payload = {
            "run_id": run_id,
            "status": status,
            "offers_found": offers_found,
            "offers_sent": offers_sent,
            "offers_new": offers_new,
            "error_message": error_message,
            "logs": logs or [],
            "sent_offers": sent_offers or [],
        }
        resp = requests.post(
            f"{dashboard_url.rstrip('/')}/api/runs/{run_id}/finish",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning("Falha ao reportar execucao: %s", e)


def _matches_keywords(title: str, include: str, exclude: str) -> bool:
    title_lower = title.lower()
    if include:
        keywords = [kw.strip().lower() for kw in include.split(",") if kw.strip()]
        if keywords and not any(kw in title_lower for kw in keywords):
            return False
    if exclude:
        keywords = [kw.strip().lower() for kw in exclude.split(",") if kw.strip()]
        if keywords and any(kw in title_lower for kw in keywords):
            return False
    return True


def main():
    for var in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]:
        if var not in os.environ:
            logger.error("Missing required env var: %s", var)
            sys.exit(1)

    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    affiliate_tag = os.environ.get("AFFILIATE_TAG", "")
    category = os.environ.get("ML_CATEGORY", "")
    pages = int(os.environ.get("ML_PAGES", "3"))
    max_offers = int(os.environ.get("MAX_OFFERS_PER_RUN", "10"))
    promotion_type = os.environ.get("ML_PROMOTION_TYPE", "")
    min_discount = int(os.environ.get("MIN_DISCOUNT", "0"))
    send_delay = int(os.environ.get("SEND_DELAY_SECONDS", "60"))

    dashboard_url = os.environ.get("DASHBOARD_URL", "")
    dashboard_key = os.environ.get("BOT_API_KEY", "")
    dashboard_run_id = None

    if dashboard_url:
        dc = _fetch_dashboard_config(dashboard_url, dashboard_key)
        if dc:
            category = dc.get("ML_CATEGORY", category)
            pages = int(dc.get("ML_PAGES", pages))
            max_offers = int(dc.get("MAX_OFFERS_PER_RUN", max_offers))
            promotion_type = dc.get("ML_PROMOTION_TYPE", promotion_type)
            min_discount = int(dc.get("MIN_DISCOUNT", min_discount))
            send_delay = int(dc.get("SEND_DELAY_SECONDS", send_delay))
            logger.info("Config carregada da dashboard")
        dashboard_run_id = _init_dashboard_run(dashboard_url, dashboard_key)

    include_kw = os.environ.get("INCLUDE_KEYWORDS", "")
    exclude_kw = os.environ.get("EXCLUDE_KEYWORDS", "")
    if dashboard_url and dc:
        include_kw = dc.get("INCLUDE_KEYWORDS", include_kw)
        exclude_kw = dc.get("EXCLUDE_KEYWORDS", exclude_kw)

    sender_tg = TelegramSender(bot_token)

    zap_token = os.environ.get("ZAP_API_TOKEN", "")
    zap_instance = os.environ.get("ZAP_API_INSTANCE_ID", "")
    zap_group = os.environ.get("ZAP_API_GROUP_JID", "")
    sender_wp = WhatsAppSender(zap_token, zap_instance) if zap_token and zap_instance and zap_group else None

    categories = [c.strip() for c in category.split(",")] if category else [""]
    promo_types = [""] if promotion_type else ["", "lightning"]

    all_offers = []
    seen_ids = set()
    for ci, cat in enumerate(categories):
        for ptype in promo_types:
            cat_label = cat if cat else "todas"
            pt_label = f"promotion_type={ptype}" if ptype else "todas"
            logger.info("Buscando ofertas [%s, %s]...", cat_label, pt_label)
            scraper = MercadoLivreScraper(category=cat, pages=pages, promotion_type=ptype)
            try:
                offers = scraper.scrape()
            except Exception as e:
                logger.error("Erro ao buscar ofertas [%s, %s]: %s", cat_label, pt_label, e)
                continue
            for o in offers:
                if o.id not in seen_ids:
                    seen_ids.add(o.id)
                    all_offers.append(o)
            logger.info("  -> %d ofertas (%s, %s)", len(offers), cat_label, pt_label)
        if ci < len(categories) - 1:
            logger.info("Aguardando 2s antes da proxima categoria...")
            time.sleep(2)

    offers = [o for o in all_offers if o.current_price > 0 and o.discount_percent >= min_discount]
    dropped = len(all_offers) - len(offers)
    if dropped:
        logger.info("Filtradas %d ofertas (preco zero ou desconto < %d%%)", dropped, min_discount)

    if include_kw or exclude_kw:
        before = len(offers)
        offers = [o for o in offers if _matches_keywords(o.title, include_kw, exclude_kw)]
        kw_dropped = before - len(offers)
        if kw_dropped:
            logger.info("Filtradas %d ofertas por palavras-chave", kw_dropped)

    offers_found = len(all_offers)
    offers_after_filters = len(offers)

    if not offers:
        logger.info("Nenhuma oferta encontrada apos filtros")
        if dashboard_run_id:
            _report_dashboard_run(dashboard_url, dashboard_key, dashboard_run_id,
                                  "success", offers_found, 0, 0)
        return

    sent_ids = load_sent_ids()
    new_offers = [o for o in offers if o.id not in sent_ids]

    if not new_offers:
        logger.info("Nenhuma oferta nova para enviar")
        if dashboard_run_id:
            _report_dashboard_run(dashboard_url, dashboard_key, dashboard_run_id,
                                  "success", offers_found, 0, 0)
        return

    to_send = new_offers[:max_offers]
    logger.info("Enviando %d de %d ofertas novas (delay %ds entre cada)", len(to_send), len(new_offers), send_delay)

    sent_offers_data = []
    sent_count = 0
    for i, offer in enumerate(to_send):
        if i > 0:
            logger.info("Aguardando %d segundos...", send_delay)
            time.sleep(send_delay)
        try:
            offer.url = make_affiliate_url(offer.clean_url, affiliate_tag)
        except Exception as e:
            logger.error("Falha ao gerar URL para '%s': %s", offer.title[:40], e)
            continue

        ok_tg = False
        try:
            sender_tg.send_offer(chat_id, offer)
            ok_tg = True
            logger.info("Telegram: %s", offer.title[:60])
        except Exception as e:
            logger.error("Falha no Telegram para '%s': %s", offer.title[:40], e)

        ok_wp = False
        if sender_wp:
            try:
                sender_wp.send_offer(zap_group, offer)
                ok_wp = True
                logger.info("WhatsApp: %s", offer.title[:60])
            except Exception as e:
                logger.error("Falha no WhatsApp para '%s': %s", offer.title[:40], e)

        if ok_tg or ok_wp:
            sent_ids[offer.id] = time.time()
            sent_count += 1
            sent_offers_data.append({
                "product_id": offer.product_id,
                "title": offer.title,
                "price": offer.current_price,
                "discount": offer.discount_label,
            })

    if sent_count > 0:
        save_sent_ids(sent_ids)

    logger.info("Concluido. %d oferta(s) enviada(s)", sent_count)

    if dashboard_run_id:
        _report_dashboard_run(
            dashboard_url, dashboard_key, dashboard_run_id,
            "success" if sent_count > 0 else "error",
            offers_found, sent_count, len(new_offers),
            sent_offers=sent_offers_data,
        )


if __name__ == "__main__":
    main()
