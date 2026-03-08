"""Test Galaxus with different approaches."""
import json
import re
import sys
sys.path.insert(0, ".")
from src.utils.stealth import create_session

s = create_session()

# Approach 1: requests with Accept-Encoding fix
print("=" * 60)
print("APPROACH 1: requests (no brotli)")
print("=" * 60)
s.headers["Accept-Encoding"] = "gzip, deflate"
r = s.get("https://www.galaxus.ch/en/search?q=mac+mini", timeout=30)
print(f"HTTP {r.status_code}, size={len(r.text)}")

if r.status_code == 200:
    # JSON-LD
    jsonld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', r.text, re.DOTALL)
    print(f"JSON-LD blocks: {len(jsonld)}")
    for block in jsonld[:3]:
        try:
            data = json.loads(block)
            print(f"  @type: {data.get('@type')}")
            items = data.get("itemListElement", [])
            if items:
                print(f"  Items: {len(items)}")
                for item in items[:3]:
                    prod = item.get("item", item)
                    print(f"    {prod.get('name')} = {prod.get('offers',{}).get('price')}")
        except:
            pass

    # __NEXT_DATA__
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text)
    if nd:
        data = json.loads(nd.group(1))
        print(f"\n__NEXT_DATA__ found, keys: {list(data.keys())}")
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
                if n and p and isinstance(n, str) and "mac" in n.lower():
                    found.append({"name": n, "price": p})
                for v in obj.values():
                    walk(v, d+1)
            elif isinstance(obj, list):
                for i in obj:
                    walk(i, d+1)
        walk(data)
        print(f"Products in __NEXT_DATA__: {len(found)}")
        for f in found[:10]:
            print(f"  {f['name']} = CHF {f['price']}")

    # Check for any mac mini content
    mac_count = len(re.findall(r'[Mm]ac\s*[Mm]ini', r.text))
    print(f"\nMac Mini mentions: {mac_count}")
elif r.status_code == 403:
    # Check if it's Datadome
    print(f"Headers: {dict(r.headers)}")
    print(f"Body preview: {r.text[:300]}")

# Approach 2: Try different URLs
print("\n" + "=" * 60)
print("APPROACH 2: Different Galaxus URLs")
print("=" * 60)
urls = [
    "https://www.galaxus.ch/en/s1/producttype/mini-pc-nettop-220?filter=t_bra%3D47",
    "https://www.galaxus.ch/en/brand/apple-47/mini-pc-nettop-220",
    "https://www.galaxus.ch/de/search?q=mac+mini",
    "https://www.galaxus.ch/en/search?q=mac%20mini",
]
for url in urls:
    try:
        r2 = s.get(url, timeout=15)
        print(f"\n{url}")
        print(f"  HTTP {r2.status_code}, size={len(r2.text)}")
        if r2.status_code == 200:
            mac_count = len(re.findall(r'[Mm]ac\s*[Mm]ini', r2.text))
            print(f"  Mac Mini mentions: {mac_count}")
    except Exception as e:
        print(f"\n{url}: {e}")

# Approach 3: Try Playwright with headless=False simulation
print("\n" + "=" * 60)
print("APPROACH 3: Playwright")
print("=" * 60)
try:
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-CH",
            timezone_id="Europe/Zurich",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = ctx.new_page()
        Stealth().apply_stealth_sync(page)

        def on_resp(resp):
            url = resp.url
            if "graphql" in url or "search" in url.split("?")[0]:
                try:
                    ct = resp.headers.get("content-type", "")
                    if "json" in ct:
                        body = resp.text()
                        if len(body) > 200:
                            captured.append({"url": url[:200], "size": len(body), "body": body[:3000]})
                except:
                    pass

        page.on("response", on_resp)

        try:
            page.goto("https://www.galaxus.ch/en/search?q=mac+mini", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            print(f"Title: {page.title()}")
            print(f"URL: {page.url}")

            # Get page content
            html = page.content()
            print(f"HTML size: {len(html)}")
            mac_count = len(re.findall(r'[Mm]ac\s*[Mm]ini', html))
            print(f"Mac Mini mentions: {mac_count}")

            # Check captured API responses
            print(f"\nCaptured API responses: {len(captured)}")
            for c in captured[:5]:
                print(f"  URL: {c['url']}")
                print(f"  Size: {c['size']}")
                if "mac" in c["body"].lower():
                    print(f"  Contains 'mac'!")
                    print(f"  Preview: {c['body'][:500]}")

        except Exception as e:
            print(f"Navigation error: {e}")

        browser.close()
except ImportError:
    print("Playwright not installed")
