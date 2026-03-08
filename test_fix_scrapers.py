"""Fix scraper issues found on server."""
import json
import re
import sys
sys.path.insert(0, ".")
from src.utils.stealth import create_session

s = create_session()

# ========== FIX FUST ==========
print("=" * 60)
print("FUST - Finding RSC data format on server")
print("=" * 60)
r = s.get("https://www.fust.ch/handy-pc-tablet/pc-computer-monitore/mac-mini-mac-studio/c/f_mac_mini_mac_studio", timeout=30)
print(f"HTTP {r.status_code}, size={len(r.text)}")

# Check if it's compressed/different format
# Look for Mac Mini in raw HTML
mac_count = len(re.findall(r'[Mm]ac\s*[Mm]ini', r.text))
print(f"Mac Mini mentions in raw HTML: {mac_count}")

# Try different RSC patterns
patterns = [
    r'self\.__next_f\.push\(\[1,"(.*?)"\]\)',
    r'self\.__next_f\.push\(\[(.*?)\]\)',
    r'self\.__next_f\.push\((\[.*?\])\)',
]
for pat in patterns:
    matches = re.findall(pat, r.text, re.DOTALL)
    print(f"Pattern '{pat[:40]}...': {len(matches)} matches")

# Try finding product data directly in HTML
# Look for price patterns
prices = re.findall(r'CHF\s*([\d.]+)', r.text)
print(f"\nCHF prices in HTML: {prices}")

# Look for product names
prod_names = re.findall(r'Mac Mini[^"<]{0,200}', r.text, re.IGNORECASE)
print(f"Mac Mini product strings: {len(prod_names)}")
for pn in prod_names[:5]:
    print(f"  {pn[:150]}")

# Find product data in any script tags
for m in re.finditer(r'<script[^>]*>(.*?)</script>', r.text, re.DOTALL):
    script = m.group(1)
    if 'mac mini' in script.lower() and 'chf' in script.lower():
        print(f"\nScript with Mac Mini + CHF (len={len(script)}):")
        # Find price near Mac Mini
        for mm in re.finditer(r'Mac Mini', script, re.IGNORECASE):
            ctx = script[max(0,mm.start()-200):mm.start()+400]
            chf_match = re.search(r'CHF\s*([\d.]+)', ctx)
            if chf_match:
                print(f"  {ctx[200:300]}... -> CHF {chf_match.group(1)}")

# Check if HTML uses different encoding or is gzipped differently
print(f"\nContent-Type: {r.headers.get('content-type')}")
print(f"Content-Encoding: {r.headers.get('content-encoding')}")
print(f"First 500 chars:\n{r.text[:500]}")


# ========== FIX APPLE ==========
print("\n\n" + "=" * 60)
print("APPLE - Finding product-price associations")
print("=" * 60)
r2 = s.get("https://www.apple.com/ch-de/shop/buy-mac/mac-mini", timeout=30)
print(f"HTTP {r2.status_code}, size={len(r2.text)}")

# The product names are in the HTML but prices aren't nearby
# Apple uses specific HTML structure - let's find it
# Find all product descriptions
descs = re.findall(r'(Mac\s*mini,\s*M\d[^"<]{0,200})', r2.text, re.IGNORECASE)
print(f"Product descriptions: {len(descs)}")
for d in descs:
    clean = re.sub(r'<[^>]+>', ' ', d).strip()
    clean = re.sub(r'\s+', ' ', clean)
    print(f"  {clean[:120]}")

# Find the prices and their HTML context
for m in re.finditer(r'Ab\s+CHF\s*([\d.]+)', r2.text):
    price = m.group(1)
    # Check wider context around the price
    start = max(0, m.start() - 2000)
    before = r2.text[start:m.start()]
    after = r2.text[m.end():m.end()+200]

    # Find closest Mac mini description
    name_match = re.search(r'(Mac\s*mini.*?)(?:$)', before[-1000:])
    if name_match:
        print(f"\n  Price CHF {price}, name nearby: {name_match.group(1)[:100]}")
    else:
        # Print surrounding HTML for pattern analysis
        ctx = r2.text[m.start()-100:m.start()+100]
        print(f"\n  Price CHF {price}, context: {ctx[:200]}")

# Try JSON-LD approach
jsonld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', r2.text, re.DOTALL)
print(f"\nJSON-LD blocks: {len(jsonld)}")
for block in jsonld:
    try:
        data = json.loads(block)
        print(f"  @type: {data.get('@type')}")
        print(f"  Data: {json.dumps(data)[:400]}")
    except:
        pass

# Find product sections using HTML structure
# Apple uses data-autom attributes
sections = re.findall(r'data-autom="([^"]*)"', r2.text)
product_sections = [s for s in sections if 'product' in s.lower() or 'hero' in s.lower()]
print(f"\nProduct-related data-autom: {product_sections[:20]}")


# ========== FIX BRACK ==========
print("\n\n" + "=" * 60)
print("BRACK - Finding correct URL")
print("=" * 60)
brack_urls = [
    "https://www.brack.ch/mac-mini",
    "https://www.brack.ch/computer-zubehoer/apple-mac/mac-mini",
    "https://www.brack.ch/search?q=mac+mini",
    "https://www.brack.ch/search?query=mac+mini",
]
for url in brack_urls:
    try:
        r3 = s.get(url, timeout=30)
        print(f"  {url}: HTTP {r3.status_code}, size={len(r3.text)}")
        if r3.status_code == 200:
            jsonld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', r3.text, re.DOTALL)
            print(f"    JSON-LD: {len(jsonld)} blocks")
            for block in jsonld[:1]:
                try:
                    data = json.loads(block)
                    items = data.get("itemListElement", [])
                    print(f"    Items: {len(items)}")
                    if items:
                        prod = items[0].get("item", items[0])
                        print(f"    First: {prod.get('name')} = {prod.get('offers',{}).get('price')}")
                except:
                    pass
            break
    except Exception as e:
        print(f"  {url}: {e}")
