"""WordPress equity extraction — read-only, for migration to a new stack.

Uses `advertools` (Scrapy-based, 1.4k stars) for crawling + extraction of
title/meta/h1/canonical/structured-data/internal-links, plus a thin custom
client for plugin-specific REST endpoints (Redirection, RankMath, Yoast).

WordPress is treated here as a *legacy data source*. Tools never write.
"""
from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

REDIRECT_ENDPOINTS = [
    ("/wp-json/redirection/v1/redirect", "Redirection"),
    ("/wp-json/rankmath/v1/redirections", "RankMath"),
    # Yoast Premium endpoint exists but rarely public; we still probe it
    ("/wp-json/yoast/v1/redirects", "Yoast Premium"),
]

UA = (
    "Mozilla/5.0 (compatible; google-seo-mcp/0.3 migration-audit; "
    "+https://github.com/mario-hernandez/google-seo-mcp-claude-code)"
)


def _site_root(wp_url: str) -> str:
    p = urlparse(wp_url if "://" in wp_url else f"https://{wp_url}")
    return f"{p.scheme}://{p.netloc}"


def _http() -> httpx.Client:
    return httpx.Client(
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": UA},
    )


def wp_summary(wp_url: str) -> dict[str, Any]:
    """High-level inventory via WP REST API: post types, taxonomies, plugin probes."""
    root = _site_root(wp_url)
    out: dict[str, Any] = {
        "site_root": root,
        "rest_api_available": False,
        "post_types": {},
        "taxonomies": [],
        "redirect_plugins_detected": [],
    }

    try:
        with _http() as c:
            info = c.get(f"{root}/wp-json/").json()
        out["rest_api_available"] = True
        out["name"] = info.get("name")
        out["description"] = info.get("description")
        out["url"] = info.get("url")
        out["timezone_string"] = info.get("timezone_string")
        out["namespaces"] = info.get("namespaces", [])
    except Exception as e:
        out["rest_api_error"] = str(e)[:200]
        return out

    # Post types with counts (X-WP-Total header trick)
    try:
        with _http() as c:
            types = c.get(f"{root}/wp-json/wp/v2/types").json()
            for slug, t in types.items():
                if not isinstance(t, dict):
                    continue
                count = 0
                try:
                    r = c.get(f"{root}/wp-json/wp/v2/{t.get('rest_base', slug)}?per_page=1")
                    count = int(r.headers.get("X-WP-Total", 0))
                except Exception:
                    pass
                out["post_types"][slug] = {
                    "name": t.get("name"),
                    "rest_base": t.get("rest_base"),
                    "viewable": t.get("viewable", False),
                    "count": count,
                }
    except Exception as e:
        out["post_types_error"] = str(e)[:200]

    # Taxonomies
    try:
        with _http() as c:
            taxs = c.get(f"{root}/wp-json/wp/v2/taxonomies").json()
        out["taxonomies"] = [
            {"slug": k, "name": v.get("name"), "rest_base": v.get("rest_base")}
            for k, v in taxs.items()
            if isinstance(v, dict)
        ]
    except Exception:
        pass

    # Probe redirect plugins
    detected = []
    for ep, plugin_name in REDIRECT_ENDPOINTS:
        try:
            with _http() as c:
                r = c.get(f"{root}{ep}", timeout=10)
            if r.status_code in (200, 401, 403):
                detected.append({"plugin": plugin_name, "endpoint": ep, "status": r.status_code})
        except Exception:
            pass
    out["redirect_plugins_detected"] = detected

    return out


def wp_iterate_urls(wp_url: str, max_pages: int = 500, post_type: str = "any") -> list[dict]:
    """List public URLs via REST API. Returns {url, type, id, title, modified}."""
    root = _site_root(wp_url)
    types: list[str]
    if post_type == "any":
        try:
            with _http() as c:
                t = c.get(f"{root}/wp-json/wp/v2/types").json()
            types = [
                v.get("rest_base", k)
                for k, v in t.items()
                if isinstance(v, dict) and v.get("viewable")
            ]
        except Exception:
            types = ["posts", "pages"]
    else:
        types = [post_type]

    urls: list[dict] = []
    with _http() as c:
        for t in types:
            page = 1
            while len(urls) < max_pages:
                try:
                    r = c.get(
                        f"{root}/wp-json/wp/v2/{t}",
                        params={"per_page": 100, "page": page,
                                "_fields": "id,link,title,type,modified"},
                    )
                    if r.status_code == 400:
                        break  # past last page
                    if r.status_code >= 400:
                        break
                    items = r.json() if r.headers.get("content-type", "").startswith("application/json") else []
                    if not items:
                        break
                    for it in items:
                        if len(urls) >= max_pages:
                            break
                        urls.append({
                            "url": it.get("link"),
                            "type": it.get("type"),
                            "id": it.get("id"),
                            "title": (it.get("title") or {}).get("rendered", ""),
                            "modified": it.get("modified"),
                        })
                    if len(items) < 100:
                        break
                    page += 1
                except Exception:
                    break
    return urls


def crawl_site_advertools(start_url: str, max_pages: int = 200) -> list[dict]:
    """Use advertools (Scrapy-based) to crawl a site and extract SEO meta.

    advertools.crawl() outputs to a JSON-Lines file we then parse. Returns rows
    with: url, title, meta_desc, h1, h2, canonical, og:*, twitter:*, jsonld_*,
    body_text length, internal_links_count, etc.
    """
    import advertools as adv  # type: ignore

    out_path = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jl", delete=False
    ).name

    # advertools crawl is synchronous; respects robots.txt by default
    custom_settings = {
        "USER_AGENT": UA,
        "CLOSESPIDER_PAGECOUNT": max_pages,
        "LOG_LEVEL": "ERROR",
        "ROBOTSTXT_OBEY": True,
    }

    try:
        adv.crawl(
            url_list=[start_url],
            output_file=out_path,
            follow_links=True,
            custom_settings=custom_settings,
        )
    except Exception as e:
        try:
            os.unlink(out_path)
        except OSError:
            pass
        raise RuntimeError(f"advertools crawl failed: {e}") from None

    rows: list[dict] = []
    try:
        with open(out_path, encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass

    return rows


def fetch_wp_redirects(wp_url: str, auth: tuple[str, str] | None = None) -> list[dict]:
    """Best-effort enumeration of redirects from common WP plugins.

    Most plugins require admin auth — pass `auth=(user, app_password)` for
    Redirection. Without auth, public-readable Redirection installs work.
    """
    root = _site_root(wp_url)
    redirects: list[dict] = []

    kw: dict[str, Any] = {"timeout": 20.0, "headers": {"User-Agent": UA}}
    if auth:
        kw["auth"] = auth

    # Redirection plugin (most popular)
    try:
        with httpx.Client(**kw) as c:
            r = c.get(f"{root}/wp-json/redirection/v1/redirect?per_page=100")
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                for it in items:
                    target = it.get("action_data", {})
                    if isinstance(target, dict):
                        target = target.get("url")
                    redirects.append({
                        "source_url": it.get("url"),
                        "target_url": target,
                        "code": it.get("action_code"),
                        "type": it.get("action_type"),
                        "plugin": "Redirection",
                    })
    except Exception:
        pass

    # Rank Math
    try:
        with httpx.Client(**kw) as c:
            r = c.get(f"{root}/wp-json/rankmath/v1/redirections")
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    for it in data:
                        redirects.append({
                            "source_url": it.get("sources"),
                            "target_url": it.get("url_to"),
                            "code": it.get("header_code"),
                            "plugin": "RankMath",
                        })
    except Exception:
        pass

    return redirects


def internal_links_graph_from_crawl(rows: list[dict]) -> dict[str, Any]:
    """Build an internal-links graph from advertools crawl output.

    advertools puts internal links in the `links_url` column as @@-separated
    strings. This function parses them and computes in/out degree per page.
    """
    out_links: dict[str, list[str]] = {}
    in_degree: defaultdict[str, int] = defaultdict(int)

    for row in rows:
        url = row.get("url", "")
        if not url:
            continue
        links_raw = row.get("links_url", "")
        if not links_raw:
            out_links[url] = []
            continue
        # advertools separates with '@@'
        links = [l.strip() for l in str(links_raw).split("@@") if l.strip()]
        # Filter to internal only
        host = urlparse(url).netloc
        internal = [l for l in links if urlparse(urljoin(url, l)).netloc == host]
        normalised = [urljoin(url, l) for l in internal]
        out_links[url] = normalised
        for link in normalised:
            in_degree[link] += 1

    nodes = []
    for url, links in out_links.items():
        nodes.append({
            "url": url,
            "out_degree": len(links),
            "in_degree": in_degree.get(url, 0),
        })

    edges = [{"from": src, "to": dst} for src, dsts in out_links.items() for dst in dsts]

    return {
        "nodes": nodes,
        "edges": edges,
        "orphans": [n["url"] for n in nodes if n["in_degree"] == 0],
        "hubs": sorted(nodes, key=lambda x: x["in_degree"], reverse=True)[:10],
    }
