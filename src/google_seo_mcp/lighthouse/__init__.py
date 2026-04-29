"""Lighthouse / PageSpeed Insights v5 — wraps the public PSI API.

Free quota: 25,000 queries/day. Optional API key for higher limits via env
`PAGESPEED_API_KEY`. Without the key the API still works but rate-limits
faster. See https://developers.google.com/speed/docs/insights/v5/get-started
"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

import httpx

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def _build_url(
    url: str,
    *,
    strategy: str = "mobile",
    categories: list[str] | None = None,
    locale: str = "en",
) -> str:
    params: list[tuple[str, str]] = [
        ("url", url),
        ("strategy", strategy.upper()),
        ("locale", locale),
    ]
    for c in categories or ["performance", "accessibility", "best-practices", "seo"]:
        params.append(("category", c.upper()))
    api_key = os.getenv("PAGESPEED_API_KEY")
    if api_key:
        params.append(("key", api_key))
    return f"{PSI_ENDPOINT}?{urlencode(params)}"


def call_psi(
    url: str,
    *,
    strategy: str = "mobile",
    categories: list[str] | None = None,
    timeout: float = 90.0,
) -> dict[str, Any]:
    """Fire the PSI API and return parsed JSON. Raises RuntimeError on HTTP errors."""
    full_url = _build_url(url, strategy=strategy, categories=categories)
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(full_url)
    except httpx.HTTPError as e:
        raise RuntimeError(f"PSI request failed: {type(e).__name__}: {e}") from None
    if resp.status_code >= 400:
        raise RuntimeError(f"PSI API returned {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def extract_field_data(psi: dict[str, Any]) -> dict[str, Any]:
    """Extract CrUX field data embedded in the PSI response.

    PSI v5 includes ``loadingExperience`` (URL-level) and
    ``originLoadingExperience`` (origin-level) — both are real-user p75
    data. They cost nothing extra (already in the same response) and
    convert a lab-only audit into a lab+field one.
    """
    out: dict[str, Any] = {"url_field": None, "origin_field": None}
    le = psi.get("loadingExperience") or {}
    if le.get("metrics"):
        out["url_field"] = {
            "id": le.get("id"),
            "overall_category": le.get("overall_category"),
            "metrics": {
                k: {
                    "percentile": v.get("percentile"),
                    "category": v.get("category"),
                }
                for k, v in (le.get("metrics") or {}).items()
            },
        }
    ole = psi.get("originLoadingExperience") or {}
    if ole.get("metrics"):
        out["origin_field"] = {
            "id": ole.get("id"),
            "overall_category": ole.get("overall_category"),
            "metrics": {
                k: {
                    "percentile": v.get("percentile"),
                    "category": v.get("category"),
                }
                for k, v in (ole.get("metrics") or {}).items()
            },
        }
    return out
