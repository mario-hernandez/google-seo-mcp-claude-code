"""Sitemap tools."""
from __future__ import annotations

import os

from ...auth import get_webmasters
from ...guardrails import with_meta


def list_sitemaps(site_url: str) -> dict:
    """List sitemaps submitted for a property, with errors/warnings/last-submitted info."""
    wm = get_webmasters()
    resp = wm.sitemaps().list(siteUrl=site_url).execute()
    return with_meta(
        resp.get("sitemap", []), source="webmasters.sitemaps.list", site_url=site_url
    )


def submit_sitemap(site_url: str, feedpath: str) -> dict:
    """Submit a sitemap. Requires GSC_ALLOW_DESTRUCTIVE=true.

    Args:
        site_url: Property URL.
        feedpath: Full sitemap URL (e.g. https://example.com/sitemap.xml).
    """
    if os.getenv("GSC_ALLOW_DESTRUCTIVE") != "true":
        return {
            "error": "destructive_disabled",
            "message": (
                "submit_sitemap is a destructive operation. Set env "
                "`GSC_ALLOW_DESTRUCTIVE=true` and restart the MCP to enable. "
                "Read-only OAuth scope is also insufficient — requires `webmasters` scope."
            ),
        }
    wm = get_webmasters()
    wm.sitemaps().submit(siteUrl=site_url, feedpath=feedpath).execute()
    return with_meta(
        {"status": "submitted", "feedpath": feedpath},
        source="webmasters.sitemaps.submit",
        site_url=site_url,
    )
