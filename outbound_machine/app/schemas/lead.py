"""
Lead packet schema — the canonical output object for each lead.
Mirrors the Lead DB model but is a pure Pydantic object usable
for exports, API responses, and template rendering.
"""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel

from app.schemas.audit import AuditFinding


class LeadPacket(BaseModel):
    """
    Complete, structured lead packet for a single brand.
    This is the central output object of the pipeline.
    """
    id: Optional[int] = None

    # Identity
    brand_name: str
    domain: str
    source: Optional[str] = None
    vertical: Optional[str] = None

    # Shopify detection
    shopify_detected: Optional[bool] = None
    shopify_confidence: Optional[float] = None
    shopify_evidence: list[str] = []

    # SKU estimation
    estimated_sku_range: Optional[str] = None
    sku_estimation_notes: Optional[str] = None

    # Product sampling
    product_sample_urls: list[str] = []
    product_sample_count: int = 0

    # Screenshots
    homepage_screenshot_path: Optional[str] = None
    collection_screenshot_path: Optional[str] = None
    product_screenshot_paths: list[str] = []

    # Audit
    imagery_audit_summary: Optional[str] = None
    audit_findings: list[AuditFinding] = []

    # Commercial pain
    commercial_pain_hypothesis: Optional[str] = None

    # Scoring
    lead_score: Optional[float] = None
    lead_segment: Optional[str] = None
    score_breakdown: dict[str, float] = {}

    # Mock opportunity
    mock_opportunity: Optional[bool] = None
    mock_opportunity_reason: Optional[str] = None

    # Contact
    contact_email: Optional[str] = None
    contact_name: Optional[str] = None
    contact_linkedin: Optional[str] = None
    contact_instagram: Optional[str] = None

    # Generated outbound
    personalised_email_subject: Optional[str] = None
    personalised_email_body: Optional[str] = None
    loom_script: Optional[str] = None

    # Workflow
    review_status: str = "pending"
    reviewer_notes: Optional[str] = None
    outbound_status: str = "uncontacted"

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class LeadSummary(BaseModel):
    """Lightweight summary for list views and review queue exports."""
    id: Optional[int] = None
    brand_name: str
    domain: str
    vertical: Optional[str] = None
    shopify_detected: Optional[bool] = None
    estimated_sku_range: Optional[str] = None
    lead_score: Optional[float] = None
    lead_segment: Optional[str] = None
    mock_opportunity: Optional[bool] = None
    review_status: str = "pending"
    commercial_pain_hypothesis: Optional[str] = None
