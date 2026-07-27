# Plano: Paintball Afiliado Bot

Repositório novo, separado do bot principal.
```
github.com/Michaelsouza13/paintball-afiliado-bot
```

---

## Estrutura de arquivos

```
paintball-afiliado-bot/
├── bot.py                # Orquestrador simplificado (~350 linhas)
├── scraper.py            # Offer + MercadoLivreScraper (cópia fiel)
├── shopee_scraper.py     # ShopeeScraper (cópia fiel)
├── telegram_sender.py    # TelegramSender (cópia fiel)
├── storage.py            # Cache FIFO (so muda CACHE_DIR)
├── utils.py              # format_price (cópia fiel)
├── main.py               # Entry point (importa bot.main)
├── requirements.txt      # So requests + beautifulsoup4
├── .env.example          # Template de env vars
├── .github/
│   └── workflows/
│       └── paintball.yml # GH Actions
└── cache/                # Cache do paintball (criado automaticamente)
```

---

## 1. Arquivos que copiar IGUAL do projeto atual

Nenhuma alteracao necessaria. Copiar literalmente.

### scraper.py

De: `mercadolivre-afiliado-bot/src/scraper.py` → `paintball-afiliado-bot/scraper.py`

Contem a classe `Offer` (com score, parcelamento, frete, source) e `MercadoLivreScraper` (scraping ML).

### shopee_scraper.py

De: `mercadolivre-afiliado-bot/src/shopee_scraper.py` → `paintball-afiliado-bot/shopee_scraper.py`

Contem `ShopeeScraper` com API GraphQL, retry via RuntimeError, assinatura SHA256.

### telegram_sender.py

De: `mercadolivre-afiliado-bot/src/telegram_sender.py` → `paintball-afiliado-bot/telegram_sender.py`

Contem `TelegramSender` com CTA variado, parcelamento, frete, foto + texto.

### utils.py

De: `mercadolivre-afiliado-bot/src/utils.py` → `paintball-afiliado-bot/utils.py`

Contem `format_price()`.

---

## 2. Arquivos que PRECISAM de alteracao

### storage.py

Muda caminho do cache. Em vez de `src/../cache`, usa `./cache`:

```python
# storage.py
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent / "cache"   # <-- UNICA DIFERENCA
CACHE_FILE = CACHE_DIR / "sent_offers.json"
MAX_CACHE_SIZE = 2000

CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_sent_ids() -> dict:
    if not CACHE_FILE.exists():
        logger.info("No cache file found, starting fresh")
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            total = len(data)
            if total > MAX_CACHE_SIZE:
                logger.info("Cache cheia (%d), mantendo as %d mais recentes",
                            total, MAX_CACHE_SIZE)
                data = dict(list(data.items())[-MAX_CACHE_SIZE:])
            return data
        logger.warning("Invalid cache format, resetting")
        return {}
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load cache (%s), resetting", e)
        return {}


def save_sent_ids(ids: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    trimmed = dict(list(ids.items())[-MAX_CACHE_SIZE:])
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False)
    logger.info("Saved %d sent offer IDs to cache", len(trimmed))
```

### requirements.txt

So o essencial, sem dashboard:

```txt
requests>=2.28.0
beautifulsoup4>=4.11.0
```

### main.py

Entry point minimalista:

```python
import sys
import os

os.environ.setdefault("CACHE_DIR", os.path.join(os.path.dirname(__file__), "cache"))

from bot import main

if __name__ == "__main__":
    main()
```

### bot.py

Orquestrador simplificado. Baseado em `mercadolivre-afiliado-bot/src/bot.py` com estas alteracoes:

#### a) Imports

```python
import json
import logging
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional
from urllib.parse import urlencode, urlparse, urlunparse

import requests

from scraper import MercadoLivreScraper, Offer
from shopee_scraper import ShopeeScraper
from storage import load_sent_ids, save_sent_ids
from telegram_sender import TelegramSender
from utils import format_price
```

**Removido:** AliExpressScraper, WhatsAppSender, dataclass, field.

#### b) make_affiliate_url — manter IGUAL

Copiar do bot original (linhas 30-49).

#### c) Remover funcoes de dashboard

NAO copiar:
- `_fetch_dashboard_config`
- `_init_dashboard_run`
- `_report_dashboard_run`

#### d) Remover Channel/parse_channels/match_channel/_matches_keywords

NAO copiar. O paintball tem 1 canal fixo, sem multi-canais.

#### e) _retry_with_backoff — manter IGUAL

Copiar do bot original (linhas 201-212).

#### f) _send_error_alert — manter IGUAL

Copiar do bot original (linhas 215-226).

#### g) _interleave_offers — MUDAR para ["ML", "SH"]

```python
def _interleave_offers(offers: list) -> list:
    groups = defaultdict(list)
    for o in offers:
        prefix = o.product_id[:2]
        groups[prefix].append(o)
    result = []
    while any(groups.values()):
        for prefix in ["ML", "SH"]:     # <-- so 2 plataformas
            if groups[prefix]:
                result.append(groups[prefix].pop(0))
    return result
```

#### h) _balance_offers — MUDAR quota para //2 e prefixes para ["ML", "SH"]

```python
def _balance_offers(all_offers: list, max_offers: int) -> list:
    if not all_offers or max_offers <= 0:
        return []

    quota = max(max_offers // 2, 1)

    groups = defaultdict(list)
    for o in all_offers:
        groups[o.product_id[:2]].append(o)

    result = []

    for i in range(quota):
        for prefix in ["ML", "SH"]:
            pool = groups.get(prefix, [])
            if i < len(pool) and len(result) < max_offers:
                result.append(pool[i])

    remaining = _interleave_offers(
        [o for prefix in ["ML", "SH"]
         for o in groups.get(prefix, [])[quota:]]
    )
    for o in remaining:
        if len(result) >= max_offers:
            break
        result.append(o)

    logger.info("Balanceamento: quota=%d, total=%d, ML=%d SH=%d",
                quota, len(result),
                sum(1 for o in result if o.product_id[:2] == "ML"),
                sum(1 for o in result if o.product_id[:2] == "SH"))
    return result
```

#### i) _scrape_ml_task — manter IGUAL

Copiar do bot original (linhas 277-303). Sem alteracoes.

#### j) NAO copiar _scrape_ae_task

#### k) _scrape_sh_task — manter IGUAL

Copiar do bot original (linhas 329-348). Sem alteracoes.

#### l) main() — versao simplificada

```python
def main():
    for var in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]:
        if var not in os.environ:
            logger.error("Missing required env var: %s", var)
            sys.exit(1)

    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    affiliate_tag = os.environ.get("AFFILIATE_TAG", "")
    category = os.environ.get("ML_CATEGORY", "")
    pages = int(os.environ.get("ML_PAGES", "3"))
    ml_max_pages = int(os.environ.get("ML_MAX_PAGES", "20"))
    ml_max_offers = int(os.environ.get("ML_MAX_OFFERS", "0")) or 0
    max_offers = int(os.environ.get("MAX_OFFERS_PER_RUN", "10"))
    promotion_type = os.environ.get("ML_PROMOTION_TYPE", "")
    send_delay = int(os.environ.get("SEND_DELAY_SECONDS", "60"))

    sh_app_id = os.environ.get("SHOPEE_APP_ID", "")
    sh_app_secret = os.environ.get("SHOPEE_APP_SECRET", "")
    sh_max_offers = int(os.environ.get("SHOPEE_MAX_OFFERS", "5"))
    sh_keywords = os.environ.get("SHOPEE_KEYWORDS",
        "paintball,marcador paintball,mascara paintball,co2 paintball,"
        "bola paintball,equipamento paintball,kit paintball,"
        "carregador paintball,cilindro co2,calça paintball,luva paintball,"
        "colete paintball,gatilho paintball,aguia paintball,spyder paintball,"
        "tippmann paintball,dye paintball,planet eclipse")

    ml_target = ml_max_offers if ml_max_offers > 0 else max_offers
    logger.info("Limite de coleta: ML=%d SH=%d (max_offers=%d)",
                ml_target, sh_max_offers, max_offers)

    sender_tg = TelegramSender(bot_token)

    all_offers = []
    sent_ids = load_sent_ids()
    sent_ids_set = set(sent_ids.keys())

    logger.info("Iniciando scraping paralelo (ML, SH)...")
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(
                _scrape_ml_task, category, pages, ml_max_pages, ml_target, promotion_type, sent_ids_set.copy()
            ): "ML",
            executor.submit(
                _scrape_sh_task, sh_app_id, sh_app_secret, sh_max_offers, sh_keywords, sent_ids_set.copy()
            ): "SH",
        }

        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                for o in result:
                    if o.id not in sent_ids_set:
                        sent_ids_set.add(o.id)
                        all_offers.append(o)
                logger.info("Thread %s concluida: %d ofertas novas", name, len(result))
            except Exception as e:
                logger.error("Thread %s falhou: %s", name, e)

    elapsed = time.time() - t0
    logger.info("Scraping paralelo concluido em %.1fs: %d ofertas", elapsed, len(all_offers))

    offers_found = len(all_offers)
    logger.info("Total coletado: %d ofertas", offers_found)

    if not all_offers:
        logger.info("Nenhuma oferta encontrada")
        return

    offers = _balance_offers(all_offers, max_offers)

    new_offers = [o for o in offers if o.id not in sent_ids]

    if not new_offers:
        logger.info("Nenhuma oferta nova para enviar")
        return

    new_offers.sort(key=lambda o: o.score, reverse=True)

    logger.info("Enviando %d ofertas (delay %ds entre cada)", len(new_offers), send_delay)

    total_sent = 0
    for i, offer in enumerate(new_offers):
        if i > 0:
            logger.info("Aguardando %d segundos...", send_delay)
            time.sleep(send_delay)

        try:
            if offer.product_id.startswith("ML"):
                offer.url = make_affiliate_url(offer.clean_url, affiliate_tag)
            else:
                offer.url = offer.clean_url
        except Exception as e:
            logger.error("Falha ao gerar URL para '%s': %s", offer.title[:40], e)
            continue

        try:
            sender_tg.send_offer(chat_id, offer)
            sent_ids[offer.id] = time.time()
            total_sent += 1
            src = offer.product_id[:2] if len(offer.product_id) >= 2 else "??"
            logger.info("[%s] Telegram: %s", src, offer.title[:60])
        except Exception as e:
            logger.error("Falha no Telegram: %s", e)

    if total_sent > 0:
        save_sent_ids(sent_ids)

    logger.info("Concluido. %d oferta(s) enviada(s)", total_sent)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical("Bot falhou: %s", e, exc_info=True)
        _send_error_alert(str(e))
        sys.exit(1)
```

---

## 3. GitHub Actions — `.github/workflows/paintball.yml`

```yaml
name: Paintball Bot

on:
  schedule:
    - cron: '0 */2 * * *'   # a cada 2 horas
  workflow_dispatch:

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Instalar dependencias
        run: pip install -r requirements.txt
      - name: Executar bot
        run: python main.py
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          AFFILIATE_TAG: ${{ secrets.AFFILIATE_TAG }}
          ML_CATEGORY: "MLB1276"
          ML_PAGES: "3"
          ML_MAX_PAGES: "15"
          MAX_OFFERS_PER_RUN: "10"
          SEND_DELAY_SECONDS: "30"
          SHOPEE_APP_ID: ${{ secrets.SHOPEE_APP_ID }}
          SHOPEE_APP_SECRET: ${{ secrets.SHOPEE_APP_SECRET }}
          SHOPEE_MAX_OFFERS: "10"
          SHOPEE_KEYWORDS: "paintball,marcador paintball,mascara paintball,co2 paintball,bola paintball,equipamento paintball,kit paintball,carregador paintball,cilindro co2,calça paintball,luva paintball,colete paintball,gatilho paintball,aguia paintball,spyder paintball,tippmann paintball,dye paintball,planet eclipse"
```

---

## 4. `.env.example`

```bash
# Obrigatorios
TELEGRAM_BOT_TOKEN=seu_token_aqui
TELEGRAM_CHAT_ID=@seu_grupo_paintball

# Opcionais
AFFILIATE_TAG=sua_tag_ml
ML_CATEGORY=MLB1276
ML_PAGES=3
ML_MAX_PAGES=15
MAX_OFFERS_PER_RUN=10
ML_PROMOTION_TYPE=
SEND_DELAY_SECONDS=30

# Shopee (opcional, se nao configurar so busca ML)
SHOPEE_APP_ID=seu_app_id
SHOPEE_APP_SECRET=seu_app_secret
SHOPEE_MAX_OFFERS=10
SHOPEE_KEYWORDS=paintball,marcador paintball,mascara paintball,co2 paintball,bola paintball,equipamento paintball
```

---

## 5. Passo a passo para criar

```bash
# 1. Cria o repo no GitHub
#    Site: https://github.com/new
#    Nome: paintball-afiliado-bot
#    Publico, sem README, sem .gitignore, sem license

# 2. Clona localmente
git clone https://github.com/Michaelsouza13/paintball-afiliado-bot.git
cd paintball-afiliado-bot

# 3. Cria estrutura de pastas
mkdir -p .github/workflows cache

# 4. Copia arquivos que NAO mudam do projeto atual:
#    cp ../mercadolivre-afiliado-bot/src/scraper.py scraper.py
#    cp ../mercadolivre-afiliado-bot/src/shopee_scraper.py shopee_scraper.py
#    cp ../mercadolivre-afiliado-bot/src/telegram_sender.py telegram_sender.py
#    cp ../mercadolivre-afiliado-bot/src/utils.py utils.py

# 5. Cria os arquivos que MUDAM (conteudo neste documento):
#    bot.py, storage.py, main.py, requirements.txt, .env.example
#    .github/workflows/paintball.yml

# 6. Commit inicial
git add -A
git commit -m "Initial commit: paintball affiliate bot (ML + Shopee)"
git push -u origin main

# 7. Configurar secrets no GitHub
#    Settings > Secrets and variables > Actions > New repository secret
#    - TELEGRAM_BOT_TOKEN (token do bot do Telegram do grupo paintball)
#    - TELEGRAM_CHAT_ID (@nome_do_grupo_paintball)
#    - AFFILIATE_TAG (sua tag de afiliado ML, ex: "maikapromos-20")
#    - SHOPEE_APP_ID (seu app id da Shopee)
#    - SHOPEE_APP_SECRET (seu app secret da Shopee)

# 8. Ativar workflow
#    Actions > Paintball Bot > Enable
```

---

## 6. Resumo das diferencas

| Caracteristica | Principal | Paintball |
|---|---|---|
| Plataformas | ML + AE + SH | ML + SH |
| AliExpress | Sim | **Removido** |
| WhatsApp | Sim | **Removido** |
| Dashboard | Sim (Railway) | **Removido** |
| Multi-canais | Sim (keyword filtering) | **Removido** (1 canal fixo) |
| Balanceamento | quota = //3 | quota = **//2** |
| Threads | 3 workers | **2 workers** |
| Cache | `cache/` (src/../cache) | `cache/` (raiz) |
| Categoria ML | vazia (todas) | **MLB1276** (esportes) |
| Cron | 1h | **2h** |
