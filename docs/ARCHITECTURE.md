# Arquitetura do Bot

## Fluxo de execucao

```
Cron (GH Actions) a cada hora (06:00-23:00)
         |
    main() em src/bot.py
         |
    Carrega sent_ids do cache FIFO
         |
    Scraping paralelo (ThreadPoolExecutor 3 workers)
    +------------------+------------------+
    |                  |                  |
    ML (1 thread)   AE (1 thread)   SH (1 thread)
    |                  |                  |
    +------------------+------------------+
         |
    _balance_offers (quota = max_offers // 3)
         |
    get_headlines() (OpenRouter IA + fallback keywords)
         |
    Ordena por score (melhores primeiro)
         |
    Loop de envio (com send_delay entre cada)
    +------------------+
    | Telegram sender  |
    +------------------+
         |
    Salva sent_ids no cache FIFO
         |
    Reporta para dashboard (se configurada)
```

## Componentes

| Arquivo | Responsabilidade |
|---|---|
| `src/bot.py` | Orquestrador principal |
| `src/scraper.py` | Classe Offer + MercadoLivreScraper |
| `src/shopee_scraper.py` | Scraper da Shopee (GraphQL) |
| `src/aliexpress_scraper.py` | Scraper do AliExpress (API) |
| `src/headlines.py` | Headlines com IA + fallback keywords |
| `src/telegram_sender.py` | Envio para Telegram |
| `src/whatsapp_sender.py` | Envio para WhatsApp |
| `src/storage.py` | Cache FIFO de ofertas enviadas |
| `src/utils.py` | Utilitarios (format_price) |
| `dashboard/` | Dashboard FastAPI |
| `tests/` | Testes unitarios pytest |
