from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.templates import templates
from app.db.models import PipelineRun

router = APIRouter()


@router.get("/runs")
def runs_list(request: Request, db: Session = Depends(get_db)):
    runs = db.query(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(50).all()
    return templates.TemplateResponse(request, "web/runs.html", {
        "active": "runs",
        "runs": runs,
    })


@router.get("/api/runs/{run_id}/detail")
def run_detail_partial(request: Request, run_id: int, db: Session = Depends(get_db)):
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    return templates.TemplateResponse(request, "web/partials/run_detail.html", {
        "run": run,
    })
