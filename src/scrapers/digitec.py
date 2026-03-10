"""Digitec.ch / Galaxus.ch scraper.

Strategy: Use requests to get the search page HTML, extract __NEXT_DATA__,
then try Playwright as fallback. Digitec serves product data through Relay
persisted queries loaded client-side, but the initial page response sometimes
contains product data in __NEXT_DATA__ or we intercept GraphQL via Playwright.
"""

import json
import logging
import re
from typing import Optional

from src.scrapers.base import BaseScraper
from src.utils.stealth import build_playwright_context_kwargs
from src.utils.validators import ScrapedPrice

logger = logging.getLogger(__name__)


class DigitecScraper(BaseScraper):
    STORE_NAME = "Digitec"
    BASE_URL = "https://www.digitec.ch"
    SEARCH_URL = "https://www.digitec.ch/de/search?q=mac+mini"

    def search_mac_mini(self) -> list[ScrapedPrice]:
        """Try requests first (works from this server), Playwright as fallback."""
        results = self._try_requests()
        if results:
            return results

        return self._try_playwright()

    def _try_requests(self) -> list[ScrapedPrice]:
        """Extract data via requests + __NEXT_DATA__ parsing."""
        results: list[ScrapedPrice] = []

        try:
            response = self.session.get(self.SEARCH_URL, timeout=15)
            if response.status_code != 200:
                logger.warning(f"[{self.STORE_NAME}] HTTP {response.status_code}")
                return []

            html = response.text

            # Try JSON-LD first
            jsonld_blocks = re.findall(
                r'<script type="application/ld\+json">(.*?)</script>',
                html,
                re.DOTALL,
            )
            for block in jsonld_blocks:
                try:
                    data = json.loads(block)
                    results.extend(self._parse_jsonld(data))
                except json.JSONDecodeError:
                    continue

            if results:
                return results

            # Try __NEXT_DATA__
            nd_match = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html
            )
            if nd_match:
                data = json.loads(nd_match.group(1))
                self._walk_for_products(data, results)

        except Exception as e:
            logger.error(f"[{self.STORE_NAME}] requests error: {e}")

        return results

    def _try_playwright(self) -> list[ScrapedPrice]:
        """Fallback: try Playwright with network interception."""
        results: list[ScrapedPrice] = []

        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth import Stealth
        except ImportError:
            logger.error(f"[{self.STORE_NAME}] Playwright not installed.")
            return []

        captured: list[dict] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            context = browser.new_context(
                **build_playwright_context_kwargs(self.browser_profile)
            )
            page = context.new_page()
            Stealth().apply_stealth_sync(page)

            def handle_response(response):
                if "/graphql" in response.url:
                    try:
                        body = response.json()
                        if isinstance(body, dict):
                            captured.append(body)
                        elif isinstance(body, list):
                            captured.extend(body)
                    except Exception:
                        pass

            page.on("response", handle_response)

            try:
                page.goto(self.SEARCH_URL, wait_until="networkidle", timeout=20000)
                page.wait_for_timeout(3000)

                for resp_data in captured:
                    self._walk_for_products(resp_data, results)
            except Exception as e:
                logger.error(f"[{self.STORE_NAME}] Playwright error: {e}")
            finally:
                browser.close()

        return results

    def _parse_jsonld(self, data) -> list[ScrapedPrice]:
        """Parse JSON-LD product data."""
        results = []
        if not isinstance(data, dict):
            return results

        items = []
        if data.get("@type") in ("CollectionPage", "ItemList"):
            items = data.get("itemListElement", [])
            if not items:
                items = data.get("mainEntity", {}).get("itemListElement", [])

        for item in items:
            prod = item.get("item", item)
            name = prod.get("name", "")
            offers = prod.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = offers.get("price")
            url = prod.get("url", "")
            if not name or not price:
                continue
            url = url if url.startswith("http") else f"{self.BASE_URL}/{url.lstrip('/')}"
            try:
                results.append(ScrapedPrice(
                    title=name,
                    price_chf=float(price),
                    url=url,
                    availability="InStock" in str(offers.get("availability", "")),
                ))
            except (ValueError, TypeError):
                pass
        return results

    def _walk_for_products(self, obj, results: list, depth: int = 0):
        """Recursively walk JSON to find product-like objects."""
        if depth > 15:
            return
        if isinstance(obj, dict):
            name = obj.get("name") or obj.get("productName") or obj.get("title", "")
            price = obj.get("price") or obj.get("amountIncl") or obj.get("salesPrice")
            if not price:
                offer = obj.get("offer") or obj.get("currentOffer") or {}
                if isinstance(offer, dict):
                    price_obj = offer.get("price", {})
                    if isinstance(price_obj, dict):
                        price = price_obj.get("amountIncl") or price_obj.get("amount")
                    elif isinstance(price_obj, (int, float)):
                        price = price_obj

            if name and price and isinstance(name, str) and "mac" in name.lower():
                url_path = obj.get("url") or obj.get("pdpUrl") or ""
                url = url_path if url_path.startswith("http") else f"{self.BASE_URL}{url_path}"
                product_id = str(obj.get("productId") or obj.get("id") or "")
                try:
                    results.append(ScrapedPrice(
                        title=str(name),
                        price_chf=float(price),
                        url=url,
                        external_id=product_id or None,
                        availability=True,
                    ))
                except (ValueError, TypeError):
                    pass

            for v in obj.values():
                self._walk_for_products(v, results, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                self._walk_for_products(item, results, depth + 1)


class GalaxusScraper(DigitecScraper):
    """Galaxus uses the same platform as Digitec."""
    STORE_NAME = "Galaxus"
    BASE_URL = "https://www.galaxus.ch"
    SEARCH_URL = "https://www.galaxus.ch/de/search?q=mac+mini"
