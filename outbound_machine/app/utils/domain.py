"""
Domain utility functions: normalisation, deduplication, URL construction.
"""
import re
from urllib.parse import urlparse, urljoin


def normalise_domain(raw: str) -> str:
    """
    Strip scheme, www, trailing slashes, paths, and lowercase.
    'https://www.Example.com/shop/' → 'example.com'
    """
    raw = raw.strip().lower()
    # Add scheme if missing so urlparse works correctly
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = parsed.netloc or parsed.path
    # Remove www.
    host = re.sub(r"^www\.", "", host)
    # Remove port
    host = host.split(":")[0]
    return host.rstrip("/")


def base_url(domain: str) -> str:
    """Return the https base URL for a normalised domain."""
    return f"https://{domain}"


def build_url(domain: str, path: str) -> str:
    """Construct an absolute URL for the given domain and path."""
    return urljoin(base_url(domain), path)


def deduplicate_domains(domains: list[str]) -> list[str]:
    """
    Return a deduplicated, normalised list preserving first-occurrence order.
    """
    seen: set[str] = set()
    result: list[str] = []
    for d in domains:
        norm = normalise_domain(d)
        if norm and norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def extract_domain_from_url(url: str) -> str:
    """Extract and normalise the domain from a full URL."""
    parsed = urlparse(url)
    host = parsed.netloc or ""
    host = re.sub(r"^www\.", "", host).split(":")[0].lower()
    return host
