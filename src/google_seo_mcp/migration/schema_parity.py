"""Schema.org parity check — preserve rich results across migration.

Compares JSON-LD blocks of an old URL (WP) vs a new URL (React+SSR) and
reports missing types and lost properties. The goal: catch rich-result
regressions BEFORE Google reindexes the new site and demotes the URL.

Uses extruct (the same lib our schema/ module already depends on).
"""
from __future__ import annotations

from typing import Any

import extruct
import httpx

CRITICAL_PROPS = {
    "Article": ("headline", "datePublished", "author", "image"),
    "BlogPosting": ("headline", "datePublished", "author", "image"),
    "NewsArticle": ("headline", "datePublished", "author", "image"),
    "Product": ("name", "image", "offers", "aggregateRating"),
    "Recipe": ("name", "image", "recipeIngredient", "recipeInstructions"),
    "FAQPage": ("mainEntity",),
    "HowTo": ("name", "step"),
    "BreadcrumbList": ("itemListElement",),
    "Organization": ("name", "logo", "url"),
    "Person": ("name",),
    "WebPage": ("name", "url"),
    "Event": ("name", "startDate", "location"),
    "VideoObject": ("name", "thumbnailUrl", "uploadDate"),
}


def _fetch_jsonld(url: str, timeout: float = 30.0) -> list[dict[str, Any]]:
    from ..security import assert_url_is_public

    assert_url_is_public(url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError(f"Failed to fetch {url!r}: {e}") from None
    extracted = extruct.extract(resp.text, base_url=url, syntaxes=["json-ld"])
    return list(extracted.get("json-ld") or [])


def _types_in(blocks: list[dict[str, Any]]) -> set[str]:
    """Extract @type values (handles arrays and string types)."""
    types: set[str] = set()
    for b in blocks:
        t = b.get("@type")
        if isinstance(t, str):
            types.add(t)
        elif isinstance(t, list):
            for x in t:
                if isinstance(x, str):
                    types.add(x)
        # Also walk one level into common nested holders
        for key in ("itemListElement", "mainEntity", "@graph"):
            inner = b.get(key)
            if isinstance(inner, list):
                for it in inner:
                    if isinstance(it, dict):
                        types |= _types_in([it])
    return types


def _props_for_type(blocks: list[dict[str, Any]], type_name: str) -> set[str]:
    """Collect prop keys present in any block whose @type matches type_name."""
    props: set[str] = set()
    for b in blocks:
        t = b.get("@type")
        match = (t == type_name) or (isinstance(t, list) and type_name in t)
        if match:
            props |= {k for k in b.keys() if not k.startswith("@")}
    return props


def schema_parity_check(old_url: str, new_url: str) -> dict[str, Any]:
    """Compare JSON-LD blocks between old (WP) and new (SSR) URLs.

    Returns: types missing in new, types added in new, lost critical
    properties per shared type, and a parity_score 0..1 (1 = full match).
    """
    old_blocks = _fetch_jsonld(old_url)
    new_blocks = _fetch_jsonld(new_url)

    old_types = _types_in(old_blocks)
    new_types = _types_in(new_blocks)

    missing_types = sorted(old_types - new_types)
    added_types = sorted(new_types - old_types)
    shared_types = sorted(old_types & new_types)

    lost_props: dict[str, list[str]] = {}
    for t in shared_types:
        old_props = _props_for_type(old_blocks, t)
        new_props = _props_for_type(new_blocks, t)
        critical = set(CRITICAL_PROPS.get(t, ()))
        # Report all losses; mark which are critical
        gone = sorted(old_props - new_props)
        if gone:
            lost_props[t] = [
                f"{p} (critical)" if p in critical else p for p in gone
            ]

    # Parity score: types_kept / types_old, weighted by property loss in shared types.
    if not old_types:
        type_score = 1.0
    else:
        type_score = len(shared_types) / len(old_types)
    if shared_types:
        prop_loss_avg = sum(
            len([p for p in (lost_props.get(t) or []) if "(critical)" in p])
            for t in shared_types
        ) / len(shared_types)
        prop_penalty = min(prop_loss_avg * 0.1, 0.4)
    else:
        prop_penalty = 0.0
    parity_score = round(max(0.0, type_score - prop_penalty), 3)

    severity = "ok"
    issues: list[str] = []
    if missing_types:
        severity = "warning"
        issues.append(f"types_lost:{','.join(missing_types)}")
    crit_loss = any(
        any("(critical)" in p for p in props) for props in lost_props.values()
    )
    if crit_loss:
        severity = "critical"
        issues.append("critical_property_lost")
    if parity_score < 0.5:
        severity = "critical"
        issues.append(f"low_parity_score:{parity_score}")

    return {
        "old_url": old_url,
        "new_url": new_url,
        "old_types": sorted(old_types),
        "new_types": sorted(new_types),
        "missing_types": missing_types,
        "added_types": added_types,
        "lost_properties_per_type": lost_props,
        "parity_score": parity_score,
        "severity": severity,
        "issues": issues,
        "old_blocks_count": len(old_blocks),
        "new_blocks_count": len(new_blocks),
    }
