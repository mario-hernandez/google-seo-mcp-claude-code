"""Date utilities — relative periods.

GA4 returns yesterday's data with ~24h lag (vs GSC's 3-day lag). Default end = yesterday.
"""
from __future__ import annotations

from datetime import date, timedelta


def yesterday() -> date:
    return date.today() - timedelta(days=1)


def period(days: int, end: date | None = None) -> tuple[str, str]:
    """Returns (start, end) ISO strings for the last N days ending at `end`."""
    if end is None:
        end = yesterday()
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def prior_period(days: int, end: date | None = None) -> tuple[str, str]:
    """The period of `days` immediately before `period(days, end)`."""
    if end is None:
        end = yesterday()
    prior_end = end - timedelta(days=days)
    prior_start = prior_end - timedelta(days=days - 1)
    return prior_start.isoformat(), prior_end.isoformat()
