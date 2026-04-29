"""Hreflang cluster audit — preserve multi-language SEO across migration.

Verifies that every URL in a language cluster (ES, FR, EN…) declares
reciprocal hreflang back to ALL siblings, including itself, and exactly
one ``x-default``. Google demotes clusters with broken reciprocity.

Designed for cross-domain clusters too (e.g. example.com ES ↔
example.org FR), not just intra-site `/es/` `/fr/` paths.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx

LINK_HREFLANG_RE = re.compile(
    r'<link\s+(?P<attrs>[^>]*?)\s*/?\s*>',
    re.IGNORECASE | re.DOTALL,
)
ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"', re.IGNORECASE)


def _extract_hreflangs(html: str) -> list[dict[str, str]]:
    """Extract every <link rel=alternate hreflang=… href=…> from the HTML."""
    out: list[dict[str, str]] = []
    for m in LINK_HREFLANG_RE.finditer(html):
        attrs = dict(ATTR_RE.findall(m.group("attrs") or ""))
        if attrs.get("rel", "").lower() != "alternate":
            continue
        if "hreflang" not in attrs:
            continue
        out.append({"hreflang": attrs["hreflang"].lower(), "href": attrs.get("href", "")})
    return out


def _fetch(url: str, timeout: float = 30.0) -> str:
    from ..security import assert_url_is_public

    assert_url_is_public(url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        ),
    }
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def _normalize(url: str) -> str:
    """Canonicalize for comparison: strip trailing slash and fragments."""
    p = urlparse(url)
    path = (p.path or "/").rstrip("/") or "/"
    base = f"{p.scheme}://{p.netloc}{path}"
    if p.query:
        base += f"?{p.query}"
    return base


def hreflang_cluster_audit(
    cluster: dict[str, list[str]] | None = None,
    urls_es: list[str] | None = None,
    urls_fr: list[str] | None = None,
) -> dict[str, Any]:
    """Audit a multi-language URL cluster for hreflang reciprocity.

    Two argument styles are accepted:

    - ``cluster={"es-ES": ["url1", "url2"], "fr-FR": ["urlA"]}`` — preferred,
      arbitrary languages.
    - ``urls_es=[...], urls_fr=[...]`` — backwards-compatible shortcut for
      ES/FR pairs (the example.com use case).

    Each lang list must align positionally: ``cluster["es-ES"][i]`` and
    ``cluster["fr-FR"][i]`` are translations of each other.

    Returns reciprocity report per index in the cluster.
    """
    if cluster is None:
        if not urls_es or not urls_fr:
            raise ValueError("Provide cluster=... or both urls_es and urls_fr")
        cluster = {"es": urls_es, "fr": urls_fr}

    langs = list(cluster.keys())
    sizes = {k: len(v) for k, v in cluster.items()}
    n = max(sizes.values())
    if len(set(sizes.values())) != 1:
        return {
            "ok": False,
            "error": f"Cluster lists have mismatched lengths: {sizes}",
            "cluster_size": n,
        }

    pairs_ok: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    for i in range(n):
        siblings: dict[str, str] = {lang: cluster[lang][i] for lang in langs}
        # Fetch every URL in this row once
        try:
            tags_per_url: dict[str, list[dict[str, str]]] = {
                u: _extract_hreflangs(_fetch(u)) for u in siblings.values()
            }
        except httpx.HTTPError as e:
            issues.append({
                "row": i,
                "siblings": siblings,
                "error": f"fetch_failed: {e}",
            })
            continue

        row_issues: list[str] = []
        # Build expected reciprocal map
        expected = {lang: _normalize(url) for lang, url in siblings.items()}
        x_default_seen: dict[str, str] = {}

        for lang, url in siblings.items():
            tags = tags_per_url[url]
            declared = {t["hreflang"]: _normalize(t["href"]) for t in tags if t["href"]}

            lang_lower = lang.lower()
            base_lang = lang_lower.split("-")[0]
            has_region = "-" in lang_lower

            # Self-reference required by Google. If the user provided a
            # region-tagged language (es-ES), require the EXACT region —
            # es-ES is NOT satisfied by es-MX.
            if has_region:
                if lang_lower not in declared:
                    row_issues.append(
                        f"{url}: missing self-hreflang for exact lang+region={lang!r} "
                        f"(generic {base_lang!r} is not enough — Google treats es-ES and es-MX as distinct clusters)"
                    )
            else:
                # No region requested: accept exact base or any region variant
                if lang_lower not in declared and not any(
                    d.startswith(base_lang + "-") for d in declared
                ):
                    row_issues.append(f"{url}: missing self-hreflang for lang={lang!r}")

            # Each sibling must appear in this URL's tags. Region-aware:
            # exact match required when sibling specifies a region.
            for sib_lang, sib_url in siblings.items():
                if sib_lang == lang:
                    continue
                sib_lower = sib_lang.lower()
                sib_has_region = "-" in sib_lower
                sib_base = sib_lower.split("-")[0]

                found = None
                if sib_has_region:
                    # EXACT match only — es-MX must not match es-ES
                    if sib_lower in declared:
                        found = declared[sib_lower]
                else:
                    # Generic sibling: accept any region variant of that base
                    if sib_lower in declared:
                        found = declared[sib_lower]
                    else:
                        for k, v in declared.items():
                            if k.split("-")[0] == sib_base:
                                found = v
                                break

                if found is None:
                    row_issues.append(
                        f"{url}: missing hreflang for sibling lang={sib_lang!r} (expected {sib_url!r})"
                    )
                elif found != _normalize(sib_url):
                    row_issues.append(
                        f"{url}: hreflang for {sib_lang!r} points to {found!r}, "
                        f"expected {_normalize(sib_url)!r}"
                    )

            # x-default tracking
            xd = declared.get("x-default")
            if xd:
                x_default_seen[url] = xd

        # Exactly one x-default (or zero) is fine; multiple distinct ones is a bug
        unique_xd = set(x_default_seen.values())
        if len(unique_xd) > 1:
            row_issues.append(
                f"row {i}: inconsistent x-default across siblings: {sorted(unique_xd)}"
            )

        if row_issues:
            issues.append({"row": i, "siblings": siblings, "problems": row_issues})
        else:
            pairs_ok.append({"row": i, "siblings": siblings})

    return {
        "ok": not issues,
        "languages": langs,
        "cluster_size": n,
        "rows_ok": len(pairs_ok),
        "rows_with_issues": len(issues),
        "pairs_ok": pairs_ok,
        "issues": issues,
    }
