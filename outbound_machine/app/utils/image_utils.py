"""
Utilities for image URL analysis and aspect ratio heuristics.
We avoid downloading every image; instead we derive signals from URLs and
dimensions where available from the HTML.
"""
import re
from fractions import Fraction
from typing import Optional


# Common Shopify CDN image size patterns
SHOPIFY_SIZE_RE = re.compile(r"_(\d+)x(\d+)\.[a-z]{3,4}$", re.IGNORECASE)
SHOPIFY_SQUARE_RE = re.compile(r"_(\d+)x\.[a-z]{3,4}$", re.IGNORECASE)

# Image file extension pattern
IMAGE_EXT_RE = re.compile(r"\.(jpg|jpeg|png|webp|gif|avif|svg)(\?.*)?$", re.IGNORECASE)

# Lifestyle/scene shot heuristics based on URL keywords
LIFESTYLE_KEYWORDS = {"lifestyle", "model", "worn", "scene", "styled", "context", "editorial"}
DETAIL_KEYWORDS = {"detail", "close", "closeup", "close-up", "zoom", "texture", "back", "side"}
WHITE_BG_KEYWORDS = {"white", "studio", "packshot", "clean", "bg_white"}


def extract_dimensions_from_url(url: str) -> Optional[tuple[int, int]]:
    """
    Try to extract width×height from a Shopify CDN URL.
    Returns (width, height) or None.
    """
    m = SHOPIFY_SIZE_RE.search(url)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def aspect_ratio_string(w: int, h: int) -> str:
    """Convert pixel dimensions to a reduced aspect ratio string like '4:5'."""
    if w <= 0 or h <= 0:
        return "unknown"
    try:
        f = Fraction(w, h).limit_denominator(20)
        return f"{f.numerator}:{f.denominator}"
    except Exception:
        return "unknown"


def classify_image_by_url(url: str) -> dict:
    """
    Derive image classification signals purely from the URL.
    Returns dict with keys: is_lifestyle, is_detail, is_white_bg
    """
    url_lower = url.lower()
    return {
        "is_lifestyle": any(kw in url_lower for kw in LIFESTYLE_KEYWORDS),
        "is_detail": any(kw in url_lower for kw in DETAIL_KEYWORDS),
        "is_white_bg": any(kw in url_lower for kw in WHITE_BG_KEYWORDS),
    }


def infer_background_type(image_urls: list[str]) -> str:
    """
    Infer overall background type from a list of image URLs.
    Returns: "white" | "lifestyle" | "mixed" | "unknown"
    """
    if not image_urls:
        return "unknown"

    signals = [classify_image_by_url(u) for u in image_urls]
    white_count = sum(1 for s in signals if s["is_white_bg"])
    lifestyle_count = sum(1 for s in signals if s["is_lifestyle"])
    total = len(signals)

    if total == 0:
        return "unknown"
    if lifestyle_count / total > 0.6:
        return "lifestyle"
    if white_count / total > 0.6:
        return "white"
    if (lifestyle_count + white_count) > 1:
        return "mixed"
    return "unknown"


def get_aspect_ratios_from_urls(image_urls: list[str]) -> list[str]:
    """Extract aspect ratio strings from URL patterns where possible."""
    ratios = []
    for url in image_urls:
        dims = extract_dimensions_from_url(url)
        if dims:
            ratios.append(aspect_ratio_string(*dims))
    return [r for r in ratios if r != "unknown"]


def count_unique_aspect_ratios(ratios: list[str]) -> int:
    return len(set(ratios))


def is_image_url(url: str) -> bool:
    return bool(IMAGE_EXT_RE.search(url))
