"""
Stage 7: Imagery audit engine.

Rule-based analysis of product imagery across a set of scraped product samples.
Each rule is deterministic, measurable, and translates directly into a
commercially meaningful pain statement.

Design principle: never output vague opinions. Every finding has:
- a specific code
- a measured metric (where applicable)
- a clear, factual detail sentence
- affected product URLs

Findings are then used by the pain hypothesis generator and scoring engine.
"""
import logging
import statistics
from typing import Optional

from app.schemas.audit import AuditFinding, AuditResult, AuditSeverity
from app.schemas.product import ProductSampleData

logger = logging.getLogger(__name__)

# --- Thresholds (all adjustable) ---
MIN_IMAGES_PER_PRODUCT = 3       # below this is a finding
GOOD_IMAGES_PER_PRODUCT = 6      # above this is healthy
CV_INCONSISTENCY_THRESHOLD = 0.4  # coefficient of variation (std/mean)
MIXED_RATIO_THRESHOLD = 2         # more than N unique aspect ratios = finding
DETAIL_SHOT_MIN_COVERAGE = 0.4    # fraction of products expected to have detail shots
LOW_VARIANT_THRESHOLD = 2         # variant count above this = complex variant set
MISSING_FRONT_BACK_THRESHOLD = 2  # need at least 2 imgs to suggest front+back coverage


def audit_imagery(products: list[ProductSampleData]) -> AuditResult:
    """
    Run all audit rules against a list of scraped products.
    Returns an AuditResult with findings, flags, and a summary.
    """
    result = AuditResult()

    if not products:
        result.summary = "No product samples available for imagery audit."
        return result

    # Filter to successfully scraped products
    valid = [p for p in products if not p.scrape_error and p.image_count >= 0]
    if not valid:
        result.summary = "All product samples failed to scrape — no imagery data available."
        return result

    logger.info("Auditing imagery for %d products", len(valid))

    # Run each rule
    _rule_low_image_count(valid, result)
    _rule_inconsistent_image_count(valid, result)
    _rule_missing_detail_shots(valid, result)
    _rule_missing_front_back(valid, result)
    _rule_inconsistent_backgrounds(valid, result)
    _rule_mixed_aspect_ratios(valid, result)
    _rule_weak_variant_representation(valid, result)
    _rule_catalogue_depth(valid, result)
    _rule_missing_alt_text(valid, result)

    result.compute_counts()
    result.summary = _build_summary(result, valid)

    logger.info(
        "Audit complete: %d findings (H=%d M=%d L=%d)",
        len(result.findings), result.high_count, result.medium_count, result.low_count,
    )
    return result


# ---------------------------------------------------------------------------
# Audit rules
# ---------------------------------------------------------------------------

def _rule_low_image_count(products: list[ProductSampleData], result: AuditResult) -> None:
    """Flag products with fewer than MIN_IMAGES_PER_PRODUCT images."""
    low_products = [p for p in products if p.image_count < MIN_IMAGES_PER_PRODUCT]
    all_counts = [p.image_count for p in products]
    avg = statistics.mean(all_counts) if all_counts else 0

    if avg < MIN_IMAGES_PER_PRODUCT:
        severity = AuditSeverity.HIGH
        result.has_low_image_count = True
    elif len(low_products) / len(products) > 0.3:
        severity = AuditSeverity.MEDIUM
        result.has_low_image_count = True
    else:
        return  # healthy

    result.findings.append(AuditFinding(
        code="LOW_IMAGE_COUNT",
        severity=severity,
        title="Low images per product",
        detail=(
            f"Average {avg:.1f} images per product across {len(products)} sampled SKUs. "
            f"{len(low_products)} product(s) have fewer than {MIN_IMAGES_PER_PRODUCT} images. "
            f"Minimum recommended for e-commerce conversion is {MIN_IMAGES_PER_PRODUCT}–{GOOD_IMAGES_PER_PRODUCT}."
        ),
        affected_products=[p.url for p in low_products],
        metric=round(avg, 2),
    ))


def _rule_inconsistent_image_count(
    products: list[ProductSampleData], result: AuditResult
) -> None:
    """Flag high variation in image count across products (catalogue inconsistency)."""
    counts = [p.image_count for p in products]
    if len(counts) < 3:
        return

    mean = statistics.mean(counts)
    stdev = statistics.stdev(counts) if len(counts) > 1 else 0
    cv = stdev / mean if mean > 0 else 0

    if cv < CV_INCONSISTENCY_THRESHOLD:
        return

    result.has_inconsistent_counts = True
    min_c, max_c = min(counts), max(counts)
    result.findings.append(AuditFinding(
        code="INCONSISTENT_IMAGE_COUNT",
        severity=AuditSeverity.MEDIUM,
        title="Inconsistent image count across catalogue",
        detail=(
            f"Image count ranges from {min_c} to {max_c} across sampled products "
            f"(CV={cv:.2f}, mean={mean:.1f}). This suggests inconsistent imagery "
            "production — some products are well-photographed, others under-resourced."
        ),
        metric=round(cv, 3),
    ))


def _rule_missing_detail_shots(
    products: list[ProductSampleData], result: AuditResult
) -> None:
    """Flag products with no detail/close-up shots."""
    no_detail = [p for p in products if p.has_detail_shots is False]
    coverage = 1 - (len(no_detail) / len(products)) if products else 0

    if coverage >= DETAIL_SHOT_MIN_COVERAGE:
        return

    result.has_missing_detail_shots = True
    result.findings.append(AuditFinding(
        code="MISSING_DETAIL_SHOTS",
        severity=AuditSeverity.MEDIUM,
        title="Limited product detail coverage",
        detail=(
            f"Only {coverage:.0%} of sampled products have identifiable detail/close-up shots. "
            "Detail shots (texture, material, craft) are a key driver of purchase confidence "
            "and return reduction for apparel and accessories brands."
        ),
        affected_products=[p.url for p in no_detail],
        metric=round(coverage, 3),
    ))


def _rule_missing_front_back(
    products: list[ProductSampleData], result: AuditResult
) -> None:
    """
    Flag products with < 2 images — unlikely to have both front and back/side coverage.
    Relevant for apparel, footwear, accessories.
    """
    limited = [p for p in products if p.image_count < MISSING_FRONT_BACK_THRESHOLD]
    if not limited:
        return

    fraction = len(limited) / len(products)
    if fraction < 0.2:
        return

    result.has_missing_front_back = True
    result.findings.append(AuditFinding(
        code="MISSING_FRONT_BACK",
        severity=AuditSeverity.MEDIUM,
        title="Insufficient angle coverage",
        detail=(
            f"{len(limited)} of {len(products)} sampled products have fewer than "
            f"{MISSING_FRONT_BACK_THRESHOLD} images, making front+back/side coverage "
            "unlikely. Multi-angle coverage is a purchase-confidence standard for "
            "apparel, footwear, and accessories."
        ),
        affected_products=[p.url for p in limited],
        metric=round(fraction, 3),
    ))


def _rule_inconsistent_backgrounds(
    products: list[ProductSampleData], result: AuditResult
) -> None:
    """Flag mixed background types (white/studio vs. lifestyle) across the catalogue."""
    bg_types = [p.background_type for p in products if p.background_type and p.background_type != "unknown"]
    if len(bg_types) < 3:
        return

    mixed = [b for b in bg_types if b == "mixed"]
    white = [b for b in bg_types if b == "white"]
    lifestyle = [b for b in bg_types if b == "lifestyle"]

    # Inconsistency: significant presence of both white and lifestyle
    if len(white) >= 2 and len(lifestyle) >= 2:
        result.has_inconsistent_backgrounds = True
        result.findings.append(AuditFinding(
            code="INCONSISTENT_BACKGROUNDS",
            severity=AuditSeverity.MEDIUM,
            title="Mixed background styles across catalogue",
            detail=(
                f"Products show mixed background treatment: {len(white)} with clean/white "
                f"backgrounds, {len(lifestyle)} with lifestyle/scene backgrounds. "
                "Visual inconsistency across a catalogue reduces perceived brand polish "
                "and can harm store conversion."
            ),
            metric=float(len(mixed + white + lifestyle)),
        ))
    elif len(mixed) / len(bg_types) > 0.5 if bg_types else False:
        result.has_inconsistent_backgrounds = True
        result.findings.append(AuditFinding(
            code="INCONSISTENT_BACKGROUNDS",
            severity=AuditSeverity.LOW,
            title="Mixed background styles within products",
            detail=(
                f"{len(mixed)} products appear to mix background styles within a single "
                "PDP. This can signal mismatched imagery from different shoots."
            ),
        ))


def _rule_mixed_aspect_ratios(
    products: list[ProductSampleData], result: AuditResult
) -> None:
    """Flag stores with multiple different aspect ratios across their imagery."""
    all_ratios: set[str] = set()
    for p in products:
        for r in p.aspect_ratios:
            if r != "unknown":
                all_ratios.add(r)

    if len(all_ratios) <= MIXED_RATIO_THRESHOLD:
        return

    result.has_mixed_aspect_ratios = True
    result.findings.append(AuditFinding(
        code="MIXED_ASPECT_RATIOS",
        severity=AuditSeverity.LOW,
        title="Mixed image aspect ratios",
        detail=(
            f"Detected {len(all_ratios)} distinct aspect ratios ({', '.join(sorted(all_ratios))}) "
            "across sampled products. Mixed ratios in a store grid create visual choppiness "
            "and suggest imagery was produced in multiple batches without a consistent spec."
        ),
        metric=float(len(all_ratios)),
    ))


def _rule_weak_variant_representation(
    products: list[ProductSampleData], result: AuditResult
) -> None:
    """
    Flag products with many variants but few images — variants likely lack visual coverage.
    """
    problematic = [
        p for p in products
        if p.variant_count > LOW_VARIANT_THRESHOLD and p.image_count < p.variant_count
    ]
    if not problematic:
        return

    result.has_weak_variant_representation = True
    avg_variants = statistics.mean([p.variant_count for p in problematic])
    result.findings.append(AuditFinding(
        code="WEAK_VARIANT_REPRESENTATION",
        severity=AuditSeverity.HIGH,
        title="Variants under-represented in imagery",
        detail=(
            f"{len(problematic)} product(s) have more variants than images "
            f"(avg {avg_variants:.0f} variants, images insufficient for per-variant coverage). "
            "Shoppers selecting colours or styles cannot visually confirm their choice — "
            "a key conversion friction point."
        ),
        affected_products=[p.url for p in problematic],
        metric=round(avg_variants, 1),
    ))


def _rule_catalogue_depth(products: list[ProductSampleData], result: AuditResult) -> None:
    """
    Flag if overall imagery depth is low relative to catalogue size.
    Uses image count as proxy for production investment per SKU.
    """
    counts = [p.image_count for p in products]
    if not counts:
        return

    avg = statistics.mean(counts)
    # If average imagery is weak AND we have a decent sample
    if avg < 4 and len(products) >= 5:
        result.has_catalogue_depth_risk = True
        result.findings.append(AuditFinding(
            code="LOW_CATALOGUE_DEPTH",
            severity=AuditSeverity.MEDIUM,
            title="Low catalogue imagery depth",
            detail=(
                f"Across {len(products)} sampled products, average imagery depth is {avg:.1f} images/SKU. "
                "For a brand in the $1M–$20M revenue range, this suggests a studio bottleneck "
                "or cost constraint limiting how much imagery can be produced at scale."
            ),
            metric=round(avg, 2),
        ))


def _rule_missing_alt_text(products: list[ProductSampleData], result: AuditResult) -> None:
    """Low severity: note if alt text coverage is poor (SEO + accessibility signal)."""
    products_with_images = [p for p in products if p.image_count > 0]
    if not products_with_images:
        return

    missing_alt = [
        p for p in products_with_images
        if not p.alt_texts or all(not a.strip() for a in p.alt_texts)
    ]
    fraction = len(missing_alt) / len(products_with_images)

    if fraction < 0.5:
        return

    result.findings.append(AuditFinding(
        code="MISSING_ALT_TEXT",
        severity=AuditSeverity.INFO,
        title="Poor image alt text coverage",
        detail=(
            f"{fraction:.0%} of sampled products have no meaningful image alt text. "
            "This is a minor SEO and accessibility signal — not a primary pain point, "
            "but relevant in an AI-generated imagery workflow where assets are auto-tagged."
        ),
        affected_products=[p.url for p in missing_alt],
        metric=round(fraction, 3),
    ))


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------

def _build_summary(result: AuditResult, products: list[ProductSampleData]) -> str:
    """
    Generate a concise, factual summary of the audit.
    Should be 2–4 sentences, grounded in data.
    """
    counts = [p.image_count for p in products]
    avg_imgs = statistics.mean(counts) if counts else 0
    n = len(products)

    if not result.findings:
        return (
            f"Imagery audit of {n} sampled products found no significant issues. "
            f"Average {avg_imgs:.1f} images per product. This brand's imagery appears well-resourced."
        )

    high_titles = [f.title for f in result.findings if f.severity == AuditSeverity.HIGH]
    med_titles = [f.title for f in result.findings if f.severity == AuditSeverity.MEDIUM]

    parts = [
        f"Imagery audit across {n} sampled products (avg {avg_imgs:.1f} images/SKU) "
        f"identified {len(result.findings)} finding(s)."
    ]

    if high_titles:
        parts.append(f"High severity: {'; '.join(high_titles)}.")
    if med_titles:
        parts.append(f"Medium severity: {'; '.join(med_titles)}.")

    if result.has_weak_variant_representation:
        parts.append(
            "Variant imagery coverage is a primary commercial pain — "
            "shoppers cannot confirm colour/style choices visually."
        )
    elif result.has_low_image_count:
        parts.append(
            "Low per-product image counts suggest either a studio bottleneck "
            "or production cost constraint limiting imagery at scale."
        )

    return " ".join(parts)
