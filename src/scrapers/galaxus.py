"""Galaxus scraper - dynamic product discovery with curl_cffi for Datadome bypass.

Instead of hardcoded product IDs, this scraper:
  1. Searches Galaxus for Mac Mini products
  2. Discovers all available variants dynamically
  3. Extracts prices from each product page
  4. Deduplicates by config (keeps cheapest per chip/ram/ssd)
"""

import json
import logging
import re
import time

from src.utils.validators import ScrapedPrice

logger = logging.getLogger(__name__)

# Search URLs to discover Mac Mini products
SEARCH_URLS = [
    "https://www.galaxus.ch/en/search?q=mac+mini+m4",
    "https://www.galaxus.ch/en/search?q=apple+mac+mini",
]

# Fallback: known product pages (updated dynamically from search results)
FALLBACK_PRODUCTS = [
    ("52491945", "https://www.galaxus.ch/en/s1/product/apple-mac-mini-2024-m4-16-gb-256-gb-pc-52491945",
     "Apple Mac Mini 2024 M4 16 GB 256 GB"),
    ("52491969", "https://www.galaxus.ch/en/s1/product/apple-mac-mini-2024-m4-24-gb-512-gb-apple-m4-10-core-pc-52491969",
     "Apple Mac Mini 2024 M4 24 GB 512 GB"),
    ("52491968", "https://www.galaxus.ch/en/s1/product/apple-mac-mini-2024-512-gb-24-gb-m4-pro-apple-m4-pro-16-core-pc-52491968",
     "Apple Mac Mini 2024 M4 Pro 24 GB 512 GB"),
]


class GalaxusScraper:
    """Galaxus scraper using curl_cffi for Datadome bypass."""

    STORE_NAME = "Galaxus"
    BASE_URL = "https://www.galaxus.ch"

    def __init__(self, proxy=None):
        self.proxy = proxy

    def run(self) -> list[ScrapedPrice]:
        """Public entry point."""
        try:
            results = self.search_mac_mini()
            logger.info(f"[{self.STORE_NAME}] Found {len(results)} Mac Mini listings")
            return results
        except Exception as e:
            logger.error(f"[{self.STORE_NAME}] Scraping failed: {type(e).__name__}: {e}")
            return []

    def search_mac_mini(self) -> list[ScrapedPrice]:
        from curl_cffi import requests as cffi_requests

        session = cffi_requests.Session(impersonate="chrome")
        results: list[ScrapedPrice] = []

        # Step 1: Discover product pages dynamically
        product_pages = self._discover_products(session)

        if not product_pages:
            logger.warning(f"[{self.STORE_NAME}] Discovery failed, using fallback products")
            product_pages = list(FALLBACK_PRODUCTS)

        logger.info(f"[{self.STORE_NAME}] Discovered {len(product_pages)} products to check")

        # Step 2: Fetch each product page and extract price
        seen_configs = {}  # config_key -> ScrapedPrice (keep cheapest)

        for product_id, url, fallback_title in product_pages:
            try:
                time.sleep(2)
                resp = session.get(url, timeout=20)

                if resp.status_code == 403:
                    logger.warning(f"[{self.STORE_NAME}] Blocked (403), stopping")
                    break
                if resp.status_code != 200:
                    continue

                price, title, available = self._extract_from_html(resp.text, fallback_title)

                if price is None or price < 100:
                    continue

                # Deduplicate: keep cheapest per config key
                config_key = self._make_config_key(title, fallback_title)
                if config_key in seen_configs and price >= seen_configs[config_key].price_chf:
                    continue

                entry = ScrapedPrice(
                    title=title,
                    price_chf=price,
                    url=url,
                    external_id=product_id,
                    availability=available,
                )
                seen_configs[config_key] = entry
                logger.info(f"[{self.STORE_NAME}] {title}: CHF {price:.2f}")

            except Exception as e:
                logger.debug(f"[{self.STORE_NAME}] Error on {product_id}: {e}")
                continue

        return list(seen_configs.values())

    def _discover_products(self, session) -> list[tuple[str, str, str]]:
        """Discover Mac Mini products from search pages."""
        products = []
        seen_ids = set()

        for search_url in SEARCH_URLS:
            try:
                time.sleep(2)
                resp = session.get(search_url, timeout=20)
                if resp.status_code != 200:
                    continue

                html = resp.text

                # Method 1: Extract product links from search results
                # Galaxus product URLs: /en/s1/product/name-PRODUCTID
                product_links = re.findall(
                    r'href="(/en/s1/product/[^"]*-(\d{7,9}))"',
                    html,
                )

                for path, pid in product_links:
                    if pid in seen_ids:
                        continue
                    if "mac" not in path.lower() or "mini" not in path.lower():
                        continue
                    seen_ids.add(pid)
                    full_url = f"{self.BASE_URL}{path}"
                    # Extract a title from the URL slug
                    slug = path.split("/product/")[1].rsplit("-", 1)[0] if "/product/" in path else ""
                    title = slug.replace("-", " ").title() if slug else f"Mac Mini {pid}"
                    products.append((pid, full_url, title))

                # Method 2: __NEXT_DATA__
                nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
                if nd:
                    try:
                        data = json.loads(nd.group(1))
                        self._walk_search_results(data, products, seen_ids)
                    except (json.JSONDecodeError, KeyError):
                        pass

                # Method 3: JSON-LD product listings
                for ld_match in re.finditer(
                    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL
                ):
                    try:
                        ld = json.loads(ld_match.group(1))
                        if isinstance(ld, dict):
                            items = ld.get("itemListElement", [])
                            for item in items:
                                prod = item.get("item", item)
                                url = prod.get("url", "")
                                name = prod.get("name", "")
                                if "mac" in name.lower() and "mini" in name.lower():
                                    pid_match = re.search(r'-(\d{7,9})$', url)
                                    if pid_match and pid_match.group(1) not in seen_ids:
                                        pid = pid_match.group(1)
                                        seen_ids.add(pid)
                                        products.append((pid, url, name))
                    except (json.JSONDecodeError, ValueError):
                        continue

            except Exception as e:
                logger.debug(f"[{self.STORE_NAME}] Search error: {e}")
                continue

        return products

    def _walk_search_results(self, data: dict, products: list, seen_ids: set):
        """Walk __NEXT_DATA__ to find product listings from search."""
        def walk(obj, depth=0):
            if depth > 15:
                return
            if isinstance(obj, dict):
                # Look for product-like objects
                name = obj.get("name") or obj.get("productName") or ""
                pid = str(obj.get("productId") or obj.get("id") or "")
                url = obj.get("url") or obj.get("canonicalUrl") or ""

                if (isinstance(name, str) and "mac" in name.lower() and "mini" in name.lower()
                        and pid and pid not in seen_ids):
                    if url and not url.startswith("http"):
                        url = f"{self.BASE_URL}{url}"
                    elif not url:
                        url = f"{self.BASE_URL}/en/s1/product/{pid}"
                    seen_ids.add(pid)
                    products.append((pid, url, name))

                for v in obj.values():
                    walk(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item, depth + 1)

        walk(data)

    @staticmethod
    def _make_config_key(title: str, fallback: str) -> str:
        """Create a dedup key from product specs."""
        text = (title or fallback).upper()
        # Extract chip + ram + ssd for grouping
        chip = re.search(r"M[1234]\s*(?:PRO|MAX|ULTRA)?", text)
        gb_vals = sorted(int(v) for v in re.findall(r"(\d+)\s*GB", text))
        chip_str = chip.group().strip() if chip else "UNKNOWN"
        return f"{chip_str}-{'_'.join(str(v) for v in gb_vals)}"

    def _extract_from_html(self, html: str, fallback_title: str):
        """Extract price, title, availability from a Galaxus product page."""
        price = None
        title = fallback_title
        available = True

        # Try JSON-LD structured data (most reliable)
        for ld_match in re.finditer(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL
        ):
            try:
                ld = json.loads(ld_match.group(1))
                if isinstance(ld, dict) and ld.get("@type") == "Product":
                    offers = ld.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    p = offers.get("price")
                    if p:
                        price = float(p)
                        ld_name = ld.get("name", "")
                        title = ld_name if ("gb" in ld_name.lower() or "m4" in ld_name.lower()) else fallback_title
                        avail_str = offers.get("availability", "")
                        available = "InStock" in avail_str
                        return price, title, available
            except (json.JSONDecodeError, ValueError):
                continue

        # Fallback: meta tags
        og_price = re.search(
            r'<meta[^>]*property="product:price:amount"[^>]*content="([\d.]+)"', html
        )
        if og_price:
            price = float(og_price.group(1))

        og_title = re.search(
            r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', html
        )
        if og_title:
            title = og_title.group(1)

        # Fallback: __NEXT_DATA__
        if price is None:
            nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
            if nd:
                try:
                    data = json.loads(nd.group(1))
                    price, title, available = self._walk_next_data(data, fallback_title)
                except (json.JSONDecodeError, KeyError):
                    pass

        return price, title, available

    def _walk_next_data(self, data: dict, fallback_title: str):
        """Walk __NEXT_DATA__ to find product price/title."""
        price = None
        title = fallback_title
        available = True

        def walk(obj, depth=0):
            nonlocal price, title, available
            if depth > 15 or price is not None:
                return
            if isinstance(obj, dict):
                amt = obj.get("amountIncl") or obj.get("amountInclusive")
                if amt and isinstance(amt, (int, float)) and 100 < amt < 10000:
                    price = float(amt)

                if not price:
                    p_obj = obj.get("price", {})
                    if isinstance(p_obj, dict):
                        amt = p_obj.get("amountIncl") or p_obj.get("amountInclusive")
                        if amt and isinstance(amt, (int, float)) and 100 < amt < 10000:
                            price = float(amt)

                n = obj.get("name") or obj.get("productName")
                if n and isinstance(n, str) and "mac" in n.lower() and len(n) > 10:
                    title = n

                for v in obj.values():
                    walk(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item, depth + 1)

        walk(data)
        return price, title, available
