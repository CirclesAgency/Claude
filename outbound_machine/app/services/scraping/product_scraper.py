"""
Stage 5: Product page scraping.

For each sampled PDP, extracts:
- product title, category, breadcrumb
- image URLs, image count, alt texts
- variant count and options
- aspect ratio clues from URL patterns or img width/height attrs
- background type inference
- page title, description snippet
- lifestyle/detail shot signals

Uses BeautifulSoup + httpx. Does NOT require Playwright.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.schemas.product import ProductSampleData
from app.utils.domain import extract_domain_from_url
from app.utils.http_client import get, get_json
from app.utils.image_utils import (
    extract_dimensions_from_url,
    aspect_ratio_string,
    classify_image_by_url,
    infer_background_type,
    is_image_url,
)

logger = logging.getLogger(__name__)

# Shopify product JSON endpoint
RE_HANDLE_FROM_URL = re.compile(r"/products/([a-z0-9_-]+)", re.IGNORECASE)
RE_OG_IMAGE = re.compile(r'content="([^"]+\.(jpg|jpeg|png|webp))"', re.IGNORECASE)
RE_SCHEMA_PRICE = re.compile(r'"price"\s*:\s*"?([\d.]+)"?')
# Shopify CDN image URL pattern
SHOPIFY_CDN_IMG_RE = re.compile(r"https://cdn\.shopify\.com/s/files/[^\s\"'>]+", re.IGNORECASE)


def scrape_product(url: str) -> ProductSampleData:
    """
    Scrape a single product page URL and return structured data.
    Never raises; errors are captured in ProductSampleData.scrape_error.
    """
    domain = extract_domain_from_url(url)
    logger.info("Scraping product: %s", url)

    result = ProductSampleData(
        url=url,
        scraped_at=datetime.now(timezone.utc),
    )

    try:
        # --- Try Shopify product JSON API first (most reliable) ---
        json_data = _try_product_json(url)
        if json_data:
            _enrich_from_json(result, json_data, url)
        else:
            _enrich_from_html(result, url)

        # Post-process
        result.image_count = len(result.image_urls)
        result.thumbnail_count = min(result.image_count, _count_thumbnails(url))
        result.background_type = infer_background_type(result.image_urls)

        # Derive lifestyle/detail flags
        signals = [classify_image_by_url(u) for u in result.image_urls]
        result.has_lifestyle_shots = any(s["is_lifestyle"] for s in signals)
        result.has_detail_shots = any(s["is_detail"] for s in signals)

        # Aspect ratios from URLs
        result.aspect_ratios = _extract_aspect_ratios(result.image_urls)

    except Exception as e:
        logger.error("Failed scraping %s: %s", url, e, exc_info=True)
        result.scrape_error = str(e)

    return result


def scrape_products(urls: list[str]) -> list[ProductSampleData]:
    """Scrape a list of product URLs, continuing on individual failures."""
    results = []
    for url in urls:
        data = scrape_product(url)
        results.append(data)
    return results


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _try_product_json(url: str) -> Optional[dict]:
    """
    For Shopify, /products/<handle>.json returns full product data.
    This is much more reliable than HTML scraping.
    """
    m = RE_HANDLE_FROM_URL.search(url)
    if not m:
        return None
    handle = m.group(1)
    domain = extract_domain_from_url(url)
    json_url = f"https://{domain}/products/{handle}.json"
    data = get_json(json_url, rate_limited=False)  # already rate-limited by get()
    if isinstance(data, dict) and "product" in data:
        return data["product"]
    return None


def _enrich_from_json(result: ProductSampleData, product: dict, original_url: str) -> None:
    """Populate ProductSampleData from Shopify product JSON."""
    result.product_title = product.get("title")
    result.page_title = product.get("title")
    result.description_snippet = _strip_html(product.get("body_html", ""))[:500]

    # Product type as category
    result.category = product.get("product_type") or product.get("vendor")

    # Images
    images = product.get("images", [])
    result.image_urls = [img["src"] for img in images if img.get("src")]
    result.alt_texts = [img.get("alt") or "" for img in images]

    # Variants
    variants = product.get("variants", [])
    result.variant_count = len(variants)
    options = product.get("options", [])
    result.variant_options = [o.get("name", "") for o in options if o.get("name")]

    # Dimensions from image URLs
    for img_url in result.image_urls:
        dims = extract_dimensions_from_url(img_url)
        if dims:
            result.image_dimensions.append({"w": dims[0], "h": dims[1]})


def _enrich_from_html(result: ProductSampleData, url: str) -> None:
    """Parse product page HTML when JSON API is not available."""
    resp = get(url, rate_limited=False)  # rate-limited upstream
    if resp is None:
        result.scrape_error = "HTTP request failed"
        return

    html = resp.text
    soup = BeautifulSoup(html, "lxml")

    # Page title
    title_tag = soup.find("title")
    result.page_title = title_tag.get_text(strip=True) if title_tag else None

    # Product title — common patterns
    for selector in ["h1.product__title", "h1.product-title", "h1.product_title",
                     "h1[itemprop='name']", ".product-name h1", "h1"]:
        el = soup.select_one(selector)
        if el:
            result.product_title = el.get_text(strip=True)
            break

    # Breadcrumb
    for selector in [".breadcrumb", "nav[aria-label='breadcrumb']", ".breadcrumbs"]:
        el = soup.select_one(selector)
        if el:
            result.breadcrumb = " > ".join(
                a.get_text(strip=True) for a in el.find_all("a")
            )
            break

    # Description
    for selector in [".product__description", ".product-description",
                     "[itemprop='description']", ".description"]:
        el = soup.select_one(selector)
        if el:
            result.description_snippet = el.get_text(separator=" ", strip=True)[:500]
            break

    # Images — collect from img tags and Shopify CDN URLs
    image_urls: set[str] = set()

    # img tags with src
    for img in soup.find_all("img", src=True):
        src = img.get("src", "")
        if is_image_url(src) or "cdn.shopify.com" in src:
            full = urljoin(url, src)
            image_urls.add(full.split("?")[0])

    # data-src / data-zoom-src (lazy loaded)
    for img in soup.find_all(attrs={"data-src": True}):
        src = img["data-src"]
        if is_image_url(src) or "cdn.shopify.com" in src:
            full = urljoin(url, src)
            image_urls.add(full.split("?")[0])

    # Open graph image
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        image_urls.add(og["content"].split("?")[0])

    result.image_urls = list(image_urls)
    result.alt_texts = [
        img.get("alt", "")
        for img in soup.find_all("img", src=True)
        if img.get("alt")
    ]

    # Variant count from select dropdowns or swatch count
    select_els = soup.find_all("select", {"name": re.compile(r"option", re.I)})
    if select_els:
        options_count = sum(len(s.find_all("option")) for s in select_els)
        result.variant_count = max(options_count, 1)
        result.variant_options = [s.get("id", "").replace("SingleOptionSelector-", "")
                                  for s in select_els]

    # Image dimensions from img width/height attributes
    for img in soup.find_all("img", src=True):
        w = img.get("width")
        h = img.get("height")
        if w and h:
            try:
                result.image_dimensions.append({"w": int(w), "h": int(h)})
            except ValueError:
                pass


def _extract_aspect_ratios(image_urls: list[str]) -> list[str]:
    ratios = []
    for url in image_urls:
        dims = extract_dimensions_from_url(url)
        if dims:
            ratios.append(aspect_ratio_string(*dims))
    return ratios


def _count_thumbnails(url: str) -> int:
    """
    Heuristic: assume up to 6 thumbnails are shown on typical Shopify PDPs.
    We don't parse the carousel here — just return a conservative estimate.
    """
    return 6


def _strip_html(html: str) -> str:
    """Strip HTML tags from a string."""
    if not html:
        return ""
    return BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)
