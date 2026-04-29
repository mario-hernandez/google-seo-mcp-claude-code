"""Regression tests for ga4_anomalies edge cases (sigma=0, near-zero variance)."""
from __future__ import annotations

from google_seo_mcp.ga4.tools import intelligence as ga_intel


def test_anomalies_skips_zero_variance(monkeypatch):
    """All-identical series → sigma=0 → no findings (no division by zero)."""
    rows = [
        {"keys": [f"2026-04-{i:02d}"], "date": f"2026-04-{i:02d}", "sessions": 100}
        for i in range(1, 30)
    ]
    monkeypatch.setattr(
        ga_intel,
        "run_report",
        lambda *a, **k: {"rows": [{"date": r["date"], "sessions": r["sessions"]} for r in rows]},
    )
    monkeypatch.setattr(ga_intel, "normalize_property", lambda x: f"properties/{x}")

    result = ga_intel.anomalies("123", metric="sessions", days=30, z_threshold=2.0)
    assert result["data"] == []  # zero variance → no findings


def test_anomalies_skips_near_zero_variance(monkeypatch):
    """A series of [100, 100.001, 100, ...] with one 500 outlier must NOT flag.

    Regression: before fix, sigma≈1e-3 made Z explode to millions on the outlier.
    """
    base = [{"date": f"2026-04-{i:02d}", "sessions": 100.001 if i % 2 else 100.0} for i in range(1, 29)]
    outlier = [{"date": "2026-04-29", "sessions": 500.0}]
    rows = base + outlier
    monkeypatch.setattr(ga_intel, "run_report", lambda *a, **k: {"rows": rows})
    monkeypatch.setattr(ga_intel, "normalize_property", lambda x: f"properties/{x}")

    result = ga_intel.anomalies("123", metric="sessions", days=30, z_threshold=2.0)
    # The outlier of 500 vs baseline ~100 IS a real anomaly — sigma≈0.0005, mu=100,
    # threshold = max(0.5, mu*0.01) = 1.0. sigma < threshold → skipped.
    assert result["data"] == []


def test_anomalies_detects_real_anomaly(monkeypatch):
    """Sanity check: a clear spike in a varied series IS detected."""
    # Mean ~100, std ~15, real outlier at 200 → Z ~6.6 on raw, but leave-one-out
    # excludes the outlier from baseline, so the test day's Z is even higher.
    rows = [
        {"date": f"2026-04-{i:02d}", "sessions": 100 + ((i * 7) % 30) - 15}
        for i in range(1, 29)
    ] + [{"date": "2026-04-29", "sessions": 200}]
    monkeypatch.setattr(ga_intel, "run_report", lambda *a, **k: {"rows": rows})
    monkeypatch.setattr(ga_intel, "normalize_property", lambda x: f"properties/{x}")

    # Run with deseasonalize=False to compare raw values (the test series
    # has an artificial weekly cycle that STL would correctly remove,
    # picking up cycle-residuals as anomalies too — for this sanity check
    # we only want the absolute outlier).
    result = ga_intel.anomalies(
        "123", metric="sessions", days=30, z_threshold=2.0,
        deseasonalize=False,
    )
    findings = result["data"]
    assert len(findings) >= 1
    # The biggest finding should be the spike on 2026-04-29
    top = findings[0]
    assert top["date"] == "2026-04-29"
    assert top["type"] == "spike"


def test_anomalies_short_series_no_crash(monkeypatch):
    """Series with fewer than 5 points must skip the segment, not crash."""
    rows = [{"date": "2026-04-01", "sessions": 100}, {"date": "2026-04-02", "sessions": 200}]
    monkeypatch.setattr(ga_intel, "run_report", lambda *a, **k: {"rows": rows})
    monkeypatch.setattr(ga_intel, "normalize_property", lambda x: f"properties/{x}")

    result = ga_intel.anomalies("123", metric="sessions", days=2, z_threshold=2.0)
    assert result["data"] == []
