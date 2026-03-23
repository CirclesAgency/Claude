"""
Pipeline orchestrator.

Wires all stages together for a single lead, and provides a batch runner
for processing multiple leads. Each stage is independently runnable.

Stages:
  1. Shopify detection
  2. SKU estimation
  3. Product sampling
  4. Product scraping
  5. Screenshot capture (optional)
  6. Imagery audit
  7. Lead scoring + mock opportunity
  8. Pain hypothesis
  9. Personalisation (email + Loom)
 10. Persist to DB
"""
import logging
import statistics
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import Lead, ProductSample, Screenshot, ReviewStatus
from app.schemas.audit import AuditResult
from app.schemas.scoring import ScoreInput
from app.services.detection.shopify_detector import detect_shopify
from app.services.sku_estimation.sku_estimator import estimate_skus
from app.services.sampling.product_sampler import sample_products
from app.services.scraping.product_scraper import scrape_product
from app.services.screenshots.screenshot_service import capture_screenshots
from app.services.audit.audit_engine import audit_imagery
from app.services.scoring.scoring_engine import score_lead, determine_mock_opportunity, load_scoring_config  # noqa: E501
from app.services.personalisation.pain_generator import generate_pain_hypothesis
from app.services.personalisation.email_generator import generate_email
from app.services.personalisation.loom_generator import generate_loom_script
from app.utils.domain import base_url

logger = logging.getLogger(__name__)


def run_detection_stage(lead: Lead, session: Session) -> Lead:
    """Stage 1: Shopify detection. Updates lead in place."""
    result = detect_shopify(lead.domain)
    lead.shopify_detected = result.shopify_detected
    lead.shopify_confidence = result.confidence
    lead.shopify_evidence = result.evidence
    session.flush()
    return lead


def run_sku_stage(lead: Lead, session: Session) -> Lead:
    """Stage 2: SKU estimation. Updates lead in place."""
    result = estimate_skus(lead.domain)
    lead.estimated_sku_range = result.bucket
    lead.sku_estimation_notes = result.notes
    session.flush()
    return lead


def run_sampling_stage(lead: Lead, session: Session) -> Lead:
    """Stage 3: Product sampling. Persists product URLs to DB."""
    result = sample_products(lead.domain)

    # Persist sampled URLs
    existing_urls = {p.url for p in lead.products}
    new_count = 0
    for url in result.product_urls:
        if url not in existing_urls:
            session.add(ProductSample(lead_id=lead.id, url=url))
            new_count += 1

    lead.product_sample_count = len(result.product_urls)

    # Store first collection URL on the lead for screenshots
    if result.collection_urls and not lead.collection_screenshot_path:
        # Just save the URL for now — screenshot stage will use it
        pass

    session.flush()
    logger.info("Sampled %d products for %s", new_count, lead.domain)
    return lead


def run_scraping_stage(lead: Lead, session: Session) -> Lead:
    """Stage 4: Product page scraping. Updates ProductSample records."""
    products = session.query(ProductSample).filter(ProductSample.lead_id == lead.id).all()
    if not products:
        logger.warning("No product samples to scrape for %s", lead.domain)
        return lead

    for ps in products:
        if ps.scraped_at:
            continue  # Skip already scraped
        result = scrape_product(ps.url)
        ps.product_title = result.product_title
        ps.category = result.category
        ps.breadcrumb = result.breadcrumb
        ps.image_urls = result.image_urls
        ps.image_count = result.image_count
        ps.alt_texts = result.alt_texts
        ps.thumbnail_count = result.thumbnail_count
        ps.variant_count = result.variant_count
        ps.variant_options = result.variant_options
        ps.aspect_ratios = result.aspect_ratios
        ps.image_dimensions = result.image_dimensions
        ps.has_lifestyle_shots = result.has_lifestyle_shots
        ps.has_detail_shots = result.has_detail_shots
        ps.background_type = result.background_type
        ps.page_title = result.page_title
        ps.description_snippet = result.description_snippet
        ps.scraped_at = result.scraped_at
        ps.scrape_error = result.scrape_error

    session.flush()
    return lead


def run_screenshot_stage(lead: Lead, session: Session, collection_url: Optional[str] = None) -> Lead:
    """Stage 5: Screenshot capture. Creates Screenshot records."""
    product_samples = (
        session.query(ProductSample)
        .filter(ProductSample.lead_id == lead.id)
        .limit(3)
        .all()
    )
    product_urls = [ps.url for ps in product_samples]

    batch = capture_screenshots(
        domain=lead.domain,
        homepage_url=base_url(lead.domain),
        collection_url=collection_url,
        product_urls=product_urls,
    )

    if batch.homepage:
        r = batch.homepage
        session.add(Screenshot(
            lead_id=lead.id,
            page_type="homepage",
            url=r.url,
            file_path=r.file_path,
            file_size_bytes=r.file_size_bytes,
            captured_at=r.captured_at,
            capture_error=r.capture_error,
        ))
        if r.file_path:
            lead.homepage_screenshot_path = r.file_path

    if batch.collection:
        r = batch.collection
        session.add(Screenshot(
            lead_id=lead.id,
            page_type="collection",
            url=r.url,
            file_path=r.file_path,
            file_size_bytes=r.file_size_bytes,
            captured_at=r.captured_at,
            capture_error=r.capture_error,
        ))
        if r.file_path:
            lead.collection_screenshot_path = r.file_path

    for r in batch.products:
        session.add(Screenshot(
            lead_id=lead.id,
            page_type="product",
            url=r.url,
            file_path=r.file_path,
            file_size_bytes=r.file_size_bytes,
            captured_at=r.captured_at,
            capture_error=r.capture_error,
        ))

    session.flush()
    return lead


def run_audit_stage(lead: Lead, session: Session) -> tuple[Lead, AuditResult]:
    """Stage 6: Imagery audit. Updates lead with findings and summary."""
    from app.schemas.product import ProductSampleData

    products_db = (
        session.query(ProductSample)
        .filter(ProductSample.lead_id == lead.id)
        .all()
    )

    products = [
        ProductSampleData(
            url=ps.url,
            image_urls=ps.image_urls or [],
            image_count=ps.image_count or 0,
            alt_texts=ps.alt_texts or [],
            variant_count=ps.variant_count or 0,
            aspect_ratios=ps.aspect_ratios or [],
            has_lifestyle_shots=ps.has_lifestyle_shots,
            has_detail_shots=ps.has_detail_shots,
            background_type=ps.background_type,
            scrape_error=ps.scrape_error,
        )
        for ps in products_db
    ]

    audit = audit_imagery(products)

    lead.imagery_audit_summary = audit.summary
    lead.audit_findings = [f.model_dump() for f in audit.findings]
    session.flush()
    return lead, audit


def run_scoring_stage(lead: Lead, audit: AuditResult, session: Session) -> Lead:
    """Stage 7: Scoring + mock opportunity."""
    products_db = (
        session.query(ProductSample)
        .filter(ProductSample.lead_id == lead.id)
        .all()
    )
    avg_variants = (
        statistics.mean([p.variant_count for p in products_db if p.variant_count])
        if products_db else 0.0
    )

    # Build score input (without mock yet — need to determine it first)
    score_input = ScoreInput.from_audit_result(
        audit,
        shopify_confidence=lead.shopify_confidence or 0.0,
        estimated_sku_range=lead.estimated_sku_range or "unknown",
        vertical=lead.vertical,
        contact_available=bool(lead.contact_email),
        has_contact_info=bool(lead.contact_email),
        avg_variant_count=avg_variants,
    )

    # Mock opportunity must be determined BEFORE scoring — it is a scored signal
    is_mock, mock_reason = determine_mock_opportunity(score_input)
    score_input.mock_opportunity = is_mock
    lead.mock_opportunity = is_mock
    lead.mock_opportunity_reason = mock_reason

    config = load_scoring_config()
    score_result = score_lead(score_input, config)

    lead.lead_score = score_result.total_score
    lead.lead_segment = score_result.segment
    lead.score_breakdown = score_result.breakdown

    session.flush()
    return lead


def run_personalisation_stage(lead: Lead, audit: AuditResult, session: Session) -> Lead:
    """Stage 8+9: Pain hypothesis + email + Loom script generation."""
    pain = generate_pain_hypothesis(audit, lead.brand_name, lead.vertical)
    lead.commercial_pain_hypothesis = pain

    email = generate_email(
        brand_name=lead.brand_name,
        domain=lead.domain,
        audit=audit,
        vertical=lead.vertical,
        contact_name=lead.contact_name,
        polish_with_llm=True,
    )
    lead.personalised_email_subject = email.subject
    lead.personalised_email_body = email.body

    loom = generate_loom_script(
        brand_name=lead.brand_name,
        domain=lead.domain,
        audit=audit,
        vertical=lead.vertical,
        polish_with_llm=True,
    )
    lead.loom_script = loom.script
    session.flush()
    return lead


def run_full_pipeline(lead: Lead, session: Session) -> Lead:
    """
    Run all pipeline stages for a single lead.
    Continues through failures at each stage (errors are logged, not raised).
    """
    logger.info("=== Pipeline: %s (%s) ===", lead.brand_name, lead.domain)

    try:
        lead = run_detection_stage(lead, session)
    except Exception as e:
        logger.error("[Detection] Failed for %s: %s", lead.domain, e)

    try:
        lead = run_sku_stage(lead, session)
    except Exception as e:
        logger.error("[SKU] Failed for %s: %s", lead.domain, e)

    try:
        lead = run_sampling_stage(lead, session)
    except Exception as e:
        logger.error("[Sampling] Failed for %s: %s", lead.domain, e)

    try:
        lead = run_scraping_stage(lead, session)
    except Exception as e:
        logger.error("[Scraping] Failed for %s: %s", lead.domain, e)

    try:
        lead = run_screenshot_stage(lead, session)
    except Exception as e:
        logger.error("[Screenshots] Failed for %s: %s", lead.domain, e)

    audit = None
    try:
        lead, audit = run_audit_stage(lead, session)
    except Exception as e:
        logger.error("[Audit] Failed for %s: %s", lead.domain, e)
        from app.schemas.audit import AuditResult
        audit = AuditResult()

    try:
        lead = run_scoring_stage(lead, audit, session)
    except Exception as e:
        logger.error("[Scoring] Failed for %s: %s", lead.domain, e)

    try:
        lead = run_personalisation_stage(lead, audit, session)
    except Exception as e:
        logger.error("[Personalisation] Failed for %s: %s", lead.domain, e)

    session.commit()
    logger.info(
        "Pipeline complete: %s — score=%.1f segment=%s",
        lead.domain,
        lead.lead_score or 0,
        lead.lead_segment or "?",
    )
    return lead


def run_pipeline_for_all_leads(session: Session, limit: Optional[int] = None) -> list[Lead]:
    """Run the full pipeline for all unprocessed leads."""
    query = session.query(Lead).filter(Lead.shopify_detected.is_(None))
    if limit:
        query = query.limit(limit)
    leads = query.all()

    logger.info("Running pipeline for %d leads", len(leads))
    results = []
    for lead in leads:
        try:
            result = run_full_pipeline(lead, session)
            results.append(result)
        except Exception as e:
            logger.error("Pipeline error for %s: %s", lead.domain, e)

    return results
