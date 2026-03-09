"""Pydantic models for validating scraped data before DB insertion."""

import re
from typing import Optional
from pydantic import BaseModel, field_validator


# Keywords that indicate an actual Mac Mini (not accessories)
MAC_MINI_KEYWORDS = ["mac mini", "macmini", "mac-mini"]
ACCESSORY_KEYWORDS = [
    "kabel", "cable", "adapter", "hülle", "case", "cover",
    "charger", "ladegerät", "tastatur", "keyboard", "maus", "mouse",
    "hub", "dock", "ständer", "stand", "schutzfolie", "ram-modul",
    "ssd für", "ram für", "speicher für", "ram 667", "ram 800",
    "festplatte", "hard drive", "lüfter", "fan ", "netzteil",
    "power supply", "display", "monitor", "tasche", "bag",
    "2gb ram", "4gb ram", "gehäuse", "enclosure",
]

# All valid Apple Silicon chips
VALID_CHIPS = {"M1", "M1 PRO", "M1 MAX", "M1 ULTRA",
               "M2", "M2 PRO", "M2 MAX", "M2 ULTRA",
               "M3", "M3 PRO", "M3 MAX", "M3 ULTRA",
               "M4", "M4 PRO", "M4 MAX", "M4 ULTRA"}

VALID_RAM = {8, 16, 24, 32, 48, 64, 128, 192}
VALID_SSD = {256, 512, 1000, 1024, 2000, 2048, 4000, 4096, 8000, 8192}
# Normalize SSD values to standard sizes
SSD_NORMALIZE = {1024: 1000, 2048: 2000, 4096: 4000, 8192: 8000}

# Apple Mac Mini M4 (2024) SKU → full specs mapping
# SKU prefix (without region suffix like SM/A) → (chip, cpu_cores, gpu_cores, ram, ssd)
# This is the most reliable way to identify exact configurations across stores
APPLE_SKU_SPECS: dict[str, tuple[str, int, int, int, int]] = {
    # M4 base models
    "MU9D3": ("M4", 10, 10, 16, 256),
    "MXK53": ("M4", 10, 10, 16, 256),
    "MXK73": ("M4", 10, 10, 16, 512),
    "MXK93": ("M4", 10, 10, 24, 512),
    # M4 Pro models
    "MXKR3": ("M4 PRO", 12, 16, 24, 512),
    "MXLT3": ("M4 PRO", 14, 20, 24, 512),
    "MXLN3": ("M4 PRO", 14, 20, 48, 512),
    # BTO / custom configs (added as discovered)
    "MXK23": ("M4", 10, 10, 16, 256),   # base with different color/region
    "MXKP3": ("M4 PRO", 12, 16, 24, 512),
}

# Reverse: generate regex pattern to match any known SKU in text
_SKU_PREFIXES = "|".join(APPLE_SKU_SPECS.keys())
SKU_PATTERN = re.compile(
    rf'({_SKU_PREFIXES})(?:[A-Z]{{0,3}}(?:/[A-Z])?)?',
    re.IGNORECASE,
)


class ScrapedPrice(BaseModel):
    """Validates a single scraped price entry."""

    title: str
    price_chf: float
    url: str
    external_id: Optional[str] = None
    availability: bool = True
    store_name: Optional[str] = None  # optional: source store for cross-reference

    @field_validator("price_chf")
    @classmethod
    def price_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"Price must be positive, got {v}")
        if v > 50000:
            raise ValueError(f"Price suspiciously high: {v} CHF")
        return round(v, 2)

    @field_validator("title")
    @classmethod
    def title_must_be_mac_mini(cls, v: str) -> str:
        lower = v.lower()
        # Must contain a Mac Mini keyword
        if not any(kw in lower for kw in MAC_MINI_KEYWORDS):
            raise ValueError(f"Title does not appear to be a Mac Mini: '{v}'")
        # Must NOT be an accessory
        if any(kw in lower for kw in ACCESSORY_KEYWORDS):
            raise ValueError(f"Title appears to be an accessory, not a Mac Mini: '{v}'")
        return v


class ParsedProduct(BaseModel):
    """Extracted product specifications from a title string."""

    chip: str  # M1, M2, M3, M4, M4 Pro, etc.
    ram: int   # in GB
    ssd: int   # in GB
    cpu_cores: Optional[int] = None  # e.g. 10, 12, 14
    gpu_cores: Optional[int] = None  # e.g. 10, 16, 20

    @field_validator("chip")
    @classmethod
    def chip_must_be_valid(cls, v: str) -> str:
        if v not in VALID_CHIPS:
            raise ValueError(f"Chip '{v}' not recognized. Valid: {VALID_CHIPS}")
        return v

    @field_validator("ram")
    @classmethod
    def ram_must_be_valid(cls, v: int) -> int:
        if v not in VALID_RAM:
            raise ValueError(f"Invalid RAM size: {v}GB. Expected one of {sorted(VALID_RAM)}")
        return v

    @field_validator("ssd")
    @classmethod
    def ssd_must_be_valid(cls, v: int) -> int:
        if v not in VALID_SSD:
            raise ValueError(f"Invalid SSD size: {v}GB. Expected one of {sorted(VALID_SSD)}")
        return SSD_NORMALIZE.get(v, v)


def parse_specs_from_sku(text: str) -> Optional[ParsedProduct]:
    """Try to identify exact specs from an Apple SKU/Model Number in text.

    This is the most reliable identification method — SKUs like MXK53SM/A
    map to an exact configuration (chip, CPU cores, GPU cores, RAM, SSD).
    """
    match = SKU_PATTERN.search(text.upper())
    if match:
        prefix = match.group(1).upper()
        specs = APPLE_SKU_SPECS.get(prefix)
        if specs:
            chip, cpu_cores, gpu_cores, ram, ssd = specs
            try:
                return ParsedProduct(
                    chip=chip, ram=ram, ssd=ssd,
                    cpu_cores=cpu_cores, gpu_cores=gpu_cores,
                )
            except ValueError:
                pass
    return None


def parse_specs_from_title(title: str, external_id: Optional[str] = None) -> Optional[ParsedProduct]:
    """Extract chip, RAM and SSD specs from a product title or SKU.

    Priority:
      1. Apple SKU match (most reliable) — checks title AND external_id
      2. Regex-based title parsing (fallback)

    Handles many formats:
      - "Mac Mini M4 16GB 256GB"
      - "Apple Mac Mini (M4 Pro, 24 GB, 512 GB SSD)"
      - "Mac mini M4 Pro 24GB RAM 1TB SSD"
      - "Mac mini 2024 M4 256 GB / 16 GB" (Brack: SSD / RAM)
      - "Mac Mini 2024 [M4 Chip, 16, 512 GB SSD, ...]" (Fust)
      - "MCYT4SM/A Apple Mac mini" (SKU-based)
    """
    # Priority 1: Try SKU-based matching (most reliable)
    for text_to_check in [external_id or "", title]:
        sku_result = parse_specs_from_sku(text_to_check)
        if sku_result:
            return sku_result

    text = title.upper()

    # Extract chip type - match M1/M2/M3/M4 with optional Pro/Max/Ultra
    chip_match = re.search(r"M[1234]\s*(?:PRO|MAX|ULTRA)?", text)
    if not chip_match:
        return None
    chip = chip_match.group().strip()

    # Find all GB/TB values after the chip match
    after_chip = text[chip_match.end():]

    # Also look before chip for specs (some formats put specs first)
    before_chip = text[:chip_match.start()]

    gb_values = re.findall(r"(\d{1,4})\s*(?:GB|GO)", after_chip)
    tb_values = re.findall(r"(\d{1,2})\s*TB", after_chip)

    # Convert TB to GB
    all_values = [int(v) for v in gb_values] + [int(v) * 1000 for v in tb_values]

    if len(all_values) < 2:
        # Try before chip too
        gb_before = re.findall(r"(\d{1,4})\s*(?:GB|GO)", before_chip)
        tb_before = re.findall(r"(\d{1,2})\s*TB", before_chip)
        all_values += [int(v) for v in gb_before] + [int(v) * 1000 for v in tb_before]

    if len(all_values) < 2:
        # Fust format: "M4 Chip, 16, 512 GB SSD"
        bare_nums = re.findall(r"(?:,\s*|\s)(\d{1,4})(?:\s*,|\s*\]|\s*GB)", after_chip)
        for bn in bare_nums:
            val = int(bn)
            if val in VALID_RAM or val in VALID_SSD:
                if val not in all_values:
                    all_values.append(val)

    if len(all_values) < 2:
        # Try the whole string as last resort
        all_gb = re.findall(r"(\d{1,4})\s*(?:GB|GO)", text)
        all_tb = re.findall(r"(\d{1,2})\s*TB", text)
        all_values = [int(v) for v in all_gb] + [int(v) * 1000 for v in all_tb]

    if len(all_values) < 2:
        return None

    # Determine which is RAM and which is SSD
    ram = None
    ssd = None

    for v in all_values:
        if v in VALID_SSD and ssd is None:
            ssd = v
        elif v in VALID_RAM and ram is None:
            ram = v

    if ram is None or ssd is None:
        # Fallback: smaller value is RAM, larger is SSD
        sorted_vals = sorted(set(all_values))
        if len(sorted_vals) >= 2:
            candidate_ram = sorted_vals[0]
            candidate_ssd = sorted_vals[-1]
            if ram is None and candidate_ram in VALID_RAM:
                ram = candidate_ram
            if ssd is None and candidate_ssd in VALID_SSD:
                ssd = candidate_ssd

    if ram is None or ssd is None:
        return None

    # Extract CPU/GPU cores from title (e.g. "10-Core CPU, 10-Core GPU" or "12c/16c")
    cpu_cores = None
    gpu_cores = None
    cpu_match = re.search(r"(\d{1,2})[-\s]*(?:CORE|KERN)\s*CPU", text)
    gpu_match = re.search(r"(\d{1,2})[-\s]*(?:CORE|KERN)\s*GPU", text)
    if cpu_match:
        cpu_cores = int(cpu_match.group(1))
    if gpu_match:
        gpu_cores = int(gpu_match.group(1))

    # If not found in text, try to infer from known chip defaults
    if cpu_cores is None and gpu_cores is None:
        # Known default core counts per chip variant
        defaults = {
            "M4": (10, 10),
            "M4 PRO": (12, 16),  # base M4 Pro; 14/20 variant needs explicit mention
        }
        if chip in defaults:
            cpu_cores, gpu_cores = defaults[chip]

    try:
        return ParsedProduct(chip=chip, ram=ram, ssd=ssd,
                             cpu_cores=cpu_cores, gpu_cores=gpu_cores)
    except ValueError:
        return None
