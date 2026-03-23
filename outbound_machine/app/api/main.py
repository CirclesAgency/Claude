"""
Prodigi Outbound — FastAPI web dashboard.

Run with:  outbound serve
Or:        uvicorn app.api.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.db.database import init_db
from app.api.routes import dashboard, leads, review, outreach, runs, settings_route, actions

app = FastAPI(title="Prodigi Outbound", docs_url=None, redoc_url=None)

# Ensure tables exist (safe to call multiple times)
init_db()

app.include_router(dashboard.router)
app.include_router(leads.router)
app.include_router(review.router)
app.include_router(outreach.router)
app.include_router(runs.router)
app.include_router(settings_route.router)
app.include_router(actions.router)


@app.get("/")
def root():
    return RedirectResponse(url="/dashboard")
