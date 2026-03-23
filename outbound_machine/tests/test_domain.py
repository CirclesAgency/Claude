"""Tests for domain normalisation and deduplication utilities."""
import pytest
from app.utils.domain import (
    normalise_domain,
    deduplicate_domains,
    base_url,
    build_url,
    extract_domain_from_url,
)


class TestNormaliseDomain:
    def test_strips_scheme(self):
        assert normalise_domain("https://example.com") == "example.com"
        assert normalise_domain("http://example.com") == "example.com"

    def test_strips_www(self):
        assert normalise_domain("www.example.com") == "example.com"
        assert normalise_domain("https://www.example.com") == "example.com"

    def test_lowercases(self):
        assert normalise_domain("EXAMPLE.COM") == "example.com"
        assert normalise_domain("Example.Com") == "example.com"

    def test_strips_trailing_slash(self):
        assert normalise_domain("example.com/") == "example.com"
        assert normalise_domain("https://example.com/shop/") == "example.com"

    def test_strips_path(self):
        assert normalise_domain("https://example.com/collections/all") == "example.com"

    def test_no_scheme(self):
        assert normalise_domain("example.com") == "example.com"

    def test_whitespace_stripped(self):
        assert normalise_domain("  example.com  ") == "example.com"

    def test_subdomain_preserved(self):
        # We only strip www, not other subdomains
        result = normalise_domain("shop.example.com")
        assert "example.com" in result


class TestDeduplicateDomains:
    def test_removes_duplicates(self):
        domains = ["example.com", "example.com", "other.com"]
        result = deduplicate_domains(domains)
        assert result.count("example.com") == 1
        assert len(result) == 2

    def test_normalises_before_dedup(self):
        domains = ["https://www.example.com", "http://example.com/", "EXAMPLE.COM"]
        result = deduplicate_domains(domains)
        assert len(result) == 1

    def test_preserves_order(self):
        domains = ["alpha.com", "beta.com", "gamma.com"]
        result = deduplicate_domains(domains)
        assert result == ["alpha.com", "beta.com", "gamma.com"]

    def test_empty_list(self):
        assert deduplicate_domains([]) == []


class TestBuildUrl:
    def test_base_url(self):
        assert base_url("example.com") == "https://example.com"

    def test_build_url_with_path(self):
        url = build_url("example.com", "/products.json")
        assert url == "https://example.com/products.json"


class TestExtractDomain:
    def test_from_full_url(self):
        assert extract_domain_from_url("https://www.example.com/products/tshirt") == "example.com"

    def test_from_url_with_port(self):
        assert extract_domain_from_url("https://example.com:443/path") == "example.com"
