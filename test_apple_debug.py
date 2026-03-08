"""Debug Apple Store price extraction."""
import re
import sys
sys.path.insert(0, ".")
from src.utils.stealth import create_session

s = create_session()
r = s.get("https://www.apple.com/ch-de/shop/buy-mac/mac-mini", timeout=30)

html = r.text

# Find ALL CHF prices >= 400 with their context
print("All CHF prices >= 400 with context:")
for m in re.finditer(r'(?:Ab\s+)?CHF\s*([\d\',.]+)', html):
    ps = m.group(1).replace("'", "").replace(",", ".")
    try:
        p = float(ps)
        if p >= 400:
            before = html[max(0,m.start()-200):m.start()]
            after = html[m.end():m.end()+100]
            # Clean HTML
            before_clean = re.sub(r'<[^>]+>', '|', before)[-100:]
            after_clean = re.sub(r'<[^>]+>', '|', after)[:50]
            print(f"  CHF {p:8.2f} | before: ...{before_clean}")
            print(f"             | after: {after_clean}")
            print()
    except:
        pass

# Find product descriptions with their full context
print("\n\nProduct description contexts:")
for m in re.finditer(r'Mac\s*mini,\s*M\d[^"<\n]{0,200}', html, re.IGNORECASE):
    desc = m.group()
    desc_clean = re.sub(r'\s+', ' ', desc).strip()
    # Look for "Ab CHF" or "CHF" within 2000 chars after
    after_section = html[m.end():m.end()+3000]
    price_match = re.search(r'(?:Ab\s+)?CHF\s*([\d\',.]+)', after_section)
    if price_match:
        ps = price_match.group(1).replace("'", "").replace(",", ".")
        print(f"  {desc_clean[:100]}")
        print(f"    -> First CHF after: {ps} (offset: {price_match.start()} chars)")
    else:
        print(f"  {desc_clean[:100]} -> NO CHF AFTER")
    print()
