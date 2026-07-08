import logging
import os
import sys
from urllib.parse import urlencode, urlparse, urlunparse

from scraper import MercadoLivreScraper
from storage import load_sent_ids, save_sent_ids
from telegram_sender import TelegramSender

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


def format_price(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    for var in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]:
        if var not in os.environ:
            logger.error("Missing required env var: %s", var)
            sys.exit(1)

    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    affiliate_tag = os.environ.get("AFFILIATE_TAG", "")
    category = os.environ.get("ML_CATEGORY", "")
    pages = int(os.environ.get("ML_PAGES", "1"))
    max_offers = int(os.environ.get("MAX_OFFERS_PER_RUN", "5"))
    promotion_type = os.environ.get("ML_PROMOTION_TYPE", "")

    sender = TelegramSender(bot_token)

    promo_types = [""] if promotion_type else ["", "lightning"]

    all_offers = []
    seen_ids = set()
    for ptype in promo_types:
        label = f"promotion_type={ptype}" if ptype else "todas"
        logger.info("Buscando ofertas (%s)...", label)
        scraper = MercadoLivreScraper(category=category, pages=pages, promotion_type=ptype)
        try:
            offers = scraper.scrape()
        except Exception as e:
            logger.error("Erro ao buscar ofertas (%s): %s", label, e)
            continue
        for o in offers:
            if o.id not in seen_ids:
                seen_ids.add(o.id)
                all_offers.append(o)
        logger.info("  -> %d ofertas (%s)", len(offers), label)

    offers = all_offers

    if not offers:
        logger.info("Nenhuma oferta encontrada")
        return

    logger.info("Encontradas %d ofertas no total (apos dedup)", len(offers))

    sent_ids = load_sent_ids()
    new_offers = [o for o in offers if o.id not in sent_ids]

    if not new_offers:
        logger.info("Nenhuma oferta nova para enviar")
        return

    to_send = new_offers[:max_offers]
    logger.info("Enviando %d de %d ofertas novas", len(to_send), len(new_offers))

    sent_count = 0
    for offer in to_send:
        try:
            offer.url = make_affiliate_url(offer.clean_url, affiliate_tag)
            sender.send_offer(chat_id, offer)
            sent_ids.add(offer.id)
            sent_count += 1
            logger.info("Enviada: %s", offer.title[:60])
        except Exception as e:
            logger.error("Falha ao enviar '%s': %s", offer.title[:40], e)

    if sent_count > 0:
        save_sent_ids(sent_ids)

    logger.info("Concluido. %d oferta(s) enviada(s)", sent_count)


if __name__ == "__main__":
    main()
