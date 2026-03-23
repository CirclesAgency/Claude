"""
Stage 8: Commercial pain hypothesis generator.

Converts audit findings into concise, commercially-grounded pain statements.
These feed directly into email and Loom personalisation.

Output: a 2–4 sentence paragraph that:
- states what we observed (factual)
- translates it into a business/operational implication
- avoids vague adjectives or overclaiming
"""
import logging
from app.schemas.audit import AuditResult, AuditSeverity

logger = logging.getLogger(__name__)

# Pain templates keyed by finding code.
# Each maps to a sentence fragment grounded in commercial implications.
PAIN_SENTENCES: dict[str, str] = {
    "LOW_IMAGE_COUNT": (
        "limited imagery per SKU, which typically constrains conversion rates "
        "and increases return rates due to insufficient shopper confidence"
    ),
    "INCONSISTENT_IMAGE_COUNT": (
        "uneven imagery coverage across the catalogue — some products well-shot, "
        "others underserved — suggesting a production bottleneck or inconsistent "
        "photography brief"
    ),
    "MISSING_DETAIL_SHOTS": (
        "a lack of detail/close-up photography, which matters most for material-led "
        "categories like apparel, accessories, and beauty where texture and finish "
        "drive purchase decisions"
    ),
    "MISSING_FRONT_BACK": (
        "insufficient angle coverage per product, making it harder for shoppers to "
        "confidently assess fit, construction, or style from all relevant views"
    ),
    "INCONSISTENT_BACKGROUNDS": (
        "visual inconsistency across the catalogue — mixed backgrounds and treatment "
        "styles undermine brand polish and create a disjointed shopping experience"
    ),
    "MIXED_ASPECT_RATIOS": (
        "mixed image aspect ratios across the product grid, which creates an uneven "
        "visual grid that can feel unfinished or low-production-value"
    ),
    "WEAK_VARIANT_REPRESENTATION": (
        "variant imagery gaps — products with multiple colours or styles lack "
        "per-variant visuals, creating friction for shoppers trying to confirm "
        "their specific choice before buying"
    ),
    "LOW_CATALOGUE_DEPTH": (
        "low catalogue imagery depth overall, consistent with a studio cost "
        "constraint or workflow bottleneck that limits how much visual content "
        "can be produced at the pace the brand needs"
    ),
}

# Operational implication templates for high-priority findings
OPERATIONAL_IMPLICATIONS: dict[str, str] = {
    "WEAK_VARIANT_REPRESENTATION": (
        "For a brand with complex variant sets, this typically means either "
        "physically photographing every colour/style (expensive and slow) "
        "or shipping products without adequate visual coverage (costly in returns)."
    ),
    "LOW_IMAGE_COUNT": (
        "Scaling a photographic studio workflow to match a growing catalogue is "
        "expensive — typically $200–$800 per SKU for professional product photography. "
        "AI-generated imagery can produce consistent, on-brand visuals at a fraction of that cost."
    ),
    "INCONSISTENT_IMAGE_COUNT": (
        "The inconsistency suggests a launch or scaling bottleneck — newer or "
        "secondary SKUs don't get the same treatment as hero products, which "
        "leaves revenue on the table across the long tail of the catalogue."
    ),
    "MISSING_DETAIL_SHOTS": (
        "Without detail shots, brands typically rely on copy to describe material "
        "and finish — a poor substitute for visual proof, especially on mobile."
    ),
}


def generate_pain_hypothesis(audit: AuditResult, brand_name: str, vertical: str | None) -> str:
    """
    Generate a concise commercial pain hypothesis from an audit result.
    Returns a 2–4 sentence string grounded in the actual findings.
    """
    if not audit.findings:
        return (
            f"{brand_name} appears to have reasonably well-resourced imagery. "
            "No significant weaknesses were identified in our audit — "
            "this may not be a strong fit for Prodigi's core value proposition right now."
        )

    # Prioritise findings by severity
    high = [f for f in audit.findings if f.severity == AuditSeverity.HIGH]
    medium = [f for f in audit.findings if f.severity == AuditSeverity.MEDIUM]
    prioritised = (high + medium)[:3]  # top 3 to keep concise

    vertical_str = f" {vertical}" if vertical else ""

    # Opening sentence: what we observed
    finding_fragments = []
    for finding in prioritised:
        fragment = PAIN_SENTENCES.get(finding.code)
        if fragment:
            finding_fragments.append(fragment)

    if not finding_fragments:
        # Fallback to raw finding titles
        finding_fragments = [f.title.lower() for f in prioritised]

    if len(finding_fragments) == 1:
        observation = (
            f"Looking at {brand_name}'s{vertical_str} catalogue, we noticed {finding_fragments[0]}."
        )
    else:
        joined = "; ".join(finding_fragments[:-1]) + f"; and {finding_fragments[-1]}"
        observation = f"Across {brand_name}'s{vertical_str} catalogue, we noticed {joined}."

    # Operational implication: pick the most relevant
    implication = ""
    for finding in prioritised:
        impl = OPERATIONAL_IMPLICATIONS.get(finding.code)
        if impl:
            implication = impl
            break

    # Closing: what Prodigi can do
    closing = (
        "Prodigi generates on-brand, consistent AI product imagery at scale — "
        "without a physical studio. Happy to mock one of your SKUs to show what "
        "this could look like on your catalogue."
    )

    parts = [observation]
    if implication:
        parts.append(implication)
    parts.append(closing)

    return " ".join(parts)
