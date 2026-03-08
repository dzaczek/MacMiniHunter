"""Extract Mac Mini prices from Geizhals and Fust."""
import json
import re
import sys
sys.path.insert(0, ".")

import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9",
})


# ========== GEIZHALS ==========
print("=" * 60)
print("GEIZHALS.CH - Extracting Mac Mini products")
print("=" * 60)

r = session.get("https://geizhals.ch/?fs=mac+mini&hloc=ch", timeout=30)
if r.status_code == 200:
    html = r.text

    # Look for product list items
    # Geizhals uses specific HTML structure for product listings
    # Find product blocks with name and price
    products = re.findall(
        r'<div[^>]*class="[^"]*productlist[^"]*"[^>]*>.*?</div>',
        html, re.DOTALL
    )
    print(f"Product divs found: {len(products)}")

    # Try finding product links with prices
    # Pattern: product name in <a> tag, price in nearby element
    items = re.findall(
        r'<a[^>]+href="(/[^"]+)"[^>]*class="[^"]*listview__name-link[^"]*"[^>]*>([^<]+)</a>',
        html
    )
    print(f"Product links found: {len(items)}")
    for href, name in items[:5]:
        print(f"  {name.strip()}: https://geizhals.ch{href}")

    # Alternative: find all links containing "mac-mini" or product IDs
    mac_links = re.findall(r'<a[^>]+href="([^"]*mac[^"]*mini[^"]*)"[^>]*>([^<]*)</a>', html, re.IGNORECASE)
    print(f"\nMac Mini links: {len(mac_links)}")
    for href, text in mac_links[:10]:
        print(f"  [{text.strip()[:60]}] -> {href[:100]}")

    # Find prices near mac mini mentions
    # Look for CHF amounts
    prices = re.findall(r'(?:CHF|Fr\.?)\s*([\d\',.]+)', html)
    print(f"\nAll CHF prices: {len(prices)}")
    print(f"  First 10: {prices[:10]}")

    # Try to find structured product data
    # Geizhals sometimes has JSON data in script tags
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for script in scripts:
        if "productId" in script or "productName" in script or "mac" in script.lower():
            if len(script) > 50 and len(script) < 50000:
                # Try to parse as JSON
                json_match = re.search(r'(\{.*\}|\[.*\])', script, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group(1))
                        print(f"\nScript JSON with product data: {json.dumps(data)[:500]}")
                    except:
                        pass

    # Save raw HTML for analysis
    # Find the actual product listing section
    # Geizhals uses specific CSS classes
    listing_section = re.search(r'id="productlist"(.*?)id="footer"', html, re.DOTALL)
    if listing_section:
        section = listing_section.group(1)
        # Find product rows
        rows = re.findall(r'<div[^>]*class="[^"]*listview__row[^"]*"[^>]*>(.*?)</div>\s*</div>', section, re.DOTALL)
        print(f"\nProduct rows: {len(rows)}")

    # Try a more specific pattern for Geizhals product listings
    # They use data-product-id attributes
    product_ids = re.findall(r'data-product-id="(\d+)"', html)
    print(f"\nProduct IDs: {len(product_ids)}")
    print(f"  IDs: {product_ids[:10]}")

    # Extract product names from title attributes or aria-labels
    product_names = re.findall(r'class="[^"]*listview__name[^"]*"[^>]*>\s*<a[^>]*>([^<]+)</a>', html)
    if not product_names:
        product_names = re.findall(r'data-product-name="([^"]+)"', html)
    print(f"\nProduct names: {len(product_names)}")
    for n in product_names[:10]:
        print(f"  {n.strip()}")

    # Find price elements
    price_elements = re.findall(r'class="[^"]*price[^"]*"[^>]*>[^<]*?(\d[\d\',.]+)', html)
    print(f"\nPrice elements: {len(price_elements)}")
    for p in price_elements[:10]:
        print(f"  CHF {p}")

    # Save a chunk of HTML around "Mac mini" mentions for pattern analysis
    mac_positions = [m.start() for m in re.finditer(r'Mac\s*[Mm]ini', html)]
    if mac_positions:
        pos = mac_positions[0]
        context = html[max(0, pos-200):pos+500]
        print(f"\nHTML context around first 'Mac mini' mention:")
        print(context[:700])


# ========== FUST ==========
print("\n\n" + "=" * 60)
print("FUST.CH - Extracting Mac Mini products")
print("=" * 60)

r2 = session.get("https://www.fust.ch/de/search?q=mac+mini", timeout=30)
if r2.status_code == 200:
    html2 = r2.text

    # JSON-LD
    jsonld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html2, re.DOTALL)
    print(f"JSON-LD blocks: {len(jsonld)}")
    for block in jsonld[:5]:
        try:
            data = json.loads(block)
            dtype = data.get("@type", "unknown")
            if "Product" in str(dtype) or "ItemList" in str(dtype):
                print(f"  Type: {dtype}")
                items = data.get("itemListElement", [])
                if items:
                    for item in items[:5]:
                        prod = item.get("item", item)
                        print(f"    {prod.get('name')} = CHF {prod.get('offers',{}).get('price')}")
        except:
            pass

    # Check __NEXT_DATA__
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html2)
    if nd:
        data = json.loads(nd.group(1))
        print(f"\n__NEXT_DATA__ found")

        found = []
        def walk(obj, d=0):
            if d > 15: return
            if isinstance(obj, dict):
                n = obj.get("name") or obj.get("productName") or obj.get("title", "")
                p = obj.get("price") or obj.get("salesPrice") or obj.get("currentPrice")
                if not p:
                    prices_obj = obj.get("prices") or obj.get("pricing") or {}
                    if isinstance(prices_obj, dict):
                        p = prices_obj.get("salesPrice") or prices_obj.get("price") or prices_obj.get("current")
                if n and p and isinstance(n, str) and "mac" in n.lower():
                    url = obj.get("url") or obj.get("pdpUrl") or obj.get("link") or ""
                    found.append({"name": n, "price": p, "url": url})
                for v in obj.values():
                    walk(v, d+1)
            elif isinstance(obj, list):
                for i in obj:
                    walk(i, d+1)

        walk(data)
        print(f"Products in __NEXT_DATA__: {len(found)}")
        for f in found[:10]:
            print(f"  {f['name']} = CHF {f['price']} | {f['url'][:80]}")

    # Look for product data in other script tags
    if not jsonld and not nd:
        # Try finding inline JSON data
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', html2, re.DOTALL)
        for script in scripts:
            if "mac" in script.lower() and "price" in script.lower():
                print(f"\nScript with Mac/price data (len={len(script)}):")
                print(script[:500])
                break

    # Find product listings in HTML
    mac_mentions = re.findall(r'(?:Mac\s*[Mm]ini[^<]{0,100})', html2)
    print(f"\nMac Mini mentions in HTML: {len(mac_mentions)}")
    for m in mac_mentions[:5]:
        print(f"  {m.strip()[:100]}")


# ========== APPLE.CH ==========
print("\n\n" + "=" * 60)
print("APPLE.COM/CH-DE - Official prices")
print("=" * 60)

r3 = session.get("https://www.apple.com/ch-de/shop/buy-mac/mac-mini", timeout=30)
if r3.status_code == 200:
    html3 = r3.text

    # Look for product tiles/cards
    # Apple uses specific JSON structure for their products
    # Find price information
    price_matches = re.findall(r'CHF\s*([\d\',.]+)', html3)
    print(f"CHF prices: {price_matches[:20]}")

    # Find product names near prices
    products = re.findall(r'(Mac\s*[Mm]ini[^<]{0,200})', html3)
    print(f"\nMac Mini product strings: {len(products)}")
    for p in products[:10]:
        # Clean up
        clean = re.sub(r'<[^>]+>', ' ', p).strip()
        clean = re.sub(r'\s+', ' ', clean)
        print(f"  {clean[:150]}")

    # JSON-LD on Apple Store
    jsonld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html3, re.DOTALL)
    print(f"\nJSON-LD blocks: {len(jsonld)}")
    for block in jsonld:
        try:
            data = json.loads(block)
            if data.get("@type") == "Product" or data.get("@type") == "ItemList":
                print(f"  Type: {data.get('@type')}")
                print(f"  Data: {json.dumps(data)[:500]}")
        except:
            pass
