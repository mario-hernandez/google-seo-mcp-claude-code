"""Tests for auth helpers (no network calls — just pure logic)."""
from __future__ import annotations

import os
import pytest

from google_seo_mcp.auth import SCOPES_READ, SCOPES_WRITE, _scopes, normalize_property


def test_normalize_property_int():
    assert normalize_property(123) == "properties/123"


def test_normalize_property_str_numeric():
    assert normalize_property("123") == "properties/123"


def test_normalize_property_str_canonical():
    assert normalize_property("properties/456") == "properties/456"


def test_normalize_property_strips_whitespace():
    assert normalize_property("  789 ") == "properties/789"


def test_normalize_property_invalid():
    with pytest.raises(ValueError, match="Invalid property_id"):
        normalize_property("not-a-property")
    with pytest.raises(ValueError):
        normalize_property("")


def test_scopes_read_only_by_default(monkeypatch):
    monkeypatch.delenv("GSC_ALLOW_DESTRUCTIVE", raising=False)
    assert _scopes() == SCOPES_READ
    # Both read scopes must be requested even in read mode
    assert any("webmasters.readonly" in s for s in SCOPES_READ)
    assert any("analytics.readonly" in s for s in SCOPES_READ)


def test_scopes_write_when_destructive_enabled(monkeypatch):
    monkeypatch.setenv("GSC_ALLOW_DESTRUCTIVE", "true")
    assert _scopes() == SCOPES_WRITE
    # Write mode must include both webmasters write and analytics read
    assert any(s == "https://www.googleapis.com/auth/webmasters" for s in SCOPES_WRITE)
    assert any("analytics.readonly" in s for s in SCOPES_WRITE)


def test_scopes_destructive_does_not_upgrade_analytics(monkeypatch):
    """GSC_ALLOW_DESTRUCTIVE only widens the GSC scope, not GA4."""
    monkeypatch.setenv("GSC_ALLOW_DESTRUCTIVE", "true")
    scopes = _scopes()
    # GA4 stays read-only even when GSC is writable.
    assert "https://www.googleapis.com/auth/analytics" not in scopes  # would be too wide
    assert "https://www.googleapis.com/auth/analytics.readonly" in scopes
