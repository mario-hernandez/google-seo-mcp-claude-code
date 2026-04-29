"""Tests for GSC analytics helpers."""
from __future__ import annotations

from google_seo_mcp.gsc.analytics import (
    DEFAULT_CTR_BENCHMARKS,
    aggregate_totals,
    ctr_benchmarks,
    expected_ctr,
)


def test_aggregate_totals_empty():
    out = aggregate_totals([])
    assert out["clicks"] == 0
    assert out["impressions"] == 0
    assert out["ctr"] == 0.0
    assert out["position"] == 0.0


def test_aggregate_totals_single():
    rows = [{"clicks": 100, "impressions": 1000, "ctr": 0.10, "position": 5.0}]
    out = aggregate_totals(rows)
    assert out["clicks"] == 100
    assert out["impressions"] == 1000
    assert out["ctr"] == 0.10
    assert out["position"] == 5.0


def test_aggregate_totals_position_weighted_by_impressions():
    """Position should be weighted by impressions, not a simple mean."""
    rows = [
        {"clicks": 0, "impressions": 1000, "position": 1.0},  # heavy weight
        {"clicks": 0, "impressions": 10, "position": 100.0},  # tiny weight
    ]
    out = aggregate_totals(rows)
    assert 0.5 < out["position"] < 2.5  # close to 1.0, not anywhere near 50


def test_aggregate_totals_zero_impressions_no_crash():
    rows = [{"clicks": 0, "impressions": 0, "position": 5.0}]
    out = aggregate_totals(rows)
    assert out["ctr"] == 0.0
    assert out["position"] == 0.0


def test_expected_ctr_top_position():
    assert expected_ctr(1) == DEFAULT_CTR_BENCHMARKS[0]


def test_expected_ctr_position_below_one():
    """Pos < 1 should be treated as pos 1 (best CTR benchmark)."""
    assert expected_ctr(0.5) == DEFAULT_CTR_BENCHMARKS[0]


def test_expected_ctr_position_beyond_table():
    """Pos > 10 should fall back to last benchmark, not crash."""
    assert expected_ctr(50) == DEFAULT_CTR_BENCHMARKS[-1]


def test_expected_ctr_uses_floor():
    """Position 4.7 → idx 3 (= benchmark[3], position 4)."""
    assert expected_ctr(4.7) == DEFAULT_CTR_BENCHMARKS[3]


def test_ctr_benchmarks_env_override(monkeypatch):
    monkeypatch.setenv("GSC_CTR_BENCHMARKS", "0.5,0.3,0.2,0.1,0.05")
    out = ctr_benchmarks()
    # First 5 come from env override, the rest pad from defaults so that
    # ``expected_ctr(position)`` never IndexErrors on positions 6-10.
    assert out[:5] == [0.5, 0.3, 0.2, 0.1, 0.05]
    assert len(out) == len(DEFAULT_CTR_BENCHMARKS)
    assert out[5:] == DEFAULT_CTR_BENCHMARKS[5:]


def test_ctr_benchmarks_short_env_does_not_indexerror(monkeypatch):
    """Regression: env override with <10 floats used to silently index out
    of range when expected_ctr() was asked about positions 6-10."""
    from google_seo_mcp.gsc.analytics import expected_ctr

    monkeypatch.setenv("GSC_CTR_BENCHMARKS", "0.3,0.2,0.1")
    # Position 7 used to crash with IndexError on parsed[6]; now pads.
    val = expected_ctr(7)
    assert isinstance(val, float)


def test_ctr_benchmarks_invalid_env_falls_back(monkeypatch):
    monkeypatch.setenv("GSC_CTR_BENCHMARKS", "garbage,not,floats")
    out = ctr_benchmarks()
    assert out == DEFAULT_CTR_BENCHMARKS
