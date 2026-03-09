"""HTTP stealth utilities: User-Agent rotation, random delays, proxy support."""

import random
import re
import socket
import subprocess
import time
import logging
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
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

_DISCOVERED_IPV6_POOL: Optional[list[str]] = None

try:
    _ua = UserAgent(fallback=FALLBACK_USER_AGENTS[0])
except Exception:
    _ua = None


class SourceAddressAdapter(HTTPAdapter):
    """Custom HTTPAdapter that binds to a specific local source address.
    
    Only binds if the target address family matches the source address family.
    """
    def __init__(self, source_address: str, **kwargs):
        self.source_address = source_address
        self.source_family = socket.AF_INET6 if ":" in source_address else socket.AF_INET
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            source_address=(self.source_address, 0),
            **pool_kwargs
        )

    def send(self, request, *args, **kwargs):
        """Override send to fall back to default adapter if target doesn't support our address family."""
        from urllib.parse import urlparse
        host = urlparse(request.url).hostname
        try:
            info = socket.getaddrinfo(host, None)
            target_families = {item[0] for item in info}
            if self.source_family not in target_families:
                logger.debug(f"Target {host} doesn't support {'IPv6' if self.source_family == socket.AF_INET6 else 'IPv4'}, using default adapter")
                fallback = HTTPAdapter()
                return fallback.send(request, *args, **kwargs)
        except Exception:
            pass
        return super().send(request, *args, **kwargs)


def get_random_user_agent() -> str:
    """Return a random, realistic browser User-Agent string."""
    if _ua:
        try:
            return _ua.random
        except Exception:
            pass
    return random.choice(FALLBACK_USER_AGENTS)


def _discover_local_ipv6_addresses() -> list[str]:
    """Return globally routable IPv6 addresses currently assigned to the host."""
    candidates: list[str] = []

    commands = [
        ["ifconfig"],
        ["ip", "-6", "addr", "show", "scope", "global"],
    ]

    for cmd in commands:
        try:
            output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        except Exception:
            continue

        for addr in re.findall(r"inet6 ([0-9a-f:]+)", output, re.IGNORECASE):
            normalized = addr.lower()
            if normalized.startswith(("fe80:", "::1")):
                continue
            if normalized not in candidates:
                candidates.append(normalized)

        if candidates:
            break

    return candidates


def get_random_ipv6() -> Optional[str]:
    """Get a random IPv6 address assigned to this host, if available."""
    global _DISCOVERED_IPV6_POOL

    if _DISCOVERED_IPV6_POOL is None:
        _DISCOVERED_IPV6_POOL = _discover_local_ipv6_addresses()
        if _DISCOVERED_IPV6_POOL:
            logger.debug("Discovered %s usable IPv6 addresses", len(_DISCOVERED_IPV6_POOL))
        else:
            logger.debug("No usable IPv6 addresses discovered for source binding")

    if not _DISCOVERED_IPV6_POOL:
        return None

    return random.choice(_DISCOVERED_IPV6_POOL)


def random_delay(min_seconds: float = 2.5, max_seconds: float = 7.8) -> None:
    """Sleep for a random duration to mimic human browsing patterns."""
    delay = random.uniform(min_seconds, max_seconds)
    logger.debug(f"Sleeping for {delay:.2f}s")
    time.sleep(delay)


def create_session(proxy: Optional[str] = None, local_addr: Optional[str] = None) -> requests.Session:
    """Create a requests.Session with stealth headers and optional proxy/local IP.

    Args:
        proxy: Optional proxy URL, e.g. "http://user:pass@proxy:8080"
        local_addr: Optional local IP address to bind to (e.g. for IPv6 rotation)
    """
    session = requests.Session()

    if local_addr:
        adapter = SourceAddressAdapter(local_addr)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        logger.debug(f"Session bound to local address: {local_addr}")

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
