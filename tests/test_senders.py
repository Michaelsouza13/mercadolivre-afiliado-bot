import sys
sys.path.insert(0, "src")

from telegram_sender import TelegramSender
from whatsapp_sender import WhatsAppSender
from scraper import Offer


def _offer(**kw):
    defaults = dict(title="Produto Teste", product_id="MLB1", current_price=89.90)
    defaults.update(kw)
    o = Offer(**defaults)
    o.url = o.clean_url
    return o


class TestTelegramFormat:
    def setup_method(self):
        self.sender = TelegramSender("fake:token")

    def test_basic_offer(self):
        o = _offer()
        msg = self.sender._format_offer_message(o)
        assert "MERCADO LIVRE" in msg
        assert "Produto Teste" in msg
        assert "R$ 89,90" in msg
        assert "Ver Oferta" in msg

    def test_with_discount(self):
        o = _offer(old_price=149.90, discount_label="40% OFF")
        msg = self.sender._format_offer_message(o)
        assert "R$ 149,90" in msg
        assert "R$ 89,90" in msg
        assert "40% OFF" in msg

    def test_with_coupon_code(self):
        o = _offer(promo_code="AE123", promo_value="R$ 20 OFF")
        msg = self.sender._format_offer_message(o)
        assert "Cupom:" in msg
        assert "AE123" in msg
        assert "R$ 20 OFF" in msg

    def test_with_coupon_label(self):
        o = _offer(coupon_label="Cupom de R$ 20")
        msg = self.sender._format_offer_message(o)
        assert "Cupom de R$ 20" in msg

    def test_with_free_shipping(self):
        o = _offer(shipping_tags=["free_shipping"])
        msg = self.sender._format_offer_message(o)
        assert "Frete Grátis" in msg

    def test_with_full_shipping(self):
        o = _offer(shipping_tags=["fulfillment"])
        msg = self.sender._format_offer_message(o)
        assert "Frete Grátis FULL" in msg

    def test_with_installments(self):
        o = _offer(installments_qty=12, installment_value=7.49)
        msg = self.sender._format_offer_message(o)
        assert "12x de R$ 7,49" in msg

    def test_aliExpress_source(self):
        o = _offer(product_id="AE12345")
        msg = self.sender._format_offer_message(o)
        assert "ALIEXPRESS" in msg

    def test_shopee_source(self):
        o = _offer(product_id="SH12345")
        msg = self.sender._format_offer_message(o)
        assert "SHOPEE" in msg

    def test_cta_present(self):
        o = _offer()
        msg = self.sender._format_offer_message(o)
        assert "📢" in msg or "🔥" in msg or "⚡" in msg or "💥" in msg or "🙌" in msg


class TestWhatsAppFormat:
    def setup_method(self):
        self.sender = WhatsAppSender("fake", "fake")

    def test_basic_offer(self):
        o = _offer()
        msg = self.sender._format_offer_message(o)
        assert "MERCADO LIVRE" in msg
        assert "Produto Teste" in msg
        assert "R$ 89,90" in msg

    def test_with_discount_and_old_price(self):
        o = _offer(old_price=149.90, discount_label="40% OFF")
        msg = self.sender._format_offer_message(o)
        assert "R$ 149,90" in msg
        assert "R$ 89,90" in msg
        assert "40% OFF" in msg

    def test_with_coupon(self):
        o = _offer(promo_code="AE123")
        msg = self.sender._format_offer_message(o)
        assert "Cupom:" in msg
        assert "AE123" in msg

    def test_with_installments(self):
        o = _offer(installments_qty=10, installment_value=8.99)
        msg = self.sender._format_offer_message(o)
        assert "10x de R$ 8,99" in msg

    def test_cta_present(self):
        o = _offer()
        msg = self.sender._format_offer_message(o)
        assert any(e in msg for e in ["📢", "🔥", "⚡", "💥", "🙌"])