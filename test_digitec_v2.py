"""Try alternative approaches for Digitec/Galaxus."""
import json
import re
import sys
sys.path.insert(0, ".")

import requests

# Approach 1: Try with curl-like headers and HTTP/1.1
print("=" * 60)
print("APPROACH 1: Minimal headers, different UA")
print("=" * 60)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
})

# Try category page instead of search (less likely to be blocked)
urls = [
    "https://www.digitec.ch/de/s1/producttype/desktop-pc-382?filter=t_bra%3D47",  # Desktop PCs, brand=Apple
    "https://www.digitec.ch/de/s1/producttype/mini-pc-nettop-220?filter=t_bra%3D47",  # Mini PC/Nettop, brand=Apple
    "https://www.digitec.ch/de/brand/apple-47/mini-pc-nettop-220",
    "https://www.galaxus.ch/de/s1/producttype/mini-pc-nettop-220?filter=t_bra%3D47",
    "https://www.galaxus.ch/de/brand/apple-47/mini-pc-nettop-220",
]

for url in urls:
    try:
        r = session.get(url, timeout=15, allow_redirects=True)
        print(f"\n{url}")
        print(f"  HTTP {r.status_code}, size={len(r.text)}")
        if r.status_code == 200:
            # Check for product data
            jsonld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', r.text, re.DOTALL)
            print(f"  JSON-LD blocks: {len(jsonld)}")
            for block in jsonld:
                try:
                    data = json.loads(block)
                    items = data.get("itemListElement", [])
                    if items:
                        print(f"  Found {len(items)} items!")
                        for item in items[:3]:
                            prod = item.get("item", item)
                            print(f"    {prod.get('name', '?')} = {prod.get('offers', {}).get('price', '?')}")
                except:
                    pass

            nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text)
            if nd:
                nd_data = json.loads(nd.group(1))
                # Look for products
                found = []
                def walk(obj, d=0):
                    if d > 10: return
                    if isinstance(obj, dict):
                        n = obj.get("name") or obj.get("productName") or ""
                        p = obj.get("price") or obj.get("amountIncl")
                        if not p:
                            o = obj.get("offer") or obj.get("currentOffer") or {}
                            if isinstance(o, dict):
                                po = o.get("price", {})
                                p = po.get("amountIncl") if isinstance(po, dict) else po
                        if n and p and "mac" in str(n).lower():
                            found.append(f"{n} = {p}")
                        for v in obj.values():
                            walk(v, d+1)
                    elif isinstance(obj, list):
                        for i in obj:
                            walk(i, d+1)
                walk(nd_data)
                print(f"  Products in __NEXT_DATA__: {len(found)}")
                for f in found[:5]:
                    print(f"    {f}")
    except Exception as e:
        print(f"\n{url}")
        print(f"  Error: {e}")


# Approach 2: Try the Digitec product type JSON API
print("\n" + "=" * 60)
print("APPROACH 2: Digitec producttype API")
print("=" * 60)

api_urls = [
    "https://www.digitec.ch/api/graphql",  # POST with search
]

# Try fetching the search API with a proper GraphQL query
gql_payload = [{
    "operationName": "SEARCH_PRODUCTS",
    "variables": {
        "searchTerm": "mac mini",
        "offset": 0,
        "limit": 24,
        "sortOrder": None,
        "siteId": None,
    },
    "query": """query SEARCH_PRODUCTS($searchTerm: String!, $offset: Int, $limit: Int) {
        search(searchTerm: $searchTerm, offset: $offset, limit: $limit) {
            products {
                name
                brandName
                currentOffer {
                    price {
                        amountIncl
                    }
                }
                url
            }
        }
    }"""
}]

try:
    r = session.post(
        "https://www.digitec.ch/api/graphql",
        json=gql_payload,
        headers={
            "Content-Type": "application/json",
            "x-dg-portal": "1",
        },
        timeout=15,
    )
    print(f"GraphQL: HTTP {r.status_code}")
    print(f"Body: {r.text[:500]}")
except Exception as e:
    print(f"GraphQL error: {e}")


# Approach 3: Try Toppreise with different URL patterns
print("\n" + "=" * 60)
print("APPROACH 3: Toppreise alternative URLs")
print("=" * 60)

tp_urls = [
    "https://www.toppreise.ch/de/cat/nettop-barebone-2",  # Category without filter
    "https://www.toppreise.ch/de/prod/Apple-Mac-mini",
    "https://www.toppreise.ch/api/v2/search?q=mac+mini",
]

for url in tp_urls:
    try:
        r = session.get(url, timeout=10)
        print(f"{url}: HTTP {r.status_code} size={len(r.text)}")
        if r.status_code == 200 and len(r.text) > 500:
            if "mac" in r.text.lower():
                print("  Contains 'mac'!")
                print(f"  Preview: {r.text[:300]}")
    except Exception as e:
        print(f"{url}: {e}")
