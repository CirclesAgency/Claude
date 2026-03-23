"""
CLI entrypoints for the outbound machine.
All commands are available via: python -m app.cli.commands <command>
Or via the installed script: outbound <command>

Commands:
  init-db              Initialise database tables
  ingest-candidates    Import brands from a CSV file
  detect-shopify       Run Shopify detection on all undetected leads
  estimate-skus        Run SKU estimation on all leads
  sample-products      Sample product URLs for all leads
  scrape-products      Scrape sampled product pages
  capture-screens      Capture screenshots (requires ENABLE_SCREENSHOTS=true)
  audit-leads          Run imagery audit on all scraped leads
  score-leads          Score and segment all audited leads
  generate-outbound    Generate personalised email/Loom copy
  export-review-queue  Export leads for human review to CSV
  export-approved      Export approved leads to CSV
  run-pipeline         Run full pipeline (all stages) for all unprocessed leads
  demo                 Run a quick demo on sample data
"""
import json
import logging
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def _setup():
    """Initialise logging and DB. Call at start of each command."""
    from app.core.logging import setup_logging
    setup_logging()
    from app.db.database import init_db
    init_db()


@click.group()
@click.option("--log-level", default="INFO", help="Logging level")
def cli(log_level: str):
    """Prodigi Outbound Machine CLI."""
    from app.core.logging import setup_logging
    setup_logging(log_level)


# ---------------------------------------------------------------------------
# init-db
# ---------------------------------------------------------------------------

@cli.command("init-db")
def init_db_cmd():
    """Initialise database tables."""
    from app.db.database import init_db
    init_db()
    console.print("[green]Database initialised.[/green]")


# ---------------------------------------------------------------------------
# ingest-candidates
# ---------------------------------------------------------------------------

@cli.command("ingest-candidates")
@click.argument("csv_path", type=click.Path(exists=True, path_type=Path))
@click.option("--source", default=None, help="Override source label for all ingested candidates")
def ingest_candidates(csv_path: Path, source: Optional[str]):
    """Import candidate brands from CSV_PATH."""
    _setup()
    from app.db.database import session_scope
    from app.services.ingestion.ingestion_service import ingest_csv

    with session_scope() as session:
        stats = ingest_csv(csv_path, session, source_override=source)

    console.print(f"[green]Ingested {stats['ingested']} new candidates[/green]")
    console.print(f"  Duplicates skipped: {stats['skipped_duplicate']}")
    console.print(f"  Invalid rows: {stats['skipped_invalid']}")
    if stats["errors"]:
        console.print(f"  [red]Errors: {stats['errors']}[/red]")


# ---------------------------------------------------------------------------
# detect-shopify
# ---------------------------------------------------------------------------

@cli.command("detect-shopify")
@click.option("--limit", default=None, type=int, help="Max number of leads to process")
@click.option("--domain", default=None, help="Run on a specific domain only")
def detect_shopify_cmd(limit: Optional[int], domain: Optional[str]):
    """Run Shopify detection on leads."""
    _setup()
    from app.db.database import session_scope
    from app.db.models import Lead
    from app.services.pipeline import run_detection_stage

    with session_scope() as session:
        query = session.query(Lead)
        if domain:
            query = query.filter(Lead.domain == domain)
        else:
            query = query.filter(Lead.shopify_detected.is_(None))
        if limit:
            query = query.limit(limit)
        leads = query.all()

        console.print(f"Running Shopify detection on {len(leads)} leads...")
        for lead in leads:
            run_detection_stage(lead, session)
            status = "[green]✓[/green]" if lead.shopify_detected else "[yellow]?[/yellow]"
            console.print(f"  {status} {lead.domain} — confidence={lead.shopify_confidence:.2f}")

    console.print("[green]Detection complete.[/green]")


# ---------------------------------------------------------------------------
# estimate-skus
# ---------------------------------------------------------------------------

@cli.command("estimate-skus")
@click.option("--limit", default=None, type=int)
def estimate_skus_cmd(limit: Optional[int]):
    """Estimate SKU ranges for all leads."""
    _setup()
    from app.db.database import session_scope
    from app.db.models import Lead
    from app.services.pipeline import run_sku_stage

    with session_scope() as session:
        query = session.query(Lead).filter(Lead.estimated_sku_range.is_(None))
        if limit:
            query = query.limit(limit)
        leads = query.all()
        console.print(f"Estimating SKUs for {len(leads)} leads...")
        for lead in leads:
            run_sku_stage(lead, session)
            console.print(f"  {lead.domain} → {lead.estimated_sku_range}")

    console.print("[green]SKU estimation complete.[/green]")


# ---------------------------------------------------------------------------
# sample-products
# ---------------------------------------------------------------------------

@cli.command("sample-products")
@click.option("--limit", default=None, type=int)
def sample_products_cmd(limit: Optional[int]):
    """Sample product URLs for all leads."""
    _setup()
    from app.db.database import session_scope
    from app.db.models import Lead
    from app.services.pipeline import run_sampling_stage

    with session_scope() as session:
        query = session.query(Lead).filter(Lead.product_sample_count == 0)
        if limit:
            query = query.limit(limit)
        leads = query.all()
        console.print(f"Sampling products for {len(leads)} leads...")
        for lead in leads:
            run_sampling_stage(lead, session)
            console.print(f"  {lead.domain} → {lead.product_sample_count} products sampled")

    console.print("[green]Product sampling complete.[/green]")


# ---------------------------------------------------------------------------
# scrape-products
# ---------------------------------------------------------------------------

@cli.command("scrape-products")
@click.option("--limit", default=None, type=int)
def scrape_products_cmd(limit: Optional[int]):
    """Scrape product pages for all leads."""
    _setup()
    from app.db.database import session_scope
    from app.db.models import Lead, ProductSample
    from app.services.pipeline import run_scraping_stage

    with session_scope() as session:
        query = session.query(Lead).join(Lead.products).filter(
            ProductSample.scraped_at.is_(None)
        ).distinct()
        if limit:
            query = query.limit(limit)
        leads = query.all()
        console.print(f"Scraping products for {len(leads)} leads...")
        for lead in leads:
            run_scraping_stage(lead, session)
            console.print(f"  {lead.domain} — scraping done")

    console.print("[green]Scraping complete.[/green]")


# ---------------------------------------------------------------------------
# capture-screens
# ---------------------------------------------------------------------------

@cli.command("capture-screens")
@click.option("--limit", default=None, type=int)
def capture_screens_cmd(limit: Optional[int]):
    """Capture screenshots (requires ENABLE_SCREENSHOTS=true)."""
    _setup()
    from app.config.settings import settings
    if not settings.enable_screenshots:
        console.print("[yellow]ENABLE_SCREENSHOTS=false — set it to true in .env to capture screenshots.[/yellow]")
        return

    from app.db.database import session_scope
    from app.db.models import Lead
    from app.services.pipeline import run_screenshot_stage

    with session_scope() as session:
        query = session.query(Lead).filter(Lead.homepage_screenshot_path.is_(None))
        if limit:
            query = query.limit(limit)
        leads = query.all()
        console.print(f"Capturing screenshots for {len(leads)} leads...")
        for lead in leads:
            run_screenshot_stage(lead, session)
            status = "[green]✓[/green]" if lead.homepage_screenshot_path else "[red]✗[/red]"
            console.print(f"  {status} {lead.domain}")

    console.print("[green]Screenshot capture complete.[/green]")


# ---------------------------------------------------------------------------
# audit-leads
# ---------------------------------------------------------------------------

@cli.command("audit-leads")
@click.option("--limit", default=None, type=int)
def audit_leads_cmd(limit: Optional[int]):
    """Run imagery audit on all leads with scraped products."""
    _setup()
    from app.db.database import session_scope
    from app.db.models import Lead, ProductSample
    from app.services.pipeline import run_audit_stage

    with session_scope() as session:
        query = (
            session.query(Lead)
            .filter(Lead.imagery_audit_summary.is_(None))
            .join(Lead.products)
            .filter(ProductSample.scraped_at.isnot(None))
            .distinct()
        )
        if limit:
            query = query.limit(limit)
        leads = query.all()
        console.print(f"Auditing imagery for {len(leads)} leads...")
        for lead in leads:
            lead, audit = run_audit_stage(lead, session)
            count = len(audit.findings)
            console.print(f"  {lead.domain} → {count} findings (H={audit.high_count} M={audit.medium_count})")

    console.print("[green]Audit complete.[/green]")


# ---------------------------------------------------------------------------
# score-leads
# ---------------------------------------------------------------------------

@cli.command("score-leads")
@click.option("--limit", default=None, type=int)
def score_leads_cmd(limit: Optional[int]):
    """Score and segment all audited leads."""
    _setup()
    from app.db.database import session_scope
    from app.db.models import Lead
    from app.schemas.audit import AuditResult, AuditFinding
    from app.services.pipeline import run_scoring_stage

    with session_scope() as session:
        query = session.query(Lead).filter(
            Lead.imagery_audit_summary.isnot(None),
            Lead.lead_score.is_(None),
        )
        if limit:
            query = query.limit(limit)
        leads = query.all()
        console.print(f"Scoring {len(leads)} leads...")
        for lead in leads:
            # Reconstruct audit from stored findings
            audit = AuditResult()
            if lead.audit_findings:
                audit.findings = [AuditFinding(**f) for f in lead.audit_findings]
                audit.compute_counts()
                # Restore flags
                codes = {f.code for f in audit.findings}
                audit.has_low_image_count = "LOW_IMAGE_COUNT" in codes
                audit.has_inconsistent_counts = "INCONSISTENT_IMAGE_COUNT" in codes
                audit.has_missing_detail_shots = "MISSING_DETAIL_SHOTS" in codes
                audit.has_missing_front_back = "MISSING_FRONT_BACK" in codes
                audit.has_inconsistent_backgrounds = "INCONSISTENT_BACKGROUNDS" in codes
                audit.has_mixed_aspect_ratios = "MIXED_ASPECT_RATIOS" in codes
                audit.has_weak_variant_representation = "WEAK_VARIANT_REPRESENTATION" in codes
                audit.has_catalogue_depth_risk = "LOW_CATALOGUE_DEPTH" in codes

            run_scoring_stage(lead, audit, session)
            seg_color = {"A": "green", "B": "cyan", "C": "yellow", "D": "red"}.get(lead.lead_segment or "D", "white")
            console.print(
                f"  {lead.domain} → score={lead.lead_score:.1f} "
                f"[{seg_color}]segment={lead.lead_segment}[/{seg_color}]"
            )

    console.print("[green]Scoring complete.[/green]")


# ---------------------------------------------------------------------------
# generate-outbound
# ---------------------------------------------------------------------------

@cli.command("generate-outbound")
@click.option("--limit", default=None, type=int)
@click.option("--segment", default=None, help="Only generate for this segment (A/B/C/D)")
def generate_outbound_cmd(limit: Optional[int], segment: Optional[str]):
    """Generate personalised email and Loom copy for scored leads."""
    _setup()
    from app.db.database import session_scope
    from app.db.models import Lead
    from app.schemas.audit import AuditResult, AuditFinding
    from app.services.pipeline import run_personalisation_stage

    with session_scope() as session:
        query = session.query(Lead).filter(
            Lead.lead_score.isnot(None),
            Lead.personalised_email_subject.is_(None),
        )
        if segment:
            query = query.filter(Lead.lead_segment == segment.upper())
        if limit:
            query = query.limit(limit)
        leads = query.all()
        console.print(f"Generating outbound assets for {len(leads)} leads...")
        for lead in leads:
            audit = _reconstruct_audit(lead)
            run_personalisation_stage(lead, audit, session)
            console.print(f"  ✓ {lead.domain}")

    console.print("[green]Outbound generation complete.[/green]")


# ---------------------------------------------------------------------------
# export-review-queue
# ---------------------------------------------------------------------------

@cli.command("export-review-queue")
@click.option("--output", default=None, type=click.Path(path_type=Path))
@click.option("--segment", default=None, help="Filter to segment A/B/C/D")
def export_review_queue_cmd(output: Optional[Path], segment: Optional[str]):
    """Export leads for human review to CSV."""
    _setup()
    from app.db.database import session_scope
    from app.db.models import Lead
    from app.services.exports.csv_exporter import export_review_queue

    with session_scope() as session:
        query = session.query(Lead).filter(Lead.lead_score.isnot(None))
        if segment:
            query = query.filter(Lead.lead_segment == segment.upper())
        leads = query.order_by(Lead.lead_score.desc()).all()
        path = export_review_queue(leads, output_path=output)

    console.print(f"[green]Review queue exported:[/green] {path}")
    console.print(f"  {len(leads)} leads exported")


# ---------------------------------------------------------------------------
# export-approved
# ---------------------------------------------------------------------------

@cli.command("export-approved")
@click.option("--output", default=None, type=click.Path(path_type=Path))
def export_approved_cmd(output: Optional[Path]):
    """Export approved leads to CSV for outbound."""
    _setup()
    from app.db.database import session_scope
    from app.db.models import Lead, ReviewStatus
    from app.services.exports.csv_exporter import export_approved_leads

    with session_scope() as session:
        leads = (
            session.query(Lead)
            .filter(Lead.review_status == ReviewStatus.approved)
            .order_by(Lead.lead_score.desc())
            .all()
        )
        path = export_approved_leads(leads, output_path=output)

    console.print(f"[green]Approved leads exported:[/green] {path}")
    console.print(f"  {len(leads)} approved leads exported")


# ---------------------------------------------------------------------------
# run-pipeline
# ---------------------------------------------------------------------------

@cli.command("run-pipeline")
@click.option("--limit", default=None, type=int, help="Max leads to process")
@click.option("--domain", default=None, help="Run for a single domain")
def run_pipeline_cmd(limit: Optional[int], domain: Optional[str]):
    """Run the full pipeline for all unprocessed leads."""
    _setup()
    from app.db.database import session_scope
    from app.db.models import Lead
    from app.services.pipeline import run_full_pipeline, run_pipeline_for_all_leads

    with session_scope() as session:
        if domain:
            lead = session.query(Lead).filter(Lead.domain == domain).first()
            if not lead:
                console.print(f"[red]No lead found for domain: {domain}[/red]")
                return
            run_full_pipeline(lead, session)
            _print_lead_summary(lead)
        else:
            leads = run_pipeline_for_all_leads(session, limit=limit)
            console.print(f"\n[green]Pipeline complete — {len(leads)} leads processed.[/green]")
            _print_pipeline_summary(leads)


# ---------------------------------------------------------------------------
# show-leads
# ---------------------------------------------------------------------------

@cli.command("show-leads")
@click.option("--segment", default=None, help="Filter to segment A/B/C/D")
@click.option("--limit", default=20, type=int)
def show_leads_cmd(segment: Optional[str], limit: int):
    """Display a summary table of leads."""
    _setup()
    from app.db.database import session_scope
    from app.db.models import Lead

    rows_data = []
    with session_scope() as session:
        query = session.query(Lead)
        if segment:
            query = query.filter(Lead.lead_segment == segment.upper())
        leads = query.order_by(Lead.lead_score.desc().nulls_last()).limit(limit).all()
        # Eagerly read all attributes while session is open
        for l in leads:
            rows_data.append({
                "id": l.id,
                "brand_name": l.brand_name,
                "domain": l.domain,
                "vertical": l.vertical,
                "shopify_detected": l.shopify_detected,
                "estimated_sku_range": l.estimated_sku_range,
                "lead_score": l.lead_score,
                "lead_segment": l.lead_segment,
                "mock_opportunity": l.mock_opportunity,
                "review_status": l.review_status.value if hasattr(l.review_status, "value") else str(l.review_status),
            })

    table = Table(title=f"Leads ({len(rows_data)} shown)")
    table.add_column("ID", style="dim")
    table.add_column("Brand")
    table.add_column("Domain")
    table.add_column("Vertical")
    table.add_column("Shopify")
    table.add_column("SKUs")
    table.add_column("Score")
    table.add_column("Seg")
    table.add_column("Mock")
    table.add_column("Status")

    seg_colors = {"A": "green", "B": "cyan", "C": "yellow", "D": "red"}
    for l in rows_data:
        seg = l["lead_segment"] or "-"
        score = f"{l['lead_score']:.1f}" if l["lead_score"] is not None else "-"
        color = seg_colors.get(seg, "white")
        table.add_row(
            str(l["id"]),
            l["brand_name"][:25],
            l["domain"][:30],
            l["vertical"] or "-",
            "✓" if l["shopify_detected"] else ("?" if l["shopify_detected"] is None else "✗"),
            l["estimated_sku_range"] or "-",
            f"[{color}]{score}[/{color}]",
            f"[{color}]{seg}[/{color}]",
            "✓" if l["mock_opportunity"] else "-",
            l["review_status"],
        )

    console.print(table)


# ---------------------------------------------------------------------------
# demo
# ---------------------------------------------------------------------------

@cli.command("demo")
def demo_cmd():
    """Run a full demo pipeline using sample data from data/sample_candidates.csv."""
    _setup()
    sample_csv = Path("data/sample_candidates.csv")
    if not sample_csv.exists():
        console.print("[red]Sample data not found. Run: python scripts/seed_data.py[/red]")
        return

    console.print("[bold]Running demo pipeline on sample candidates...[/bold]")
    ctx = click.get_current_context()
    ctx.invoke(ingest_candidates, csv_path=sample_csv, source="demo")
    ctx.invoke(run_pipeline_cmd, limit=5)
    ctx.invoke(export_review_queue_cmd, output=None, segment=None)
    ctx.invoke(show_leads_cmd, segment=None, limit=20)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reconstruct_audit(lead):
    from app.schemas.audit import AuditResult, AuditFinding
    audit = AuditResult()
    if lead.audit_findings:
        try:
            audit.findings = [AuditFinding(**f) for f in lead.audit_findings]
            audit.compute_counts()
            codes = {f.code for f in audit.findings}
            audit.has_low_image_count = "LOW_IMAGE_COUNT" in codes
            audit.has_inconsistent_counts = "INCONSISTENT_IMAGE_COUNT" in codes
            audit.has_missing_detail_shots = "MISSING_DETAIL_SHOTS" in codes
            audit.has_missing_front_back = "MISSING_FRONT_BACK" in codes
            audit.has_inconsistent_backgrounds = "INCONSISTENT_BACKGROUNDS" in codes
            audit.has_mixed_aspect_ratios = "MIXED_ASPECT_RATIOS" in codes
            audit.has_weak_variant_representation = "WEAK_VARIANT_REPRESENTATION" in codes
            audit.has_catalogue_depth_risk = "LOW_CATALOGUE_DEPTH" in codes
        except Exception as e:
            logging.getLogger(__name__).warning("Failed reconstructing audit: %s", e)
    audit.summary = lead.imagery_audit_summary or ""
    return audit


def _print_lead_summary(lead) -> None:
    seg = lead.lead_segment or "-"
    color = {"A": "green", "B": "cyan", "C": "yellow", "D": "red"}.get(seg, "white")
    console.print(f"\n[bold]{lead.brand_name}[/bold] ({lead.domain})")
    console.print(f"  Shopify: {lead.shopify_detected} (confidence={lead.shopify_confidence})")
    console.print(f"  SKU range: {lead.estimated_sku_range}")
    console.print(f"  Score: [{color}]{lead.lead_score}[/{color}] | Segment: [{color}]{seg}[/{color}]")
    console.print(f"  Mock opportunity: {lead.mock_opportunity}")
    if lead.imagery_audit_summary:
        console.print(f"  Audit: {lead.imagery_audit_summary[:200]}...")
    if lead.personalised_email_subject:
        console.print(f"  Email subject: {lead.personalised_email_subject}")


def _print_pipeline_summary(leads) -> None:
    if not leads:
        return
    table = Table(title="Pipeline Results")
    table.add_column("Domain")
    table.add_column("Score")
    table.add_column("Segment")
    table.add_column("Mock")
    seg_colors = {"A": "green", "B": "cyan", "C": "yellow", "D": "red"}
    for l in sorted(leads, key=lambda x: x.lead_score or 0, reverse=True):
        seg = l.lead_segment or "-"
        color = seg_colors.get(seg, "white")
        table.add_row(
            l.domain,
            f"[{color}]{l.lead_score or 0:.1f}[/{color}]",
            f"[{color}]{seg}[/{color}]",
            "✓" if l.mock_opportunity else "-",
        )
    console.print(table)


if __name__ == "__main__":
    cli()
