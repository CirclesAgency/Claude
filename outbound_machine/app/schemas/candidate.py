"""Schemas for candidate ingestion."""
from typing import Optional
from pydantic import BaseModel, field_validator
import re


def normalise_domain(domain: str) -> str:
    """Strip scheme, www, trailing slashes, and lowercase."""
    domain = domain.strip().lower()
    domain = re.sub(r"^https?://", "", domain)
    domain = re.sub(r"^www\.", "", domain)
    domain = domain.rstrip("/")
    return domain


class CandidateIn(BaseModel):
    """Input row from CSV or API."""
    brand_name: str
    domain: str
    source: Optional[str] = None
    vertical: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("domain", mode="before")
    @classmethod
    def clean_domain(cls, v):
        return normalise_domain(str(v))

    @field_validator("brand_name", mode="before")
    @classmethod
    def clean_name(cls, v):
        return str(v).strip()

    @field_validator("vertical", mode="before")
    @classmethod
    def clean_vertical(cls, v):
        if v is None:
            return None
        return str(v).strip().lower()


class CandidateRow(CandidateIn):
    """CSV row including optional extra fields we may encounter."""
    contact_email: Optional[str] = None
    contact_name: Optional[str] = None
