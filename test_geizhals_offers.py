"""Extract shop offers from Geizhals product detail pages for Mac Mini."""
import json
import re
import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9",
})

# Known Mac Mini product IDs from Geizhals
product_id = "3342613"  # Mac mini M4 16GB/256GB

# Try different URL patterns for Geizhals.ch product page
urls = [
    f"https://geizhals.ch/apple-mac-mini-mu9d3d-a-2023-z1cf-a{product_id}.html",
    f"https://geizhals.ch/a{product_id}.html",
    f"https://geizhals.ch/a{product_id}.html?hloc=ch",
]

for url in urls:
    r = session.get(url, timeout=15)
    print(f"\n{url}")
    print(f"HTTP {r.status_code}, size={len(r.text)}")
    if r.status_code != 200:
        continue

    html = r.text
    title_match = re.search(r'<title>(.*?)</title>', html)
    print(f"Title: {title_match.group(1) if title_match else '?'}")

    # Check if it has Mac Mini content
    has_mac = "mac mini" in html.lower()
    print(f"Has Mac Mini: {has_mac}")

    if not has_mac:
        continue

    # Find the offer list section
    # Look for various patterns Geizhals uses for offers

    # Pattern 1: Offer rows with shop name and price
    # Geizhals uses variant blocks
    variant_blocks = re.findall(
        r'class="[^"]*variant__header[^"]*"(.*?)(?=class="[^"]*variant__header|$)',
        html, re.DOTALL
    )
    print(f"\nVariant blocks: {len(variant_blocks)}")

    # Pattern 2: Shop offer rows
    offer_rows = re.findall(
        r'<div[^>]*class="[^"]*offer__row[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
        html, re.DOTALL
    )
    print(f"Offer rows: {len(offer_rows)}")

    # Pattern 3: Look for shop names and prices in any format
    shops = re.findall(r'data-shop-name="([^"]+)"', html)
    print(f"Shops (data-shop-name): {shops[:20]}")

    # Find all price mentions
    chf_prices = re.findall(r'CHF\s*([\d\',.]+)', html)
    eur_prices = re.findall(r'€\s*([\d\',.]+)', html)
    print(f"CHF prices: {chf_prices[:10]}")
    print(f"EUR prices: {eur_prices[:10]}")

    # Find the offer list - look for JSON data
    offer_json = re.findall(r'window\.__OFFERS__\s*=\s*(\{.*?\});', html, re.DOTALL)
    if offer_json:
        print(f"\nFound __OFFERS__ JSON!")
        data = json.loads(offer_json[0])
        print(json.dumps(data)[:1000])

    # Look for any JSON with price data
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for script in scripts:
        if "price" in script.lower() and ("mac" in script.lower() or "offer" in script.lower()):
            if 100 < len(script) < 50000:
                try:
                    # Try extracting JSON objects
                    json_match = re.search(r'(\{[^{]*?"price"[^}]*\})', script)
                    if json_match:
                        print(f"\nJSON with price: {json_match.group(1)[:300]}")
                except:
                    pass

    # Look for the offer table structure
    # Geizhals recent versions use React/Next.js
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
    if nd:
        data = json.loads(nd.group(1))
        print(f"\n__NEXT_DATA__ found!")
        pp = data.get("props", {}).get("pageProps", {})
        print(f"pageProps keys: {list(pp.keys())[:20]}")

        # Look for offers/dealers
        offers = pp.get("offers") or pp.get("dealers") or pp.get("shopOffers")
        if offers:
            print(f"Offers type: {type(offers)}, len: {len(offers) if isinstance(offers, list) else '?'}")
            if isinstance(offers, list):
                for o in offers[:5]:
                    print(f"  {o}")
            elif isinstance(offers, dict):
                print(f"  Keys: {list(offers.keys())[:20]}")

        # Walk for offer data
        def find_offers(obj, path="", d=0):
            if d > 8: return
            if isinstance(obj, dict):
                # Check if this looks like an offer
                if "shopName" in obj or "dealerName" in obj or "merchant" in obj:
                    name = obj.get("shopName") or obj.get("dealerName") or obj.get("merchant", {}).get("name", "?")
                    price = obj.get("price") or obj.get("totalPrice")
                    if isinstance(price, dict):
                        price = price.get("amount") or price.get("value")
                    print(f"  OFFER at {path}: {name} = {price}")

                for k, v in obj.items():
                    find_offers(v, f"{path}.{k}", d+1)
            elif isinstance(obj, list):
                for i, item in enumerate(obj[:50]):
                    find_offers(item, f"{path}[{i}]", d+1)

        print("\nSearching for offers in __NEXT_DATA__:")
        find_offers(data)

        # Also check for product variants
        products = pp.get("products") or pp.get("productVariants") or pp.get("variants")
        if products:
            print(f"\nProducts/variants: {type(products)}")

    # Print a larger chunk of HTML for manual pattern inspection
    # Find the first CHF or offer section
    chf_pos = html.lower().find("chf")
    if chf_pos > 0:
        print(f"\n--- HTML around CHF mention (pos {chf_pos}) ---")
        print(html[max(0,chf_pos-200):chf_pos+500])

    break  # Only need to analyze one URL


# Now try the category listing page with Swiss price filter
print("\n\n" + "=" * 60)
print("Geizhals category with CHF prices")
print("=" * 60)

# Force Swiss locale / CHF
cat_url = "https://geizhals.ch/?cat=sysdiv&xf=21862_Apple+Mac+mini&hloc=ch&v=l&sort=p&lcur=CHF"
r2 = session.get(cat_url, timeout=30)
print(f"HTTP {r2.status_code}")

if r2.status_code == 200:
    html2 = r2.text

    # Find product entries with name and price
    # In list view, products appear in rows with name-link and price
    nd2 = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html2)
    if nd2:
        data2 = json.loads(nd2.group(1))
        pp2 = data2.get("props", {}).get("pageProps", {})
        print(f"pageProps keys: {list(pp2.keys())[:20]}")

        # Look for product listing data
        products = pp2.get("products") or pp2.get("productListing") or pp2.get("items")
        if products:
            print(f"Products: {type(products)}, {len(products) if isinstance(products, list) else 'dict'}")

        # Walk for product data
        found = []
        def walk(obj, d=0):
            if d > 12: return
            if isinstance(obj, dict):
                name = obj.get("name") or obj.get("productName") or ""
                price = obj.get("price") or obj.get("bestPrice") or obj.get("minPrice")
                if isinstance(price, dict):
                    price = price.get("amount") or price.get("value")
                if name and price and isinstance(name, str) and "mac" in name.lower():
                    found.append({"name": name, "price": price})
                for v in obj.values():
                    walk(v, d+1)
            elif isinstance(obj, list):
                for i in obj:
                    walk(i, d+1)
        walk(data2)
        print(f"Products found: {len(found)}")
        for f in found[:10]:
            print(f"  {f['name']} = {f['price']}")
    else:
        # No __NEXT_DATA__, parse HTML directly
        # Find product rows
        products = re.findall(
            r'<a[^>]*href="([^"]*a\d+\.html[^"]*)"[^>]*title="([^"]+)"',
            html2
        )
        print(f"Product links with titles: {len(products)}")
        for href, title in products:
            if "mac" in title.lower():
                print(f"  {title}: {href}")

    # Find CHF prices on this page
    chf = re.findall(r'CHF\s*([\d\',.]+)', html2)
    print(f"\nCHF prices on page: {chf[:20]}")
