import yaml
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from pathlib import Path
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.templates import templates
from app.config.settings import settings

router = APIRouter()


def _load_au_cfg() -> dict:
    p = settings.au_discovery_config_path
    if p.exists():
        with open(p) as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_au_cfg(cfg: dict) -> None:
    with open(settings.au_discovery_config_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)


@router.get("/settings")
def settings_page(request: Request, saved: bool = False):
    au_cfg = _load_au_cfg()
    disc = au_cfg.get("discovery", {})
    qual = au_cfg.get("qualification", {})

    return templates.TemplateResponse(request, "web/settings.html", {
        "active": "settings",
        "saved": saved,
        "disc": disc,
        "qual": qual,
        "app_settings": {
            "database_url": settings.database_url,
            "rate_limit_delay": settings.rate_limit_delay,
            "enable_llm": settings.enable_llm,
            "enable_screenshots": settings.enable_screenshots,
            "llm_model": settings.llm_model,
        },
    })


@router.post("/settings/discovery")
async def save_discovery_settings(
    request: Request,
    daily_limit: int = Form(100),
    limit_per_query: int = Form(12),
    search_delay: float = Form(3.5),
    au_threshold: float = Form(0.55),
    shopify_threshold: float = Form(0.50),
):
    au_cfg = _load_au_cfg()
    au_cfg.setdefault("discovery", {}).update({
        "daily_limit": daily_limit,
        "limit_per_query": limit_per_query,
        "search_delay_seconds": search_delay,
    })
    au_cfg.setdefault("qualification", {}).update({
        "au_confidence_threshold": au_threshold,
        "shopify_confidence_threshold": shopify_threshold,
    })
    _save_au_cfg(au_cfg)
    return RedirectResponse(url="/settings?saved=1", status_code=303)
