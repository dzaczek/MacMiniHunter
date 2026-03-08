"""Ricardo.ch scraper - uses Playwright to bypass anti-bot and extract listings."""

import json
import logging
import re
from typing import Optional

from src.scrapers.base import BaseScraper
from src.utils.validators import ScrapedPrice

logger = logging.getLogger(__name__)


class RicardoScraper(BaseScraper):
    STORE_NAME = "Ricardo"
    BASE_URL = "https://www.ricardo.ch"

    SEARCH_URLS = [
        "https://www.ricardo.ch/de/s/mac+mini?sort=newest",
    ]

    def search_mac_mini(self) -> list[ScrapedPrice]:
        """Use Playwright to render Ricardo search and extract listings."""
        results: list[ScrapedPrice] = []

        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth import Stealth
        except ImportError:
            logger.error("[Ricardo] Playwright not installed. Skipping.")
            return []

        captured_api: list[dict] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )

            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="de-CH",
                timezone_id="Europe/Zurich",
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
            )

            page = context.new_page()
            Stealth().apply_stealth_sync(page)

            # Capture API/GraphQL responses
            def handle_response(response):
                url = response.url
                if any(kw in url for kw in ["graphql", "api", "search"]):
                    try:
                        body = response.json()
                        captured_api.append({"url": url, "data": body})
                    except Exception:
                        pass

            page.on("response", handle_response)

            try:
                for search_url in self.SEARCH_URLS:
                    page.goto(search_url, wait_until="networkidle", timeout=60000)
                    page.wait_for_timeout(3000)

                    # Scroll down to load more items
                    for _ in range(3):
                        page.evaluate("window.scrollBy(0, 800)")
                        page.wait_for_timeout(1000)

                # Strategy 1: Extract from captured API responses
                for api_resp in captured_api:
                    self._extract_from_api(api_resp.get("data", {}), results)

                # Strategy 2: Parse rendered DOM
                if not results:
                    results.extend(self._extract_from_dom(page))

            except Exception as e:
                logger.error(f"[Ricardo] Page error: {e}")
            finally:
                browser.close()

        # Deduplicate
        seen = set()
        unique = []
        for r in results:
            key = r.external_id or r.url
            if key not in seen:
                seen.add(key)
                unique.append(r)

        return unique

    def _extract_from_api(self, data, results: list, depth: int = 0):
        """Walk API response JSON to find article listings."""
        if depth > 12:
            return

        if isinstance(data, dict):
            # Look for article-like structures
            title = data.get("title") or data.get("name", "")
            article_id = data.get("id") or data.get("articleId")

            # Price can be in different places
            price = None
            if data.get("buyNowPrice"):
                p = data["buyNowPrice"]
                price = p.get("value") or p.get("amount") if isinstance(p, dict) else p
            elif data.get("currentBidPrice"):
                p = data["currentBidPrice"]
                price = p.get("value") or p.get("amount") if isinstance(p, dict) else p
            elif data.get("price"):
                p = data["price"]
                price = p.get("value") or p.get("amount") if isinstance(p, dict) else p

            if title and price and isinstance(title, str) and article_id:
                url_path = data.get("url") or data.get("link") or f"/de/a/{article_id}"
                url = (
                    url_path
                    if url_path.startswith("http")
                    else f"{self.BASE_URL}{url_path}"
                )

                try:
                    validated = ScrapedPrice(
                        title=title,
                        price_chf=float(price),
                        url=url,
                        external_id=str(article_id),
                        availability=True,
                    )
                    results.append(validated)
                except (ValueError, TypeError) as e:
                    logger.debug(f"[Ricardo] Skip API item '{title}': {e}")

            for v in data.values():
                self._extract_from_api(v, results, depth + 1)

        elif isinstance(data, list):
            for item in data:
                self._extract_from_api(item, results, depth + 1)

    def _extract_from_dom(self, page) -> list[ScrapedPrice]:
        """Extract product listings from rendered Ricardo DOM."""
        results = []

        items = page.evaluate("""
            () => {
                const products = [];
                // Ricardo uses article cards in search results
                const selectors = [
                    'a[href*="/de/a/"]',
                    'article',
                    '[data-testid*="article"]',
                    '[class*="ArticleCard"]',
                    '[class*="articleCard"]',
                    '[class*="SearchResult"]',
                ];

                for (const sel of selectors) {
                    const els = document.querySelectorAll(sel);
                    if (els.length > 2) {
                        els.forEach(el => {
                            const text = el.innerText || '';
                            const link = el.tagName === 'A' ? el : el.querySelector('a[href]');
                            const href = link ? link.getAttribute('href') : '';
                            products.push({ text: text.substring(0, 500), href: href || '' });
                        });
                        break;
                    }
                }
                return products;
            }
        """)

        for item in items:
            text = item.get("text", "")
            href = item.get("href", "")

            if not text or "mac" not in text.lower():
                continue

            # Extract price (CHF format)
            price_match = re.search(r"(?:CHF|Fr\.?)\s*(\d+(?:[.']\d{1,3})*(?:\.\d{2})?)", text)
            if not price_match:
                # Try bare number patterns
                price_match = re.search(r"(\d{2,5}(?:\.\d{2}))", text)
            if not price_match:
                continue

            price_str = price_match.group(1).replace("'", "").replace("'", "")
            try:
                price = float(price_str)
            except ValueError:
                continue

            lines = [l.strip() for l in text.split("\n") if l.strip()]
            title = lines[0] if lines else text[:100]

            url = href if href.startswith("http") else f"{self.BASE_URL}{href}"

            ext_id_match = re.search(r"/a/(\d+)", url)
            external_id = ext_id_match.group(1) if ext_id_match else None

            try:
                validated = ScrapedPrice(
                    title=title,
                    price_chf=price,
                    url=url,
                    external_id=external_id,
                    availability=True,
                )
                results.append(validated)
            except ValueError as e:
                logger.debug(f"[Ricardo] DOM skip: {e}")

        return results
