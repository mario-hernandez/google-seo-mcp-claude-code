"""llms.txt protocol checker.

The llms.txt convention (https://llmstxt.org) lets a site declare what an
LLM should ingest. Anthropic, Vercel, Cloudflare and most modern docs
sites publish ``/llms.txt`` (index) and ``/llms-full.txt`` (full corpus).
This tool verifies presence, parses the H1/blocks structure, and flags
common authoring mistakes.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import httpx

from ..security import assert_url_is_public

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def _fetch(url: str, timeout: float = 15.0) -> tuple[int, str | None, dict[str, str]]:
    assert_url_is_public(url)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": UA}) as c:
            r = c.get(url)
        h = {k.lower(): v for k, v in r.headers.items()}
        return r.status_code, (r.text if r.status_code < 400 else None), h
    except httpx.HTTPError:
        return 0, None, {}


def llms_txt_check(origin_url: str) -> dict[str, Any]:
    """Verify ``/llms.txt`` and ``/llms-full.txt`` against the spec.

    Args:
        origin_url: scheme + host (e.g. ``https://example.com``).

    Returns presence flags, parsed top-of-document fields (H1 title,
    summary blockquote, sections), and lint warnings.
    """
    if not origin_url.startswith(("http://", "https://")):
        raise ValueError("origin_url must include scheme (https://...)")

    llms_url = urljoin(origin_url + "/", "llms.txt")
    full_url = urljoin(origin_url + "/", "llms-full.txt")

    status, body, headers = _fetch(llms_url)
    full_status, full_body, _ = _fetch(full_url)

    out: dict[str, Any] = {
        "origin": origin_url,
        "llms_txt": {
            "url": llms_url,
            "status": status,
            "present": bool(body),
            "content_type": headers.get("content-type"),
        },
        "llms_full_txt": {
            "url": full_url,
            "status": full_status,
            "present": bool(full_body),
        },
        "issues": [],
        "title": None,
        "summary": None,
        "sections": [],
    }

    if not body:
        out["issues"].append("llms_txt_missing")
        out["health"] = "red"
        return out

    # Parse the spec format: # Title\n> Summary blockquote\n## Section
    lines = body.splitlines()
    title_match = re.match(r"^#\s+(.+)\s*$", lines[0]) if lines else None
    if title_match:
        out["title"] = title_match.group(1).strip()
    else:
        out["issues"].append("missing_h1_title")

    # Summary block: first ``> ...`` paragraph after title
    summary_lines = []
    for ln in lines[1:]:
        if ln.startswith(">"):
            summary_lines.append(ln.lstrip("> ").rstrip())
        elif summary_lines:
            break
    if summary_lines:
        out["summary"] = " ".join(summary_lines).strip()
    else:
        out["issues"].append("missing_summary_blockquote")

    # Sections: ## Heading
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for ln in lines:
        sec = re.match(r"^##\s+(.+)\s*$", ln)
        if sec:
            if current:
                sections.append(current)
            current = {"name": sec.group(1).strip(), "links": []}
            continue
        link = re.match(r"^\s*-\s*\[([^\]]+)\]\(([^)]+)\)(?:\s*:\s*(.*))?", ln)
        if link and current is not None:
            current["links"].append({
                "title": link.group(1).strip(),
                "url": link.group(2).strip(),
                "description": (link.group(3) or "").strip() or None,
            })
    if current:
        sections.append(current)
    out["sections"] = sections
    out["section_count"] = len(sections)
    out["link_count"] = sum(len(s.get("links", [])) for s in sections)

    # Health verdict
    if not out["issues"]:
        out["health"] = "green"
    elif "llms_txt_missing" in out["issues"]:
        out["health"] = "red"
    else:
        out["health"] = "amber"

    return out
