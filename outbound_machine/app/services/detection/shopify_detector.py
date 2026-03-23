"""
Stage 2: Shopify detection.

Uses multiple independent signals to determine whether a domain runs on Shopify.
Returns a confidence score (0.0–1.0) and a list of evidence strings.

Signal hierarchy (highest to lowest confidence):
1. /products.json responds with valid Shopify product JSON         → 0.95
2. myshopify.com reference in HTML                                 → 0.90
3. Shopify CDN (cdn.shopify.com) references                        → 0.85
4. window.Shopify JS object in source                              → 0.80
5. /collections/all returns a page with Shopify class patterns     → 0.75
6. X-ShopId / X-Shopify-Stage HTTP response headers               → 0.80
7. /sitemap.xml references /products/ URLs                         → 0.70
8. Shopify payment badges / script tags in source                  → 0.65
9. /robots.txt mentions myshopify.com or Shopify                   → 0.60

Final confidence = max of any triggered signal (not additive).
Multiple signals increase confidence: final = 1 - prod(1 - p_i) clipped to 0.99.
"""
import logging
import re
from dataclasses import dataclass, field

from app.utils.domain import build_url
from app.utils.http_client import get, get_json, get_text

logger = logging.getLogger(__name__)

# --- Regex patterns ---
RE_MYSHOPIFY = re.compile(r"myshopify\.com", re.IGNORECASE)
RE_SHOPIFY_CDN = re.compile(r"cdn\.shopify\.com", re.IGNORECASE)
RE_WINDOW_SHOPIFY = re.compile(r"window\.Shopify\s*=|Shopify\.theme|ShopifyAnalytics", re.IGNORECASE)
RE_SHOPIFY_SCRIPT = re.compile(r"shopify\.com/s/files|Shopify\.shop", re.IGNORECASE)
RE_SHOPIFY_CLASS = re.compile(r'class="shopify-|data-shopify|shopify-section', re.IGNORECASE)
RE_PRODUCT_JSON_KEY = re.compile(r'"products"\s*:\s*\[', re.IGNORECASE)
RE_SITEMAP_PRODUCT = re.compile(r"<loc>[^<]*/products/[^<]+</loc>", re.IGNORECASE)
RE_PAYMENT_BADGE = re.compile(r"shopify-payment-button|shopify_pay", re.IGNORECASE)


@dataclass
class ShopifyDetectionResult:
    domain: str
    shopify_detected: bool
    confidence: float
    evidence: list[str] = field(default_factory=list)


def detect_shopify(domain: str) -> ShopifyDetectionResult:
    """
    Run all detection signals for the given domain.
    Returns a ShopifyDetectionResult with confidence and evidence.
    """
    logger.info("Detecting Shopify for: %s", domain)
    evidence: list[str] = []
    signal_scores: list[float] = []

    def record(signal: str, score: float) -> None:
        evidence.append(signal)
        signal_scores.append(score)
        logger.debug("  Signal: %s (%.2f)", signal, score)

    # --- Signal 1: /products.json ---
    products_url = build_url(domain, "/products.json?limit=1")
    pj = get_json(products_url, rate_limited=True)
    if isinstance(pj, dict) and "products" in pj:
        record("products_json_endpoint_valid", 0.95)

    # --- Fetch homepage HTML once (reuse for multiple signals) ---
    homepage_html = get_text(build_url(domain, "/"), rate_limited=True) or ""

    # --- Signal 2: myshopify.com reference ---
    if RE_MYSHOPIFY.search(homepage_html):
        record("myshopify_reference_in_html", 0.90)

    # --- Signal 3: Shopify CDN ---
    if RE_SHOPIFY_CDN.search(homepage_html):
        record("shopify_cdn_reference", 0.85)

    # --- Signal 4: window.Shopify JS object ---
    if RE_WINDOW_SHOPIFY.search(homepage_html):
        record("window_shopify_js_object", 0.80)

    # --- Signal 5: Shopify script URLs ---
    if RE_SHOPIFY_SCRIPT.search(homepage_html):
        record("shopify_script_url", 0.75)

    # --- Signal 6: Shopify HTML classes/attributes ---
    if RE_SHOPIFY_CLASS.search(homepage_html):
        record("shopify_html_attributes", 0.70)

    # --- Signal 7: Payment badge ---
    if RE_PAYMENT_BADGE.search(homepage_html):
        record("shopify_payment_badge", 0.65)

    # --- Signal 8: HTTP response headers (re-fetch homepage for headers) ---
    resp = get(build_url(domain, "/"), rate_limited=False)  # already rate-limited above
    if resp is not None:
        headers_lower = {k.lower(): v.lower() for k, v in resp.headers.items()}
        if "x-shopid" in headers_lower or "x-shopify-stage" in headers_lower:
            record("shopify_http_headers", 0.80)
        # Some stores expose this
        powered_by = headers_lower.get("x-powered-by", "")
        if "shopify" in powered_by:
            record("x_powered_by_shopify", 0.90)

    # --- Signal 9: Sitemap ---
    sitemap_text = get_text(build_url(domain, "/sitemap.xml"), rate_limited=False) or ""
    if RE_SITEMAP_PRODUCT.search(sitemap_text):
        record("sitemap_product_urls", 0.70)

    # --- Signal 10: robots.txt ---
    robots_text = get_text(build_url(domain, "/robots.txt"), rate_limited=False) or ""
    if RE_MYSHOPIFY.search(robots_text) or "shopify" in robots_text.lower():
        record("robots_txt_shopify_reference", 0.60)

    # --- Combine scores (Bayesian combination: p = 1 - prod(1 - p_i)) ---
    if not signal_scores:
        combined = 0.0
    else:
        from functools import reduce
        combined = 1.0 - reduce(lambda acc, s: acc * (1 - s), signal_scores, 1.0)
        combined = min(combined, 0.99)

    detected = combined >= 0.50
    logger.info(
        "Shopify detection: %s — detected=%s confidence=%.2f signals=%d",
        domain, detected, combined, len(signal_scores),
    )
    return ShopifyDetectionResult(
        domain=domain,
        shopify_detected=detected,
        confidence=round(combined, 3),
        evidence=evidence,
    )
