"""robots.txt audit + diff for migrations.

Parsing robots.txt is solved by stdlib ``urllib.robotparser``, but for
migrations the senior question is *which URLs that already rank are
suddenly blocked by the new robots.txt?*. That requires intersecting the
new robots policy with GSC clicked URLs — exactly what this module does.
"""
from __future__ import annotations

import urllib.robotparser
from typing import Any
from urllib.parse import urljoin

import httpx

from ..security import assert_url_is_public

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def _fetch(robots_url: str, timeout: float = 15.0) -> tuple[int, str | None]:
    assert_url_is_public(robots_url)
    try:
        with httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": UA}
        ) as c:
            r = c.get(robots_url)
        return r.status_code, (r.text if r.status_code < 400 else None)
    except httpx.HTTPError as e:
        raise RuntimeError(f"robots.txt fetch failed: {e}") from None


def _parser_from(text: str) -> urllib.robotparser.RobotFileParser:
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(text.splitlines())
    return rp


def robots_audit(
    origin_url: str, sample_paths: list[str] | None = None
) -> dict[str, Any]:
    """Inspect robots.txt for one origin: presence, sitemap declarations,
    crawl-delay, and disallow patterns for Googlebot vs other major bots.
    """
    if not origin_url.startswith(("http://", "https://")):
        raise ValueError("origin_url must include scheme (https://...)")
    robots_url = urljoin(origin_url + "/", "robots.txt")
    status, text = _fetch(robots_url)
    if not text:
        return {
            "origin": origin_url,
            "robots_txt": {"url": robots_url, "status": status, "present": False},
            "warnings": [
                f"robots.txt status {status} — most crawlers default to allow-all "
                "but this is fragile. Publish an explicit /robots.txt."
            ],
        }

    sitemaps: list[str] = []
    crawl_delays: dict[str, float] = {}
    disallows: dict[str, list[str]] = {}
    current_uas: list[str] = []
    for raw in text.splitlines():
        ln = raw.split("#", 1)[0].strip()
        if not ln:
            current_uas = []
            continue
        if ":" not in ln:
            continue
        directive, _, value = ln.partition(":")
        directive = directive.strip().lower()
        value = value.strip()
        if directive == "user-agent":
            current_uas = [value]
        elif directive == "sitemap":
            if value:
                sitemaps.append(value)
        elif directive == "crawl-delay":
            try:
                cd = float(value)
                for ua in current_uas:
                    crawl_delays[ua] = cd
            except ValueError:
                pass
        elif directive == "disallow":
            for ua in current_uas:
                disallows.setdefault(ua, []).append(value)

    sample_paths = sample_paths or ["/", "/wp-admin/", "/search"]
    rp = _parser_from(text)
    sample_results = {
        path: {
            "googlebot": rp.can_fetch("Googlebot", urljoin(origin_url, path)),
            "googlebot_smartphone": rp.can_fetch(
                "Googlebot-smartphone", urljoin(origin_url, path)
            ),
            "bingbot": rp.can_fetch("bingbot", urljoin(origin_url, path)),
            "any_user_agent": rp.can_fetch("*", urljoin(origin_url, path)),
        }
        for path in sample_paths
    }

    warnings: list[str] = []
    if not sitemaps:
        warnings.append("robots.txt declares no Sitemap — discoverability hit.")
    if "*" in disallows and "/" in disallows["*"]:
        warnings.append("`Disallow: /` for User-agent: *  — site is fully blocked.")
    if any(cd >= 5 for cd in crawl_delays.values()):
        warnings.append(
            "Crawl-delay >= 5s — Googlebot ignores Crawl-delay but Bingbot honors it. "
            "May hurt Bing crawl rate; consider GSC Settings → Crawl rate instead."
        )

    return {
        "origin": origin_url,
        "robots_txt": {
            "url": robots_url,
            "status": status,
            "size_bytes": len(text),
            "present": True,
        },
        "sitemaps_declared": sitemaps,
        "crawl_delays": crawl_delays,
        "disallow_count_per_user_agent": {ua: len(d) for ua, d in disallows.items()},
        "sample_paths": sample_results,
        "warnings": warnings,
    }


def robots_diff(
    old_origin_url: str,
    new_origin_url: str,
    paths_to_check: list[str],
    user_agent: str = "Googlebot",
) -> dict[str, Any]:
    """Compare two robots.txt files (e.g. WordPress origin vs new SSR domain)
    and intersect with a list of paths that were ranked / clicked.

    For each path, returns whether it was allowed under old vs new robots
    and flags it as ``newly_blocked`` (highest severity — these need an
    URGENT robots.txt fix or 301 to an allowed path).

    The ``paths_to_check`` list typically comes from
    ``gsc_search_analytics(dimensions=['page'], row_limit=25000)`` — the
    URLs that already drive clicks.
    """
    old_robots_url = urljoin(old_origin_url + "/", "robots.txt")
    new_robots_url = urljoin(new_origin_url + "/", "robots.txt")
    _, old_text = _fetch(old_robots_url)
    _, new_text = _fetch(new_robots_url)
    if not old_text or not new_text:
        raise RuntimeError(
            f"Could not fetch both robots.txt files (old={bool(old_text)}, "
            f"new={bool(new_text)})"
        )

    old_rp = _parser_from(old_text)
    new_rp = _parser_from(new_text)

    rows: list[dict[str, Any]] = []
    newly_blocked: list[str] = []
    newly_allowed: list[str] = []
    for path in paths_to_check:
        old_allowed = old_rp.can_fetch(
            user_agent, urljoin(old_origin_url, path)
        )
        new_allowed = new_rp.can_fetch(
            user_agent, urljoin(new_origin_url, path)
        )
        rows.append({
            "path": path,
            "old_allowed": old_allowed,
            "new_allowed": new_allowed,
            "verdict": (
                "newly_blocked" if old_allowed and not new_allowed
                else "newly_allowed" if (not old_allowed) and new_allowed
                else "unchanged"
            ),
        })
        if old_allowed and not new_allowed:
            newly_blocked.append(path)
        elif (not old_allowed) and new_allowed:
            newly_allowed.append(path)

    return {
        "user_agent": user_agent,
        "old_origin": old_origin_url,
        "new_origin": new_origin_url,
        "paths_checked": len(paths_to_check),
        "newly_blocked_count": len(newly_blocked),
        "newly_allowed_count": len(newly_allowed),
        "newly_blocked": newly_blocked[:200],
        "newly_allowed": newly_allowed[:200],
        "rows_sample": rows[:50],
        "severity": (
            "critical" if newly_blocked
            else "warning" if newly_allowed
            else "ok"
        ),
    }
