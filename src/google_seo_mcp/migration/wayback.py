"""Wayback Machine baseline — anchor what existed before migration.

Step 1 of any migration workflow: capture the public archive's snapshot of
your site BEFORE you change anything. Lets you prove "what we had" months
later when stakeholders ask "did the migration kill traffic?".

Uses the Internet Archive Wayback CDX API via `waybackpy` (free, no key).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx


def wayback_baseline(
    origin_url: str,
    snapshot_date: str | None = None,
    max_urls: int = 500,
) -> dict[str, Any]:
    """Fetch the Wayback Machine's snapshot inventory for an origin.

    Returns the most recent archived snapshot per URL prefix (or the closest
    to ``snapshot_date`` if provided as ``YYYYMMDD``). Use this BEFORE
    migration as a public anchor of what existed.

    Args:
        origin_url: Origin to query, e.g. ``https://www.example.com``.
        snapshot_date: Optional ``YYYYMMDD`` to anchor closest snapshot.
        max_urls: Cap on URLs returned (CDX API can return tens of thousands).

    Returns ``{anchor_url, urls_archived, snapshots[]}``. Each snapshot
    entry has ``original_url``, ``archived_url`` (the wayback link),
    ``timestamp``, ``status``, ``mime_type``.
    """
    from ..security import assert_url_is_public

    # We talk to web.archive.org (always public), so the SSRF guard checks
    # the user-supplied origin only — to stop someone shipping a CDX-style
    # request whose effective target is internal.
    if origin_url.startswith(("http://", "https://")):
        assert_url_is_public(origin_url)
    # Strip protocol for the CDX query (Wayback handles both http/https)
    host = origin_url.replace("https://", "").replace("http://", "").rstrip("/")
    cdx_url = (
        f"https://web.archive.org/cdx/search/cdx"
        f"?url={host}/*"
        f"&output=json"
        f"&fl=original,timestamp,statuscode,mimetype"
        f"&filter=mimetype:text/html"
        f"&filter=statuscode:200"
        f"&collapse=urlkey"
        f"&limit={max_urls}"
    )
    if snapshot_date:
        # Validate format (loose)
        if not (len(snapshot_date) >= 4 and snapshot_date.isdigit()):
            raise ValueError("snapshot_date must be a numeric YYYY[MMDD] string")
        cdx_url += f"&from={snapshot_date}&to={snapshot_date}"

    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            resp = client.get(cdx_url)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        raise RuntimeError(f"Wayback CDX query failed: {e}") from None
    except ValueError as e:
        raise RuntimeError(f"Wayback CDX returned invalid JSON: {e}") from None

    if not data or len(data) < 2:
        return {
            "origin_url": origin_url,
            "anchor_url": f"https://web.archive.org/web/*/{host}",
            "urls_archived": 0,
            "snapshots": [],
            "note": "No archived snapshots found in CDX index.",
        }

    # First row is column headers
    rows = data[1:]
    snapshots = []
    latest_ts = ""
    for r in rows:
        if len(r) < 4:
            continue
        original, ts, status, mime = r[0], r[1], r[2], r[3]
        snapshots.append({
            "original_url": original,
            "timestamp": ts,
            "archived_url": f"https://web.archive.org/web/{ts}/{original}",
            "status": status,
            "mime_type": mime,
        })
        if ts > latest_ts:
            latest_ts = ts

    anchor = (
        f"https://web.archive.org/web/{latest_ts}/{host}"
        if latest_ts
        else f"https://web.archive.org/web/*/{host}"
    )

    return {
        "origin_url": origin_url,
        "anchor_url": anchor,
        "latest_snapshot_timestamp": latest_ts or None,
        "urls_archived": len(snapshots),
        "snapshots": snapshots,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
    }
