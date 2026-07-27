import json
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, "src")

from headlines import (
    FALLBACKS,
    _call_openrouter,
    _extract_from_data,
    _fallback_keywords,
    _parse_openrouter_response,
    _try_direct_json,
    _try_extract_array,
    _try_extract_json_block,
    _try_regex_pairs,
    _validar_headline,
    get_headlines,
)


class MockOffer:
    def __init__(self, title, product_id):
        self.title = title
        self.id = product_id


@pytest.fixture
def offers():
    return [
        MockOffer("Perfume Montblanc Explorer 100ml", "MLB123"),
        MockOffer("Fone Bluetooth JBL Tune 510BT", "MLB456"),
        MockOffer("Tapete Sala 2m x 1.5m", "MLB789"),
    ]


@pytest.fixture
def product_ids():
    return ["MLB123", "MLB456", "MLB789"]


class TestValidarHeadline:
    def test_valid_headline(self):
        assert _validar_headline("OFERTA IMPERDIVEL") == "OFERTA IMPERDIVEL"

    def test_too_short(self):
        assert _validar_headline("OI") is None

    def test_too_long(self):
        assert _validar_headline("A" * 81) is None

    def test_no_letters(self):
        assert _validar_headline("123!!!") is None

    def test_uppercase_conversion(self):
        result = _validar_headline("Oferta boa")
        assert result == "OFERTA BOA"

    def test_html_escape(self):
        result = _validar_headline("OFERTA <3")
        assert "&lt;" in result


class TestExtractFromData:
    def test_list_format(self, product_ids):
        data = [{"id": 1, "headline": "OFERTA BOA"}, {"id": 2, "headline": "PROMO LEGAL"}]
        result = _extract_from_data(data, product_ids)
        assert result["MLB123"] == "OFERTA BOA"
        assert result["MLB456"] == "PROMO LEGAL"

    def test_dict_with_headlines_key(self, product_ids):
        data = {"headlines": [{"id": 1, "headline": "TOP DEMAIS"}]}
        result = _extract_from_data(data, product_ids)
        assert result["MLB123"] == "TOP DEMAIS"

    def test_numeric_keys(self, product_ids):
        data = {"1": "PRIMEIRA OFERTA", "2": "SEGUNDA OFERTA"}
        result = _extract_from_data(data, product_ids)
        assert result["MLB123"] == "PRIMEIRA OFERTA"
        assert result["MLB456"] == "SEGUNDA OFERTA"

    def test_invalid_item_skipped(self, product_ids):
        data = [{"id": 99, "headline": "MUITO LONGE"}, {"id": 1, "headline": "OFERTA VALIDA"}]
        result = _extract_from_data(data, product_ids)
        assert "MLB123" in result
        assert result["MLB123"] == "OFERTA VALIDA"


class TestTryDirectJson:
    def test_valid_json(self, product_ids):
        text = '[{"id": 1, "headline": "PROMO TOP"}]'
        result = _try_direct_json(text, product_ids)
        assert result["MLB123"] == "PROMO TOP"

    def test_invalid_json(self, product_ids):
        result = _try_direct_json("not json", product_ids)
        assert result is None


class TestTryExtractJsonBlock:
    def test_markdown_json(self, product_ids):
        text = '```json\n[{"id": 1, "headline": "PROMO TOP"}]\n```'
        result = _try_extract_json_block(text, product_ids)
        assert result["MLB123"] == "PROMO TOP"

    def test_backtick_block(self, product_ids):
        text = '`[{"id": 1, "headline": "PROMO TOP"}]`'
        result = _try_extract_json_block(text, product_ids)
        assert result["MLB123"] == "PROMO TOP"


class TestTryExtractArray:
    def test_extract_array(self, product_ids):
        text = 'Aqui estao os dados [{"id": 1, "headline": "PROMO TOP"}] espero que goste'
        result = _try_extract_array(text, product_ids)
        assert result["MLB123"] == "PROMO TOP"


class TestTryRegexPairs:
    def test_regex_pairs(self, product_ids):
        text = '{"id": 1, "headline": "TOP DEMAIS"}, {"id": 2, "headline": "SEGUNDA FEIRA"}, {"id": 3, "headline": "MEGA OFERTA"}'
        result = _try_regex_pairs(text, product_ids)
        assert result is not None
        assert "TOP DEMAIS" in result.values()
        assert "MEGA OFERTA" in result.values()


class TestParseOpenRouterResponse:
    def test_valid_response(self, product_ids):
        text = '[{"id": 1, "headline": "PROMO TOP"}, {"id": 2, "headline": "PROMO LEGAL"}]'
        result = _parse_openrouter_response(text, product_ids)
        assert result["MLB123"] == "PROMO TOP"
        assert result["MLB456"] == "PROMO LEGAL"

    def test_invalid_response(self, product_ids):
        result = _parse_openrouter_response("nada aqui", product_ids)
        assert result is None

    def test_repeated_headlines_rejected(self, product_ids):
        text = '[{"id": 1, "headline": "OFERTA TOP"}, {"id": 2, "headline": "OFERTA TOP"}, {"id": 3, "headline": "OFERTA TOP"}]'
        result = _parse_openrouter_response(text, product_ids)
        assert result is None


class TestCallOpenRouter:
    @patch("headlines.requests.post")
    def test_success(self, mock_post, offers):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"choices": [{"message": {"content": '[{"id": 1, "headline": "PROMO TOP"}]'}}]}
        mock_post.return_value = mock_resp

        result = _call_openrouter(offers, "sk-test", "test-model")
        assert result is not None
        assert "PROMO TOP" in result

    @patch("headlines.requests.post")
    def test_http_error(self, mock_post, offers):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 401
        mock_post.return_value = mock_resp

        result = _call_openrouter(offers, "sk-test", "test-model")
        assert result is None

    @patch("headlines.requests.post")
    def test_network_error(self, mock_post, offers):
        mock_post.side_effect = Exception("Network error")
        result = _call_openrouter(offers, "sk-test", "test-model")
        assert result is None

    def test_no_api_key(self, offers):
        result = _call_openrouter(offers, "", "")
        assert result is None


class TestFallbackKeywords:
    def test_perfume_match(self):
        offers = [MockOffer("Perfume Importado 100ml", "MLB1")]
        result = _fallback_keywords(offers)
        assert "CHEIROSO" in result["MLB1"] or "PERFUME" in result["MLB1"]

    def test_fone_match(self):
        offers = [MockOffer("Fone Bluetooth JBL", "MLB2")]
        result = _fallback_keywords(offers)
        assert "SOM" in result["MLB2"]

    def test_fallback_generic(self):
        offers = [MockOffer("Produto Aleatorio XYZ 123", "MLB3")]
        result = _fallback_keywords(offers)
        assert result["MLB3"] in FALLBACKS

    def test_multiple_offers(self):
        offers = [
            MockOffer("Perfume Nacional", "MLB1"),
            MockOffer("Tapete Sala", "MLB2"),
            MockOffer("Coisa Estranha", "MLB3"),
        ]
        result = _fallback_keywords(offers)
        assert "CHEIROSO" in result["MLB1"] or "PERFUME" in result["MLB1"]
        assert "DECORE" in result["MLB2"] or "CASA" in result["MLB2"]
        assert result["MLB3"] in FALLBACKS


class TestGetHeadlines:
    def test_empty_offers(self):
        result = get_headlines([])
        assert result == {}

    def test_no_api_key_uses_fallback(self, offers):
        result = get_headlines(offers, api_key="")
        assert len(result) == 3
        for headline in result.values():
            assert len(headline) >= 5

    def test_fallback_never_empty_string(self, offers):
        result = get_headlines(offers, api_key="")
        for headline in result.values():
            assert headline != ""
            assert headline is not None
