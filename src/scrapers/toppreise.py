"""Toppreise.ch price comparison scraper.

Toppreise.ch aggregates prices from Swiss shops. This scraper:
  1. Discovers Mac Mini products from search results
  2. Fetches each product detail page
  3. Extracts best price from JSON-LD structured data (AggregateOffer)

Uses curl_cffi to handle any anti-bot protection.
"""

import json
import html as html_lib
import logging
import re
from typing import Optional
from urllib.parse import parse_qs, urljoin, urlparse

from src.utils.stealth import (
    build_headers_for_profile,
    get_random_browser_profile,
    random_delay,
)
from src.utils.validators import (
    ScrapedPrice,
    is_probable_m4_mac_mini,
    parse_specs_from_title,
)

logger = logging.getLogger(__name__)


class ToppreiseScraper:
    STORE_NAME = "Toppreise"
    BASE_URL = "https://www.toppreise.ch"

    SEARCH_URLS = [
        "https://www.toppreise.ch/produktsuche?q=mac+mini&cid=",
    ]

    def __init__(self, proxy=None):
        self.proxy = proxy
        self.browser_profile = get_random_browser_profile(browser="chrome")

    def run(self) -> list[ScrapedPrice]:
        """Public entry point."""
        try:
            random_delay()
            results = self._dedupe_offers(self.search_mac_mini())
            logger.info(f"[{self.STORE_NAME}] Found {len(results)} Mac Mini listings")
            return results
        except Exception as e:
            logger.error(f"[{self.STORE_NAME}] Scraping failed: {type(e).__name__}: {e}")
            return []

    def _create_session(self):
        from curl_cffi import requests as cffi_requests
        session = cffi_requests.Session(impersonate="chrome")
        session.headers.update(build_headers_for_profile(self.browser_profile))
        if self.proxy:
            session.proxies = {"http": self.proxy, "https": self.proxy}
        return session

    def search_mac_mini(self) -> list[ScrapedPrice]:
        """Discover Mac Mini products and extract prices."""
        self.session = self._create_session()

        # Step 1: Discover products from search
        product_links = self._discover_products()
        if not product_links:
            logger.warning(f"[{self.STORE_NAME}] No products discovered")
            return []

        logger.info(f"[{self.STORE_NAME}] Discovered {len(product_links)} products, fetching prices...")

        # Step 2: Fetch each detail page for pricing
        results: list[ScrapedPrice] = []
        for pid, url, title in product_links:
            random_delay(1.5, 3.5)
            entries = self._fetch_product_offers(pid, url, title)
            if entries:
                results.extend(entries)

        logger.info(f"[{self.STORE_NAME}] Got {len(results)} offers from {len(product_links)} products")
        return results

    def _discover_products(self) -> list[tuple[str, str, str]]:
        """Discover Mac Mini products from search pages."""
        seen_pids: set[str] = set()
        products = []

        for search_url in self.SEARCH_URLS:
            try:
                resp = self.session.get(search_url, timeout=20)
                if resp.status_code != 200:
                    logger.debug(f"[{self.STORE_NAME}] Search HTTP {resp.status_code}")
                    continue

                html = resp.text

                # Extract product links from both data-link and href attributes
                # Pattern: /preisvergleich/...-pXXXXXX
                all_links = re.findall(
                    r'(?:data-link|href)="(/preisvergleich/[^"?]*-p(\d+))',
                    html,
                )
                for href, pid in all_links:
                    if pid in seen_pids:
                        continue
                    href_lower = href.lower()
                    if "mac-mini" not in href_lower:
                        continue
                    seen_pids.add(pid)

                    # Extract title from URL slug
                    slug = href.split("/")[-1].rsplit("-p", 1)[0]
                    title = slug.replace("-", " ")
                    full_url = f"{self.BASE_URL}{href}"
                    products.append((pid, full_url, title))

                if products:
                    break

            except Exception as e:
                logger.debug(f"[{self.STORE_NAME}] Search error: {e}")
                continue

        return products

    def _fetch_product_offers(self, pid: str, url: str, fallback_title: str) -> list[ScrapedPrice]:
        """Fetch product detail page and extract per-shop offers."""
        try:
            resp = self.session.get(url, timeout=20)
            if resp.status_code != 200:
                logger.debug(f"[{self.STORE_NAME}] Detail HTTP {resp.status_code} for p{pid}")
                return []

            html = resp.text
            price = None
            title = fallback_title
            offer_count = 0
            mpn = ""

            # Primary: JSON-LD structured data
            ld_matches = re.findall(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                html, re.DOTALL,
            )
            for ld_str in ld_matches:
                try:
                    ld = json.loads(ld_str)
                    if not isinstance(ld, dict) or ld.get("@type") != "Product":
                        continue

                    title = ld.get("name", fallback_title)
                    # Clean up &nbsp; etc
                    title = title.replace("\xa0", " ").replace("&nbsp;", " ")
                    mpn = ld.get("mpn", "")

                    offers = ld.get("offers", {})
                    if isinstance(offers, dict):
                        low = offers.get("lowPrice")
                        if low is not None:
                            price = float(low)
                            offer_count = int(offers.get("offerCount", 0))
                    elif isinstance(offers, list) and offers:
                        prices = []
                        for o in offers:
                            p = o.get("price")
                            if p:
                                prices.append(float(p))
                        if prices:
                            price = min(prices)
                            offer_count = len(prices)
                    break
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue

            offer_entries = self._extract_offer_entries(pid=pid, product_url=url, title=title, html=html, mpn=mpn)
            if offer_entries:
                logger.info(
                    f"[{self.STORE_NAME}] {title}: extracted {len(offer_entries)} shop offers"
                )
                return offer_entries

            # Fallback: title tag with price
            if price is None:
                title_tag = re.search(r'<title>(.*?)</title>', html)
                if title_tag:
                    price_match = re.search(r'CHF\s*([\d\',.\-]+)', title_tag.group(1))
                    if price_match:
                        price = self._parse_chf_price(price_match.group(1))

            if price is None or price < 100:
                return []
            if not is_probable_m4_mac_mini(title, external_id=mpn or f"tp-{pid}"):
                return []

            offers_info = f" ({offer_count} offers)" if offer_count else ""
            logger.info(f"[{self.STORE_NAME}] {title}: CHF {price:.2f}{offers_info}")

            return [ScrapedPrice(
                title=title,
                price_chf=price,
                url=url,
                external_id=mpn or f"tp-{pid}",
                availability=offer_count > 0,
                store_name=self.STORE_NAME,
            )]

        except Exception as e:
            logger.debug(f"[{self.STORE_NAME}] Detail error for p{pid}: {e}")
            return []

    def _extract_offer_entries(
        self,
        pid: str,
        product_url: str,
        title: str,
        html: str,
        mpn: str,
    ) -> list[ScrapedPrice]:
        """Parse per-shop offer rows from the product detail page."""
        offer_section_start = html.find('Plugin_PriceComparisonOfferList')
        if offer_section_start == -1:
            return []

        section_html = html[offer_section_start:]
        chunks = section_html.split('<div id="Plugin_Offer_')[1:]
        results: list[ScrapedPrice] = []

        for chunk in chunks:
            block = '<div id="Plugin_Offer_' + chunk
            next_offer_options = block.find('<div class="offer_options')
            if next_offer_options != -1:
                block = block[:next_offer_options]

            dealer_id_match = re.search(r'data-dealer-id="(\d+)"', block)
            offer_link_match = re.search(r'data-link="([^"]+)"', block)
            shop_match = re.search(r'alt="([^"]+)" title="[^"]+"', block)

            shipping_price_match = re.search(
                r'priceContainer shippingPrice.*?<div class="Plugin_Price ">\s*([\d.]+)\s*</div>',
                block,
                re.DOTALL,
            )
            product_price_match = re.search(
                r'priceContainer productPrice.*?<div class="Plugin_Price ">\s*([\d.]+)\s*</div>',
                block,
                re.DOTALL,
            )

            price_raw = (
                shipping_price_match.group(1)
                if shipping_price_match
                else product_price_match.group(1)
                if product_price_match
                else None
            )
            price = self._parse_chf_price(price_raw) if price_raw else None
            if not dealer_id_match or not offer_link_match or not shop_match or price is None:
                continue

            offer_name_match = re.search(r'class="offer-name">\s*(.*?)\s*</a>', block, re.DOTALL)
            offer_title = html_lib.unescape(offer_name_match.group(1)).strip() if offer_name_match else title
            shop_name = html_lib.unescape(shop_match.group(1)).strip()
            offer_url = urljoin(self.BASE_URL, html_lib.unescape(offer_link_match.group(1)))
            query = parse_qs(urlparse(offer_url).query)
            offer_oid = query.get("oid", [""])[0]
            offer_did = query.get("did", [dealer_id_match.group(1)])[0]
            offer_external_id = (
                f"{mpn or f'tp-{pid}'}:dealer-{offer_did}:oid-{offer_oid}"
                if offer_oid
                else f"{mpn or f'tp-{pid}'}:dealer-{offer_did}"
            )

            try:
                if not is_probable_m4_mac_mini(offer_title, external_id=offer_external_id):
                    continue
                results.append(ScrapedPrice(
                    title=offer_title,
                    price_chf=price,
                    url=offer_url,
                    external_id=offer_external_id,
                    availability=True,
                    store_name=shop_name,
                ))
            except (ValueError, TypeError):
                continue

        return results

    def _dedupe_offers(self, offers: list[ScrapedPrice]) -> list[ScrapedPrice]:
        """Keep only the cheapest Toppreise offer per normalized config and store."""
        deduped: dict[tuple[str, str], ScrapedPrice] = {}

        for offer in offers:
            if not is_probable_m4_mac_mini(offer.title, external_id=offer.external_id):
                continue
            specs = parse_specs_from_title(offer.title, external_id=offer.external_id)
            if specs:
                config_key = (
                    f"{specs.chip}|{specs.ram}|{specs.ssd}|"
                    f"{specs.cpu_cores or 'na'}|{specs.gpu_cores or 'na'}"
                )
            else:
                config_key = offer.title.strip().lower()

            store_key = (offer.store_name or self.STORE_NAME).strip().lower()
            dedupe_key = (store_key, config_key)

            current = deduped.get(dedupe_key)
            if current is None or offer.price_chf < current.price_chf:
                deduped[dedupe_key] = offer

        return sorted(
            deduped.values(),
            key=lambda offer: ((offer.store_name or self.STORE_NAME).lower(), offer.price_chf),
        )

    @staticmethod
    def _parse_chf_price(price_str: str) -> Optional[float]:
        """Parse a Swiss price string into float."""
        if not price_str:
            return None
        cleaned = price_str.replace("'", "").replace("\u2019", "").replace("\u2018", "")
        cleaned = cleaned.replace("–", "").replace(".-", "")

        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")

        cleaned = cleaned.strip().rstrip(".")

        try:
            return float(cleaned)
        except ValueError:
            return None
