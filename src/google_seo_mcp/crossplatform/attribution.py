"""SEO → revenue attribution: which organic queries actually generate revenue."""
from __future__ import annotations

from urllib.parse import urlparse

from ..auth import get_webmasters, normalize_property
from ..ga4.data import run_report
from ..ga4.dates import period as ga_period
from ..gsc.analytics import query_search_analytics
from ..gsc.dates import period as gsc_period
from ..guardrails import with_meta


def seo_to_revenue_attribution(
    site_url: str,
    property_id: int | str,
    days: int = 28,
    min_clicks: int = 10,
    top_n: int = 30,
) -> dict:
    """Estimates revenue attributed to each top organic query.

    Approach:
      1. From GSC, fetch (query, page) pairs with clicks ≥ min_clicks.
      2. From GA4, fetch organic-channel revenue and conversions per landing page.
      3. For each (query, page) pair, attribute revenue proportionally to its share
         of total clicks landing on that page.

    Caveat: GSC↔GA4 attribution is *approximate*. Same page can be reached via many
    queries; we distribute revenue by GSC click-share. This is an estimate, not
    multi-touch attribution. Useful for relative ranking ("which queries pay").
    """
    pid = normalize_property(property_id)
    gsc_start, gsc_end = gsc_period(days)
    ga_start, ga_end = ga_period(days)

    # ── 1) GSC (query, page) ───────────────────────────────
    gsc_rows = query_search_analytics(
        get_webmasters(),
        site_url,
        gsc_start,
        gsc_end,
        dimensions=["query", "page"],
        row_limit=25000,
        fetch_all=True,
    )
    pairs = []
    page_clicks: dict[str, float] = {}
    for r in gsc_rows:
        keys = r.get("keys", [])
        if len(keys) < 2:
            continue
        clicks = r.get("clicks", 0)
        if clicks < min_clicks:
            continue
        q, p = keys[0], keys[1]
        pairs.append({"query": q, "page": p, "gsc_clicks": clicks})
        page_clicks[p] = page_clicks.get(p, 0) + clicks

    if not pairs:
        return with_meta(
            [],
            source="crossplatform.seo_to_revenue_attribution",
            site_url=site_url,
            property=pid,
            period={
                "gsc": {"start": gsc_start, "end": gsc_end},
                "ga4": {"start": ga_start, "end": ga_end},
            },
        )

    # ── 2) GA4 organic revenue per landing page ────────────
    # Sort by click volume so we don't drop high-traffic pages by dict iteration order.
    pages_to_query = [
        p for p, _ in sorted(page_clicks.items(), key=lambda x: x[1], reverse=True)
    ][:200]
    dropped_pages = max(0, len(page_clicks) - len(pages_to_query))
    ga4_revenue: dict[str, dict] = {}
    for full_url in pages_to_query:
        path = _to_path(full_url)
        rows = run_report(
            pid,
            start_date=ga_start,
            end_date=ga_end,
            metrics=["totalRevenue", "conversions", "sessions"],
            dimension_filter={
                "and": [
                    {
                        "field": "landingPagePlusQueryString",
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
        ga4_revenue[full_url] = {
            "revenue": float(totals.get("totalRevenue", 0)),
            "conversions": float(totals.get("conversions", 0)),
            "sessions": float(totals.get("sessions", 0)),
        }

    # ── 3) Distribute by click-share ──────────────────────
    out = []
    for pair in pairs:
        page_total = page_clicks[pair["page"]]
        share = pair["gsc_clicks"] / page_total if page_total else 0
        ga = ga4_revenue.get(pair["page"], {"revenue": 0, "conversions": 0, "sessions": 0})
        attributed_rev = ga["revenue"] * share
        attributed_conv = ga["conversions"] * share
        out.append({
            **pair,
            "click_share_on_page": round(share, 3),
            "attributed_revenue": round(attributed_rev, 2),
            "attributed_conversions": round(attributed_conv, 2),
            "ga4_page_total_revenue": ga["revenue"],
            "ga4_page_total_sessions": ga["sessions"],
        })
    out.sort(key=lambda x: x["attributed_revenue"], reverse=True)
    return with_meta(
        out[:top_n],
        source="crossplatform.seo_to_revenue_attribution",
        site_url=site_url,
        property=pid,
        period={
            "gsc": {"start": gsc_start, "end": gsc_end},
            "ga4": {"start": ga_start, "end": ga_end},
        },
        extra={
            "attribution_model": "click_share_proportional",
            "pages_dropped_due_to_filter_cap": dropped_pages,
        },
    )


def _to_path(page_url: str) -> str:
    if page_url.startswith("http"):
        parsed = urlparse(page_url)
        return parsed.path + (f"?{parsed.query}" if parsed.query else "")
    return page_url
