import hashlib
import logging
import time as time_module
from datetime import datetime
from typing import List, Optional

import requests

from scraper import Offer

logger = logging.getLogger(__name__)

API_URL = "https://api-sg.aliexpress.com/sync"
METHOD_HOTPRODUCT = "aliexpress.affiliate.hotproduct.query"


class AliExpressScraper:
    def __init__(self, app_key: str, app_secret: str, tracking_id: str,
                 max_offers: int = 5, category_ids: str = "",
                 currency: str = "BRL", language: str = "pt_BR",
                 ship_country: str = "BR", timeout: int = 30):
        self.app_key = app_key
        self.app_secret = app_secret
        self.tracking_id = tracking_id
        self.max_offers = max_offers
        self.category_ids = category_ids
        self.currency = currency
        self.language = language
        self.ship_country = ship_country
        self.timeout = timeout
        self.session = requests.Session()

    def _sign(self, params: dict) -> str:
        filtered = {k: v for k, v in params.items()
                    if k != "sign" and v is not None and str(v).strip() != ""}
        sorted_keys = sorted(filtered.keys())
        raw = self.app_secret
        for k in sorted_keys:
            raw += f"{k}{filtered[k]}"
        raw += self.app_secret
        return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()

    def _call(self, method: str, params: dict) -> Optional[dict]:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "method": method,
            "app_key": self.app_key,
            "timestamp": timestamp,
            "format": "json",
            "v": "2.0",
            "sign_method": "md5",
        }
        payload.update(params)
        payload = {k: v for k, v in payload.items()
                   if v is not None and str(v).strip() != ""}
        payload["sign"] = self._sign(payload)

        try:
            resp = self.session.post(API_URL, data=payload, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("AliExpress API error: %s", e)
            return None

    def _parse_price(self, value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def scrape(self) -> List[Offer]:
        if self.max_offers <= 0:
            return []

        page_size = min(self.max_offers, 50)
        params = {
            "tracking_id": self.tracking_id,
            "local_currency": self.currency,
            "target_language": self.language,
            "ship_to_country": self.ship_country,
            "page_no": "1",
            "page_size": str(page_size),
            "sort": "SALE_PRICE_ASC",
        }
        if self.category_ids:
            params["category_ids"] = self.category_ids

        data = self._call(METHOD_HOTPRODUCT, params)
        if not data:
            return []

        offers = []

        if "error_response" in data:
            err = data["error_response"]
            logger.warning("AliExpress: erro da API: code=%s msg=%s",
                           err.get("code"), err.get("msg"))
            return []

        try:
            resp = data["aliexpress_affiliate_hotproduct_query_response"]
        except KeyError:
            logger.warning("AliExpress: resposta inesperada (chaves: %s)",
                           list(data.keys()))
            return []

        resp_result = resp.get("resp_result", {})
        resp_code = resp_result.get("resp_code", "200")
        if resp_code != "200":
            logger.warning("AliExpress: resp_code=%s resp_msg=%s",
                           resp_code, resp_result.get("resp_msg", ""))
            return []

        result = resp_result.get("result")
        if not result:
            logger.warning("AliExpress: sem 'result' na resposta")
            return []

        products_data = result.get("products", {})
        products = products_data.get("product", [])
        if not products:
            logger.info("AliExpress: nenhum produto retornado")
            return []

        for item in products:
            try:
                product_id = str(item.get("product_id", ""))
                if not product_id:
                    continue

                title = item.get("product_title", "").strip()
                if not title:
                    continue

                current_price = self._parse_price(item.get("sale_price", "0"))
                old_price = self._parse_price(item.get("original_price", "0"))
                if old_price == 0 or old_price <= current_price:
                    old_price = None

                discount_label = item.get("discount", "")

                image_url = item.get("product_main_image_url", "")

                raw_url = item.get("promotion_link", "")
                if raw_url.startswith("https://") or raw_url.startswith("http://"):
                    product_url = raw_url.split("://", 1)[1]
                else:
                    product_url = raw_url

                offers.append(Offer(
                    title=title,
                    product_id=f"AE{product_id}",
                    current_price=current_price,
                    old_price=old_price,
                    discount_label=discount_label,
                    image_url=image_url,
                    product_url=product_url,
                ))
            except Exception as e:
                logger.debug("AliExpress: erro ao processar item: %s", e)
                continue

        logger.info("AliExpress: %d ofertas encontradas", len(offers))
        return offers[:self.max_offers]
