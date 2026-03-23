"""
Stage 9 & 10: Lead scoring + mock opportunity flag.

Additive points model (scoring_method: additive in config).
Each signal contributes explicit points — no averaging, no compression.
Severity is differentiated: HIGH findings worth 2x MEDIUM findings.
mock_opportunity MUST be determined before calling score_lead and passed
in ScoreInput — it is the largest single commercial signal (10pts).

Max possible: ICP(25) + Imagery(45) + Commercial(20) + Outreach(10) = 100.
"""
import logging
from pathlib import Path
from typing import Optional

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


def determine_mock_opportunity(score_input: ScoreInput) -> tuple[bool, str]:
    """
    Determine whether there is a clear mock/demo opportunity.
    Call this BEFORE score_lead and pass result into ScoreInput.mock_opportunity.

    Criteria:
    - Vertical is in our target set (or ICP signals suggest it)
    - At least one meaningful imagery weakness exists
    - Not a trivially tiny or unqualified store
    """
    vertical_ok = bool(
        score_input.vertical and
        score_input.vertical.lower().strip() in MOCK_SUITABLE_VERTICALS
    )

    has_weakness = any([
        score_input.has_low_image_count,
        score_input.has_inconsistent_counts,
        score_input.has_missing_detail_shots,
        score_input.has_weak_variant_representation,
        score_input.has_inconsistent_backgrounds,
    ])

    # Require at least one finding and a plausible ICP fit
    sku_ok = score_input.estimated_sku_range not in ("under_20", "unknown")

    if vertical_ok and has_weakness and sku_ok:
        if score_input.has_weak_variant_representation:
            reason = "variant imagery gap — can demo per-colour/style renders"
        elif score_input.has_low_image_count:
            reason = "low image count — can demo expanding coverage with AI"
        elif score_input.has_missing_detail_shots:
            reason = "missing detail shots — can demo close-up/texture renders"
        elif score_input.has_inconsistent_backgrounds:
            reason = "inconsistent backgrounds — can demo clean consistent packshots"
        else:
            reason = "clear imagery improvement potential"
        return True, reason
    elif not vertical_ok:
        return False, "Vertical not in primary target set"
    elif not has_weakness:
        return False, "No significant imagery weakness found — limited demo angle"
    else:
        return False, "Store too small or unqualified for meaningful mock"


def score_lead(
    score_input: ScoreInput,
    config: Optional[dict] = None,
) -> ScoreResult:
    """
    Compute an additive lead score from a ScoreInput.
    mock_opportunity must already be set on score_input before calling this.
    Returns ScoreResult with total, segment, breakdown, and reasoning notes.
    """
    if config is None:
        config = load_scoring_config()

    breakdown: dict[str, float] = {}
    reasoning: list[str] = []
    total = 0.0

    cats = config.get("categories", {})

    # --- ICP Fit (max 25) ---
    icp_pts = _score_icp_fit(score_input, cats.get("icp_fit", {}), reasoning)
    breakdown["icp_fit"] = round(icp_pts, 2)
    total += icp_pts

    # --- Imagery Opportunity (max 45) ---
    img_pts = _score_imagery_opportunity(score_input, cats.get("imagery_opportunity", {}), reasoning)
    breakdown["imagery_opportunity"] = round(img_pts, 2)
    total += img_pts

    # --- Commercial Potential (max 20) ---
    comm_pts = _score_commercial_potential(score_input, cats.get("commercial_potential", {}), reasoning)
    breakdown["commercial_potential"] = round(comm_pts, 2)
    total += comm_pts

    # --- Outreach Viability (max 10) ---
    out_pts = _score_outreach_viability(score_input, cats.get("outreach_viability", {}), reasoning)
    breakdown["outreach_viability"] = round(out_pts, 2)
    total += out_pts

    total = round(min(total, 100.0), 1)
    segment = _assign_segment(total, config)

    logger.info("Score: %.1f → %s | breakdown: %s", total, segment, breakdown)

    return ScoreResult(
        total_score=total,
        segment=segment,
        breakdown=breakdown,
        reasoning=reasoning,
    )


# ---------------------------------------------------------------------------
# Category scoring — all additive, no averaging
# ---------------------------------------------------------------------------

def _score_icp_fit(inp: ScoreInput, cfg: dict, reasoning: list[str]) -> float:
    """Additive ICP fit. Max from config (default 25)."""
    inputs = cfg.get("inputs", {})
    max_pts = cfg.get("max", 25)
    pts = 0.0

    # Shopify signal
    shopify_cfg = inputs.get("shopify_confirmed", {})
    if inp.shopify_confidence >= shopify_cfg.get("threshold", 0.7):
        p = shopify_cfg.get("points", 8)
        pts += p
        reasoning.append(f"Shopify confirmed ({inp.shopify_confidence:.2f}) +{p}pts")
    elif inp.shopify_confidence >= shopify_cfg.get("partial_threshold", 0.4):
        p = shopify_cfg.get("partial_points", 4)
        pts += p
        reasoning.append(f"Shopify probable ({inp.shopify_confidence:.2f}) +{p}pts")
    else:
        reasoning.append(f"Shopify unconfirmed ({inp.shopify_confidence:.2f}) +0pts")

    # SKU fit
    sku_cfg = inputs.get("sku_fit", {}).get("buckets", {})
    sku_key = (inp.estimated_sku_range or "unknown").replace("-", "_")
    sku_pts = sku_cfg.get(sku_key, 1)
    pts += sku_pts
    reasoning.append(f"SKU range={inp.estimated_sku_range} +{sku_pts}pts")

    # Vertical fit
    vert_cfg = inputs.get("preferred_vertical", {})
    vertical = (inp.vertical or "").lower().strip()
    preferred = set(v.lower() for v in vert_cfg.get("preferred", []))
    if vertical in preferred:
        vp = vert_cfg.get("points", 7)
        pts += vp
        reasoning.append(f"Preferred vertical ({vertical}) +{vp}pts")
    else:
        vp = vert_cfg.get("other_points", 2)
        pts += vp
        reasoning.append(f"Non-preferred vertical ({vertical or 'unknown'}) +{vp}pts")

    # Contact bonus
    if inp.contact_available or inp.has_contact_info:
        cp = inputs.get("contact_available", {}).get("points", 2)
        pts += cp
        reasoning.append(f"Contact info available +{cp}pts")

    return min(pts, max_pts)


def _score_imagery_opportunity(inp: ScoreInput, cfg: dict, reasoning: list[str]) -> float:
    """
    Additive severity-based imagery scoring.
    HIGH findings worth 2x MEDIUM. Breadth bonus for 3+ distinct findings.
    """
    max_pts = cfg.get("max", 45)
    per_sev = cfg.get("per_severity", {"high": 12, "medium": 6, "low": 2})
    breadth_cfg = cfg.get("breadth_bonus", {"min_findings": 3, "points": 5})

    pts = 0.0

    high_pts = per_sev.get("high", 12) * inp.high_finding_count
    med_pts = per_sev.get("medium", 6) * inp.medium_finding_count
    low_pts = per_sev.get("low", 2) * inp.low_finding_count

    if inp.high_finding_count:
        pts += high_pts
        reasoning.append(
            f"{inp.high_finding_count} HIGH finding(s) "
            f"({per_sev.get('high', 12)}pts each) +{high_pts}pts"
        )
    if inp.medium_finding_count:
        pts += med_pts
        reasoning.append(
            f"{inp.medium_finding_count} MEDIUM finding(s) "
            f"({per_sev.get('medium', 6)}pts each) +{med_pts}pts"
        )
    if inp.low_finding_count:
        pts += low_pts
        reasoning.append(f"{inp.low_finding_count} LOW finding(s) +{low_pts}pts")

    # Breadth bonus: multiple distinct issues compound the pain
    if inp.total_finding_count >= breadth_cfg.get("min_findings", 3):
        bp = breadth_cfg.get("points", 5)
        pts += bp
        reasoning.append(
            f"Breadth bonus ({inp.total_finding_count} distinct findings) +{bp}pts"
        )

    if pts == 0:
        reasoning.append("No imagery findings — no opportunity signal")

    return min(pts, max_pts)


def _score_commercial_potential(inp: ScoreInput, cfg: dict, reasoning: list[str]) -> float:
    """Additive commercial signals. Mock opportunity is the anchor point."""
    inputs = cfg.get("inputs", {})
    max_pts = cfg.get("max", 20)
    pts = 0.0

    # Mock opportunity — must be pre-computed and set on ScoreInput
    if inp.mock_opportunity:
        mp = inputs.get("mock_opportunity", {}).get("points", 10)
        pts += mp
        reasoning.append(f"Mock opportunity confirmed +{mp}pts")
    else:
        reasoning.append("No mock opportunity — commercial signal weak")

    # Variant complexity: high variant count = more imagery work = bigger pain
    vc_cfg = inputs.get("variant_complexity", {})
    if inp.avg_variant_count > vc_cfg.get("high_threshold", 4):
        vp = vc_cfg.get("high_points", 5)
        pts += vp
        reasoning.append(f"High variant complexity (avg {inp.avg_variant_count:.1f}) +{vp}pts")
    elif inp.avg_variant_count > vc_cfg.get("medium_threshold", 2):
        vp = vc_cfg.get("medium_points", 3)
        pts += vp
        reasoning.append(f"Moderate variant complexity (avg {inp.avg_variant_count:.1f}) +{vp}pts")

    # Catalogue depth risk: thin imagery at scale = operational bottleneck pain
    if inp.has_catalogue_depth_risk:
        dp = inputs.get("catalogue_depth_risk", {}).get("points", 5)
        pts += dp
        reasoning.append(f"Catalogue depth risk (scale bottleneck) +{dp}pts")

    return min(pts, max_pts)


def _score_outreach_viability(inp: ScoreInput, cfg: dict, reasoning: list[str]) -> float:
    """Additive outreach signals. No minimum floor — if no signals, 0."""
    inputs = cfg.get("inputs", {})
    max_pts = cfg.get("max", 10)
    pts = 0.0

    if inp.has_contact_info or inp.contact_available:
        cp = inputs.get("has_contact_info", {}).get("points", 7)
        pts += cp
        reasoning.append(f"Contact info found +{cp}pts")

    if inp.social_presence:
        sp = inputs.get("social_presence", {}).get("points", 3)
        pts += sp
        reasoning.append(f"Social presence +{sp}pts")

    if pts == 0:
        reasoning.append("No outreach signals found")

    return min(pts, max_pts)


def _assign_segment(score: float, config: dict) -> str:
    thresholds = config.get("segments", {"A": 80, "B": 60, "C": 40})
    if score >= thresholds.get("A", 80):
        return "A"
    if score >= thresholds.get("B", 60):
        return "B"
    if score >= thresholds.get("C", 40):
        return "C"
    return "D"
