from datetime import date, datetime, timezone, timedelta
from fastapi import APIRouter, Request, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.templates import templates
from app.db.models import Lead, LeadActivity, PipelineRun, ReviewStatus, OutboundStatus

router = APIRouter()


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    yesterday = today - timedelta(days=1)

    new_today = db.query(Lead).filter(func.date(Lead.created_at) == today).count()
    qualified_today = db.query(Lead).filter(
        func.date(Lead.created_at) == today,
        Lead.lead_score >= 60,
    ).count()
    a_tier = db.query(Lead).filter(Lead.lead_segment == "A").count()
    sent_today = db.query(Lead).filter(
        Lead.outbound_status == OutboundStatus.sent,
        func.date(Lead.updated_at) == today,
    ).count()
    replies = db.query(Lead).filter(Lead.outbound_status == OutboundStatus.replied).count()
    booked = db.query(Lead).filter(Lead.call_booked == True).count()

    # Segment distribution
    segs = {s: db.query(Lead).filter(Lead.lead_segment == s).count() for s in ["A", "B", "C", "D"]}
    total_scored = sum(segs.values()) or 1

    # Top opportunities (A-tier, uncontacted or queued, mock)
    top_opps = (
        db.query(Lead)
        .filter(Lead.lead_segment == "A", Lead.mock_opportunity == True)
        .order_by(Lead.lead_score.desc())
        .limit(6)
        .all()
    )

    # Queue snapshot
    queue = {
        "pending": db.query(Lead).filter(Lead.review_status == ReviewStatus.pending).count(),
        "reviewing": db.query(Lead).filter(Lead.review_status == ReviewStatus.needs_edit).count(),
        "approved": db.query(Lead).filter(Lead.review_status == ReviewStatus.approved).count(),
    }

    # Recent leads
    recent_leads = (
        db.query(Lead)
        .order_by(Lead.created_at.desc())
        .limit(8)
        .all()
    )

    # Activity feed
    activity_feed = (
        db.query(LeadActivity)
        .order_by(LeadActivity.created_at.desc())
        .limit(12)
        .all()
    )
    # Attach lead brand names to activities
    lead_map = {l.id: l for l in db.query(Lead).filter(
        Lead.id.in_([a.lead_id for a in activity_feed])
    ).all()} if activity_feed else {}

    return templates.TemplateResponse(request, "web/dashboard.html", {
        "active": "dashboard",
        "kpis": {
            "new_today": new_today,
            "qualified_today": qualified_today,
            "a_tier": a_tier,
            "sent_today": sent_today,
            "replies": replies,
            "booked": booked,
        },
        "segs": segs,
        "total_scored": total_scored,
        "top_opps": top_opps,
        "queue": queue,
        "recent_leads": recent_leads,
        "activity_feed": activity_feed,
        "lead_map": lead_map,
    })
