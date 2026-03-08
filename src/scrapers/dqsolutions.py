"""DQ Solutions scraper - Swiss Apple Reseller with GA4 ecommerce data."""

import json
import logging
import re

from src.scrapers.base import BaseScraper
from src.utils.validators import ScrapedPrice

logger = logging.getLogger(__name__)

CATALOG_URL = (
    "https://www.dq-solutions.ch/de/alle-produkte/-products/--page{page}"
    "?_filter=gH4sIAAAAAAAAA6tWSlOyqlbKySwu0U3LzClJLdJNK83J0S1JrSjRLU5NLErO"
    "ICyvlJuYrJCbmZeppINXZXwFyKyyxJzSVCWrPKCkjlJJZQGcXVCUX1AM4dQCAQAO3aH5mwAAAA"
)
BASE_URL = "https://www.dq-solutions.ch"


class DQSolutionsScraper(BaseScraper):
    STORE_NAME = "DQ Solutions"
    BASE_URL = BASE_URL

    def __init__(self, proxy=None):
        super().__init__(proxy)
        # DQ Solutions filter breaks with stealth UA; use simple headers
        import requests
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept-Encoding": "gzip, deflate",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def search_mac_mini(self) -> list[ScrapedPrice]:
        results: list[ScrapedPrice] = []
        seen_ids = set()
        self.session.headers["Accept-Encoding"] = "gzip, deflate"

        for page in (1, 2):
            url = CATALOG_URL.format(page=page)
            try:
                resp = self.session.get(url, timeout=20)
                if resp.status_code != 200:
                    logger.warning(f"[DQ] Page {page}: HTTP {resp.status_code}")
                    break

                items = self._extract_items(resp.text)
                links = self._extract_links(resp.text)

                for item in items:
                    item_id = item.get("item_id", "")
                    name = item.get("item_name", "")
                    price = item.get("price")

                    if not name or not price or item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)

                    # Only Mac Mini M4 with 256/512 SSD
                    if "mac mini" not in name.lower():
                        continue
                    if "256 GB" not in name and "512 GB" not in name:
                        continue

                    # Build product URL
                    product_url = links.get(item_id, url)

                    try:
                        results.append(ScrapedPrice(
                            title=f"Apple {name}",
                            price_chf=float(price),
                            url=product_url,
                            external_id=item_id,
                            availability=True,
                        ))
                    except (ValueError, TypeError):
                        continue

            except Exception as e:
                logger.error(f"[DQ] Page {page} error: {e}")

        # Deduplicate: keep cheapest per config (same name, different color)
        best = {}
        for r in results:
            key = r.title
            if key not in best or r.price_chf < best[key].price_chf:
                best[key] = r
        return list(best.values())

    def _extract_items(self, html: str) -> list[dict]:
        """Extract GA4 ecommerce items from page HTML."""
        match = re.search(r'"items"\s*:\s*\[(\{[^]]+)\]', html)
        if not match:
            return []
        try:
            return json.loads("[" + match.group(1) + "]")
        except json.JSONDecodeError:
            return []

    def _extract_links(self, html: str) -> dict[str, str]:
        """Extract product page URLs mapped by item ID."""
        links = re.findall(
            r'href="(https://www\.dq-solutions\.ch/de/apple/mac/mac-mini/[^"]+)"',
            html,
        )
        result = {}
        for link in links:
            cpm = re.search(r"(cpm\d+)", link)
            if cpm:
                result[cpm.group(1)] = link
        return result
