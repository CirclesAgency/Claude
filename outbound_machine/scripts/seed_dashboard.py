"""
Seed realistic demo data for the lead dashboard UI.
Creates 25 leads across all segments/statuses/verticals,
5 pipeline runs, and 20+ lead activities.

Usage:
    python scripts/seed_dashboard.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone, timedelta
from app.db.database import SessionLocal, init_db
from app.db.models import Candidate, Lead, LeadActivity, PipelineRun, ReviewStatus, OutboundStatus

init_db()

LEADS_DATA = [
    # (brand, domain, vertical, seg, score, sku_range, au_conf, mock, review_st, outbound_st,
    #  call_booked, contact_email, subject, body_snippet, pain, findings_count, days_ago)
    (
        "Stride Athletics", "strideathleticsco.com.au", "activewear", "A", 97.0,
        "100_200", 0.92, True, "approved", "sent",
        False, "james@strideathleticsco.com.au",
        "Your product imagery is costing you conversions",
        "Hi James,\n\nI was browsing Stride Athletics this morning and noticed your activewear photography uses lifestyle shots without white-background variants...",
        "Lifestyle-only imagery limits Shopify collection grid performance; missing white-BG variants block marketplace expansion.",
        [{"severity": "HIGH", "title": "No white-background variants", "description": "All hero shots are lifestyle only — no clean product cut-outs for marketplace listings."},
         {"severity": "HIGH", "title": "Inconsistent angles", "description": "6 of 12 sampled PDPs show inconsistent camera angles across colourways."},
         {"severity": "MEDIUM", "title": "Missing model size callout", "description": "Size reference missing on most images."}],
        0,
    ),
    (
        "Clasp Jewellery", "claspjewellery.com.au", "jewellery", "A", 94.0,
        "50_100", 0.89, True, "approved", "uncontacted",
        False, "hello@claspjewellery.com.au",
        "Jewellery photography that actually converts",
        "Hi there,\n\nI spent time with Clasp Jewellery's collection pages and found a specific issue that's likely suppressing your conversion rate...",
        "Fine jewellery requires macro/detail photography; current product shots lack close-up detail views.",
        [{"severity": "HIGH", "title": "No macro detail shots", "description": "Fine jewellery requires detail close-ups; all PDPs show only hero angle."},
         {"severity": "MEDIUM", "title": "Dark backgrounds on delicate pieces", "description": "Dark lifestyle backgrounds reduce perceived product quality for fine jewellery."}],
        5,
    ),
    (
        "Ember Home", "emberhome.com.au", "homewares", "A", 91.0,
        "100_200", 0.88, True, "approved", "replied",
        True, "tom@emberhome.com.au",
        "Scale your product catalogue faster with Prodigi",
        "Hi Tom,\n\nEmber Home is doing something really special in the homewares space...",
        "Inconsistent room-set photography slows product launches — a studio workflow could 10x throughput.",
        [{"severity": "HIGH", "title": "Inconsistent room sets", "description": "Multiple room set styles across collection create incoherent brand aesthetic."},
         {"severity": "MEDIUM", "title": "Low resolution lifestyle shots", "description": "Several images are under 800px wide."}],
        -2,
    ),
    (
        "Bloom Botanicals", "bloombotanicals.com.au", "beauty", "B", 72.0,
        "50_100", 0.85, False, "approved", "sent",
        False, "info@bloombotanicals.com.au",
        "Your ingredient photography could tell a better story",
        "Hi,\n\nI've been looking at Bloom Botanicals and the ingredient macro photography is a clear opportunity...",
        "Botanical skincare brands differentiate via ingredient story-telling; current imagery misses this.",
        [{"severity": "MEDIUM", "title": "Missing ingredient close-ups", "description": "No macro shots of key botanicals despite brand positioning."},
         {"severity": "LOW", "title": "Packaging shot quality", "description": "Some packaging images show fingerprints."}],
        1,
    ),
    (
        "Hearth & Co", "hearthandco.com.au", "homewares", "B", 68.0,
        "20_50", 0.91, False, "approved", "uncontacted",
        False, "hey@hearthandco.com.au",
        None, None,
        "Candle and home fragrance brand with limited photography variety.",
        [{"severity": "MEDIUM", "title": "Single angle only", "description": "Candles shown from top-down only; no 45° or straight-on shots."}],
        3,
    ),
    (
        "Rove Outdoors", "roveoutdoors.com.au", "outdoor", "B", 65.0,
        "100_200", 0.87, True, "pending", "uncontacted",
        False, None, None, None,
        "Outdoor gear with no studio imagery — all lifestyle, limits product comparison.",
        [{"severity": "HIGH", "title": "No studio product shots", "description": "100% lifestyle photography makes product comparison difficult."},
         {"severity": "MEDIUM", "title": "Colour variants inconsistent", "description": "Different lighting across colourways."}],
        7,
    ),
    (
        "Lace & Thread", "laceandthread.com.au", "fashion", "B", 62.0,
        "200_plus", 0.83, False, "pending", "uncontacted",
        False, None, None, None,
        "Fashion brand with model imagery but no flat-lay or product-only shots.",
        [{"severity": "MEDIUM", "title": "No flat-lay options", "description": "Wholesale buyers expect flat-lay; currently not offered."}],
        10,
    ),
    (
        "Petal & Pine", "petalandpine.com.au", "beauty", "B", 58.0,
        "50_100", 0.78, False, "needs_edit", "uncontacted",
        False, "chloe@petalandpine.com.au",
        "Skincare imagery review",
        "Hi Chloe,\n\nI noticed some opportunities with Petal & Pine's product photography...",
        "Skincare brand relying on single hero shot per SKU.",
        [{"severity": "MEDIUM", "title": "Single SKU shot", "description": "Only one image per product in most PDPs."}],
        4,
    ),
    (
        "Ironwood Furniture", "ironwoodfurniture.com.au", "homewares", "C", 45.0,
        "under_20", 0.90, False, "pending", "uncontacted",
        False, None, None, None,
        "Bespoke furniture brand with amateurish photography.",
        [{"severity": "HIGH", "title": "Amateur photography", "description": "Visible shadows, uneven backgrounds, JPEG artifacts."}],
        14,
    ),
    (
        "Swift Swim", "swiftswim.com.au", "activewear", "C", 42.0,
        "50_100", 0.82, False, "pending", "uncontacted",
        False, None, None, None,
        "Swimwear brand with limited shot angles.",
        [{"severity": "MEDIUM", "title": "Front-only shots", "description": "No back or side views for swimwear."}],
        8,
    ),
    (
        "Oakdale Skincare", "oakdaleskincare.com.au", "beauty", "C", 38.0,
        "20_50", 0.75, False, "pending", "uncontacted",
        False, None, None, None,
        "Clinical skincare with clinical imagery — no lifestyle context.",
        [],
        6,
    ),
    (
        "Peak Nutrition", "peaknutrition.com.au", "health", "C", 35.0,
        "100_200", 0.80, False, "rejected", "uncontacted",
        False, None, None, None,
        "Nutrition supplements — photography adequate, low mock opportunity.",
        [],
        20,
    ),
    (
        "Zest Activewear", "zestactivewear.com.au", "activewear", "C", 33.0,
        "50_100", 0.77, False, "pending", "uncontacted",
        False, None, None, None,
        "Small activewear startup, limited budget signals.",
        [],
        15,
    ),
    (
        "Harbour Lane", "harbourlane.com.au", "fashion", "D", 22.0,
        "under_20", 0.65, False, "rejected", "uncontacted",
        False, None, None, None,
        "Fashion brand with very limited catalogue.",
        [],
        30,
    ),
    (
        "Bush & Bloom", "bushandbloom.com.au", "beauty", "D", 18.0,
        "under_20", 0.71, False, "pending", "uncontacted",
        False, None, None, None,
        "Cottage-industry beauty brand, too small.",
        [],
        25,
    ),
    # Extra A-tier for variety
    (
        "Kite & Thread", "kiteandthread.com.au", "fashion", "A", 88.0,
        "100_200", 0.86, True, "approved", "queued",
        False, "kate@kiteandthread.com.au",
        "Your fashion imagery is ready for a Prodigi upgrade",
        "Hi Kate,\n\nI've been reviewing Kite & Thread...",
        "Fashion brand scaling SKU count rapidly — photography bottleneck is real.",
        [{"severity": "HIGH", "title": "Photoshoot bottleneck", "description": "New SKUs are delayed by 6-8 weeks due to photoshoot scheduling."}],
        2,
    ),
    (
        "Copper & Clay", "copperandclay.com.au", "homewares", "A", 85.0,
        "50_100", 0.91, True, "approved", "uncontacted",
        False, "studio@copperandclay.com.au",
        "Handmade ceramics deserve better product photography",
        "Hi there,\n\nCopper & Clay's ceramics are beautiful...",
        "Handmade ceramics lose texture detail in current photography setup.",
        [{"severity": "HIGH", "title": "Texture detail lost", "description": "Ceramic texture not captured — critical for handmade positioning."},
         {"severity": "MEDIUM", "title": "Inconsistent white balance", "description": "Warm/cool tones vary across product range."}],
        1,
    ),
    (
        "Aurora Lighting", "auroralighting.com.au", "homewares", "B", 61.0,
        "50_100", 0.84, False, "approved", "sent",
        False, "mark@auroralighting.com.au",
        "Lighting product photography challenges",
        "Hi Mark,\n\nI noticed Aurora Lighting's product photography...",
        "Lighting products are notoriously hard to photograph — opportunity for specialist workflow.",
        [{"severity": "HIGH", "title": "Bloom/flare issues", "description": "Glowing bulbs causing overexposure in most product shots."}],
        3,
    ),
    (
        "Saffron Kitchen", "saffroncook.com.au", "homewares", "B", 55.0,
        "50_100", 0.87, False, "pending", "uncontacted",
        False, None, None, None,
        "Kitchenware brand with adequate but unexciting photography.",
        [{"severity": "LOW", "title": "No lifestyle context", "description": "All products on plain background only."}],
        9,
    ),
    (
        "Drift Surf Co", "driftsurfco.com.au", "outdoor", "B", 52.0,
        "20_50", 0.79, False, "pending", "uncontacted",
        False, None, None, None,
        "Surf brand with heavily stylised lifestyle photos, lacking e-comm basics.",
        [{"severity": "MEDIUM", "title": "No plain background option", "description": "Surf lifestyle photography only — no clean e-comm images."}],
        12,
    ),
    (
        "Mossy Creek", "mossycreek.com.au", "outdoor", "C", 40.0,
        "under_20", 0.76, False, "pending", "uncontacted",
        False, None, None, None,
        "Hiking gear, very small catalogue.",
        [],
        18,
    ),
    (
        "Velvet & Vine", "velvetandvine.com.au", "fashion", "A", 83.0,
        "100_200", 0.85, True, "approved", "replied",
        True, "sophie@velvetandvine.com.au",
        "Velvet & Vine — luxury fashion imagery upgrade",
        "Hi Sophie,\n\nI've spent time with Velvet & Vine...",
        "Luxury positioning undercut by inconsistent image quality across collections.",
        [{"severity": "HIGH", "title": "Luxury positioning mismatch", "description": "Brand positions as luxury but photography is mid-market quality."},
         {"severity": "MEDIUM", "title": "No video content", "description": "No motion/video for hero products — industry standard for luxury."}],
        -4,
    ),
    (
        "Sage & Silo", "sageandsilo.com.au", "beauty", "B", 57.0,
        "20_50", 0.81, False, "needs_edit", "uncontacted",
        False, "founder@sageandsilo.com.au",
        None, None,
        "Natural beauty brand, inconsistent brand aesthetic.",
        [{"severity": "MEDIUM", "title": "Brand aesthetic inconsistency", "description": "Mix of minimalist and bohemian aesthetics across PDPs."}],
        6,
    ),
    (
        "Archways Studio", "archwaystudio.com.au", "fashion", "C", 37.0,
        "under_20", 0.73, False, "pending", "uncontacted",
        False, None, None, None,
        "Design studio, limited fashion catalogue.",
        [],
        22,
    ),
    (
        "Tidal Surf Goods", "tidalsurfgoods.com.au", "outdoor", "B", 59.0,
        "50_100", 0.82, True, "approved", "uncontacted",
        False, "ops@tidalsurfgoods.com.au",
        "Your product images could match your surf brand energy",
        "Hi,\n\nTidal Surf Goods has great lifestyle photography but...",
        "Strong lifestyle presence but no e-comm product grid images.",
        [{"severity": "HIGH", "title": "No grid-ready images", "description": "Collection grid uses lifestyle crops — no clean product images."}],
        4,
    ),
]


def seed():
    db = SessionLocal()
    try:
        # Check if already seeded
        existing = db.query(Lead).count()
        if existing > 0:
            print(f"Database already has {existing} leads. Skipping seed.")
            print("To reseed, delete the database file and run again.")
            return

        now = datetime.now(timezone.utc)

        print(f"Seeding {len(LEADS_DATA)} leads...")

        for i, row in enumerate(LEADS_DATA):
            (brand, domain, vertical, seg, score, sku_range, au_conf, mock,
             review_st, outbound_st, call_booked, contact_email,
             subject, body_snippet, pain, findings, days_ago) = row

            created_at = now - timedelta(days=abs(days_ago), hours=i % 12)
            updated_at = created_at + timedelta(hours=1 + (i % 5))

            # Candidate
            cand = Candidate(
                brand_name=brand,
                domain=domain,
                source="seed_demo",
                vertical=vertical,
                discovery_source="duckduckgo_search",
                discovery_vertical=vertical,
                discovered_at=created_at,
                country_guess="AU",
                au_confidence=au_conf,
                au_signals=["com_au_tld"] if au_conf > 0.85 else ["au_cities", "aud_currency"],
                created_at=created_at,
            )
            db.add(cand)
            db.flush()

            # Lead
            lead = Lead(
                candidate_id=cand.id,
                brand_name=brand,
                domain=domain,
                vertical=vertical,
                source="seed_demo",
                discovery_source="duckduckgo_search",
                discovery_vertical=vertical,
                discovered_at=created_at,
                country_guess="AU",
                au_confidence=au_conf,
                au_signals=cand.au_signals,
                shopify_detected=True,
                shopify_confidence=0.85,
                estimated_sku_range=sku_range,
                product_sample_count=min(12, int(score / 8)),
                audit_findings=findings,
                commercial_pain_hypothesis=pain,
                lead_score=score,
                lead_segment=seg,
                score_breakdown={
                    "high_findings_pts": len([f for f in findings if f.get("severity") == "HIGH"]) * 12,
                    "medium_findings_pts": len([f for f in findings if f.get("severity") == "MEDIUM"]) * 6,
                    "mock_bonus": 10 if mock else 0,
                },
                mock_opportunity=mock,
                mock_opportunity_reason="High finding count + Shopify confirmed + AU" if mock else None,
                contact_email=contact_email,
                personalised_email_subject=subject,
                personalised_email_body=body_snippet,
                review_status=ReviewStatus(review_st),
                outbound_status=OutboundStatus(outbound_st),
                call_booked=call_booked,
                created_at=created_at,
                updated_at=updated_at,
            )
            db.add(lead)
            db.flush()

            # Activities
            db.add(LeadActivity(
                lead_id=lead.id,
                activity_type="discovered",
                content=f"Discovered via DuckDuckGo ({vertical})",
                created_at=created_at,
                created_by="system",
            ))

            if score is not None:
                db.add(LeadActivity(
                    lead_id=lead.id,
                    activity_type="scored",
                    content=f"Scored {score:.0f} — Segment {seg}",
                    created_at=created_at + timedelta(minutes=30),
                    created_by="system",
                ))

            if review_st == "approved":
                db.add(LeadActivity(
                    lead_id=lead.id,
                    activity_type="approved",
                    content="Marked approved",
                    created_at=updated_at,
                    created_by="user",
                ))
            elif review_st == "rejected":
                db.add(LeadActivity(
                    lead_id=lead.id,
                    activity_type="rejected",
                    content="Marked rejected — low opportunity",
                    created_at=updated_at,
                    created_by="user",
                ))

            if outbound_st == "sent":
                db.add(LeadActivity(
                    lead_id=lead.id,
                    activity_type="email_sent",
                    content="Email marked as sent",
                    created_at=updated_at + timedelta(hours=2),
                    created_by="user",
                ))
            elif outbound_st == "replied":
                db.add(LeadActivity(
                    lead_id=lead.id,
                    activity_type="email_sent",
                    content="Email marked as sent",
                    created_at=updated_at + timedelta(hours=2),
                    created_by="user",
                ))
                db.add(LeadActivity(
                    lead_id=lead.id,
                    activity_type="replied",
                    content="Reply received — interested in a call",
                    created_at=updated_at + timedelta(days=2),
                    created_by="user",
                ))

            if call_booked:
                db.add(LeadActivity(
                    lead_id=lead.id,
                    activity_type="call_booked",
                    content="Discovery call booked",
                    created_at=updated_at + timedelta(days=3),
                    created_by="user",
                ))

        # Pipeline runs
        print("Seeding pipeline runs...")
        run_data = [
            ("daily_au", "completed", 35, 18, 180, 25, 4, 8, 6, 3, 0, now - timedelta(days=1)),
            ("daily_au", "completed", 42, 22, 210, 30, 5, 9, 7, 4, 1, now - timedelta(days=2)),
            ("manual", "completed", 15, 10, 95, 15, 2, 5, 3, 2, 0, now - timedelta(days=3)),
            ("daily_au", "failed", 8, 0, 0, 0, 0, 0, 0, 0, 3, now - timedelta(days=4)),
            ("manual", "completed", 50, 28, 260, 35, 6, 12, 8, 5, 0, now - timedelta(days=7)),
        ]
        for run_type, status, disc, qual, dur, proc, a, b, c, d, errs, started in run_data:
            run = PipelineRun(
                run_type=run_type,
                status=status,
                started_at=started,
                completed_at=started + timedelta(seconds=dur) if status != "failed" else started + timedelta(seconds=30),
                duration_seconds=dur if status != "failed" else None,
                leads_discovered=disc,
                leads_qualified=qual,
                leads_processed=proc,
                leads_a_tier=a,
                leads_b_tier=b,
                leads_c_tier=c,
                leads_d_tier=d,
                error_count=errs,
                notes="Completed successfully." if status == "completed" and errs == 0 else
                      f"{errs} errors during processing." if errs > 0 else
                      "DuckDuckGo rate limit hit — pipeline aborted.",
            )
            db.add(run)

        db.commit()
        print("✓ Seeded successfully.")
        print(f"  - {len(LEADS_DATA)} leads")
        print(f"  - {len(run_data)} pipeline runs")
        print(f"  - Activities created for each lead")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
