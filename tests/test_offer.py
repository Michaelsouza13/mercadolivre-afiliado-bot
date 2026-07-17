import sys
sys.path.insert(0, "src")

from scraper import Offer


def test_discount_percent_from_label():
    o = Offer(title="Produto", product_id="MLB1", current_price=50, discount_label="40% OFF")
    assert o.discount_percent == 40


def test_discount_percent_from_prices():
    o = Offer(title="Produto", product_id="MLB1", current_price=60, old_price=100)
    assert o.discount_percent == 40


def test_discount_percent_zero_when_no_data():
    o = Offer(title="Produto", product_id="MLB1", current_price=60)
    assert o.discount_percent == 0


def test_source_ml():
    assert Offer(title="X", product_id="MLB1", current_price=10).source == "Mercado Livre"


def test_source_ae():
    assert Offer(title="X", product_id="AE1", current_price=10).source == "AliExpress"


def test_source_sh():
    assert Offer(title="X", product_id="SH1", current_price=10).source == "Shopee"


def test_source_fallback():
    assert Offer(title="X", product_id="XX1", current_price=10).source == "Oferta"


def test_has_free_shipping():
    o = Offer(title="X", product_id="MLB1", current_price=10, shipping_tags=["free_shipping"])
    assert o.has_free_shipping is True
    assert o.has_full_shipping is False


def test_has_full_shipping():
    o = Offer(title="X", product_id="MLB1", current_price=10, shipping_tags=["fulfillment"])
    assert o.has_full_shipping is True
    assert o.has_free_shipping is True


def test_no_shipping():
    o = Offer(title="X", product_id="MLB1", current_price=10)
    assert o.has_free_shipping is False
    assert o.has_full_shipping is False


class TestScore:
    def test_score_based_on_discount(self):
        o = Offer(title="X", product_id="MLB1", current_price=60, old_price=100)
        assert o.score == 40.0

    def test_score_coupon_bonus(self):
        o = Offer(title="X", product_id="AE1", current_price=50,
                  old_price=100, promo_code="AE123", promo_value="R$ 20 OFF")
        assert o.score == 65.0

    def test_score_coupon_label_bonus(self):
        o = Offer(title="X", product_id="MLB1", current_price=50,
                  old_price=100, coupon_label="Cupom de R$ 10")
        assert o.score == 65.0

    def test_score_free_shipping_bonus(self):
        o = Offer(title="X", product_id="MLB1", current_price=50,
                  old_price=100, shipping_tags=["free_shipping"])
        assert o.score == 60.0

    def test_score_full_shipping_bonus(self):
        o = Offer(title="X", product_id="MLB1", current_price=50,
                  old_price=100, shipping_tags=["fulfillment"])
        assert o.score == 65.0

    def test_score_installments_bonus(self):
        o = Offer(title="X", product_id="MLB1", current_price=50,
                  old_price=100, installments_qty=12, installment_value=4.99)
        assert o.score == 55.0

    def test_score_all_bonuses(self):
        o = Offer(title="X", product_id="MLB1", current_price=50,
                  old_price=100, promo_code="PROMO", shipping_tags=["fulfillment"],
                  installments_qty=12, installment_value=4.99)
        assert o.score == 85.0