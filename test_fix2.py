"""Fix Fust brotli, Apple price-name matching, Brack search."""
import json
import re
import sys
sys.path.insert(0, ".")
from src.utils.stealth import create_session

s = create_session()

# ========== FUST FIX: Disable brotli ==========
print("=" * 60)
print("FUST - with Accept-Encoding: gzip, deflate")
print("=" * 60)
s.headers["Accept-Encoding"] = "gzip, deflate"
r = s.get("https://www.fust.ch/handy-pc-tablet/pc-computer-monitore/mac-mini-mac-studio/c/f_mac_mini_mac_studio", timeout=30)
print(f"HTTP {r.status_code}, size={len(r.text)}, encoding={r.headers.get('content-encoding')}")

mac_count = len(re.findall(r'[Mm]ac\s*[Mm]ini', r.text))
print(f"Mac Mini mentions: {mac_count}")

if mac_count > 0:
    # Try RSC extraction
    rsc_chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', r.text, re.DOTALL)
    print(f"RSC chunks: {len(rsc_chunks)}")

    combined = "".join(rsc_chunks)
    combined = combined.replace('\\"', '"').replace('\\n', '\n').replace('\\/', '/')

    mac_matches = list(re.finditer(r'"name"\s*:\s*"(Mac Mini[^"]*)"', combined, re.IGNORECASE))
    print(f"Mac Mini products: {len(mac_matches)}")
    for m in mac_matches:
        start = max(0, m.start() - 500)
        end = min(len(combined), m.end() + 500)
        ctx = combined[start:end]
        chf = re.search(r'CHF\s*([\d.]+)', ctx)
        val = re.search(r'"value"\s*:\s*"?([\d.]+)"?', ctx)
        print(f"  {m.group(1)} -> CHF={chf.group(1) if chf else '?'}, value={val.group(1) if val else '?'}")
else:
    print("HTML preview (decoded):")
    print(r.text[:500])

# Reset encoding
s.headers["Accept-Encoding"] = "gzip, deflate"

# ========== APPLE FIX: Extract product tiles ==========
print("\n" + "=" * 60)
print("APPLE - Structured extraction")
print("=" * 60)
r2 = s.get("https://www.apple.com/ch-de/shop/buy-mac/mac-mini", timeout=30)
print(f"HTTP {r2.status_code}")

if r2.status_code == 200:
    html = r2.text

    # Strategy: Apple uses product "tiles" where each tile has a description + price
    # The tiles are separate HTML sections
    # Let's find all "Ab CHF XXX" prices and associate them with product configs

    # First, get all product descriptions (they appear in order)
    descriptions = []
    for m in re.finditer(r'Mac\s*mini,\s*M\d[^"<\n]{0,200}', html, re.IGNORECASE):
        desc = re.sub(r'<[^>]+>', ' ', m.group()).strip()
        desc = re.sub(r'\s+', ' ', desc)
        desc = desc.replace('\u00a0', ' ').replace('\u202f', ' ').replace('\u2011', '-')
        if desc not in [d['text'] for d in descriptions]:  # Dedupe
            descriptions.append({'text': desc, 'pos': m.start()})

    print(f"Product descriptions: {len(descriptions)}")
    for d in descriptions:
        print(f"  pos={d['pos']}: {d['text'][:100]}")

    # Get all "Ab CHF" or "CHF" prices >= 400
    prices = []
    for m in re.finditer(r'(?:Ab\s+)?CHF\s*([\d\',.]+)', html):
        ps = m.group(1).replace("'", "").replace(",", ".")
        try:
            p = float(ps)
            if 400 <= p <= 10000:
                prices.append({'price': p, 'pos': m.start()})
        except:
            pass

    # Deduplicate prices
    seen = set()
    unique_prices = []
    for p in prices:
        if p['price'] not in seen:
            seen.add(p['price'])
            unique_prices.append(p)

    print(f"\nUnique prices (CHF 400+): {len(unique_prices)}")
    for p in unique_prices:
        print(f"  pos={p['pos']}: CHF {p['price']}")

    # Match: for each description, find the nearest price AFTER it
    print("\nMatching descriptions to prices:")
    for desc in descriptions:
        # Find nearest price after this description
        nearest = None
        for p in prices:
            if p['pos'] > desc['pos']:
                if nearest is None or p['pos'] < nearest['pos']:
                    nearest = p
        if nearest:
            print(f"  {desc['text'][:80]} -> CHF {nearest['price']}")


# ========== BRACK FIX: Search page ==========
print("\n" + "=" * 60)
print("BRACK - Search page analysis")
print("=" * 60)
r3 = s.get("https://www.brack.ch/search?q=mac+mini", timeout=60)
print(f"HTTP {r3.status_code}, size={len(r3.text)}")

if r3.status_code == 200:
    # JSON-LD
    jsonld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', r3.text, re.DOTALL)
    print(f"JSON-LD blocks: {len(jsonld)}")
    for block in jsonld:
        try:
            data = json.loads(block)
            print(f"  @type: {data.get('@type')}")
            items = data.get("itemListElement", [])
            main_items = data.get("mainEntity", {}).get("itemListElement", [])
            print(f"  Items: {len(items)}, MainEntity items: {len(main_items)}")
        except:
            pass

    # Find product data in HTML
    # Brack uses specific product card HTML
    product_cards = re.findall(r'class="[^"]*product-card[^"]*"(.*?)</article>', r3.text, re.DOTALL)
    print(f"\nProduct cards: {len(product_cards)}")

    # Find product links
    prod_links = re.findall(r'href="(/[^"]*)"[^>]*>\s*(Mac[^<]*mini[^<]*)</a>', r3.text, re.IGNORECASE)
    print(f"Mac Mini links: {len(prod_links)}")
    for href, name in prod_links[:5]:
        print(f"  {name.strip()} -> {href}")

    # Find product data in script tags
    for m in re.finditer(r'<script[^>]*>(.*?)</script>', r3.text, re.DOTALL):
        script = m.group(1)
        if 'mac mini' in script.lower() and ('price' in script.lower() or 'chf' in script.lower()):
            if 50 < len(script) < 100000:
                # Find product names with prices
                product_names = re.findall(r'"name"\s*:\s*"([^"]*[Mm]ac[^"]*[Mm]ini[^"]*)"', script)
                print(f"\nScript with Mac Mini products (len={len(script)}):")
                print(f"  Names: {product_names[:5]}")
                product_prices = re.findall(r'"price"\s*:\s*"?([\d.]+)"?', script)
                print(f"  Prices: {product_prices[:5]}")

    # Find Mac Mini mentions in page text
    mac_texts = re.findall(r'Mac\s*mini[^<]{0,100}', r3.text, re.IGNORECASE)
    print(f"\nMac Mini text matches: {len(mac_texts)}")
    for mt in mac_texts[:10]:
        print(f"  {mt.strip()[:100]}")
