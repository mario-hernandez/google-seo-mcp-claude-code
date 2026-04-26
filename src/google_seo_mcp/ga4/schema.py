"""Schema cache & search — adapted from surendranb's schema discovery.

Caches GA4 dimension/metric metadata at first use and exposes TF-IDF-style
keyword search to avoid dumping the full ~10k-token catalog into the LLM.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from ..auth import get_data_client, normalize_property

log = logging.getLogger(__name__)

_schema_by_property: dict[str, dict] = {}


def _fetch_metadata(property_id: int | str) -> dict:
    pid = normalize_property(property_id)
    name = f"{pid}/metadata"
    md = get_data_client().get_metadata(name=name)

    dims = []
    for d in md.dimensions:
        dims.append({
            "api_name": d.api_name,
            "ui_name": d.ui_name,
            "description": d.description,
            "category": d.category,
            "custom_definition": d.custom_definition,
        })
    metrics = []
    for m in md.metrics:
        metrics.append({
            "api_name": m.api_name,
            "ui_name": m.ui_name,
            "description": m.description,
            "category": m.category,
            "type": m.type_.name if m.type_ is not None else "TYPE_UNSPECIFIED",
            "custom_definition": m.custom_definition,
        })
    return {"dimensions": dims, "metrics": metrics}


def get_schema(property_id: int | str) -> dict:
    """Returns the cached schema for a property, fetching once."""
    pid = normalize_property(property_id)
    if pid not in _schema_by_property:
        log.info("Fetching GA4 metadata for %s (cached afterwards)", pid)
        _schema_by_property[pid] = _fetch_metadata(pid)
    return _schema_by_property[pid]


def invalidate_schema(property_id: int | str | None = None) -> None:
    if property_id is None:
        _schema_by_property.clear()
    else:
        _schema_by_property.pop(normalize_property(property_id), None)


def _score(item: dict, terms: list[str]) -> int:
    """Field-weighted scoring: api_name=10, ui_name=5, description=2, category=1."""
    s = 0
    name = (item.get("api_name") or "").lower()
    ui = (item.get("ui_name") or "").lower()
    desc = (item.get("description") or "").lower()
    cat = (item.get("category") or "").lower()
    for t in terms:
        if t in name:
            s += 10
        if t in ui:
            s += 5
        if t in desc:
            s += 2
        if t in cat:
            s += 1
    return s


def search_schema(property_id: int | str, keyword: str, top_n: int = 10) -> dict:
    """Returns top-N dimensions and metrics matching the keyword by weighted score."""
    schema = get_schema(property_id)
    terms = [t for t in re.split(r"\W+", keyword.lower()) if t]
    if not terms:
        return {"dimensions": [], "metrics": []}
    dims = sorted(
        ((it, _score(it, terms)) for it in schema["dimensions"]),
        key=lambda x: x[1],
        reverse=True,
    )
    mets = sorted(
        ((it, _score(it, terms)) for it in schema["metrics"]),
        key=lambda x: x[1],
        reverse=True,
    )
    return {
        "dimensions": [{**it, "_score": s} for it, s in dims[:top_n] if s > 0],
        "metrics": [{**it, "_score": s} for it, s in mets[:top_n] if s > 0],
    }


def categories(property_id: int | str) -> dict:
    """Returns dimension/metric categories with counts (cheap discovery)."""
    schema = get_schema(property_id)
    dim_cats: dict[str, int] = {}
    for d in schema["dimensions"]:
        c = d.get("category") or "Other"
        dim_cats[c] = dim_cats.get(c, 0) + 1
    met_cats: dict[str, int] = {}
    for m in schema["metrics"]:
        c = m.get("category") or "Other"
        met_cats[c] = met_cats.get(c, 0) + 1
    return {"dimension_categories": dim_cats, "metric_categories": met_cats}
