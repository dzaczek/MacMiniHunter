"""Base scraper interface that all store-specific scrapers must implement."""

import logging
from abc import ABC, abstractmethod
from typing import Optional

from src.utils.stealth import (
    create_session,
    get_random_browser_profile,
    get_random_ipv6,
    random_delay,
)
from src.utils.validators import ScrapedPrice

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base class for all store scrapers.

    Each subclass implements search_mac_mini() which returns validated ScrapedPrice objects.
    """

    STORE_NAME: str = ""
    BASE_URL: str = ""

    def __init__(self, proxy: Optional[str] = None):
        self.browser_profile = get_random_browser_profile()
        self.local_addr = get_random_ipv6()
        self.session = create_session(
            proxy=proxy,
            local_addr=self.local_addr,
            profile=self.browser_profile,
        )
        self.proxy = proxy

    @abstractmethod
    def search_mac_mini(self) -> list[ScrapedPrice]:
        """Search the store for Mac Mini listings.

        Returns:
            List of validated ScrapedPrice objects.
        """
        ...

    def _safe_scrape(self) -> list[ScrapedPrice]:
        """Wrapper with error handling - never crashes the entire pipeline."""
        try:
            random_delay()
            results = self.search_mac_mini()
            logger.info(f"[{self.STORE_NAME}] Found {len(results)} Mac Mini listings")
            return results
        except Exception as e:
            logger.error(f"[{self.STORE_NAME}] Scraping failed: {type(e).__name__}: {e}")
            return []

    def run(self) -> list[ScrapedPrice]:
        """Public entry point. Use this instead of search_mac_mini() directly."""
        return self._safe_scrape()
