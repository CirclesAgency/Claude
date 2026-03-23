# Prodigi Outbound Machine — V1

An automated outbound lead generation system for Prodigi. Finds Shopify e-commerce brands
in our ICP, audits their product imagery, scores and segments them, and generates
personalised email + Loom outreach assets.

**This system is for human-reviewed outbound — no email is ever sent automatically.**

---

## What it does

| Stage | Input | Output |
|-------|-------|--------|
| 1. Ingestion | CSV of brand candidates | Candidates + Lead records in DB |
| 2. Shopify detection | Domain | Confidence score + evidence signals |
| 3. SKU estimation | Domain | Bucket: `under_20` → `200_plus` |
| 4. Product sampling | Domain | 5–15 representative product URLs |
| 5. Product scraping | Product URLs | Image counts, variants, alt text, dimensions |
| 6. Screenshot capture | URLs | PNG screenshots (optional, needs Playwright) |
| 7. Imagery audit | Scraped product data | Structured findings + plain English summary |
| 8. Commercial pain | Audit findings | 2–4 sentence pain hypothesis |
| 9. Lead scoring | Audit + ICP signals | 0–100 score + A/B/C/D segment |
| 10. Mock opportunity | Score + vertical | True/False + reason |
| 11. Personalisation | Pain + findings | Email subject/body + Loom script |
| 12. Review queue | All leads | CSV for human approval |
| 13. Approved export | Approved leads | CSV ready for CRM import |

---

## Architecture

```
app/
├── config/           Settings (pydantic-settings), scoring_config.yaml
├── core/             Logging, retry, rate limiting
├── db/               SQLAlchemy models, session factory
├── schemas/          Pydantic schemas (pure data, no DB)
├── services/
│   ├── ingestion/    CSV → Candidate + Lead records
│   ├── detection/    Shopify multi-signal detection
│   ├── sku_estimation/ products.json / sitemap enumeration
│   ├── sampling/     Diverse product URL selection
│   ├── scraping/     PDP HTML + Shopify JSON scraping
│   ├── screenshots/  Playwright capture (optional)
│   ├── audit/        Rule-based imagery audit engine
│   ├── scoring/      YAML-configurable weighted scoring
│   ├── personalisation/ Pain hypothesis, email, Loom generators
│   ├── crm/          Webhook CRM sync abstraction
│   └── exports/      CSV export (review queue + approved)
├── templates/        Jinja2 email + Loom templates
├── cli/              Click CLI commands
└── utils/            Domain, HTTP client, image analysis
```

All pipeline stages are independently runnable. The `run-pipeline` command orchestrates all stages for unprocessed leads.

---

## Quick start (local with SQLite)

### 1. Install

```bash
# Clone repo and cd in
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — defaults work for local SQLite without any changes
```

### 3. Initialise database

```bash
python scripts/init_db.py
# or:
outbound init-db
```

### 4. Run the demo

```bash
# Seeds synthetic data and runs full pipeline locally (no HTTP calls needed)
python scripts/seed_data.py

# View results
outbound show-leads

# Export review CSV
outbound export-review-queue
# Opens: data/exports/review_queue_<timestamp>.csv
```

### 5. Run on real brands

```bash
# Ingest your own CSV (see data/sample_candidates.csv for format)
outbound ingest-candidates data/sample_candidates.csv --source "manual"

# Run the full pipeline (makes real HTTP requests, respects rate limits)
outbound run-pipeline --limit 5

# Review results
outbound show-leads
outbound export-review-queue
```

---

## Environment variables

See `.env.example` for all options. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | SQLite | Postgres or SQLite connection string |
| `RATE_LIMIT_DELAY` | `2.0` | Seconds between requests per domain |
| `ENABLE_SCREENSHOTS` | `false` | Enable Playwright screenshots |
| `ENABLE_LLM` | `false` | Enable LLM-assisted copy polishing |
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` | — | Required only if `ENABLE_LLM=true` |
| `ENABLE_WEBHOOK_SYNC` | `false` | Enable CRM webhook sync |
| `CRM_WEBHOOK_URL` | — | Webhook endpoint for CRM push |

---

## CLI reference

```bash
outbound --help                        # List all commands

# Pipeline stages (run independently or all at once)
outbound init-db
outbound ingest-candidates <csv>       # --source "manual"
outbound detect-shopify                # --limit 10 --domain example.com
outbound estimate-skus                 # --limit 10
outbound sample-products               # --limit 10
outbound scrape-products               # --limit 10
outbound capture-screens               # --limit 10 (needs ENABLE_SCREENSHOTS=true)
outbound audit-leads                   # --limit 10
outbound score-leads                   # --limit 10
outbound generate-outbound             # --limit 10 --segment A

# Review + export
outbound show-leads                    # --segment A --limit 20
outbound export-review-queue           # --output path/to/file.csv
outbound export-approved               # exports leads with review_status=approved

# Run everything
outbound run-pipeline                  # --limit 10 --domain example.com
outbound demo                          # Uses sample_candidates.csv
```

---

## Reviewing and approving leads

The review workflow is manual by design. To approve leads:

1. Run `outbound export-review-queue` to get a CSV
2. Open in Google Sheets or Excel
3. Review the `imagery_audit_summary`, `personalised_email_subject`, and `personalised_email_body` columns
4. Update `review_status` to `approved`, `rejected`, or `needs_edit`
5. Re-import approved leads via SQL or a future `/approve` CLI command
6. Run `outbound export-approved` to get the final outbound CSV

**Shortcut for quick approval** (via DB):
```sql
UPDATE leads SET review_status = 'approved' WHERE lead_segment = 'A' AND mock_opportunity = true;
```

---

## Scoring configuration

Edit `app/config/scoring_config.yaml` to adjust scoring weights and thresholds.
No code changes needed.

```yaml
segments:
  A: 80    # A = 80+
  B: 65    # B = 65–79
  C: 50    # C = 50–64
             # D = <50

categories:
  icp_fit:
    weight: 30    # max 30 points
    inputs:
      shopify_confirmed:
        threshold: 0.7
        score: 1.0
      sku_fit:
        buckets:
          "50_100": 1.0    # ideal range
          "20_50": 0.7
          ...
```

---

## Screenshots (optional)

Screenshots require Playwright:

```bash
playwright install chromium
```

Then set `ENABLE_SCREENSHOTS=true` in `.env` and run `outbound capture-screens`.

Screenshots are saved to `data/screenshots/<domain>/`.

---

## LLM polishing (optional)

When `ENABLE_LLM=true` and an API key is set, email and Loom copy gets a polish pass.
The system **always works without an LLM key** — template output is production-ready.

```bash
# In .env:
ENABLE_LLM=true
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-3-5-haiku-20241022
```

---

## Local Postgres setup

```bash
# Start Postgres via Docker Compose
docker-compose up db -d

# Set DATABASE_URL in .env:
DATABASE_URL=postgresql://outbound:outbound@localhost:5432/outbound_machine

python scripts/init_db.py
```

---

## Running tests

```bash
pytest tests/ -v

# Fast subset (no mocking of network):
pytest tests/test_domain.py tests/test_audit.py tests/test_scoring.py -v
```

---

## Adding a CRM integration

1. Subclass `BaseCrmAdapter` in `app/services/crm/`
2. Implement `sync_lead(self, lead: LeadPacket) -> CrmSyncResult`
3. Wire it into `run_pipeline` or export commands

The `WebhookCrmAdapter` covers Zapier/Make → HubSpot/Apollo/Instantly/Smartlead today.

---

## Future extension points

- **OpenClaw integration**: Replace `httpx` calls in `http_client.py` with OpenClaw browser sessions for JS-heavy stores
- **Contact enrichment**: Add a `ContactEnricher` service that finds founder emails via Apollo/Hunter
- **Scheduled runs**: Wrap `run-pipeline` in a cron or OpenClaw scheduler for daily discovery
- **Admin UI**: FastAPI + simple HTML for the review queue (stubs in `app/api/`)
- **HubSpot/Apollo adapters**: Implement `BaseCrmAdapter` subclasses
- **LLM scoring uplift**: Add LLM-based visual audit when screenshots are available
- **Vertical expansion**: Add `homewares_email.j2`, `footwear_email.j2` templates
