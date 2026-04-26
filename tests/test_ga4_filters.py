"""Tests for GA4 filter builder — guards against the NumericValue bug we just fixed."""
from __future__ import annotations

import pytest
from google.analytics.data_v1beta.types import (
    Filter,
    FilterExpression,
    FilterExpressionList,
    NumericValue,
)

from google_seo_mcp.ga4.data import _build_filter


def test_build_filter_string_eq():
    expr = _build_filter({"field": "country", "string_value": "ES"})
    assert isinstance(expr, FilterExpression)
    assert expr.filter.field_name == "country"
    assert expr.filter.string_filter.value == "ES"
    assert expr.filter.string_filter.match_type == Filter.StringFilter.MatchType.EXACT


def test_build_filter_string_with_match_type():
    expr = _build_filter({"field": "page", "string_value": "/blog/", "match": "BEGINS_WITH"})
    assert expr.filter.string_filter.match_type == Filter.StringFilter.MatchType.BEGINS_WITH


def test_build_filter_numeric_int():
    """Regression: building a numeric filter with int value (was crashing with proto-plus dict)."""
    expr = _build_filter({"field": "sessions", "numeric_value": 100, "op": "GREATER_THAN"})
    assert isinstance(expr, FilterExpression)
    assert expr.filter.field_name == "sessions"
    assert expr.filter.numeric_filter.operation == Filter.NumericFilter.Operation.GREATER_THAN
    # The value must be a NumericValue message, not a dict
    assert isinstance(expr.filter.numeric_filter.value, NumericValue)
    assert expr.filter.numeric_filter.value.int64_value == 100


def test_build_filter_numeric_float():
    expr = _build_filter({"field": "ctr", "numeric_value": 0.05, "op": "LESS_THAN"})
    assert isinstance(expr.filter.numeric_filter.value, NumericValue)
    assert expr.filter.numeric_filter.value.double_value == 0.05


def test_build_filter_and_group():
    expr = _build_filter({
        "and": [
            {"field": "country", "string_value": "ES"},
            {"field": "deviceCategory", "string_value": "mobile"},
        ]
    })
    assert isinstance(expr.and_group, FilterExpressionList)
    assert len(expr.and_group.expressions) == 2


def test_build_filter_or_group():
    expr = _build_filter({
        "or": [
            {"field": "country", "string_value": "ES"},
            {"field": "country", "string_value": "FR"},
        ]
    })
    assert isinstance(expr.or_group, FilterExpressionList)
    assert len(expr.or_group.expressions) == 2


def test_build_filter_not():
    expr = _build_filter({"not": {"field": "deviceCategory", "string_value": "tablet"}})
    assert expr.not_expression.filter.string_filter.value == "tablet"


def test_build_filter_none_returns_none():
    assert _build_filter(None) is None


def test_build_filter_invalid_spec_raises():
    with pytest.raises(ValueError):
        _build_filter({"unknown_key": 123})


def test_build_filter_nested_and_or():
    expr = _build_filter({
        "and": [
            {"field": "country", "string_value": "ES"},
            {"or": [
                {"field": "deviceCategory", "string_value": "mobile"},
                {"field": "deviceCategory", "string_value": "desktop"},
            ]},
        ]
    })
    assert len(expr.and_group.expressions) == 2
    inner = expr.and_group.expressions[1]
    assert len(inner.or_group.expressions) == 2
