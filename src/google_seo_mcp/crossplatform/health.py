"""Traffic health check — detects tracking gaps between GSC and GA4."""
from __future__ import annotations

from ..auth import get_webmasters, normalize_property
from ..ga4.data import run_report
from ..ga4.dates import period as ga_period
from ..gsc.analytics import aggregate_totals, query_search_analytics
from ..gsc.dates import period as gsc_period
from ..guardrails import with_meta


def traffic_health_check(
    site_url: str,
    property_id: int | str,
    days: int = 28,
) -> dict:
    """Compare GSC organic clicks vs GA4 organic sessions to detect tracking gaps.

    A healthy ratio is roughly 0.7-1.3: GA4 sessions slightly higher than GSC clicks
    (because GA4 counts re-entries & deeplinks). Outliers indicate a problem:

      - **Tracking gap** (ratio < 0.6): GA4 missing organic traffic.
        Possible causes: incorrect channel group, GA4 referral exclusions wrong,
        consent banner blocking analytics, JavaScript broken on landing pages.
      - **Filter issue / spam** (ratio > 1.4): GA4 reports more sessions than GSC clicks.
        Possible causes: bot traffic, internal traffic not filtered, GSC under-reporting
        due to low-volume filter, or organic traffic being mis-classified as direct.
      - **Healthy** (0.6 ≤ ratio ≤ 1.4): both systems agree within reasonable margin.

    Args:
        site_url: GSC property URL.
        property_id: GA4 property ID.
        days: lookback window (default 28).
    """
    pid = normalize_property(property_id)

    # Align both windows to the more lagged source (GSC, ~3 days) so we compare
    # the same calendar dates on both sides. Otherwise GSC ends at t-3 and GA4
    # ends at t-1, and a viral day in t-2 would falsely trip filter_issue.
    from datetime import date
    gsc_start, gsc_end = gsc_period(days)
    aligned_end = date.fromisoformat(gsc_end)
    ga_start, ga_end = ga_period(days, end=aligned_end)

    gsc_rows = query_search_analytics(
        get_webmasters(), site_url, gsc_start, gsc_end, dimensions=[]
    )
    gsc_totals = aggregate_totals(gsc_rows)
    gsc_clicks = gsc_totals["clicks"]

    ga_rows = run_report(
        pid,
        start_date=ga_start,
        end_date=ga_end,
        metrics=["sessions"],
        dimension_filter={
            "field": "sessionDefaultChannelGroup",
            "string_value": "Organic Search",
        },
        limit=1,
        aggregations=["TOTAL"],
    )
    totals = ga_rows.get("totals") or []
    # GA4 returns "" for some empty metric values — float("") raises.
    ga_sessions = float(totals[0].get("sessions") or 0) if totals else 0

    if gsc_clicks == 0 and ga_sessions == 0:
        diagnosis = "no_organic_traffic"
        ratio = None
    elif gsc_clicks == 0:
        diagnosis = "filter_issue"
        ratio = None
    else:
        ratio = ga_sessions / gsc_clicks
        if ratio < 0.6:
            diagnosis = "tracking_gap"
        elif ratio > 1.4:
            diagnosis = "filter_issue"
        else:
            diagnosis = "healthy"

    return with_meta(
        {
            "diagnosis": diagnosis,
            "ratio_ga4_to_gsc": round(ratio, 3) if ratio is not None else None,
            "gsc_organic_clicks": gsc_clicks,
            "ga4_organic_sessions": ga_sessions,
            "interpretation": _interpret(diagnosis, ratio),
        },
        source="crossplatform.traffic_health_check",
        site_url=site_url,
        property=pid,
        period={
            "gsc": {"start": gsc_start, "end": gsc_end},
            "ga4": {"start": ga_start, "end": ga_end},
        },
    )


def _interpret(diagnosis: str, ratio: float | None) -> str:
    if diagnosis == "healthy":
        return (
            f"GA4 reports {ratio:.0%} of GSC organic clicks — within the expected "
            "0.6-1.4 range. Tracking is consistent."
        )
    if diagnosis == "tracking_gap":
        return (
            f"GA4 only sees {ratio:.0%} of GSC organic clicks — significant tracking "
            "gap. Check: GA4 channel-group rules, referral exclusions, consent banner "
            "blocking analytics on first page-view, broken JS on landing pages."
        )
    if diagnosis == "filter_issue":
        if ratio is None:
            return (
                "GSC reports zero organic clicks but GA4 has organic sessions — "
                "either organic traffic is mis-classified in GA4 (bot/internal/referral "
                "wrongly bucketed as organic) or GSC has not yet indexed the property."
            )
        return (
            f"GA4 reports {ratio:.0%} of GSC clicks — more sessions than searches. "
            "Possible causes: bot traffic not filtered, internal/dev traffic counted, "
            "or organic mis-classified by GA4's channel grouping."
        )
    if diagnosis == "no_organic_traffic":
        return "Both systems report zero organic traffic for this period."
    return "Unable to compute health ratio."
