"""
Tests for the Australian e-commerce store detector.

All tests use the deterministic signal-checking functions directly —
no HTTP requests are made (html is injected directly).
"""
import pytest
from app.services.detection.au_detector import (
    detect_au,
    _check_tld_signals,
    _check_content_signals,
    _bayesian_combine,
    _infer_country,
    SIGNAL_WEIGHTS,
    AUDetectionResult,
)


# ---------------------------------------------------------------------------
# TLD signal tests
# ---------------------------------------------------------------------------

class TestTLDSignals:
    def test_com_au_detected(self):
        signals = []
        _check_tld_signals("example.com.au", signals)
        assert "com_au_tld" in signals

    def test_net_au_detected(self):
        signals = []
        _check_tld_signals("example.net.au", signals)
        assert "net_au_tld" in signals

    def test_org_au_detected(self):
        signals = []
        _check_tld_signals("example.org.au", signals)
        assert "net_au_tld" in signals

    def test_new_au_gtld_detected(self):
        signals = []
        _check_tld_signals("brand.au", signals)
        assert "au_gtld" in signals

    def test_com_au_does_not_trigger_au_gtld(self):
        """A .com.au domain should trigger com_au_tld, not au_gtld."""
        signals = []
        _check_tld_signals("example.com.au", signals)
        assert "au_gtld" not in signals
        assert "com_au_tld" in signals

    def test_us_domain_no_au_signals(self):
        signals = []
        _check_tld_signals("example.com", signals)
        assert signals == []

    def test_uk_domain_no_au_signals(self):
        signals = []
        _check_tld_signals("example.co.uk", signals)
        assert signals == []

    def test_case_insensitive(self):
        signals = []
        _check_tld_signals("BRAND.COM.AU", signals)
        assert "com_au_tld" in signals


# ---------------------------------------------------------------------------
# Content signal tests
# ---------------------------------------------------------------------------

class TestContentSignals:
    def test_abn_full_pattern(self):
        html = "<p>ABN: 12 345 678 901</p>"
        signals = []
        _check_content_signals(html, signals)
        assert "abn_pattern" in signals

    def test_abn_label_only(self):
        html = "<footer>ABN 32123456789</footer>"
        signals = []
        _check_content_signals(html, signals)
        # Should match abn_pattern (11 contiguous digits after ABN)
        # or at minimum abn_label
        assert "abn_pattern" in signals or "abn_label" in signals

    def test_no_abn_in_non_au_content(self):
        html = "<p>Tax ID: 123-45-6789</p>"
        signals = []
        _check_content_signals(html, signals)
        assert "abn_pattern" not in signals
        assert "abn_label" not in signals

    def test_phone_61_detected(self):
        html = "<p>Call us: +61 2 9876 5432</p>"
        signals = []
        _check_content_signals(html, signals)
        assert "phone_61" in signals

    def test_au_mobile_format(self):
        html = "<p>Mobile: 0412 345 678</p>"
        signals = []
        _check_content_signals(html, signals)
        assert "au_mobile_format" in signals

    def test_aud_currency(self):
        signals = []
        _check_content_signals("Price: AUD 89.95", signals)
        assert "aud_currency" in signals

    def test_a_dollar_currency(self):
        signals = []
        _check_content_signals("Price: A$89.95", signals)
        assert "aud_currency" in signals

    def test_gst_mention(self):
        signals = []
        _check_content_signals("All prices include GST.", signals)
        assert "gst_mention" in signals

    def test_gst_full_name(self):
        signals = []
        _check_content_signals("Goods and Services Tax applies.", signals)
        assert "gst_mention" in signals

    def test_au_states_two_or_more(self):
        html = "We ship to NSW, VIC and QLD daily."
        signals = []
        _check_content_signals(html, signals)
        assert "au_states" in signals

    def test_au_states_single_not_enough(self):
        html = "Located in NSW."
        signals = []
        _check_content_signals(html, signals)
        # One state mention is not enough to avoid false positives
        assert "au_states" not in signals

    def test_au_city_detected(self):
        signals = []
        _check_content_signals("Based in Melbourne, Australia.", signals)
        assert "au_cities" in signals

    def test_australia_wide_shipping(self):
        signals = []
        _check_content_signals("Australia-wide free shipping on orders over $100", signals)
        assert "au_shipping" in signals

    def test_ship_to_australia(self):
        signals = []
        _check_content_signals("We ship to Australia and internationally.", signals)
        assert "au_shipping" in signals

    def test_afterpay_detected(self):
        signals = []
        _check_content_signals("Pay with Afterpay — 4 interest-free instalments", signals)
        assert "afterpay_zip" in signals

    def test_zip_pay_detected(self):
        signals = []
        _check_content_signals("Buy now pay later with Zip Pay", signals)
        assert "afterpay_zip" in signals

    def test_pty_ltd_detected(self):
        signals = []
        _check_content_signals("© 2024 Brand Name Pty Ltd", signals)
        assert "pty_ltd" in signals

    def test_empty_html_no_signals(self):
        signals = []
        _check_content_signals("", signals)
        assert signals == []


# ---------------------------------------------------------------------------
# Bayesian combination tests
# ---------------------------------------------------------------------------

class TestBayesianCombine:
    def test_no_signals_zero_confidence(self):
        assert _bayesian_combine([]) == 0.0

    def test_single_high_signal(self):
        conf = _bayesian_combine(["com_au_tld"])
        assert conf == pytest.approx(SIGNAL_WEIGHTS["com_au_tld"], abs=0.001)

    def test_two_signals_compound(self):
        conf_single = _bayesian_combine(["gst_mention"])
        conf_double = _bayesian_combine(["gst_mention", "aud_currency"])
        assert conf_double > conf_single

    def test_many_signals_approach_one(self):
        all_signals = list(SIGNAL_WEIGHTS.keys())
        conf = _bayesian_combine(all_signals)
        assert conf > 0.99

    def test_confidence_never_exceeds_one(self):
        all_signals = list(SIGNAL_WEIGHTS.keys()) * 3
        conf = _bayesian_combine(all_signals)
        assert conf <= 1.0

    def test_confidence_never_below_zero(self):
        conf = _bayesian_combine(["com_au_tld", "abn_pattern"])
        assert conf >= 0.0


# ---------------------------------------------------------------------------
# Country inference tests
# ---------------------------------------------------------------------------

class TestInferCountry:
    def test_com_au_always_au(self):
        result = _infer_country("brand.com.au", ["com_au_tld"], 0.90)
        assert result == "AU"

    def test_high_confidence_au(self):
        result = _infer_country("brand.com", [], 0.80)
        assert result == "AU"

    def test_medium_confidence_au_uncertain(self):
        result = _infer_country("brand.com", [], 0.45)
        assert result == "AU?"

    def test_low_confidence_unknown(self):
        result = _infer_country("brand.com", [], 0.10)
        assert result == "unknown"


# ---------------------------------------------------------------------------
# Full detect_au integration tests (no HTTP)
# ---------------------------------------------------------------------------

class TestDetectAU:
    def test_com_au_domain_high_confidence(self):
        """A .com.au domain alone should produce high confidence without fetching HTML."""
        result = detect_au("brandname.com.au", html="")
        assert result.is_australian is True
        assert result.au_confidence >= 0.85
        assert "com_au_tld" in result.au_signals
        assert result.country_guess == "AU"

    def test_us_domain_no_content_low_confidence(self):
        result = detect_au("example.com", html="<html><body>Shop now</body></html>")
        assert result.is_australian is False
        assert result.au_confidence < 0.50

    def test_au_rich_content_high_confidence(self):
        au_html = """
        <html>
        <body>
        ABN: 12 345 678 901
        <p>Call us: +61 2 9876 5432</p>
        <p>Prices include GST. Ship Australia-wide free.</p>
        <p>We deliver to NSW, VIC, QLD, WA and SA.</p>
        <p>Pay with Afterpay. Based in Melbourne.</p>
        <footer>© 2024 Brand Pty Ltd</footer>
        </body>
        </html>
        """
        result = detect_au("brand.com", html=au_html)
        assert result.is_australian is True
        assert result.au_confidence >= 0.98
        assert len(result.au_signals) >= 6

    def test_partial_au_signals_medium_confidence(self):
        html = "<p>Free shipping to NSW and VIC. Pay with Afterpay.</p>"
        result = detect_au("brand.com", html=html)
        # afterpay + states should give meaningful confidence
        assert result.au_confidence >= 0.30

    def test_result_fields_always_populated(self):
        result = detect_au("any-domain.com", html="")
        assert isinstance(result.domain, str)
        assert isinstance(result.is_australian, bool)
        assert isinstance(result.au_confidence, float)
        assert isinstance(result.au_signals, list)
        assert isinstance(result.country_guess, str)

    def test_confidence_bounded(self):
        au_html = "ABN: 12 345 678 901 GST +61 AUD NSW VIC QLD AfterPay Pty Ltd Australia-wide"
        result = detect_au("brand.com.au", html=au_html)
        assert 0.0 <= result.au_confidence <= 1.0
