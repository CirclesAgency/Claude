"""
Stage 11a: Email draft generator.

Generates personalised email subjects and bodies from:
1. Jinja2 templates (always works, no API key needed)
2. Optional LLM polish pass

Template selection is vertical-aware. All facts are grounded in real audit findings.
"""
import logging
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from app.schemas.audit import AuditResult, AuditSeverity, AuditFinding
from app.schemas.outbound import EmailDraft
from app.services.personalisation import llm_interface

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "email"

# Vertical → template filename
VERTICAL_TEMPLATE_MAP = {
    "apparel": "apparel_email.j2",
    "clothing": "apparel_email.j2",
    "fashion": "apparel_email.j2",
    "beauty": "beauty_email.j2",
    "skincare": "beauty_email.j2",
    "cosmetics": "beauty_email.j2",
}

# Subject line templates keyed by primary finding code
SUBJECT_TEMPLATES: dict[str, str] = {
    "WEAK_VARIANT_REPRESENTATION": (
        "Quick note on {brand_name}'s variant imagery"
    ),
    "LOW_IMAGE_COUNT": (
        "Spotted something on {brand_name}'s product pages"
    ),
    "INCONSISTENT_IMAGE_COUNT": (
        "{brand_name} — quick observation on your catalogue imagery"
    ),
    "MISSING_DETAIL_SHOTS": (
        "Quick thought on {brand_name}'s product detail coverage"
    ),
    "INCONSISTENT_BACKGROUNDS": (
        "Noticed something about {brand_name}'s imagery consistency"
    ),
    "LOW_CATALOGUE_DEPTH": (
        "{brand_name} — a thought on scaling your product imagery"
    ),
}

DEFAULT_SUBJECT = "Noticed something on {brand_name}'s product pages"

# Sentence fragments per finding code for email body
FINDING_TO_EMAIL_SENTENCE: dict[str, str] = {
    "WEAK_VARIANT_REPRESENTATION": (
        "Several of your products have multiple colour or style options, but the imagery "
        "doesn't show each variant — shoppers have to guess what they're getting. "
        "That creates friction right at the point of purchase."
    ),
    "LOW_IMAGE_COUNT": (
        "A number of your products are running with {metric:.0f} images or fewer — "
        "below what's typically needed to give shoppers the confidence to buy, "
        "especially on mobile."
    ),
    "INCONSISTENT_IMAGE_COUNT": (
        "Image count varies quite a bit across your catalogue — some products are "
        "well-covered, others much less so. It suggests the secondary SKUs aren't "
        "getting the same treatment as your hero products."
    ),
    "MISSING_DETAIL_SHOTS": (
        "Your products don't appear to have much in the way of detail or close-up "
        "photography. For a {vertical} brand, that's where buyers confirm material, "
        "finish, and quality — and it's often what tips the purchase decision."
    ),
    "INCONSISTENT_BACKGROUNDS": (
        "The imagery treatment varies across your catalogue — some products have "
        "clean studio shots, others look more lifestyle or mixed. "
        "The inconsistency makes the store feel less polished than the products deserve."
    ),
    "MIXED_ASPECT_RATIOS": (
        "Your product grid shows mixed aspect ratios, which creates a visually "
        "uneven layout. It's a small thing, but it affects the overall store impression."
    ),
    "LOW_CATALOGUE_DEPTH": (
        "Across the catalogue, imagery depth is fairly thin — consistent with brands "
        "at a stage where studio costs are a real constraint on how much content "
        "can be produced."
    ),
}

CTA_BY_FINDING: dict[str, str] = {
    "WEAK_VARIANT_REPRESENTATION": (
        "We could generate per-variant imagery for a few of your SKUs so you can "
        "see how they'd look with proper visual coverage."
    ),
    "LOW_IMAGE_COUNT": (
        "Happy to run 3 of your products through Prodigi and show you what "
        "expanded imagery coverage looks like."
    ),
    "LOW_CATALOGUE_DEPTH": (
        "Worth showing what a consistent, on-brand set of product images would look "
        "like across a section of your catalogue."
    ),
}

DEFAULT_CTA = (
    "Happy to mock one of your SKUs and show you what this could look like on your store."
)


def generate_email(
    brand_name: str,
    domain: str,
    audit: AuditResult,
    vertical: Optional[str] = None,
    contact_name: Optional[str] = None,
    sender_name: str = "The Prodigi team",
    polish_with_llm: bool = True,
) -> EmailDraft:
    """
    Generate a personalised email draft for a lead.
    Returns an EmailDraft with subject and body.
    """
    if not audit.findings:
        return _fallback_email(brand_name, contact_name, sender_name)

    # Select primary and secondary findings
    prioritised = _prioritise_findings(audit)
    primary = prioritised[0] if prioritised else None
    secondary = prioritised[1] if len(prioritised) > 1 else None

    # Build context for template
    context = _build_context(
        brand_name=brand_name,
        domain=domain,
        primary=primary,
        secondary=secondary,
        vertical=vertical or "",
        contact_name=contact_name,
        sender_name=sender_name,
    )

    # Render template
    template_name = _select_template(vertical)
    body = _render_template(template_name, context)

    # Build subject
    subject = _build_subject(brand_name, primary)

    # Optional LLM polish
    llm_polished = False
    if polish_with_llm:
        polished_subject, polished_body = llm_interface.polish_email(subject, body)
        if polished_subject != subject or polished_body != body:
            llm_polished = True
        subject, body = polished_subject, polished_body

    return EmailDraft(
        subject=subject,
        body=body.strip(),
        template_used=template_name,
        llm_polished=llm_polished,
    )


def _prioritise_findings(audit: AuditResult) -> list[AuditFinding]:
    high = [f for f in audit.findings if f.severity == AuditSeverity.HIGH]
    medium = [f for f in audit.findings if f.severity == AuditSeverity.MEDIUM]
    return (high + medium)[:3]


def _build_context(
    brand_name: str,
    domain: str,
    primary: Optional[AuditFinding],
    secondary: Optional[AuditFinding],
    vertical: str,
    contact_name: Optional[str],
    sender_name: str,
) -> dict:
    primary_sentence = ""
    secondary_sentence = ""
    cta_sentence = DEFAULT_CTA

    if primary:
        template_str = FINDING_TO_EMAIL_SENTENCE.get(primary.code, primary.title)
        metric = primary.metric or 0
        primary_sentence = template_str.format(
            metric=metric,
            brand_name=brand_name,
            vertical=vertical or "e-commerce",
        )
        cta_sentence = CTA_BY_FINDING.get(primary.code, DEFAULT_CTA)

    if secondary:
        template_str = FINDING_TO_EMAIL_SENTENCE.get(secondary.code, secondary.title)
        metric = secondary.metric or 0
        secondary_sentence = template_str.format(
            metric=metric,
            brand_name=brand_name,
            vertical=vertical or "e-commerce",
        )

    return {
        "brand_name": brand_name,
        "domain": domain,
        "vertical": vertical,
        "contact_name": contact_name,
        "sender_name": sender_name,
        "primary_finding": primary_sentence,
        "secondary_finding": secondary_sentence,
        "cta_sentence": cta_sentence,
    }


def _build_subject(brand_name: str, primary: Optional[AuditFinding]) -> str:
    if primary:
        template = SUBJECT_TEMPLATES.get(primary.code, DEFAULT_SUBJECT)
    else:
        template = DEFAULT_SUBJECT
    return template.format(brand_name=brand_name)


def _select_template(vertical: Optional[str]) -> str:
    if vertical:
        return VERTICAL_TEMPLATE_MAP.get(vertical.lower().strip(), "generic_email.j2")
    return "generic_email.j2"


def _render_template(template_name: str, context: dict) -> str:
    try:
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        template = env.get_template(template_name)
        return template.render(**context)
    except TemplateNotFound:
        logger.warning("Template not found: %s — using inline fallback", template_name)
        return _inline_fallback_body(context)
    except Exception as e:
        logger.error("Template render error: %s", e)
        return _inline_fallback_body(context)


def _inline_fallback_body(context: dict) -> str:
    greeting = context.get("contact_name") or "Hi"
    brand = context.get("brand_name", "your brand")
    primary = context.get("primary_finding", "a product imagery opportunity")
    cta = context.get("cta_sentence", DEFAULT_CTA)
    sender = context.get("sender_name", "The Prodigi team")
    return (
        f"{greeting},\n\n"
        f"I was looking at {brand}'s store and noticed {primary}\n\n"
        f"{cta}\n\n"
        f"Worth a quick look?\n\n{sender}\nProdigi"
    )


def _fallback_email(
    brand_name: str,
    contact_name: Optional[str],
    sender_name: str,
) -> EmailDraft:
    greeting = contact_name or "Hi"
    subject = f"Quick thought on {brand_name}'s product imagery"
    body = (
        f"{greeting},\n\n"
        f"I was looking at {brand_name}'s store and thought it might be worth "
        "showing you what Prodigi can do for product imagery at scale.\n\n"
        "Happy to mock one of your SKUs and share it — no obligation.\n\n"
        f"{sender_name}\nProdigi"
    )
    return EmailDraft(subject=subject, body=body, template_used="fallback")
