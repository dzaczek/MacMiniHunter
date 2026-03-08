"""Try Galaxus with HTTP/1.1 only (bypass HTTP/2 protocol error)."""
import json
import re
import sys
sys.path.insert(0, ".")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

captured = []

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-http2",  # Force HTTP/1.1
        ],
    )
    ctx = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        locale="en-CH",
        timezone_id="Europe/Zurich",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    page = ctx.new_page()
    Stealth().apply_stealth_sync(page)

    # Remove webdriver flag
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)

    def on_resp(resp):
        url = resp.url
        ct = resp.headers.get("content-type", "")
        if "json" in ct and len(url) < 300:
            try:
                body = resp.text()
                if len(body) > 200 and ("product" in body.lower() or "mac" in body.lower()):
                    captured.append({"url": url[:200], "body": body[:5000]})
            except:
                pass

    page.on("response", on_resp)

    try:
        print("Navigating to Galaxus...")
        page.goto(
            "https://www.galaxus.ch/en/search?q=mac+mini",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        print(f"Title: {page.title()}")
        print(f"URL: {page.url}")

        # Wait for content to load
        page.wait_for_timeout(5000)

        html = page.content()
        print(f"HTML size: {len(html)}")
        mac_count = len(re.findall(r'[Mm]ac\s*[Mm]ini', html))
        print(f"Mac Mini mentions: {mac_count}")

        # Check if we passed Datadome
        if "datadome" in html.lower() or "captcha" in html.lower():
            print("Datadome challenge detected")
            # Wait more
            page.wait_for_timeout(10000)
            html = page.content()
            print(f"After wait: HTML size={len(html)}")

        # Check for product data
        text = page.evaluate("() => document.body?.innerText?.substring(0, 3000) || ''")
        print(f"\nPage text:\n{text[:1000]}")

        print(f"\nCaptured API responses: {len(captured)}")
        for c in captured[:3]:
            print(f"  URL: {c['url']}")
            print(f"  Body preview: {c['body'][:300]}")

    except Exception as e:
        print(f"Error: {e}")

    browser.close()
