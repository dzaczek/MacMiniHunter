"""HTTP stealth utilities: browser profile rotation, delays, proxy support."""

from dataclasses import dataclass
import random
import re
import socket
import subprocess
import time
import logging
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class BrowserProfile:
    """A coherent browser/device profile used across requests, curl_cffi, and Playwright."""

    id: str
    browser: str
    user_agent: str
    accept_language: str
    locale: str
    timezone_id: str
    viewport_width: int
    viewport_height: int
    screen_width: int
    screen_height: int
    platform: str
    sec_ch_ua_platform: Optional[str]
    sec_ch_ua: Optional[str]
    sec_ch_ua_mobile: Optional[str]
    hardware_concurrency: int
    device_memory: int
    color_scheme: str = "light"
    mobile: bool = False


SWISS_BROWSER_PROFILES = [
    BrowserProfile(
        id="mac-chrome-arm",
        browser="chrome",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        accept_language="de-CH,de;q=0.9,en;q=0.8",
        locale="de-CH",
        timezone_id="Europe/Zurich",
        viewport_width=1728,
        viewport_height=1117,
        screen_width=1728,
        screen_height=1117,
        platform="MacIntel",
        sec_ch_ua_platform="macOS",
        sec_ch_ua='"Chromium";v="134", "Google Chrome";v="134", "Not:A-Brand";v="24"',
        sec_ch_ua_mobile="?0",
        hardware_concurrency=8,
        device_memory=8,
    ),
    BrowserProfile(
        id="windows-chrome-x64",
        browser="chrome",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        accept_language="de-CH,de;q=0.9,en;q=0.8",
        locale="de-CH",
        timezone_id="Europe/Zurich",
        viewport_width=1920,
        viewport_height=1080,
        screen_width=1920,
        screen_height=1080,
        platform="Win32",
        sec_ch_ua_platform="Windows",
        sec_ch_ua='"Chromium";v="134", "Google Chrome";v="134", "Not:A-Brand";v="24"',
        sec_ch_ua_mobile="?0",
        hardware_concurrency=12,
        device_memory=8,
    ),
    BrowserProfile(
        id="linux-chrome-x64",
        browser="chrome",
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        accept_language="de-CH,de;q=0.9,en;q=0.8",
        locale="de-CH",
        timezone_id="Europe/Zurich",
        viewport_width=1536,
        viewport_height=960,
        screen_width=1536,
        screen_height=960,
        platform="Linux x86_64",
        sec_ch_ua_platform="Linux",
        sec_ch_ua='"Chromium";v="133", "Google Chrome";v="133", "Not:A-Brand";v="24"',
        sec_ch_ua_mobile="?0",
        hardware_concurrency=8,
        device_memory=8,
    ),
    BrowserProfile(
        id="mac-safari",
        browser="safari",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
        accept_language="de-CH,de;q=0.9,en;q=0.8",
        locale="de-CH",
        timezone_id="Europe/Zurich",
        viewport_width=1512,
        viewport_height=982,
        screen_width=1512,
        screen_height=982,
        platform="MacIntel",
        sec_ch_ua_platform=None,
        sec_ch_ua=None,
        sec_ch_ua_mobile=None,
        hardware_concurrency=8,
        device_memory=8,
    ),
]

# Fallback User-Agents in case fake_useragent service is down
FALLBACK_USER_AGENTS = [profile.user_agent for profile in SWISS_BROWSER_PROFILES]

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


def get_random_browser_profile(browser: Optional[str] = None) -> BrowserProfile:
    """Pick a coherent browser profile, optionally constrained to one browser family."""
    candidates = [
        profile for profile in SWISS_BROWSER_PROFILES
        if browser is None or profile.browser == browser
    ]
    if not candidates:
        candidates = SWISS_BROWSER_PROFILES
    return random.choice(candidates)


def build_headers_for_profile(
    profile: BrowserProfile,
    *,
    compressed: bool = True,
    navigation: bool = True,
) -> dict[str, str]:
    """Build realistic request headers for a browser profile."""
    headers = {
        "User-Agent": profile.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": profile.accept_language,
        "Accept-Encoding": "gzip, deflate, br" if compressed else "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
    }
    if navigation:
        headers.update({
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        })
    if profile.sec_ch_ua:
        headers["sec-ch-ua"] = profile.sec_ch_ua
    if profile.sec_ch_ua_mobile:
        headers["sec-ch-ua-mobile"] = profile.sec_ch_ua_mobile
    if profile.sec_ch_ua_platform:
        headers["sec-ch-ua-platform"] = f'"{profile.sec_ch_ua_platform}"'
    return headers


def build_playwright_context_kwargs(profile: BrowserProfile) -> dict[str, Any]:
    """Build Playwright context kwargs matching the selected profile."""
    return {
        "viewport": {"width": profile.viewport_width, "height": profile.viewport_height},
        "screen": {"width": profile.screen_width, "height": profile.screen_height},
        "locale": profile.locale,
        "timezone_id": profile.timezone_id,
        "user_agent": profile.user_agent,
        "color_scheme": profile.color_scheme,
    }


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


def create_session(
    proxy: Optional[str] = None,
    local_addr: Optional[str] = None,
    profile: Optional[BrowserProfile] = None,
    *,
    compressed: bool = True,
) -> requests.Session:
    """Create a requests.Session with stealth headers and optional proxy/local IP.

    Args:
        proxy: Optional proxy URL, e.g. "http://user:pass@proxy:8080"
        local_addr: Optional local IP address to bind to (e.g. for IPv6 rotation)
    """
    profile = profile or get_random_browser_profile()
    session = requests.Session()

    if local_addr:
        adapter = SourceAddressAdapter(local_addr)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        logger.debug(f"Session bound to local address: {local_addr}")

    session.headers.update(build_headers_for_profile(profile, compressed=compressed))
    session.browser_profile = profile

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
