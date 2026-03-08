"""Deep Fust.ch analysis - find product listing in RSC data."""
import json
import re
import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9",
})

# Try the Mac mini category page
url = "https://www.fust.ch/de/c/computer-gaming/mac/mac-mini-mac-studio/~cat460"
r = session.get(url, timeout=30)
print(f"Category page: HTTP {r.status_code}, size={len(r.text)}")

if r.status_code != 200:
    # Try alternative URL
    url = "https://www.fust.ch/handy-pc-tablet/pc-computer-monitore/mac-mini-mac-studio/c/f_mac_mini_mac_studio"
    r = session.get(url, timeout=30)
    print(f"Alt category: HTTP {r.status_code}, size={len(r.text)}")

if r.status_code == 200:
    html = r.text

    # Extract and combine RSC data
    rsc_chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.DOTALL)
    combined = "".join(rsc_chunks)
    # Unescape
    combined = combined.replace('\\"', '"').replace('\\n', '\n').replace('\\/', '/')

    # Find product-like data blocks
    # Fust RSC data might have product objects with names and prices
    # Look for price patterns near product names
    mac_products = []
    for m in re.finditer(r'"name"\s*:\s*"([^"]*(?:[Mm]ac\s*[Mm]ini|Mac\s*Studio)[^"]*)"', combined):
        name = m.group(1)
        # Get surrounding context for price
        start = max(0, m.start() - 500)
        end = min(len(combined), m.end() + 500)
        context = combined[start:end]
        # Find price
        price_match = re.search(r'"(?:price|salesPrice|currentPrice|amount)":\s*"?([\d.]+)"?', context)
        if price_match:
            mac_products.append({"name": name, "price": price_match.group(1)})
        else:
            mac_products.append({"name": name, "price": "?"})

    print(f"\nMac products found: {len(mac_products)}")
    for p in mac_products[:20]:
        print(f"  {p['name']} = CHF {p['price']}")

    # Find all product URL patterns
    product_urls = re.findall(r'/de/p/(\d+)-([^"\\,\s]+)', combined)
    print(f"\nProduct URLs in RSC: {len(product_urls)}")
    for pid, slug in product_urls[:20]:
        print(f"  https://www.fust.ch/de/p/{pid}-{slug}")

    # Find all price mentions
    prices = re.findall(r'"(?:price|salesPrice|formattedPrice)":\s*"?([\d.]+)"?', combined)
    print(f"\nPrices in RSC: {prices[:20]}")

    # Try to find JSON product arrays
    # Look for arrays of product objects
    product_arrays = re.findall(r'"products"\s*:\s*\[(.*?)\]', combined, re.DOTALL)
    print(f"\nProduct arrays: {len(product_arrays)}")
    for pa in product_arrays[:2]:
        print(f"  Length: {len(pa)}")
        print(f"  Preview: {pa[:300]}")

    # Look for "code" or "sku" fields with prices
    sku_matches = re.findall(r'"(?:code|sku|articleNumber)"\s*:\s*"([^"]+)"', combined)
    print(f"\nSKU/codes: {sku_matches[:10]}")


# Try search page with RSC headers (Next.js RSC format)
print("\n\n" + "=" * 60)
print("Fust RSC API")
print("=" * 60)

# Next.js apps sometimes have RSC endpoints
rsc_headers = {
    "RSC": "1",
    "Next-Router-State-Tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22de%22%2C%7B%22children%22%3A%5B%22search%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%5D%7D%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D",
    "Next-Url": "/de/search?q=mac+mini",
}

try:
    r2 = session.get(
        "https://www.fust.ch/de/search?q=mac+mini",
        headers=rsc_headers,
        timeout=15
    )
    print(f"RSC request: HTTP {r2.status_code}, size={len(r2.text)}")
    if r2.status_code == 200 and r2.text[:10] != "<!DOCTYPE":
        # This is RSC payload
        text = r2.text
        # Find product data
        mac_mentions = [(m.start(), text[m.start():m.start()+200]) for m in re.finditer(r'[Mm]ac\s*[Mm]ini', text)]
        print(f"Mac Mini in RSC: {len(mac_mentions)}")

        # Find prices
        prices = re.findall(r'"price":\s*"?([\d.]+)"?', text)
        print(f"Prices: {prices[:20]}")

        # Find product URLs
        prod_urls = re.findall(r'/de/p/(\d+)-([^"\\,\s]+)', text)
        print(f"Product URLs: {len(prod_urls)}")
        for pid, slug in prod_urls[:10]:
            print(f"  /de/p/{pid}-{slug}")

        # Print first 2000 chars for analysis
        print(f"\nRSC payload preview:\n{text[:2000]}")
except Exception as e:
    print(f"RSC error: {e}")


# Try fetching a known Fust Mac Mini product page
print("\n\n" + "=" * 60)
print("Fust product pages")
print("=" * 60)

# Search for Mac Mini product IDs from the search page
r3 = session.get("https://www.fust.ch/de/search?q=mac+mini", timeout=30)
if r3.status_code == 200:
    # Find product references
    # Look for any product identifiers
    ids = re.findall(r'"productCode"\s*:\s*"(\d+)"', r3.text)
    if not ids:
        ids = re.findall(r'"articleId"\s*:\s*"(\d+)"', r3.text)
    if not ids:
        ids = re.findall(r'"id"\s*:\s*"(\d+)"', r3.text)
    print(f"Product IDs found: {ids[:10]}")

    # Find href to product pages
    prod_links = re.findall(r'href="(/de/p/[^"]+)"', r3.text)
    print(f"Product links: {len(prod_links)}")
    for pl in prod_links[:10]:
        print(f"  {pl}")

    # If we found product pages, fetch one
    if prod_links:
        prod_url = f"https://www.fust.ch{prod_links[0]}"
        pr = session.get(prod_url, timeout=15)
        print(f"\nProduct page: HTTP {pr.status_code}")
        if pr.status_code == 200:
            # JSON-LD
            jsonld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', pr.text, re.DOTALL)
            for block in jsonld:
                try:
                    data = json.loads(block)
                    if data.get("@type") == "Product":
                        print(f"  Product: {data.get('name')}")
                        offers = data.get("offers", {})
                        if isinstance(offers, dict):
                            print(f"  Price: {offers.get('price')} {offers.get('priceCurrency')}")
                        elif isinstance(offers, list):
                            for o in offers:
                                print(f"  Price: {o.get('price')} {o.get('priceCurrency')}")
                except:
                    pass
