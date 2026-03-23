"""Schemas for product page scraping results."""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class ProductSampleData(BaseModel):
    """Structured result from scraping a single product page."""
    url: str
    product_title: Optional[str] = None
    category: Optional[str] = None
    breadcrumb: Optional[str] = None

    image_urls: list[str] = []
    image_count: int = 0
    alt_texts: list[str] = []
    thumbnail_count: int = 0

    variant_count: int = 0
    variant_options: list[str] = []

    aspect_ratios: list[str] = []
    image_dimensions: list[dict] = []   # [{"w": 800, "h": 1000}, ...]
    has_lifestyle_shots: Optional[bool] = None
    has_detail_shots: Optional[bool] = None
    background_type: Optional[str] = None  # "white" | "lifestyle" | "mixed"

    page_title: Optional[str] = None
    description_snippet: Optional[str] = None

    scraped_at: Optional[datetime] = None
    scrape_error: Optional[str] = None
