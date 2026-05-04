"""SERP intelligence — direct queries to Google SERPs via DataForSEO.

DataForSEO is the cheapest pay-as-you-go SERP API in 2026:
  - Live SERP (organic + AI Overview + PAA + featured snippet): ~$0.0006/call
  - Bulk: $0.0009/call advanced
  - 30 queries × 12 months = ~$0.20/year per client

Set ``DATAFORSEO_LOGIN`` and ``DATAFORSEO_PASSWORD`` env vars to enable.
Without them, every tool returns ``{"error": "credentials_missing", "fix": ...}``
so the agent fails gracefully and explains how to enable.

API docs: https://docs.dataforseo.com/v3/serp/google/organic/live/advanced/
"""
from __future__ import annotations

import base64
import os
from typing import Any

import httpx

from ..security import assert_url_is_public

DATAFORSEO_BASE = "https://api.dataforseo.com/v3"


class SerpCredentialsMissing(RuntimeError):
    """Raised when DATAFORSEO_LOGIN/PASSWORD are not configured."""


def _auth_header() -> dict[str, str]:
    login = os.getenv("DATAFORSEO_LOGIN")
    password = os.getenv("DATAFORSEO_PASSWORD")
    if not login or not password:
        raise SerpCredentialsMissing(
            "DataForSEO credentials missing. Set DATAFORSEO_LOGIN and "
            "DATAFORSEO_PASSWORD env vars (sign up free at "
            "https://dataforseo.com/register — pay-as-you-go, ~$0.0006/SERP)."
        )
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def call_dataforseo(endpoint: str, payload: list[dict[str, Any]], timeout: float = 60.0) -> dict[str, Any]:
    """POST a payload to DataForSEO. Returns the parsed JSON response."""
    url = f"{DATAFORSEO_BASE}{endpoint}"
    assert_url_is_public(url)
    headers = _auth_header()
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        raise RuntimeError(f"DataForSEO request failed: {type(e).__name__}: {e}") from None
    if r.status_code >= 400:
        raise RuntimeError(f"DataForSEO returned {r.status_code}: {r.text[:300]}")
    return r.json()
