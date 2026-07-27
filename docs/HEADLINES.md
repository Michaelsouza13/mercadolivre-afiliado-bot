# Sistema de Headlines

As headlines sao os titulos chamativos que aparecem no topo de cada mensagem,
substituindo o generico "PROMOCAO MERCADO LIVRE".

## Formato final

```
CHEIROSO ASSIM TU CONQUISTA A GATINHA FIT 

📌 Perfume Montblanc Explorer 100ml
🔥 Por: R$ 399,00
🛒 https://...

📢 Nao perca essa chance!
```

## Emojis por plataforma

| Plataforma | Emoji |
|---|---|
| Mercado Livre |  |
| Shopee |  |
| AliExpress |  |

## Fluxo de geracao

```
get_headlines(offers, api_key)
  |
  +-- Se api_key existe:
  |     _call_openrouter(offers, api_key, model)
  |     |
  |     +-- Sucesso -> _parse_openrouter_response()
  |     |     tenta 4 estrategias de parsing
  |     |     valida cada headline
  |     |     detecta duplicatas em massa
  |     |
  |     +-- Falha -> fallback keywords
  |
  +-- Se sem api_key OU IA falhou:
        _fallback_keywords(offers)
          match por grupos de palavras
          +-- achou -> headline do grupo
          +-- nao achou -> fallback generico
```

## OpenRouter

**Provider:** `openai/gpt-4o-mini` (ou configurado via env)
**Plugin:** `response-healing` (corrige JSON automaticamente)
**Formato:** `response_format=json_object`
**Custo:** 0 (modelos gratuitos, 50 req/dia limite, 18 req/dia uso)

## Fallback keywords

Grupos de palavras chave com headlines pre-definidas. Exemplos:

| Palavras | Headlines |
|---|---|
| perfume, colonia, essencia | CHEIROSO ASSIM TU CONQUISTA A GATINHA FIT |
| fone, bluetooth, audio | SOM DE QUALIDADE SEM GASTAR MUITO |
| tapete, cortina, quadro | DECORE SUA CASA SEM PESAR NO BOLSO |
| creatina, whey, suplemento | META FITNESS? COM ESSE PRECO FICA FACIL |

## Tratamento de erros

| Problema | Mitigacao |
|---|---|
| JSON mal formatado | 4 estrategias de parsing + response-healing |
| Modelo fora do ar | Fallback keywords |
| Rate limit (429) | Retry nao necessario (cai direto pra fallback) |
| Headline quebra HTML | `html.escape()` |
| Headlines repetidas | Deteccao >70% iguais -> descarta batch |
| Headline vazia | Validacao de tamanho (5-80 chars) |
