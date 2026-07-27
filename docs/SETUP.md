# Setup

## Requisitos

- Python 3.11+
- Conta no Telegram (criar bot em @BotFather)
- GitHub (para Actions e cache)

## Variaveis de ambiente

Variaveis obrigatorias no arquivo `.env` ou GitHub Secrets:

```bash
# Telegram
TELEGRAM_BOT_TOKEN=token_do_seu_bot
TELEGRAM_CHAT_ID=@id_do_grupo_ou_canal

# Afiliado Mercado Livre
AFFILIATE_TAG=matt:seu_usuario:seu_tool_id
```

## Deploy no GitHub Actions

1. Crie o repositorio no GitHub
2. Adicione os Secrets no Settings > Secrets and variables > Actions:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `AFFILIATE_TAG`
3. O workflow em `.github/workflows/bot.yml` roda automaticamente a cada hora
4. Para acionar manualmente: va em Actions > Bot ML Afiliado > Run workflow

## Opcionais

### Shopee

Adicione os secrets `SHOPEE_APP_ID` e `SHOPEE_APP_SECRET` para buscar ofertas da Shopee.

### AliExpress

Adicione `ALIEXPRESS_APP_KEY`, `ALIEXPRESS_APP_SECRET` e `ALIEXPRESS_TRACKING_ID` para ofertas do AliExpress.

### OpenRouter (headlines com IA)

Adicione o secret `OPENROUTER_API_KEY` para headlines geradas por IA.

### Dashboard

Deploy separado no Railway com `dashboard/` e configurar `DASHBOARD_URL` e `BOT_API_KEY`.

## Executar localmente

```bash
pip install -r requirements.txt
python src/bot.py
```
