"""
Stage 6: Screenshot capture.

Uses Playwright for full-page screenshots of:
- Homepage
- One collection page
- Up to 3 product pages

Screenshots are gated behind ENABLE_SCREENSHOTS config flag.
When disabled, the service returns placeholder metadata indicating skipped status.

Playwright must be installed separately: `playwright install chromium`
"""
import logging
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from app.config.settings import settings
from app.utils.domain import extract_domain_from_url

logger = logging.getLogger(__name__)

VIEWPORT_WIDTH = 1440
VIEWPORT_HEIGHT = 900
MAX_PRODUCT_SCREENSHOTS = 3


@dataclass
class ScreenshotResult:
    url: str
    page_type: str          # "homepage" | "collection" | "product"
    file_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    captured_at: Optional[datetime] = None
    capture_error: Optional[str] = None
    skipped: bool = False


@dataclass
class ScreenshotBatch:
    domain: str
    homepage: Optional[ScreenshotResult] = None
    collection: Optional[ScreenshotResult] = None
    products: list[ScreenshotResult] = field(default_factory=list)
    screenshots_enabled: bool = False


def capture_screenshots(
    domain: str,
    homepage_url: str,
    collection_url: Optional[str],
    product_urls: list[str],
) -> ScreenshotBatch:
    """
    Capture screenshots for a lead. Gate on ENABLE_SCREENSHOTS.
    Returns a ScreenshotBatch with results (or skipped flags).
    """
    batch = ScreenshotBatch(domain=domain, screenshots_enabled=settings.enable_screenshots)

    if not settings.enable_screenshots:
        logger.info("Screenshots disabled — skipping for %s", domain)
        batch.homepage = ScreenshotResult(
            url=homepage_url, page_type="homepage", skipped=True
        )
        if collection_url:
            batch.collection = ScreenshotResult(
                url=collection_url, page_type="collection", skipped=True
            )
        for url in product_urls[:MAX_PRODUCT_SCREENSHOTS]:
            batch.products.append(ScreenshotResult(url=url, page_type="product", skipped=True))
        return batch

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        batch.homepage = ScreenshotResult(
            url=homepage_url, page_type="homepage",
            capture_error="Playwright not installed"
        )
        return batch

    output_dir = settings.screenshots_dir / _safe_dirname(domain)
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            user_agent=settings.http_user_agent,
        )
        page = context.new_page()

        # Homepage
        batch.homepage = _capture_page(
            page, homepage_url, "homepage", output_dir, PlaywrightTimeout
        )

        # Collection
        if collection_url:
            batch.collection = _capture_page(
                page, collection_url, "collection", output_dir, PlaywrightTimeout
            )

        # Products (up to MAX_PRODUCT_SCREENSHOTS)
        for url in product_urls[:MAX_PRODUCT_SCREENSHOTS]:
            result = _capture_page(page, url, "product", output_dir, PlaywrightTimeout)
            batch.products.append(result)

        browser.close()

    logger.info(
        "Screenshots complete for %s — homepage=%s collection=%s products=%d",
        domain,
        "ok" if batch.homepage and not batch.homepage.capture_error else "failed",
        "ok" if batch.collection and not batch.collection.capture_error else "n/a",
        len([p for p in batch.products if not p.capture_error]),
    )
    return batch


def _capture_page(
    page,
    url: str,
    page_type: str,
    output_dir: Path,
    PlaywrightTimeout,
) -> ScreenshotResult:
    result = ScreenshotResult(url=url, page_type=page_type)
    file_path = output_dir / f"{page_type}_{_url_hash(url)}.png"

    try:
        page.goto(url, wait_until="networkidle", timeout=30_000)
        page.screenshot(path=str(file_path), full_page=False)
        stat = file_path.stat()
        result.file_path = str(file_path.relative_to(settings.screenshots_dir))
        result.file_size_bytes = stat.st_size
        result.width = VIEWPORT_WIDTH
        result.height = VIEWPORT_HEIGHT
        result.captured_at = datetime.now(timezone.utc)
        logger.debug("Screenshot saved: %s", file_path)
    except PlaywrightTimeout:
        result.capture_error = f"Timeout loading {url}"
        logger.warning("Playwright timeout for %s", url)
    except Exception as e:
        result.capture_error = str(e)
        logger.warning("Screenshot failed for %s: %s", url, e)

    return result


def _safe_dirname(domain: str) -> str:
    return re.sub(r"[^a-z0-9-]", "_", domain.lower())


def _url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:8]
