import json
import logging
import re
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class Offer:
    def __init__(self, title: str, product_id: str, current_price: float,
                 old_price: Optional[float] = None,
                 discount_label: str = "", image_url: str = "",
                 product_url: str = ""):
        self.title = title
        self.product_id = product_id
        self.current_price = current_price
        self.old_price = old_price
        self.discount_label = discount_label
        self.image_url = image_url
        self._product_url = product_url

    @property
    def id(self) -> str:
        return self.product_id

    @property
    def clean_url(self) -> str:
        if self._product_url:
            return f"https://{self._product_url}"
        return f"https://www.mercadolivre.com.br/p/{self.product_id}"

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "product_id": self.product_id,
            "current_price": self.current_price,
            "old_price": self.old_price,
            "discount_label": self.discount_label,
            "image_url": self.image_url,
        }


class MercadoLivreScraper:
    BASE_URL = "https://www.mercadolivre.com.br/ofertas"

    CATEGORIAS = {
        "celulares": "MLB1051",
        "eletronicos": "MLB1000",
        "informatica": "MLB1648",
        "eletrodomesticos": "MLB1144",
        "casa": "MLB1073",
        "moda": "MLB1430",
        "esportes": "MLB1276",
        "ferramentas": "MLB1500",
        "brinquedos": "MLB1132",
        "supermercado": "MLB1403",
        "automotivo": "MLB1743",
        "moveis": "MLB1892",
        "pet": "MLB1071",
        "saude": "MLB1407",
        "bebes": "MLB1384",
    }

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    def __init__(self, category: str = "", pages: int = 1, promotion_type: str = "", timeout: int = 30):
        self.category = category
        self.pages = pages
        self.promotion_type = promotion_type
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def _make_url(self, page: int) -> str:
        url = self.BASE_URL
        params = {}
        if self.category:
            params["category"] = self.CATEGORIAS.get(self.category.lower(), self.category)
        if self.promotion_type:
            params["promotion_type"] = self.promotion_type
        if page > 1:
            params["page"] = str(page)
        if params:
            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
        return url

    def scrape(self, max_offers: int = 20) -> List[Offer]:
        import time

        seen = set()
        all_offers = []

        for page in range(1, self.pages + 1):
            if page > 1:
                time.sleep(1.5)

            url = self._make_url(page)
            logger.info("Buscando pagina %d/%d...", page, self.pages)

            try:
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                resp.encoding = "utf-8"
            except Exception as e:
                logger.warning("Erro na pagina %d: %s", page, e)
                continue

            page_offers = self._extract_from_json(resp.text)
            if not page_offers:
                page_offers = self._extract_from_html(resp.text)

            for offer in page_offers:
                if offer.id not in seen:
                    seen.add(offer.id)
                    all_offers.append(offer)

            logger.info("  -> %d ofertas encontradas nessa pagina", len(page_offers))
            if not page_offers:
                break

        logger.info("Total de %d ofertas unicas em %d pagina(s)", len(all_offers), self.pages)
        return all_offers[:max_offers]

    def _extract_from_json(self, html: str) -> List[Offer]:
        match = re.search(r'_n\.ctx\.r\s*=\s*(\{.+?\});', html, re.DOTALL)
        if not match:
            return []

        try:
            ctx = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []

        app_props = ctx.get("appProps", {})
        page_props = app_props.get("pageProps", {})
        data = page_props.get("data", {})
        items = data.get("items", [])

        offers = []
        for item in items:
            try:
                card = item.get("card", {})
                meta = card.get("metadata", {})
                product_id = meta.get("id", "")
                if not product_id:
                    continue

                components = card.get("components", [])
                title = ""
                current_price = 0.0
                old_price = None
                discount_label = ""

                for comp in components:
                    ctype = comp.get("type")

                    if ctype == "title":
                        title = comp.get("title", {}).get("text", "")

                    if ctype == "price":
                        price_data = comp.get("price", {})
                        current = price_data.get("current_price", {})
                        current_price = current.get("value", 0.0)
                        previous = price_data.get("previous_price", {})
                        if previous.get("value"):
                            old_price = previous["value"]
                        discount = price_data.get("discount_label", {})
                        discount_label = discount.get("text", "")

                if not title or not product_id:
                    continue

                image_url = ""
                pics = card.get("pictures", {}).get("pictures", [])
                if pics:
                    image_url = (
                        f"https://http2.mlstatic.com/D_{pics[0]['id']}-O.jpg"
                    )

                product_url = meta.get("url", "")
                offers.append(Offer(
                    title=title,
                    product_id=product_id,
                    current_price=current_price,
                    old_price=old_price,
                    discount_label=discount_label,
                    image_url=image_url,
                    product_url=product_url,
                ))
            except Exception as e:
                logger.debug("Error parsing item: %s", e)
                continue

        return offers

    def _extract_from_html(self, html: str) -> List[Offer]:
        soup = BeautifulSoup(html, "html.parser")
        offers = []
        seen = set()

        for link in soup.find_all("a", href=re.compile(r"/p/MLB\d+")):
            href = link.get("href", "")
            match = re.search(r"/p/(MLB\d+)", href)
            if not match:
                continue
            pid = match.group(1)
            if pid in seen:
                continue
            seen.add(pid)

            title = link.get("title", "") or link.get_text(strip=True)
            offers.append(Offer(
                title=title,
                product_id=pid,
                current_price=0.0,
                product_url=href,
            ))

        return offers
