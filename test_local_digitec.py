"""Test Digitec/Galaxus from local machine to find working approach."""
import json
import re
import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
})

# Try Galaxus search
print("Testing Galaxus search...")
r = session.get("https://www.galaxus.ch/en/search?q=mac+mini", timeout=30)
print(f"HTTP {r.status_code}, size={len(r.text)}")

if r.status_code == 200:
    # JSON-LD
    jsonld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', r.text, re.DOTALL)
    print(f"JSON-LD blocks: {len(jsonld)}")
    for block in jsonld[:3]:
        try:
            data = json.loads(block)
            print(f"  Type: {data.get('@type')}")
            items = data.get("itemListElement", [])
            if items:
                print(f"  Items: {len(items)}")
                for item in items[:3]:
                    prod = item.get("item", item)
                    print(f"    {prod.get('name')} = {prod.get('offers', {}).get('price')} CHF")
        except:
            pass

    # __NEXT_DATA__
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text)
    if nd:
        data = json.loads(nd.group(1))
        # Save for analysis
        with open("/tmp/galaxus_nextdata.json", "w") as f:
            json.dump(data, f, indent=2)
        print(f"Saved __NEXT_DATA__ to /tmp/galaxus_nextdata.json")

        # Walk for products
        found = []
        def walk(obj, d=0):
            if d > 15: return
            if isinstance(obj, dict):
                n = obj.get("name") or obj.get("productName") or ""
                p = obj.get("price") or obj.get("amountIncl")
                if not p:
                    o = obj.get("offer") or obj.get("currentOffer") or {}
                    if isinstance(o, dict):
                        po = o.get("price", {})
                        p = po.get("amountIncl") if isinstance(po, dict) else po
                if n and p and isinstance(n, str):
                    found.append(f"{n} = {p}")
                for v in obj.values():
                    walk(v, d+1)
            elif isinstance(obj, list):
                for i in obj:
                    walk(i, d+1)
        walk(data)
        print(f"Products in __NEXT_DATA__: {len(found)}")
        for f2 in found[:10]:
            print(f"  {f2}")
else:
    print(f"Response preview: {r.text[:500]}")
