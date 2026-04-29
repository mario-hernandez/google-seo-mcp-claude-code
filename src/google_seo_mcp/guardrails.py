"""Anti-hallucination guardrails — _meta provenance on every tool response."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

GUARDRAIL_SUFFIX = (
    "\n\nIMPORTANT: Use ONLY the data returned by this tool. Do not speculate "
    "about figures, do not extrapolate beyond the time range queried, and cite "
    "_meta.source / _meta.site_url|property / _meta.period when reporting numbers."
)


def _json_safe(value: Any) -> Any:
    """Coerce values that JSON encoders refuse into safe primitives.

    The MCP serialises tool returns as JSON-RPC. Any datetime / Decimal /
    set / Path / numpy scalar / bytes that slips into a tool's payload
    would raise ``TypeError: not JSON serializable`` and break the
    transport. We walk the tree once, defensively, before returning.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (set, frozenset)):
        return [_json_safe(v) for v in sorted(value, key=str)]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    # numpy / pandas scalars expose `.item()` to convert to a native Python
    # type without us depending on numpy as a hard dependency.
    if hasattr(value, "item") and callable(getattr(value, "item")):
        try:
            return _json_safe(value.item())
        except Exception:  # noqa: BLE001
            pass
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    # Last-resort: stringify so the protocol never fails. The agent gets
    # a readable representation rather than a hard error.
    return str(value)


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

    ``site_url`` is the GSC property URL; ``property`` is the GA4 property
    resource name. Cross-platform tools may include both. The payload and
    every nested value are passed through ``_json_safe`` so the JSON-RPC
    transport never fails on datetimes, sets, numpy scalars, etc.
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
        meta["period"] = _json_safe(period)
    if extra:
        meta.update(_json_safe(extra))
    return {"data": _json_safe(payload), "_meta": meta}
