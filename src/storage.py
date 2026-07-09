import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
CACHE_FILE = CACHE_DIR / "sent_offers.json"
MAX_CACHE_SIZE = 5000
CACHE_EXPIRY_DAYS = int(os.environ.get("CACHE_EXPIRY_DAYS", "7"))

CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_sent_ids() -> dict:
    now = time.time()
    cutoff = now - CACHE_EXPIRY_DAYS * 86400
    if not CACHE_FILE.exists():
        logger.info("No cache file found, starting fresh")
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            valid = {k: v for k, v in data.items() if v >= cutoff}
            expired = len(data) - len(valid)
            if expired:
                logger.info("Expired %d old entries from cache", expired)
            return valid
        logger.warning("Invalid cache format, resetting")
        return {}
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load cache (%s), resetting", e)
        return {}


def save_sent_ids(ids: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    trimmed = dict(list(ids.items())[-MAX_CACHE_SIZE:])
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False)
    logger.info("Saved %d sent offer IDs to cache", len(trimmed))
