"""HTTP stealth utilities: User-Agent rotation, random delays, proxy support."""

import random
import re
import time
import logging
from typing import Optional

import requests
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)

# Fallback User-Agents in case fake_useragent service is down
FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

try:
    _ua = UserAgent(fallback=FALLBACK_USER_AGENTS[0])
except Exception:
    _ua = None


def get_random_user_agent() -> str:
    """Return a random, realistic browser User-Agent string."""
    if _ua:
        try:
            return _ua.random
        except Exception:
            pass
    return random.choice(FALLBACK_USER_AGENTS)


def random_delay(min_seconds: float = 2.5, max_seconds: float = 7.8) -> None:
    """Sleep for a random duration to mimic human browsing patterns."""
    delay = random.uniform(min_seconds, max_seconds)
    logger.debug(f"Sleeping for {delay:.2f}s")
    time.sleep(delay)


def create_session(proxy: Optional[str] = None) -> requests.Session:
    """Create a requests.Session with stealth headers and optional proxy.

    Args:
        proxy: Optional proxy URL, e.g. "http://user:pass@proxy:8080"
    """
    session = requests.Session()

    session.headers.update({
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    })

    if proxy:
        session.proxies = {"http": proxy, "https": proxy}

    return session


def extract_price_from_text(text: str) -> Optional[float]:
    """Extract a numeric CHF price from various text formats.

    Handles: "CHF 549.00", "Fr. 549.-", "1'299.00", "549,90", "549.–"
    """
    if not text or not text.strip():
        return None
    # Remove thousands separators and special chars
    cleaned = text.replace("'", "").replace("\u2019", "").replace("'", "")
    cleaned = cleaned.replace("–", "").replace("-", "")
    # Try to find a price pattern
    match = re.search(r"(\d+(?:[.,]\d{1,2})?)", cleaned)
    if match:
        price_str = match.group(1).replace(",", ".")
        if price_str.endswith("."):
            price_str += "00"
        try:
            return float(price_str)
        except ValueError:
            return None
    return None
