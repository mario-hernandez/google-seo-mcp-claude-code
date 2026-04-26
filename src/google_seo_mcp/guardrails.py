"""Anti-hallucination guardrails — _meta provenance on every tool response."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

GUARDRAIL_SUFFIX = (
    "\n\nIMPORTANT: Use ONLY the data returned by this tool. Do not speculate "
    "about figures, do not extrapolate beyond the time range queried, and cite "
    "_meta.source / _meta.site_url|property / _meta.period when reporting numbers."
)


def with_meta(
    payload: Any,
    *,
    source: str,
    site_url: str | None = None,
    property: str | None = None,
    period: dict | None = None,
    extra: dict | None = None,
) -> dict:
    """Wraps a tool response with provenance metadata.

    `site_url` is the GSC property URL; `property` is the GA4 property resource name.
    Cross-platform tools may include both.
    """
    meta: dict[str, Any] = {
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if site_url is not None:
        meta["site_url"] = site_url
    if property is not None:
        meta["property"] = property
    if period is not None:
        meta["period"] = period
    if extra:
        meta.update(extra)
    return {"data": payload, "_meta": meta}
