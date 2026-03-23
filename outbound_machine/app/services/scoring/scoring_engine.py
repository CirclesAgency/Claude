"""
Stage 9 & 10: Lead scoring + mock opportunity flag.

Reads scoring weights from scoring_config.yaml.
Produces a 0–100 score and A/B/C/D segment.

Design: fully deterministic, config-driven, no AI calls.
All scoring logic is transparent and auditable.
"""
import logging
from pathlib import Path
from typing import Any, Optional

import yaml

from app.config.settings import settings
from app.schemas.scoring import ScoreInput, ScoreResult

logger = logging.getLogger(__name__)

PREFERRED_VERTICALS = {
    "apparel", "accessories", "beauty", "footwear", "homewares",
    "home", "jewelry", "jewellery", "skincare", "cosmetics",
}

MOCK_SUITABLE_VERTICALS = PREFERRED_VERTICALS


def load_scoring_config(path: Optional[Path] = None) -> dict:
    config_path = path or settings.scoring_config_path
    if not Path(config_path).exists():
        logger.warning("Scoring config not found at %s — using defaults", config_path)
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def score_lead(
    score_input: ScoreInput,
    config: Optional[dict] = None,
) -> ScoreResult:
    """
    Compute a weighted lead score from a ScoreInput.
    Returns ScoreResult with total, segment, breakdown, and reasoning notes.
    """
    if config is None:
        config = load_scoring_config()

    breakdown: dict[str, float] = {}
    reasoning: list[str] = []
    total = 0.0

    cats = config.get("categories", {})

    # --- ICP Fit (max 30) ---
    icp_weight = cats.get("icp_fit", {}).get("weight", 30)
    icp_score = _score_icp_fit(score_input, cats.get("icp_fit", {}), reasoning)
    icp_points = icp_score * icp_weight
    breakdown["icp_fit"] = round(icp_points, 2)
    total += icp_points

    # --- Imagery Opportunity (max 40) ---
    img_weight = cats.get("imagery_opportunity", {}).get("weight", 40)
    img_score = _score_imagery_opportunity(score_input, cats.get("imagery_opportunity", {}), reasoning)
    img_points = img_score * img_weight
    breakdown["imagery_opportunity"] = round(img_points, 2)
    total += img_points

    # --- Commercial Potential (max 20) ---
    comm_weight = cats.get("commercial_potential", {}).get("weight", 20)
    comm_score = _score_commercial_potential(score_input, cats.get("commercial_potential", {}), reasoning)
    comm_points = comm_score * comm_weight
    breakdown["commercial_potential"] = round(comm_points, 2)
    total += comm_points

    # --- Outreach Viability (max 10) ---
    out_weight = cats.get("outreach_viability", {}).get("weight", 10)
    out_score = _score_outreach_viability(score_input, cats.get("outreach_viability", {}), reasoning)
    out_points = out_score * out_weight
    breakdown["outreach_viability"] = round(out_points, 2)
    total += out_points

    total = round(min(total, 100.0), 1)
    segment = _assign_segment(total, config)

    logger.info("Score: %.1f → %s | breakdown: %s", total, segment, breakdown)

    return ScoreResult(
        total_score=total,
        segment=segment,
        breakdown=breakdown,
        reasoning=reasoning,
    )


def determine_mock_opportunity(
    score_input: ScoreInput,
    score_result: ScoreResult,
) -> tuple[bool, str]:
    """
    Determine whether there is a clear mock/demo opportunity for this lead.
    Returns (is_opportunity: bool, reason: str).

    Mock is suitable if:
    - Vertical is in our target set
    - There's at least one meaningful imagery weakness
    - Score is not so low the brand is out of ICP
    """
    vertical_ok = (
        score_input.vertical and
        score_input.vertical.lower().strip() in MOCK_SUITABLE_VERTICALS
    ) or score_result.breakdown.get("icp_fit", 0) >= 10

    has_weakness = any([
        score_input.has_low_image_count,
        score_input.has_inconsistent_counts,
        score_input.has_missing_detail_shots,
        score_input.has_weak_variant_representation,
        score_input.has_inconsistent_backgrounds,
    ])

    score_ok = score_result.total_score >= 40

    if vertical_ok and has_weakness and score_ok:
        reasons = []
        if score_input.has_weak_variant_representation:
            reasons.append("variant imagery gap — can demo per-colour/style renders")
        elif score_input.has_low_image_count:
            reasons.append("low image count — can demo expanding coverage with AI")
        elif score_input.has_missing_detail_shots:
            reasons.append("missing detail shots — can demo close-up/texture renders")
        elif score_input.has_inconsistent_backgrounds:
            reasons.append("inconsistent backgrounds — can demo clean consistent packshots")
        else:
            reasons.append("clear imagery improvement potential")
        return True, "; ".join(reasons)
    elif not vertical_ok:
        return False, "Vertical not in primary target set — mock less compelling"
    elif not has_weakness:
        return False, "No significant imagery weakness found — limited demo angle"
    else:
        return False, "Lead score too low — likely out of ICP"


# ---------------------------------------------------------------------------
# Category scoring helpers
# ---------------------------------------------------------------------------

def _score_icp_fit(inp: ScoreInput, cfg: dict, reasoning: list[str]) -> float:
    """Returns 0.0–1.0 representing ICP fit."""
    inputs = cfg.get("inputs", {})
    scores: list[float] = []

    # Shopify confirmed
    shopify_cfg = inputs.get("shopify_confirmed", {})
    threshold = shopify_cfg.get("threshold", 0.7)
    if inp.shopify_confidence >= threshold:
        scores.append(shopify_cfg.get("score", 1.0))
        reasoning.append(f"Shopify confirmed (confidence={inp.shopify_confidence:.2f})")
    elif inp.shopify_confidence > 0:
        scores.append(0.4)
        reasoning.append(f"Shopify probable (confidence={inp.shopify_confidence:.2f})")

    # SKU fit
    sku_cfg = inputs.get("sku_fit", {}).get("buckets", {})
    sku_key = inp.estimated_sku_range
    # Map DB enum values to config keys
    sku_key_clean = sku_key.replace("-", "_") if sku_key else "unknown"
    sku_score = sku_cfg.get(sku_key_clean, 0.3)
    scores.append(sku_score)
    reasoning.append(f"SKU range={sku_key} (score={sku_score:.2f})")

    # Preferred vertical
    vert_cfg = inputs.get("preferred_vertical", {})
    vertical = (inp.vertical or "").lower().strip()
    preferred = set(v.lower() for v in vert_cfg.get("preferred", []))
    if vertical in preferred:
        scores.append(vert_cfg.get("preferred_score", 1.0))
        reasoning.append(f"Preferred vertical: {vertical}")
    else:
        scores.append(vert_cfg.get("other_score", 0.4))
        if vertical:
            reasoning.append(f"Non-preferred vertical: {vertical}")

    # Contact available
    if inp.contact_available:
        scores.append(inputs.get("contact_available", {}).get("score", 0.3))
        reasoning.append("Contact info available")

    return _weighted_mean(scores)


def _score_imagery_opportunity(inp: ScoreInput, cfg: dict, reasoning: list[str]) -> float:
    inputs = cfg.get("inputs", {})
    scores: list[float] = []

    flag_map = {
        "low_image_count": (inp.has_low_image_count, "Low image count per product"),
        "inconsistent_image_count": (inp.has_inconsistent_counts, "Inconsistent image counts"),
        "missing_detail_shots": (inp.has_missing_detail_shots, "Missing detail shots"),
        "missing_front_back": (inp.has_missing_front_back, "Missing front/back coverage"),
        "inconsistent_backgrounds": (inp.has_inconsistent_backgrounds, "Inconsistent backgrounds"),
        "inconsistent_framing": (inp.has_inconsistent_framing, "Inconsistent framing"),
        "mixed_aspect_ratios": (inp.has_mixed_aspect_ratios, "Mixed aspect ratios"),
        "weak_variant_representation": (
            inp.has_weak_variant_representation, "Weak variant imagery"
        ),
    }

    for key, (flag, label) in flag_map.items():
        if flag:
            s = inputs.get(key, {}).get("score", 0.5)
            scores.append(s)
            reasoning.append(f"Imagery issue: {label} (+{s:.2f})")

    return _weighted_mean(scores) if scores else 0.0


def _score_commercial_potential(inp: ScoreInput, cfg: dict, reasoning: list[str]) -> float:
    inputs = cfg.get("inputs", {})
    scores: list[float] = []

    if inp.mock_opportunity:
        scores.append(inputs.get("mock_opportunity", {}).get("score", 1.0))
        reasoning.append("Mock/demo opportunity identified")

    if inp.avg_variant_count > inputs.get("variant_complexity", {}).get("threshold", 3):
        scores.append(inputs.get("variant_complexity", {}).get("score", 0.8))
        reasoning.append(f"High variant complexity (avg {inp.avg_variant_count:.0f} variants)")

    if inp.has_catalogue_depth_risk:
        scores.append(inputs.get("catalogue_depth_risk", {}).get("score", 0.7))
        reasoning.append("Catalogue depth risk — scale imagery bottleneck")

    return _weighted_mean(scores) if scores else 0.0


def _score_outreach_viability(inp: ScoreInput, cfg: dict, reasoning: list[str]) -> float:
    inputs = cfg.get("inputs", {})
    scores: list[float] = []

    if inp.has_contact_info:
        scores.append(inputs.get("has_contact_info", {}).get("score", 1.0))
        reasoning.append("Contact info found")

    if inp.social_presence:
        scores.append(inputs.get("social_presence", {}).get("score", 0.5))
        reasoning.append("Social presence detected")

    return _weighted_mean(scores) if scores else 0.2  # small base score


def _weighted_mean(scores: list[float]) -> float:
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _assign_segment(score: float, config: dict) -> str:
    thresholds = config.get("segments", {"A": 80, "B": 65, "C": 50})
    if score >= thresholds.get("A", 80):
        return "A"
    if score >= thresholds.get("B", 65):
        return "B"
    if score >= thresholds.get("C", 50):
        return "C"
    return "D"
