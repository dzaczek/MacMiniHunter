"""Tests for scraper base class and price extraction."""

import pytest
from src.scrapers.base import BaseScraper
from src.utils.stealth import extract_price_from_text
from src.utils.validators import ScrapedPrice


class TestPriceExtraction:
    """Test price extraction from various Swiss text formats."""

    def test_chf_format(self):
        assert extract_price_from_text("CHF 549.00") == 549.0

    def test_fr_format(self):
        assert extract_price_from_text("Fr. 549.-") == 549.0

    def test_thousands_separator(self):
        assert extract_price_from_text("CHF 1'299.00") == 1299.0

    def test_comma_decimal(self):
        assert extract_price_from_text("CHF 549,90") == 549.9

    def test_dash_format(self):
        assert extract_price_from_text("549.–") == 549.0

    def test_clean_number(self):
        assert extract_price_from_text("1299.00") == 1299.0

    def test_returns_none_for_empty(self):
        assert extract_price_from_text("") is None
        assert extract_price_from_text("no price here") is None

    def test_unicode_apostrophe(self):
        assert extract_price_from_text("CHF 1\u2019299.00") == 1299.0


class TestBaseScraper:
    """Test base scraper error handling."""

    def test_safe_scrape_catches_errors(self):
        class FailingScraper(BaseScraper):
            STORE_NAME = "TestStore"
            BASE_URL = "https://example.com"

            def search_mac_mini(self):
                raise ConnectionError("Network down")

        scraper = FailingScraper()
        result = scraper.run()
        assert result == []
