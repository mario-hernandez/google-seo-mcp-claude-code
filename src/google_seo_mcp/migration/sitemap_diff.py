"""Sitemap parsing + diff for migration planning."""
from __future__ import annotations

import time

# defusedxml protects against billion-laughs / quadratic blowup / external
# entity attacks when the LLM is asked (potentially via prompt injection)
# to parse a hostile sitemap.
from defusedxml.ElementTree import ParseError, fromstring
from typing import Any
from urllib.parse import urlparse

import httpx

from ..security import assert_url_is_public

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# XML namespaces commonly seen in sitemaps
_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "xhtml": "http://www.w3.org/1999/xhtml",
}

# Body size cap (10 MB). Sitemaps that exceed this are pathological.
_MAX_BODY_BYTES = 10 * 1024 * 1024


def parse_sitemap(url: str, max_urls: int = 50000) -> list[str]:
    """Backwards-compatible: returns flat list of URLs (no hreflang)."""
    return [e["url"] for e in parse_sitemap_with_alternates(url, max_urls=max_urls)]


def parse_sitemap_with_alternates(url: str, max_urls: int = 50000) -> list[dict[str, Any]]:
    """Recursively parse a sitemap (or sitemap index) with hreflang alternates.

    Returns a list of ``{"url": str, "alternates": {hreflang: href, ...}}``.
    The alternate dict captures ``<xhtml:link rel="alternate" hreflang>``
    siblings that Google recommends for multi-language sitemaps. Earlier
    versions silently ignored these — Inditex / Booking-class sitemaps
    were treated as monolingual.
    """
    assert_url_is_public(url)
    try:
        with httpx.Client(
            timeout=30.0, follow_redirects=True, headers={"User-Agent": UA}
        ) as c:
            resp = c.get(url)
    except httpx.HTTPError as e:
        raise RuntimeError(f"Sitemap fetch failed: {e}") from None
    if resp.status_code >= 400:
        raise RuntimeError(f"Sitemap returned {resp.status_code} at {url}")
    body = resp.content
    if len(body) > _MAX_BODY_BYTES:
        raise RuntimeError(
            f"Sitemap body exceeds {_MAX_BODY_BYTES} bytes ({len(body)}); refusing to parse."
        )

    try:
        root = fromstring(body)
    except ParseError as e:
        raise RuntimeError(f"Could not parse sitemap XML: {e}") from None

    entries: list[dict[str, Any]] = []

    # URL set
    for url_node in root.findall(".//sm:url", _NS):
        loc = url_node.find("sm:loc", _NS)
        if loc is None or not loc.text:
            continue
        entry: dict[str, Any] = {"url": loc.text.strip(), "alternates": {}}
        for alt in url_node.findall("xhtml:link", _NS):
            rel = (alt.attrib.get("rel") or "").lower()
            if rel != "alternate":
                continue
            hreflang = (alt.attrib.get("hreflang") or "").strip()
            href = (alt.attrib.get("href") or "").strip()
            if hreflang and href:
                entry["alternates"][hreflang] = href
        entries.append(entry)
        if len(entries) >= max_urls:
            return entries

    # Sitemap index — recurse
    for sub in root.findall(".//sm:sitemap/sm:loc", _NS):
        if not sub.text:
            continue
        try:
            entries.extend(
                parse_sitemap_with_alternates(
                    sub.text.strip(), max_urls=max_urls - len(entries)
                )
            )
        except Exception:
            continue
        if len(entries) >= max_urls:
            break

    return entries[:max_urls]


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

    # Concurrent GET (with Range: 0-0 for efficiency) — many origins behind
    # CF / Workers reject HEAD with 405. Range avoids downloading the body.
    # Retry once on 503/504 (CDN incident or rolling-deploy hiccup).
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _check_one(client: httpx.Client, u: str) -> tuple[str, int | None, str | None]:
        for attempt in (1, 2):
            try:
                r = client.get(u, headers={"Range": "bytes=0-0"})
                if r.status_code in (503, 504) and attempt == 1:
                    time.sleep(0.5)
                    continue
                return u, r.status_code, None
            except Exception as e:  # noqa: BLE001 — collect any network error
                if attempt == 1:
                    time.sleep(0.5)
                    continue
                return u, None, str(e)[:100]
        return u, None, "exhausted retries"

    with httpx.Client(timeout=timeout, follow_redirects=False, headers={"User-Agent": UA}) as c:
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(_check_one, c, u) for u in sample]
            for f in as_completed(futures):
                u, code, err = f.result()
                if err:
                    status_counts["error"] += 1
                    failures.append({"url": u, "error": err})
                    continue
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
