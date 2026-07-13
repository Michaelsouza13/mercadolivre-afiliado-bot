import json
import logging
import re
import time
from typing import List, Optional

import requests

from scraper import Offer

logger = logging.getLogger(__name__)

SEARCH_URL = "https://shopee.com.br/api/v4/search/search_items"
TIMEOUT = 30


class ShopeeScraper:
    def __init__(self, max_offers: int = 5, keywords: str = "",
                 min_discount: int = 5, affiliate_tag: str = "",
                 timeout: int = TIMEOUT):
        self.max_offers = max_offers
        self.keywords = keywords
        self.min_discount = min_discount
        self.affiliate_tag = affiliate_tag
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            "Referer": "https://shopee.com.br/",
            "x-api-source": "pc",
            "Origin": "https://shopee.com.br",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        })

    def _search(self, keyword: str, page: int = 0,
                limit: int = 60) -> Optional[dict]:
        params = {
            "keyword": keyword,
            "page": page,
            "limit": limit,
            "sortBy": "sales",
        }
        try:
            resp = self.session.get(
                SEARCH_URL, params=params, timeout=self.timeout
            )
            if resp.status_code == 403:
                logger.warning("Shopee: bloqueado (403)")
                return None
            if resp.status_code == 429:
                logger.warning("Shopee: rate limit (429)")
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.JSONDecodeError:
            logger.warning("Shopee: resposta nao JSON")
            return None
        except Exception as e:
            logger.error("Shopee API error: %s", e)
            return None

    def _parse_price(self, value) -> float:
        try:
            return float(value) / 100.0 if value > 0 else 0.0
        except (TypeError, ValueError):
            return 0.0

    def scrape(self) -> List[Offer]:
        if self.max_offers <= 0:
            return []

        keywords = [k.strip() for k in self.keywords.split(",") if k.strip()]
        if not keywords:
            keywords = ["promocao", "oferta", "desconto"]

        all_products = []
        seen_ids = set()

        for kw in keywords:
            if len(all_products) >= self.max_offers:
                break
            logger.info("Shopee: buscando '%s'...", kw)
            data = self._search(kw)
            if not data:
                continue

            items = data.get("items", [])
            if not items:
                logger.info("Shopee: sem resultados para '%s'", kw)
                continue

            for item in items:
                if len(all_products) >= self.max_offers:
                    break
                try:
                    item_id = item.get("item_id", 0)
                    shop_id = item.get("shop_id", 0)
                    if not item_id or not shop_id:
                        continue

                    product_id = f"SH{item_id}"
                    if product_id in seen_ids:
                        continue
                    seen_ids.add(product_id)

                    title = (item.get("name") or item.get("item_name", "")).strip()
                    if not title:
                        continue

                    raw_price_min = item.get("price_min", 0)
                    raw_price_max = item.get("price_max", 0)
                    raw_price_before = item.get("price_before_discount", 0)

                    current_price = self._parse_price(raw_price_min)
                    old_price = self._parse_price(raw_price_before)

                    if old_price == 0 or old_price <= current_price:
                        old_price = current_price * 1.3

                    discount = item.get("discount", "")
                    if not discount and old_price > current_price:
                        pct = int((1 - current_price / old_price) * 100)
                        discount = f"{pct}% OFF"

                    image_url = item.get("image", "")
                    if not image_url:
                        image_url = (item.get("images", [None]) or [None])[0] or ""

                    product_url_base = f"https://shopee.com.br/product/{shop_id}/{item_id}"
                    product_url = ""
                    if product_url_base.startswith("https://") or product_url_base.startswith("http://"):
                        product_url = product_url_base.split("://", 1)[1]
                    else:
                        product_url = product_url_base

                    all_products.append(Offer(
                        title=title,
                        product_id=product_id,
                        current_price=current_price,
                        old_price=old_price,
                        discount_label=discount,
                        image_url=image_url,
                        product_url=product_url,
                    ))
                except Exception as e:
                    logger.debug("Shopee: erro item: %s", e)
                    continue

            time.sleep(1)

        logger.info("Shopee: %d ofertas encontradas", len(all_products))
        return all_products[:self.max_offers]
