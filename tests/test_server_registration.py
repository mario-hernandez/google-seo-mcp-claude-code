"""Sanity tests for the server registration — all 32 tools must register."""
from __future__ import annotations

from google_seo_mcp.server import mcp


def test_tool_count():
    tools = list(mcp._tool_manager.list_tools())
    # 12 GSC + 13 GA4 + 6 cross + 5 LH + 3 CrUX + 3 Schema + 5 Idx + 5 Trends + 2 meta = 54
    assert len(tools) == 73, f"Expected 73 tools, got {len(tools)}"


def test_tool_names_have_expected_prefixes():
    tools = {t.name for t in mcp._tool_manager.list_tools()}
    # 6 cross-platform
    assert {
        "cross_gsc_to_ga4_journey",
        "cross_traffic_health_check",
        "cross_opportunity_matrix",
        "cross_seo_to_revenue_attribution",
        "cross_landing_page_full_diagnosis",
        "cross_multi_property_comparison",
    } <= tools
    assert sum(1 for t in tools if t.startswith("gsc_")) == 12
    assert sum(1 for t in tools if t.startswith("ga4_")) == 13
    assert sum(1 for t in tools if t.startswith("cross_")) == 6
    assert "get_capabilities" in tools
    assert "reauthenticate" in tools


def test_diagnostic_tools_have_guardrail_suffix():
    """Every registered _diagnostic_ tool (gsc_/ga4_/cross_) must include the suffix.

    Meta tools (get_capabilities, reauthenticate) are registered with @mcp.tool()
    directly without going through `_register`, so they don't carry the suffix —
    that's intentional since they don't return user-facing data.
    """
    suffix_marker = "Use ONLY the data returned by this tool"
    for tool in mcp._tool_manager.list_tools():
        if tool.name in {"get_capabilities", "reauthenticate"}:
            continue
        desc = tool.description or ""
        assert suffix_marker in desc, f"Tool {tool.name} missing guardrail suffix"
