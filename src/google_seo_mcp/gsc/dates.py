"""Date utilities — relative periods and offsets."""
from __future__ import annotations

from datetime import date, timedelta


def today() -> date:
    return date.today()


def lag_days(days: int = 3) -> date:
    """GSC has ~3 days lag. Use as latest "complete" day."""
    return today() - timedelta(days=days)


def period(days: int, end: date | None = None) -> tuple[str, str]:
    """Returns (start, end) ISO strings for the last N days ending at `end`."""
    if end is None:
        end = lag_days()
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def prior_period(days: int, end: date | None = None) -> tuple[str, str]:
    """Returns the period of `days` immediately before `period(days, end)`."""
    if end is None:
        end = lag_days()
    prior_end = end - timedelta(days=days)
    prior_start = prior_end - timedelta(days=days - 1)
    return prior_start.isoformat(), prior_end.isoformat()
