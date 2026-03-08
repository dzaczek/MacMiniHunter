"""Test Brack with correct search params."""
import json
import re
import sys
sys.path.insert(0, ".")
from src.utils.stealth import create_session

s = create_session()

# Test with query= param (what scraper uses)
r = s.get("https://www.brack.ch/search", params={"query": "Mac Mini"}, timeout=60)
print(f"Brack search (query=): HTTP {r.status_code}, size={len(r.text)}")
print(f"  Final URL: {r.url}")

if r.status_code == 200:
    jsonld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', r.text, re.DOTALL)
    for block in jsonld:
        try:
            data = json.loads(block)
            if data.get("@type") == "CollectionPage":
                items = data.get("mainEntity", {}).get("itemListElement", [])
                print(f"  mainEntity items: {len(items)}")
                for item in items[:3]:
                    prod = item.get("item", {})
                    print(f"    {prod.get('name', '?')} = CHF {prod.get('offers', {}).get('price', '?')}")
        except:
            pass

# Also test with q= param
r2 = s.get("https://www.brack.ch/search", params={"q": "Mac Mini"}, timeout=60)
print(f"\nBrack search (q=): HTTP {r2.status_code}, size={len(r2.text)}")
print(f"  Final URL: {r2.url}")

if r2.status_code == 200:
    jsonld2 = re.findall(r'<script type="application/ld\+json">(.*?)</script>', r2.text, re.DOTALL)
    for block in jsonld2:
        try:
            data = json.loads(block)
            if data.get("@type") == "CollectionPage":
                items = data.get("mainEntity", {}).get("itemListElement", [])
                print(f"  mainEntity items: {len(items)}")
        except:
            pass
