"""Test Galaxus/Digitec search via requests and API exploration."""
import json
import re
import sys
sys.path.insert(0, ".")

from src.utils.stealth import create_session

s = create_session()

# Try Galaxus EN search
print("=" * 60)
print("GALAXUS SEARCH PAGE")
print("=" * 60)
r = s.get("https://www.galaxus.ch/en/search?q=mac+mini", timeout=30)
print(f"HTTP {r.status_code}")

if r.status_code == 200:
    html = r.text
    print(f"HTML length: {len(html)}")

    # Check for JSON-LD
    jsonld = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
    )
    print(f"JSON-LD blocks: {len(jsonld)}")
    for block in jsonld[:3]:
        try:
            data = json.loads(block)
            dtype = data.get("@type", "unknown")
            print(f"  Type: {dtype}")
            items = data.get("itemListElement", [])
            if items:
                print(f"  Items: {len(items)}")
                for item in items[:3]:
                    prod = item.get("item", item)
                    print(f"    - {prod.get('name', '?')} = {prod.get('offers', {}).get('price', '?')} CHF")
        except Exception as e:
            print(f"  Parse error: {e}")

    # Check __NEXT_DATA__
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
    if nd:
        data = json.loads(nd.group(1))
        print(f"\n__NEXT_DATA__ top keys: {list(data.keys())}")
        props = data.get("props", {})
        print(f"props keys: {list(props.keys())}")
        pp = props.get("pageProps", {})
        print(f"pageProps keys: {list(pp.keys())[:20]}")

        # Walk for product data
        products_found = []

        def walk(obj, depth=0):
            if depth > 12:
                return
            if isinstance(obj, dict):
                name = obj.get("name") or obj.get("productName") or obj.get("title", "")
                price = obj.get("price") or obj.get("amountIncl") or obj.get("salesPrice")
                if not price:
                    offer = obj.get("offer") or obj.get("currentOffer") or {}
                    if isinstance(offer, dict):
                        po = offer.get("price", {})
                        if isinstance(po, dict):
                            price = po.get("amountIncl") or po.get("amount")
                        elif isinstance(po, (int, float)):
                            price = po

                if name and price and isinstance(name, str) and "mac" in name.lower():
                    products_found.append({"name": name, "price": price})

                for v in obj.values():
                    walk(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item, depth + 1)

        walk(data)
        print(f"\nProducts found in __NEXT_DATA__: {len(products_found)}")
        for p in products_found[:5]:
            print(f"  {p['name']} = {p['price']} CHF")

# Try Digitec DE search
print("\n" + "=" * 60)
print("DIGITEC SEARCH PAGE")
print("=" * 60)
r2 = s.get("https://www.digitec.ch/de/search?q=mac+mini", timeout=30)
print(f"HTTP {r2.status_code}")

if r2.status_code == 200:
    html2 = r2.text
    print(f"HTML length: {len(html2)}")

    jsonld2 = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html2, re.DOTALL
    )
    print(f"JSON-LD blocks: {len(jsonld2)}")
    for block in jsonld2[:3]:
        try:
            data = json.loads(block)
            dtype = data.get("@type", "unknown")
            print(f"  Type: {dtype}")
            items = data.get("itemListElement", [])
            if items:
                print(f"  Items: {len(items)}")
                for item in items[:3]:
                    prod = item.get("item", item)
                    print(f"    - {prod.get('name', '?')} = {prod.get('offers', {}).get('price', '?')} CHF")
        except Exception as e:
            print(f"  Parse error: {e}")

    nd2 = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html2)
    if nd2:
        data2 = json.loads(nd2.group(1))
        products_found2 = []

        def walk2(obj, depth=0):
            if depth > 12:
                return
            if isinstance(obj, dict):
                name = obj.get("name") or obj.get("productName") or obj.get("title", "")
                price = obj.get("price") or obj.get("amountIncl") or obj.get("salesPrice")
                if not price:
                    offer = obj.get("offer") or obj.get("currentOffer") or {}
                    if isinstance(offer, dict):
                        po = offer.get("price", {})
                        if isinstance(po, dict):
                            price = po.get("amountIncl") or po.get("amount")
                        elif isinstance(po, (int, float)):
                            price = po

                if name and price and isinstance(name, str) and "mac" in name.lower():
                    products_found2.append({"name": name, "price": price})

                for v in obj.values():
                    walk2(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    walk2(item, depth + 1)

        walk2(data2)
        print(f"\nProducts found in __NEXT_DATA__: {len(products_found2)}")
        for p in products_found2[:5]:
            print(f"  {p['name']} = {p['price']} CHF")

# Try Toppreise API directly
print("\n" + "=" * 60)
print("TOPPREISE API")
print("=" * 60)
# Try their API endpoint
for url in [
    "https://www.toppreise.ch/api/search?q=Mac+Mini",
    "https://www.toppreise.ch/api/products?q=Mac+Mini",
    "https://api.toppreise.ch/search?q=Mac+Mini",
    "https://www.toppreise.ch/service/search?q=Mac+Mini",
]:
    try:
        r3 = s.get(url, timeout=10)
        print(f"  {url}: HTTP {r3.status_code} size={len(r3.text)}")
        if r3.status_code == 200 and len(r3.text) > 100:
            print(f"    Preview: {r3.text[:300]}")
    except Exception as e:
        print(f"  {url}: {e}")
