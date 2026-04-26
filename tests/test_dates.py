"""Tests for date helpers — period adjacency without overlap."""
from __future__ import annotations

from datetime import date, timedelta

from google_seo_mcp.ga4 import dates as ga_dates
from google_seo_mcp.gsc import dates as gsc_dates


def _to_date(s: str) -> date:
    return date.fromisoformat(s)


def test_gsc_period_28_days_inclusive():
    end = date(2026, 1, 28)
    s, e = gsc_dates.period(28, end=end)
    assert _to_date(s) == date(2026, 1, 1)
    assert _to_date(e) == date(2026, 1, 28)
    # 28 days inclusive
    assert (_to_date(e) - _to_date(s)).days + 1 == 28


def test_gsc_prior_period_adjacent_no_overlap():
    end = date(2026, 1, 28)
    cur_s, cur_e = gsc_dates.period(28, end=end)
    prev_s, prev_e = gsc_dates.prior_period(28, end=end)
    # prior_end must be exactly 1 day before current_start
    assert _to_date(prev_e) == _to_date(cur_s) - timedelta(days=1)
    # Both windows are 28 days long
    assert (_to_date(prev_e) - _to_date(prev_s)).days + 1 == 28


def test_ga4_period_uses_yesterday_default():
    yesterday = date.today() - timedelta(days=1)
    s, e = ga_dates.period(7)
    assert _to_date(e) == yesterday
    assert (_to_date(e) - _to_date(s)).days + 1 == 7


def test_gsc_period_uses_3day_lag():
    """GSC has a 3-day reporting lag so default end is `today - 3`."""
    expected_end = date.today() - timedelta(days=3)
    s, e = gsc_dates.period(7)
    assert _to_date(e) == expected_end


def test_gsc_and_ga4_default_lag_difference():
    """GSC default end is 2 days behind GA4 default (3-day vs 1-day lag)."""
    _, gsc_end = gsc_dates.period(7)
    _, ga_end = ga_dates.period(7)
    assert (_to_date(ga_end) - _to_date(gsc_end)).days == 2


def test_period_one_day_window():
    """Edge: a 1-day window is just `start == end`."""
    end = date(2026, 1, 28)
    s, e = gsc_dates.period(1, end=end)
    assert s == e == "2026-01-28"
