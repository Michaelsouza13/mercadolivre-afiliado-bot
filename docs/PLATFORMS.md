# Plataformas

## Mercado Livre

- **Fonte:** Pagina de ofertas do ML (`mercadolivre.com.br/ofertas`)
- **Metodo:** Scraping HTML/JSON embedded
- **Afiliado:** Link gerado com `make_affiliate_url()` (tag `matt` ou `?tag=`)
- **Filtros:** Categoria (`ML_CATEGORY`) e tipo de promocao (`ML_PROMOTION_TYPE`)
- **Limite:** `ML_MAX_OFFERS` (ou `MAX_OFFERS_PER_RUN` se vazio)
- **Scraper:** `MercadoLivreScraper` em `src/scraper.py`

## Shopee

- **Fonte:** API GraphQL da Shopee Open Platform
- **Autenticacao:** SHA256 com `app_id` + `app_secret`
- **Afiliado:** Link direto do `offerLink` (ja tem tracking)
- **Filtros:** Keywords separadas por virgula (`SHOPEE_KEYWORDS`)
- **Limite:** `SHOPEE_MAX_OFFERS`
- **Scraper:** `ShopeeScraper` em `src/shopee_scraper.py`

## AliExpress

- **Fonte:** API `product.query` da AliExpress Affiliate
- **Autenticacao:** `app_key` + `app_secret` + `tracking_id`
- **Afiliado:** Link ja inclui tracking
- **Filtros:** Categorias (`ALIEXPRESS_CATEGORY_IDS`) ou keywords
- **Limite:** `ALIEXPRESS_MAX_OFFERS`
- **Scraper:** `AliExpressScraper` em `src/aliexpress_scraper.py`
