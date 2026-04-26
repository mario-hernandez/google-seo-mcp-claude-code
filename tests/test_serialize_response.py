"""Tests for ga4/data._serialize_response — critical pure function with 0% prior coverage."""
from __future__ import annotations

from types import SimpleNamespace as NS

from google_seo_mcp.ga4.data import _coerce_metric, _serialize_response, _serialize_totals


def _mock_response(dim_headers: list[str], met_headers: list[str], rows: list[dict],
                   totals: list[list[str]] | None = None, row_count: int = 0):
    """Builds a minimal mock that quacks like a GA4 RunReportResponse."""
    return NS(
        dimension_headers=[NS(name=d) for d in dim_headers],
        metric_headers=[NS(name=m) for m in met_headers],
        rows=[
            NS(
                dimension_values=[NS(value=str(r.get(d, ""))) for d in dim_headers],
                metric_values=[NS(value=str(r.get(m, ""))) for m in met_headers],
            )
            for r in rows
        ],
        row_count=row_count or len(rows),
        totals=[
            NS(metric_values=[NS(value=str(v)) for v in row])
            for row in (totals or [])
        ],
    )


def test_serialize_response_basic():
    resp = _mock_response(
        dim_headers=["country"],
        met_headers=["sessions"],
        rows=[{"country": "ES", "sessions": "150"}, {"country": "FR", "sessions": "75"}],
    )
    out = _serialize_response(resp)
    assert out["dimension_headers"] == ["country"]
    assert out["metric_headers"] == ["sessions"]
    assert out["rows"] == [{"country": "ES", "sessions": 150}, {"country": "FR", "sessions": 75}]


def test_serialize_response_empty_rows():
    resp = _mock_response(["query"], ["clicks"], [])
    out = _serialize_response(resp)
    assert out["rows"] == []
    assert out["row_count"] == 0


def test_serialize_response_with_totals():
    resp = _mock_response(
        dim_headers=["channel"],
        met_headers=["sessions", "conversions"],
        rows=[{"channel": "Organic Search", "sessions": "500", "conversions": "20"}],
        totals=[["500", "20"]],
    )
    out = _serialize_response(resp)
    assert "totals" in out
    assert out["totals"][0] == {"sessions": 500, "conversions": 20}


def test_coerce_metric_int():
    assert _coerce_metric("100") == 100
    assert isinstance(_coerce_metric("100"), int)


def test_coerce_metric_float():
    assert _coerce_metric("0.123") == 0.123


def test_coerce_metric_integer_float_becomes_int():
    """Floats that are whole numbers (e.g. "100.0") should be returned as int."""
    out = _coerce_metric("100.0")
    assert out == 100
    assert isinstance(out, int)


def test_coerce_metric_non_numeric_passthrough():
    assert _coerce_metric("not-a-number") == "not-a-number"


def test_serialize_totals_aligns_metric_names():
    """Metric values must be aligned to the metric_headers order."""
    totals_msg = NS(metric_values=[NS(value="1000"), NS(value="3.5")])
    out = _serialize_totals(totals_msg, ["sessions", "engagementRate"])
    assert out == {"sessions": 1000, "engagementRate": 3.5}
