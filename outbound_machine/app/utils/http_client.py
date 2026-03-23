"""
Shared HTTP client. Uses httpx with polite defaults.
Always call rate_limit(domain) before making requests.
"""
import logging
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.config.settings import settings
from app.core.rate_limiter import rate_limit

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": settings.http_user_agent,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def _domain_from_url(url: str) -> str:
    return urlparse(url).netloc or url


def get(
    url: str,
    timeout: int | None = None,
    headers: dict | None = None,
    follow_redirects: bool = True,
    rate_limited: bool = True,
) -> Optional[httpx.Response]:
    """
    Make a GET request with rate limiting and error handling.
    Returns the response or None on failure.
    """
    domain = _domain_from_url(url)
    if rate_limited:
        rate_limit(domain)

    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
    t = timeout or settings.http_timeout

    try:
        with httpx.Client(timeout=t, follow_redirects=follow_redirects) as client:
            resp = client.get(url, headers=merged_headers)
            resp.raise_for_status()
            return resp
    except httpx.HTTPStatusError as e:
        logger.warning("HTTP %s for %s", e.response.status_code, url)
        return None
    except httpx.TimeoutException:
        logger.warning("Timeout fetching %s", url)
        return None
    except httpx.HTTPError as e:
        logger.warning("HTTP error fetching %s: %s", url, e)
        return None
    except Exception as e:
        logger.warning("Unexpected error fetching %s: %s", url, e)
        return None


def get_json(url: str, **kwargs) -> Optional[dict | list]:
    """Fetch a URL and parse as JSON. Returns None on any failure."""
    resp = get(url, **kwargs)
    if resp is None:
        return None
    try:
        return resp.json()
    except Exception as e:
        logger.debug("Failed to parse JSON from %s: %s", url, e)
        return None


def get_text(url: str, **kwargs) -> Optional[str]:
    """Fetch a URL and return its text body. Returns None on failure."""
    resp = get(url, **kwargs)
    return resp.text if resp else None
