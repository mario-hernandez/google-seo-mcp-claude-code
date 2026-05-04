"""Regression tests for the JSON-LD block detector in prerender._extract_signals.

Reported in a real-world technical review: pages with whitespace before the
closing `</script>` tag, with whitespace around `type=`, or with extra HTML
attributes (data-react-helmet, nonce) were occasionally undetected by the
original strict regex. v0.8.3 hardened the pattern; these tests lock in the
behavior across all the variants seen in the wild.

For rigorous JSON-LD parsing use ``schema_extract_url`` (extruct-based).
This regex is a fast heuristic count for ``prerender_signals``.
"""
from __future__ import annotations

from google_seo_mcp.migration.prerender import _extract_signals


def _count(html: str) -> int:
    return _extract_signals(html, "http://test.local/")["jsonld_blocks"]


def test_canonical_form() -> None:
    assert _count('<script type="application/ld+json">{}</script>') == 1


def test_single_quotes() -> None:
    assert _count("<script type='application/ld+json'>{}</script>") == 1


def test_extra_attrs_before_type() -> None:
    # data-react-helmet="true" and nonce="abc" are common in SSR frameworks
    html = (
        '<script data-react-helmet="true" nonce="abc" '
        'type="application/ld+json">{}</script>'
    )
    assert _count(html) == 1


def test_extra_attrs_after_type() -> None:
    html = '<script type="application/ld+json" nonce="abc">{}</script>'
    assert _count(html) == 1


def test_whitespace_around_equals() -> None:
    html = '<script type = "application/ld+json">{}</script>'
    assert _count(html) == 1


def test_whitespace_in_closing_tag() -> None:
    # Some pretty-printers emit `</script >` with a trailing space before `>`
    html = '<script type="application/ld+json">{}</script >'
    assert _count(html) == 1


def test_multiline_attributes() -> None:
    html = (
        '<script\n'
        '  type="application/ld+json"\n'
        '>{\n'
        '  "@type":"Article"\n'
        '}</script>'
    )
    assert _count(html) == 1


def test_multiple_blocks_counted_independently() -> None:
    html = (
        '<script type="application/ld+json">{}</script>'
        '<script type="application/ld+json">{}</script>'
    )
    assert _count(html) == 2


def test_no_schema_returns_zero() -> None:
    assert _count("<html><body>plain content</body></html>") == 0


def test_does_not_match_other_script_types() -> None:
    # Plain `application/json` (without the +ld) is a different MIME type
    # and must NOT be counted as JSON-LD schema.
    html = '<script type="application/json">{}</script>'
    assert _count(html) == 0


def test_does_not_match_javascript() -> None:
    html = '<script>console.log("not schema");</script>'
    assert _count(html) == 0
