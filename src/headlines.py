import ast
import json
import logging
import random
import re
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
FALLBACK_MODELS = [
    "google/gemma-4-26b-a4b-it:free",
    "openai/gpt-oss-20b:free",
    "openrouter/free",
]
RETRY_DELAY = 2

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


def _do_request(api_key: str, model: str, messages: list) -> Optional[str]:
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "max_tokens": 1000,
                "temperature": 0.8,
            },
            timeout=30,
        )
        if not resp.ok:
            logger.warning("OpenRouter error %s [%s]: %s", resp.status_code, model, resp.text[:300])
            return None
        data = resp.json()
        raw = data["choices"][0]["message"]["content"]
        logger.info("OpenRouter [%s]: %s", model, raw[:300])
        return raw
    except Exception as e:
        logger.warning("OpenRouter request failed [%s]: %s", model, e)
        return None


def _call_openrouter(offers: list, api_key: str, model: str) -> Optional[str]:
    if not api_key:
        return None

    titles = [o.title.strip() for o in offers]
    lines = "\n".join(f'{i+1}. "{t}"' for i, t in enumerate(titles))

    system_msg = (
        "Voce e um copywriter de e-commerce brasileiro, criativo e descontraido. "
        "Gere headlines curtas (max 7 palavras) em CAIXA ALTA, "
        "no estilo 'zoacao entre amigos'. "
        "Cada headline deve ser UNICA e relevante ao produto, "
        "nunca generica. SEM frases como 'OFERTA IMPERDIVEL' ou 'NAO PERCA'. "
        "Responda APENAS com o array JSON, sem explicacao."
    )

    user_msg = (
        'Exemplos:\n'
        '- Monitor Gamer AOC 27 144Hz -> "ESSE AQUI E PRA JOGAR AQUELE CSGO"\n'
        '- Fone Bluetooth JBL Tune 510BT -> "PRA FAZER AQUELA FESTA NO CHURRAS"\n'
        '- Aspirador Electrolux em Inox -> "SUA CASA EMPOEIRADA, NUNCA MAIS"\n\n'
        "Agora gere para:\n"
        f"{lines}\n\n"
        'Formato: [{"id": 1, "headline": "HEADLINE"}, ...]'
    )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    models_to_try = [model] if model else FALLBACK_MODELS

    for i, mdl in enumerate(models_to_try):
        if i > 0:
            time.sleep(RETRY_DELAY)

        logger.info("OpenRouter tentando [%s] (tentativa %d/%d)...", mdl, i + 1, len(models_to_try))
        raw = _do_request(api_key, mdl, messages)
        if raw is not None:
            return raw

        if i == 0 and not model:
            logger.info("  Gemini falhou, retentando em %ds...", RETRY_DELAY)
            time.sleep(RETRY_DELAY)
            raw = _do_request(api_key, mdl, messages)
            if raw is not None:
                return raw

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
    pairs = re.findall(r'["\']id["\']\s*:\s*(\d+)\s*,\s*["\']headline["\']\s*:\s*["\']([^"\']+)["\']', text)
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
        if data and not isinstance(data[0], dict):
            items = [{"id": i + 1, "headline": str(v)} for i, v in enumerate(data) if v]
        else:
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


def _normalize_json(text: str) -> str:
    text = text.strip().lstrip('\ufeff')
    text = re.sub(r"(?<=[{,\s])'(?=[^\])}:,])", '"', text)
    text = re.sub(r"'(?=\s*[:,}\]])", '"', text)
    text = re.sub(r',\s*([}\]])', r'\1', text)
    text = re.sub(r'(?<![{"\w])(\w+)(?=\s*:)', r'"\1"', text)
    return text


def _try_literal_eval(text: str, product_ids: list) -> Optional[dict]:
    try:
        data = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None
    return _extract_from_data(data, product_ids)


def _parse_openrouter_response(text: str, product_ids: list) -> Optional[dict]:
    text = _normalize_json(text)
    estrategias = [
        _try_direct_json,
        _try_extract_json_block,
        _try_extract_array,
        _try_regex_pairs,
        _try_literal_eval,
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
    for o in offers:
        h = parsed.get(o.id, "")
        if h:
            pid = getattr(o, "product_id", o.id)
            logger.info("  HEADLINE [%s] %s -> %s", pid, o.title[:50], h)
    return parsed
