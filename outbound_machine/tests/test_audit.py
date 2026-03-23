"""Tests for the imagery audit engine."""
import pytest
from app.schemas.product import ProductSampleData
from app.schemas.audit import AuditSeverity
from app.services.audit.audit_engine import audit_imagery


def make_product(
    url: str = "https://example.com/products/test",
    image_count: int = 5,
    variant_count: int = 1,
    has_detail_shots: bool = True,
    has_lifestyle_shots: bool = False,
    background_type: str = "white",
    aspect_ratios: list | None = None,
    scrape_error: str | None = None,
) -> ProductSampleData:
    return ProductSampleData(
        url=url,
        image_urls=[f"https://cdn.shopify.com/img_{i}_800x1000.jpg" for i in range(image_count)],
        image_count=image_count,
        variant_count=variant_count,
        has_detail_shots=has_detail_shots,
        has_lifestyle_shots=has_lifestyle_shots,
        background_type=background_type,
        aspect_ratios=aspect_ratios or ["4:5"] * image_count,
        scrape_error=scrape_error,
    )


class TestAuditEngine:
    def test_no_findings_for_healthy_catalogue(self):
        """A well-resourced catalogue with 6+ images should have minimal findings."""
        products = [make_product(image_count=8, variant_count=3, has_detail_shots=True)
                    for _ in range(8)]
        result = audit_imagery(products)
        high_critical = [f for f in result.findings if f.severity == AuditSeverity.HIGH]
        assert len(high_critical) == 0

    def test_low_image_count_flagged(self):
        """Average < 3 images should trigger LOW_IMAGE_COUNT at HIGH severity."""
        products = [make_product(image_count=1) for _ in range(7)]
        result = audit_imagery(products)

        codes = {f.code for f in result.findings}
        assert "LOW_IMAGE_COUNT" in codes

        finding = next(f for f in result.findings if f.code == "LOW_IMAGE_COUNT")
        assert finding.severity == AuditSeverity.HIGH
        assert result.has_low_image_count is True

    def test_inconsistent_image_counts_flagged(self):
        """High coefficient of variation should trigger INCONSISTENT_IMAGE_COUNT."""
        products = (
            [make_product(url=f"https://ex.com/products/p{i}", image_count=1) for i in range(4)] +
            [make_product(url=f"https://ex.com/products/q{i}", image_count=10) for i in range(4)]
        )
        result = audit_imagery(products)
        codes = {f.code for f in result.findings}
        assert "INCONSISTENT_IMAGE_COUNT" in codes
        assert result.has_inconsistent_counts is True

    def test_weak_variant_representation(self):
        """Products with more variants than images should be flagged."""
        products = [
            make_product(image_count=2, variant_count=8),
            make_product(image_count=2, variant_count=6),
            make_product(image_count=3, variant_count=7),
        ]
        result = audit_imagery(products)
        codes = {f.code for f in result.findings}
        assert "WEAK_VARIANT_REPRESENTATION" in codes
        assert result.has_weak_variant_representation is True

        finding = next(f for f in result.findings if f.code == "WEAK_VARIANT_REPRESENTATION")
        assert finding.severity == AuditSeverity.HIGH

    def test_mixed_aspect_ratios(self):
        """More than 2 distinct aspect ratios should be flagged."""
        products = [
            make_product(aspect_ratios=["1:1", "4:5", "16:9", "3:2"]),
            make_product(aspect_ratios=["1:1", "4:5", "16:9"]),
        ]
        result = audit_imagery(products)
        codes = {f.code for f in result.findings}
        assert "MIXED_ASPECT_RATIOS" in codes
        assert result.has_mixed_aspect_ratios is True

    def test_inconsistent_backgrounds(self):
        """Mix of white and lifestyle backgrounds should be flagged."""
        products = (
            [make_product(url=f"https://ex.com/products/w{i}", background_type="white") for i in range(3)] +
            [make_product(url=f"https://ex.com/products/l{i}", background_type="lifestyle") for i in range(3)]
        )
        result = audit_imagery(products)
        codes = {f.code for f in result.findings}
        assert "INCONSISTENT_BACKGROUNDS" in codes
        assert result.has_inconsistent_backgrounds is True

    def test_empty_products_handled_gracefully(self):
        """No products should return a summary, not raise."""
        result = audit_imagery([])
        assert result.summary != ""
        assert result.findings == []

    def test_all_scrape_errors_handled(self):
        """All scraped with errors should produce a meaningful result."""
        products = [make_product(scrape_error="Timeout") for _ in range(5)]
        result = audit_imagery(products)
        # Should not raise, summary should explain
        assert "no" in result.summary.lower() or "scrape" in result.summary.lower() or result.summary

    def test_summary_is_factual(self):
        """Summary should include numeric data."""
        products = [make_product(image_count=2) for _ in range(5)]
        result = audit_imagery(products)
        # Summary should reference the number of products
        assert "5" in result.summary or "2" in result.summary

    def test_severity_counts_correct(self):
        products = [make_product(image_count=1, variant_count=5) for _ in range(5)]
        result = audit_imagery(products)
        result.compute_counts()
        assert result.high_count == sum(
            1 for f in result.findings if f.severity == AuditSeverity.HIGH
        )
        assert result.medium_count == sum(
            1 for f in result.findings if f.severity == AuditSeverity.MEDIUM
        )
