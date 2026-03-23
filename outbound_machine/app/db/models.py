"""
SQLAlchemy ORM models. All tables are defined here.
Column design follows the lead packet spec, with supporting tables
for products, images, audit findings, screenshots, and outbound assets.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ReviewStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    needs_edit = "needs_edit"


class OutboundStatus(str, enum.Enum):
    queued = "queued"
    sent = "sent"
    replied = "replied"
    uncontacted = "uncontacted"


class SkuRange(str, enum.Enum):
    under_20 = "under_20"
    r20_50 = "20_50"
    r50_100 = "50_100"
    r100_200 = "100_200"
    r200_plus = "200_plus"
    unknown = "unknown"


# ---------------------------------------------------------------------------
# Candidates — raw input from CSV/ingestion
# ---------------------------------------------------------------------------

class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True)
    brand_name = Column(String(255), nullable=False)
    domain = Column(String(255), nullable=False, unique=True)
    source = Column(String(255), nullable=True)
    vertical = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    # Discovery metadata (populated by automated AU store discovery)
    discovery_source = Column(String(100), nullable=True)    # "duckduckgo_search" | "manual" | etc.
    discovery_query = Column(String(500), nullable=True)     # search query that surfaced this domain
    discovery_vertical = Column(String(100), nullable=True)  # vertical the query belonged to
    discovered_at = Column(DateTime(timezone=True), nullable=True)

    # AU detection results
    country_guess = Column(String(10), nullable=True)        # "AU" | "AU?" | "unknown"
    au_confidence = Column(Float, nullable=True)             # 0.0–1.0
    au_signals = Column(JSON, default=list)                  # list of triggered signal codes

    # Relationship to lead (1:1, created after detection)
    lead = relationship("Lead", back_populates="candidate", uselist=False)


# ---------------------------------------------------------------------------
# Leads — enriched, scored, personalised records
# ---------------------------------------------------------------------------

class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False, unique=True)

    # Basic info (denormalised from candidate for convenience)
    brand_name = Column(String(255), nullable=False)
    domain = Column(String(255), nullable=False)
    source = Column(String(255), nullable=True)
    vertical = Column(String(100), nullable=True)

    # Discovery + AU detection (denormalised from Candidate for easy querying/export)
    discovery_source = Column(String(100), nullable=True)
    discovery_query = Column(String(500), nullable=True)
    discovery_vertical = Column(String(100), nullable=True)
    discovered_at = Column(DateTime(timezone=True), nullable=True)
    country_guess = Column(String(10), nullable=True)
    au_confidence = Column(Float, nullable=True)
    au_signals = Column(JSON, default=list)

    # Shopify detection
    shopify_detected = Column(Boolean, nullable=True)
    shopify_confidence = Column(Float, nullable=True)
    shopify_evidence = Column(JSON, default=list)  # list of signal strings

    # SKU estimation
    estimated_sku_range = Column(String(50), nullable=True)  # SkuRange value
    sku_estimation_notes = Column(Text, nullable=True)

    # Product sampling
    product_sample_count = Column(Integer, default=0)

    # Screenshot paths (relative to SCREENSHOTS_DIR)
    homepage_screenshot_path = Column(String(500), nullable=True)
    collection_screenshot_path = Column(String(500), nullable=True)

    # Audit summary (structured)
    imagery_audit_summary = Column(Text, nullable=True)
    audit_findings = Column(JSON, default=list)  # list of AuditFinding dicts

    # Commercial pain
    commercial_pain_hypothesis = Column(Text, nullable=True)

    # Scoring
    lead_score = Column(Float, nullable=True)
    lead_segment = Column(String(5), nullable=True)  # A/B/C/D
    score_breakdown = Column(JSON, default=dict)

    # Mock opportunity
    mock_opportunity = Column(Boolean, nullable=True)
    mock_opportunity_reason = Column(Text, nullable=True)

    # Contact info (populated when available)
    contact_email = Column(String(255), nullable=True)
    contact_name = Column(String(255), nullable=True)
    contact_linkedin = Column(String(500), nullable=True)
    contact_instagram = Column(String(500), nullable=True)
    contact_source = Column(String(100), nullable=True)

    # Generated outbound assets
    personalised_email_subject = Column(Text, nullable=True)
    personalised_email_body = Column(Text, nullable=True)
    loom_script = Column(Text, nullable=True)

    # Workflow state
    review_status = Column(
        SAEnum(ReviewStatus, name="review_status_enum"),
        default=ReviewStatus.pending,
        nullable=False,
    )
    reviewer_notes = Column(Text, nullable=True)
    outbound_status = Column(
        SAEnum(OutboundStatus, name="outbound_status_enum"),
        default=OutboundStatus.uncontacted,
        nullable=False,
    )

    # CRM sync
    crm_synced = Column(Boolean, default=False)
    crm_record_id = Column(String(255), nullable=True)
    crm_synced_at = Column(DateTime(timezone=True), nullable=True)

    # Outreach tracking
    call_booked = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    candidate = relationship("Candidate", back_populates="lead")
    products = relationship("ProductSample", back_populates="lead", cascade="all, delete-orphan")
    screenshots = relationship("Screenshot", back_populates="lead", cascade="all, delete-orphan")
    activities = relationship(
        "LeadActivity", back_populates="lead",
        cascade="all, delete-orphan", order_by="LeadActivity.created_at",
    )


# ---------------------------------------------------------------------------
# Product samples — sampled PDPs per lead
# ---------------------------------------------------------------------------

class ProductSample(Base):
    __tablename__ = "product_samples"

    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)

    url = Column(String(1000), nullable=False)
    product_title = Column(String(500), nullable=True)
    category = Column(String(255), nullable=True)
    breadcrumb = Column(String(500), nullable=True)

    # Image data
    image_urls = Column(JSON, default=list)         # list of URLs
    image_count = Column(Integer, default=0)
    alt_texts = Column(JSON, default=list)          # list of alt text strings
    thumbnail_count = Column(Integer, default=0)

    # Variant info
    variant_count = Column(Integer, default=0)
    variant_options = Column(JSON, default=list)    # e.g. ["Color", "Size"]

    # Image quality signals
    aspect_ratios = Column(JSON, default=list)      # e.g. ["1:1", "4:3"]
    image_dimensions = Column(JSON, default=list)   # list of {w, h} dicts
    has_lifestyle_shots = Column(Boolean, nullable=True)
    has_detail_shots = Column(Boolean, nullable=True)
    background_type = Column(String(50), nullable=True)  # "white", "lifestyle", "mixed"

    # Page metadata
    page_title = Column(String(500), nullable=True)
    description_snippet = Column(Text, nullable=True)

    scraped_at = Column(DateTime(timezone=True), nullable=True)
    scrape_error = Column(Text, nullable=True)

    lead = relationship("Lead", back_populates="products")

    __table_args__ = (UniqueConstraint("lead_id", "url", name="uq_lead_product_url"),)


# ---------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------

class Screenshot(Base):
    __tablename__ = "screenshots"

    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)

    page_type = Column(String(50), nullable=False)   # "homepage", "collection", "product"
    url = Column(String(1000), nullable=False)
    file_path = Column(String(500), nullable=True)   # relative path
    file_size_bytes = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=True)
    capture_error = Column(Text, nullable=True)

    lead = relationship("Lead", back_populates="screenshots")


# ---------------------------------------------------------------------------
# Pipeline runs — one record per outbound run-daily-au-pipeline execution
# ---------------------------------------------------------------------------

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True)
    run_type = Column(String(50), default="manual")   # "manual" | "daily_au" | "scheduled"
    status = Column(String(20), default="running")    # "running" | "completed" | "failed"
    started_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)

    leads_discovered = Column(Integer, default=0)
    leads_qualified = Column(Integer, default=0)
    leads_processed = Column(Integer, default=0)
    leads_a_tier = Column(Integer, default=0)
    leads_b_tier = Column(Integer, default=0)
    leads_c_tier = Column(Integer, default=0)
    leads_d_tier = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    notes = Column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Lead activities — notes, status changes, email events, call booked
# ---------------------------------------------------------------------------

class LeadActivity(Base):
    __tablename__ = "lead_activities"

    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)
    activity_type = Column(String(50), nullable=False)
    # types: note | status_change | email_sent | replied | call_booked | approved | rejected
    content = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    created_by = Column(String(100), default="system")

    lead = relationship("Lead", back_populates="activities")
