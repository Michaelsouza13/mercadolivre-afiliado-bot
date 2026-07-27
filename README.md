# Maika Promos Bot

Bot automatico de afiliados que busca ofertas do **Mercado Livre**, **Shopee** e **AliExpress** e envia para grupos do Telegram com headlines criativas geradas por IA.

## Funcionalidades

-  3 plataformas: Mercado Livre, Shopee, AliExpress
-  Headlines com IA (OpenRouter) + fallback keywords
-  Scraping paralelo (3 threads simultaneas)
-  Balanceamento de cotas por plataforma
-  Score de oferta (ranking por qualidade)
-  Cache FIFO (2000 ofertas)
-  Dashboard web (FastAPI) com graficos
-  Multi-canais com keyword filtering
-  Retry com backoff exponencial
-  Testes unitarios (40+)

## Documentacao

| Documento | Descricao |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | Configuracao completa do zero |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Fluxo interno do bot |
| [docs/HEADLINES.md](docs/HEADLINES.md) | Sistema de headlines com IA |
| [docs/DASHBOARD.md](docs/DASHBOARD.md) | Dashboard, rotas e API |
| [docs/PLATFORMS.md](docs/PLATFORMS.md) | Detalhes: ML, Shopee, AliExpress |
| [docs/GITHUB_ACTIONS.md](docs/GITHUB_ACTIONS.md) | Workflow, secrets e cron |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Historico de versoes |
