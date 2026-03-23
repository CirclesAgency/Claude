from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.templates import templates
from app.db.models import Lead, ReviewStatus, OutboundStatus

router = APIRouter()


@router.get("/outreach")
def outreach(request: Request, tab: str = "ready", db: Session = Depends(get_db)):
    ready = (
        db.query(Lead)
        .filter(
            Lead.review_status == ReviewStatus.approved,
            Lead.outbound_status == OutboundStatus.uncontacted,
            Lead.personalised_email_subject.isnot(None),
        )
        .order_by(Lead.lead_score.desc())
        .all()
    )
    sent = (
        db.query(Lead)
        .filter(Lead.outbound_status == OutboundStatus.sent)
        .order_by(Lead.updated_at.desc())
        .all()
    )
    replied = (
        db.query(Lead)
        .filter(Lead.outbound_status == OutboundStatus.replied)
        .order_by(Lead.updated_at.desc())
        .all()
    )
    # Follow-up due = sent more than 3 days ago, no reply
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    follow_up = (
        db.query(Lead)
        .filter(
            Lead.outbound_status == OutboundStatus.sent,
            Lead.updated_at < cutoff,
        )
        .order_by(Lead.updated_at.asc())
        .all()
    )
    booked = db.query(Lead).filter(Lead.call_booked == True).order_by(Lead.updated_at.desc()).all()

    tabs = {
        "ready": ready,
        "sent": sent,
        "replied": replied,
        "follow_up": follow_up,
        "booked": booked,
    }
    counts = {k: len(v) for k, v in tabs.items()}

    return templates.TemplateResponse(request, "web/outreach.html", {
        "active": "outreach",
        "tab": tab,
        "tabs": tabs,
        "counts": counts,
    })
