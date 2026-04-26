"""Site listing & inspection tools."""
from __future__ import annotations

from ...auth import get_searchconsole, get_webmasters
from ...guardrails import with_meta


def list_sites() -> dict:
    """List all Search Console properties the authenticated user has access to.

    Returns each site's URL, permission level, and whether it's a domain or URL property.
    """
    wm = get_webmasters()
    resp = wm.sites().list().execute()
    sites = resp.get("siteEntry", [])
    return with_meta(
        [
            {
                "site_url": s.get("siteUrl"),
                "permission_level": s.get("permissionLevel"),
                "type": "domain" if (s.get("siteUrl") or "").startswith("sc-domain:") else "url",
            }
            for s in sites
        ],
        source="webmasters.sites.list",
        site_url="*",
    )


def inspect_url(site_url: str, page_url: str, language: str = "en-US") -> dict:
    """Inspect a single URL against Google's index.

    Args:
        site_url: Property URL (e.g. `https://example.com/` or `sc-domain:example.com`).
        page_url: Full URL to inspect (must belong to `site_url`).
        language: BCP-47 lang for human-readable strings.

    Returns indexing status, last-crawl, canonical, mobile usability, rich-results.
    """
    sc = get_searchconsole()
    body = {"inspectionUrl": page_url, "siteUrl": site_url, "languageCode": language}
    resp = sc.urlInspection().index().inspect(body=body).execute()
    return with_meta(
        resp.get("inspectionResult", {}),
        source="searchconsole.urlInspection.index.inspect",
        site_url=site_url,
    )
