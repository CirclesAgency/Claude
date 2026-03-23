"""
Seed script — creates synthetic test leads with realistic imagery audit data.
Useful for testing the scoring, personalisation, and export pipeline
without running actual HTTP requests.

Usage: python scripts/seed_data.py
"""
import sys
import os
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import setup_logging
from app.db.database import init_db, session_scope
from app.db.models import Lead, ProductSample, ReviewStatus, OutboundStatus
from app.schemas.audit import AuditResult, AuditFinding, AuditSeverity
from app.schemas.scoring import ScoreInput
from app.services.audit.audit_engine import audit_imagery
from app.services.scoring.scoring_engine import score_lead, determine_mock_opportunity, load_scoring_config
from app.services.personalisation.pain_generator import generate_pain_hypothesis
from app.services.personalisation.email_generator import generate_email
from app.services.personalisation.loom_generator import generate_loom_script
from app.schemas.product import ProductSampleData
from datetime import datetime, timezone
import json

setup_logging()


SEED_BRANDS = [
    {
        "brand_name": "Ember Apparel",
        "domain": "emberapparelco.com",
        "vertical": "apparel",
        "source": "seed",
        "shopify_detected": True,
        "shopify_confidence": 0.95,
        "shopify_evidence": ["products_json_endpoint_valid", "shopify_cdn_reference"],
        "estimated_sku_range": "50_100",
        "products": [
            {"image_count": 2, "variant_count": 4, "background_type": "white", "has_detail_shots": False},
            {"image_count": 1, "variant_count": 6, "background_type": "white", "has_detail_shots": False},
            {"image_count": 3, "variant_count": 3, "background_type": "lifestyle", "has_detail_shots": True},
            {"image_count": 2, "variant_count": 5, "background_type": "white", "has_detail_shots": False},
            {"image_count": 8, "variant_count": 2, "background_type": "white", "has_detail_shots": True},
        ],
        "contact_email": "founder@emberapparelco.com",
        "contact_name": "Alex",
    },
    {
        "brand_name": "Bloom Beauty",
        "domain": "bloombeautyco.com",
        "vertical": "beauty",
        "source": "seed",
        "shopify_detected": True,
        "shopify_confidence": 0.88,
        "shopify_evidence": ["shopify_cdn_reference", "window_shopify_js_object"],
        "estimated_sku_range": "20_50",
        "products": [
            {"image_count": 3, "variant_count": 2, "background_type": "white", "has_detail_shots": False},
            {"image_count": 3, "variant_count": 1, "background_type": "white", "has_detail_shots": False},
            {"image_count": 4, "variant_count": 3, "background_type": "lifestyle", "has_detail_shots": True},
            {"image_count": 2, "variant_count": 2, "background_type": "lifestyle", "has_detail_shots": False},
            {"image_count": 3, "variant_count": 1, "background_type": "white", "has_detail_shots": False},
        ],
    },
    {
        "brand_name": "Stride Footwear",
        "domain": "stridefootwear.com",
        "vertical": "footwear",
        "source": "seed",
        "shopify_detected": True,
        "shopify_confidence": 0.92,
        "shopify_evidence": ["products_json_endpoint_valid", "myshopify_reference_in_html"],
        "estimated_sku_range": "100_200",
        "products": [
            {"image_count": 1, "variant_count": 8, "background_type": "white", "has_detail_shots": False},
            {"image_count": 2, "variant_count": 6, "background_type": "white", "has_detail_shots": False},
            {"image_count": 1, "variant_count": 5, "background_type": "white", "has_detail_shots": False},
            {"image_count": 2, "variant_count": 7, "background_type": "white", "has_detail_shots": False},
            {"image_count": 1, "variant_count": 4, "background_type": "white", "has_detail_shots": False},
        ],
        "contact_email": "hello@stridefootwear.com",
    },
    {
        "brand_name": "Hearth & Home",
        "domain": "hearthandhome.co",
        "vertical": "homewares",
        "source": "seed",
        "shopify_detected": True,
        "shopify_confidence": 0.85,
        "shopify_evidence": ["shopify_cdn_reference"],
        "estimated_sku_range": "50_100",
        "products": [
            {"image_count": 5, "variant_count": 2, "background_type": "lifestyle", "has_detail_shots": True},
            {"image_count": 4, "variant_count": 3, "background_type": "lifestyle", "has_detail_shots": True},
            {"image_count": 6, "variant_count": 1, "background_type": "lifestyle", "has_detail_shots": True},
            {"image_count": 7, "variant_count": 2, "background_type": "lifestyle", "has_detail_shots": True},
            {"image_count": 5, "variant_count": 2, "background_type": "lifestyle", "has_detail_shots": True},
        ],
    },
    {
        "brand_name": "Clasp Accessories",
        "domain": "claspaccessories.com",
        "vertical": "accessories",
        "source": "seed",
        "shopify_detected": True,
        "shopify_confidence": 0.78,
        "shopify_evidence": ["shopify_cdn_reference", "window_shopify_js_object"],
        "estimated_sku_range": "20_50",
        "products": [
            {"image_count": 2, "variant_count": 4, "background_type": "white", "has_detail_shots": False},
            {"image_count": 3, "variant_count": 3, "background_type": "mixed", "has_detail_shots": False},
            {"image_count": 1, "variant_count": 5, "background_type": "lifestyle", "has_detail_shots": False},
            {"image_count": 4, "variant_count": 2, "background_type": "white", "has_detail_shots": True},
            {"image_count": 2, "variant_count": 6, "background_type": "white", "has_detail_shots": False},
        ],
        "contact_email": "founder@claspaccessories.com",
        "contact_name": "Jordan",
    },
]


def make_product_sample_data(p_dict: dict, url_base: str, i: int) -> ProductSampleData:
    n_imgs = p_dict["image_count"]
    return ProductSampleData(
        url=f"https://{url_base}/products/product-{i}",
        image_urls=[f"https://cdn.shopify.com/s/files/img_{j}_800x1000.jpg" for j in range(n_imgs)],
        image_count=n_imgs,
        alt_texts=[f"Product image {j}" for j in range(n_imgs)],
        variant_count=p_dict.get("variant_count", 1),
        has_detail_shots=p_dict.get("has_detail_shots"),
        has_lifestyle_shots=p_dict.get("background_type") == "lifestyle",
        background_type=p_dict.get("background_type", "white"),
        aspect_ratios=["4:5"] * n_imgs,
        scraped_at=datetime.now(timezone.utc),
    )


def seed():
    init_db()
    config = load_scoring_config()

    from app.db.models import Candidate
    with session_scope() as session:
        # Clear existing seed data (in FK order)
        seed_lead_ids = [r[0] for r in session.query(Lead.id).filter(Lead.source == "seed")]
        if seed_lead_ids:
            session.query(ProductSample).filter(
                ProductSample.lead_id.in_(seed_lead_ids)
            ).delete(synchronize_session=False)
        session.query(Lead).filter(Lead.source == "seed").delete(synchronize_session=False)
        session.query(Candidate).filter(Candidate.source == "seed").delete(synchronize_session=False)
        session.commit()

    with session_scope() as session:
        for brand_data in SEED_BRANDS:
            products_raw = brand_data.pop("products", [])

            # Create a Candidate stub for each seed brand
            from app.db.models import Candidate
            candidate = Candidate(
                brand_name=brand_data["brand_name"],
                domain=brand_data["domain"],
                source=brand_data.get("source", "seed"),
                vertical=brand_data.get("vertical"),
            )
            session.add(candidate)
            session.flush()

            lead = Lead(
                candidate_id=candidate.id,
                brand_name=brand_data["brand_name"],
                domain=brand_data["domain"],
                vertical=brand_data.get("vertical"),
                source=brand_data.get("source", "seed"),
                shopify_detected=brand_data.get("shopify_detected"),
                shopify_confidence=brand_data.get("shopify_confidence"),
                shopify_evidence=brand_data.get("shopify_evidence", []),
                estimated_sku_range=brand_data.get("estimated_sku_range"),
                contact_email=brand_data.get("contact_email"),
                contact_name=brand_data.get("contact_name"),
                review_status=ReviewStatus.pending,
                outbound_status=OutboundStatus.uncontacted,
            )
            session.add(lead)
            session.flush()

            # Persist product samples
            product_objects = []
            for i, p_dict in enumerate(products_raw):
                pdata = make_product_sample_data(p_dict, brand_data["domain"], i)
                ps = ProductSample(
                    lead_id=lead.id,
                    url=pdata.url,
                    image_urls=pdata.image_urls,
                    image_count=pdata.image_count,
                    alt_texts=pdata.alt_texts,
                    variant_count=pdata.variant_count,
                    has_detail_shots=pdata.has_detail_shots,
                    has_lifestyle_shots=pdata.has_lifestyle_shots,
                    background_type=pdata.background_type,
                    aspect_ratios=pdata.aspect_ratios,
                    scraped_at=pdata.scraped_at,
                )
                session.add(ps)
                product_objects.append(pdata)

            lead.product_sample_count = len(product_objects)

            # Audit
            audit = audit_imagery(product_objects)
            lead.imagery_audit_summary = audit.summary
            lead.audit_findings = [f.model_dump() for f in audit.findings]

            # Score
            import statistics as st
            avg_v = st.mean([p.variant_count for p in product_objects]) if product_objects else 0
            score_input = ScoreInput.from_audit_result(
                audit,
                shopify_confidence=lead.shopify_confidence or 0,
                estimated_sku_range=lead.estimated_sku_range or "unknown",
                vertical=lead.vertical,
                contact_available=bool(lead.contact_email),
                has_contact_info=bool(lead.contact_email),
                avg_variant_count=avg_v,
            )
            score_result = score_lead(score_input, config)
            lead.lead_score = score_result.total_score
            lead.lead_segment = score_result.segment
            lead.score_breakdown = score_result.breakdown

            is_mock, mock_reason = determine_mock_opportunity(score_input, score_result)
            score_input.mock_opportunity = is_mock
            lead.mock_opportunity = is_mock
            lead.mock_opportunity_reason = mock_reason

            # Personalisation
            pain = generate_pain_hypothesis(audit, lead.brand_name, lead.vertical)
            lead.commercial_pain_hypothesis = pain

            email = generate_email(
                brand_name=lead.brand_name,
                domain=lead.domain,
                audit=audit,
                vertical=lead.vertical,
                contact_name=lead.contact_name,
                polish_with_llm=False,
            )
            lead.personalised_email_subject = email.subject
            lead.personalised_email_body = email.body

            loom = generate_loom_script(
                brand_name=lead.brand_name,
                domain=lead.domain,
                audit=audit,
                vertical=lead.vertical,
                polish_with_llm=False,
            )
            lead.loom_script = loom.script

            print(f"  Seeded: {lead.brand_name} | score={lead.lead_score:.1f} | seg={lead.lead_segment}")

        session.commit()

    print(f"\nSeeded {len(SEED_BRANDS)} leads successfully.")
    print("Run: outbound show-leads")
    print("Run: outbound export-review-queue")


if __name__ == "__main__":
    seed()
