"""Fust.ch scraper - extracts Mac Mini prices from RSC (React Server Components) data."""

import logging
import re

from src.scrapers.base import BaseScraper
from src.utils.validators import ScrapedPrice

logger = logging.getLogger(__name__)


class FustScraper(BaseScraper):
    STORE_NAME = "Fust"
    BASE_URL = "https://www.fust.ch"
    CATEGORY_URL = "https://www.fust.ch/handy-pc-tablet/pc-computer-monitore/mac-mini-mac-studio/c/f_mac_mini_mac_studio"

    def search_mac_mini(self) -> list[ScrapedPrice]:
        """Extract Mac Mini products from Fust category page RSC data."""
        results: list[ScrapedPrice] = []

        try:
            self.session.headers["Accept-Encoding"] = "gzip, deflate"
            response = self.session.get(self.CATEGORY_URL, timeout=30)
            if response.status_code != 200:
                logger.warning(f"[{self.STORE_NAME}] HTTP {response.status_code}")
                return []

            html = response.text

            # Extract RSC chunks and combine
            rsc_chunks = re.findall(
                r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.DOTALL
            )
            combined = "".join(rsc_chunks)
            combined = combined.replace('\\"', '"').replace('\\n', '\n').replace('\\/', '/')

            # Find Mac Mini 2024 product names (M4 only)
            for m in re.finditer(
                r'"name"\s*:\s*"(Mac Mini 2024[^"]*M4[^"]*)"', combined, re.IGNORECASE
            ):
                name = m.group(1)

                # Look AFTER the name for price and URL
                after = combined[m.end():m.end() + 3000]

                # Extract price - the "value" closest after the name
                price_match = re.search(r'"value"\s*:\s*"?([\d.]+)"?', after[:500])
                if not price_match:
                    price_match = re.search(r'CHF\s*([\d.]+)', after[:500])
                if not price_match:
                    continue

                price = float(price_match.group(1))
                if price < 100:
                    continue

                # Extract product URL (must contain mac-mini and /p/)
                url_match = re.search(
                    r'"url"\s*:\s*"(/[^"]*mac-mini[^"]*/p/\d+)"', after
                )
                url = (
                    f"{self.BASE_URL}{url_match.group(1)}"
                    if url_match
                    else self.CATEGORY_URL
                )

                # Extract SKU from title (e.g. MCYT4SM/A)
                sku_match = re.search(r'([A-Z0-9]{5,}SM/A)', name)
                external_id = sku_match.group(1) if sku_match else None

                try:
                    results.append(
                        ScrapedPrice(
                            title=f"Apple {name}",
                            price_chf=price,
                            url=url,
                            external_id=external_id,
                            availability=True,
                        )
                    )
                except (ValueError, TypeError):
                    continue

        except Exception as e:
            logger.error(f"[{self.STORE_NAME}] Error: {e}")

        return results
