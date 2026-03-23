from fastapi import APIRouter, Request, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_db
from app.api.templates import templates
from app.db.models import Lead, LeadActivity

router = APIRouter()


@router.get("/leads")
def leads_list(
    request: Request,
    db: Session = Depends(get_db),
    q: Optional[str] = None,
    segment: Optional[str] = None,
    score_min: Optional[float] = None,
    score_max: Optional[float] = None,
    vertical: Optional[str] = None,
    sku_range: Optional[str] = None,
    au_min: Optional[float] = None,
    mock: Optional[str] = None,
    review_status: Optional[str] = None,
    outbound_status: Optional[str] = None,
    sort: str = "score",
):
    query = db.query(Lead)

    if q:
        query = query.filter(
            or_(Lead.brand_name.ilike(f"%{q}%"), Lead.domain.ilike(f"%{q}%"))
        )
    if segment:
        query = query.filter(Lead.lead_segment == segment.upper())
    if score_min is not None:
        query = query.filter(Lead.lead_score >= score_min)
    if score_max is not None:
        query = query.filter(Lead.lead_score <= score_max)
    if vertical:
        query = query.filter(Lead.vertical == vertical)
    if sku_range:
        query = query.filter(Lead.estimated_sku_range == sku_range)
    if au_min is not None:
        query = query.filter(Lead.au_confidence >= au_min)
    if mock == "yes":
        query = query.filter(Lead.mock_opportunity == True)
    elif mock == "no":
        query = query.filter(Lead.mock_opportunity == False)
    if review_status:
        query = query.filter(Lead.review_status == review_status)
    if outbound_status:
        query = query.filter(Lead.outbound_status == outbound_status)

    if sort == "score":
        query = query.order_by(Lead.lead_score.desc().nulls_last())
    elif sort == "created":
        query = query.order_by(Lead.created_at.desc())
    elif sort == "brand":
        query = query.order_by(Lead.brand_name)

    leads = query.limit(200).all()

    # Distinct verticals for filter dropdown
    verticals = sorted(set(
        l.vertical for l in db.query(Lead.vertical).distinct() if l.vertical
    ))

    return templates.TemplateResponse(request, "web/leads_list.html", {
        "active": "leads",
        "leads": leads,
        "total": len(leads),
        "verticals": verticals,
        "filters": {
            "q": q or "",
            "segment": segment or "",
            "score_min": score_min or "",
            "score_max": score_max or "",
            "vertical": vertical or "",
            "sku_range": sku_range or "",
            "au_min": au_min or "",
            "mock": mock or "",
            "review_status": review_status or "",
            "outbound_status": outbound_status or "",
            "sort": sort,
        },
    })


@router.get("/leads/{lead_id}")
def lead_detail(request: Request, lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return templates.TemplateResponse(request, "web/404.html", {}, status_code=404)

    activities = (
        db.query(LeadActivity)
        .filter(LeadActivity.lead_id == lead_id)
        .order_by(LeadActivity.created_at.desc())
        .all()
    )

    findings = []
    if lead.audit_findings:
        findings = lead.audit_findings  # list of dicts

    return templates.TemplateResponse(request, "web/lead_detail.html", {
        "active": "leads",
        "lead": lead,
        "findings": findings,
        "activities": activities,
    })


@router.get("/api/leads/{lead_id}/preview")
def lead_preview(request: Request, lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    findings = lead.audit_findings or [] if lead else []
    return templates.TemplateResponse(request, "web/partials/lead_preview.html", {
        "lead": lead,
        "findings": findings[:4],
    })
