"""Opportunity matrix — cross-references GSC quick wins with GA4 conversion data."""
from __future__ import annotations

from urllib.parse import urlparse

from ..auth import get_webmasters, normalize_property
from ..ga4.data import run_report
from ..ga4.dates import period as ga_period
from ..gsc.analytics import expected_ctr, query_search_analytics
from ..gsc.dates import period as gsc_period
from ..guardrails import with_meta


def opportunity_matrix(
    site_url: str,
    property_id: int | str,
    days: int = 28,
    min_impressions: int = 100,
    top_n: int = 20,
) -> dict:
    """Cross-references GSC quick-win pages with their GA4 conversion performance.

    For pages ranking in positions 4-15 with significant GSC impressions, fetches
    their GA4 conversion rate and revenue per session. Each row gets a quadrant tag:

      - **`high_impact`** — High GSC opportunity AND high GA4 conversion: rank these up FIRST.
      - **`worth_optimizing`** — High GSC opportunity, low GA4 conversion: rank up + improve page.
      - **`good_but_capped`** — Already converting well but GSC ceiling reached.
      - **`low_priority`** — Low opportunity on both axes.

    This is the holy-grail SEO prioritization — not just "what could rank higher",
    but "what would actually pay off if it did".

    Args:
        site_url: GSC property URL.
        property_id: GA4 property ID.
        days: lookback window (default 28).
        min_impressions: minimum GSC impressions to be a candidate.
        top_n: max rows returned (default 20).
    """
    pid = normalize_property(property_id)
    gsc_start, gsc_end = gsc_period(days)
    ga_start, ga_end = ga_period(days)

    # ── 1) GSC: pages with quick-win potential ─────────────
    gsc_rows = query_search_analytics(
        get_webmasters(),
        site_url,
        gsc_start,
        gsc_end,
        dimensions=["page"],
        row_limit=25000,
        fetch_all=True,
    )
    target_ctr = expected_ctr(3)
    candidates = []
    for r in gsc_rows:
        keys = r.get("keys", [])
        impr = r.get("impressions", 0)
        pos = r.get("position", 0)
        ctr = r.get("ctr", 0)
        if impr < min_impressions or pos < 4 or pos > 15:
            continue
        gap = max(0, target_ctr - ctr)
        candidates.append({
            "page_url": keys[0] if keys else "",
            "gsc_impressions": impr,
            "gsc_clicks": r.get("clicks", 0),
            "gsc_position": pos,
            "gsc_ctr_gap": gap,
            "gsc_opportunity_score": impr * gap,
        })
    candidates.sort(key=lambda x: x["gsc_opportunity_score"], reverse=True)
    candidates = candidates[: top_n * 2]  # take a buffer to merge with GA4

    if not candidates:
        return with_meta(
            [],
            source="crossplatform.opportunity_matrix",
            site_url=site_url,
            property=pid,
            period={
                "gsc": {"start": gsc_start, "end": gsc_end},
                "ga4": {"start": ga_start, "end": ga_end},
            },
        )

    # ── 2) GA4: conversion data for each candidate page ────
    ga4_by_path: dict[str, dict] = {}
    for c in candidates:
        path = _to_path(c["page_url"], site_url)
        if not path or path in ga4_by_path:
            continue
        rows = run_report(
            pid,
            start_date=ga_start,
            end_date=ga_end,
            metrics=["sessions", "conversions", "totalRevenue", "engagementRate"],
            dimension_filter={
                "and": [
                    {
                        # `landingPage` skips query string — UTM/gclid would
                        # break EXACT match on sites with paid traffic.
                        "field": "landingPage",
                        "string_value": path,
                        "match": "EXACT",
                    },
                    {
                        "field": "sessionDefaultChannelGroup",
                        "string_value": "Organic Search",
                    },
                ]
            },
            limit=1,
            aggregations=["TOTAL"],
        )
        totals = rows["totals"][0] if rows.get("totals") else {}
        ga4_by_path[path] = {
            "sessions": float(totals.get("sessions", 0)),
            "conversions": float(totals.get("conversions", 0)),
            "revenue": float(totals.get("totalRevenue", 0)),
            "engagement_rate": float(totals.get("engagementRate", 0)),
        }

    # ── 3) Merge + classify ─────────────────────────────────
    # Use the lower-median opportunity score as the "high" threshold — auto-calibrates
    # to the site's traffic volume rather than using an arbitrary 50. With N<4 samples
    # the median degenerates (e.g. N=2 picks the higher of two scores, leaving only
    # the top-1 as "high"), so we fall back to a safer percentile and require min N.
    import statistics as _stats
    scores = sorted([c["gsc_opportunity_score"] for c in candidates if c["gsc_opportunity_score"] > 0])
    if len(scores) >= 4:
        opp_threshold = _stats.median(scores)
    elif len(scores) >= 1:
        # Too few candidates for a stable median: use the 25th percentile so at
        # least the top-half-of-top-half qualifies as "high".
        opp_threshold = scores[max(0, (len(scores) - 1) // 4)]
    else:
        opp_threshold = 0

    out = []
    for c in candidates:
        path = _to_path(c["page_url"], site_url)
        ga = ga4_by_path.get(path, {"sessions": 0, "conversions": 0, "revenue": 0, "engagement_rate": 0})
        cvr = (ga["conversions"] / ga["sessions"]) if ga["sessions"] else 0
        rev_per_session = (ga["revenue"] / ga["sessions"]) if ga["sessions"] else 0

        # Classify (top half by opportunity = "high"; CVR ≥1% or rev/sess ≥ 0.5 = "high")
        opp_high = c["gsc_opportunity_score"] >= opp_threshold and c["gsc_opportunity_score"] > 0
        ga4_high = cvr >= 0.01 or rev_per_session >= 0.5
        if opp_high and ga4_high:
            quadrant = "high_impact"
        elif opp_high and not ga4_high:
            quadrant = "worth_optimizing"
        elif not opp_high and ga4_high:
            quadrant = "good_but_capped"
        else:
            quadrant = "low_priority"

        out.append({
            **c,
            "ga4_sessions": ga["sessions"],
            "ga4_conversions": ga["conversions"],
            "ga4_conversion_rate": round(cvr, 4),
            "ga4_revenue": ga["revenue"],
            "ga4_revenue_per_session": round(rev_per_session, 2),
            "ga4_engagement_rate": ga["engagement_rate"],
            "quadrant": quadrant,
        })

    # Sort: high_impact first, then by opportunity × conversion
    quadrant_order = {"high_impact": 0, "worth_optimizing": 1, "good_but_capped": 2, "low_priority": 3}
    out.sort(key=lambda x: (quadrant_order[x["quadrant"]], -x["gsc_opportunity_score"]))
    return with_meta(
        out[:top_n],
        source="crossplatform.opportunity_matrix",
        site_url=site_url,
        property=pid,
        period={
            "gsc": {"start": gsc_start, "end": gsc_end},
            "ga4": {"start": ga_start, "end": ga_end},
        },
    )


def _to_path(page_url: str, site_url: str = "") -> str:
    """Convert a full URL to a path-only form for GA4 matching."""
    if not page_url:
        return ""
    if page_url.startswith("http"):
        parsed = urlparse(page_url)
        return parsed.path + (f"?{parsed.query}" if parsed.query else "")
    return page_url
