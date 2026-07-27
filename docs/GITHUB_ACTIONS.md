# GitHub Actions

## Workflow

**Arquivo:** `.github/workflows/bot.yml`

```yaml
name: Bot ML Afiliado
on:
  schedule:
    - cron: '0 6-23 * * *'   # 06:00 as 23:00 (18x/dia)
  workflow_dispatch:
```

## Secrets obrigatorios

| Secret | Descricao |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token do bot Telegram |
| `TELEGRAM_CHAT_ID` | ID do grupo/canal |

## Secrets opcionais

| Secret | Descricao |
|---|---|
| `AFFILIATE_TAG` | Tag de afiliado ML |
| `SHOPEE_APP_ID` | App ID Shopee |
| `SHOPEE_APP_SECRET` | App Secret Shopee |
| `ALIEXPRESS_APP_KEY` | App Key AliExpress |
| `ALIEXPRESS_APP_SECRET` | App Secret AliExpress |
| `OPENROUTER_API_KEY` | API Key OpenRouter (headlines IA) |
| `DASHBOARD_URL` | URL da dashboard |
| `BOT_API_KEY` | Chave de autenticacao da dashboard |

## Vars (repository variables)

| Var | Default | Descricao |
|---|---|---|
| `ML_CATEGORY` | vazio | Categoria ML (todas se vazio) |
| `ML_PAGES` | 3 | Paginas ML |
| `MAX_OFFERS_PER_RUN` | 10 | Limite de ofertas |
| `SEND_DELAY_SECONDS` | 60 | Delay entre envios |
| `SHOPEE_KEYWORDS` | vazio | Keywords Shopee |

## Cache

O cache de ofertas enviadas fica no diretorio `cache/` e persiste entre execucoes via
`actions/cache@v4`.
