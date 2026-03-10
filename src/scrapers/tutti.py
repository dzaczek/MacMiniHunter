"""Tutti.ch scraper - Swiss classifieds portal for second-hand Mac Mini M4."""

import json
import logging
import re

from src.scrapers.base import BaseScraper
from src.utils.stealth import build_headers_for_profile
from src.utils.validators import ScrapedPrice

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://www.tutti.ch/de/q/suche/Ak6ttYWMgbWluaSBtNMCUwMDAwA"
    "?sorting=newest&page={page}&query=mac+mini+m4"
)
BASE_URL = "https://www.tutti.ch"


class TuttiScraper(BaseScraper):
    STORE_NAME = "Tutti"
    BASE_URL = BASE_URL

    def __init__(self, proxy=None):
        super().__init__(proxy)
        # Override stealth session - Tutti returns brotli with stealth UA
        import requests
        self.session = requests.Session()
        self.session.headers.update(
            build_headers_for_profile(self.browser_profile, compressed=False)
        )

    def search_mac_mini(self) -> list[ScrapedPrice]:
        results: list[ScrapedPrice] = []
        seen_ids: set[str] = set()

        for page in (1, 2):
            url = SEARCH_URL.format(page=page)
            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code != 200:
                    logger.warning(f"[Tutti] Page {page}: HTTP {resp.status_code}")
                    break

                listings = self._extract_listings(resp.text)
                if not listings:
                    break

                for listing in listings:
                    lid = listing["id"]
                    if lid in seen_ids:
                        continue
                    seen_ids.add(lid)

                    title = listing["title"]
                    price = listing["price"]
                    listing_url = listing["url"]

                    # Filter: must mention Mac Mini (not just M4 accessories)
                    lower = title.lower()
                    if "mac mini" not in lower and "mac-mini" not in lower:
                        continue
                    if "m4" not in lower:
                        continue

                    # Skip accessories
                    accessory_kw = [
                        "ssd für", "ssd for", "ram für", "für mac",
                        "dock", "hub", "stand", "ständer", "untersatz",
                        "charger", "ladegerät", "kabel", "cable",
                        "adapter", "tastatur", "keyboard", "maus", "mouse",
                        "hülle", "case", "cover", "display", "monitor",
                    ]
                    if any(kw in lower for kw in accessory_kw):
                        continue

                    # Skip trade/exchange listings
                    if "echange" in lower or "tausch" in lower:
                        continue

                    # Prefix "Apple" if not present
                    display_title = title
                    if not display_title.lower().startswith("apple"):
                        display_title = f"Apple {display_title}"

                    try:
                        results.append(ScrapedPrice(
                            title=display_title,
                            price_chf=float(price),
                            url=listing_url,
                            external_id=lid,
                            availability=True,
                        ))
                    except (ValueError, TypeError):
                        continue

            except Exception as e:
                logger.error(f"[Tutti] Page {page} error: {e}")

        return results

    def _extract_listings(self, html: str) -> list[dict]:
        """Extract listings from Next.js __NEXT_DATA__ JSON."""
        match = re.search(
            r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
            html, re.DOTALL,
        )
        if not match:
            logger.warning("[Tutti] No __NEXT_DATA__ found")
            return []

        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.warning("[Tutti] Failed to parse __NEXT_DATA__")
            return []

        # Navigate: props > pageProps > dehydratedState > queries[0] > state > data > listings > edges
        try:
            edges = (
                data["props"]["pageProps"]["dehydratedState"]
                ["queries"][0]["state"]["data"]["listings"]["edges"]
            )
        except (KeyError, IndexError, TypeError):
            logger.warning("[Tutti] Could not find listings in __NEXT_DATA__")
            return []

        results = []
        for edge in edges:
            node = edge.get("node", {})
            listing_id = node.get("listingID")
            title = node.get("title", "")
            formatted_price = node.get("formattedPrice", "")

            if not listing_id or not title or not formatted_price:
                continue

            # Parse price: "450.-", "2'000.-", "1'299.–"
            price_str = formatted_price.replace("'", "").replace("\u2019", "")
            pm = re.search(r'(\d+(?:\.\d+)?)', price_str)
            if not pm:
                continue
            price = float(pm.group(1))

            # Build URL from SEO slug
            slug = node.get("seoInformation", {}).get("deSlug", "")
            if slug:
                url = f"{BASE_URL}/de/vi/{slug}/{listing_id}"
            else:
                url = f"{BASE_URL}/de/vi/{listing_id}"

            results.append({
                "id": str(listing_id),
                "title": title,
                "price": price,
                "url": url,
            })

        return results
