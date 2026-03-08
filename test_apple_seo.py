"""Debug Apple seoPrice extraction."""
import re, sys
sys.path.insert(0, ".")
from src.utils.stealth import create_session

s = create_session()
r = s.get("https://www.apple.com/ch-de/shop/buy-mac/mac-mini", timeout=30)
html = r.text

# Find seoPrice entries
seo = re.findall(r'"(m4[^"]+)"[^}]*"seoPrice"\s*:\s*([\d.]+)', html)
print(f"seoPrice entries: {seo}")

# Try broader pattern
seo2 = re.findall(r'"seoPrice"\s*:\s*([\d.]+)', html)
print(f"All seoPrice values: {seo2}")

# Find the prices section
prices_section = re.search(r'"prices"\s*:\s*\{(.*?)\}\}', html, re.DOTALL)
if prices_section:
    print(f"\nPrices section (first 1000 chars):\n{prices_section.group()[:1000]}")
else:
    # Try to find where m4-10-10 appears
    m4_pos = html.find("m4-10-10")
    if m4_pos >= 0:
        print(f"\nm4-10-10 context:\n{html[m4_pos:m4_pos+500]}")
    else:
        m4_pos2 = html.find("m4pro")
        if m4_pos2 >= 0:
            print(f"\nm4pro context:\n{html[m4_pos2:m4_pos2+500]}")
        else:
            print("\nNo m4 key found. Looking for seoPrice anywhere:")
            for m in re.finditer(r'seoPrice', html):
                print(f"  pos {m.start()}: ...{html[m.start()-50:m.start()+100]}...")
