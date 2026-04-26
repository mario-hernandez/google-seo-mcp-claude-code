"""Core reporting tools — schema discovery + raw report + estimate probe."""
from __future__ import annotations

from ...auth import normalize_property
from ..data import estimate_row_count, run_report
from ...guardrails import with_meta
from ..schema import categories, search_schema


def search_ga4_schema(property_id: int | str, keyword: str, top_n: int = 10) -> dict:
    """Find GA4 dimensions and metrics by keyword. Use BEFORE running queries.

    Examples:
        keyword="organic" → finds sessionDefaultChannelGroup, firstUserSource, etc.
        keyword="revenue" → finds totalRevenue, purchaseRevenue, itemRevenue, etc.
        keyword="engagement" → finds engagementRate, userEngagementDuration, etc.

    Returns top-N dimensions and metrics by weighted score (api_name×10 + ui_name×5
    + description×2 + category×1). Avoids dumping the full ~10k-token catalog.
    """
    pid = normalize_property(property_id)
    return with_meta(
        search_schema(pid, keyword, top_n=top_n),
        source="schema.search",
        property=pid,
        extra={"keyword": keyword, "top_n": top_n},
    )


def list_schema_categories(property_id: int | str) -> dict:
    """List all dimension/metric categories with counts (cheap, no LLM-tax)."""
    pid = normalize_property(property_id)
    return with_meta(categories(pid), source="schema.categories", property=pid)


def estimate_query_size(
    property_id: int | str,
    start_date: str,
    end_date: str,
    metrics: list[str],
    dimensions: list[str] | None = None,
    dimension_filter: dict | None = None,
) -> dict:
    """Estimate the row count of a query BEFORE fetching it (anti-context-blowup).

    Fires a `limit=1` probe to GA4 — the API returns the total row_count even with
    limit=1, so you get the size for the cost of one tiny request. If row_count is
    high (>2500), refine your query before calling `query_ga4`.
    """
    pid = normalize_property(property_id)
    n = estimate_row_count(
        pid,
        start_date=start_date,
        end_date=end_date,
        metrics=metrics,
        dimensions=dimensions,
        dimension_filter=dimension_filter,
    )
    advice = "ok" if n <= 2500 else "narrow_filter_or_dates"
    return with_meta(
        {"estimated_row_count": n, "recommendation": advice},
        source="data.estimate_row_count",
        property=pid,
        period={"start": start_date, "end": end_date},
    )


def query_ga4(
    property_id: int | str,
    start_date: str,
    end_date: str,
    metrics: list[str],
    dimensions: list[str] | None = None,
    dimension_filter: dict | None = None,
    metric_filter: dict | None = None,
    order_bys: list[dict] | None = None,
    limit: int = 1000,
    aggregations: list[str] | None = None,
) -> dict:
    """Run a GA4 Data API report.

    Args:
        property_id: GA4 property ID (int or "properties/<id>").
        start_date / end_date: ISO YYYY-MM-DD or relative "NdaysAgo" / "yesterday" / "today".
        metrics: e.g. ["sessions", "totalUsers", "engagementRate"]. Use `search_ga4_schema` first.
        dimensions: e.g. ["sessionDefaultChannelGroup", "country"].
        dimension_filter / metric_filter: nested {"and": [...]} / {"or": [...]} / {"not": ...} / {"field": ..., "string_value": ...}.
        order_bys: list of {"metric": "sessions", "desc": true} or {"dimension": "date", "desc": false}.
        limit: max rows (server-side cap 2500).
        aggregations: list of "TOTAL", "MAXIMUM", "MINIMUM" — auto-includes TOTAL when no `date` dimension.
    """
    pid = normalize_property(property_id)
    result = run_report(
        pid,
        start_date=start_date,
        end_date=end_date,
        metrics=metrics,
        dimensions=dimensions,
        dimension_filter=dimension_filter,
        metric_filter=metric_filter,
        order_bys=order_bys,
        limit=limit,
        aggregations=aggregations,
    )
    return with_meta(
        result,
        source="data.run_report",
        property=pid,
        period={"start": start_date, "end": end_date},
    )
