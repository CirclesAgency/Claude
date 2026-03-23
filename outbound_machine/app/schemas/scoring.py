"""Schemas for lead scoring."""
from typing import Optional
from pydantic import BaseModel
from app.schemas.audit import AuditResult


class ScoreInput(BaseModel):
    """All inputs needed to compute a lead score."""
    shopify_confidence: float = 0.0
    estimated_sku_range: str = "unknown"
    vertical: Optional[str] = None
    contact_available: bool = False
    has_contact_info: bool = False

    # Imagery audit flags
    has_low_image_count: bool = False
    has_inconsistent_counts: bool = False
    has_missing_detail_shots: bool = False
    has_missing_front_back: bool = False
    has_inconsistent_backgrounds: bool = False
    has_inconsistent_framing: bool = False
    has_mixed_aspect_ratios: bool = False
    has_weak_variant_representation: bool = False
    has_catalogue_depth_risk: bool = False

    # Commercial
    mock_opportunity: bool = False
    avg_variant_count: float = 0.0

    # Outreach
    social_presence: bool = False

    @classmethod
    def from_audit_result(cls, audit: AuditResult, **kwargs) -> "ScoreInput":
        return cls(
            has_low_image_count=audit.has_low_image_count,
            has_inconsistent_counts=audit.has_inconsistent_counts,
            has_missing_detail_shots=audit.has_missing_detail_shots,
            has_missing_front_back=audit.has_missing_front_back,
            has_inconsistent_backgrounds=audit.has_inconsistent_backgrounds,
            has_inconsistent_framing=audit.has_inconsistent_framing,
            has_mixed_aspect_ratios=audit.has_mixed_aspect_ratios,
            has_weak_variant_representation=audit.has_weak_variant_representation,
            has_catalogue_depth_risk=audit.has_catalogue_depth_risk,
            **kwargs,
        )


class ScoreResult(BaseModel):
    """Scored output from the scoring engine."""
    total_score: float
    segment: str                    # A / B / C / D
    breakdown: dict[str, float]     # category → points contribution
    reasoning: list[str] = []       # human-readable scoring notes
