"""Search Analytics tools — basic queries."""
from __future__ import annotations

from ..analytics import aggregate_totals, query_search_analytics
from ...auth import get_webmasters
from ..dates import period, prior_period
from ...guardrails import with_meta


def search_analytics(
    site_url: str,
    start_date: str,
    end_date: str,
    dimensions: list[str] | None = None,
    row_limit: int = 1000,
    search_type: str = "web",
) -> dict:
    """Custom Search Analytics query.

    Args:
        site_url: Property URL.
        start_date / end_date: ISO YYYY-MM-DD.
        dimensions: e.g. ["query"], ["page"], ["query","page"], ["country"], ["device"].
        row_limit: Max rows (server-side cap 25000).
        search_type: "web" | "image" | "video" | "news".
    """
    rows = query_search_analytics(
        get_webmasters(),
        site_url,
        start_date,
        end_date,
        dimensions=dimensions or [],
        row_limit=row_limit,
        search_type=search_type,
    )
    return with_meta(
        rows,
        source="webmasters.searchanalytics.query",
        site_url=site_url,
        period={"start": start_date, "end": end_date},
    )


def site_snapshot(site_url: str, days: int = 28) -> dict:
    """Aggregated totals (clicks/impressions/CTR/position) for the last N days vs prior period."""
    cur_start, cur_end = period(days)
    prev_start, prev_end = prior_period(days)
    wm = get_webmasters()
    cur = aggregate_totals(query_search_analytics(wm, site_url, cur_start, cur_end))
    prev = aggregate_totals(query_search_analytics(wm, site_url, prev_start, prev_end))

    def delta(a: float, b: float) -> dict:
        diff = a - b
        pct = (diff / b * 100) if b else 0.0
        return {"absolute": diff, "percent": pct}

    return with_meta(
        {
            "current": cur,
            "previous": prev,
            "delta": {
                "clicks": delta(cur["clicks"], prev["clicks"]),
                "impressions": delta(cur["impressions"], prev["impressions"]),
                "ctr": delta(cur["ctr"], prev["ctr"]),
                "position": delta(cur["position"], prev["position"]),
            },
        },
        source="webmasters.searchanalytics.query (snapshot)",
        site_url=site_url,
        period={
            "current": {"start": cur_start, "end": cur_end},
            "previous": {"start": prev_start, "end": prev_end},
        },
    )
