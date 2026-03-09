"""Apple Store CH scraper - extracts official Mac Mini prices.

Strategy: Apple embeds JSON price objects in the page with keys like
"m4-10-10" containing seoPrice values. We also scan for product cards
with full specs (chip, RAM, SSD) to create proper product entries.
"""

import json
import logging
import re

from src.scrapers.base import BaseScraper
from src.utils.validators import ScrapedPrice

logger = logging.getLogger(__name__)


class AppleScraper(BaseScraper):
    STORE_NAME = "Apple Store"
    BASE_URL = "https://www.apple.com"
    SHOP_URL = "https://www.apple.com/ch-de/shop/buy-mac/mac-mini"

    # Map Apple's internal price keys to human-readable labels.
    PRICE_KEY_MAP = {
        "m4-10-10": ("M4", "10-Core CPU, 10-Core GPU"),
        "m4pro-12-16": ("M4 Pro", "12-Core CPU, 16-Core GPU"),
        "m4pro-14-20": ("M4 Pro", "14-Core CPU, 20-Core GPU"),
    }

    # Apple reuses the same "m4-10-10" key for several M4 storage / RAM options.
    # We map each repeated key occurrence to a concrete variant in ascending price order.
    SEO_KEY_CONFIGS = {
        "m4-10-10": [
            ("M4", 16, 256, 10, 10),
            ("M4", 16, 512, 10, 10),
            ("M4", 24, 512, 10, 10),
        ],
        "m4pro-12-16": [
            ("M4 Pro", 24, 512, 12, 16),
        ],
        "m4pro-14-20": [
            ("M4 Pro", 48, 512, 14, 20),
        ],
    }

    def search_mac_mini(self) -> list[ScrapedPrice]:
        """Extract Mac Mini prices from Apple Store CH."""
        results: list[ScrapedPrice] = []

        try:
            response = self.session.get(self.SHOP_URL, timeout=30)
            if response.status_code != 200:
                logger.warning(f"[{self.STORE_NAME}] HTTP {response.status_code}")
                return []

            html = response.text

            # Strategy 1: Find product cards with full specs
            results = self._extract_product_cards(html)

            # Strategy 2: Extract seoPrice values from embedded JSON
            if not results:
                results = self._extract_seo_prices(html)

            # Strategy 3: JSON-LD fallback
            if not results:
                results = self._extract_jsonld(html)

        except Exception as e:
            logger.error(f"[{self.STORE_NAME}] Error: {e}")

        return results

    def _extract_product_cards(self, html: str) -> list[ScrapedPrice]:
        """Extract product cards that contain chip, RAM, SSD, and price."""
        results = []

        # Apple embeds product data in JSON - look for product configurations
        # Pattern: objects with memory, storage, and price info
        # Try to find the full product JSON
        config_json = re.findall(
            r'"(?:product|model|configuration)[^"]*":\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})',
            html,
        )

        # Also look for structured product data blocks
        # Apple format: "16 GB RAM" or "16GB", "256 GB SSD" or "256GB"
        product_blocks = re.findall(
            r'Mac\s*mini[^<]*?M4[^<]*?(\d{1,3})\s*GB[^<]*?(\d{3,4})\s*(?:GB|TB)',
            html, re.IGNORECASE,
        )

        for ram_str, ssd_str in product_blocks:
            ram = int(ram_str)
            ssd = int(ssd_str)
            if ssd <= 8:  # TB value
                ssd *= 1000

            # Find a nearby price
            chip = "M4 Pro" if ram >= 24 else "M4"
            logger.debug(f"[{self.STORE_NAME}] Found card: {chip} {ram}GB {ssd}GB")

        # Primary extraction: seoPrice with deterministic config matching
        seo_prices = re.findall(r'"seoPrice"\s*:\s*([\d.]+)', html)
        config_keys = re.findall(r'"(m4[^"]*)":\{[^}]*comparativeDisplayPrice', html)

        if seo_prices and config_keys:
            prices_by_key: dict[str, list[float]] = {}
            for key, price_str in zip(config_keys, seo_prices):
                try:
                    prices_by_key.setdefault(key, []).append(float(price_str))
                except (ValueError, TypeError):
                    continue

            for key, prices in prices_by_key.items():
                chip_label, desc = self.PRICE_KEY_MAP.get(key, ("M4", key))
                variants = self.SEO_KEY_CONFIGS.get(key, [])

                if variants:
                    for (chip, ram, ssd, cpu_cores, gpu_cores), price in zip(variants, sorted(prices)):
                        title = (
                            f"Apple Mac mini {chip} {ram}GB {ssd}GB "
                            f"({cpu_cores}-Core CPU, {gpu_cores}-Core GPU)"
                        )
                        try:
                            results.append(ScrapedPrice(
                                title=title,
                                price_chf=price,
                                url=self.SHOP_URL,
                                external_id=f"apple-seo:{key}:{ram}:{ssd}:{cpu_cores}:{gpu_cores}",
                                availability=True,
                            ))
                        except (ValueError, TypeError):
                            continue

                    if len(prices) != len(variants):
                        logger.warning(
                            "[%s] Expected %s price entries for %s, got %s",
                            self.STORE_NAME,
                            len(variants),
                            key,
                            len(prices),
                        )
                    continue

                for price in prices:
                    title = f"Apple Mac mini {chip_label} ({desc})"
                    try:
                        results.append(ScrapedPrice(
                            title=title,
                            price_chf=price,
                            url=self.SHOP_URL,
                            external_id=f"apple-seo:{key}:{price}",
                            availability=True,
                        ))
                    except (ValueError, TypeError):
                        continue

        return results

    def _extract_seo_prices(self, html: str) -> list[ScrapedPrice]:
        """Fallback: extract seoPrice values."""
        results = []
        seo_prices = re.findall(r'"seoPrice"\s*:\s*([\d.]+)', html)
        config_keys = re.findall(r'"(m4[^"]*)":\{[^}]*comparativeDisplayPrice', html)

        if seo_prices and config_keys:
            for key, price_str in zip(config_keys, seo_prices):
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    continue

                chip_label, desc = self.PRICE_KEY_MAP.get(key, ("M4", key))
                title = f"Apple Mac mini {chip_label}, {desc}"
                try:
                    results.append(ScrapedPrice(
                        title=title,
                        price_chf=price,
                        url=self.SHOP_URL,
                        availability=True,
                    ))
                except (ValueError, TypeError):
                    continue

        return results

    def _extract_jsonld(self, html: str) -> list[ScrapedPrice]:
        """Last resort: JSON-LD aggregate pricing."""
        results = []
        jsonld = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>',
            html, re.DOTALL,
        )
        for block in jsonld:
            try:
                data = json.loads(block)
                if data.get("@type") == "Product":
                    offers = data.get("offers", [])
                    if isinstance(offers, list):
                        for o in offers:
                            if o.get("@type") == "AggregateOffer":
                                low = o.get("lowPrice")
                                if low:
                                    results.append(ScrapedPrice(
                                        title="Apple Mac mini (lowest price)",
                                        price_chf=float(low),
                                        url=self.SHOP_URL,
                                        availability=True,
                                    ))
            except (json.JSONDecodeError, ValueError):
                pass
        return results
