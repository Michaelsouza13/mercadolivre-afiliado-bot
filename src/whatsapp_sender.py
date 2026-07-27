import logging
import random

import requests

from utils import format_price

logger = logging.getLogger(__name__)

CTA_PHRASES = [
    "Aproveite antes que acabe!",
    "Corre que \u00E9 oportunidade!",
    "Oferta por tempo limitado!",
    "Garanta a sua agora!",
    "N\u00E3o perca essa chance!",
]


class WhatsAppSender:
    API_BASE = "https://api.zap-api.tech/v1"

    def __init__(self, api_token: str, instance_id: str):
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }
        self.api_url = f"{self.API_BASE}/instances/{instance_id}/send"

    def send_message(self, group_jid: str, text: str) -> bool:
        resp = requests.post(
            self.api_url,
            json={
                "phone": group_jid,
                "type": "text",
                "body": text,
            },
            headers=self.headers,
            timeout=15,
        )
        if not resp.ok:
            logger.error("ZAP-API send error %s: %s", resp.status_code, resp.text)
            resp.raise_for_status()
        return True

    def send_image(self, group_jid: str, image_url: str, caption: str) -> bool:
        resp = requests.post(
            self.api_url,
            json={
                "phone": group_jid,
                "type": "image",
                "mediaUrl": image_url,
                "caption": caption,
            },
            headers=self.headers,
            timeout=15,
        )
        if not resp.ok:
            logger.error("ZAP-API image error %s: %s", resp.status_code, resp.text)
            resp.raise_for_status()
        return True

    def send_offer(self, group_jid: str, offer, headline=None, platform_emoji="") -> bool:
        message = self._format_offer_message(offer, headline, platform_emoji)
        if offer.image_url:
            try:
                return self.send_image(group_jid, offer.image_url, message)
            except Exception as e:
                logger.warning("Falha ao enviar imagem no WhatsApp, enviando so texto: %s", e)
        return self.send_message(group_jid, message)

    def _format_offer_message(self, offer, headline=None, platform_emoji="") -> str:
        title = offer.title.strip()
        current = format_price(offer.current_price)
        old = format_price(offer.old_price) if offer.old_price else ""
        discount = offer.discount_label.strip() if offer.discount_label else ""
        url = offer.url.strip()

        if headline and platform_emoji:
            first_line = f"*{headline}* {platform_emoji}"
        elif headline:
            first_line = f"*{headline}*"
        else:
            platform = offer.source.upper()
            first_line = f"\U0001F525 *PROMOÇÃO {platform}* \U0001F525"

        lines = [
            first_line,
            "",
            f"\U0001F4CC *{title}*",
        ]

        if old:
            lines.append(f"\U0001F4B0 De: ~{old}~")
        lines.append(f"\U0001F525 Por: *{current}*")

        if discount:
            lines.append(f"\U0001F3AF {discount}")

        if offer.installments_qty > 1 and offer.installment_value > 0:
            iv = format_price(offer.installment_value)
            lines.append(f"\U0001F4B3 {offer.installments_qty}x de {iv} sem juros")

        if offer.promo_code:
            lines.append(f"\U0001F39F *Cupom:* {offer.promo_code}")
            if offer.promo_value:
                lines.append(f"\U0001F4CB {offer.promo_value}")
        elif offer.coupon_label:
            lines.append(f"\U0001F39F {offer.coupon_label}")

        lines.extend([
            "",
            f"\U0001F6D2 {url}",
            "",
            f"\U0001F4E2 {random.choice(CTA_PHRASES)}",
        ])

        return "\n".join(lines)
