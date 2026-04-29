"""Regression tests for v0.7.1 stability fixes (panel #4 — bugs and instabilities)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from google_seo_mcp.guardrails import _json_safe, with_meta


# ── _json_safe coercion (MCP protocol hygiene) ──────────────────────


def test_json_safe_passes_primitives():
    assert _json_safe(None) is None
    assert _json_safe(True) is True
    assert _json_safe(42) == 42
    assert _json_safe(3.14) == 3.14
    assert _json_safe("hello") == "hello"


def test_json_safe_coerces_datetime():
    out = _json_safe(datetime(2026, 4, 29, 10, 30))
    assert out == "2026-04-29T10:30:00"


def test_json_safe_coerces_date():
    out = _json_safe(date(2026, 4, 29))
    assert out == "2026-04-29"


def test_json_safe_coerces_set_to_sorted_list():
    out = _json_safe({"b", "a", "c"})
    assert out == ["a", "b", "c"]


def test_json_safe_coerces_path():
    p = Path("/tmp/example.json")
    assert _json_safe(p) == "/tmp/example.json"


def test_json_safe_coerces_decimal_to_float():
    assert _json_safe(Decimal("3.14")) == 3.14


def test_json_safe_coerces_bytes_with_replace():
    assert _json_safe(b"hello") == "hello"
    # Invalid utf-8 doesn't crash — replaced with U+FFFD.
    out = _json_safe(b"\xff\xfe")
    assert isinstance(out, str)


def test_json_safe_walks_nested_dict_and_list():
    out = _json_safe({"d": datetime(2026, 1, 1), "items": [{"s": {"a", "b"}}]})
    assert out["d"] == "2026-01-01T00:00:00"
    assert out["items"][0]["s"] == ["a", "b"]


def test_json_safe_coerces_numpy_scalars_via_item():
    class FakeNumpy:
        def item(self):
            return 42

    assert _json_safe(FakeNumpy()) == 42


def test_json_safe_falls_back_to_str_on_unknown():
    class Weird:
        def __str__(self):
            return "weird-instance"

    assert _json_safe(Weird()) == "weird-instance"


def test_with_meta_passes_payload_through_json_safe():
    payload = {"timestamp": datetime(2026, 4, 29), "tags": {"a", "b"}}
    out = with_meta(payload, source="test")
    assert out["data"]["timestamp"] == "2026-04-29T00:00:00"
    assert out["data"]["tags"] == ["a", "b"]
    # _meta itself is always JSON-safe.
    assert isinstance(out["_meta"]["fetched_at"], str)


# ── Float empty-string regression ───────────────────────────────────


def test_health_handles_ga4_empty_sessions(monkeypatch):
    """`float("")` would crash multi-property/health when GA4 returns empty
    metric values. Verifies the `or 0` guard works."""
    from google_seo_mcp.crossplatform import health

    # Fake the GSC + GA4 paths used by traffic_health_check.
    monkeypatch.setattr(
        health, "query_search_analytics", lambda *a, **k: [{"clicks": 0, "impressions": 0, "ctr": 0, "position": 0}]
    )
    monkeypatch.setattr(
        health, "aggregate_totals", lambda rows: {"clicks": 0, "impressions": 0, "ctr": 0, "position": 0}
    )
    monkeypatch.setattr(
        health, "run_report",
        lambda *a, **k: {"totals": [{"sessions": ""}], "rows": []},
    )
    monkeypatch.setattr(health, "get_webmasters", lambda: object())
    monkeypatch.setattr(health, "normalize_property", lambda x: f"properties/{x}")

    # Should NOT raise ValueError on float("").
    result = health.traffic_health_check("https://example.com/", "123", days=7)
    data = result["data"]
    assert data["ga4_organic_sessions"] == 0


# ── auth atomic write ───────────────────────────────────────────────


def test_atomic_write_text_creates_file(tmp_path):
    from google_seo_mcp.auth import _atomic_write_text

    target = tmp_path / "token.json"
    _atomic_write_text(target, '{"refresh_token": "x"}')
    assert target.read_text() == '{"refresh_token": "x"}'


def test_atomic_write_text_does_not_leak_temp_on_failure(tmp_path, monkeypatch):
    from google_seo_mcp.auth import _atomic_write_text

    target = tmp_path / "token.json"

    # Simulate a failure during the write to verify the temp file is cleaned.
    real_replace = __import__("os").replace

    def boom(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr("os.replace", boom)
    with pytest.raises(OSError):
        _atomic_write_text(target, "data")
    monkeypatch.setattr("os.replace", real_replace)

    leftovers = list(tmp_path.glob("token.json.*"))
    assert leftovers == [], f"temp file leaked: {leftovers}"


# ── Credentials fingerprint detects account rotation ────────────────


def test_credentials_fingerprint_changes_on_env_swap(monkeypatch):
    from google_seo_mcp.auth import _current_credentials_fingerprint

    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/path/to/account-A.json")
    fp_a = _current_credentials_fingerprint()
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/path/to/account-B.json")
    fp_b = _current_credentials_fingerprint()
    assert fp_a != fp_b


# ── equity_report URL normalisation ─────────────────────────────────


def test_equity_url_norm_collapses_trailing_slash_and_case():
    from google_seo_mcp.migration.equity_report import _norm_url

    assert _norm_url("https://Example.com/Post/") == "https://example.com/Post"
    assert _norm_url("https://example.com/post") == "https://example.com/post"
    # Root path '/' is preserved.
    assert _norm_url("https://example.com/") == "https://example.com/"
    # Fragment dropped, query kept.
    assert _norm_url("https://example.com/x?p=1#section") == "https://example.com/x?p=1"


# ── rapidfuzz tuple guard (defensive against API drift) ─────────────


def test_redirects_plan_handles_no_match_gracefully():
    from google_seo_mcp.migration.redirects_plan import migration_redirects_plan

    # totally dissimilar slugs — fuzzy match should return None and the
    # tool must not crash on tuple unpacking.
    result = migration_redirects_plan(
        old_urls=["https://a.com/totally-unique-string-zzz"],
        new_urls=["https://b.com/another-completely-different-yyy"],
        min_score=95.0,  # very strict so no fuzzy match
    )
    assert result["unmatched_old_count"] == 1
    assert result["plan"] == []
