"""
Stage 1: Candidate store ingestion.

Accepts a CSV file of candidate brands, normalises domains, deduplicates,
and persists to the candidates table. Creates corresponding lead records
ready for downstream enrichment.
"""
import csv
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import Candidate, Lead, ReviewStatus, OutboundStatus
from app.schemas.candidate import CandidateRow
from app.utils.domain import normalise_domain, deduplicate_domains

logger = logging.getLogger(__name__)

# Columns we'll look for in input CSVs (case-insensitive, flexible naming)
COLUMN_ALIASES = {
    "brand_name": ["brand_name", "brand", "name", "store_name", "company"],
    "domain": ["domain", "url", "website", "site", "store_url"],
    "source": ["source", "list_source", "origin"],
    "vertical": ["vertical", "category", "niche", "industry"],
    "notes": ["notes", "note", "comments"],
    "contact_email": ["contact_email", "email"],
    "contact_name": ["contact_name", "contact", "founder"],
}


def _map_columns(fieldnames: list[str]) -> dict[str, str]:
    """Map CSV column names to canonical field names."""
    mapping: dict[str, str] = {}
    for canon, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            for fn in fieldnames:
                if fn.strip().lower() == alias:
                    mapping[canon] = fn
                    break
            if canon in mapping:
                break
    return mapping


def ingest_csv(
    csv_path: Path,
    session: Session,
    source_override: Optional[str] = None,
) -> dict:
    """
    Read a CSV of candidate brands and persist them to the DB.

    Returns a summary dict with keys:
        total_rows, ingested, skipped_duplicate, skipped_invalid, errors
    """
    logger.info("Ingesting candidates from: %s", csv_path)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    stats = {
        "total_rows": 0,
        "ingested": 0,
        "skipped_duplicate": 0,
        "skipped_invalid": 0,
        "errors": 0,
    }

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            logger.warning("Empty CSV or missing headers: %s", csv_path)
            return stats

        col_map = _map_columns(list(reader.fieldnames))

        if "domain" not in col_map:
            raise ValueError(
                f"CSV must have a domain/url column. Found: {list(reader.fieldnames)}"
            )
        if "brand_name" not in col_map:
            raise ValueError(
                f"CSV must have a brand_name/name column. Found: {list(reader.fieldnames)}"
            )

        for row in reader:
            stats["total_rows"] += 1
            try:
                raw = {
                    canon: row.get(csv_col, "").strip()
                    for canon, csv_col in col_map.items()
                }

                if not raw.get("domain") or not raw.get("brand_name"):
                    logger.debug("Skipping row with missing domain or name: %s", row)
                    stats["skipped_invalid"] += 1
                    continue

                candidate = CandidateRow(**raw)
                if source_override:
                    candidate.source = source_override

                # Check for existing domain
                existing = (
                    session.query(Candidate)
                    .filter(Candidate.domain == candidate.domain)
                    .first()
                )
                if existing:
                    logger.debug("Duplicate domain skipped: %s", candidate.domain)
                    stats["skipped_duplicate"] += 1
                    continue

                db_candidate = Candidate(
                    brand_name=candidate.brand_name,
                    domain=candidate.domain,
                    source=candidate.source,
                    vertical=candidate.vertical,
                    notes=candidate.notes,
                )
                session.add(db_candidate)
                session.flush()  # Get the ID

                # Create a lead record immediately (starts at pending)
                db_lead = Lead(
                    candidate_id=db_candidate.id,
                    brand_name=candidate.brand_name,
                    domain=candidate.domain,
                    source=candidate.source,
                    vertical=candidate.vertical,
                    contact_email=candidate.contact_email,
                    contact_name=candidate.contact_name,
                    review_status=ReviewStatus.pending,
                    outbound_status=OutboundStatus.uncontacted,
                )
                session.add(db_lead)
                stats["ingested"] += 1
                logger.info("Ingested: %s (%s)", candidate.brand_name, candidate.domain)

            except Exception as e:
                stats["errors"] += 1
                logger.error("Error ingesting row %d: %s — %s", stats["total_rows"], row, e)

    session.commit()
    logger.info(
        "Ingestion complete. Ingested=%d Dupes=%d Invalid=%d Errors=%d",
        stats["ingested"],
        stats["skipped_duplicate"],
        stats["skipped_invalid"],
        stats["errors"],
    )
    return stats


def ingest_list(
    candidates: list[dict],
    session: Session,
) -> dict:
    """Ingest from a list of dicts instead of a CSV. Useful for programmatic use."""
    stats = {"total_rows": 0, "ingested": 0, "skipped_duplicate": 0, "errors": 0}
    for item in candidates:
        stats["total_rows"] += 1
        try:
            candidate = CandidateRow(**item)
            existing = (
                session.query(Candidate)
                .filter(Candidate.domain == candidate.domain)
                .first()
            )
            if existing:
                stats["skipped_duplicate"] += 1
                continue
            db_candidate = Candidate(
                brand_name=candidate.brand_name,
                domain=candidate.domain,
                source=candidate.source,
                vertical=candidate.vertical,
            )
            session.add(db_candidate)
            session.flush()
            db_lead = Lead(
                candidate_id=db_candidate.id,
                brand_name=candidate.brand_name,
                domain=candidate.domain,
                source=candidate.source,
                vertical=candidate.vertical,
            )
            session.add(db_lead)
            stats["ingested"] += 1
        except Exception as e:
            stats["errors"] += 1
            logger.error("Error ingesting item: %s — %s", item, e)
    session.commit()
    return stats
