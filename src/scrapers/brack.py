"""Brack.ch scraper - extracts product data from JSON-LD structured data."""

import json
import logging
import re

from src.scrapers.base import BaseScraper
from src.utils.validators import ScrapedPrice

logger = logging.getLogger(__name__)

BRACK_SEARCH_URL = "https://www.brack.ch/search"


class BrackScraper(BaseScraper):
    STORE_NAME = "Brack"
    BASE_URL = "https://www.brack.ch"

    def search_mac_mini(self) -> list[ScrapedPrice]:
        results: list[ScrapedPrice] = []

        params = {"query": "Mac Mini M4"}
        # Brack can be slow - retry once on timeout
        response = None
        for attempt in range(2):
            try:
                response = self.session.get(BRACK_SEARCH_URL, params=params, timeout=60)
                response.raise_for_status()
                break
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"[Brack] Attempt 1 failed: {e}, retrying...")
                    continue
                raise

        if response is None:
            return []

        # Extract JSON-LD structured data - Brack embeds full product listings here
        jsonld_blocks = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>',
            response.text,
            re.DOTALL,
        )

        for block in jsonld_blocks:
            try:
                data = json.loads(block)
            except json.JSONDecodeError:
                continue

            if data.get("@type") != "CollectionPage":
                continue

            items = data.get("mainEntity", {}).get("itemListElement", [])
            logger.info(f"[Brack] Found {len(items)} items in JSON-LD")

            for item in items:
                prod = item.get("item", {})
                if not prod:
                    continue

                name = prod.get("name", "")
                url_path = prod.get("url", "")
                url = (
                    url_path
                    if url_path.startswith("http")
                    else f"{self.BASE_URL}/{url_path.lstrip('/')}"
                )

                # Extract offers/price
                offers = prod.get("offers", {})
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}

                price_val = offers.get("price")
                if price_val is None:
                    continue

                try:
                    price = float(price_val)
                except (ValueError, TypeError):
                    continue

                # Check availability
                availability = offers.get("availability", "")
                is_available = "InStock" in availability

                # Extract Apple SKU from product name (e.g. "MXK53SM/A") or URL
                sku_match = re.search(r'(MX[A-Z0-9]{2,4}(?:SM)?(?:/[A-Z])?)', name)
                if not sku_match:
                    sku_match = re.search(r'(MX[A-Z0-9]{2,4}(?:SM)?(?:/[A-Z])?)', url_path)
                # Fallback: extract numeric ID from URL slug
                ext_id_match = re.search(r"-(\d{5,})$", url_path)
                external_id = (sku_match.group(1) if sku_match
                               else ext_id_match.group(1) if ext_id_match
                               else None)

                try:
                    validated = ScrapedPrice(
                        title=name,
                        price_chf=price,
                        url=url,
                        external_id=external_id,
                        availability=is_available,
                    )
                    results.append(validated)
                except ValueError as e:
                    logger.debug(f"[Brack] Skipping '{name}': {e}")

        return results
