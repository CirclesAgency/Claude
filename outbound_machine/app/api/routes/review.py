from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.templates import templates
from app.db.models import Lead, ReviewStatus

router = APIRouter()


@router.get("/review")
def review_queue(request: Request, db: Session = Depends(get_db)):
    new_leads = (
        db.query(Lead)
        .filter(Lead.review_status == ReviewStatus.pending, Lead.lead_score.isnot(None))
        .order_by(Lead.lead_score.desc())
        .all()
    )
    reviewing = (
        db.query(Lead)
        .filter(Lead.review_status == ReviewStatus.needs_edit)
        .order_by(Lead.lead_score.desc())
        .all()
    )
    approved = (
        db.query(Lead)
        .filter(Lead.review_status == ReviewStatus.approved)
        .order_by(Lead.lead_score.desc())
        .all()
    )

    return templates.TemplateResponse(request, "web/review.html", {
        "active": "review",
        "new_leads": new_leads,
        "reviewing": reviewing,
        "approved": approved,
    })
