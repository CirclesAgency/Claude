# Architecture Overview

## Data flow

```
CSV input
    ↓
[Ingestion Service]
    → Candidates table
    → Leads table (pending)
    ↓
[Shopify Detector]
    → Multi-signal analysis (products.json, CDN refs, JS objects, headers)
    → confidence: 0.0–1.0 (Bayesian combination of independent signals)
    ↓
[SKU Estimator]
    → products.json enumeration → sitemap → collections/all text hints
    → bucket: under_20 / 20_50 / 50_100 / 100_200 / 200_plus
    ↓
[Product Sampler]
    → Diverse URL selection from products.json + collections
    → 5–15 representative product URLs
    → ProductSample records created
    ↓
[Product Scraper]
    → Shopify product.json API (preferred) or HTML parsing fallback
    → image_count, image_urls, variant_count, alt_texts, background_type
    → aspect_ratio extraction from Shopify CDN URL patterns
    ↓
[Screenshot Service]    ← optional, ENABLE_SCREENSHOTS=true
    → Playwright headless chromium
    → homepage + collection + 2-3 product screenshots
    ↓
[Audit Engine]
    → Rule-based checks against scraped product data
    → AuditFinding objects with codes, severity, metrics, affected URLs
    → AuditResult with flags (has_low_image_count, etc.) used by scoring
    ↓
[Pain Hypothesis Generator]
    → Maps finding codes → commercial pain sentence fragments
    → Adds operational implication + Prodigi CTA
    ↓
[Scoring Engine]
    → YAML-configured weighted categories
    → ICP fit (30pt) + Imagery opportunity (40pt) + Commercial (20pt) + Outreach (10pt)
    → Mock opportunity determination
    ↓
[Email Generator]          [Loom Generator]
    → Jinja2 vertical templates   → Jinja2 script template
    → LLM polish (optional)       → LLM polish (optional)
    ↓
[Review Queue]
    → All leads exported to CSV
    → Human reviewer approves / rejects / requests edit
    ↓
[Approved Export]
    → CSV for CRM import / manual outbound
    → Webhook sync (optional)
```

## Design decisions

### Why rule-based audit (not AI-vision)?
V1 needs to be deterministic, inspectable, and runnable without GPU or expensive API calls.
The Shopify CDN URL patterns encode image dimensions — we extract aspect ratios and count
images without downloading a single image file. This is fast, reliable, and sufficient for
identifying the commercially meaningful weaknesses (low count, variant gaps, inconsistency).

AI-vision can be added later as a layer on top of screenshots once we validate the
commercial hypothesis with this simpler approach.

### Why Bayesian signal combination for Shopify detection?
Each signal is independent. `products.json` is the strongest signal (0.95) because Shopify's
default JSON API is only enabled on Shopify stores. Multiple weaker signals (CDN refs, JS objects)
compound to high confidence even when no single signal is definitive.

Formula: `confidence = 1 - ∏(1 - p_i)` (capped at 0.99)

### Why products.json for SKU estimation?
Shopify exposes `/products.json?limit=250&page=N` publicly by default. Enumerating pages
gives an exact product count with high reliability. Sitemap and collections/all are fallbacks
for stores that have disabled the API.

### Why templates-first, LLM-optional?
Templates ensure the system works for any engineer without API keys. LLM polish is
strictly additive — it can only improve copy, never change the factual grounding.
This keeps the system auditable and trustworthy.

### Why SQLite default?
SQLite requires zero infrastructure. An engineer can clone, install, and run the full
pipeline in under 5 minutes. Postgres is production-recommended but not required for V1.

## Key schemas

### Lead (DB model)
Central record — one per brand. Has all enriched fields plus FK to candidate.

### ProductSample (DB model)
Scraped PDP data. FK to Lead. One row per sampled URL.

### AuditResult (Pydantic)
Computed in memory from ProductSample records. Stored as JSON in Lead.audit_findings.

### ScoreInput (Pydantic)
All inputs to the scoring engine. Derived from AuditResult + Lead fields.

### LeadPacket (Pydantic)
Read-only view of a fully processed Lead. Used for exports and API responses.
