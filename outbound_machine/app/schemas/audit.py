"""Schemas for imagery audit findings."""
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class AuditSeverity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AuditFinding(BaseModel):
    """A single, machine-readable audit finding."""
    code: str                        # e.g. "LOW_IMAGE_COUNT"
    severity: AuditSeverity
    title: str                       # Short human-readable label
    detail: str                      # Specific observation grounded in data
    affected_products: list[str] = [] # product URLs affected
    metric: Optional[float] = None   # numeric value behind finding (e.g. avg 1.8 images)


class AuditResult(BaseModel):
    """
    Full audit result for a lead.
    Contains both machine-readable findings and a concise human summary.
    """
    findings: list[AuditFinding] = []
    summary: str = ""                # 2-4 sentence plain English summary
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0

    # Derived flags used by scoring engine
    has_low_image_count: bool = False
    has_inconsistent_counts: bool = False
    has_missing_detail_shots: bool = False
    has_missing_front_back: bool = False
    has_inconsistent_backgrounds: bool = False
    has_inconsistent_framing: bool = False
    has_mixed_aspect_ratios: bool = False
    has_weak_variant_representation: bool = False
    has_catalogue_depth_risk: bool = False

    def compute_counts(self) -> None:
        self.high_count = sum(1 for f in self.findings if f.severity == AuditSeverity.HIGH)
        self.medium_count = sum(1 for f in self.findings if f.severity == AuditSeverity.MEDIUM)
        self.low_count = sum(1 for f in self.findings if f.severity == AuditSeverity.LOW)
