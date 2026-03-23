"""
Australian Shopify store discovery module.

Finds candidate AU e-commerce domains from DuckDuckGo search queries
defined in au_discovery_config.yaml. Deduplicates against the existing
Candidates table so domains already seen or processed are skipped.

Flow:
  1. Load queries from config (grouped by vertical)
  2. POST each query to DuckDuckGo HTML — extract result URLs
  3. Normalise and deduplicate domains
  4. Skip blacklisted domains (marketplaces, social, news)
  5. Return DiscoveryResult objects with source + query metadata

The caller (CLI or daily runner) is responsible for:
  - Running AU detection on each result
  - Filtering by au_confidence threshold
  - Creating Candidate records in the DB
"""
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs, unquote

import httpx
from bs4 import BeautifulSoup

from app.config.settings import settings
from app.utils.domain import normalise_domain

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domains that are never useful as e-commerce candidates
# ---------------------------------------------------------------------------

_BLACKLIST: set[str] = {
    # Social / content
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "pinterest.com", "tiktok.com", "reddit.com",
    "linkedin.com", "snapchat.com", "tumblr.com",
    # Marketplaces (not direct-to-consumer)
    "amazon.com", "amazon.com.au", "ebay.com", "ebay.com.au",
    "etsy.com", "catch.com.au", "kogan.com", "myer.com.au",
    "davidjones.com", "theiconic.com.au", "styletread.com.au",
    # General web / search
    "google.com", "bing.com", "yahoo.com", "duckduckgo.com",
    "wikipedia.org", "wikimedia.org",
    # Review / directory
    "yelp.com", "tripadvisor.com", "productreview.com.au",
    "trustpilot.com",
    # News
    "news.com.au", "abc.net.au", "smh.com.au", "heraldsun.com.au",
    "theage.com.au", "theguardian.com", "nytimes.com",
    # Payment / BNPL (not stores)
    "afterpay.com", "zip.co", "paypal.com", "stripe.com",
    # Wholesale / B2B
    "alibaba.com", "aliexpress.com", "dhgate.com",
}

# Substrings that indicate non-DTC domains (applied to full domain)
_BLACKLIST_PATTERNS = [
    "wordpress.com", "blogspot.com", "wix.com", "squarespace.com",
    "shopify.com",  # Shopify itself, not a merchant
    "myshopify.com",  # Dev stores — we want custom domains
]

# DuckDuckGo search endpoint (HTML version — no JS, no API key needed)
_DDG_URL = "https://html.duckduckgo.com/html/"

_SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
}


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------

@dataclass
class DiscoveryResult:
    domain: str
    discovery_source: str          # "duckduckgo_search" | "static_seed"
    discovery_query: str           # query string that surfaced this domain
    discovery_vertical: str        # apparel | beauty | accessories | etc.
    raw_url: str                   # original URL before domain normalisation
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def discover_au_candidates(
    queries_by_vertical: dict[str, list[str]],
    limit_per_query: int = 10,
    search_delay: float = 3.0,
    existing_domains: Optional[set[str]] = None,
    daily_limit: Optional[int] = None,
) -> list[DiscoveryResult]:
    """
    Search for candidate AU e-commerce domains from vertical-keyed queries.

    Args:
        queries_by_vertical: {"apparel": ["query1", ...], "beauty": [...], ...}
        limit_per_query:     Max domains to extract per search query.
        search_delay:        Seconds to wait between search requests (polite).
        existing_domains:    Set of domains already in DB — these are skipped.
        daily_limit:         Hard cap on total new domains returned.

    Returns:
        List of DiscoveryResult, deduplicated against existing_domains.
    """
    seen = set(existing_domains or [])
    results: list[DiscoveryResult] = []

    for vertical, queries in queries_by_vertical.items():
        for query in queries:
            if daily_limit and len(results) >= daily_limit:
                logger.info("Daily discovery limit (%d) reached", daily_limit)
                return results

            try:
                logger.info("Searching [%s]: %s", vertical, query)
                raw_urls = _search_duckduckgo(query, limit=limit_per_query)
                time.sleep(search_delay)

                for url in raw_urls:
                    domain = _extract_domain(url)
                    if not domain or domain in seen or _is_blacklisted(domain):
                        continue
                    seen.add(domain)
                    results.append(DiscoveryResult(
                        domain=domain,
                        discovery_source="duckduckgo_search",
                        discovery_query=query,
                        discovery_vertical=vertical,
                        raw_url=url,
                    ))

            except Exception as e:
                logger.warning("Discovery query failed [%s] '%s': %s", vertical, query, e)

    logger.info("Discovery complete: %d new candidate domains found", len(results))
    return results


def get_existing_domains(session) -> set[str]:
    """Return set of all domains already in the candidates table."""
    from app.db.models import Candidate
    rows = session.query(Candidate.domain).all()
    return {r[0] for r in rows}


# ---------------------------------------------------------------------------
# DuckDuckGo search
# ---------------------------------------------------------------------------

def _search_duckduckgo(query: str, limit: int = 10) -> list[str]:
    """
    POST a query to DuckDuckGo HTML endpoint and return result URLs.
    Returns empty list on any failure — callers should handle gracefully.
    """
    try:
        with httpx.Client(
            timeout=20,
            follow_redirects=True,
            headers=_SEARCH_HEADERS,
        ) as client:
            resp = client.post(
                _DDG_URL,
                data={"q": query, "kl": "au-en"},
            )
            resp.raise_for_status()
            return _parse_ddg_html(resp.text, limit=limit)

    except httpx.HTTPStatusError as e:
        logger.warning("DuckDuckGo returned %s for query: %s", e.response.status_code, query)
    except httpx.TimeoutException:
        logger.warning("DuckDuckGo timeout for query: %s", query)
    except Exception as e:
        logger.warning("DuckDuckGo error for query '%s': %s", query, e)

    return []


def _parse_ddg_html(html: str, limit: int = 10) -> list[str]:
    """
    Parse DuckDuckGo HTML search results and return raw result URLs.

    DuckDuckGo HTML result links use `class="result__a"` and their href
    is a redirect: `//duckduckgo.com/l/?uddg=<url-encoded-destination>`.
    """
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []

    for a_tag in soup.find_all("a", class_="result__a"):
        href = a_tag.get("href", "")
        url = _decode_ddg_href(href)
        if url:
            urls.append(url)
        if len(urls) >= limit:
            break

    # Fallback: if result__a class parsing found nothing, try result-link
    if not urls:
        for a_tag in soup.find_all("a", class_="result-link"):
            href = a_tag.get("href", "")
            if href.startswith("http"):
                urls.append(href)
            if len(urls) >= limit:
                break

    return urls


def _decode_ddg_href(href: str) -> Optional[str]:
    """Decode a DuckDuckGo redirect href to get the destination URL."""
    if not href:
        return None
    # Handle absolute or protocol-relative DDG redirect
    if "uddg=" in href:
        try:
            # href may start with // — normalise to https:
            if href.startswith("//"):
                href = "https:" + href
            parsed = urlparse(href)
            params = parse_qs(parsed.query)
            if "uddg" in params:
                return unquote(params["uddg"][0])
        except Exception:
            return None
    # Direct URL
    if href.startswith("http"):
        return href
    return None


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

def _extract_domain(url: str) -> Optional[str]:
    """Extract and normalise the domain from a URL."""
    try:
        return normalise_domain(url)
    except Exception:
        return None


def _is_blacklisted(domain: str) -> bool:
    """Return True if domain is in the blacklist or matches a blacklist pattern."""
    if domain in _BLACKLIST:
        return True
    d_lower = domain.lower()
    return any(pat in d_lower for pat in _BLACKLIST_PATTERNS)
