"""Final attempt at Galaxus - find search query ID and call it."""
import json
import re
import sys
import time
sys.path.insert(0, ".")

import requests

# Fresh session with browser-like headers
s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-CH,en;q=0.9,de-CH;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
})

# First visit homepage to get cookies
print("Visiting homepage...")
time.sleep(2)
r0 = s.get("https://www.galaxus.ch/en", timeout=30)
print(f"Homepage: HTTP {r0.status_code}")

time.sleep(3)

# Now visit search page
print("\nVisiting search page...")
r = s.get("https://www.galaxus.ch/en/search?q=mac+mini", timeout=30)
print(f"Search: HTTP {r.status_code}, size={len(r.text)}")

if r.status_code != 200:
    print("Blocked by Datadome")
    print(f"Cookies: {dict(s.cookies)}")
    sys.exit(1)

nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text)
if not nd:
    print("No __NEXT_DATA__")
    sys.exit(1)

data = json.loads(nd.group(1))
build_id = data.get("buildId")
print(f"Build ID: {build_id}")

# Get JS chunks to find search query ID
script_srcs = re.findall(r'src="([^"]+\.js[^"]*)"', r.text)
print(f"\nJS chunks: {len(script_srcs)}")

# Download chunks and find search query definitions
time.sleep(2)
found_queries = {}

for i, src in enumerate(script_srcs):
    url = src if src.startswith("http") else f"https://www.galaxus.ch{src}"
    try:
        jr = s.get(url, timeout=10)
        if jr.status_code != 200:
            continue
        js = jr.text

        # Find Relay persisted query IDs
        # Pattern: {id:"hash",metadata:{...},name:"QueryName",operationKind:"query"}
        query_defs = re.findall(
            r'\{[^{}]*id\s*:\s*"([a-f0-9]{32,64})"[^{}]*name\s*:\s*"([^"]+)"[^{}]*operationKind\s*:\s*"([^"]+)"[^{}]*\}',
            js
        )
        for qid, name, kind in query_defs:
            found_queries[name] = {"id": qid, "kind": kind}

        # Also try alternative pattern
        alt_defs = re.findall(r'id:"([a-f0-9]{32,64})",metadata:\{[^}]*\},name:"([^"]+)"', js)
        for qid, name in alt_defs:
            if name not in found_queries:
                found_queries[name] = {"id": qid, "kind": "query"}

        if i % 5 == 4:
            time.sleep(1)

    except:
        continue

print(f"\nFound {len(found_queries)} Relay queries:")
for name, info in sorted(found_queries.items()):
    tag = " <-- SEARCH" if "search" in name.lower() else ""
    tag = tag or (" <-- PRODUCT" if "product" in name.lower() else "")
    print(f"  {name}: {info['id'][:16]}... ({info['kind']}){tag}")

# Try search-related queries
search_queries = {k: v for k, v in found_queries.items()
                  if "search" in k.lower() or "product" in k.lower() or "listing" in k.lower()}

if search_queries:
    print(f"\n\nTrying {len(search_queries)} search queries on gateway:")

    pp = data["props"]["pageProps"]
    search_vars = pp.get("variables", {})

    for name, info in search_queries.items():
        time.sleep(1)
        payload = {
            "id": info["id"],
            "variables": search_vars,
        }
        try:
            gr = s.post("https://www.galaxus.ch/graphql", json=payload, timeout=15, headers={
                "Content-Type": "application/json",
                "Origin": "https://www.galaxus.ch",
                "Referer": "https://www.galaxus.ch/en/search?q=mac+mini",
            })
            body = gr.text
            has_products = "productId" in body or "productName" in body or '"name"' in body
            print(f"\n  {name}: HTTP {gr.status_code}, size={len(body)}, has_products={has_products}")
            if has_products and len(body) > 500:
                # Parse and find products
                try:
                    result = json.loads(body)
                    # Walk for product data
                    products = []
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
                            if n and isinstance(n, str) and len(n) > 5:
                                products.append({"name": n, "price": p})
                            for v in obj.values():
                                walk(v, d+1)
                        elif isinstance(obj, list):
                            for item in obj:
                                walk(item, d+1)
                    walk(result)
                    mac_products = [p for p in products if "mac" in p["name"].lower()]
                    print(f"  Products: {len(products)}, Mac Mini: {len(mac_products)}")
                    for mp in mac_products[:5]:
                        print(f"    {mp['name']} = CHF {mp['price']}")
                except:
                    print(f"  Body preview: {body[:500]}")
            elif len(body) < 500:
                print(f"  Body: {body[:500]}")
        except Exception as e:
            print(f"\n  {name}: {e}")
