"""Tests for data validation and spec parsing."""

import pytest
from src.utils.validators import ScrapedPrice, parse_specs_from_title, ParsedProduct


class TestScrapedPrice:
    def test_valid_mac_mini(self):
        p = ScrapedPrice(
            title="Apple Mac Mini M4 16GB 256GB SSD",
            price_chf=549.0,
            url="https://digitec.ch/product/123",
        )
        assert p.price_chf == 549.0

    def test_rejects_accessory(self):
        with pytest.raises(ValueError, match="accessory"):
            ScrapedPrice(
                title="Mac Mini USB-C Kabel Cable",
                price_chf=29.90,
                url="https://digitec.ch/product/999",
            )

    def test_rejects_non_mac_mini(self):
        with pytest.raises(ValueError, match="does not appear"):
            ScrapedPrice(
                title="MacBook Pro M4 16GB",
                price_chf=1999.0,
                url="https://digitec.ch/product/456",
            )

    def test_rejects_negative_price(self):
        with pytest.raises(ValueError, match="positive"):
            ScrapedPrice(
                title="Mac Mini M4 16GB 256GB",
                price_chf=-10.0,
                url="https://example.com",
            )

    def test_rejects_suspicious_price(self):
        with pytest.raises(ValueError, match="suspiciously high"):
            ScrapedPrice(
                title="Mac Mini M4 16GB 256GB",
                price_chf=99999.0,
                url="https://example.com",
            )

    def test_rounds_price(self):
        p = ScrapedPrice(
            title="Mac Mini M4 16GB 256GB",
            price_chf=549.999,
            url="https://example.com",
        )
        assert p.price_chf == 550.0


class TestParseSpecs:
    def test_standard_format(self):
        result = parse_specs_from_title("Mac Mini M4 16GB 256GB")
        assert result is not None
        assert result.chip == "M4"
        assert result.ram == 16
        assert result.ssd == 256

    def test_with_spaces_and_units(self):
        result = parse_specs_from_title("Apple Mac Mini (M4 Pro, 24 GB, 512 GB SSD)")
        assert result is not None
        assert result.chip == "M4 PRO"
        assert result.ram == 24
        assert result.ssd == 512

    def test_slash_format(self):
        """Handles Ricardo-style "8GB/256GB" format."""
        result = parse_specs_from_title("Mac Mini M2 8GB/256GB")
        assert result is not None
        assert result.chip == "M2"
        assert result.ram == 8
        assert result.ssd == 256

    def test_tb_format(self):
        result = parse_specs_from_title("Mac mini M4 Pro 24GB RAM 1TB SSD")
        assert result is not None
        assert result.chip == "M4 PRO"
        assert result.ram == 24
        assert result.ssd == 1000

    def test_m2_basic(self):
        result = parse_specs_from_title("Apple Mac Mini M2 8 GB 256 GB")
        assert result is not None
        assert result.chip == "M2"
        assert result.ram == 8
        assert result.ssd == 256

    def test_no_chip_returns_none(self):
        result = parse_specs_from_title("Mac Mini 16GB 256GB")
        assert result is None

    def test_no_ssd_returns_none(self):
        result = parse_specs_from_title("Mac Mini M4 16GB")
        assert result is None

    def test_invalid_ram_returns_none(self):
        result = parse_specs_from_title("Mac Mini M4 12GB 256GB")
        assert result is None


class TestParsedProduct:
    def test_rejects_invalid_ram(self):
        with pytest.raises(ValueError, match="Invalid RAM"):
            ParsedProduct(chip="M4", ram=12, ssd=256)

    def test_rejects_invalid_ssd(self):
        with pytest.raises(ValueError, match="Invalid SSD"):
            ParsedProduct(chip="M4", ram=16, ssd=300)
