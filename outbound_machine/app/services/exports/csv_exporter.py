"""
CSV export service.

Exports lead data to CSV for:
1. Review queue — all pending leads with audit findings and generated copy
2. Approved leads — approved leads ready for outbound, CRM import, or Google Sheets

Both exports use a consistent, readable column layout.
Google Sheets-friendly: UTF-8 BOM, no exotic characters.
"""
import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config.settings import settings
from app.db.models import Lead, ReviewStatus
from app.schemas.lead import LeadPacket, LeadSummary

logger = logging.getLogger(__name__)

# --- Review queue columns ---
REVIEW_COLUMNS = [
    "id", "brand_name", "domain", "vertical", "source",
    "shopify_detected", "shopify_confidence", "estimated_sku_range",
    "product_sample_count", "lead_score", "lead_segment", "mock_opportunity",
    "imagery_audit_summary", "top_findings",
    "commercial_pain_hypothesis",
    "personalised_email_subject", "personalised_email_body", "loom_script",
    "review_status", "reviewer_notes",
    "contact_email", "contact_name",
    "created_at",
]

# --- Approved leads export columns ---
APPROVED_COLUMNS = [
    "id", "brand_name", "domain", "vertical",
    "shopify_detected", "estimated_sku_range",
    "lead_score", "lead_segment", "mock_opportunity",
    "commercial_pain_hypothesis",
    "personalised_email_subject", "personalised_email_body", "loom_script",
    "contact_email", "contact_name", "contact_linkedin",
    "outbound_status", "created_at",
]


def export_review_queue(
    leads: list[Lead],
    output_path: Optional[Path] = None,
) -> Path:
    """
    Export all leads (regardless of review status) for human review.
    Returns the path to the written CSV.
    """
    if output_path is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = settings.exports_dir / f"review_queue_{ts}.csv"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_lead_to_review_row(lead) for lead in leads]
    _write_csv(output_path, REVIEW_COLUMNS, rows)
    logger.info("Review queue exported: %s (%d leads)", output_path, len(rows))
    return output_path


def export_approved_leads(
    leads: list[Lead],
    output_path: Optional[Path] = None,
) -> Path:
    """
    Export only approved leads for outbound.
    Returns the path to the written CSV.
    """
    approved = [l for l in leads if l.review_status == ReviewStatus.approved]
    if output_path is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = settings.exports_dir / f"approved_leads_{ts}.csv"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_lead_to_approved_row(lead) for lead in approved]
    _write_csv(output_path, APPROVED_COLUMNS, rows)
    logger.info("Approved leads exported: %s (%d leads)", output_path, len(rows))
    return output_path


def export_lead_packets(
    packets: list[LeadPacket],
    output_path: Optional[Path] = None,
) -> Path:
    """Export LeadPacket objects directly (no DB session needed)."""
    if output_path is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = settings.exports_dir / f"lead_packets_{ts}.csv"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_packet_to_row(p) for p in packets]
    _write_csv(output_path, REVIEW_COLUMNS, rows)
    logger.info("Lead packets exported: %s (%d)", output_path, len(rows))
    return output_path


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------

def _lead_to_review_row(lead: Lead) -> dict:
    # Summarise top findings
    findings = lead.audit_findings or []
    top = "; ".join(
        f"{f.get('code', '')} ({f.get('severity', '')})"
        for f in findings[:3]
    ) if findings else ""

    return {
        "id": lead.id,
        "brand_name": lead.brand_name,
        "domain": lead.domain,
        "vertical": lead.vertical or "",
        "source": lead.source or "",
        "shopify_detected": lead.shopify_detected,
        "shopify_confidence": lead.shopify_confidence,
        "estimated_sku_range": lead.estimated_sku_range or "",
        "product_sample_count": lead.product_sample_count or 0,
        "lead_score": lead.lead_score,
        "lead_segment": lead.lead_segment or "",
        "mock_opportunity": lead.mock_opportunity,
        "imagery_audit_summary": (lead.imagery_audit_summary or "").replace("\n", " "),
        "top_findings": top,
        "commercial_pain_hypothesis": (lead.commercial_pain_hypothesis or "").replace("\n", " "),
        "personalised_email_subject": lead.personalised_email_subject or "",
        "personalised_email_body": (lead.personalised_email_body or "").replace("\n", "\\n"),
        "loom_script": (lead.loom_script or "").replace("\n", "\\n"),
        "review_status": lead.review_status.value if hasattr(lead.review_status, "value") else str(lead.review_status),
        "reviewer_notes": lead.reviewer_notes or "",
        "contact_email": lead.contact_email or "",
        "contact_name": lead.contact_name or "",
        "created_at": lead.created_at.isoformat() if lead.created_at else "",
    }


def _lead_to_approved_row(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "brand_name": lead.brand_name,
        "domain": lead.domain,
        "vertical": lead.vertical or "",
        "shopify_detected": lead.shopify_detected,
        "estimated_sku_range": lead.estimated_sku_range or "",
        "lead_score": lead.lead_score,
        "lead_segment": lead.lead_segment or "",
        "mock_opportunity": lead.mock_opportunity,
        "commercial_pain_hypothesis": (lead.commercial_pain_hypothesis or "").replace("\n", " "),
        "personalised_email_subject": lead.personalised_email_subject or "",
        "personalised_email_body": (lead.personalised_email_body or "").replace("\n", "\\n"),
        "loom_script": (lead.loom_script or "").replace("\n", "\\n"),
        "contact_email": lead.contact_email or "",
        "contact_name": lead.contact_name or "",
        "contact_linkedin": lead.contact_linkedin or "",
        "outbound_status": lead.outbound_status.value if hasattr(lead.outbound_status, "value") else str(lead.outbound_status),
        "created_at": lead.created_at.isoformat() if lead.created_at else "",
    }


def _packet_to_row(p: LeadPacket) -> dict:
    top = "; ".join(
        f"{f.code} ({f.severity.value})"
        for f in (p.audit_findings or [])[:3]
    ) if p.audit_findings else ""

    return {
        "id": p.id,
        "brand_name": p.brand_name,
        "domain": p.domain,
        "vertical": p.vertical or "",
        "source": p.source or "",
        "shopify_detected": p.shopify_detected,
        "shopify_confidence": p.shopify_confidence,
        "estimated_sku_range": p.estimated_sku_range or "",
        "product_sample_count": p.product_sample_count,
        "lead_score": p.lead_score,
        "lead_segment": p.lead_segment or "",
        "mock_opportunity": p.mock_opportunity,
        "imagery_audit_summary": (p.imagery_audit_summary or "").replace("\n", " "),
        "top_findings": top,
        "commercial_pain_hypothesis": (p.commercial_pain_hypothesis or "").replace("\n", " "),
        "personalised_email_subject": p.personalised_email_subject or "",
        "personalised_email_body": (p.personalised_email_body or "").replace("\n", "\\n"),
        "loom_script": (p.loom_script or "").replace("\n", "\\n"),
        "review_status": p.review_status,
        "reviewer_notes": p.reviewer_notes or "",
        "contact_email": p.contact_email or "",
        "contact_name": p.contact_name or "",
        "created_at": p.created_at.isoformat() if p.created_at else "",
    }


def _write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    """Write rows to CSV with UTF-8 BOM (Google Sheets compatible)."""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=columns,
            extrasaction="ignore",
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        writer.writerows(rows)
