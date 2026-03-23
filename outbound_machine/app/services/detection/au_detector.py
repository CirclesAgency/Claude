"""
Australian e-commerce store detector.

Determines whether a domain is likely an Australian e-commerce business
using deterministic weighted signals from the domain TLD and page content.

Confidence = Bayesian combination: 1 - ∏(1 - p_i)
for all triggered signals. Each signal contributes independently; multiple
weak signals compound into high confidence.

Signal weights (probability that signal implies an AU business):
  .com.au TLD            → 0.90  (only AU entities can register)
  .net.au / .org.au      → 0.80
  .au gTLD (new 2022)    → 0.70
  ABN pattern (11 digits)→ 0.85  (Australian Business Number)
  ABN label only         → 0.70
  +61 phone prefix       → 0.72
  04XX mobile format     → 0.55  (AU mobile number format)
  AUD / A$ currency      → 0.55
  GST mention            → 0.65  (AU goods and services tax)
  2+ AU state codes      → 0.45  (NSW, VIC, QLD, etc.)
  AU postcode context    → 0.40
  Major AU cities        → 0.35
  Australia-wide shipping→ 0.50
  AfterPay / Zip Pay     → 0.45  (AU-origin BNPL brands)
  Pty Ltd suffix         → 0.45  (AU company structure)
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.utils.http_client import get_text
from app.utils.domain import base_url

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Signal weights — code → probability that this signal implies AU
# ---------------------------------------------------------------------------

SIGNAL_WEIGHTS: dict[str, float] = {
    "com_au_tld":          0.90,
    "net_au_tld":          0.80,
    "au_gtld":             0.70,
    "abn_pattern":         0.85,
    "abn_label":           0.70,
    "phone_61":            0.72,
    "au_mobile_format":    0.55,
    "aud_currency":        0.55,
    "gst_mention":         0.65,
    "au_states":           0.45,
    "au_postcode_context": 0.40,
    "au_cities":           0.35,
    "au_shipping":         0.50,
    "afterpay_zip":        0.45,
    "pty_ltd":             0.45,
}

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_ABN_FULL_RE = re.compile(
    r'\bABN[\s:]*\d{2}\s*\d{3}\s*\d{3}\s*\d{3}\b', re.IGNORECASE
)
_ABN_LABEL_RE = re.compile(r'\bABN\b', re.IGNORECASE)

_PHONE_61_RE = re.compile(r'\+61[\s\-]?\d')
_AU_MOBILE_RE = re.compile(r'\b04\d{2}[\s\-]?\d{3}[\s\-]?\d{3}\b')

_AUD_RE = re.compile(r'\bAUD\b|A\$|AU\$')
_GST_RE = re.compile(r'\bGST\b|Goods\s+and\s+Services\s+Tax', re.IGNORECASE)

_AU_STATES_RE = re.compile(r'\b(NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\b')

_AU_POSTCODE_RE = re.compile(
    r'\b(?:postcode|post\s+code|suburb)[\s:]*\d{4}\b'
    r'|\b\d{4}\s*(?:NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\b',
    re.IGNORECASE,
)
_AU_CITIES_RE = re.compile(
    r'\b(Sydney|Melbourne|Brisbane|Perth|Adelaide|Canberra|Darwin|Hobart|'
    r'Gold\s+Coast|Sunshine\s+Coast|Newcastle|Wollongong|Geelong|Cairns|Townsville)\b',
    re.IGNORECASE,
)
_AU_SHIPPING_RE = re.compile(
    r'Australia[\s\-]wide'
    r'|ship(?:ping)?\s+to\s+Australia'
    r'|free.*?Australia.*?shipping'
    r'|deliver(?:ing|y)\s+(?:across\s+)?Australia'
    r'|nationwide.*?Australia',
    re.IGNORECASE,
)
_AFTERPAY_ZIP_RE = re.compile(
    r'\b(Afterpay|After\s*pay|Zip\s*Pay|ZipCo|Zip\s*Co|Laybuy|Humm)\b',
    re.IGNORECASE,
)
_PTY_LTD_RE = re.compile(r'Pty\.?\s*Ltd\.?', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class AUDetectionResult:
    domain: str
    is_australian: bool
    au_confidence: float
    au_signals: list[str] = field(default_factory=list)
    country_guess: str = "unknown"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_au(domain: str, html: Optional[str] = None) -> AUDetectionResult:
    """
    Detect whether a domain is likely an Australian e-commerce business.

    Args:
        domain: Normalised domain (e.g. "example.com.au" or "brand.com")
        html:   Optional pre-fetched homepage HTML. If None, fetches the
                homepage; returns TLD-only result if fetch fails.

    Returns:
        AUDetectionResult with confidence 0–1, triggered signals, and
        a country_guess string ("AU", "AU?", or "unknown").
    """
    signals: list[str] = []

    # TLD signals — no HTTP required
    _check_tld_signals(domain, signals)

    # Page content signals
    if html is None:
        html = _fetch_homepage(domain)

    if html:
        _check_content_signals(html, signals)
    else:
        logger.debug("No HTML for %s — using TLD signals only", domain)

    confidence = _bayesian_combine(signals)
    country_guess = _infer_country(domain, signals, confidence)
    is_au = confidence >= 0.50

    logger.info(
        "AU detect: %s → %.2f is_au=%s signals=%s",
        domain, confidence, is_au, signals,
    )
    return AUDetectionResult(
        domain=domain,
        is_australian=is_au,
        au_confidence=round(confidence, 4),
        au_signals=signals,
        country_guess=country_guess,
    )


# ---------------------------------------------------------------------------
# Signal checkers
# ---------------------------------------------------------------------------

def _check_tld_signals(domain: str, signals: list[str]) -> None:
    d = domain.lower()
    if d.endswith(".com.au"):
        signals.append("com_au_tld")
    elif d.endswith(".net.au") or d.endswith(".org.au") or d.endswith(".edu.au"):
        signals.append("net_au_tld")
    elif d.endswith(".au"):
        # New .au gTLD — only if it's not a known .com.au sub-variant
        signals.append("au_gtld")


def _check_content_signals(html: str, signals: list[str]) -> None:
    # ABN — full pattern takes priority over label-only
    if _ABN_FULL_RE.search(html):
        signals.append("abn_pattern")
    elif _ABN_LABEL_RE.search(html):
        signals.append("abn_label")

    if _PHONE_61_RE.search(html):
        signals.append("phone_61")

    if _AU_MOBILE_RE.search(html):
        signals.append("au_mobile_format")

    if _AUD_RE.search(html):
        signals.append("aud_currency")

    if _GST_RE.search(html):
        signals.append("gst_mention")

    # Require at least 2 distinct state mentions to reduce false positives
    state_matches = _AU_STATES_RE.findall(html)
    unique_states = len(set(state_matches))
    if unique_states >= 2:
        signals.append("au_states")

    if _AU_POSTCODE_RE.search(html):
        signals.append("au_postcode_context")

    if _AU_CITIES_RE.search(html):
        signals.append("au_cities")

    if _AU_SHIPPING_RE.search(html):
        signals.append("au_shipping")

    if _AFTERPAY_ZIP_RE.search(html):
        signals.append("afterpay_zip")

    if _PTY_LTD_RE.search(html):
        signals.append("pty_ltd")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_homepage(domain: str) -> Optional[str]:
    """Fetch homepage HTML. Tries https then https://www.{domain}."""
    html = get_text(base_url(domain))
    if html is None:
        html = get_text(f"https://www.{domain}")
    return html


def _bayesian_combine(signals: list[str]) -> float:
    """Combine independent signal probabilities: 1 - ∏(1 - p_i)."""
    if not signals:
        return 0.0
    not_au_prob = 1.0
    for sig in signals:
        p = SIGNAL_WEIGHTS.get(sig, 0.0)
        not_au_prob *= (1.0 - p)
    return round(min(1.0, 1.0 - not_au_prob), 4)


def _infer_country(domain: str, signals: list[str], confidence: float) -> str:
    tld_signals = {"com_au_tld", "net_au_tld", "au_gtld"}
    if tld_signals & set(signals) or confidence >= 0.65:
        return "AU"
    if confidence >= 0.35:
        return "AU?"
    return "unknown"
