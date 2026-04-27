"""Chrome UX Report API — real user data, not lab.

Free quota: 150 QPS. Optional API key via env `CRUX_API_KEY` (or PSI key works,
they share the Google Cloud project model). Use this when Lighthouse says the
site is fast but real users complain — CrUX is the source of truth Google
actually uses for ranking signals.

https://developer.chrome.com/docs/crux/api
"""
from __future__ import annotations

import os
from typing import Any

import httpx

CRUX_RECORD_ENDPOINT = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"
CRUX_HISTORY_ENDPOINT = (
    "https://chromeuxreport.googleapis.com/v1/records:queryHistoryRecord"
)


def _api_key() -> str | None:
    return os.getenv("CRUX_API_KEY") or os.getenv("PAGESPEED_API_KEY")


def _post_crux(endpoint: str, body: dict, timeout: float = 30.0) -> dict[str, Any]:
    key = _api_key()
    if not key:
        raise RuntimeError(
            "CrUX API requires an API key. Set CRUX_API_KEY (or PAGESPEED_API_KEY) "
            "to a Google Cloud API key with 'Chrome UX Report API' enabled. "
            "Free tier: 150 QPS. https://console.cloud.google.com/apis/library/chromeuxreport.googleapis.com"
        )
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{endpoint}?key={key}", json=body)
    except httpx.HTTPError as e:
        raise RuntimeError(f"CrUX request failed: {type(e).__name__}: {e}") from None
    if resp.status_code == 404:
        # CrUX returns 404 when the URL/origin isn't in the public dataset
        # (insufficient real-user traffic). Treat this as "no data".
        return {"_no_data": True}
    if resp.status_code >= 400:
        raise RuntimeError(f"CrUX API returned {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def query_record(
    url: str | None = None,
    origin: str | None = None,
    *,
    form_factor: str = "PHONE",
    metrics: list[str] | None = None,
) -> dict[str, Any]:
    """Query the latest 28-day rolling CrUX record for a URL or origin."""
    if not (url or origin):
        raise ValueError("Either url or origin must be provided")
    body: dict[str, Any] = {"formFactor": form_factor.upper()}
    if url:
        body["url"] = url
    else:
        body["origin"] = origin
    if metrics:
        body["metrics"] = metrics
    return _post_crux(CRUX_RECORD_ENDPOINT, body)


def query_history(
    url: str | None = None,
    origin: str | None = None,
    *,
    form_factor: str = "PHONE",
    metrics: list[str] | None = None,
    collection_period_count: int = 25,
) -> dict[str, Any]:
    """Historical CrUX data — up to 25 weekly snapshots (~6 months).

    Use this to correlate traffic drops with CWV degradation: if `gsc_traffic_drops`
    flags a page on date X, check if LCP/INP went red in the same week here.
    """
    if not (url or origin):
        raise ValueError("Either url or origin must be provided")
    body: dict[str, Any] = {
        "formFactor": form_factor.upper(),
        "collectionPeriodCount": min(collection_period_count, 25),
    }
    if url:
        body["url"] = url
    else:
        body["origin"] = origin
    if metrics:
        body["metrics"] = metrics
    return _post_crux(CRUX_HISTORY_ENDPOINT, body)
