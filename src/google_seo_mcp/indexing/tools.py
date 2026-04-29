"""IndexNow + Google Indexing API tools."""
from __future__ import annotations

from urllib.parse import urlparse

from ..guardrails import with_meta
from . import (
    generate_indexnow_key,
    submit_google_indexing,
    submit_indexnow,
)


def indexnow_generate_key() -> dict:
    """Generate a fresh IndexNow ownership key (32-char hex).

    After getting the key, host a file at https://{your-site}/{key}.txt with the
    key as its only content. Once that's done, you can call `indexnow_submit`.
    """
    key = generate_indexnow_key()
    return with_meta(
        {
            "key": key,
            "instructions": (
                "Host a plain-text file at https://{YOUR_SITE}/{key}.txt with this "
                "key as its only content. Once accessible, call indexnow_submit "
                "with site=YOUR_SITE and key=this_key."
            ),
        },
        source="indexing.indexnow_generate_key",
    )


def indexnow_submit(
    urls: list[str],
    site: str,
    key: str,
    key_location: str | None = None,
) -> dict:
    """Submit URLs to IndexNow (Bing, Yandex, Seznam — Google ignores it).

    Args:
        urls: Full URLs to notify; all must share the same host.
        site: Bare host (e.g. "www.example.com" — no scheme, no path).
        key: The 32-char IndexNow key hosted at /{key}.txt on the site.
        key_location: Optional explicit URL to the key file (override default path).
    """
    # Validate all URLs share the host
    hosts = {urlparse(u).hostname for u in urls}
    if len(hosts) > 1 or (urls and site not in hosts):
        return with_meta(
            {
                "ok": False,
                "error": (
                    f"All URLs must share host {site!r}. Got hosts: {sorted(h for h in hosts if h)}"
                ),
            },
            source="indexing.indexnow_submit",
            site_url=f"https://{site}/",
        )
    result = submit_indexnow(urls, host=site, key=key, key_location=key_location)
    return with_meta(result, source="indexing.indexnow_submit", site_url=f"https://{site}/")


def indexnow_submit_sitemap(
    sitemap_url: str,
    site: str,
    key: str,
    key_location: str | None = None,
    max_urls: int = 10000,
) -> dict:
    """Fetch a sitemap.xml and submit all listed URLs to IndexNow.

    Note: IndexNow accepts up to 10,000 URLs per call. Larger sitemaps must be
    chunked — we do that automatically and return one result per chunk.
    """
    import httpx
    from defusedxml import ElementTree as ET  # XXE-safe replacement

    from ..security import assert_url_is_public

    assert_url_is_public(sitemap_url)
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(sitemap_url)
    except httpx.HTTPError as e:
        raise RuntimeError(f"Sitemap fetch failed: {e}") from None
    if resp.status_code >= 400:
        raise RuntimeError(f"Sitemap returned {resp.status_code}")

    # Parse XML — handle namespaces ergonomically
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        raise RuntimeError(f"Could not parse sitemap XML: {e}") from None
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [el.text for el in root.findall(".//sm:url/sm:loc", ns) if el.text]

    if not urls:
        # Maybe it's a sitemap index — recurse first one
        sitemap_indexes = [el.text for el in root.findall(".//sm:sitemap/sm:loc", ns) if el.text]
        return with_meta(
            {
                "ok": False,
                "discovered_sub_sitemaps": sitemap_indexes,
                "note": "This is a sitemap index, not a URL set. Submit each child sitemap separately.",
            },
            source="indexing.indexnow_submit_sitemap",
            site_url=f"https://{site}/",
        )

    chunks = [urls[i : i + max_urls] for i in range(0, len(urls), max_urls)]
    results = []
    for chunk in chunks:
        results.append(submit_indexnow(chunk, host=site, key=key, key_location=key_location))

    total_ok = sum(1 for r in results if r.get("ok"))
    total_submitted = sum(r.get("submitted_count", 0) for r in results)
    return with_meta(
        {
            "ok": total_ok == len(results),
            "chunks_submitted": len(results),
            "chunks_ok": total_ok,
            "total_urls_submitted": total_submitted,
            "results_per_chunk": results,
        },
        source="indexing.indexnow_submit_sitemap",
        site_url=f"https://{site}/",
        extra={"sitemap_url": sitemap_url},
    )


def google_indexing_publish(url: str) -> dict:
    """Notify Google Indexing API that a URL was updated.

    Requires `GSC_ALLOW_DESTRUCTIVE=true` AND the `indexing` OAuth scope
    (NOT in the default read-only set). Officially Google supports only
    `JobPosting` and `BroadcastEvent` URLs but it works for general URLs.
    Use sparingly — abuse can lead to API access being revoked.
    """
    return with_meta(
        submit_google_indexing(url, notification_type="URL_UPDATED"),
        source="indexing.google_indexing_publish",
        site_url=url,
    )


def google_indexing_delete(url: str) -> dict:
    """Notify Google Indexing API that a URL was deleted (used for 404/410)."""
    return with_meta(
        submit_google_indexing(url, notification_type="URL_DELETED"),
        source="indexing.google_indexing_delete",
        site_url=url,
    )
