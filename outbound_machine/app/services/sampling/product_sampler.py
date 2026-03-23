"""
Stage 4: Product sampling.

Selects 5–15 representative product URLs from a store, attempting to
diversify across collections/categories. Outputs a list of URLs ready
for scraping in Stage 5.

Strategy:
1. Pull product list from /products.json (most reliable for Shopify)
2. Discover collections and sample from top-N collections
3. Fall back to /collections/all page link scraping
4. Fall back to sitemap product URLs

Goal is diversity — we want to see representative breadth of the catalogue.
"""
import logging
import random
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.utils.domain import build_url, base_url
from app.utils.http_client import get_json, get_text

logger = logging.getLogger(__name__)

MIN_SAMPLE = 5
MAX_SAMPLE = 15
# Shopify product handle pattern
RE_PRODUCT_PATH = re.compile(r"^/products/[a-z0-9_-]+$", re.IGNORECASE)


@dataclass
class SamplingResult:
    domain: str
    product_urls: list[str] = field(default_factory=list)
    collection_urls: list[str] = field(default_factory=list)  # for screenshots
    method: str = "unknown"
    notes: str = ""


def sample_products(
    domain: str,
    min_sample: int = MIN_SAMPLE,
    max_sample: int = MAX_SAMPLE,
) -> SamplingResult:
    logger.info("Sampling products for: %s", domain)

    result = SamplingResult(domain=domain)

    # --- Try products.json ---
    products_json_result = _sample_from_products_json(domain, max_sample)
    if len(products_json_result) >= min_sample:
        result.product_urls = products_json_result
        result.method = "products_json"
        result.notes = f"Sampled {len(result.product_urls)} products via /products.json."
        # Also discover collection URLs for screenshots
        result.collection_urls = _get_collection_urls(domain)
        logger.info("Sampled %d products via products.json", len(result.product_urls))
        return result

    # --- Try collections-based sampling ---
    collection_urls = _get_collection_urls(domain)
    result.collection_urls = collection_urls
    if collection_urls:
        collection_products = _sample_from_collections(domain, collection_urls, max_sample)
        if len(collection_products) >= min_sample:
            result.product_urls = collection_products
            result.method = "collection_pages"
            result.notes = f"Sampled {len(result.product_urls)} products from collection pages."
            logger.info("Sampled %d products from collections", len(result.product_urls))
            return result

    # --- Combine what we have ---
    combined = list(set(products_json_result + _sample_from_collections(domain, collection_urls or [], max_sample)))
    if combined:
        result.product_urls = combined[:max_sample]
        result.method = "combined"
        result.notes = f"Combined sampling: {len(result.product_urls)} products."
        return result

    # --- Fallback: sitemap ---
    sitemap_products = _sample_from_sitemap(domain, max_sample)
    if sitemap_products:
        result.product_urls = sitemap_products
        result.method = "sitemap"
        result.notes = f"Sampled {len(result.product_urls)} products from sitemap."
        return result

    logger.warning("Could not sample products for %s", domain)
    result.notes = "No product URLs discovered."
    return result


def _sample_from_products_json(domain: str, max_sample: int) -> list[str]:
    """
    Get product URLs from /products.json. Returns absolute URLs.
    Picks from multiple pages to maximise diversity.
    """
    urls: list[str] = []
    base = base_url(domain)

    # Pull up to 3 pages and sample from each for diversity
    handles_by_page: list[list[str]] = []
    for page in range(1, 6):
        data = get_json(
            build_url(domain, f"/products.json?limit=250&page={page}"),
            rate_limited=(page == 1),
        )
        if not isinstance(data, dict) or not data.get("products"):
            break
        page_handles = [
            p["handle"] for p in data["products"] if p.get("handle")
        ]
        if not page_handles:
            break
        handles_by_page.append(page_handles)

    if not handles_by_page:
        return []

    # Flatten and deduplicate
    all_handles = list(dict.fromkeys(h for page in handles_by_page for h in page))

    # Diverse sampling: pick evenly across the catalogue
    if len(all_handles) <= max_sample:
        sampled = all_handles
    else:
        step = len(all_handles) // max_sample
        sampled = [all_handles[i * step] for i in range(max_sample)]

    return [f"{base}/products/{h}" for h in sampled]


def _get_collection_urls(domain: str) -> list[str]:
    """
    Discover collection URLs by fetching /collections.json or parsing the
    nav/footer of the homepage.
    """
    base = base_url(domain)
    collections: list[str] = []

    # Try Shopify collections.json
    data = get_json(build_url(domain, "/collections.json?limit=20"))
    if isinstance(data, dict) and data.get("collections"):
        for c in data["collections"]:
            handle = c.get("handle")
            if handle and handle not in ("all", "frontpage"):
                collections.append(f"{base}/collections/{handle}")
        if collections:
            return collections[:10]

    # Fall back to parsing homepage navigation
    html = get_text(build_url(domain, "/")) or ""
    if html:
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r"/collections/[a-z0-9_-]+", href):
                full = urljoin(base, href)
                if full not in collections and "all" not in full:
                    collections.append(full)
        if collections:
            return list(dict.fromkeys(collections))[:10]

    # Include /collections/all as a final fallback
    return [f"{base}/collections/all"]


def _sample_from_collections(
    domain: str,
    collection_urls: list[str],
    max_sample: int,
) -> list[str]:
    """Scrape each collection page and collect product links."""
    base = base_url(domain)
    product_urls: set[str] = set()
    per_collection = max(2, max_sample // max(len(collection_urls), 1))

    for col_url in collection_urls[:5]:
        html = get_text(col_url) or ""
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        count = 0
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if RE_PRODUCT_PATH.match(href) or "/products/" in href:
                full = urljoin(base, href).split("?")[0]
                if full not in product_urls:
                    product_urls.add(full)
                    count += 1
                    if count >= per_collection:
                        break

    result = list(product_urls)
    if len(result) > max_sample:
        random.shuffle(result)
        result = result[:max_sample]
    return result


def _sample_from_sitemap(domain: str, max_sample: int) -> list[str]:
    """Extract product URLs from sitemap as a last resort."""
    base = base_url(domain)
    sitemap = get_text(build_url(domain, "/sitemap.xml")) or ""
    if not sitemap:
        return []

    # Check for product sub-sitemaps
    sub_re = re.compile(r"<loc>([^<]*sitemap_products[^<]*)</loc>")
    subs = sub_re.findall(sitemap)
    product_locs: list[str] = []
    if subs:
        for sub_url in subs[:3]:
            sub_text = get_text(sub_url) or ""
            locs = re.findall(r"<loc>([^<]*/products/[^<]+)</loc>", sub_text)
            product_locs.extend(locs)
    else:
        product_locs = re.findall(r"<loc>([^<]*/products/[^<]+)</loc>", sitemap)

    # Deduplicate and diversify
    unique = list(dict.fromkeys(product_locs))
    if len(unique) <= max_sample:
        return unique
    step = len(unique) // max_sample
    return [unique[i * step] for i in range(max_sample)]
