"""
HTMX action endpoints — small POST handlers that return HTML fragments.
All UI interactions (approve, ignore, mark-sent, add-note, etc.) hit these.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_db
from app.api.templates import templates
from app.db.models import Lead, LeadActivity, ReviewStatus, OutboundStatus

router = APIRouter(prefix="/api")

SEG_COLORS = {"A": "green", "B": "blue", "C": "amber", "D": "red"}


def _seg_badge(seg: Optional[str]) -> str:
    c = SEG_COLORS.get(seg or "", "gray")
    return f'<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-{c}-100 text-{c}-800">{seg or "?"}</span>'


def _status_badge(status: str) -> str:
    colors = {
        "pending": "gray", "approved": "green", "rejected": "red", "needs_edit": "yellow",
    }
    c = colors.get(status, "gray")
    label = status.replace("_", " ").title()
    return f'<span class="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-{c}-100 text-{c}-700">{label}</span>'


# ---------------------------------------------------------------------------
# Review status actions
# ---------------------------------------------------------------------------

@router.post("/leads/{lead_id}/approve")
def approve_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if lead:
        lead.review_status = ReviewStatus.approved
        lead.updated_at = datetime.now(timezone.utc)
        db.add(LeadActivity(lead_id=lead_id, activity_type="approved", content="Marked approved"))
        db.commit()
    return HTMLResponse(_status_badge("approved"))


@router.post("/leads/{lead_id}/reject")
def reject_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if lead:
        lead.review_status = ReviewStatus.rejected
        lead.updated_at = datetime.now(timezone.utc)
        db.add(LeadActivity(lead_id=lead_id, activity_type="rejected", content="Marked rejected"))
        db.commit()
    return HTMLResponse(_status_badge("rejected"))


@router.post("/leads/{lead_id}/needs-review")
def needs_review(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if lead:
        lead.review_status = ReviewStatus.needs_edit
        lead.updated_at = datetime.now(timezone.utc)
        db.commit()
    return HTMLResponse(_status_badge("needs_edit"))


# ---------------------------------------------------------------------------
# Outbound status actions
# ---------------------------------------------------------------------------

@router.post("/leads/{lead_id}/mark-sent")
def mark_sent(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if lead:
        lead.outbound_status = OutboundStatus.sent
        lead.updated_at = datetime.now(timezone.utc)
        db.add(LeadActivity(lead_id=lead_id, activity_type="email_sent", content="Email marked as sent"))
        db.commit()
    label = "Sent"
    return HTMLResponse(
        f'<span class="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700">{label}</span>'
    )


@router.post("/leads/{lead_id}/mark-replied")
def mark_replied(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if lead:
        lead.outbound_status = OutboundStatus.replied
        lead.updated_at = datetime.now(timezone.utc)
        db.add(LeadActivity(lead_id=lead_id, activity_type="replied", content="Reply received"))
        db.commit()
    return HTMLResponse(
        '<span class="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">Replied</span>'
    )


@router.post("/leads/{lead_id}/book-call")
def book_call(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if lead:
        lead.call_booked = True
        lead.updated_at = datetime.now(timezone.utc)
        db.add(LeadActivity(lead_id=lead_id, activity_type="call_booked", content="Call booked"))
        db.commit()
    return HTMLResponse(
        '<span class="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-700">Call Booked ✓</span>'
    )


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

@router.post("/leads/{lead_id}/notes")
def add_note(
    request: Request,
    lead_id: int,
    content: str = Form(...),
    db: Session = Depends(get_db),
):
    activity = LeadActivity(
        lead_id=lead_id,
        activity_type="note",
        content=content,
        created_by="user",
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)

    ts = activity.created_at.strftime("%d %b %H:%M") if activity.created_at else ""
    return HTMLResponse(f"""
    <div class="flex gap-2 py-2 border-b border-gray-100 last:border-0">
      <span class="w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-xs flex-shrink-0 mt-0.5">N</span>
      <div class="flex-1 min-w-0">
        <p class="text-xs text-gray-900">{content}</p>
        <p class="text-xs text-gray-400 mt-0.5">{ts}</p>
      </div>
    </div>
    """)
