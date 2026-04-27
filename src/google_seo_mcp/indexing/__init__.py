"""IndexNow + Google Indexing API helpers.

IndexNow (Bing/Yandex/Seznam, ignored by Google) is a single HTTP POST.
Google Indexing API requires OAuth and is officially limited to JobPosting
and BroadcastEvent — but works for general URLs in practice (ToS-grey).
"""
from __future__ import annotations

import os
import secrets
from typing import Any

import httpx

INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
GOOGLE_INDEXING_ENDPOINT = (
    "https://indexing.googleapis.com/v3/urlNotifications:publish"
)


def generate_indexnow_key() -> str:
    """Generate a 32-char hex key suitable for IndexNow ownership verification.

    The user must host this key as <site>/<key>.txt with the key as content.
    """
    return secrets.token_hex(16)


def submit_indexnow(
    urls: list[str],
    *,
    host: str,
    key: str,
    key_location: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Submit one or more URLs to IndexNow.

    Args:
        urls: Full URLs (must all share the host).
        host: Bare host (e.g. "www.example.com").
        key: The IndexNow key hosted at https://{host}/{key}.txt.
        key_location: Optional explicit key URL if it lives at a non-default path.
    """
    if not urls:
        raise ValueError("urls must be non-empty")
    body: dict[str, Any] = {"host": host, "key": key, "urlList": urls}
    if key_location:
        body["keyLocation"] = key_location
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                INDEXNOW_ENDPOINT,
                json=body,
                headers={"Content-Type": "application/json"},
            )
    except httpx.HTTPError as e:
        raise RuntimeError(f"IndexNow request failed: {type(e).__name__}: {e}") from None
    return {
        "status_code": resp.status_code,
        "ok": resp.status_code in (200, 202),
        "submitted_count": len(urls),
        "host": host,
        "response_text": resp.text[:300] if resp.text else "",
    }


def submit_google_indexing(
    url: str,
    notification_type: str = "URL_UPDATED",
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Notify Google Indexing API that a URL was updated or deleted.

    Args:
        notification_type: URL_UPDATED | URL_DELETED.
    """
    # Lazy import to avoid forcing google-auth load unless this is used.
    from ..auth import _build_creds  # type: ignore

    if notification_type not in {"URL_UPDATED", "URL_DELETED"}:
        raise ValueError("notification_type must be URL_UPDATED or URL_DELETED")

    if os.getenv("GSC_ALLOW_DESTRUCTIVE") != "true":
        # Indexing API doesn't strictly modify the index destructively but it
        # adds your URL to Google's queue. We gate it like other write ops.
        raise RuntimeError(
            "Google Indexing API requires GSC_ALLOW_DESTRUCTIVE=true. "
            "It also requires the OAuth scope `indexing` which is NOT included "
            "in the default read-only scope set. You must re-auth with "
            "https://www.googleapis.com/auth/indexing added."
        )

    creds = _build_creds()
    # Refresh if needed
    if hasattr(creds, "refresh") and getattr(creds, "expired", False):
        from google.auth.transport.requests import Request as _Req

        creds.refresh(_Req())

    token = getattr(creds, "token", None)
    if not token:
        raise RuntimeError("Could not obtain access token from credentials")

    body = {"url": url, "type": notification_type}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                GOOGLE_INDEXING_ENDPOINT,
                json=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.HTTPError as e:
        raise RuntimeError(f"Indexing API request failed: {e}") from None
    return {
        "status_code": resp.status_code,
        "ok": resp.status_code == 200,
        "url": url,
        "notification_type": notification_type,
        "response": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text[:300],
    }
