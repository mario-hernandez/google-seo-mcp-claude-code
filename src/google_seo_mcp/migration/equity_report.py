"""SEO equity report — combines WP audit + GSC + GA4 data into a migration plan.

This is the killer composer: ranks each WordPress URL by its SEO value
(clicks, sessions, internal links pointing to it, schema richness) and
classifies it as MUST_PRESERVE / WORTH_PRESERVING / DEPRECATE.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from ..gsc.analytics import query_search_analytics
from ..gsc.dates import period as gsc_period
from .wp_audit import (
    crawl_site_advertools,
    fetch_wp_redirects,
    internal_links_graph_from_crawl,
    wp_iterate_urls,
    wp_summary,
)


def _classify(score: float) -> str:
    if score >= 70:
        return "MUST_PRESERVE"
    if score >= 30:
        return "WORTH_PRESERVING"
    if score > 0:
        return "LOW_VALUE"
    return "DEPRECATE"


def build_equity_report(
    wp_url: str,
    gsc_site_url: str | None = None,
    days: int = 90,
    max_pages: int = 200,
) -> dict[str, Any]:
    """Build a complete SEO equity report for a WordPress site.

    Composes:
      - WP REST API inventory (post types, taxonomies, plugin probes)
      - advertools crawl (title/meta/h1/canonical/schema/internal links)
      - GSC clicks + impressions per URL (last `days`, requires gsc_site_url)
      - Internal links graph (in-degree per URL = backlink-equity proxy)
      - Composite equity score 0-100 + classification per URL
    """
    # 1. WP inventory
    inventory = wp_summary(wp_url)
    rest_urls = wp_iterate_urls(wp_url, max_pages=max_pages)

    # 2. Crawl with advertools (title/meta/schema/links)
    crawl_rows = []
    crawl_error: str | None = None
    try:
        crawl_rows = crawl_site_advertools(wp_url, max_pages=max_pages)
    except Exception as e:
        crawl_error = str(e)[:200]

    # 3. Build crawled-rows lookup. URLs are normalised (lowercase host,
    # no trailing slash, no fragment) so REST + crawl + GSC entries that
    # logically point to the same page collapse into a single record
    # instead of being scored separately as duplicates.
    crawl_by_url: dict[str, dict] = {
        _norm_url(row.get("url", "")): row for row in crawl_rows if row.get("url")
    }

    # 4. Internal links graph
    graph = internal_links_graph_from_crawl(crawl_rows) if crawl_rows else {
        "nodes": [], "edges": [], "orphans": [], "hubs": []
    }
    in_degree_by_url = {n["url"]: n["in_degree"] for n in graph["nodes"]}

    # 5. GSC data per URL (if site_url passed)
    gsc_by_url: dict[str, dict] = {}
    if gsc_site_url:
        try:
            from ..auth import get_webmasters
            wm = get_webmasters()
            start, end = gsc_period(days)
            rows = query_search_analytics(
                wm, gsc_site_url, start, end,
                dimensions=["page"], row_limit=25000, fetch_all=True,
            )
            for r in rows:
                page_url = (r.get("keys") or [None])[0]
                if page_url:
                    gsc_by_url[_norm_url(page_url)] = {
                        "clicks": r.get("clicks", 0),
                        "impressions": r.get("impressions", 0),
                        "ctr": r.get("ctr", 0),
                        "position": r.get("position", 0),
                    }
        except Exception as e:
            inventory["gsc_error"] = str(e)[:200]

    # 6. Score each URL
    # Components: clicks (50%), impressions (15%), in_degree (20%), schema (10%), text length (5%)
    max_clicks = max((d["clicks"] for d in gsc_by_url.values()), default=1) or 1
    max_impr = max((d["impressions"] for d in gsc_by_url.values()), default=1) or 1
    max_in_deg = max(in_degree_by_url.values(), default=1) or 1

    per_url: list[dict] = []
    rest_normed = {_norm_url(u) for u in rest_urls_to_set(rest_urls)}
    all_urls = rest_normed | set(crawl_by_url.keys()) | set(gsc_by_url.keys())
    for url in all_urls:
        gsc = gsc_by_url.get(url, {"clicks": 0, "impressions": 0, "ctr": 0, "position": 0})
        crawled = crawl_by_url.get(url, {})
        in_deg = in_degree_by_url.get(url, 0)

        clicks_score = (gsc["clicks"] / max_clicks) * 50
        impr_score = (gsc["impressions"] / max_impr) * 15
        link_score = (in_deg / max_in_deg) * 20
        schema_score = 10 if (crawled.get("jsonld") or crawled.get("structured_data")) else 0
        body_text = crawled.get("body_text", "") or ""
        text_score = 5 if len(body_text) > 1000 else (2 if len(body_text) > 200 else 0)

        score = round(clicks_score + impr_score + link_score + schema_score + text_score, 1)

        per_url.append({
            "url": url,
            "score": score,
            "classification": _classify(score),
            "gsc_clicks": gsc["clicks"],
            "gsc_impressions": gsc["impressions"],
            "gsc_position": round(gsc["position"], 1) if gsc["position"] else None,
            "in_degree": in_deg,
            "title": crawled.get("title", ""),
            "has_schema": schema_score > 0,
            "body_text_len": len(body_text),
        })

    per_url.sort(key=lambda x: x["score"], reverse=True)

    # 7. Buckets summary
    by_class: dict[str, list] = {}
    for u in per_url:
        by_class.setdefault(u["classification"], []).append(u)

    # 8. Redirects (best-effort, no auth — public Redirection plugin)
    plugin_redirects: list[dict] = []
    try:
        plugin_redirects = fetch_wp_redirects(wp_url)
    except Exception:
        pass

    return {
        "wp_url": wp_url,
        "gsc_site_url": gsc_site_url,
        "period_days": days,
        "summary": {
            "total_urls": len(all_urls),
            "rest_api_count": len(rest_urls),
            "crawled_count": len(crawl_rows),
            "gsc_url_count": len(gsc_by_url),
            "crawl_error": crawl_error,
            "buckets": {k: len(v) for k, v in by_class.items()},
        },
        "inventory": inventory,
        "internal_links": {
            "total_edges": len(graph["edges"]),
            "orphans_count": len(graph.get("orphans", [])),
            "top_hubs": graph.get("hubs", [])[:10],
        },
        "plugin_redirects": plugin_redirects,
        "plugin_redirect_count": len(plugin_redirects),
        "urls_by_score": per_url[:200],  # cap output
        "must_preserve_count": len(by_class.get("MUST_PRESERVE", [])),
        "deprecate_count": len(by_class.get("DEPRECATE", [])),
    }


def rest_urls_to_set(rest_urls: list[dict]) -> list[str]:
    return [u["url"] for u in rest_urls if u.get("url")]


def _norm_url(url: str) -> str:
    """Canonicalise a URL for set operations.

    Lowercases scheme + host, strips trailing slash from path (except for
    the root), drops fragment. This makes ``https://X.com/post/`` and
    ``https://x.com/post`` collapse into the same key — the equity report
    used to count them as separate URLs and assign the SEO value to the
    wrong one when GSC and the crawl disagreed on slash form.
    """
    if not url:
        return ""
    from urllib.parse import urlsplit, urlunsplit

    s = urlsplit(url.strip())
    scheme = (s.scheme or "https").lower()
    host = (s.netloc or "").lower()
    path = s.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    # Drop fragment, keep query (semantically meaningful for some sites).
    return urlunsplit((scheme, host, path, s.query, ""))
