"""GA4 Data API v1beta helpers — query construction, pagination, anti-blowup.

The row-count probe pattern is borrowed from surendranb/google-analytics-mcp:
GA4 returns `row_count` even when `limit=1`, so we can estimate result size for
~free before committing to a full fetch — preventing context-window blowup.
"""
from __future__ import annotations

import logging
from typing import Any

from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    DimensionExpression,
    Filter,
    FilterExpression,
    FilterExpressionList,
    Metric,
    MetricAggregation,
    NumericValue,
    OrderBy,
    RunReportRequest,
)
from google.api_core.exceptions import GoogleAPIError

from ..auth import get_data_client, normalize_property

log = logging.getLogger(__name__)

# Server-side cap. GA4 hard-limits at 250k but practical LLM context dies long before.
MAX_ROWS = 2500


def _build_dimensions(dims: list[str] | None) -> list[Dimension]:
    return [Dimension(name=d) for d in (dims or [])]


def _build_metrics(metrics: list[str]) -> list[Metric]:
    return [Metric(name=m) for m in metrics]


def _build_filter(spec: dict | None) -> FilterExpression | None:
    """Builds a FilterExpression from a JSON-friendly spec.

    Supported shapes:
      {"field": "country", "string_value": "ES"}
      {"field": "sessions", "numeric_value": 100, "op": "GREATER_THAN"}
      {"and": [<spec>, <spec>]}
      {"or": [<spec>, <spec>]}
      {"not": <spec>}
    """
    if not spec:
        return None
    if "and" in spec:
        return FilterExpression(
            and_group=FilterExpressionList(expressions=[_build_filter(s) for s in spec["and"]])
        )
    if "or" in spec:
        return FilterExpression(
            or_group=FilterExpressionList(expressions=[_build_filter(s) for s in spec["or"]])
        )
    if "not" in spec:
        return FilterExpression(not_expression=_build_filter(spec["not"]))
    if "field" in spec:
        if "string_value" in spec:
            f = Filter(
                field_name=spec["field"],
                string_filter=Filter.StringFilter(
                    value=spec["string_value"],
                    match_type=getattr(
                        Filter.StringFilter.MatchType,
                        spec.get("match", "EXACT"),
                        Filter.StringFilter.MatchType.EXACT,
                    ),
                    case_sensitive=spec.get("case_sensitive", False),
                ),
            )
        elif "numeric_value" in spec:
            v = spec["numeric_value"]
            numeric_value = (
                NumericValue(int64_value=int(v))
                if isinstance(v, int)
                else NumericValue(double_value=float(v))
            )
            f = Filter(
                field_name=spec["field"],
                numeric_filter=Filter.NumericFilter(
                    operation=getattr(
                        Filter.NumericFilter.Operation,
                        spec.get("op", "GREATER_THAN"),
                        Filter.NumericFilter.Operation.GREATER_THAN,
                    ),
                    value=numeric_value,
                ),
            )
        else:
            raise ValueError(f"Unsupported filter spec: {spec}")
        return FilterExpression(filter=f)
    raise ValueError(f"Unsupported filter spec: {spec}")


def _build_order_bys(order: list[dict] | None) -> list[OrderBy]:
    out: list[OrderBy] = []
    for o in order or []:
        desc = o.get("desc", True)
        if "metric" in o:
            out.append(OrderBy(desc=desc, metric=OrderBy.MetricOrderBy(metric_name=o["metric"])))
        elif "dimension" in o:
            out.append(
                OrderBy(desc=desc, dimension=OrderBy.DimensionOrderBy(dimension_name=o["dimension"]))
            )
    return out


def run_report(
    property_id: int | str,
    *,
    start_date: str,
    end_date: str,
    metrics: list[str],
    dimensions: list[str] | None = None,
    dimension_filter: dict | None = None,
    metric_filter: dict | None = None,
    order_bys: list[dict] | None = None,
    limit: int = 1000,
    offset: int = 0,
    aggregations: list[str] | None = None,
    return_property_quota: bool = False,
) -> dict:
    """Run a GA4 `runReport` and return rows as a list of dicts plus optional totals.

    Aggregations: list of `["TOTAL", "MAXIMUM", "MINIMUM"]`. If `dimensions` excludes
    `date` and aggregations is empty, we add `TOTAL` automatically (server-side sum).
    """
    if aggregations is None and dimensions and "date" not in dimensions:
        aggregations = ["TOTAL"]
    metric_aggregations = [
        getattr(MetricAggregation, a, MetricAggregation.TOTAL) for a in (aggregations or [])
    ]

    req = RunReportRequest(
        property=normalize_property(property_id),
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=_build_dimensions(dimensions),
        metrics=_build_metrics(metrics),
        dimension_filter=_build_filter(dimension_filter),
        metric_filter=_build_filter(metric_filter),
        order_bys=_build_order_bys(order_bys),
        limit=min(limit, MAX_ROWS),
        offset=offset,
        metric_aggregations=metric_aggregations,
        return_property_quota=return_property_quota,
    )
    try:
        resp = get_data_client().run_report(req)
    except GoogleAPIError as e:
        raise _humanize_error(e, property_id) from None

    return _serialize_response(resp)


def estimate_row_count(
    property_id: int | str,
    *,
    start_date: str,
    end_date: str,
    metrics: list[str],
    dimensions: list[str] | None = None,
    dimension_filter: dict | None = None,
    metric_filter: dict | None = None,
) -> int:
    """Anti-context-blowup probe: fires a `limit=1` query and returns the total row_count.

    GA4 returns the total number of rows even when `limit=1` — so a single tiny
    request gives you the full size before committing to fetching everything.
    """
    req = RunReportRequest(
        property=normalize_property(property_id),
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=_build_dimensions(dimensions),
        metrics=_build_metrics(metrics),
        dimension_filter=_build_filter(dimension_filter),
        metric_filter=_build_filter(metric_filter),
        limit=1,
    )
    try:
        resp = get_data_client().run_report(req)
    except GoogleAPIError as e:
        raise _humanize_error(e, property_id) from None
    return int(resp.row_count or 0)


def _serialize_response(resp: Any) -> dict:
    dims = [d.name for d in resp.dimension_headers]
    mets = [m.name for m in resp.metric_headers]
    rows: list[dict] = []
    for r in resp.rows:
        row: dict[str, Any] = {}
        for i, dv in enumerate(r.dimension_values):
            row[dims[i]] = dv.value
        for i, mv in enumerate(r.metric_values):
            row[mets[i]] = _coerce_metric(mv.value)
        rows.append(row)
    out: dict[str, Any] = {
        "rows": rows,
        "row_count": int(resp.row_count or 0),
        "dimension_headers": dims,
        "metric_headers": mets,
    }
    if resp.totals:
        out["totals"] = [_serialize_totals(t, mets) for t in resp.totals]
    return out


def _serialize_totals(t: Any, mets: list[str]) -> dict:
    return {mets[i]: _coerce_metric(mv.value) for i, mv in enumerate(t.metric_values)}


def _coerce_metric(v: str) -> float | int | str:
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (ValueError, TypeError):
        return v


def _humanize_error(err: Exception, property_id: int | str) -> RuntimeError:
    msg = str(err)
    if "403" in msg or "PermissionDenied" in msg:
        return RuntimeError(
            f"Forbidden on property {property_id!r}. Verify the auth account has "
            "Viewer access in GA4 Admin → Property → Property Access Management."
        )
    if "404" in msg or "NotFound" in msg:
        return RuntimeError(
            f"Property {property_id!r} not found. Use `list_properties` to enumerate."
        )
    if "429" in msg or "ResourceExhausted" in msg:
        return RuntimeError(
            "GA4 API quota exceeded. Wait a minute and retry; consider narrowing "
            "the date range or `limit`. Tokens-per-property are limited."
        )
    if "400" in msg or "InvalidArgument" in msg:
        return RuntimeError(
            f"Bad request to GA4 ({msg[:200]}). Check dimension/metric names with "
            "`search_schema` and date format (YYYY-MM-DD)."
        )
    return RuntimeError(f"GA4 API error: {msg[:300]}")
