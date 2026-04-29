"""Sitemap parsing + diff for migration planning."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlparse

import httpx

UA = "google-seo-mcp/0.3 sitemap-diff"


def parse_sitemap(url: str, max_urls: int = 50000) -> list[str]:
    """Recursively parse a sitemap (or sitemap index) and return all URLs.

    Supports nested sitemap indexes. Caps at max_urls to avoid runaway parses.
    """
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": UA}) as c:
            resp = c.get(url)
    except httpx.HTTPError as e:
        raise RuntimeError(f"Sitemap fetch failed: {e}") from None
    if resp.status_code >= 400:
        raise RuntimeError(f"Sitemap returned {resp.status_code} at {url}")

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        raise RuntimeError(f"Could not parse sitemap XML: {e}") from None

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls: list[str] = []

    # URL set
    for loc in root.findall(".//sm:url/sm:loc", ns):
        if loc.text:
            urls.append(loc.text.strip())
            if len(urls) >= max_urls:
                return urls

    # Sitemap index — recurse
    for sub in root.findall(".//sm:sitemap/sm:loc", ns):
        if not sub.text:
            continue
        try:
            urls.extend(parse_sitemap(sub.text.strip(), max_urls=max_urls - len(urls)))
        except Exception:
            continue
        if len(urls) >= max_urls:
            break

    return urls[:max_urls]


def sitemap_diff(old_sitemap_url: str, new_sitemap_url: str) -> dict[str, Any]:
    """Compare two sitemaps. Returns URLs added, removed, and unchanged.

    Useful for migration validation: confirm the new site exposes everything
    the old one did (missing URLs need 301s) and no junk URLs slipped in.
    """
    old_urls = set(parse_sitemap(old_sitemap_url))
    new_urls = set(parse_sitemap(new_sitemap_url))

    only_old = old_urls - new_urls
    only_new = new_urls - old_urls
    common = old_urls & new_urls

    return {
        "old_sitemap": old_sitemap_url,
        "new_sitemap": new_sitemap_url,
        "old_count": len(old_urls),
        "new_count": len(new_urls),
        "common_count": len(common),
        "only_in_old_count": len(only_old),
        "only_in_new_count": len(only_new),
        "only_in_old_sample": sorted(only_old)[:50],
        "only_in_new_sample": sorted(only_new)[:50],
        "common_sample": sorted(common)[:20],
    }


def sitemap_validate(sitemap_url: str, sample_size: int = 50, timeout: float = 10.0) -> dict[str, Any]:
    """Parse a sitemap and HEAD-check a sample of URLs.

    Returns counts of URLs that return 2xx vs 3xx vs 4xx vs 5xx vs unreachable.
    Use this on a freshly deployed sitemap to catch dead pages before Googlebot does.
    """
    urls = parse_sitemap(sitemap_url)
    if not urls:
        return {
            "sitemap_url": sitemap_url,
            "url_count": 0,
            "error": "No URLs found in sitemap",
        }

    # Sample evenly through the list
    if len(urls) > sample_size:
        step = max(1, len(urls) // sample_size)
        sample = urls[::step][:sample_size]
    else:
        sample = urls

    status_counts: dict[str, int] = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0, "error": 0}
    failures: list[dict] = []

    with httpx.Client(timeout=timeout, follow_redirects=False, headers={"User-Agent": UA}) as c:
        for u in sample:
            try:
                r = c.head(u)
                code = r.status_code
                bucket = (
                    "2xx" if 200 <= code < 300 else
                    "3xx" if 300 <= code < 400 else
                    "4xx" if 400 <= code < 500 else
                    "5xx" if 500 <= code < 600 else
                    "error"
                )
                status_counts[bucket] += 1
                if code >= 400:
                    failures.append({"url": u, "status": code})
            except Exception as e:
                status_counts["error"] += 1
                failures.append({"url": u, "error": str(e)[:100]})

    return {
        "sitemap_url": sitemap_url,
        "url_count": len(urls),
        "sampled": len(sample),
        "status_distribution": status_counts,
        "failures": failures[:30],
        "health": (
            "green" if status_counts["4xx"] == 0 and status_counts["5xx"] == 0 and status_counts["error"] == 0
            else "amber" if status_counts["4xx"] + status_counts["5xx"] + status_counts["error"] <= 3
            else "red"
        ),
    }
