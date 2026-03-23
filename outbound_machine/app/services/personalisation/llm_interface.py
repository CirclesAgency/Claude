"""
LLM interface for optional personalisation polishing.

When ENABLE_LLM=true, this polishes template-generated emails/Loom scripts
using a real LLM. When disabled, the template output is returned as-is.

Pluggable: supports anthropic and openai providers.
The system ALWAYS works without an LLM key — LLM polish is additive, not required.
"""
import logging
from typing import Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)

POLISH_SYSTEM_PROMPT = """You are a senior growth marketer at Prodigi — an AI-powered product imagery
platform for e-commerce brands. You write sharp, credible, founder-led outbound emails.

Your style:
- Direct and observant. No fluff.
- Grounded in real findings from the brand's own store.
- Short paragraphs. No bullet points in emails.
- Never overclaim. Never use cringe sales language.
- CTA is always low-friction: "happy to mock one SKU", "can run 3 products", etc.
- Tone: peer-to-peer, not vendor-to-prospect.

Only lightly polish the provided draft. Preserve all factual observations.
Do not change the CTA. Keep total length under 200 words."""


def polish_email(subject: str, body: str) -> tuple[str, str]:
    """
    Optionally polish an email draft using an LLM.
    Returns (polished_subject, polished_body).
    If LLM is disabled or fails, returns the original.
    """
    if not settings.enable_llm:
        return subject, body

    try:
        prompt = (
            f"Subject: {subject}\n\n"
            f"Body:\n{body}\n\n"
            "Polish this email to be sharper and more natural. "
            "Return ONLY the polished email in the format:\n"
            "SUBJECT: <subject>\n\nBODY:\n<body>"
        )
        response = _call_llm(prompt)
        if not response:
            return subject, body

        # Parse response
        lines = response.strip().split("\n")
        new_subject = subject
        new_body_lines = []
        in_body = False
        for line in lines:
            if line.startswith("SUBJECT:"):
                new_subject = line.replace("SUBJECT:", "").strip()
            elif line.startswith("BODY:"):
                in_body = True
            elif in_body:
                new_body_lines.append(line)

        new_body = "\n".join(new_body_lines).strip() or body
        return new_subject, new_body

    except Exception as e:
        logger.warning("LLM email polish failed: %s", e)
        return subject, body


def polish_loom_script(script: str) -> str:
    """
    Optionally polish a Loom script using an LLM.
    Returns polished script or original on failure.
    """
    if not settings.enable_llm:
        return script

    try:
        prompt = (
            f"Loom script:\n{script}\n\n"
            "Polish this Loom script to be more natural and conversational. "
            "Keep it under 90 seconds when spoken aloud (~180 words). "
            "Return only the polished script text."
        )
        response = _call_llm(prompt)
        return response.strip() if response else script
    except Exception as e:
        logger.warning("LLM Loom polish failed: %s", e)
        return script


def _call_llm(prompt: str) -> Optional[str]:
    """Dispatch to the configured LLM provider."""
    provider = settings.llm_provider.lower()
    if provider == "anthropic":
        return _call_anthropic(prompt)
    elif provider == "openai":
        return _call_openai(prompt)
    else:
        logger.warning("Unknown LLM provider: %s", provider)
        return None


def _call_anthropic(prompt: str) -> Optional[str]:
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping LLM polish")
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = client.messages.create(
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            system=POLISH_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text if message.content else None
    except Exception as e:
        logger.error("Anthropic API call failed: %s", e)
        return None


def _call_openai(prompt: str) -> Optional[str]:
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — skipping LLM polish")
        return None
    try:
        import openai
        client = openai.OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=settings.llm_max_tokens,
            messages=[
                {"role": "system", "content": POLISH_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content if response.choices else None
    except Exception as e:
        logger.error("OpenAI API call failed: %s", e)
        return None
