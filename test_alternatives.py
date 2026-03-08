"""Try alternative price sources for Swiss Mac Mini prices."""
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


def try_url(name, url, timeout=15):
    try:
        r = session.get(url, timeout=timeout)
        print(f"\n{name}: HTTP {r.status_code}, size={len(r.text)}")
        if r.status_code == 200 and len(r.text) > 500:
            # Check for product-like content
            text = r.text.lower()
            has_mac = "mac mini" in text or "mac-mini" in text
            has_price = bool(re.search(r'\d{3,4}[.,]\d{2}', r.text))
            print(f"  Has 'mac mini': {has_mac}, Has price: {has_price}")
            if has_mac:
                # Try JSON-LD
                jsonld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', r.text, re.DOTALL)
                if jsonld:
                    print(f"  JSON-LD blocks: {len(jsonld)}")
                    for block in jsonld[:2]:
                        try:
                            data = json.loads(block)
                            items = data.get("itemListElement", [])
                            if items:
                                print(f"  {len(items)} items found!")
                                for item in items[:3]:
                                    prod = item.get("item", item)
                                    print(f"    {prod.get('name')} = CHF {prod.get('offers',{}).get('price')}")
                        except:
                            pass
                return r
        return None
    except Exception as e:
        print(f"\n{name}: Error - {e}")
        return None


# 1. Geizhals.ch - Swiss price comparison (owns Toppreise)
print("=" * 60)
print("GEIZHALS.CH")
print("=" * 60)
try_url("Geizhals search", "https://geizhals.ch/?fs=mac+mini&hloc=ch")
try_url("Geizhals category", "https://geizhals.ch/mac-mini.html")
try_url("Geizhals Mac Mini M4", "https://geizhals.ch/?cat=sysdiv&xf=21862_Apple+Mac+mini")

# 2. Preisvergleich.ch
print("\n" + "=" * 60)
print("PREISVERGLEICH.CH")
print("=" * 60)
try_url("Preisvergleich", "https://www.preisvergleich.ch/search?q=mac+mini")
try_url("Preisvergleich2", "https://preisvergleich.ch/search?q=mac+mini")

# 3. Comparis.ch price comparison
print("\n" + "=" * 60)
print("COMPARIS.CH")
print("=" * 60)
try_url("Comparis", "https://www.comparis.ch/comparis/search?q=mac+mini")

# 4. PriceRunner.ch
print("\n" + "=" * 60)
print("PRICERUNNER.CH")
print("=" * 60)
try_url("PriceRunner", "https://www.pricerunner.ch/search?q=mac+mini")

# 5. Interdiscount.ch (Swiss electronics retailer)
print("\n" + "=" * 60)
print("INTERDISCOUNT.CH")
print("=" * 60)
r = try_url("Interdiscount", "https://www.interdiscount.ch/de/search?q=mac+mini")
if r and r.status_code == 200:
    # Look for product data
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text)
    if nd:
        print("  Has __NEXT_DATA__")

# 6. Microspot.ch
print("\n" + "=" * 60)
print("MICROSPOT.CH")
print("=" * 60)
try_url("Microspot", "https://www.microspot.ch/de/search?q=mac+mini")

# 7. Fust.ch
print("\n" + "=" * 60)
print("FUST.CH")
print("=" * 60)
try_url("Fust search", "https://www.fust.ch/de/search?q=mac+mini")
try_url("Fust catalog", "https://www.fust.ch/de/c/computer-gaming/mac/mac-mini/~cat460")

# 8. Melectronics (Migros)
print("\n" + "=" * 60)
print("MELECTRONICS")
print("=" * 60)
try_url("Melectronics", "https://www.melectronics.ch/de/search?q=mac+mini")

# 9. Apple.ch direct
print("\n" + "=" * 60)
print("APPLE.CH")
print("=" * 60)
r = try_url("Apple Store CH", "https://www.apple.com/ch-de/shop/buy-mac/mac-mini")
if r and r.status_code == 200:
    # Find product names and prices
    prices = re.findall(r'CHF\s*([\d\',.]+)', r.text)
    print(f"  CHF prices found: {prices[:10]}")

# 10. Steg Electronics
print("\n" + "=" * 60)
print("STEG.CH")
print("=" * 60)
try_url("Steg", "https://www.steg-electronics.ch/de/search?q=mac+mini")
