"""CrUX tools — real-user CWV from Chrome UX Report."""
from __future__ import annotations

from typing import Any

from ..guardrails import with_meta
from . import query_history, query_record

# Mapping from API metric names to friendlier output keys
METRIC_LABELS = {
    "largest_contentful_paint": "lcp",
    "cumulative_layout_shift": "cls",
    "first_contentful_paint": "fcp",
    "interaction_to_next_paint": "inp",
    "experimental_time_to_first_byte": "ttfb",
    "round_trip_time": "rtt",
}


def _summarise_record(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("_no_data"):
        return {
            "available": False,
            "reason": (
                "URL/origin not in public CrUX dataset (insufficient real-user traffic "
                "or page is non-indexable). Try the origin instead of the URL, or "
                "wait until the site has more traffic."
            ),
        }
    record = payload.get("record", {})
    metrics = record.get("metrics", {})
    out: dict[str, Any] = {"available": True, "key": record.get("key", {})}
    for api_name, label in METRIC_LABELS.items():
        m = metrics.get(api_name)
        if not m:
            continue
        p75 = m.get("percentiles", {}).get("p75")
        out[label] = {
            "p75": p75,
            "histogram": m.get("histogram", []),
        }
    out["collection_period"] = record.get("collectionPeriod", {})
    return out


def crux_current(
    url_or_origin: str,
    form_factor: str = "PHONE",
    is_origin: bool = False,
) -> dict:
    """Latest 28-day CrUX snapshot for a URL or origin (real user data).

    Args:
        url_or_origin: Full URL (e.g. https://example.com/page) OR origin
            (https://example.com — no path) when is_origin=True.
        form_factor: PHONE | DESKTOP | TABLET. Mobile is what Google uses
            primarily for ranking.
        is_origin: True to query the origin (aggregated across all URLs);
            False (default) to query the specific URL.
    """
    payload = (
        query_record(origin=url_or_origin, form_factor=form_factor)
        if is_origin
        else query_record(url=url_or_origin, form_factor=form_factor)
    )
    return with_meta(
        _summarise_record(payload),
        source="crux.queryRecord",
        site_url=url_or_origin,
        extra={"form_factor": form_factor, "is_origin": is_origin},
    )


def crux_history(
    url_or_origin: str,
    metric: str = "largest_contentful_paint",
    form_factor: str = "PHONE",
    is_origin: bool = False,
    weeks: int = 25,
) -> dict:
    """Historical p75 of one CrUX metric — up to 25 weekly snapshots (~6 months).

    Use this to correlate traffic drops with performance regressions. Example:
    if `gsc_traffic_drops` flags a page on 2026-03-15, run this with
    `metric='largest_contentful_paint'` and look for the same week — a sudden
    LCP jump in the timeline likely caused the ranking loss.

    Args:
        metric: largest_contentful_paint | cumulative_layout_shift |
            interaction_to_next_paint | first_contentful_paint |
            experimental_time_to_first_byte
    """
    payload = query_history(
        url=None if is_origin else url_or_origin,
        origin=url_or_origin if is_origin else None,
        form_factor=form_factor,
        metrics=[metric],
        collection_period_count=weeks,
    )
    if payload.get("_no_data"):
        return with_meta(
            {"available": False, "reason": "Not in CrUX dataset."},
            source="crux.queryHistoryRecord",
            site_url=url_or_origin,
        )
    record = payload.get("record", {})
    metrics_data = record.get("metrics", {}).get(metric, {})
    p75_series = [
        ts.get("p75") for ts in metrics_data.get("percentilesTimeseries", {}).get("p75s", [])
    ]
    periods = record.get("collectionPeriods", [])
    timeline = [
        {
            "week_ending": (p.get("lastDate") or {}),
            "p75": p75_series[i] if i < len(p75_series) else None,
        }
        for i, p in enumerate(periods)
    ]
    return with_meta(
        {
            "available": True,
            "metric": metric,
            "label": next(
                (lbl for k, lbl in {
                    "largest_contentful_paint": "lcp",
                    "cumulative_layout_shift": "cls",
                    "interaction_to_next_paint": "inp",
                    "first_contentful_paint": "fcp",
                    "experimental_time_to_first_byte": "ttfb",
                }.items() if k == metric),
                metric,
            ),
            "timeline": timeline,
        },
        source="crux.queryHistoryRecord",
        site_url=url_or_origin,
        extra={"form_factor": form_factor, "is_origin": is_origin, "weeks": weeks},
    )


def crux_compare_origins(
    origin_a: str,
    origin_b: str,
    metric: str = "largest_contentful_paint",
    form_factor: str = "PHONE",
) -> dict:
    """Compare a CWV metric between two origins (e.g. yours vs a competitor).

    Useful for: am I better/worse than the leader on this metric? By how much?
    """
    a = query_record(origin=origin_a, form_factor=form_factor, metrics=[metric])
    b = query_record(origin=origin_b, form_factor=form_factor, metrics=[metric])

    def _p75(payload: dict) -> float | None:
        if payload.get("_no_data"):
            return None
        return (
            payload.get("record", {})
            .get("metrics", {})
            .get(metric, {})
            .get("percentiles", {})
            .get("p75")
        )

    p75_a = _p75(a)
    p75_b = _p75(b)
    return with_meta(
        {
            "origin_a": {"origin": origin_a, "p75": p75_a},
            "origin_b": {"origin": origin_b, "p75": p75_b},
            "delta": (p75_a - p75_b) if (p75_a is not None and p75_b is not None) else None,
            "metric": metric,
        },
        source="crux.compare",
    )
