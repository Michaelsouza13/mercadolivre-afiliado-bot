import json
import logging
import random
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
FALLBACK_MODEL = "meta-llama/llama-3.1-8b-instruct"

HEADLINES_KEYWORDS = [
    (["perfume", "colonia", "essencia", "fragrancia", "cosmetico", "batom",
      "maquiagem", "hidratante", "protetor solar", "shampoo", "condicionador",
      "desodorante", "gloss", "serum", "delineador", "paleta", "sabonete",
      "oleo corporal", "loçao", "perfumaria", "leave-in", "oleo capilar",
      "reparador capilar", "maskara capilar", "protetor labial"],
     ["CHEIROSO ASSIM TU CONQUISTA A GATINHA FIT",
      "PERFUME DE QUALIDADE, PRECO DE FABRICA"]),
    (["fone", "bluetooth", "headset", "audio", "caixa som", "microfone",
      "fone cancelamento"],
     ["SOM DE QUALIDADE SEM GASTAR MUITO"]),
    (["smartwatch", "relogio", "pulseira inteligente", "smart band"],
     ["NAO PERCA TEMPO, FIQUE CONECTADO"]),
    (["tapete", "cortina", "quadro", "espelho", "papel parede",
      "painel", "revestimento", "manta", "almofada", "luminaria",
      "cortina blackout", "ripado", "adnet", "jogo de cama", "toalha"],
     ["DECORE SUA CASA SEM PESAR NO BOLSO"]),
    (["creatina", "suplemento", "whey", "pre treino", "vitamina",
      "termogenico", "bcaa", "albumina", "pasta de amendoim"],
     ["META FITNESS? COM ESSE PRECO FICA FACIL"]),
    (["celular", "smartphone", "iphone", "samsung", "motorola", "xiaomi"],
     ["TECNOLOGIA QUE CABE NO SEU BOLSO"]),
    (["tv", "televisao", "monitor", "led", "oled", "smart tv"],
     ["IMAGEM PERFEITA, PRECO IMPERDIVEL"]),
    (["notebook", "laptop", "ultrabook", "macbook", "chromebook"],
     ["PRODUTIVIDADE SEM GASTAR MUITO"]),
    (["paintball", "marcador", "mascara paintball", "bola paintball", "co2"],
     ["PESADO? PREPARA O BOLSO"]),
    (["drone", "camera seguranca", "webcam", "camera digital"],
     ["MOMENTOS INESQUECIVEIS COM O MELHOR PRECO"]),
    (["tapete sala", "tapete banheiro", "tapete cozinha"],
     ["CONFORTO E ESTILO PARA SEU LAR"]),
    (["ferramenta", "parafusadeira", "furadeira", "serra", "kit ferramenta"],
     ["FERRAMENTAS COM PRECO DE FABRICA"]),
    (["brinquedo", "jogo", "boneco", "carrinho", "video game", "controle"],
     ["DIVERSÃO GARANTIDA, PRECO IMPERDIVEL"]),
    (["ventilador", "climatizador", "ar condicionado", "umidificador"],
     ["FRESCURA QUE CABE NO SEU ORCAMENTO"]),
    (["pet", "cachorro", "gato", "racao", "brinquedo pet"],
     ["SEU PET MERECE O MELHOR"]),
    (["livro", "kindle", "ebook", "leitura"],
     ["CONHECIMENTO QUE TRANSFORMA VIDAS"]),
    (["teclado", "mouse gamer", "gamer", "cadeira gamer", "monitor gamer"],
     ["GAMER DE VERDADE NAO PERDE ESSA"]),
]

FALLBACKS = [
    "OFERTA IMPERDIVEL",
    "VOCE NAO VAI ACREDITAR NESSE PRECO",
    "ECONOMIA QUE FAZ A DIFERENCA",
    "OPORTUNIDADE UNICA",
    "CORRE QUE E PROMO",
]


def _call_openrouter(offers: list, api_key: str, model: str) -> Optional[str]:
    if not api_key:
        return None
    model = model or FALLBACK_MODEL
    titles = [o.title.strip() for o in offers]
    lines = "\n".join(f'{i+1}. "{t}"' for i, t in enumerate(titles))

    prompt = (
        "Gere headlines curtas, EM CAIXA ALTA, max 7 palavras, "
        "tom informal e chamativo, para cada produto abaixo.\n"
        "Responda APENAS com um array JSON, sem markdown, sem explicacao.\n\n"
        "Produtos:\n"
        f"{lines}\n\n"
        'Formato: [{"id": 1, "headline": "HEADLINE"}, ...]'
    )

    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "plugins": [{"id": "response-healing"}],
                "max_tokens": 500,
                "temperature": 0.8,
            },
            timeout=30,
        )
        if not resp.ok:
            logger.warning("OpenRouter error %s: %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        raw = data["choices"][0]["message"]["content"]
        logger.debug("OpenRouter raw: %s", raw[:300])
        return raw
    except Exception as e:
        logger.warning("OpenRouter request failed: %s", e)
        return None


def _try_direct_json(text: str, product_ids: list) -> Optional[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return _extract_from_data(data, product_ids)


def _try_extract_json_block(text: str, product_ids: list) -> Optional[dict]:
    for pattern in [r'```(?:json)?\s*([\s\S]*?)\s*```', r'`([\s\S]*?)`']:
        match = re.search(pattern, text)
        if match:
            try:
                data = json.loads(match.group(1))
                return _extract_from_data(data, product_ids)
            except (json.JSONDecodeError, KeyError):
                continue
    return None


def _try_extract_array(text: str, product_ids: list) -> Optional[dict]:
    match = re.search(r'(\[.*?\])', text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            return _extract_from_data(data, product_ids)
        except (json.JSONDecodeError, KeyError):
            pass
    return None


def _try_regex_pairs(text: str, product_ids: list) -> Optional[dict]:
    pairs = re.findall(r'"id"\s*:\s*(\d+)\s*,\s*"headline"\s*:\s*"([^"]+)"', text)
    if len(pairs) >= len(product_ids) * 0.5:
        result = {}
        for idx_str, headline in pairs:
            idx = int(idx_str) - 1
            if 0 <= idx < len(product_ids):
                validated = _validar_headline(headline)
                if validated:
                    result[product_ids[idx]] = validated
        return result if len(result) >= len(product_ids) * 0.5 else None
    return None


def _extract_from_data(data, product_ids: list) -> Optional[dict]:
    headlines = {}
    items = []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        if "headlines" in data:
            items = data["headlines"]
        elif "data" in data:
            items = data["data"]
        else:
            for k, v in data.items():
                try:
                    idx = int(k)
                    if isinstance(v, str):
                        items.append({"id": idx, "headline": v})
                    elif isinstance(v, dict) and "headline" in v:
                        items.append({"id": idx, "headline": v["headline"]})
                except ValueError:
                    pass

    for item in items:
        if not isinstance(item, dict):
            continue
        idx = item.get("id") or item.get("index") or item.get("n") or item.get("product_id")
        if idx is None:
            continue
        try:
            idx = int(idx) - 1
        except (ValueError, TypeError):
            continue
        if idx < 0 or idx >= len(product_ids):
            continue
        headline = (item.get("headline") or item.get("title") or
                    item.get("text") or item.get("h1") or item.get("h2") or "")
        validated = _validar_headline(headline)
        if validated:
            headlines[product_ids[idx]] = validated

    return headlines if headlines else None


def _validar_headline(texto: str) -> Optional[str]:
    texto = texto.strip().upper()
    if len(texto) < 5 or len(texto) > 80:
        return None
    if not any(c.isalpha() for c in texto):
        return None
    import html
    return html.escape(texto)


def _parse_openrouter_response(text: str, product_ids: list) -> Optional[dict]:
    estrategias = [
        _try_direct_json,
        _try_extract_json_block,
        _try_extract_array,
        _try_regex_pairs,
    ]
    for fn in estrategias:
        result = fn(text, product_ids)
        if result:
            if len(set(result.values())) < len(result) * 0.5:
                logger.warning("Muitas headlines repetidas, descartando IA")
                return None
            return result
    return None


def _fallback_keywords(offers: list) -> dict:
    result = {}
    for o in offers:
        title_lower = o.title.lower()
        matched = None
        for keywords, headlines_list in HEADLINES_KEYWORDS:
            if any(kw in title_lower for kw in keywords):
                matched = random.choice(headlines_list)
                break
        if matched:
            result[o.id] = matched
        else:
            result[o.id] = random.choice(FALLBACKS)
    return result


def get_headlines(offers: list, api_key: str = "", model: str = "") -> dict:
    if not offers:
        return {}

    product_ids = [o.id for o in offers]
    ia_ok = 0
    kw_ok = 0

    raw = _call_openrouter(offers, api_key, model)
    if raw:
        parsed = _parse_openrouter_response(raw, product_ids)
        if parsed:
            ia_ok = len(parsed)
            remaining = [o for o in offers if o.id not in parsed]
        else:
            remaining = offers
    else:
        remaining = offers

    if remaining:
        kw = _fallback_keywords(remaining)
        kw_ok = len(kw)
        if ia_ok > 0:
            parsed.update(kw)
        else:
            parsed = kw

    logger.info("Headlines: %d via IA, %d via fallback (%d ofertas)",
                ia_ok, kw_ok, len(offers))
    return parsed
