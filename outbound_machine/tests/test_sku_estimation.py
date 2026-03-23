"""Tests for SKU estimation and bucketing logic."""
import pytest
from app.services.sku_estimation.sku_estimator import _bucket
from app.db.models import SkuRange


class TestSkuBuckets:
    def test_under_20(self):
        assert _bucket(0) == SkuRange.under_20.value
        assert _bucket(5) == SkuRange.under_20.value
        assert _bucket(19) == SkuRange.under_20.value

    def test_20_to_50(self):
        assert _bucket(20) == SkuRange.r20_50.value
        assert _bucket(35) == SkuRange.r20_50.value
        assert _bucket(49) == SkuRange.r20_50.value

    def test_50_to_100(self):
        assert _bucket(50) == SkuRange.r50_100.value
        assert _bucket(75) == SkuRange.r50_100.value
        assert _bucket(99) == SkuRange.r50_100.value

    def test_100_to_200(self):
        assert _bucket(100) == SkuRange.r100_200.value
        assert _bucket(150) == SkuRange.r100_200.value
        assert _bucket(199) == SkuRange.r100_200.value

    def test_200_plus(self):
        assert _bucket(200) == SkuRange.r200_plus.value
        assert _bucket(500) == SkuRange.r200_plus.value
        assert _bucket(1000) == SkuRange.r200_plus.value

    def test_icp_ideal_range(self):
        """20–200 SKUs are our ICP sweet spot."""
        icp_buckets = {
            SkuRange.r20_50.value,
            SkuRange.r50_100.value,
            SkuRange.r100_200.value,
        }
        for count in [25, 50, 100, 150, 199]:
            assert _bucket(count) in icp_buckets


class TestSkuEstimator:
    """Integration-level tests with mocked HTTP."""

    def _make_products_json(self, count: int) -> dict:
        return {
            "products": [
                {"handle": f"product-{i}", "id": i}
                for i in range(count)
            ]
        }

    def test_estimates_from_products_json(self):
        from unittest.mock import patch
        from app.services.sku_estimation.sku_estimator import estimate_skus

        with patch("app.services.sku_estimation.sku_estimator.get_json") as mock_gj, \
             patch("app.services.sku_estimation.sku_estimator.get_text") as mock_gt:

            # First page: 45 products (under 250 limit = last page)
            mock_gj.return_value = self._make_products_json(45)
            mock_gt.return_value = ""

            result = estimate_skus("test.com")

        assert result.estimated_count == 45
        assert result.bucket == SkuRange.r20_50.value
        assert result.method == "products_json"

    def test_fallback_to_unknown_on_failure(self):
        from unittest.mock import patch
        from app.services.sku_estimation.sku_estimator import estimate_skus

        with patch("app.services.sku_estimation.sku_estimator.get_json") as mock_gj, \
             patch("app.services.sku_estimation.sku_estimator.get_text") as mock_gt:
            mock_gj.return_value = None
            mock_gt.return_value = ""

            result = estimate_skus("unknown.com")

        assert result.bucket == SkuRange.unknown.value
        assert result.estimated_count is None
