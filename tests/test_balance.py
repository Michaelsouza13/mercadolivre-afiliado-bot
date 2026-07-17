import sys
sys.path.insert(0, "src")

from bot import _balance_offers
from scraper import Offer


def _ml(title, price=100):
    return Offer(title=title, product_id="MLB1", current_price=price)


def _ae(title, price=100):
    return Offer(title=title, product_id="AE1", current_price=price)


def _sh(title, price=100):
    return Offer(title=title, product_id="SH1", current_price=price)


def test_balance_empty():
    assert _balance_offers([], 21) == []


def test_balance_zero_max():
    assert _balance_offers([_ml("X")], 0) == []


class TestQuota:
    def test_even_distribution(self):
        result = _balance_offers([_ml("M1"), _ml("M2"), _ml("M3"),
                                  _ae("A1"), _ae("A2"), _ae("A3"),
                                  _sh("S1"), _sh("S2"), _sh("S3")], 9)
        assert len(result) == 9
        ml = [o for o in result if o.product_id[:2] == "ML"]
        ae = [o for o in result if o.product_id[:2] == "AE"]
        sh = [o for o in result if o.product_id[:2] == "SH"]
        assert len(ml) == 3
        assert len(ae) == 3
        assert len(sh) == 3

    def test_gap_filled_by_others(self):
        result = _balance_offers([_ml("M1"), _ml("M2"), _ml("M3"),
                                  _ae("A1")], 9)
        assert len(result) == 4
        ml = [o for o in result if o.product_id[:2] == "ML"]
        ae = [o for o in result if o.product_id[:2] == "AE"]
        assert len(ml) == 3
        assert len(ae) == 1

    def test_sh_only(self):
        result = _balance_offers([_sh("S1"), _sh("S2"), _sh("S3")], 9)
        assert len(result) == 3
        assert all(o.product_id[:2] == "SH" for o in result)

    def test_respects_max_offers(self):
        offers = [_ml(f"M{i}") for i in range(10)] + \
                 [_ae(f"A{i}") for i in range(10)] + \
                 [_sh(f"S{i}") for i in range(10)]
        result = _balance_offers(offers, 10)
        assert len(result) == 10

    def test_interleave_order(self):
        result = _balance_offers([_ml("M1"), _ml("M2"),
                                  _ae("A1"), _ae("A2"),
                                  _sh("S1"), _sh("S2")], 6)
        prefixes = [o.product_id[:2] for o in result]
        # Should alternate: ML, AE, SH, ML, AE, SH
        assert prefixes == ["ML", "AE", "SH", "ML", "AE", "SH"]

    def test_quota_with_21(self):
        offers = [_ml(f"M{i}") for i in range(21)] + \
                 [_ae(f"A{i}") for i in range(21)] + \
                 [_sh(f"S{i}") for i in range(21)]
        result = _balance_offers(offers, 21)
        assert len(result) == 21
        ml = [o for o in result if o.product_id[:2] == "ML"]
        ae = [o for o in result if o.product_id[:2] == "AE"]
        sh = [o for o in result if o.product_id[:2] == "SH"]
        assert len(ml) == 7
        assert len(ae) == 7
        assert len(sh) == 7