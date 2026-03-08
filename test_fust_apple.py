"""Extract Mac Mini prices from Fust.ch and Apple Store CH."""
import json
import re
import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9",
})

# ========== FUST ==========
print("=" * 60)
print("FUST.CH")
print("=" * 60)

# Try the category page instead of search
fust_urls = [
    "https://www.fust.ch/de/search?q=mac+mini",
    "https://www.fust.ch/de/c/computer-gaming/mac/mac-mini/~cat460",
    "https://www.fust.ch/de/c/computer-gaming/mac/~cat76",
]

for url in fust_urls:
    r = session.get(url, timeout=30)
    print(f"\n{url}")
    print(f"HTTP {r.status_code}, size={len(r.text)}")
    if r.status_code != 200:
        continue

    html = r.text

    # Look for RSC data (React Server Components)
    # Fust uses Next.js with app router, data is in self.__next_f.push chunks
    rsc_chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.DOTALL)
    print(f"RSC chunks: {len(rsc_chunks)}")

    # Combine and search for product data
    combined = "".join(rsc_chunks)
    # Find Mac Mini mentions
    mac_mentions = [(m.start(), combined[m.start():m.start()+200]) for m in re.finditer(r'[Mm]ac\s*[Mm]ini', combined)]
    print(f"Mac Mini mentions in RSC: {len(mac_mentions)}")
    for pos, context in mac_mentions[:5]:
        print(f"  pos {pos}: ...{context[:150]}...")

    # Look for JSON objects with product data in RSC stream
    # RSC format: key:value pairs with JSON objects
    json_objects = re.findall(r'\{[^{}]*"name"[^{}]*"price"[^{}]*\}', combined)
    print(f"\nJSON objects with name+price: {len(json_objects)}")
    for jo in json_objects[:5]:
        print(f"  {jo[:200]}")

    # Try to find product cards/tiles in HTML
    product_cards = re.findall(
        r'<a[^>]*href="(/de/p/[^"]+)"[^>]*>(.*?)</a>',
        html, re.DOTALL
    )
    print(f"\nProduct page links (/de/p/...): {len(product_cards)}")
    for href, content in product_cards[:10]:
        text = re.sub(r'<[^>]+>', ' ', content).strip()
        text = re.sub(r'\s+', ' ', text)
        if text and len(text) > 5:
            print(f"  {href}: {text[:100]}")

    # Alternative: search for product URLs
    product_urls = re.findall(r'/de/p/\d+-[^"\'\\]+', html)
    print(f"\nProduct URL patterns: {len(product_urls)}")
    for pu in product_urls[:10]:
        print(f"  {pu}")

    # Look for structured data in data attributes
    data_attrs = re.findall(r'data-product[^=]*="([^"]+)"', html)
    print(f"\nData-product attributes: {len(data_attrs)}")
    for da in data_attrs[:10]:
        print(f"  {da[:100]}")

    if "mac" in html.lower():
        break

# Try a known Fust Mac Mini product page
print("\n\n" + "=" * 60)
print("FUST - Search for product URLs")
print("=" * 60)

# Search for product URLs in the RSC data
r = session.get("https://www.fust.ch/de/search?q=mac+mini", timeout=30)
if r.status_code == 200:
    # Find all product URLs
    all_urls = re.findall(r'(?:href|url)["\s:=]+["\']?(/de/p/[^"\'\\,\s]+)', r.text)
    print(f"Product URLs: {len(all_urls)}")
    for u in all_urls[:20]:
        print(f"  https://www.fust.ch{u}")

    # Also look for JSON-like product data in RSC
    # Pattern: "name":"Mac mini..." followed by price
    product_matches = re.findall(
        r'"name"\s*:\s*"([^"]*[Mm]ac[^"]*[Mm]ini[^"]*)"',
        r.text
    )
    print(f"\nProduct names in data: {len(product_matches)}")
    for pm in product_matches[:10]:
        print(f"  {pm}")

    # Find prices near Mac Mini mentions
    for m in re.finditer(r'[Mm]ac\s*[Mm]ini', r.text):
        context = r.text[m.start():m.start()+500]
        prices = re.findall(r'"(?:price|amount|salesPrice|currentPrice)"[:\s]+"?([\d.]+)"?', context)
        if prices:
            print(f"\n  Near '{m.group()}': prices = {prices}")

    # Try to find the search results API
    # Some Next.js apps have /api/search endpoints
    api_urls = [
        "https://www.fust.ch/api/search?q=mac+mini",
        "https://www.fust.ch/api/products?q=mac+mini",
    ]
    for api_url in api_urls:
        try:
            ar = session.get(api_url, timeout=10)
            print(f"\n{api_url}: HTTP {ar.status_code}")
            if ar.status_code == 200:
                print(f"  Body: {ar.text[:500]}")
        except Exception as e:
            print(f"\n{api_url}: {e}")


# ========== APPLE STORE ==========
print("\n\n" + "=" * 60)
print("APPLE STORE CH")
print("=" * 60)

r = session.get("https://www.apple.com/ch-de/shop/buy-mac/mac-mini", timeout=30)
if r.status_code == 200:
    html = r.text

    # JSON-LD
    jsonld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    for block in jsonld:
        try:
            data = json.loads(block)
            print(f"JSON-LD type: {data.get('@type')}")
            if data.get("@type") == "Product":
                print(f"  Name: {data.get('name')}")
                offers = data.get("offers", [])
                if isinstance(offers, list):
                    for o in offers:
                        print(f"  Offer: {o.get('@type')} low={o.get('lowPrice')} high={o.get('highPrice')} {o.get('priceCurrency')}")
                elif isinstance(offers, dict):
                    print(f"  Price: {offers.get('price')} {offers.get('priceCurrency')}")
        except:
            pass

    # Find individual product cards with prices
    # Apple Store uses specific HTML structure
    # Look for product tiles
    product_tiles = re.findall(
        r'<div[^>]*class="[^"]*product[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
        html, re.DOTALL
    )
    print(f"\nProduct tiles: {len(product_tiles)}")

    # Find product names with prices
    # Pattern: "Mac mini, M4 Chip..." and "CHF 599.00" or "Ab CHF 599.00"
    products = re.findall(
        r'(Mac\s*mini[^<]{0,200}?)(?:<|$)',
        html
    )
    print(f"\nMac Mini strings: {len(products)}")

    # Find all CHF price patterns with context
    for m in re.finditer(r'(?:Ab\s+)?CHF\s*([\d\',.]+)', html):
        price = m.group(1).replace("'", "").replace(",", ".")
        context_start = max(0, m.start() - 200)
        before = html[context_start:m.start()]
        # Find nearest product name before price
        name_match = re.search(r'(Mac\s*mini[^<]{0,150})', before)
        if name_match:
            print(f"  {name_match.group(1).strip()[:80]} -> CHF {price}")

    # Try to extract from data attributes or JS
    product_data = re.findall(r'data-autom="[^"]*product[^"]*"', html)
    print(f"\nProduct data attributes: {len(product_data)}")

    # Look for window.__NEXT_DATA__ or similar
    nd = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\});\s*</script>', html, re.DOTALL)
    if nd:
        print("Found __PRELOADED_STATE__!")

    # Look for JSON data in scripts
    for script in re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
        if "mac mini" in script.lower() and "price" in script.lower() and len(script) < 50000:
            # Try to find product objects
            products_json = re.findall(
                r'\{[^{}]*"(?:partNumber|sku)"\s*:\s*"[^"]+[^{}]*"price"\s*:\s*\{[^{}]*\}[^{}]*\}',
                script
            )
            if products_json:
                print(f"\nProduct JSON objects: {len(products_json)}")
                for pj in products_json[:3]:
                    print(f"  {pj[:300]}")
