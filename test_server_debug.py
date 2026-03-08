"""Debug why Fust and Apple return 0 on server."""
import json
import logging
import re
import sys

logging.basicConfig(level=logging.DEBUG, format="%(message)s")
sys.path.insert(0, ".")

from src.utils.stealth import create_session

s = create_session()

# Test Fust
print("=" * 60)
print("FUST")
print("=" * 60)
url = "https://www.fust.ch/handy-pc-tablet/pc-computer-monitore/mac-mini-mac-studio/c/f_mac_mini_mac_studio"
try:
    r = s.get(url, timeout=30)
    print(f"HTTP {r.status_code}, size={len(r.text)}")
    if r.status_code == 200:
        rsc_chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', r.text, re.DOTALL)
        combined = "".join(rsc_chunks)
        combined = combined.replace('\\"', '"').replace('\\n', '\n').replace('\\/', '/')
        mac_matches = list(re.finditer(r'"name"\s*:\s*"(Mac Mini[^"]*)"', combined, re.IGNORECASE))
        print(f"RSC chunks: {len(rsc_chunks)}")
        print(f"Mac Mini matches: {len(mac_matches)}")
        for m in mac_matches:
            start = max(0, m.start() - 500)
            end = min(len(combined), m.end() + 500)
            ctx = combined[start:end]
            chf = re.search(r'CHF\s*([\d.]+)', ctx)
            val = re.search(r'"value"\s*:\s*"?([\d.]+)"?', ctx)
            print(f"  {m.group(1)} -> CHF={chf.group(1) if chf else '?'}, value={val.group(1) if val else '?'}")
    else:
        print(f"First 500 chars: {r.text[:500]}")
except Exception as e:
    print(f"Error: {e}")


# Test Apple
print("\n" + "=" * 60)
print("APPLE STORE CH")
print("=" * 60)
url2 = "https://www.apple.com/ch-de/shop/buy-mac/mac-mini"
try:
    r2 = s.get(url2, timeout=30)
    print(f"HTTP {r2.status_code}, size={len(r2.text)}")
    if r2.status_code == 200:
        # Find CHF prices >= 400
        for m in re.finditer(r'(?:Ab\s+)?CHF\s*([\d\',.]+)', r2.text):
            price_str = m.group(1).replace("'", "").replace(",", ".")
            try:
                price = float(price_str)
                if price >= 400:
                    before = r2.text[max(0, m.start()-500):m.start()]
                    name_match = re.search(r'(Mac\s*mini,\s*M\d[^<]{0,150})', before, re.IGNORECASE)
                    print(f"  CHF {price} <- {name_match.group(1)[:80] if name_match else 'NO NAME FOUND'}")
            except:
                pass
        # Also check what product names exist
        products = re.findall(r'Mac\s*mini,\s*M\d[^<]{0,100}', r2.text)
        print(f"\nMac Mini product strings: {len(products)}")
        for p in products[:10]:
            clean = re.sub(r'<[^>]+>', ' ', p).strip()
            clean = re.sub(r'\s+', ' ', clean)
            print(f"  {clean[:120]}")
    else:
        print(f"First 500 chars: {r2.text[:500]}")
except Exception as e:
    print(f"Error: {e}")


# Test Brack with longer timeout
print("\n" + "=" * 60)
print("BRACK (60s timeout)")
print("=" * 60)
try:
    r3 = s.get("https://www.brack.ch/mac-mini", timeout=60)
    print(f"HTTP {r3.status_code}, size={len(r3.text)}")
    if r3.status_code == 200:
        jsonld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', r3.text, re.DOTALL)
        print(f"JSON-LD blocks: {len(jsonld)}")
        for block in jsonld[:2]:
            try:
                data = json.loads(block)
                items = data.get("itemListElement", [])
                if items:
                    print(f"  Items: {len(items)}")
                    for item in items[:3]:
                        prod = item.get("item", item)
                        print(f"    {prod.get('name')} = {prod.get('offers',{}).get('price')}")
            except:
                pass
except Exception as e:
    print(f"Error: {e}")


# Test Geizhals
print("\n" + "=" * 60)
print("GEIZHALS")
print("=" * 60)
try:
    r4 = s.get("https://geizhals.ch/?cat=sysdiv&xf=21862_Apple+Mac+mini&hloc=ch&v=e", timeout=30)
    print(f"HTTP {r4.status_code}, size={len(r4.text)}")
    if r4.status_code == 200:
        products = re.findall(r'title="([^"]*[Mm]ac[^"]*[Mm]ini[^"]*)"', r4.text)
        print(f"Mac Mini product titles: {len(products)}")
        for p in products[:5]:
            print(f"  {p}")
except Exception as e:
    print(f"Error: {e}")
