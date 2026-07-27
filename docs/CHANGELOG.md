# Changelog

## v1.1 (atual)

-  Headlines com IA via OpenRouter (response healing + fallback keywords)
-  Emojis por plataforma: ML , Shops , ALI
-  Cron ajustado para 06:00-23:00 (18 execucoes/dia)
-  Documentacao completa (docs/)
-  Testes de headlines

## v1.0

-  Scraping paralelo (3 threads)
-  Balanceamento pos-coleta (quota = max//3)
-  Score de oferta (desconto, cupom, frete, parcela)
-  CTA variado (5 frases)
-  Retry com backoff (AE/SH 3x, ML 2x)
-  Cache FIFO (2000 entradas)
-  Testes unitarios (40/40)
-  Dashboard web com graficos (Chart.js)
-  Alerta de erro no Telegram
-  Parcelamento ML na mensagem
