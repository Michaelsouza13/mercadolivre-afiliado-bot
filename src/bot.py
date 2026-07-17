import json
import logging
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlencode, urlparse, urlunparse

import requests

from aliexpress_scraper import AliExpressScraper
from scraper import MercadoLivreScraper
from shopee_scraper import ShopeeScraper
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


@dataclass
class Channel:
    name: str
    telegram_chat_id: str = ""
    whatsapp_group_jid: str = ""
    include_keywords: str = ""
    exclude_keywords: str = ""
    ml_category: str = ""
    min_discount: int = 0


def _get_channel_value(dc: Optional[dict], key: str, fallback: str) -> str:
    if dc and key in dc and dc[key]:
        return dc[key]
    val = os.environ.get(key, "")
    return val if val else fallback


def parse_channels(dc: Optional[dict] = None) -> List[Channel]:
    channels_str = ""
    if dc and dc.get("CHANNELS"):
        channels_str = dc["CHANNELS"]
    if not channels_str:
        channels_str = os.environ.get("CHANNELS", "")

    if not channels_str:
        return [
            Channel(
                name="default",
                telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
                whatsapp_group_jid=os.environ.get("ZAP_API_GROUP_JID", ""),
            )
        ]

    kw_channels = []
    catch_all_channels = []
    for name in [n.strip() for n in channels_str.split(",") if n.strip()]:
        prefix = f"CHANNEL_{name.upper()}"
        include = _get_channel_value(dc, f"{prefix}_INCLUDE", "")
        exclude = _get_channel_value(dc, f"{prefix}_EXCLUDE", "")
        telegram = _get_channel_value(dc, f"{prefix}_TELEGRAM",
                                      os.environ.get("TELEGRAM_CHAT_ID", ""))
        whatsapp = _get_channel_value(dc, f"{prefix}_WHATSAPP",
                                      os.environ.get("ZAP_API_GROUP_JID", ""))
        category = _get_channel_value(dc, f"{prefix}_CATEGORY", "")
        min_disc_str = _get_channel_value(dc, f"{prefix}_MIN_DISCOUNT", "0")
        min_disc = int(min_disc_str) if min_disc_str else 0
        ch = Channel(
            name=name, telegram_chat_id=telegram,
            whatsapp_group_jid=whatsapp,
            include_keywords=include, exclude_keywords=exclude,
            ml_category=category, min_discount=min_disc,
        )
        if include or exclude:
            kw_channels.append(ch)
        else:
            catch_all_channels.append(ch)

    channels = kw_channels + catch_all_channels

    if not catch_all_channels and not kw_channels:
        channels.append(Channel(
            name="geral",
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
            whatsapp_group_jid=os.environ.get("ZAP_API_GROUP_JID", ""),
        ))

    return channels


def match_channel(offer, channels: List[Channel]) -> Optional[Channel]:
    for ch in channels:
        kw = ch.include_keywords
        ex = ch.exclude_keywords
        if kw or ex:
            if _matches_keywords(offer.title, kw, ex):
                return ch
            continue
        return ch
    return channels[0] if channels else None


def _interleave_offers(offers: list) -> list:
    groups = defaultdict(list)
    for o in offers:
        prefix = o.product_id[:2]
        groups[prefix].append(o)
    result = []
    while any(groups.values()):
        for prefix in ["ML", "AE", "SH"]:
            if groups[prefix]:
                result.append(groups[prefix].pop(0))
    return result


def _balance_offers(all_offers: list, max_offers: int) -> list:
    if not all_offers or max_offers <= 0:
        return []

    quota = max(max_offers // 3, 1)

    groups = defaultdict(list)
    for o in all_offers:
        groups[o.product_id[:2]].append(o)

    result = []

    for i in range(quota):
        for prefix in ["ML", "AE", "SH"]:
            pool = groups.get(prefix, [])
            if i < len(pool) and len(result) < max_offers:
                result.append(pool[i])

    remaining = _interleave_offers(
        [o for prefix in ["ML", "AE", "SH"]
         for o in groups.get(prefix, [])[quota:]]
    )
    for o in remaining:
        if len(result) >= max_offers:
            break
        result.append(o)

    logger.info("Balanceamento: quota=%d, total=%d, composicao: ML=%d AE=%d SH=%d",
                quota, len(result),
                sum(1 for o in result if o.product_id[:2] == "ML"),
                sum(1 for o in result if o.product_id[:2] == "AE"),
                sum(1 for o in result if o.product_id[:2] == "SH"))
    return result


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
    ml_max_pages = int(os.environ.get("ML_MAX_PAGES", "20"))
    ml_max_offers = int(os.environ.get("ML_MAX_OFFERS", "0")) or 0
    max_offers = int(os.environ.get("MAX_OFFERS_PER_RUN", "10"))
    promotion_type = os.environ.get("ML_PROMOTION_TYPE", "")
    min_discount = int(os.environ.get("MIN_DISCOUNT", "0"))
    send_delay = int(os.environ.get("SEND_DELAY_SECONDS", "60"))

    ae_app_key = os.environ.get("ALIEXPRESS_APP_KEY", "")
    ae_app_secret = os.environ.get("ALIEXPRESS_APP_SECRET", "")
    ae_tracking_id = os.environ.get("ALIEXPRESS_TRACKING_ID", "maikapromos")
    ae_max_offers = int(os.environ.get("ALIEXPRESS_MAX_OFFERS", "5"))
    ae_category_ids = os.environ.get("ALIEXPRESS_CATEGORY_IDS", "") or "44,7,509"
    ae_keywords = os.environ.get("ALIEXPRESS_KEYWORDS", "")

    sh_app_id = os.environ.get("SHOPEE_APP_ID", "")
    sh_app_secret = os.environ.get("SHOPEE_APP_SECRET", "")
    sh_max_offers = int(os.environ.get("SHOPEE_MAX_OFFERS", "5"))
    sh_keywords = os.environ.get("SHOPEE_KEYWORDS", "") or "fone bluetooth,smartwatch,caixa som,drone,camera seguranca,tapete sala,tapete banheiro,cortina blackout,revestimento ripado,papel parede 3d,quadro decorativo,espelho adnet,painel ripado,manta sofa,ventilador teto,mini aspirador,papa bolinhas,ferro portatil,umidificador,climatizador,passadeira vapor,irrigador dental,creatina,suplemento"

    dashboard_url = os.environ.get("DASHBOARD_URL", "")
    dashboard_key = os.environ.get("BOT_API_KEY", "")
    dashboard_run_id = None

    if dashboard_url:
        dc = _fetch_dashboard_config(dashboard_url, dashboard_key)
        if dc:
            category = dc.get("ML_CATEGORY", category)
            pages = int(dc.get("ML_PAGES", pages))
            ml_max_pages = int(dc.get("ML_MAX_PAGES", str(ml_max_pages)))
            ml_max_offers_str = dc.get("ML_MAX_OFFERS", "")
            if ml_max_offers_str:
                ml_max_offers = int(ml_max_offers_str)
            max_offers = int(dc.get("MAX_OFFERS_PER_RUN", max_offers))
            promotion_type = dc.get("ML_PROMOTION_TYPE", promotion_type)
            min_discount = int(dc.get("MIN_DISCOUNT", min_discount))
            send_delay = int(dc.get("SEND_DELAY_SECONDS", send_delay))
            ae_max_offers = int(dc.get("ALIEXPRESS_MAX_OFFERS", str(ae_max_offers)))
            ae_category_ids = dc.get("ALIEXPRESS_CATEGORY_IDS") or ae_category_ids
            ae_keywords = dc.get("ALIEXPRESS_KEYWORDS", "") or ae_keywords
            sh_max_offers = int(dc.get("SHOPEE_MAX_OFFERS", str(sh_max_offers)))
            sh_keywords = dc.get("SHOPEE_KEYWORDS", sh_keywords)
            logger.info("Config carregada da dashboard")
        dashboard_run_id = _init_dashboard_run(dashboard_url, dashboard_key)

    ml_target = ml_max_offers if ml_max_offers > 0 else max_offers
    logger.info("Limite de coleta: ML=%d AE=%d SH=%d (max_offers=%d)",
                ml_target, ae_max_offers, sh_max_offers, max_offers)

    channels = parse_channels(dc if dashboard_url else None)
    logger.info("Canais configurados: %s", ", ".join(ch.name for ch in channels))

    sender_tg = TelegramSender(bot_token)

    zap_token = os.environ.get("ZAP_API_TOKEN", "")
    zap_instance = os.environ.get("ZAP_API_INSTANCE_ID", "")
    sender_wp = WhatsAppSender(zap_token, zap_instance) if zap_token and zap_instance else None

    categories = [c.strip() for c in category.split(",")] if category else [""]
    promo_types = [""] if promotion_type else ["", "lightning"]

    all_offers = []
    sent_ids = load_sent_ids()
    sent_ids_set = set(sent_ids.keys())
    for ci, cat in enumerate(categories):
        for ptype in promo_types:
            cat_label = cat if cat else "todas"
            pt_label = f"promotion_type={ptype}" if ptype else "todas"
            logger.info("Buscando ofertas [%s, %s]...", cat_label, pt_label)
            scraper = MercadoLivreScraper(category=cat, pages=pages, promotion_type=ptype)
            try:
                offers = scraper.scrape(
                    max_offers=ml_target,
                    seen_ids=sent_ids_set,
                    target_new=ml_target,
                    max_pages=ml_max_pages,
                )
            except Exception as e:
                logger.error("Erro ao buscar ofertas [%s, %s]: %s", cat_label, pt_label, e)
                continue
            for o in offers:
                sent_ids_set.add(o.id)
                all_offers.append(o)
            logger.info("  -> %d ofertas (%s, %s)", len(offers), cat_label, pt_label)
        if ci < len(categories) - 1:
            logger.info("Aguardando 2s antes da proxima categoria...")
            time.sleep(2)

    if ae_app_key and ae_app_secret:
        logger.info("Buscando ofertas do AliExpress...")
        ae_scraper = AliExpressScraper(
            app_key=ae_app_key,
            app_secret=ae_app_secret,
            tracking_id=ae_tracking_id,
            max_offers=ae_max_offers,
            category_ids=ae_category_ids,
            keywords=ae_keywords,
        )
        try:
            ae_offers = ae_scraper.scrape()
            for o in ae_offers:
                if o.id not in sent_ids_set:
                    sent_ids_set.add(o.id)
                    all_offers.append(o)
            logger.info("  -> %d ofertas do AliExpress", len(ae_offers))
        except Exception as e:
            logger.error("Erro ao buscar ofertas AliExpress: %s", e)
        time.sleep(2)

    if sh_app_id and sh_app_secret:
        logger.info("Buscando ofertas da Shopee...")
        sh_scraper = ShopeeScraper(
            app_id=sh_app_id,
            app_secret=sh_app_secret,
            max_offers=sh_max_offers,
            keywords=sh_keywords,
        )
        try:
            sh_offers = sh_scraper.scrape()
            for o in sh_offers:
                if o.id not in sent_ids_set:
                    sent_ids_set.add(o.id)
                    all_offers.append(o)
            logger.info("  -> %d ofertas da Shopee", len(sh_offers))
        except Exception as e:
            logger.error("Erro ao buscar ofertas Shopee: %s", e)
        time.sleep(2)

    offers_found = len(all_offers)
    logger.info("Total coletado: %d ofertas", offers_found)

    if not all_offers:
        logger.info("Nenhuma oferta encontrada")
        if dashboard_run_id:
            _report_dashboard_run(dashboard_url, dashboard_key, dashboard_run_id,
                                  "success", offers_found, 0, 0)
        return

    offers = _balance_offers(all_offers, max_offers)

    channel_to_offers = defaultdict(list)
    for offer in offers:
        ch = match_channel(offer, channels)
        if ch and offer.id not in sent_ids:
            channel_to_offers[ch.name].append(offer)

    total_new = sum(len(v) for v in channel_to_offers.values())
    if total_new == 0:
        logger.info("Nenhuma oferta nova para enviar")
        if dashboard_run_id:
            _report_dashboard_run(dashboard_url, dashboard_key, dashboard_run_id,
                                  "success", offers_found, 0, 0)
        return

    logger.info("Enviando ofertas (%d novas no total, delay %ds entre cada)", total_new, send_delay)

    all_sent_offers_data = []
    total_sent = 0
    first = True

    for channel in channels:
        channel_offers = channel_to_offers.get(channel.name, [])[:max_offers]
        if not channel_offers:
            continue

        sources = [o.product_id[:2] for o in channel_offers if len(o.product_id) >= 2]
        logger.info("Canal '%s': %d ofertas para enviar [%s]",
                     channel.name, len(channel_offers), ",".join(sources))

        for offer in channel_offers:
            if not first:
                logger.info("Aguardando %d segundos...", send_delay)
                time.sleep(send_delay)
            first = False

            try:
                if offer.product_id.startswith("ML"):
                    offer.url = make_affiliate_url(offer.clean_url, affiliate_tag)
                else:
                    offer.url = offer.clean_url
            except Exception as e:
                logger.error("Falha ao gerar URL para '%s': %s", offer.title[:40], e)
                continue

            ok_tg = False
            if channel.telegram_chat_id:
                try:
                    sender_tg.send_offer(channel.telegram_chat_id, offer)
                    ok_tg = True
                    src = offer.product_id[:2] if len(offer.product_id) >= 2 else "??"
                    logger.info("[%s][%s] Telegram: %s", channel.name, src, offer.title[:60])
                except Exception as e:
                    logger.error("[%s] Falha no Telegram: %s", channel.name, e)

            ok_wp = False
            if channel.whatsapp_group_jid and sender_wp:
                try:
                    sender_wp.send_offer(channel.whatsapp_group_jid, offer)
                    ok_wp = True
                    logger.info("[%s] WhatsApp: %s", channel.name, offer.title[:60])
                except Exception as e:
                    logger.error("[%s] Falha no WhatsApp: %s", channel.name, e)

            if ok_tg or ok_wp:
                sent_ids[offer.id] = time.time()
                total_sent += 1
                all_sent_offers_data.append({
                    "product_id": offer.product_id,
                    "title": offer.title,
                    "price": offer.current_price,
                    "discount": offer.discount_label,
                    "clean_url": offer.clean_url,
                    "image_url": offer.image_url,
                })

    if total_sent > 0:
        save_sent_ids(sent_ids)

    logger.info("Concluido. %d oferta(s) enviada(s) no total", total_sent)

    if dashboard_run_id:
        _report_dashboard_run(
            dashboard_url, dashboard_key, dashboard_run_id,
            "success" if total_sent > 0 else "error",
            offers_found, total_sent, total_new,
            sent_offers=all_sent_offers_data,
        )


if __name__ == "__main__":
    main()
