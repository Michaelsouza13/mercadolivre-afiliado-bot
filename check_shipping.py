import json, re, requests

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9'
}

r = requests.get('https://www.mercadolivre.com.br/ofertas', headers=headers, timeout=15)
match = re.search(r"_n\.ctx\.r\s*=\s*(\{.+?\});", r.text, re.DOTALL)
ctx = json.loads(match.group(1))
data = ctx['appProps']['pageProps']['data']
items = data.get('items', [])

print(f'Total items returned: {len(items)}')
print()

def get_title(item):
    for comp in item.get('card', {}).get('components', []):
        if comp.get('type') == 'title':
            return comp.get('title', {}).get('text', 'N/A')
    return 'N/A'

def get_shipping_info(item):
    for comp in item.get('card', {}).get('components', []):
        if comp.get('type') == 'shipping_v2':
            sv2 = comp.get('shipping_v2')
            if sv2 is None:
                return None, None
            if not isinstance(sv2, list):
                return None, None
            tags = []
            is_full = False
            for entry in sv2:
                txt = entry.get('text', entry.get('alt_text', '')).lower()
                if 'frete gr' in txt:
                    if 'free_shipping' not in tags:
                        tags.append('free_shipping')
                vals = entry.get('values', [])
                for v in vals:
                    if v.get('type') == 'icon':
                        ico = v.get('icon', {})
                        alt = ico.get('alt_text', '').lower()
                        if 'full' in alt:
                            is_full = True
                    if v.get('type') == 'label':
                        lbl = v.get('label', {})
                        ltxt = lbl.get('text', '').lower()
                        if 'frete gr' in ltxt and 'free_shipping' not in tags:
                            tags.append('free_shipping')
                alt_txt = entry.get('alt_text', '').lower()
                if 'frete gr' in alt_txt and 'free_shipping' not in tags:
                    tags.append('free_shipping')
            if is_full:
                tags.append('fulfillment')
            return tags, sv2
    return None, None

# Show first 5 items
for i, item in enumerate(items[:5]):
    title = get_title(item)
    tags, raw = get_shipping_info(item)
    print(f'Item {i+1}: {title}')
    print(f'  Shipping tags: {tags}')
    print()

# Count in first 15
free_count = 0
full_count = 0
for item in items[:15]:
    tags, _ = get_shipping_info(item)
    if tags:
        if 'free_shipping' in tags:
            free_count += 1
        if 'fulfillment' in tags:
            full_count += 1

print('--- Summary (first 15 items) ---')
print(f'Items with free_shipping: {free_count}')
print(f'Items with fulfillment (FULL): {full_count}')
print(f'Items with either: {free_count}')
