import logging

import requests

logger = logging.getLogger(__name__)


class WhatsAppSender:
    API_BASE = "https://graph.facebook.com/v21.0"

    def __init__(self, phone_number_id: str, access_token: str):
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.api_url = f"{self.API_BASE}/{phone_number_id}/messages"

    def _send(self, to: str, payload: dict) -> bool:
        resp = requests.post(
            self.api_url,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                **payload,
            },
            timeout=15,
        )
        if not resp.ok:
            logger.error("WhatsApp API error %s: %s", resp.status_code, resp.text)
            resp.raise_for_status()
        return True

    def send_text(self, to: str, text: str) -> bool:
        return self._send(to, {"type": "text", "text": {"body": text}})

    def send_offer(self, to: str, offer) -> bool:
        message = self._format_offer_message(offer)
        return self.send_text(to, message)

    def _format_price(self, raw: str) -> str:
        raw = raw.strip().replace(" ", "")
        if "," in raw and "." in raw:
            raw = raw.replace(".", "").replace(",", ",")
        elif raw.isdigit() or raw.replace(".", "").isdigit():
            try:
                val = float(raw.replace(",", "."))
                raw = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            except ValueError:
                pass
        return raw

    def _format_offer_message(self, offer) -> str:
        title = offer.title.strip()
        current = self._format_price(offer.current_price)
        old = self._format_price(offer.old_price) if offer.old_price else ""
        discount = offer.discount.strip() if offer.discount else ""
        url = offer.url.strip()

        lines = [
            "\u{1F525} *PROMO\u00C7\u00C3O DO MERCADO LIVRE* \u{1F525}",
            "",
            f"\u{1F4CC} *{title}*",
        ]

        if old and old != current:
            lines.append(f"\u{1F4B0} De: ~~R$ {old}~~")
        lines.append(f"\u{1F525} Por: *R$ {current}*")

        if discount:
            lines.append(f"\u{1F3AF} {discount}")

        lines.extend([
            "",
            "\u{1F6D2} *Compre agora com meu link:*",
            url,
            "",
            "\u{1F4E3} Aproveite antes que acabe!",
        ])

        return "\n".join(lines)
