"""
Stage 3: SKU estimation.

Goal: classify a store into a rough SKU bucket that determines ICP fit.
We want 20–200 SKUs (ideal ICP range). Very small or very large stores
are lower priority.

Strategy (in order of reliability):
1. Enumerate /products.json pages — most accurate if accessible (Shopify default)
2. Parse /collections/all page for product count hint
3. Count product URLs in /sitemap.xml product sub-sitemaps
4. Scan /collections/all page for pagination hints ("Showing X of Y")
5. Count internal /products/ links on collection pages

Returns a SkuEstimationResult with a bucket enum and notes string.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.utils.domain import build_url
from app.utils.http_client import get_json, get_text, get
from app.db.models import SkuRange

logger = logging.getLogger(__name__)

# Shopify products.json is paginated; max 250 per page
SHOPIFY_PAGE_SIZE = 250
# We'll cap at 10 pages (2500) to avoid abuse
MAX_PAGES_TO_CHECK = 10

RE_PRODUCT_COUNT_HINT = re.compile(
    r"(\d[\d,]*)\s*(products?|items?|styles?|results?)", re.IGNORECASE
)
RE_SITEMAP_PRODUCT_LOC = re.compile(
    r"<loc>([^<]*/products/[^<]+)</loc>", re.IGNORECASE
)
RE_PRODUCT_LINK = re.compile(r'href="(/products/[^"?#]+)"')


def _bucket(count: int) -> str:
    if count < 20:
        return SkuRange.under_20.value
    if count < 50:
        return SkuRange.r20_50.value
    if count < 100:
        return SkuRange.r50_100.value
    if count < 200:
        return SkuRange.r100_200.value
    return SkuRange.r200_plus.value


@dataclass
class SkuEstimationResult:
    domain: str
    estimated_count: Optional[int]      # best-effort count; None if unknown
    bucket: str                          # SkuRange value
    method: str                          # how we estimated
    notes: str


def estimate_skus(domain: str) -> SkuEstimationResult:
    logger.info("Estimating SKUs for: %s", domain)

    # --- Method 1: /products.json enumeration ---
    result = _try_products_json(domain)
    if result:
        return result

    # --- Method 2: collections/all page hint ---
    result = _try_collections_all(domain)
    if result:
        return result

    # --- Method 3: sitemap product URLs ---
    result = _try_sitemap(domain)
    if result:
        return result

    # --- Fallback ---
    logger.info("Could not estimate SKUs for %s — defaulting to unknown", domain)
    return SkuEstimationResult(
        domain=domain,
        estimated_count=None,
        bucket=SkuRange.unknown.value,
        method="unknown",
        notes="Could not determine product count from public endpoints.",
    )


def _try_products_json(domain: str) -> Optional[SkuEstimationResult]:
    """
    Shopify exposes /products.json?limit=250&page=N by default.
    We enumerate pages until we get an empty result.
    """
    all_handles: set[str] = set()
    page = 1
    while page <= MAX_PAGES_TO_CHECK:
        url = build_url(domain, f"/products.json?limit={SHOPIFY_PAGE_SIZE}&page={page}")
        data = get_json(url, rate_limited=(page == 1))
        if not isinstance(data, dict) or "products" not in data:
            if page == 1:
                return None  # Not Shopify or products.json blocked
            break  # No more pages
        products = data["products"]
        if not products:
            break
        for p in products:
            handle = p.get("handle") or str(p.get("id", ""))
            all_handles.add(handle)
        if len(products) < SHOPIFY_PAGE_SIZE:
            break  # Last page
        page += 1

    if not all_handles:
        return None

    count = len(all_handles)
    bucket = _bucket(count)
    logger.info("products.json method: %d SKUs → bucket=%s", count, bucket)
    return SkuEstimationResult(
        domain=domain,
        estimated_count=count,
        bucket=bucket,
        method="products_json",
        notes=f"Enumerated {count} products via /products.json (pages checked: {page - 1}).",
    )


def _try_collections_all(domain: str) -> Optional[SkuEstimationResult]:
    """
    Parse /collections/all for text hints about total product count.
    Many Shopify themes show "Showing 1–24 of 142 products".
    """
    html = get_text(build_url(domain, "/collections/all"), rate_limited=True) or ""
    if not html:
        return None

    # Look for explicit count text
    m = RE_PRODUCT_COUNT_HINT.search(html)
    if m:
        count_str = m.group(1).replace(",", "")
        try:
            count = int(count_str)
            if count > 0:
                bucket = _bucket(count)
                logger.info("collections/all hint: %d SKUs → bucket=%s", count, bucket)
                return SkuEstimationResult(
                    domain=domain,
                    estimated_count=count,
                    bucket=bucket,
                    method="collections_all_text_hint",
                    notes=f"Found '{m.group(0)}' on /collections/all.",
                )
        except ValueError:
            pass

    # Count /products/ links as a proxy
    links = set(RE_PRODUCT_LINK.findall(html))
    if len(links) >= 5:
        # Assume this is at least one page of products
        # We can't know the total without pagination, so classify conservatively
        visible = len(links)
        # If we see e.g. 24 products on page 1, likely more — treat as lower bound
        notes = (
            f"Found {visible} product links on /collections/all page 1. "
            "Total may be higher — classified as lower bound."
        )
        bucket = _bucket(visible)
        logger.info("collections/all link count: %d visible → bucket=%s", visible, bucket)
        return SkuEstimationResult(
            domain=domain,
            estimated_count=visible,
            bucket=bucket,
            method="collections_all_link_count",
            notes=notes,
        )

    return None


def _try_sitemap(domain: str) -> Optional[SkuEstimationResult]:
    """
    Fetch sitemap.xml and count /products/ URLs. Works for both
    Shopify standard sitemaps and custom sitemap structures.
    """
    sitemap_text = get_text(build_url(domain, "/sitemap.xml"), rate_limited=True) or ""
    if not sitemap_text:
        return None

    # Shopify sitemaps link to sub-sitemaps like /sitemap_products_1.xml
    sub_sitemap_re = re.compile(r"<loc>([^<]*sitemap_products[^<]*)</loc>", re.IGNORECASE)
    sub_urls = sub_sitemap_re.findall(sitemap_text)

    product_urls: set[str] = set()

    if sub_urls:
        for sub_url in sub_urls[:5]:  # cap at 5 sub-sitemaps
            sub_text = get_text(sub_url, rate_limited=True) or ""
            locs = RE_SITEMAP_PRODUCT_LOC.findall(sub_text)
            product_urls.update(locs)
    else:
        # Direct product URLs in main sitemap
        locs = RE_SITEMAP_PRODUCT_LOC.findall(sitemap_text)
        product_urls.update(locs)

    if not product_urls:
        return None

    count = len(product_urls)
    bucket = _bucket(count)
    logger.info("sitemap method: %d SKUs → bucket=%s", count, bucket)
    return SkuEstimationResult(
        domain=domain,
        estimated_count=count,
        bucket=bucket,
        method="sitemap",
        notes=f"Found {count} product URLs in sitemap.",
    )
