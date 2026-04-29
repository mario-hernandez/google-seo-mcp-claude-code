"""SSRF guard + untrusted-content wrapper regression tests."""
from __future__ import annotations

import pytest

from google_seo_mcp.security import (
    SSRFBlocked,
    assert_url_is_public,
    mark_third_party_strings,
    wrap_untrusted,
)


# ── SSRF guard ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://172.16.5.5/",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://example.com/",
    ],
)
def test_ssrf_guard_blocks(url):
    with pytest.raises(SSRFBlocked):
        assert_url_is_public(url)


def test_ssrf_guard_allows_public():
    # Real public host — needs DNS but should succeed in test envs with internet
    assert_url_is_public("https://www.google.com/")


def test_ssrf_guard_blocks_decimal_ip_loopback():
    # 2130706433 = 127.0.0.1 in decimal
    with pytest.raises(SSRFBlocked):
        assert_url_is_public("http://2130706433/")


# ── Untrusted wrapper ───────────────────────────────────────────────


def test_wrap_untrusted_basic():
    out = wrap_untrusted("Hello")
    assert out.startswith("<untrusted-third-party-content>")
    assert out.endswith("</untrusted-third-party-content>")
    assert "Hello" in out


def test_wrap_untrusted_truncates_long():
    payload = "x" * 50_000
    out = wrap_untrusted(payload, max_bytes=1000)
    assert "[truncated]" in out
    assert len(out) < 2000


def test_wrap_untrusted_passes_non_strings():
    assert wrap_untrusted(None) is None
    assert wrap_untrusted(42) == 42
    assert wrap_untrusted(True) is True


def test_mark_third_party_strings_wraps_known_fields():
    sig = {
        "title": "Real title",
        "meta_description": "Some desc",
        "h1": ["First", "Second"],
        "og": {"title": "OG title"},
        "url": "https://example.com",  # not in untrusted set
        "html_size_bytes": 1234,        # not a string
    }
    out = mark_third_party_strings(sig)
    assert "<untrusted" in out["title"]
    assert "<untrusted" in out["meta_description"]
    assert all("<untrusted" in h for h in out["h1"])
    assert "<untrusted" in out["og"]["title"]
    # url and html_size_bytes pass through unchanged
    assert out["url"] == "https://example.com"
    assert out["html_size_bytes"] == 1234


# ── XXE / defusedxml regression ─────────────────────────────────────


def test_sitemap_diff_imports_use_defusedxml():
    """Static check: the sitemap_diff module must not import the unsafe ET."""
    import google_seo_mcp.migration.sitemap_diff as sd

    src = open(sd.__file__).read()
    assert "from defusedxml" in src
    assert "import xml.etree.ElementTree" not in src
