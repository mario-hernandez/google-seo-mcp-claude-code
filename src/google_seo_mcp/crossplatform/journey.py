"""GSC → GA4 journey: complete the loop from organic landing to conversion."""
from __future__ import annotations

from urllib.parse import urlparse

from ..auth import get_webmasters, normalize_property
from ..ga4.data import run_report
from ..ga4.dates import period as ga_period
from ..gsc.analytics import query_search_analytics
from ..gsc.dates import period as gsc_period
from ..guardrails import with_meta


def gsc_to_ga4_journey(
    site_url: str,
    property_id: int | str,
    landing_path: str,
    days: int = 28,
) -> dict:
    """The killer feature: closes the loop from GSC organic clicks to GA4 conversions.

    Given a landing path that surfaces in Search Console (organic), returns:
      - GSC side: top queries that drove clicks to this page, their CTR/position
      - GA4 side: sessions, engagement, bounce, conversions, revenue, secondary pages

    Args:
        site_url: GSC property URL (e.g. "https://www.example.com/" or "sc-domain:example.com").
        property_id: GA4 property ID (int or "properties/<id>").
        landing_path: full URL or path-only — both forms are normalized.
        days: lookback window (default 28).

    Returns a dict with `gsc` (top queries) and `ga4` (behavior) blocks plus _meta
    citing both data sources and their respective time windows (note: GSC and GA4
    have different reporting lags, so the periods may differ by 2-3 days).
    """
    # Normalize path. GA4 expects path-only; GSC expects absolute URL.
    path = landing_path
    if path.startswith("http"):
        parsed = urlparse(path)
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    # Ensure path starts with exactly one "/" so concatenation can't create
    # malformed URLs like "https://x.comblog/post" or "https://x.com//evil/x".
    path = "/" + path.lstrip("/")
    full_page_url = (
        landing_path if landing_path.startswith("http")
        else (site_url.rstrip("/") + path if not site_url.startswith("sc-domain:")
              else f"https://{site_url[len('sc-domain:'):]}{path}")
    )

    pid = normalize_property(property_id)

    # ── GSC side ─────────────────────────────────────────────
    gsc_start, gsc_end = gsc_period(days)
    gsc_rows = query_search_analytics(
        get_webmasters(),
        site_url,
        gsc_start,
        gsc_end,
        dimensions=["query"],
        dimension_filter_groups=[
            {
                "filters": [
                    {
                        "dimension": "page",
                        "operator": "equals",
                        "expression": full_page_url,
                    }
                ]
            }
        ],
        row_limit=20,
    )
    top_queries = [
        {
            "query": r.get("keys", [""])[0],
            "clicks": r.get("clicks", 0),
            "impressions": r.get("impressions", 0),
            "ctr": r.get("ctr", 0),
            "position": r.get("position", 0),
        }
        for r in gsc_rows
    ]

    # ── GA4 side ─────────────────────────────────────────────
    ga_start, ga_end = ga_period(days)
    organic_filter = {
        "and": [
            # `landingPage` (no query string) avoids UTM-driven cardinality
            # explosion that broke EXACT match on paid-traffic sites.
            {"field": "landingPage", "string_value": path, "match": "EXACT"},
            {"field": "sessionDefaultChannelGroup", "string_value": "Organic Search"},
        ]
    }
    overview = run_report(
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
    next_pages = run_report(
        pid,
        start_date=ga_start,
        end_date=ga_end,
        metrics=["screenPageViews"],
        dimensions=["pagePath"],
        dimension_filter=organic_filter,
        order_bys=[{"metric": "screenPageViews", "desc": True}],
        limit=10,
    )["rows"]

    return with_meta(
        {
            "landing_path": path,
            "gsc": {
                "site_url": site_url,
                "period": {"start": gsc_start, "end": gsc_end},
                "top_queries": top_queries,
                "total_clicks": sum(q["clicks"] for q in top_queries),
                "total_impressions": sum(q["impressions"] for q in top_queries),
            },
            "ga4": {
                "property": pid,
                "period": {"start": ga_start, "end": ga_end},
                "totals": overview["totals"][0] if overview.get("totals") else {},
                "secondary_pages": [
                    {"page": r["pagePath"], "page_views": float(r["screenPageViews"])}
                    for r in next_pages
                    # `pagePath` strips query string, so compare against path-without-query
                    if r.get("pagePath") and r["pagePath"] != path.split("?")[0]
                ][:10],
            },
        },
        source="crossplatform.gsc_to_ga4_journey",
        site_url=site_url,
        property=pid,
        period={
            "gsc": {"start": gsc_start, "end": gsc_end},
            "ga4": {"start": ga_start, "end": ga_end},
        },
        extra={"landing_path": path},
    )
