"""Test if Digitec can be scraped via plain requests (no Playwright)."""
import re
import json
import sys
sys.path.insert(0, ".")

from src.utils.stealth import create_session

s = create_session()
r = s.get("https://www.digitec.ch/de/search?q=mac+mini", timeout=30)
print(f"Status: {r.status_code}, Length: {len(r.text)}")

if r.status_code == 200:
    nd_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text)
    if nd_match:
        raw = nd_match.group(1)
        print(f"Found __NEXT_DATA__ ({len(raw)} chars)")
        data = json.loads(raw)
        text = json.dumps(data)

        # Look for price amounts
        prices = re.findall(r'"amountIncl":([\d.]+)', text)
        names = re.findall(r'"name":"([^"]*[Mm]ac[^"]*)"', text)
        urls = re.findall(r'"url":"(/de/product/[^"]*mac[^"]*)"', text, re.IGNORECASE)
        product_ids = re.findall(r'"productId":(\d+)', text)

        print(f"Prices: {prices[:10]}")
        print(f"Names: {names[:10]}")
        print(f"URLs: {urls[:5]}")
        print(f"Product IDs: {product_ids[:10]}")
    else:
        print("No __NEXT_DATA__ found")
        # Check if it's a bot challenge page
        if "captcha" in r.text.lower() or "challenge" in r.text.lower():
            print("Bot challenge detected!")
        title = re.search(r"<title>(.*?)</title>", r.text)
        print(f"Title: {title.group(1) if title else 'none'}")
else:
    print(f"HTTP {r.status_code}")
    print(r.text[:500])
