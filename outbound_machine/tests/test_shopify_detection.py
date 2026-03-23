"""
Tests for Shopify detection logic.
Uses mock HTTP responses to avoid live network calls.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestShopifyDetector:
    """Test the multi-signal detection logic."""

    def _make_response(self, text: str = "", status: int = 200, json_data=None):
        resp = MagicMock()
        resp.status_code = status
        resp.text = text
        resp.headers = {}
        if json_data is not None:
            resp.json.return_value = json_data
        else:
            resp.json.side_effect = ValueError("not json")
        return resp

    @patch("app.services.detection.shopify_detector.get_json")
    @patch("app.services.detection.shopify_detector.get_text")
    @patch("app.services.detection.shopify_detector.get")
    def test_detects_via_products_json(self, mock_get, mock_get_text, mock_get_json):
        """Products.json returning valid data → high confidence."""
        mock_get_json.return_value = {"products": [{"handle": "test-product"}]}
        mock_get_text.return_value = ""
        mock_get.return_value = self._make_response()

        from app.services.detection.shopify_detector import detect_shopify
        result = detect_shopify("example.com")

        assert result.shopify_detected is True
        assert result.confidence >= 0.90
        assert "products_json_endpoint_valid" in result.evidence

    @patch("app.services.detection.shopify_detector.get_json")
    @patch("app.services.detection.shopify_detector.get_text")
    @patch("app.services.detection.shopify_detector.get")
    def test_detects_via_cdn_reference(self, mock_get, mock_get_text, mock_get_json):
        """CDN reference in HTML → moderate-high confidence."""
        mock_get_json.return_value = None
        mock_get_text.return_value = (
            '<script src="https://cdn.shopify.com/s/files/1/0000/theme.js"></script>'
        )
        mock_get.return_value = self._make_response(
            text='<script src="https://cdn.shopify.com/s/files/1/0000/theme.js"></script>'
        )

        from app.services.detection.shopify_detector import detect_shopify
        result = detect_shopify("example.com")

        assert result.shopify_detected is True
        assert "shopify_cdn_reference" in result.evidence

    @patch("app.services.detection.shopify_detector.get_json")
    @patch("app.services.detection.shopify_detector.get_text")
    @patch("app.services.detection.shopify_detector.get")
    def test_no_signals_returns_not_detected(self, mock_get, mock_get_text, mock_get_json):
        """No Shopify signals → not detected."""
        mock_get_json.return_value = None
        mock_get_text.return_value = "<html><body>Plain website</body></html>"
        mock_get.return_value = self._make_response(text="<html><body>Plain website</body></html>")

        from app.services.detection.shopify_detector import detect_shopify
        result = detect_shopify("plainwebsite.com")

        assert result.shopify_detected is False
        assert result.confidence < 0.5

    @patch("app.services.detection.shopify_detector.get_json")
    @patch("app.services.detection.shopify_detector.get_text")
    @patch("app.services.detection.shopify_detector.get")
    def test_multiple_signals_compound_confidence(self, mock_get, mock_get_text, mock_get_json):
        """Multiple signals should compound to higher confidence."""
        shopify_html = (
            "window.Shopify = {}; cdn.shopify.com; myshopify.com reference"
        )
        mock_get_json.return_value = {"products": [{"handle": "p1"}]}
        mock_get_text.return_value = shopify_html
        mock_get.return_value = self._make_response(text=shopify_html)

        from app.services.detection.shopify_detector import detect_shopify
        result = detect_shopify("bigshop.com")

        assert result.shopify_detected is True
        assert result.confidence > 0.95
        assert len(result.evidence) > 1

    @patch("app.services.detection.shopify_detector.get_json")
    @patch("app.services.detection.shopify_detector.get_text")
    @patch("app.services.detection.shopify_detector.get")
    def test_graceful_on_network_failure(self, mock_get, mock_get_text, mock_get_json):
        """Network failures should return not-detected, not raise."""
        mock_get_json.return_value = None
        mock_get_text.return_value = None
        mock_get.return_value = None

        from app.services.detection.shopify_detector import detect_shopify
        result = detect_shopify("unreachable.com")

        assert result.shopify_detected is False
        assert result.confidence == 0.0
