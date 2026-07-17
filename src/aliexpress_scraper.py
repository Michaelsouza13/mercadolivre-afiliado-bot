import hashlib
import logging
import time as time_module
from datetime import datetime
from typing import List, Optional

import requests

from scraper import Offer

logger = logging.getLogger(__name__)

API_URL = "https://api-sg.aliexpress.com/sync"
METHOD_PRODUCT_QUERY = "aliexpress.affiliate.product.query"


class AliExpressScraper:
    def __init__(self, app_key: str, app_secret: str, tracking_id: str,
                 max_offers: int = 5, category_ids: str = "",
                 keywords: str = "",
                 currency: str = "BRL", language: str = "PT",
                 ship_country: str = "BR", timeout: int = 30):
        self.app_key = app_key
        self.app_secret = app_secret
        self.tracking_id = tracking_id
        self.max_offers = max_offers
        self.category_ids = category_ids
        self.keywords = keywords
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
            resp = self.session.get(API_URL, params=payload, timeout=self.timeout)
            resp.raise_for_status()
            j = resp.json()
            if "error_response" in j:
                err = j["error_response"]
                logger.warning("AliExpress raw error: %s", resp.text[:800])
            return j
        except Exception as e:
            logger.error("AliExpress API error: %s", e)
            if hasattr(e, 'response') and e.response is not None:
                logger.warning("AliExpress response body: %s", e.response.text[:800])
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
            "target_currency": self.currency,
            "target_language": self.language,
            "page_no": "1",
            "page_size": str(page_size),
            "sort": "LAST_VOLUME_DESC",
            "fields": "product_id,product_title,product_small_image_urls,product_main_image_url,target_app_sale_price,target_sale_price,app_sale_price,sale_price,target_original_price,original_price,discount,promotion_link,product_detail_url,promo_code_info",
        }
        if self.tracking_id:
            params["tracking_id"] = self.tracking_id
        if self.category_ids:
            params["category_ids"] = self.category_ids
        elif self.keywords:
            params["keywords"] = self.keywords
        else:
            params["keywords"] = "fone"

        data = self._call(METHOD_PRODUCT_QUERY, params)
        if not data:
            return []

        offers = []

        if "error_response" in data:
            err = data["error_response"]
            logger.warning("AliExpress: erro da API: code=%s msg=%s",
                           err.get("code"), err.get("msg"))
            return []

        try:
            resp = (data.get("aliexpress_affiliate_hotproduct_query_response")
                    or data["aliexpress_affiliate_product_query_response"])
        except KeyError:
            logger.warning("AliExpress: resposta inesperada (chaves: %s)",
                           list(data.keys()))
            return []

        resp_result = resp.get("resp_result", {})
        resp_code = resp_result.get("resp_code", 200)
        if str(resp_code) != "200":
            logger.warning("AliExpress: resp_code=%s resp_msg=%s raw=%s",
                           resp_code, resp_result.get("resp_msg", ""),
                           str(data)[:500])
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
                product_id = str(item.get("product_id", "") or "")
                if not product_id:
                    continue

                title = (item.get("product_title", "") or "").strip()
                if not title:
                    continue

                raw_prices = {
                    "target_app_sale_price": item.get("target_app_sale_price"),
                    "target_sale_price": item.get("target_sale_price"),
                    "app_sale_price": item.get("app_sale_price"),
                    "sale_price": item.get("sale_price"),
                }
                logger.debug("AE raw price fields for '%s': %s", title[:40], raw_prices)

                current_price = self._parse_price(
                    item.get("target_app_sale_price")
                    or item.get("target_sale_price")
                    or item.get("app_sale_price")
                    or item.get("sale_price", "0")
                )
                raw_old = {
                    "target_original_price": item.get("target_original_price"),
                    "original_price": item.get("original_price"),
                }
                raw_discount = item.get("discount", "")
                logger.debug("AE old_price fields: %s | discount=%s", raw_old, raw_discount)

                old_price = self._parse_price(
                    item.get("target_original_price")
                    or item.get("original_price", "0")
                )
                if old_price == 0 or old_price <= current_price:
                    old_price = None

                discount_label = raw_discount

                promo_code_info = item.get("promo_code_info", {}) or {}
                promo_code = promo_code_info.get("promo_code", "") or ""
                promo_value = promo_code_info.get("code_value", "") or ""

                img_list = item.get("product_small_image_urls", {})
                image_url = img_list.get("string", [None])[0] if isinstance(img_list, dict) else item.get("product_main_image_url", "")

                raw_url = item.get("promotion_link") or item.get("product_detail_url", "")
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
                    promo_code=promo_code,
                    promo_value=promo_value,
                ))
            except Exception as e:
                logger.debug("AliExpress: erro ao processar item: %s", e)
                continue

        logger.info("AliExpress: %d ofertas encontradas", len(offers))
        return offers[:self.max_offers]
