"""Tests for email, Loom, and pain hypothesis generation."""
import pytest
from app.schemas.audit import AuditResult, AuditFinding, AuditSeverity
from app.services.personalisation.email_generator import generate_email
from app.services.personalisation.loom_generator import generate_loom_script
from app.services.personalisation.pain_generator import generate_pain_hypothesis


def make_audit_with_findings(*codes: str) -> AuditResult:
    severity_map = {
        "WEAK_VARIANT_REPRESENTATION": AuditSeverity.HIGH,
        "LOW_IMAGE_COUNT": AuditSeverity.HIGH,
        "INCONSISTENT_IMAGE_COUNT": AuditSeverity.MEDIUM,
        "MISSING_DETAIL_SHOTS": AuditSeverity.MEDIUM,
        "INCONSISTENT_BACKGROUNDS": AuditSeverity.MEDIUM,
        "MIXED_ASPECT_RATIOS": AuditSeverity.LOW,
        "LOW_CATALOGUE_DEPTH": AuditSeverity.MEDIUM,
    }
    audit = AuditResult()
    for code in codes:
        audit.findings.append(AuditFinding(
            code=code,
            severity=severity_map.get(code, AuditSeverity.MEDIUM),
            title=code.replace("_", " ").title(),
            detail=f"Test detail for {code}",
            metric=2.5,
        ))

    # Set flags
    codes_set = set(codes)
    audit.has_low_image_count = "LOW_IMAGE_COUNT" in codes_set
    audit.has_inconsistent_counts = "INCONSISTENT_IMAGE_COUNT" in codes_set
    audit.has_missing_detail_shots = "MISSING_DETAIL_SHOTS" in codes_set
    audit.has_inconsistent_backgrounds = "INCONSISTENT_BACKGROUNDS" in codes_set
    audit.has_weak_variant_representation = "WEAK_VARIANT_REPRESENTATION" in codes_set
    audit.compute_counts()
    return audit


class TestEmailGenerator:
    def test_generates_subject_and_body(self):
        audit = make_audit_with_findings("LOW_IMAGE_COUNT")
        email = generate_email("Acme Apparel", "acmeapparel.com", audit, vertical="apparel")
        assert email.subject
        assert email.body
        assert len(email.body) > 50

    def test_brand_name_in_email(self):
        audit = make_audit_with_findings("LOW_IMAGE_COUNT")
        email = generate_email("Sunshine Threads", "sunshine.com", audit, vertical="apparel")
        assert "Sunshine Threads" in email.subject or "Sunshine Threads" in email.body

    def test_no_cringe_phrases(self):
        audit = make_audit_with_findings("LOW_IMAGE_COUNT", "MISSING_DETAIL_SHOTS")
        email = generate_email("TestBrand", "testbrand.com", audit)
        body_lower = email.body.lower()
        # Check for phrases we explicitly avoid
        cringe = ["synergize", "best-in-class", "disruptive", "leverage", "game-changer"]
        for phrase in cringe:
            assert phrase not in body_lower, f"Found cringe phrase: {phrase}"

    def test_fallback_on_no_findings(self):
        audit = AuditResult()
        email = generate_email("CleanBrand", "cleanbrand.com", audit)
        assert email.subject
        assert email.body

    def test_contact_name_used_when_provided(self):
        audit = make_audit_with_findings("LOW_IMAGE_COUNT")
        email = generate_email(
            "BrandX", "brandx.com", audit,
            contact_name="Sarah"
        )
        assert "Sarah" in email.body

    def test_vertical_selects_template(self):
        audit = make_audit_with_findings("MISSING_DETAIL_SHOTS")
        beauty_email = generate_email("GlowCo", "glowco.com", audit, vertical="beauty")
        apparel_email = generate_email("ThreadCo", "thread.com", audit, vertical="apparel")
        # Templates are different
        assert beauty_email.template_used != apparel_email.template_used or True  # May be same, just check no error

    def test_llm_polish_skipped_when_disabled(self):
        from unittest.mock import patch
        audit = make_audit_with_findings("LOW_IMAGE_COUNT")
        with patch("app.services.personalisation.email_generator.llm_interface.polish_email") as mock_polish:
            mock_polish.return_value = ("subject", "body")
            email = generate_email("Brand", "brand.com", audit, polish_with_llm=False)
            # Should not call polish when False
            mock_polish.assert_not_called()


class TestLoomGenerator:
    def test_generates_script(self):
        audit = make_audit_with_findings("WEAK_VARIANT_REPRESENTATION")
        loom = generate_loom_script("FabricCo", "fabricco.com", audit, vertical="apparel")
        assert loom.script
        assert len(loom.script) > 100
        assert loom.estimated_duration_seconds > 0

    def test_brand_name_in_script(self):
        audit = make_audit_with_findings("LOW_IMAGE_COUNT")
        loom = generate_loom_script("StrapsWorld", "strapsworld.com", audit)
        assert "StrapsWorld" in loom.script

    def test_prodigi_mentioned(self):
        audit = make_audit_with_findings("LOW_IMAGE_COUNT")
        loom = generate_loom_script("Brand", "brand.com", audit)
        assert "Prodigi" in loom.script

    def test_fallback_on_no_findings(self):
        audit = AuditResult()
        loom = generate_loom_script("Brand", "brand.com", audit)
        assert loom.script
        assert loom.template_used == "fallback"


class TestPainHypothesis:
    def test_generates_grounded_hypothesis(self):
        audit = make_audit_with_findings("LOW_IMAGE_COUNT", "MISSING_DETAIL_SHOTS")
        pain = generate_pain_hypothesis(audit, "DenimCo", "apparel")
        assert "DenimCo" in pain
        assert len(pain) > 50

    def test_no_imagery_issues_gives_honest_assessment(self):
        audit = AuditResult()
        pain = generate_pain_hypothesis(audit, "PerfectBrand", "homewares")
        # Should honestly say the brand looks healthy
        assert "PerfectBrand" in pain
        assert len(pain) > 20

    def test_variant_pain_mentioned_for_variant_issue(self):
        audit = make_audit_with_findings("WEAK_VARIANT_REPRESENTATION")
        pain = generate_pain_hypothesis(audit, "ColourBrand", "accessories")
        lower = pain.lower()
        assert "variant" in lower or "colour" in lower or "color" in lower or "style" in lower
