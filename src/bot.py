import logging
import os
import sys

from scraper import MercadoLivreScraper
from storage import load_sent_ids, save_sent_ids
from telegram_sender import TelegramSender

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    for var in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]:
        if var not in os.environ:
            logger.error("Missing required env var: %s", var)
            sys.exit(1)

    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    affiliate_param = os.environ.get("AFFILIATE_PARAM", "")
    max_offers = int(os.environ.get("MAX_OFFERS_PER_RUN", "5"))

    scraper = MercadoLivreScraper()
    sender = TelegramSender(bot_token)

    logger.info("Scraping Mercado Livre offers...")
    try:
        offers = scraper.scrape()
    except Exception as e:
        logger.error("Failed to scrape: %s", e)
        sys.exit(2)

    if not offers:
        logger.info("No offers found on page")
        return

    logger.info("Found %d offers total", len(offers))

    sent_ids = load_sent_ids()
    new_offers = [o for o in offers if o.id not in sent_ids]

    if not new_offers:
        logger.info("No new offers to send (all already sent)")
        return

    to_send = new_offers[:max_offers]
    logger.info("Sending %d of %d new offers", len(to_send), len(new_offers))

    sent_count = 0
    for offer in to_send:
        try:
            if affiliate_param:
                sep = "&" if "?" in offer.url else "?"
                offer.url = f"{offer.url}{sep}{affiliate_param.lstrip('?&')}"

            sender.send_offer(chat_id, offer)
            sent_ids.add(offer.id)
            sent_count += 1
            logger.info("Sent: %s", offer.title[:60])
        except Exception as e:
            logger.error("Failed to send '%s': %s", offer.title[:40], e)

    if sent_count > 0:
        save_sent_ids(sent_ids)

    logger.info("Done. Sent %d offer(s) successfully", sent_count)


if __name__ == "__main__":
    main()
