"""
Stage 11b: Loom script generator.

Generates a structured Loom script (60–90 seconds when read aloud) for each lead.
The script is grounded in real audit findings and follows a consistent narrative arc:
1. Why we looked at this brand
2. What we noticed (specific findings)
3. What it likely means operationally
4. What Prodigi can do
5. Low-friction CTA
"""
import logging
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from app.schemas.audit import AuditResult, AuditSeverity, AuditFinding
from app.schemas.outbound import LoomScript
from app.services.personalisation import llm_interface

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "loom"

# Loom-specific finding sentences (slightly more conversational than email)
FINDING_TO_LOOM_SENTENCE: dict[str, str] = {
    "WEAK_VARIANT_REPRESENTATION": (
        "several products with multiple colours or styles don't have per-variant images — "
        "so if I pick a different colour, I'm guessing what I'm going to get"
    ),
    "LOW_IMAGE_COUNT": (
        "the average product has around {metric:.0f} images — that's quite lean, "
        "especially for a {vertical} brand where visual confidence really matters"
    ),
    "INCONSISTENT_IMAGE_COUNT": (
        "some products are really well-shot with good coverage, but others — "
        "especially what looks like newer or secondary SKUs — have much less. "
        "That inconsistency is usually a signal of a production bottleneck"
    ),
    "MISSING_DETAIL_SHOTS": (
        "I'm not seeing detail or close-up shots — the kind that show texture, "
        "stitching, material finish. For a {vertical} brand that really matters "
        "because it's what convinces buyers the quality is there"
    ),
    "INCONSISTENT_BACKGROUNDS": (
        "the background treatment varies — some products are clean studio, "
        "others feel more mixed. Across a catalogue, that inconsistency "
        "chips away at the overall brand impression"
    ),
    "MIXED_ASPECT_RATIOS": (
        "there are mixed aspect ratios across products — it creates a slightly "
        "uneven grid that's worth tidying up"
    ),
    "LOW_CATALOGUE_DEPTH": (
        "overall imagery depth is fairly thin — "
        "consistent with brands where studio cost is a real constraint on "
        "how much content you can produce per SKU"
    ),
}

OPERATIONAL_IMPLICATION_LOOM: dict[str, str] = {
    "WEAK_VARIANT_REPRESENTATION": (
        "The challenge here is that if you want to fix this the traditional way, "
        "you're either shooting every colour variant — which is expensive and slow — "
        "or you're launching without proper visual coverage and eating the returns."
    ),
    "LOW_IMAGE_COUNT": (
        "Professional product photography typically runs $200 to $800 a SKU. "
        "At that cost, expanding coverage across a growing catalogue gets expensive fast. "
        "It's a really common bottleneck for brands at this stage."
    ),
    "INCONSISTENT_IMAGE_COUNT": (
        "What this usually means is the hero products got a proper shoot, "
        "but the long tail of the catalogue is under-resourced. "
        "That's revenue left on the table across your secondary SKUs."
    ),
    "MISSING_DETAIL_SHOTS": (
        "Without detail photography, the product copy has to do all the work — "
        "which is a poor substitute for visual proof, especially on mobile "
        "where buyers are making quick decisions."
    ),
}


def generate_loom_script(
    brand_name: str,
    domain: str,
    audit: AuditResult,
    vertical: Optional[str] = None,
    polish_with_llm: bool = True,
) -> LoomScript:
    """
    Generate a Loom script for a lead.
    Returns a LoomScript object with the script text.
    """
    if not audit.findings:
        return _fallback_loom(brand_name, vertical)

    prioritised = _prioritise_findings(audit)
    primary = prioritised[0] if prioritised else None
    secondary = prioritised[1] if len(prioritised) > 1 else None

    context = _build_context(
        brand_name=brand_name,
        domain=domain,
        primary=primary,
        secondary=secondary,
        vertical=vertical or "e-commerce",
    )

    script = _render_template("generic_loom.j2", context)

    llm_polished = False
    if polish_with_llm:
        polished = llm_interface.polish_loom_script(script)
        if polished != script:
            llm_polished = True
        script = polished

    return LoomScript(
        script=script.strip(),
        estimated_duration_seconds=75,
        template_used="generic_loom.j2",
        llm_polished=llm_polished,
    )


def _prioritise_findings(audit: AuditResult) -> list[AuditFinding]:
    high = [f for f in audit.findings if f.severity == AuditSeverity.HIGH]
    medium = [f for f in audit.findings if f.severity == AuditSeverity.MEDIUM]
    return (high + medium)[:2]


def _build_context(
    brand_name: str,
    domain: str,
    primary: Optional[AuditFinding],
    secondary: Optional[AuditFinding],
    vertical: str,
) -> dict:
    primary_loom = ""
    secondary_loom = ""
    operational_implication = (
        "This is the kind of thing that's easy to let slide, "
        "but it compounds — every new SKU adds to the backlog."
    )
    specific_observation = f"look at how {brand_name}'s product pages present the imagery"

    if primary:
        tmpl = FINDING_TO_LOOM_SENTENCE.get(primary.code, primary.title)
        metric = primary.metric or 0
        primary_loom = tmpl.format(
            metric=metric,
            brand_name=brand_name,
            vertical=vertical,
        )
        operational_implication = OPERATIONAL_IMPLICATION_LOOM.get(
            primary.code, operational_implication
        )
        specific_observation = _observation_for_finding(primary, brand_name)

    if secondary:
        tmpl = FINDING_TO_LOOM_SENTENCE.get(secondary.code, secondary.title)
        metric = secondary.metric or 0
        secondary_loom = tmpl.format(
            metric=metric,
            brand_name=brand_name,
            vertical=vertical,
        )

    return {
        "brand_name": brand_name,
        "domain": domain,
        "vertical": vertical,
        "primary_finding_loom": primary_loom,
        "secondary_finding_loom": secondary_loom,
        "operational_implication": operational_implication,
        "specific_observation": specific_observation,
    }


def _observation_for_finding(finding: AuditFinding, brand_name: str) -> str:
    if finding.affected_products:
        return f"look at one of these product pages — {finding.affected_products[0]}"
    return f"look at how the imagery is set up across {brand_name}'s catalogue"


def _render_template(template_name: str, context: dict) -> str:
    try:
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        return env.get_template(template_name).render(**context)
    except TemplateNotFound:
        logger.warning("Loom template not found: %s", template_name)
        return _inline_loom(context)
    except Exception as e:
        logger.error("Loom template render error: %s", e)
        return _inline_loom(context)


def _inline_loom(context: dict) -> str:
    brand = context.get("brand_name", "this brand")
    vertical = context.get("vertical", "e-commerce")
    finding = context.get("primary_finding_loom", "some imagery gaps worth addressing")
    implication = context.get(
        "operational_implication",
        "This is a common bottleneck at this stage of growth.",
    )
    return (
        f"Hey — this is a quick look at {brand}'s store.\n\n"
        f"We look at {vertical} brands on Shopify to find stores where there's "
        f"a clear product imagery opportunity. {brand} came up.\n\n"
        f"When I look at the product pages, I noticed {finding}.\n\n"
        f"{implication}\n\n"
        "Prodigi generates on-brand AI product imagery without a studio — "
        "consistent backgrounds, proper variant coverage, format-ready assets.\n\n"
        f"Happy to mock one of {brand}'s SKUs and show you what's possible. Reply if useful."
    )


def _fallback_loom(brand_name: str, vertical: Optional[str]) -> LoomScript:
    vertical_str = vertical or "e-commerce"
    script = (
        f"Hey — this is a quick look at {brand_name}'s store.\n\n"
        f"We look at {vertical_str} brands on Shopify to find stores where "
        "there's a clear product imagery opportunity.\n\n"
        "I wanted to share what I noticed and show you what Prodigi could do "
        "for your product imagery — without a studio shoot.\n\n"
        "Happy to mock one SKU and share it. Reply if that's useful."
    )
    return LoomScript(script=script, estimated_duration_seconds=60, template_used="fallback")
