"""Schemas for generated outbound assets."""
from typing import Optional
from pydantic import BaseModel


class EmailDraft(BaseModel):
    subject: str
    body: str
    template_used: str = "generic"
    llm_polished: bool = False


class LoomScript(BaseModel):
    script: str
    estimated_duration_seconds: int = 75
    template_used: str = "generic"
    llm_polished: bool = False


class OutboundAssets(BaseModel):
    """All generated outbound materials for a lead."""
    pain_hypothesis: str
    email: EmailDraft
    loom: LoomScript
