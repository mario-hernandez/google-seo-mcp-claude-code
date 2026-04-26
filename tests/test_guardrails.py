"""Tests for the _meta provenance wrapper."""
from __future__ import annotations

import re

from google_seo_mcp.guardrails import GUARDRAIL_SUFFIX, with_meta


def test_with_meta_basic():
    out = with_meta([1, 2, 3], source="test.tool", site_url="https://example.com/")
    assert out["data"] == [1, 2, 3]
    assert out["_meta"]["source"] == "test.tool"
    assert out["_meta"]["site_url"] == "https://example.com/"
    assert "fetched_at" in out["_meta"]
    # Should be ISO 8601 with Z suffix
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", out["_meta"]["fetched_at"])
    assert out["_meta"]["fetched_at"].endswith("Z")


def test_with_meta_property_only():
    out = with_meta({}, source="ga4.test", property="properties/123")
    assert out["_meta"]["property"] == "properties/123"
    assert "site_url" not in out["_meta"]


def test_with_meta_cross_platform():
    """Cross-platform tools include both site_url and property."""
    out = with_meta(
        {},
        source="cross.test",
        site_url="https://example.com/",
        property="properties/123",
        period={"gsc": {"start": "2026-01-01", "end": "2026-01-28"}},
    )
    assert out["_meta"]["site_url"] == "https://example.com/"
    assert out["_meta"]["property"] == "properties/123"
    assert out["_meta"]["period"]["gsc"]["start"] == "2026-01-01"


def test_with_meta_extra():
    out = with_meta(
        [],
        source="test",
        property="properties/1",
        extra={"attribution_model": "click_share", "pages_dropped_due_to_filter_cap": 5},
    )
    assert out["_meta"]["attribution_model"] == "click_share"
    assert out["_meta"]["pages_dropped_due_to_filter_cap"] == 5


def test_guardrail_suffix_present_and_useful():
    """Check the suffix is non-empty and warns about hallucinations."""
    assert "speculate" in GUARDRAIL_SUFFIX.lower()
    assert "_meta" in GUARDRAIL_SUFFIX
    assert len(GUARDRAIL_SUFFIX) > 100
