"""Post-migration indexation recovery monitor.

Tracks how Google indexes the new URLs in the days/weeks AFTER a migration.
Uses GSC URL Inspection API (NOT the Indexing API, which is officially
limited to JobPosting/BroadcastEvent). Quota: 2000/day/property, 600/min.

Classifies each URL into:
  - INDEXED        — verdict PASS, status indexed
  - DISCOVERED     — Google knows the URL but hasn't crawled or chose not to index
  - SOFT_404       — page returns 200 but Google sees thin/empty content
  - BLOCKED        — robots.txt or noindex
  - ERROR          — fetch failure, redirect issue, etc.
  - UNKNOWN        — verdict NEUTRAL with no clear category
"""
from __future__ import annotations

import time
from typing import Any

from googleapiclient.errors import HttpError

from ..gsc.tools.sites import inspect_url


def _classify(result: dict[str, Any]) -> str:
    """Map a urlInspection.index.inspect result to a coarse category."""
    idx = result.get("indexStatusResult") or {}
    verdict = idx.get("verdict") or ""
    coverage = (idx.get("coverageState") or "").lower()
    robots = (idx.get("robotsTxtState") or "").upper()
    indexing = (idx.get("indexingState") or "").upper()
    page_fetch = (idx.get("pageFetchState") or "").upper()

    if verdict == "PASS":
        return "INDEXED"
    if "soft 404" in coverage or "soft-404" in coverage:
        return "SOFT_404"
    if robots == "DISALLOWED" or indexing == "BLOCKED_BY_META_TAG" or indexing == "BLOCKED_BY_HTTP_HEADER":
        return "BLOCKED"
    if page_fetch in ("SOFT_404", "BLOCKED_ROBOTS_TXT", "NOT_FOUND", "ACCESS_DENIED", "SERVER_ERROR"):
        return "ERROR"
    if "discovered" in coverage and "not indexed" in coverage:
        return "DISCOVERED"
    if "crawled" in coverage and "not indexed" in coverage:
        return "DISCOVERED"
    return "UNKNOWN"


def indexation_recovery_monitor(
    site_url: str,
    urls: list[str],
    days_after_launch: int | None = None,
    pause_ms: int = 100,
) -> dict[str, Any]:
    """Inspect each URL via GSC URL Inspection and aggregate by category.

    Args:
        site_url: Verified GSC property (URL prefix or sc-domain:).
        urls: URLs to inspect. Cap at 600/min (we sleep ``pause_ms`` between
              calls — default ~10/sec stays well under quota).
        days_after_launch: Optional context tag included in output.
        pause_ms: Throttle between inspections (default 100ms).

    Returns ``{summary{}, classified{}, errors[]}``. ``classified`` maps
    each URL to its category and the raw inspection verdict.
    """
    if not urls:
        raise ValueError("urls must be a non-empty list")

    classified: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []

    for u in urls:
        try:
            r = inspect_url(site_url, u)
            data = r.get("data") if isinstance(r, dict) and "data" in r else r
            cat = _classify(data or {})
            idx = (data or {}).get("indexStatusResult") or {}
            classified[u] = {
                "category": cat,
                "verdict": idx.get("verdict"),
                "coverage_state": idx.get("coverageState"),
                "indexing_state": idx.get("indexingState"),
                "robots_txt_state": idx.get("robotsTxtState"),
                "page_fetch_state": idx.get("pageFetchState"),
                "last_crawl_time": idx.get("lastCrawlTime"),
                "google_canonical": idx.get("googleCanonical"),
            }
        except HttpError as e:
            errors.append({"url": u, "http_error": str(e)[:200]})
        except Exception as e:  # noqa: BLE001 — surface any other failure per-url
            errors.append({"url": u, "error": f"{type(e).__name__}: {str(e)[:200]}"})
        if pause_ms:
            time.sleep(pause_ms / 1000)

    summary: dict[str, int] = {}
    for entry in classified.values():
        summary[entry["category"]] = summary.get(entry["category"], 0) + 1

    total = len(urls)
    indexed = summary.get("INDEXED", 0)
    indexation_rate = round(indexed / total, 3) if total else 0.0

    health = "green"
    if total > 0:
        if indexation_rate < 0.5:
            health = "red"
        elif indexation_rate < 0.85:
            health = "amber"
    notes: list[str] = []
    if errors:
        notes.append(f"{len(errors)} URLs failed inspection (see `errors`).")
    if summary.get("DISCOVERED", 0) > total * 0.2 and total > 5:
        notes.append(
            ">20% of URLs are 'Discovered, not indexed' — Google sees them but isn't indexing. "
            "Likely thin content, low internal link equity, or quality signals."
        )
    if summary.get("SOFT_404", 0):
        notes.append(
            f"{summary['SOFT_404']} URL(s) returning soft-404. Check the destination "
            "renders real content (SSR may be returning shell HTML)."
        )
    if summary.get("BLOCKED", 0):
        notes.append(
            f"{summary['BLOCKED']} URL(s) blocked by robots/meta. Verify intentional."
        )

    return {
        "site_url": site_url,
        "total_urls": total,
        "summary": summary,
        "indexation_rate": indexation_rate,
        "health": health,
        "days_after_launch": days_after_launch,
        "classified": classified,
        "errors": errors,
        "notes": notes,
    }
