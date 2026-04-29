"""Multi-property comparison — fan out to N GA4 properties in one call."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..auth import normalize_property
from ..ga4.data import run_report
from ..ga4.dates import period as ga_period
from ..guardrails import with_meta


def multi_property_comparison(
    property_ids: list[int | str],
    metric: str = "sessions",
    days: int = 28,
    dimension: str | None = None,
    max_concurrent: int = 5,
) -> dict:
    """Compare a single metric across multiple GA4 properties in one call.

    Useful for agencies / multi-site owners who want a single overview of all
    their properties without one query per property. Fans out to GA4 with
    bounded concurrency (default 5 parallel) and aggregates results.

    Args:
        property_ids: list of GA4 property IDs (int or "properties/<id>").
        metric: e.g. "sessions", "totalUsers", "purchaseRevenue", "conversions".
        days: lookback window (default 28).
        dimension: optional secondary dimension (e.g. "deviceCategory") — when
            set, returns per-dimension breakdown per property.
        max_concurrent: max parallel GA4 calls (default 5; raise carefully — the
            GA4 API rate-limits per-property tokens, not globally).

    Returns a list of {property, total, breakdown} sorted by total descending.
    """
    if not property_ids:
        raise ValueError("property_ids must not be empty")
    if len(property_ids) > 50:
        raise ValueError(f"max 50 properties per call, got {len(property_ids)}")

    start, end = ga_period(days)
    norm_ids = [normalize_property(p) for p in property_ids]

    def _fetch(pid: str) -> dict[str, Any]:
        try:
            result = run_report(
                pid,
                start_date=start,
                end_date=end,
                metrics=[metric],
                dimensions=[dimension] if dimension else None,
                limit=200,
                aggregations=["TOTAL"],
            )
            # GA4 sometimes returns empty strings for missing metric values;
            # ``float("")`` raises. ``or 0`` handles both None and "".
            totals = result.get("totals") or []
            if totals and metric in totals[0]:
                total = float(totals[0].get(metric) or 0)
            else:
                total = sum(float(r.get(metric) or 0) for r in result["rows"])
            breakdown = None
            if dimension:
                breakdown = sorted(
                    [
                        {dimension: r.get(dimension, ""), metric: float(r.get(metric) or 0)}
                        for r in result["rows"]
                    ],
                    key=lambda x: x[metric],
                    reverse=True,
                )
            return {"property": pid, "total": total, "breakdown": breakdown, "error": None}
        except Exception as e:
            return {"property": pid, "total": None, "breakdown": None, "error": str(e)[:200]}

    with ThreadPoolExecutor(max_workers=max_concurrent) as pool:
        results = list(pool.map(_fetch, norm_ids))

    # Sort: properties with data first (by total desc), then errored ones at the end
    results.sort(
        key=lambda x: (x["error"] is not None, -(x["total"] or 0))
    )
    return with_meta(
        results,
        source="crossplatform.multi_property_comparison",
        period={"start": start, "end": end},
        extra={
            "metric": metric,
            "dimension": dimension,
            "properties_queried": len(norm_ids),
            "errored": sum(1 for r in results if r["error"]),
        },
    )
