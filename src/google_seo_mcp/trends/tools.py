"""Trends, Suggest, and Alerts tools."""
from __future__ import annotations

from defusedxml import ElementTree as ET  # XXE-safe replacement
from typing import Any
from urllib.parse import urlencode

import httpx

from ..guardrails import with_meta

SUGGEST_ENDPOINT = "https://suggestqueries.google.com/complete/search"


def google_suggest(
    keyword: str,
    *,
    hl: str = "es",
    gl: str = "ES",
    timeout: float = 15.0,
) -> dict:
    """Google Autocomplete suggestions for a keyword.

    Free, no auth. Returns the same suggestions a user sees while typing in
    google.com — these are the queries Google's traffic actually flows through.

    Args:
        hl: Interface language (BCP-47, e.g. "es", "en", "fr").
        gl: Country code (uppercase, e.g. "ES", "US", "FR").
    """
    params = {"client": "firefox", "q": keyword, "hl": hl, "gl": gl}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{SUGGEST_ENDPOINT}?{urlencode(params)}")
    except httpx.HTTPError as e:
        raise RuntimeError(f"Suggest request failed: {e}") from None
    if resp.status_code >= 400:
        raise RuntimeError(f"Suggest returned {resp.status_code}: {resp.text[:200]}")

    # The endpoint returns text/javascript with latin-1 encoding when accents
    # are present. resp.text handles encoding negotiation; parse from there.
    import json as _json
    try:
        data = _json.loads(resp.text)
        suggestions = data[1] if isinstance(data, list) and len(data) > 1 else []
    except (ValueError, IndexError):
        suggestions = []

    return with_meta(
        {
            "keyword": keyword,
            "suggestions": suggestions,
            "count": len(suggestions),
        },
        source="trends.google_suggest",
        extra={"hl": hl, "gl": gl},
    )


def google_suggest_alphabet(
    keyword: str,
    *,
    hl: str = "es",
    gl: str = "ES",
) -> dict:
    """Run Suggest with `keyword + a`, `keyword + b`, ..., `keyword + z`.

    Replicates the "alphabet method" SEOs use to discover long-tails. Returns
    a flat deduped list of all suggestions across the 26 calls.
    """
    all_suggestions: set[str] = set()
    per_letter: dict[str, list[str]] = {}
    for letter in "abcdefghijklmnopqrstuvwxyz":
        try:
            result = google_suggest(f"{keyword} {letter}", hl=hl, gl=gl)
            sug_list = result["data"]["suggestions"]
        except Exception:
            sug_list = []
        per_letter[letter] = sug_list
        all_suggestions.update(sug_list)
    return with_meta(
        {
            "seed": keyword,
            "total_unique": len(all_suggestions),
            "all_suggestions": sorted(all_suggestions),
            "per_letter": per_letter,
        },
        source="trends.google_suggest_alphabet",
        extra={"hl": hl, "gl": gl},
    )


def google_trends_keyword(
    keyword: str,
    *,
    timeframe: str = "today 12-m",
    geo: str = "ES",
    hl: str = "es-ES",
) -> dict:
    """Time series of relative search interest from Google Trends.

    Args:
        timeframe: pytrends format. Common: "today 5-y", "today 12-m",
            "today 3-m", "now 7-d".
        geo: 2-letter country code or "" for worldwide.
    """
    try:
        from pytrends.request import TrendReq  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "Trends tools require `pytrends`. Install: pip install pytrends"
        ) from e

    pt = TrendReq(hl=hl, tz=0)
    pt.build_payload([keyword], timeframe=timeframe, geo=geo)
    df = pt.interest_over_time()
    if df.empty:
        return with_meta(
            {"available": False, "reason": "No data returned by Trends"},
            source="trends.google_trends_keyword",
            extra={"keyword": keyword, "timeframe": timeframe, "geo": geo},
        )
    series = [
        {"date": idx.strftime("%Y-%m-%d"), "value": int(row[keyword])}
        for idx, row in df.iterrows()
        if not row.get("isPartial", False)
    ]
    return with_meta(
        {
            "keyword": keyword,
            "timeframe": timeframe,
            "geo": geo,
            "series": series,
            "max": max((p["value"] for p in series), default=0),
            "min": min((p["value"] for p in series), default=0),
            "latest": series[-1] if series else None,
        },
        source="trends.google_trends_keyword",
    )


def google_trends_related(
    keyword: str,
    *,
    timeframe: str = "today 12-m",
    geo: str = "ES",
    hl: str = "es-ES",
) -> dict:
    """Related queries from Google Trends — both top (consistent) and rising
    (acceleration). The "rising" list is gold for early-trend content.
    """
    try:
        from pytrends.request import TrendReq  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "Trends tools require `pytrends`. Install: pip install pytrends"
        ) from e

    pt = TrendReq(hl=hl, tz=0)
    pt.build_payload([keyword], timeframe=timeframe, geo=geo)
    rel = pt.related_queries() or {}
    item = rel.get(keyword, {}) or {}

    def _df_to_list(df: Any) -> list[dict]:
        if df is None:
            return []
        try:
            return df.head(20).to_dict(orient="records")
        except Exception:
            return []

    return with_meta(
        {
            "keyword": keyword,
            "top": _df_to_list(item.get("top")),
            "rising": _df_to_list(item.get("rising")),
        },
        source="trends.google_trends_related",
        extra={"timeframe": timeframe, "geo": geo},
    )


def alerts_rss_parse(rss_url: str, max_items: int = 50) -> dict:
    """Parse a Google Alerts RSS feed (or any RSS feed) and return items.

    Google Alerts RSS feed URLs come from manually creating an alert at
    https://www.google.com/alerts and choosing "Deliver to: RSS feed". Pass that
    URL here to fetch the latest brand mentions/news without scraping anything.

    Args:
        rss_url: Public RSS feed URL.
        max_items: Cap on items returned.
    """
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(rss_url)
    except httpx.HTTPError as e:
        raise RuntimeError(f"RSS fetch failed: {e}") from None
    if resp.status_code >= 400:
        raise RuntimeError(f"RSS returned {resp.status_code}")

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        raise RuntimeError(f"Could not parse RSS: {e}") from None

    # Atom (Google Alerts uses atom) and RSS 2.0 both supported
    items: list[dict[str, Any]] = []
    atom_ns = {"a": "http://www.w3.org/2005/Atom"}

    for entry in root.findall(".//a:entry", atom_ns)[:max_items]:
        title = entry.findtext("a:title", default="", namespaces=atom_ns)
        link_el = entry.find("a:link", atom_ns)
        link = link_el.get("href") if link_el is not None else ""
        published = entry.findtext("a:published", default="", namespaces=atom_ns)
        summary = entry.findtext("a:content", default="", namespaces=atom_ns) or entry.findtext(
            "a:summary", default="", namespaces=atom_ns
        )
        items.append({
            "title": title,
            "link": link,
            "published": published,
            "summary": summary[:500] if summary else "",
        })

    if not items:
        for item in root.findall(".//item")[:max_items]:
            items.append({
                "title": item.findtext("title", "") or "",
                "link": item.findtext("link", "") or "",
                "published": item.findtext("pubDate", "") or "",
                "summary": (item.findtext("description", "") or "")[:500],
            })

    return with_meta(
        {"feed_url": rss_url, "count": len(items), "items": items},
        source="trends.alerts_rss_parse",
    )
