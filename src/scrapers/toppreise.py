"""Toppreise/Geizhals price comparison scraper.

Geizhals.ch (parent company of Toppreise.ch) aggregates prices from Swiss shops.
This scraper:
  1. Discovers all Mac Mini products from the category listing
  2. Fetches each product detail page to get per-shop offers in CHF
  3. Returns individual shop offers (not aggregated) for cross-reference with direct scrapers

This is the "smart" scraper — it traverses the comparison site to find all
available offers across multiple retailers from a single source.
"""

import json
import logging
import re
import time
from typing import Optional

from src.scrapers.base import BaseScraper
from src.utils.stealth import random_delay
from src.utils.validators import ScrapedPrice

logger = logging.getLogger(__name__)


class ToppreiseScraper(BaseScraper):
    STORE_NAME = "Toppreise"
    BASE_URL = "https://geizhals.ch"

    # Category: Desktop PCs / Nettops, filter: Apple Mac mini, Swiss shops only
    # Note: geizhals.ch may redirect to geizhals.eu — we try both
    CATEGORY_URLS = [
        "https://geizhals.de/?cat=sysdiv&xf=21862_Apple+Mac+mini&hloc=ch&v=l&sort=p",
        "https://geizhals.eu/?cat=sysdiv&xf=21862_Apple+Mac+mini&hloc=ch&v=l&sort=p",
        "https://geizhals.ch/?cat=sysdiv&xf=21862_Apple+Mac+mini&hloc=ch&v=e",
    ]

    def search_mac_mini(self) -> list[ScrapedPrice]:
        """Discover Mac Mini products and extract per-shop offers."""
        # Step 1: Discover products from category listing
        product_links = self._discover_products()
        if not product_links:
            logger.warning(f"[{self.STORE_NAME}] No products discovered")
            return []

        logger.info(f"[{self.STORE_NAME}] Discovered {len(product_links)} products, fetching offers...")

        # Step 2: For each product, fetch detail page and extract shop offers
        all_results: list[ScrapedPrice] = []
        for pid, url, title in product_links:
            random_delay(1.5, 3.5)  # be gentle with requests
            offers = self._fetch_product_offers(pid, url, title)
            all_results.extend(offers)

        # Deduplicate: keep cheapest per (title_normalized, shop_name)
        seen = {}
        for r in all_results:
            key = (r.title.lower().strip(), (r.store_name or "").lower())
            if key not in seen or r.price_chf < seen[key].price_chf:
                seen[key] = r

        results = list(seen.values())
        logger.info(f"[{self.STORE_NAME}] Total: {len(results)} unique offers from {len(product_links)} products")
        return results

    def _discover_products(self) -> list[tuple[str, str, str]]:
        """Discover Mac Mini product pages from the category listing.

        Returns list of (product_id, url, title).
        """
        products = []

        for cat_url in self.CATEGORY_URLS:
            try:
                resp = self.session.get(cat_url, timeout=30)
                if resp.status_code != 200:
                    logger.debug(f"[{self.STORE_NAME}] Category HTTP {resp.status_code}")
                    continue

                html = resp.text

                # Try __NEXT_DATA__ first (modern Geizhals uses Next.js)
                nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
                if nd:
                    try:
                        data = json.loads(nd.group(1))
                        products = self._extract_products_from_nextdata(data)
                        if products:
                            return products
                    except (json.JSONDecodeError, KeyError):
                        pass

                # Fallback: parse HTML directly
                # Pattern 1: gallery view with title attribute
                gallery = re.findall(
                    r'href="([^"]*a(\d+)\.html[^"]*)"[^>]*title="([^"]+)"',
                    html,
                )
                for href, pid, title in gallery:
                    if "mac" in title.lower() and "mini" in title.lower():
                        full_url = href if href.startswith("http") else f"{self.BASE_URL}/{href.lstrip('/')}"
                        products.append((pid, full_url, title))

                # Pattern 2: list view name links
                if not products:
                    listview = re.findall(
                        r'href="([^"]*a(\d+)\.html[^"]*)"[^>]*>\s*([^<]*[Mm]ac[^<]*[Mm]ini[^<]*)</a>',
                        html,
                    )
                    for href, pid, title in listview:
                        full_url = href if href.startswith("http") else f"{self.BASE_URL}/{href.lstrip('/')}"
                        products.append((pid, full_url, title.strip()))

                if products:
                    return products

            except Exception as e:
                logger.debug(f"[{self.STORE_NAME}] Category error: {e}")
                continue

        return products

    def _extract_products_from_nextdata(self, data: dict) -> list[tuple[str, str, str]]:
        """Walk __NEXT_DATA__ to find product listings."""
        products = []

        def walk(obj, depth=0):
            if depth > 12:
                return
            if isinstance(obj, dict):
                name = obj.get("name") or obj.get("productName") or ""
                pid = obj.get("id") or obj.get("productId") or ""
                url = obj.get("url") or obj.get("href") or ""

                if isinstance(name, str) and "mac" in name.lower() and "mini" in name.lower():
                    pid_str = str(pid) if pid else ""
                    if not url and pid_str:
                        url = f"{self.BASE_URL}/a{pid_str}.html?hloc=ch"
                    elif url and not url.startswith("http"):
                        url = f"{self.BASE_URL}/{url.lstrip('/')}"
                    if url:
                        products.append((pid_str, url, name))

                for v in obj.values():
                    walk(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item, depth + 1)

        walk(data)
        return products

    def _fetch_product_offers(self, pid: str, url: str, title: str) -> list[ScrapedPrice]:
        """Fetch individual shop offers from a product detail page.

        This extracts per-shop prices — the key advantage of a comparison site.
        """
        results = []

        # Ensure Swiss shops and CHF
        if "hloc=ch" not in url:
            url += ("&" if "?" in url else "?") + "hloc=ch"

        try:
            resp = self.session.get(url, timeout=20)
            if resp.status_code != 200:
                logger.debug(f"[{self.STORE_NAME}] Detail HTTP {resp.status_code} for {pid}")
                return []

            html = resp.text

            # Try __NEXT_DATA__ first
            nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
            if nd:
                try:
                    data = json.loads(nd.group(1))
                    results = self._extract_offers_from_nextdata(data, title, url)
                    if results:
                        return results
                except (json.JSONDecodeError, KeyError):
                    pass

            # Fallback: parse HTML for shop offers
            # Pattern: data-shop-name with nearby price
            shop_blocks = re.findall(
                r'data-shop-name="([^"]+)".*?'
                r'(?:CHF|Fr\.?)\s*([\d\',.]+)',
                html, re.DOTALL
            )
            for shop_name, price_str in shop_blocks:
                price = self._parse_chf_price(price_str)
                if price and 100 < price < 10000:
                    results.append(ScrapedPrice(
                        title=title,
                        price_chf=price,
                        url=url,
                        external_id=f"gh-{pid}-{shop_name[:20]}",
                        availability=True,
                        store_name=shop_name.strip(),
                    ))

            # Alternative: find CHF prices near shop mentions
            if not results:
                # Look for offer rows with shop name and price
                offer_pattern = re.findall(
                    r'class="[^"]*(?:offer|shop|dealer)[^"]*"[^>]*>([^<]{2,50})</.*?'
                    r'CHF\s*([\d\',.]+)',
                    html, re.DOTALL
                )
                for shop_raw, price_str in offer_pattern:
                    shop_name = re.sub(r'<[^>]+>', '', shop_raw).strip()
                    if not shop_name or len(shop_name) > 50:
                        continue
                    price = self._parse_chf_price(price_str)
                    if price and 100 < price < 10000:
                        results.append(ScrapedPrice(
                            title=title,
                            price_chf=price,
                            url=url,
                            external_id=f"gh-{pid}",
                            availability=True,
                            store_name=shop_name,
                        ))

            # Last resort: get the best (lowest) price from the page
            if not results:
                all_chf = re.findall(r'CHF\s*([\d\',.]+)', html)
                all_eur = re.findall(r'(?:€|&euro;)\s*([\d\',.]+)', html)

                prices = []
                for p in all_chf:
                    val = self._parse_chf_price(p)
                    if val and 100 < val < 10000:
                        prices.append(val)

                # EUR fallback (approximate)
                if not prices:
                    for p in all_eur:
                        val = self._parse_chf_price(p)
                        if val and 100 < val < 10000:
                            prices.append(round(val * 0.94, 2))

                if prices:
                    best_price = min(prices)
                    results.append(ScrapedPrice(
                        title=title,
                        price_chf=best_price,
                        url=url,
                        external_id=f"gh-{pid}",
                        availability=True,
                        store_name="Geizhals Best",
                    ))

        except Exception as e:
            logger.debug(f"[{self.STORE_NAME}] Detail page error for {pid}: {e}")

        return results

    def _extract_offers_from_nextdata(self, data: dict, title: str, url: str) -> list[ScrapedPrice]:
        """Extract shop offers from __NEXT_DATA__ JSON."""
        results = []

        def walk(obj, depth=0):
            if depth > 10:
                return
            if isinstance(obj, dict):
                # Look for shop offer patterns
                shop = (obj.get("shopName") or obj.get("dealerName") or
                        obj.get("merchantName") or "")
                if isinstance(obj.get("merchant"), dict):
                    shop = obj["merchant"].get("name", shop)

                price_val = obj.get("price") or obj.get("totalPrice") or obj.get("bestPrice")
                if isinstance(price_val, dict):
                    price_val = price_val.get("amount") or price_val.get("value")

                if shop and price_val:
                    try:
                        price = float(price_val)
                        if 100 < price < 10000:
                            results.append(ScrapedPrice(
                                title=title,
                                price_chf=price,
                                url=url,
                                external_id=f"gh-{shop[:20]}",
                                availability=True,
                                store_name=shop,
                            ))
                    except (ValueError, TypeError):
                        pass

                for v in obj.values():
                    walk(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item, depth + 1)

        walk(data)
        return results

    @staticmethod
    def _parse_chf_price(price_str: str) -> Optional[float]:
        """Parse a Swiss price string into float.

        Handles: "1'299.00", "599,90", "1.299,00", "599.00", "599.-"
        """
        if not price_str:
            return None
        cleaned = price_str.replace("'", "").replace("\u2019", "").replace("'", "")
        cleaned = cleaned.replace("–", "").replace(".-", "")

        # Handle European format: 1.299,00 → 1299.00
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")

        cleaned = cleaned.strip().rstrip(".")

        try:
            return float(cleaned)
        except ValueError:
            return None
