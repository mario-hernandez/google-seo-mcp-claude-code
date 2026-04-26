"""Full landing-page diagnosis: combines GSC ranking signals with GA4 behavior."""
from __future__ import annotations

from urllib.parse import urlparse

from ..auth import get_webmasters, normalize_property
from ..ga4.data import run_report
from ..ga4.dates import period as ga_period
from ..gsc.analytics import expected_ctr, query_search_analytics
from ..gsc.dates import period as gsc_period
from ..guardrails import with_meta


def landing_page_full_diagnosis(
    site_url: str,
    property_id: int | str,
    page_url: str,
    days: int = 28,
) -> dict:
    """Complete diagnosis of a landing page across both Search Console and GA4.

    Returns a single composed view:
      - **GSC**: top queries driving clicks, ranking position, CTR vs benchmark,
                 cannibalization signal (>1 of your pages competing for same query).
      - **GA4**: organic sessions, engagement rate, bounce rate, avg duration,
                 conversion rate, revenue per session.
      - **Health score**: 0-100 composite + tag (red/amber/green) + specific issues
                          flagged: `low_ctr`, `cannibalized`, `high_bounce`,
                          `low_engagement`, `no_conversions`.

    Use this when you want to triage one specific page end-to-end without writing
    queries against both APIs separately.
    """
    pid = normalize_property(property_id)
    gsc_start, gsc_end = gsc_period(days)
    ga_start, ga_end = ga_period(days)

    path = _to_path(page_url)

    # ── GSC: queries for this exact page ────────────────────
    gsc_rows = query_search_analytics(
        get_webmasters(),
        site_url,
        gsc_start,
        gsc_end,
        dimensions=["query"],
        dimension_filter_groups=[
            {
                "filters": [
                    {"dimension": "page", "operator": "equals", "expression": page_url}
                ]
            }
        ],
        row_limit=50,
    )
    gsc_clicks = sum(r.get("clicks", 0) for r in gsc_rows)
    gsc_impressions = sum(r.get("impressions", 0) for r in gsc_rows)
    gsc_ctr = (gsc_clicks / gsc_impressions) if gsc_impressions else 0
    weighted_pos = (
        sum(r.get("position", 0) * r.get("impressions", 0) for r in gsc_rows)
        / gsc_impressions
    ) if gsc_impressions else 0
    top_queries = [
        {
            "query": r.get("keys", [""])[0],
            "clicks": r.get("clicks", 0),
            "impressions": r.get("impressions", 0),
            "ctr": r.get("ctr", 0),
            "position": r.get("position", 0),
        }
        for r in gsc_rows[:10]
    ]

    # ── Cannibalization: any of these queries served by another page on this site? ──
    cannibalized_queries: list[str] = []
    top_q_strs = {q["query"] for q in top_queries[:5] if q["query"]}
    if top_q_strs:
        qp_rows = query_search_analytics(
            get_webmasters(),
            site_url,
            gsc_start,
            gsc_end,
            dimensions=["query", "page"],
            row_limit=5000,
        )
        by_query: dict[str, set[str]] = {}
        for r in qp_rows:
            ks = r.get("keys", [])
            if len(ks) < 2:
                continue
            q, p = ks[0], ks[1]
            if q not in top_q_strs:
                continue
            if r.get("impressions", 0) < 10:
                continue
            by_query.setdefault(q, set()).add(p)
        for q, pages in by_query.items():
            if len(pages) >= 2:
                cannibalized_queries.append(q)

    # ── GA4: behavior on this landing page (organic only) ──
    organic_filter = {
        "and": [
            {"field": "landingPagePlusQueryString", "string_value": path, "match": "EXACT"},
            {"field": "sessionDefaultChannelGroup", "string_value": "Organic Search"},
        ]
    }
    ga = run_report(
        pid,
        start_date=ga_start,
        end_date=ga_end,
        metrics=[
            "sessions",
            "engagementRate",
            "bounceRate",
            "averageSessionDuration",
            "conversions",
            "totalRevenue",
            "screenPageViewsPerSession",
        ],
        dimension_filter=organic_filter,
        limit=1,
        aggregations=["TOTAL"],
    )
    ga_totals = ga["totals"][0] if ga.get("totals") else {}
    sessions = float(ga_totals.get("sessions", 0))
    engagement = float(ga_totals.get("engagementRate", 0))
    bounce = float(ga_totals.get("bounceRate", 0))
    avg_dur = float(ga_totals.get("averageSessionDuration", 0))
    conversions = float(ga_totals.get("conversions", 0))
    revenue = float(ga_totals.get("totalRevenue", 0))
    cvr = (conversions / sessions) if sessions else 0

    # ── Health score & tags ────────────────────────────────
    score = 100
    issues: list[str] = []
    expected = expected_ctr(weighted_pos) if weighted_pos else 0
    if expected and gsc_ctr < expected * 0.6:
        score -= 20
        issues.append("low_ctr")
    if cannibalized_queries:
        score -= 15
        issues.append(f"cannibalized:{len(cannibalized_queries)}")
    if bounce > 0.70:
        score -= 20
        issues.append("high_bounce")
    elif bounce > 0.50:
        score -= 8
    if engagement < 0.40:
        score -= 15
        issues.append("low_engagement")
    if avg_dur < 30:
        score -= 10
        issues.append("low_duration")
    if conversions == 0 and sessions > 50:
        score -= 15
        issues.append("no_conversions")

    tag = "red" if score < 50 else ("amber" if score < 75 else "green")

    return with_meta(
        {
            "page_url": page_url,
            "score": score,
            "tag": tag,
            "issues": issues,
            "gsc": {
                "total_clicks": gsc_clicks,
                "total_impressions": gsc_impressions,
                "ctr": round(gsc_ctr, 4),
                "ctr_expected_for_position": round(expected, 4) if expected else None,
                "avg_position": round(weighted_pos, 2),
                "top_queries": top_queries,
                "cannibalized_queries": cannibalized_queries,
            },
            "ga4": {
                "sessions": sessions,
                "engagement_rate": engagement,
                "bounce_rate": bounce,
                "avg_session_duration_s": avg_dur,
                "conversions": conversions,
                "revenue": revenue,
                "conversion_rate": round(cvr, 4),
            },
        },
        source="crossplatform.landing_page_full_diagnosis",
        site_url=site_url,
        property=pid,
        period={
            "gsc": {"start": gsc_start, "end": gsc_end},
            "ga4": {"start": ga_start, "end": ga_end},
        },
        extra={"page_url": page_url},
    )


def _to_path(page_url: str) -> str:
    if page_url.startswith("http"):
        parsed = urlparse(page_url)
        return parsed.path + (f"?{parsed.query}" if parsed.query else "")
    return page_url
