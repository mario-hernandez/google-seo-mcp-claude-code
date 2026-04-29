"""Search Analytics helpers — pagination, error handling, CTR benchmarks."""
from __future__ import annotations

import logging
import os
from typing import Any

from googleapiclient.errors import HttpError

log = logging.getLogger(__name__)

# Default expected-CTR-by-position table. Conservative values that work as a
# rough upper bound for "expected CTR if you were doing well at this position".
# Override with env GSC_CTR_BENCHMARKS (comma-separated 10 floats).
DEFAULT_CTR_BENCHMARKS = [0.285, 0.157, 0.110, 0.080, 0.060, 0.045, 0.034, 0.026, 0.020, 0.016]


def ctr_benchmarks() -> list[float]:
    raw = os.getenv("GSC_CTR_BENCHMARKS")
    if not raw:
        return DEFAULT_CTR_BENCHMARKS
    try:
        parsed = [float(x.strip()) for x in raw.split(",")][:10]
    except ValueError:
        log.warning("Bad GSC_CTR_BENCHMARKS, using defaults")
        return DEFAULT_CTR_BENCHMARKS
    # Pad with the defaults if the user provided fewer than 10 values, so
    # downstream code can always index positions 1-10 without IndexError.
    if len(parsed) < len(DEFAULT_CTR_BENCHMARKS):
        parsed.extend(DEFAULT_CTR_BENCHMARKS[len(parsed):])
    return parsed


def expected_ctr(position: float) -> float:
    """Returns the expected CTR for a given average position (rounded down)."""
    benchmarks = ctr_benchmarks()
    idx = int(position) - 1
    if idx < 0:
        return benchmarks[0]
    if idx >= len(benchmarks):
        return benchmarks[-1]
    return benchmarks[idx]


def query_search_analytics(
    webmasters,
    site_url: str,
    start_date: str,
    end_date: str,
    *,
    dimensions: list[str] | None = None,
    dimension_filter_groups: list[dict] | None = None,
    row_limit: int = 25000,
    data_state: str = "all",
    search_type: str = "web",
    fetch_all: bool = False,
) -> list[dict]:
    """Run a `searchanalytics().query()` call and return a list of rows.

    `data_state="all"` matches the GSC dashboard (includes fresh data); use
    `"final"` to match historical reports.
    """
    body: dict[str, Any] = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions or [],
        "type": search_type,
        "dataState": data_state,
        "rowLimit": min(row_limit, 25000),
    }
    if dimension_filter_groups:
        body["dimensionFilterGroups"] = dimension_filter_groups

    rows: list[dict] = []
    start_row = 0
    while True:
        body["startRow"] = start_row
        try:
            resp = webmasters.searchanalytics().query(siteUrl=site_url, body=body).execute()
        except HttpError as e:
            raise _humanize_error(e, site_url) from None
        page = resp.get("rows", [])
        rows.extend(page)
        if not fetch_all or len(page) < body["rowLimit"]:
            break
        start_row += body["rowLimit"]
        if start_row >= 250_000:
            log.warning("Hit 250k row safety cap on %s", site_url)
            break

    return rows


def _humanize_error(err: HttpError, site_url: str) -> RuntimeError:
    """Convert googleapi HttpError to a user-friendly RuntimeError."""
    status = err.resp.status if err.resp else 0
    detail = err.error_details if hasattr(err, "error_details") else None
    msg_map = {
        400: "Bad request to Search Console. Check date format (YYYY-MM-DD) and dimensions.",
        401: "Unauthenticated. Run `gcloud auth application-default login` with the "
             "webmasters.readonly scope, or check GOOGLE_SEO_OAUTH_CLIENT_FILE.",
        403: f"Forbidden. The authenticated user does not have access to {site_url!r}. "
             "Verify the property in Search Console and grant access to the auth account.",
        404: f"Site {site_url!r} not found. List your sites with `list_sites`. "
             "Domain properties use the form `sc-domain:example.com`.",
        429: "Search Console quota exceeded. Wait a minute and retry; consider narrowing "
             "the date range or row limit.",
        500: "Google Search Console API internal error. Retry in a few seconds.",
        503: "Google Search Console API unavailable. Retry shortly.",
    }
    base = msg_map.get(status, f"Search Console API error (HTTP {status}).")
    if detail:
        base += f" Detail: {detail!r}"
    return RuntimeError(base)


def aggregate_totals(rows: list[dict]) -> dict[str, float]:
    """Sums clicks/impressions and computes CTR, position weighted by impressions."""
    clicks = sum(r.get("clicks", 0) for r in rows)
    impressions = sum(r.get("impressions", 0) for r in rows)
    weighted_pos = sum(
        r.get("position", 0) * r.get("impressions", 0) for r in rows
    )
    return {
        "clicks": clicks,
        "impressions": impressions,
        "ctr": (clicks / impressions) if impressions else 0.0,
        "position": (weighted_pos / impressions) if impressions else 0.0,
    }
