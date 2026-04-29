"""Unified authentication for Google Search Console + Google Analytics 4.

Single entry point that requests BOTH scopes (`webmasters.readonly` +
`analytics.readonly`) and builds clients for:
  - Webmasters API v3 (GSC search analytics, sitemaps, sites)
  - Search Console API v1 (URL Inspection)
  - GA4 Admin API v1beta (account/property listing)
  - GA4 Data API v1beta (run_report, run_realtime_report)

Resolution order:
  1. ADC — `GOOGLE_APPLICATION_CREDENTIALS` env or default `gcloud` ADC file.
  2. Service account — `GOOGLE_SEO_SERVICE_ACCOUNT_FILE`.
  3. OAuth user flow — `GOOGLE_SEO_OAUTH_CLIENT_FILE` (Desktop client JSON).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from google.analytics.admin_v1beta import AnalyticsAdminServiceClient
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.auth import default as google_auth_default
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as SACredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from platformdirs import user_config_dir

log = logging.getLogger(__name__)

# Singleton client cache is mutated lazily across tool calls. FastMCP runs
# tool handlers concurrently in worker threads; without this lock two
# parallel calls can both pass the ``is None`` check and run a fresh OAuth
# flow simultaneously (two browser tabs, racy ``token.json`` writes).
_auth_lock = threading.Lock()

# Read scopes only — destructive ops are gated by env flag, requested only when set.
SCOPES_READ = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]
SCOPES_WRITE = [
    "https://www.googleapis.com/auth/webmasters",
    "https://www.googleapis.com/auth/analytics.readonly",
]

_searchconsole_service: Any = None
_webmasters_service: Any = None
_ga4_data_client: Any = None
_ga4_admin_client: Any = None

# Identity fingerprint of the credentials currently held in the singletons.
# Recomputed on every getter: when the operator runs ``gcloud auth
# application-default login`` with a different account (or rotates
# GOOGLE_APPLICATION_CREDENTIALS / GOOGLE_SEO_SERVICE_ACCOUNT_FILE), the
# fingerprint changes and we transparently rebuild the clients — without
# this, all tools silently keep returning data from the previous account.
_credentials_fingerprint: str | None = None


def _current_credentials_fingerprint() -> str:
    """Hash of the ENV vars + file mtimes that determine which identity wins.

    Cheap to recompute (a couple of stat() calls). Rebuilt on every getter
    call; if it differs from the cached fingerprint, the singletons are
    discarded and built afresh — preventing silent multi-tenant bleed when
    the operator swaps accounts mid-session.
    """
    parts: list[str] = [
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        os.getenv("GOOGLE_SEO_SERVICE_ACCOUNT_FILE", ""),
        os.getenv("GOOGLE_SEO_OAUTH_CLIENT_FILE", ""),
        os.getenv("GOOGLE_PROJECT_ID", ""),
        os.getenv("GSC_ALLOW_DESTRUCTIVE", ""),
    ]
    for path_var in (
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
        os.getenv("GOOGLE_SEO_SERVICE_ACCOUNT_FILE"),
    ):
        if path_var:
            try:
                parts.append(str(Path(path_var).stat().st_mtime_ns))
            except OSError:
                parts.append("missing")
    token_path = _config_dir() / "token.json"
    try:
        parts.append(str(token_path.stat().st_mtime_ns))
    except OSError:
        parts.append("no-token")
    return "|".join(parts)


def _check_fingerprint_or_invalidate() -> None:
    """Rebuild singletons if the underlying credentials sources changed."""
    global _credentials_fingerprint
    fp = _current_credentials_fingerprint()
    if _credentials_fingerprint is None:
        _credentials_fingerprint = fp
        return
    if fp != _credentials_fingerprint:
        log.info(
            "Credentials fingerprint changed (account rotation detected). "
            "Discarding cached clients."
        )
        global _searchconsole_service, _webmasters_service, _ga4_data_client, _ga4_admin_client
        _searchconsole_service = None
        _webmasters_service = None
        _ga4_data_client = None
        _ga4_admin_client = None
        _credentials_fingerprint = fp


def _config_dir() -> Path:
    p = Path(user_config_dir("google-seo-mcp"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _scopes() -> list[str]:
    return SCOPES_WRITE if os.getenv("GSC_ALLOW_DESTRUCTIVE") == "true" else SCOPES_READ


def _from_adc() -> Any | None:
    try:
        creds, project = google_auth_default(scopes=_scopes())
        log.info("Using ADC credentials (project=%s)", project)
        return creds
    except Exception as e:
        log.debug("ADC unavailable: %s", e)
        return None


def _from_service_account() -> Any | None:
    sa_path = os.getenv("GOOGLE_SEO_SERVICE_ACCOUNT_FILE")
    if not sa_path or not Path(sa_path).exists():
        return None
    log.info("Using service account at %s", sa_path)
    return SACredentials.from_service_account_file(sa_path, scopes=_scopes())


def _from_oauth_flow() -> Any | None:
    client_file = os.getenv("GOOGLE_SEO_OAUTH_CLIENT_FILE")
    if not client_file or not Path(client_file).exists():
        return None

    token_path = _config_dir() / "token.json"
    needed_scopes = _scopes()
    creds: Credentials | None = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_info(
                json.loads(token_path.read_text()), needed_scopes
            )
        except Exception as e:
            log.warning("Could not load cached token, re-authenticating: %s", e)
            creds = None

    # Detect scope upgrade — if the cached token doesn't grant all required scopes
    # (e.g. user just enabled GSC_ALLOW_DESTRUCTIVE which expands `webmasters` scope),
    # discard the cached token and force a fresh consent flow.
    if creds is not None:
        granted = set(getattr(creds, "scopes", None) or [])
        if not set(needed_scopes).issubset(granted):
            log.info(
                "Cached token scopes %s missing required %s — forcing re-auth.",
                granted, set(needed_scopes) - granted,
            )
            creds = None

    if creds and not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as e:
                # Refresh token revoked/rotated — fall through to fresh consent
                # flow rather than letting the exception escape to the LLM.
                log.warning("Refresh failed (%s); will run consent flow.", e)
                creds = None
        else:
            creds = None

    if not creds:
        flow = InstalledAppFlow.from_client_secrets_file(client_file, needed_scopes)
        creds = flow.run_local_server(port=0, open_browser=True)
        # Atomic write — protects against half-written ``token.json`` when two
        # processes / SIGINT race during write.
        _atomic_write_text(token_path, creds.to_json())
        try:
            token_path.chmod(0o600)
        except OSError:  # noqa: PERF203 — chmod can fail on Windows; best-effort.
            pass

    return creds


def _atomic_write_text(target: Path, text: str) -> None:
    """Write text to ``target`` atomically (POSIX + Windows).

    Uses a same-directory tempfile + ``os.replace`` to ensure either the
    old file or the new is observable, never a partial file.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _build_creds() -> Any:
    creds = _from_adc() or _from_service_account() or _from_oauth_flow()
    if creds is None:
        raise RuntimeError(
            "No Google credentials found. Set up ADC with `gcloud auth application-default "
            "login --scopes=https://www.googleapis.com/auth/webmasters.readonly,"
            "https://www.googleapis.com/auth/analytics.readonly`, or set "
            "GOOGLE_SEO_OAUTH_CLIENT_FILE / GOOGLE_SEO_SERVICE_ACCOUNT_FILE."
        )
    return creds


# ── GSC clients ─────────────────────────────────────────────────────────────

def get_searchconsole():
    """Search Console v1 client (URL Inspection API lives here)."""
    global _searchconsole_service
    if _searchconsole_service is not None:
        return _searchconsole_service
    with _auth_lock:
        _check_fingerprint_or_invalidate()
        if _searchconsole_service is None:
            _searchconsole_service = build(
                "searchconsole", "v1", credentials=_build_creds(), cache_discovery=False
            )
    return _searchconsole_service


def get_webmasters():
    """Webmasters v3 client (Search Analytics, sitemaps, sites)."""
    global _webmasters_service
    if _webmasters_service is not None:
        return _webmasters_service
    with _auth_lock:
        _check_fingerprint_or_invalidate()
        if _webmasters_service is None:
            _webmasters_service = build(
                "webmasters", "v3", credentials=_build_creds(), cache_discovery=False
            )
    return _webmasters_service


# ── GA4 clients ─────────────────────────────────────────────────────────────

def get_data_client() -> BetaAnalyticsDataClient:
    """GA4 Data API v1beta client (runReport, runRealtimeReport, etc.)."""
    global _ga4_data_client
    if _ga4_data_client is not None:
        return _ga4_data_client
    with _auth_lock:
        _check_fingerprint_or_invalidate()
        if _ga4_data_client is None:
            _ga4_data_client = BetaAnalyticsDataClient(credentials=_build_creds())
    return _ga4_data_client


def get_admin_client() -> AnalyticsAdminServiceClient:
    """GA4 Admin API v1beta client (accounts, properties, custom dims)."""
    global _ga4_admin_client
    if _ga4_admin_client is not None:
        return _ga4_admin_client
    with _auth_lock:
        _check_fingerprint_or_invalidate()
        if _ga4_admin_client is None:
            _ga4_admin_client = AnalyticsAdminServiceClient(credentials=_build_creds())
    return _ga4_admin_client


# ── Helpers ─────────────────────────────────────────────────────────────────

def reset_clients(*, drop_oauth_token: bool = True) -> None:
    """Force rebuild on next access — used by `reauthenticate` tool.

    By default also deletes the cached OAuth `token.json` so that a fresh
    consent flow runs on next use. Pass `drop_oauth_token=False` to keep the
    cached token (useful when you only want to re-read ADC credentials after
    a `gcloud auth application-default login`).
    """
    global _searchconsole_service, _webmasters_service, _ga4_data_client, _ga4_admin_client
    with _auth_lock:
        _searchconsole_service = None
        _webmasters_service = None
        _ga4_data_client = None
        _ga4_admin_client = None

    if drop_oauth_token:
        token_path = _config_dir() / "token.json"
        if token_path.exists():
            try:
                token_path.unlink()
                log.info("Cleared cached OAuth token at %s", token_path)
            except OSError as e:
                log.warning("Could not delete cached token at %s: %s", token_path, e)


def normalize_property(property_id: int | str) -> str:
    """Accepts int, '123', 'properties/123' and returns canonical 'properties/123'."""
    s = str(property_id).strip()
    if s.startswith("properties/"):
        return s
    if s.isdigit():
        return f"properties/{s}"
    raise ValueError(f"Invalid property_id {property_id!r} — expected int or 'properties/<id>'")
