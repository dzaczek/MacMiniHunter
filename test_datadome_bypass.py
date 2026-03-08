"""Try to work through Datadome challenge on Galaxus."""
import json
import re
import sys
import time
sys.path.insert(0, ".")


def test_galaxus_playwright():
    """Try Playwright with full stealth and waiting for challenge."""
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="de-CH",
            timezone_id="Europe/Zurich",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        # Remove webdriver flag
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            delete navigator.__proto__.webdriver;
        """)

        captured_data = []

        def on_response(resp):
            if resp.status >= 200 and resp.status < 400:
                ct = resp.headers.get("content-type", "")
                if "json" in ct and len(resp.url) < 500:
                    try:
                        body = resp.text()
                        if "mac" in body.lower() or "product" in body.lower():
                            captured_data.append({
                                "url": resp.url[:200],
                                "body": body[:5000],
                            })
                    except:
                        pass

        page.on("response", on_response)

        # Try the EN search page
        print("Navigating to Galaxus search...")
        try:
            page.goto(
                "https://www.galaxus.ch/en/search?q=mac+mini",
                wait_until="domcontentloaded",
                timeout=60000,
            )
        except Exception as e:
            print(f"Navigation error: {e}")

        # Wait and check
        page.wait_for_timeout(5000)
        print(f"Title: {page.title()}")
        print(f"URL: {page.url}")
        html = page.content()
        print(f"HTML length: {len(html)}")

        # Check if we got Datadome challenge
        if "captcha" in html.lower() or "datadome" in html.lower():
            print("Datadome challenge detected, waiting...")
            page.wait_for_timeout(15000)
            html = page.content()
            print(f"After wait - HTML length: {len(html)}")

        # Check for product content
        if "mac" in html.lower():
            print("Page contains 'mac' - looking for products")

            # Try JSON-LD
            jsonld = re.findall(
                r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
            )
            print(f"JSON-LD blocks: {len(jsonld)}")
            for block in jsonld:
                try:
                    data = json.loads(block)
                    items = data.get("itemListElement", [])
                    if items:
                        print(f"  Found {len(items)} items in JSON-LD!")
                        for item in items[:5]:
                            prod = item.get("item", item)
                            name = prod.get("name", "?")
                            price = prod.get("offers", {}).get("price", "?")
                            print(f"    {name} = {price} CHF")
                except:
                    pass

        print(f"\nCaptured {len(captured_data)} JSON responses with product data")
        for d in captured_data[:5]:
            print(f"  URL: {d['url']}")
            print(f"  Preview: {d['body'][:300]}")

        # Take screenshot-like dump
        text_content = page.evaluate("() => document.body?.innerText?.substring(0, 2000) || ''")
        print(f"\nPage text (first 1000 chars):\n{text_content[:1000]}")

        browser.close()


def test_digitec_direct_product():
    """Try accessing a known Digitec product page directly."""
    import requests
    from src.utils.stealth import create_session

    s = create_session()

    # Known Mac Mini product URLs on digitec
    known_urls = [
        "https://www.digitec.ch/de/s1/product/apple-mac-mini-m4-pro-24-gb-512-gb-mini-pc-47889585",
        "https://www.digitec.ch/de/s1/product/apple-mac-mini-m4-16-gb-256-gb-mini-pc-47889581",
    ]

    for url in known_urls:
        try:
            r = s.get(url, timeout=15)
            print(f"\n{url}")
            print(f"  HTTP {r.status_code}")
            if r.status_code == 200:
                jsonld = re.findall(
                    r'<script type="application/ld\+json">(.*?)</script>',
                    r.text, re.DOTALL,
                )
                for block in jsonld:
                    try:
                        data = json.loads(block)
                        if data.get("@type") == "Product":
                            name = data.get("name", "?")
                            offers = data.get("offers", {})
                            if isinstance(offers, list):
                                offers = offers[0]
                            price = offers.get("price", "?")
                            print(f"  Product: {name}")
                            print(f"  Price: {price} CHF")
                    except:
                        pass
        except Exception as e:
            print(f"\n{url}: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("TEST 1: Galaxus via Playwright")
    print("=" * 60)
    test_galaxus_playwright()

    print("\n" + "=" * 60)
    print("TEST 2: Digitec direct product pages")
    print("=" * 60)
    test_digitec_direct_product()
