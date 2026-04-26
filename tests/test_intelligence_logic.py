"""Regression tests for diagnostic-logic bugs found in audit rounds.

These tests directly exercise the classification logic without hitting Google APIs
by monkey-patching the data-fetching helpers used by the intelligence tools.
"""
from __future__ import annotations

import pytest

from google_seo_mcp.gsc.tools import intelligence as gsc_intel


def test_traffic_drops_classifies_disappeared_pages(monkeypatch):
    """Page absent from current must be tagged 'disappeared', not 'ctr_collapse'.

    Regression: prior to the fix the default-fill (ctr=0, position=prev.position)
    made delta_pos=0 and ctr_ratio=0, which fell through to ctr_collapse.

    Call order in `traffic_drops`: query_search_analytics is called FIRST for
    cur (current period), THEN for prev. Our mock returns rows by call index.
    """
    prev_rows = [
        {
            "keys": ["https://example.com/missing-page"],
            "clicks": 100,
            "impressions": 1000,
            "ctr": 0.10,
            "position": 5.0,
        }
    ]
    cur_rows: list[dict] = []  # page disappeared completely

    call_idx = [0]

    def counting_query(*args, **kwargs):
        idx = call_idx[0]
        call_idx[0] += 1
        # 1st call = current period (empty), 2nd = prior period (has the page)
        return cur_rows if idx == 0 else prev_rows

    monkeypatch.setattr(gsc_intel, "query_search_analytics", counting_query)
    monkeypatch.setattr(gsc_intel, "get_webmasters", lambda: None)

    result = gsc_intel.traffic_drops(
        "https://example.com/", days=28, top_n=20, min_clicks_prior=20
    )
    drops = result["data"]
    assert len(drops) == 1
    assert drops[0]["diagnosis"] == "disappeared"
    assert drops[0]["click_delta"] == -100
    assert drops[0]["page"] == "https://example.com/missing-page"


def test_cannibalization_aggregates_before_threshold(monkeypatch):
    """Two pages at 30 impressions each (60 total) must pass min_impressions=50.

    Regression: prior version filtered per-row, dropping this real cannibalization.
    """
    rows = [
        {"keys": ["best foo", "https://x.com/a"], "clicks": 5, "impressions": 30, "ctr": 0.16, "position": 4.0},
        {"keys": ["best foo", "https://x.com/b"], "clicks": 3, "impressions": 30, "ctr": 0.10, "position": 7.0},
        # Same query but only one page — must NOT show
        {"keys": ["unique foo", "https://x.com/c"], "clicks": 2, "impressions": 100, "ctr": 0.02, "position": 9.0},
    ]
    monkeypatch.setattr(gsc_intel, "query_search_analytics", lambda *a, **k: rows)
    monkeypatch.setattr(gsc_intel, "get_webmasters", lambda: None)

    result = gsc_intel.cannibalization("https://x.com/", days=28, min_impressions=50, top_n=10)
    conflicts = result["data"]
    assert len(conflicts) == 1
    assert conflicts[0]["query"] == "best foo"
    assert conflicts[0]["total_impressions"] == 60


def test_content_decay_strict_monotonic(monkeypatch):
    """Strict monotonic decline: c1>c2>c3. A plateau (c1==c2) must NOT flag.

    Source code calls `fetch(p3)` then `fetch(p2)` then `fetch(p1)` in that order.
    """
    p1 = {"https://x.com/a": 100, "https://x.com/b": 100}  # oldest
    p2 = {"https://x.com/a": 80, "https://x.com/b": 100}   # middle (plateau on b)
    p3 = {"https://x.com/a": 50, "https://x.com/b": 50}    # recent

    call_idx = [0]

    def fake_query(*args, **kwargs):
        idx = call_idx[0]
        call_idx[0] += 1
        # Order: p3 first, p2 second, p1 third
        source = [p3, p2, p1][min(idx, 2)]
        return [
            {"keys": [page], "clicks": clicks, "impressions": clicks * 10, "ctr": 0.1, "position": 5}
            for page, clicks in source.items()
        ]

    monkeypatch.setattr(gsc_intel, "query_search_analytics", fake_query)
    monkeypatch.setattr(gsc_intel, "get_webmasters", lambda: None)

    result = gsc_intel.content_decay("https://x.com/", top_n=10, min_clicks_p3=10)
    decaying = result["data"]
    pages = {d["page"] for d in decaying}
    # 'a' has p1=100 > p2=80 > p3=50 (strict monotonic) → MUST flag
    assert "https://x.com/a" in pages
    # 'b' has p1=100 = p2=100 > p3=50 (NOT strict monotonic, plateau) → must NOT flag
    assert "https://x.com/b" not in pages
