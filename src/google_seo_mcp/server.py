"""MCP server entrypoint — unified Google SEO suite (GSC + GA4 + cross-platform).

Tools are namespaced with prefixes to avoid collisions and aid LLM discovery:
  - `gsc_*`  for Google Search Console tools (14)
  - `ga4_*`  for Google Analytics 4 tools (14)
  - `cross_*` for cross-platform tools that use both APIs (5)
  - meta:    `get_capabilities`, `reauthenticate`
"""
from __future__ import annotations

import logging
import os

from mcp.server.fastmcp import FastMCP

from . import auth as auth_module
from .crossplatform import attribution as cp_attr
from .crossplatform import diagnosis as cp_diag
from .crossplatform import health as cp_health
from .crossplatform import journey as cp_journey
from .crossplatform import matrix as cp_matrix
from .ga4.tools import admin as ga4_admin
from .ga4.tools import intelligence as ga4_intel
from .ga4.tools import reporting as ga4_reporting
from .gsc.tools import analytics as gsc_analytics
from .gsc.tools import intelligence as gsc_intel
from .gsc.tools import sitemaps as gsc_sitemaps
from .gsc.tools import sites as gsc_sites
from .guardrails import GUARDRAIL_SUFFIX

logging.basicConfig(
    level=os.getenv("GOOGLE_SEO_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

mcp = FastMCP("google-seo-mcp")


def _register(fn, *, name: str):
    """Register a tool with a specific name and append the guardrail suffix.

    Idempotent: detects whether the suffix has already been appended (so registering
    the same function twice doesn't duplicate the suffix).
    """
    base_doc = (fn.__doc__ or "").rstrip()
    if not base_doc.endswith(GUARDRAIL_SUFFIX.rstrip()):
        fn.__doc__ = base_doc + GUARDRAIL_SUFFIX
    return mcp.tool(name=name)(fn)


# ─── GSC: sites & inspection ─────────────────────────────────
_register(gsc_sites.list_sites, name="gsc_list_sites")
_register(gsc_sites.inspect_url, name="gsc_inspect_url")

# ─── GSC: sitemaps ───────────────────────────────────────────
_register(gsc_sitemaps.list_sitemaps, name="gsc_list_sitemaps")
_register(gsc_sitemaps.submit_sitemap, name="gsc_submit_sitemap")

# ─── GSC: analytics ──────────────────────────────────────────
_register(gsc_analytics.search_analytics, name="gsc_search_analytics")
_register(gsc_analytics.site_snapshot, name="gsc_site_snapshot")

# ─── GSC: intelligence ───────────────────────────────────────
_register(gsc_intel.quick_wins, name="gsc_quick_wins")
_register(gsc_intel.traffic_drops, name="gsc_traffic_drops")
_register(gsc_intel.content_decay, name="gsc_content_decay")
_register(gsc_intel.cannibalization, name="gsc_cannibalization")
_register(gsc_intel.ctr_opportunities, name="gsc_ctr_opportunities")
_register(gsc_intel.alerts, name="gsc_alerts")

# ─── GA4: admin ──────────────────────────────────────────────
_register(ga4_admin.list_properties, name="ga4_list_properties")
_register(ga4_admin.get_property_details, name="ga4_get_property_details")

# ─── GA4: schema & reporting ─────────────────────────────────
_register(ga4_reporting.search_ga4_schema, name="ga4_search_schema")
_register(ga4_reporting.list_schema_categories, name="ga4_list_schema_categories")
_register(ga4_reporting.estimate_query_size, name="ga4_estimate_query_size")
_register(ga4_reporting.query_ga4, name="ga4_query")

# ─── GA4: intelligence ───────────────────────────────────────
_register(ga4_intel.anomalies, name="ga4_anomalies")
_register(ga4_intel.traffic_drops_by_channel, name="ga4_traffic_drops_by_channel")
_register(ga4_intel.landing_page_health, name="ga4_landing_page_health")
_register(ga4_intel.conversion_funnel, name="ga4_conversion_funnel")
_register(ga4_intel.cohort_retention, name="ga4_cohort_retention")
_register(ga4_intel.channel_attribution, name="ga4_channel_attribution")
_register(ga4_intel.content_decay, name="ga4_content_decay")

# ─── Cross-platform (the killer features) ────────────────────
_register(cp_journey.gsc_to_ga4_journey, name="cross_gsc_to_ga4_journey")
_register(cp_health.traffic_health_check, name="cross_traffic_health_check")
_register(cp_matrix.opportunity_matrix, name="cross_opportunity_matrix")
_register(cp_attr.seo_to_revenue_attribution, name="cross_seo_to_revenue_attribution")
_register(cp_diag.landing_page_full_diagnosis, name="cross_landing_page_full_diagnosis")


@mcp.tool()
def reauthenticate() -> dict:
    """Force re-authentication on the next API call.

    Useful when ADC credentials have changed or OAuth token has expired and
    cached state is stale. Resets in-process clients for both GSC and GA4.
    """
    auth_module.reset_clients()
    return {
        "status": "ok",
        "message": "Auth clients reset; next call will rebuild credentials for both GSC and GA4.",
    }


@mcp.tool()
def get_capabilities() -> dict:
    """List all tools exposed by this MCP and current auth status. Call FIRST.

    Returns the tool catalog grouped by category, plus a quick check of whether
    credentials are reachable for both Google Search Console and Google Analytics 4.
    """
    gsc_ok = True
    ga4_ok = True
    gsc_err: str | None = None
    ga4_err: str | None = None
    try:
        auth_module.get_webmasters().sites().list().execute()
    except Exception as e:
        gsc_ok = False
        gsc_err = str(e)[:200]
    try:
        admin = auth_module.get_admin_client()
        next(iter(admin.list_account_summaries()), None)
    except Exception as e:
        ga4_ok = False
        ga4_err = str(e)[:200]

    return {
        "auth": {
            "gsc": {"ok": gsc_ok, "error": gsc_err},
            "ga4": {"ok": ga4_ok, "error": ga4_err},
            "destructive_enabled": os.getenv("GSC_ALLOW_DESTRUCTIVE") == "true",
        },
        "categories": {
            "gsc_sites": ["gsc_list_sites", "gsc_inspect_url"],
            "gsc_sitemaps": ["gsc_list_sitemaps", "gsc_submit_sitemap"],
            "gsc_analytics": ["gsc_search_analytics", "gsc_site_snapshot"],
            "gsc_intelligence": [
                "gsc_quick_wins", "gsc_traffic_drops", "gsc_content_decay",
                "gsc_cannibalization", "gsc_ctr_opportunities", "gsc_alerts",
            ],
            "ga4_admin": ["ga4_list_properties", "ga4_get_property_details"],
            "ga4_reporting": [
                "ga4_search_schema", "ga4_list_schema_categories",
                "ga4_estimate_query_size", "ga4_query",
            ],
            "ga4_intelligence": [
                "ga4_anomalies", "ga4_traffic_drops_by_channel",
                "ga4_landing_page_health", "ga4_conversion_funnel",
                "ga4_cohort_retention", "ga4_channel_attribution",
                "ga4_content_decay",
            ],
            "cross_platform": [
                "cross_gsc_to_ga4_journey",
                "cross_traffic_health_check",
                "cross_opportunity_matrix",
                "cross_seo_to_revenue_attribution",
                "cross_landing_page_full_diagnosis",
            ],
            "meta": ["get_capabilities", "reauthenticate"],
        },
        "tip": (
            "Workflow: (1) `gsc_list_sites` + `ga4_list_properties` to enumerate. "
            "(2) `cross_traffic_health_check` to verify GSC↔GA4 tracking is consistent. "
            "(3) `cross_opportunity_matrix` to surface pages where ranking up would also "
            "convert. (4) `cross_landing_page_full_diagnosis` to triage one page end-to-end. "
            "(5) `cross_seo_to_revenue_attribution` to see which queries actually pay."
        ),
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
