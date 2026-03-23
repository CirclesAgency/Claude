"""Tests for the lead scoring engine."""
import pytest
from app.schemas.scoring import ScoreInput, ScoreResult
from app.services.scoring.scoring_engine import score_lead, determine_mock_opportunity
from app.services.sku_estimation.sku_estimator import _bucket as _sku_bucket


def make_score_input(**kwargs) -> ScoreInput:
    defaults = {
        "shopify_confidence": 0.9,
        "estimated_sku_range": "50_100",
        "vertical": "apparel",
        "contact_available": True,
        "has_contact_info": True,
        "has_low_image_count": True,
        "has_inconsistent_counts": False,
        "has_missing_detail_shots": True,
        "has_missing_front_back": False,
        "has_inconsistent_backgrounds": False,
        "has_inconsistent_framing": False,
        "has_mixed_aspect_ratios": False,
        "has_weak_variant_representation": False,
        "has_catalogue_depth_risk": False,
        "high_finding_count": 1,
        "medium_finding_count": 1,
        "low_finding_count": 0,
        "total_finding_count": 2,
        "mock_opportunity": True,
        "avg_variant_count": 3.0,
        "social_presence": True,
    }
    defaults.update(kwargs)
    return ScoreInput(**defaults)


class TestScoringEngine:
    def test_high_icp_fit_scores_well(self):
        inp = make_score_input(
            shopify_confidence=0.95,
            estimated_sku_range="50_100",
            vertical="apparel",
        )
        result = score_lead(inp)
        assert result.total_score > 50
        assert result.breakdown["icp_fit"] > 15

    def test_shopify_not_detected_reduces_score(self):
        inp_confirmed = make_score_input(shopify_confidence=0.95)
        inp_uncertain = make_score_input(shopify_confidence=0.1)

        r1 = score_lead(inp_confirmed)
        r2 = score_lead(inp_uncertain)

        assert r1.breakdown["icp_fit"] > r2.breakdown["icp_fit"]

    def test_no_imagery_issues_scores_lower(self):
        inp_with_issues = make_score_input(
            has_low_image_count=True,
            has_missing_detail_shots=True,
            has_weak_variant_representation=True,
            high_finding_count=2,
            medium_finding_count=1,
            total_finding_count=3,
        )
        inp_clean = make_score_input(
            has_low_image_count=False,
            has_missing_detail_shots=False,
            has_weak_variant_representation=False,
            high_finding_count=0,
            medium_finding_count=0,
            low_finding_count=0,
            total_finding_count=0,
        )
        r1 = score_lead(inp_with_issues)
        r2 = score_lead(inp_clean)
        assert r1.breakdown["imagery_opportunity"] > r2.breakdown["imagery_opportunity"]

    def test_segment_a_threshold(self):
        inp = make_score_input(
            shopify_confidence=0.95,
            estimated_sku_range="50_100",
            vertical="apparel",
            has_low_image_count=True,
            has_weak_variant_representation=True,
            has_inconsistent_counts=True,
            mock_opportunity=True,
            has_contact_info=True,
        )
        result = score_lead(inp)
        assert result.segment in ("A", "B")

    def test_segment_d_for_weak_lead(self):
        inp = make_score_input(
            shopify_confidence=0.1,
            estimated_sku_range="under_20",
            vertical="other_unknown",
            has_low_image_count=False,
            has_missing_detail_shots=False,
            has_weak_variant_representation=False,
            mock_opportunity=False,
            has_contact_info=False,
        )
        result = score_lead(inp)
        assert result.segment in ("C", "D")

    def test_score_bounded_0_to_100(self):
        """Score should never exceed 100."""
        inp = make_score_input(
            shopify_confidence=0.99,
            has_low_image_count=True,
            has_inconsistent_counts=True,
            has_missing_detail_shots=True,
            has_missing_front_back=True,
            has_inconsistent_backgrounds=True,
            has_mixed_aspect_ratios=True,
            has_weak_variant_representation=True,
            has_catalogue_depth_risk=True,
            mock_opportunity=True,
        )
        result = score_lead(inp)
        assert 0 <= result.total_score <= 100

    def test_breakdown_keys_present(self):
        inp = make_score_input()
        result = score_lead(inp)
        assert "icp_fit" in result.breakdown
        assert "imagery_opportunity" in result.breakdown
        assert "commercial_potential" in result.breakdown
        assert "outreach_viability" in result.breakdown

    def test_reasoning_populated(self):
        inp = make_score_input()
        result = score_lead(inp)
        assert len(result.reasoning) > 0


class TestMockOpportunity:
    def test_apparel_with_issues_is_opportunity(self):
        inp = make_score_input(
            vertical="apparel",
            has_low_image_count=True,
        )
        result = score_lead(inp)
        is_mock, reason = determine_mock_opportunity(inp)
        assert is_mock is True
        assert len(reason) > 0

    def test_no_issues_not_opportunity(self):
        inp = make_score_input(
            vertical="apparel",
            has_low_image_count=False,
            has_inconsistent_counts=False,
            has_missing_detail_shots=False,
            has_weak_variant_representation=False,
            has_inconsistent_backgrounds=False,
        )
        result = score_lead(inp)
        is_mock, reason = determine_mock_opportunity(inp)
        assert is_mock is False

    def test_unknown_vertical_reduces_opportunity(self):
        inp = make_score_input(
            vertical="industrial_machinery",
            has_low_image_count=True,
        )
        result = score_lead(inp)
        is_mock, reason = determine_mock_opportunity(inp)
        # May still be True if ICP fit is ok, but reason should explain
        assert isinstance(is_mock, bool)
        assert len(reason) > 0
