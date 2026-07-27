# Dashboard

Dashboard web para monitorar execucoes, configurar o bot e visualizar graficos.

**URL:** `https://mercadolivre-afiliado-bot-production.up.railway.app`

## Rotas Web

| Rota | Descricao |
|---|---|
| `GET /` | Home com stats, ultimo run, botao de trigger |
| `GET /login` | Login com senha |
| `GET /config` | Configuracao (categoria, paginas, limites, etc) |
| `GET /history` | Historico de ultimos 50 runs |
| `GET /runs/{id}` | Detalhe de um run (logs, ofertas enviadas) |
| `GET /offers` | Ofertas enviadas (ultimas 100) |
| `GET /charts` | Graficos: ofertas/dia, por plataforma, tempo execucao |
| `GET /promos` | Compartilhar promos selecionadas (formatar texto + link WA) |

## Bot API (usado pelo bot para reportar)

| Rota | Descricao |
|---|---|
| `GET /api/config` | Bot busca config para execucao |
| `POST /api/runs/init` | Inicia um novo run |
| `POST /api/runs/{id}/log` | Adiciona log ao run |
| `POST /api/runs/{id}/offer` | Registra oferta enviada |
| `POST /api/runs/{id}/finish` | Finaliza o run com resumo |

## Autenticacao

- Login via senha unica (`DASHBOARD_PASSWORD` no ambiente)
- Bot usa `BOT_API_KEY` via header `Authorization: Bearer <key>`
