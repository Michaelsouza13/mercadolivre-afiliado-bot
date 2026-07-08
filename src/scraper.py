import json
import logging
import re
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class Offer:
    def __init__(self, title: str, url: str, current_price: str,
                 old_price: str = "", discount: str = "",
                 image_url: str = ""):
        self.title = title
        self.url = url
        self.current_price = current_price
        self.old_price = old_price
        self.discount = discount
        self.image_url = image_url

    @property
    def id(self) -> str:
        return self.url

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "current_price": self.current_price,
            "old_price": self.old_price,
            "discount": self.discount,
            "image_url": self.image_url,
        }


class MercadoLivreScraper:
    OFFERS_URL = "https://www.mercadolivre.com.br/ofertas"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def scrape(self, max_offers: int = 20) -> List[Offer]:
        resp = self.session.get(
            self.OFFERS_URL,
            timeout=self.timeout
        )
        resp.raise_for_status()
        resp.encoding = "utf-8"

        soup = BeautifulSoup(resp.text, "html.parser")

        offers = self._extract_jsonld(soup)
        if offers:
            logger.info("Extracted %d offers via JSON-LD", len(offers))
            return offers[:max_offers]

        offers = self._extract_initial_state(soup)
        if offers:
            logger.info("Extracted %d offers via __INITIAL_STATE__", len(offers))
            return offers[:max_offers]

        offers = self._extract_html(soup)
        logger.info("Extracted %d offers via HTML parsing", len(offers))
        return offers[:max_offers]

    def _extract_jsonld(self, soup: BeautifulSoup) -> List[Offer]:
        offers = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if data.get("@type") == "ItemList":
                        for item in data.get("itemListElement", []):
                            product = item
                            if isinstance(item, dict) and "item" in item:
                                product = item["item"]
                            offer = self._parse_ld_product(product)
                            if offer:
                                offers.append(offer)
                    elif data.get("@type") == "Product":
                        offer = self._parse_ld_product(data)
                        if offer:
                            offers.append(offer)
            except (json.JSONDecodeError, AttributeError):
                continue
        return offers

    def _parse_ld_product(self, data: dict) -> Optional[Offer]:
        try:
            title = data.get("name", "")
            url = data.get("url", "")
            image = ""
            img_data = data.get("image")
            if isinstance(img_data, dict):
                image = img_data.get("url", "")
            elif isinstance(img_data, str):
                image = img_data

            offers_data = data.get("offers", {})
            if isinstance(offers_data, dict):
                offers_data = [offers_data]

            current_price = ""
            for offer_data in offers_data if isinstance(offers_data, list) else []:
                if isinstance(offer_data, dict) and offer_data.get("price"):
                    current_price = str(offer_data["price"])
                    break

            if title and url and current_price:
                return Offer(
                    title=title, url=url,
                    current_price=current_price,
                    image_url=image,
                )
        except Exception as e:
            logger.debug("JSON-LD parse error: %s", e)
        return None

    def _extract_initial_state(self, soup: BeautifulSoup) -> List[Offer]:
        for script in soup.find_all("script"):
            if not script.string:
                continue
            text = script.string

            # Try common initial state patterns
            for var in ["__INITIAL_STATE__", "__PRELOADED_STATE__", "__NEXT_DATA__"]:
                pattern = re.compile(
                    rf"(?:window\.)?{var}\s*=\s*(\{{.+?\}});",
                    re.DOTALL
                )
                match = pattern.search(text)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        offers = self._extract_from_state(data)
                        if offers:
                            return offers
                    except json.JSONDecodeError:
                        continue

        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                offers = self._extract_from_state(data)
                if offers:
                    return offers
            except json.JSONDecodeError:
                pass

        return []

    def _extract_from_state(self, obj: dict, depth: int = 0) -> List[Offer]:
        offers = []
        if depth > 6:
            return offers

        if isinstance(obj, dict):
            if "name" in obj and "url" in obj:
                title = str(obj.get("name", ""))
                url = str(obj.get("url", ""))
                prices = obj.get("prices", obj.get("price", {}))
                if isinstance(prices, (int, float)):
                    current_price = str(prices)
                elif isinstance(prices, dict):
                    current_price = str(prices.get("current_price", prices.get("price", "")))
                else:
                    current_price = str(prices) if prices else ""

                old_price = ""
                discount = ""
                if isinstance(prices, dict):
                    old_price = str(prices.get("old_price", ""))
                    discount = str(prices.get("discount", ""))

                if title and url and current_price and current_price != "0":
                    image = ""
                    images = obj.get("images", obj.get("image", ""))
                    if isinstance(images, list) and images:
                        img = images[0]
                        image = img if isinstance(img, str) else img.get("url", "")
                    elif isinstance(images, str):
                        image = images

                    offers.append(Offer(
                        title=title, url=url,
                        current_price=current_price,
                        old_price=old_price,
                        discount=discount,
                        image_url=image,
                    ))

            for value in obj.values():
                offers.extend(self._extract_from_state(value, depth + 1))

        elif isinstance(obj, list):
            for item in obj:
                offers.extend(self._extract_from_state(item, depth + 1))

        return offers

    def _extract_html(self, soup: BeautifulSoup) -> List[Offer]:
        offers = []
        seen_urls = set()

        product_links = soup.find_all(
            "a", href=re.compile(r"/(?:p/MLB|produto/|item/|MLB)")
        )
        if not product_links:
            product_links = soup.find_all(
                "a", href=re.compile(r"mercadolivre\.com\.br")
            )

        for link in product_links:
            href = link.get("href", "").strip()
            product_url = href.split("?")[0]

            if product_url in seen_urls or not product_url:
                continue
            seen_urls.add(product_url)

            container = link.find_parent(["div", "li", "section"]) or link.parent

            title = (link.get("title", "")
                     or link.get_text(strip=True)
                     or "")
            title_el = container.find(["h2", "h3"], class_=re.compile(r"(title|name)", re.I))
            if title_el:
                title = title_el.get_text(strip=True)

            prices = re.findall(
                r"R\$\s*([\d\s.]+,\d{2})",
                container.get_text()
            )
            current_price = prices[-1] if prices else ""
            old_price = prices[0] if len(prices) > 1 else ""

            discount_el = container.find(class_=re.compile(r"(discount|off|badge|desconto)", re.I))
            discount = discount_el.get_text(strip=True) if discount_el else ""

            img = container.find("img")
            image_url = (img.get("src", "")
                         or img.get("data-src", "")) if img else ""

            if title and (current_price or old_price):
                offers.append(Offer(
                    title=title, url=product_url,
                    current_price=current_price,
                    old_price=old_price,
                    discount=discount,
                    image_url=image_url,
                ))

        return offers
