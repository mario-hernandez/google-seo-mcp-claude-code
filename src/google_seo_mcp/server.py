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
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version

from mcp.server.fastmcp import FastMCP


def _resolve_mcp_version() -> str:
    """Returns the installed `google-seo-mcp` package version, or 'unknown'.

    Used by `get_capabilities` so the operator can verify which version
    the MCP process actually loaded into memory — independent of what
    `pip show` reports (which only reflects metadata at install time
    and lies for editable installs after a code update without reinstall).
    """
    try:
        return _pkg_version("google-seo-mcp")
    except PackageNotFoundError:
        return "unknown (not installed as a package)"

from . import auth as auth_module
from .crossplatform import attribution as cp_attr
from .crossplatform import diagnosis as cp_diag
from .crossplatform import health as cp_health
from .crossplatform import journey as cp_journey
from .crossplatform import matrix as cp_matrix
from .crossplatform import multi_property as cp_multi
from .crux import tools as crux_tools
from .ga4.tools import admin as ga4_admin
from .ga4.tools import intelligence as ga4_intel
from .ga4.tools import reporting as ga4_reporting
from .gsc.tools import analytics as gsc_analytics
from .gsc.tools import intelligence as gsc_intel
from .gsc.tools import sitemaps as gsc_sitemaps
from .gsc.tools import sites as gsc_sites
from .history import tools as history_tools
from .indexing import tools as indexing_tools
from .lighthouse import tools as lh_tools
from .logs import tools as logs_tools
from .migration import crawl_advanced as migration_crawl_advanced
from .migration import tools as migration_tools
from .schema import tools as schema_tools
from .serp import tools as serp_tools
from .trends import tools as trends_tools
from .guardrails import GUARDRAIL_SUFFIX
from .resources.google_algorithm_updates import algorithm_updates_text

# MCP servers communicate JSON-RPC over stdout. ANY library log line that
# slips to stdout corrupts the protocol and the agent stops receiving
# tool results. We force every logger (ours and third-party) to stderr,
# and use ``force=True`` in case a library imported earlier already
# attached a handler to the root logger.
logging.basicConfig(
    level=os.getenv("GOOGLE_SEO_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stderr,
    force=True,
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
_register(ga4_intel.event_volume_comparison, name="ga4_event_volume_comparison")
_register(ga4_intel.cohort_retention, name="ga4_cohort_retention")
_register(ga4_intel.channel_attribution, name="ga4_channel_attribution")
_register(ga4_intel.content_decay, name="ga4_content_decay")

# ─── Cross-platform (the killer features) ────────────────────
_register(cp_journey.gsc_to_ga4_journey, name="cross_gsc_to_ga4_journey")
_register(cp_health.traffic_health_check, name="cross_traffic_health_check")
_register(cp_matrix.opportunity_matrix, name="cross_opportunity_matrix")
_register(cp_attr.seo_to_revenue_attribution, name="cross_seo_to_revenue_attribution")
_register(cp_diag.landing_page_full_diagnosis, name="cross_landing_page_full_diagnosis")
_register(cp_multi.multi_property_comparison, name="cross_multi_property_comparison")

# ─── Lighthouse / PageSpeed Insights (5) ────────────────────
_register(lh_tools.lighthouse_audit, name="lighthouse_audit")
_register(lh_tools.lighthouse_core_web_vitals, name="lighthouse_core_web_vitals")
_register(lh_tools.lighthouse_lcp_opportunities, name="lighthouse_lcp_opportunities")
_register(lh_tools.lighthouse_compare_mobile_desktop, name="lighthouse_compare_mobile_desktop")
_register(lh_tools.lighthouse_seo_score, name="lighthouse_seo_score")

# ─── Chrome UX Report (real-user CWV) (3) ───────────────────
_register(crux_tools.crux_current, name="crux_current")
_register(crux_tools.crux_history, name="crux_history")
_register(crux_tools.crux_compare_origins, name="crux_compare_origins")

# ─── Schema.org / structured data (3) ───────────────────────
_register(schema_tools.schema_extract_url, name="schema_extract_url")
_register(schema_tools.schema_validate_url, name="schema_validate_url")
_register(schema_tools.schema_suggest_for_page, name="schema_suggest_for_page")

# ─── Sitemap submission / Indexing (5) ──────────────────────
_register(indexing_tools.indexnow_generate_key, name="indexnow_generate_key")
_register(indexing_tools.indexnow_submit, name="indexnow_submit")
_register(indexing_tools.indexnow_submit_sitemap, name="indexnow_submit_sitemap")
_register(indexing_tools.google_indexing_publish, name="google_indexing_publish")
_register(indexing_tools.google_indexing_delete, name="google_indexing_delete")

# ─── Trends / Suggest / Alerts (5) ───────────────────────────
_register(trends_tools.google_suggest, name="google_suggest")
_register(trends_tools.google_suggest_alphabet, name="google_suggest_alphabet")
_register(trends_tools.google_trends_keyword, name="google_trends_keyword")
_register(trends_tools.google_trends_related, name="google_trends_related")
_register(trends_tools.alerts_rss_parse, name="alerts_rss_parse")

# ─── Migration: WP equity + SSR verify + sitemap diff (14) ───
_register(migration_tools.wp_audit_site, name="migration_wp_audit_site")
_register(migration_tools.wp_extract_redirects, name="migration_wp_extract_redirects")
_register(migration_tools.wp_internal_links_graph, name="migration_wp_internal_links_graph")
_register(migration_tools.prerender_check, name="migration_prerender_check")
_register(migration_tools.prerender_vs_hydrated, name="migration_prerender_vs_hydrated")
_register(migration_tools.googlebot_diff, name="migration_googlebot_diff")
_register(migration_tools.multi_bot_diff, name="migration_multi_bot_diff")
_register(migration_tools.verify_googlebot_ip, name="migration_verify_googlebot_ip")
_register(migration_tools.sitemap_diff, name="migration_sitemap_diff")
_register(migration_tools.sitemap_validate, name="migration_sitemap_validate")
_register(migration_tools.migration_redirects_plan, name="migration_redirects_plan")
_register(migration_tools.export_redirects_nginx, name="migration_export_redirects_nginx")
_register(migration_tools.export_redirects_apache, name="migration_export_redirects_apache")
_register(migration_tools.export_redirects_cloudflare, name="migration_export_redirects_cloudflare")
_register(migration_tools.seo_equity_report, name="migration_seo_equity_report")
_register(migration_tools.wayback_baseline, name="migration_wayback_baseline")
_register(migration_tools.schema_parity_check, name="migration_schema_parity_check")
_register(migration_tools.hreflang_cluster_audit, name="migration_hreflang_cluster_audit")
_register(migration_tools.indexation_recovery_monitor, name="migration_indexation_recovery_monitor")

# v0.7.0 — robots.txt audit + diff (Crawl Budget review)
from .migration import robots_audit as _robots_audit  # noqa: E402

def _robots_audit_tool(origin_url: str, sample_paths: list[str] | None = None) -> dict:
    """Audit robots.txt: sitemaps declared, crawl-delay, disallows, sample-path verdicts."""
    from .guardrails import with_meta
    return with_meta(
        _robots_audit.robots_audit(origin_url, sample_paths=sample_paths),
        source="migration.robots_audit", site_url=origin_url,
    )


def _robots_diff_tool(
    old_origin_url: str, new_origin_url: str,
    paths_to_check: list[str], user_agent: str = "Googlebot",
) -> dict:
    """Diff old vs new robots.txt for a set of ranked paths.

    Pass paths_to_check from `gsc_search_analytics(dimensions=['page'])` —
    URLs that already drive clicks. Anything `newly_blocked` is critical:
    you'll lose those clicks the day Google reads the new robots.txt.
    """
    from .guardrails import with_meta
    return with_meta(
        _robots_audit.robots_diff(
            old_origin_url, new_origin_url, paths_to_check, user_agent=user_agent,
        ),
        source="migration.robots_diff",
    )

_register(_robots_audit_tool, name="migration_robots_audit")
_register(_robots_diff_tool, name="migration_robots_diff")

# v0.7.0 — AEO foundation (Answer Engine Optimization)
from .aeo import llms_txt as _llms_txt_mod  # noqa: E402
from .aeo import ai_bots_robots as _ai_bots_mod  # noqa: E402

def _llms_txt_check(origin_url: str) -> dict:
    """Verify ``/llms.txt`` and ``/llms-full.txt`` (LLM-discoverable index).

    The llmstxt.org convention lets a site declare what an LLM should
    ingest. Anthropic, Vercel, Cloudflare and most modern docs sites
    publish it. Returns presence + parsed structure + lint warnings.
    """
    from .guardrails import with_meta
    return with_meta(
        _llms_txt_mod.llms_txt_check(origin_url),
        source="aeo.llms_txt_check", site_url=origin_url,
    )


def _ai_bots_robots(origin_url: str, sample_path: str = "/") -> dict:
    """Audit how every major AI/LLM crawler is treated by robots.txt.

    Reports per-bot allow/block (GPTBot, ClaudeBot, PerplexityBot,
    Google-Extended, CCBot, Bytespider, etc.) plus a vendor + purpose +
    docs URL so the agent can flag accidental blocks or accidental allows.
    """
    from .guardrails import with_meta
    return with_meta(
        _ai_bots_mod.aibots_robots_audit(origin_url, sample_path=sample_path),
        source="aeo.aibots_robots_audit", site_url=origin_url,
    )

_register(_llms_txt_check, name="aeo_llms_txt_check")
_register(_ai_bots_robots, name="aeo_ai_bots_robots_audit")

# v0.8.0 — Persistence (history/), SERP intelligence (DataForSEO),
# server log analysis, advanced technical crawl
_register(history_tools.history_save_snapshot, name="history_save_snapshot")
_register(history_tools.history_diff,          name="history_diff")
_register(history_tools.history_list,          name="history_list")

_register(serp_tools.serp_check,                name="serp_check")
_register(serp_tools.serp_aio_monitor,          name="serp_aio_monitor")
_register(serp_tools.serp_paa_extractor,        name="serp_paa_extractor")
_register(serp_tools.serp_competitor_intersect, name="serp_competitor_intersect")

_register(logs_tools.logs_parse,                  name="logs_parse")
_register(logs_tools.logs_googlebot_crawl_budget, name="logs_googlebot_crawl_budget")
_register(logs_tools.logs_bot_ratio,              name="logs_bot_ratio")
_register(logs_tools.logs_spider_trap_detector,   name="logs_spider_trap_detector")
_register(logs_tools.logs_crawl_waste,            name="logs_crawl_waste")
_register(logs_tools.logs_status_distribution,    name="logs_status_distribution")
_register(logs_tools.logs_verify_googlebot_ip,    name="logs_verify_googlebot_ip")

_register(migration_crawl_advanced.crawl_redirect_chains,        name="migration_redirect_chains")
_register(migration_crawl_advanced.check_broken_internal_links,  name="migration_broken_internal_links")
_register(migration_crawl_advanced.measure_response_times,       name="migration_response_times")
_register(migration_crawl_advanced.check_image_alt_coverage,     name="migration_image_alt_coverage")


# Singular convenience wrappers — same logic, single-URL input, friendlier
# return shape. Several internal docs and external prompts referenced these
# names before the plural ones were finalized; keeping both avoids breaking
# anyone's existing playbook.
def _migration_redirect_chain(url: str, max_hops: int = 10, timeout: float = 15.0) -> dict:
    """Trace the full 301/302 chain for a SINGLE URL.

    Returns the chain (list of {url, status, location}), final URL, hop count,
    and a flag if it exceeds Googlebot's drop threshold (5 hops).
    Use ``migration_redirect_chains`` for batched lookups over a URL list.
    """
    result = migration_crawl_advanced.crawl_redirect_chains(
        [url], max_hops=max_hops, timeout=timeout,
    )
    data = result.get("data") if isinstance(result, dict) and "data" in result else result
    chains = (data or {}).get("results", []) if isinstance(data, dict) else []
    single = chains[0] if chains else {"url": url, "error": "empty_result"}
    return {**result, "data": single} if isinstance(result, dict) and "_meta" in result else single


def _migration_image_alts(url: str, timeout: float = 15.0) -> dict:
    """Check ``<img alt>`` coverage for a SINGLE URL.

    Returns counts of images with/without alt, coverage_pct, and a sample of
    the missing-alt URLs. Use ``migration_image_alt_coverage`` for a batch over
    a list of pages.
    """
    result = migration_crawl_advanced.check_image_alt_coverage(
        [url], timeout=timeout,
    )
    data = result.get("data") if isinstance(result, dict) and "data" in result else result
    pages = (data or {}).get("page_results", []) if isinstance(data, dict) else []
    single = pages[0] if pages else {"page": url, "error": "empty_result"}
    return {**result, "data": single} if isinstance(result, dict) and "_meta" in result else single


_register(_migration_redirect_chain, name="migration_redirect_chain")
_register(_migration_image_alts,     name="migration_image_alts")


# ─── MCP Resource: Google algorithm updates reference ────────
@mcp.resource("google-seo://algorithm-updates")
def google_algorithm_updates_resource() -> str:
    """Reference list of confirmed Google Search algorithm updates (2023–2026).

    Use this resource when investigating traffic drops to correlate with industry-wide
    events. A drop on a core-update rollout day is much more likely Google-driven
    than site-specific.
    """
    return algorithm_updates_text()


@mcp.tool()
def reload_credentials() -> dict:
    """Reset in-process auth clients and reload credentials on next call.

    Use this when:
      - You rotated the Service Account JSON file (GOOGLE_SEO_SERVICE_ACCOUNT_FILE).
      - You ran `gcloud auth application-default login` and need the MCP to pick
        up the new ADC.
      - Tools are returning data from the previous client / tenant after switching.
      - The cached OAuth token is stale and you want a fresh consent flow.

    The response includes `credential_type` ('service_account' / 'adc' /
    'oauth_flow' / 'none') so you know which method will be used on the next
    call. Service Account credentials are self-issued JWTs — no real "re-auth"
    happens, just a cache reset and JSON reload from disk. ADC and OAuth flow
    do re-validate against Google.
    """
    return auth_module.reset_clients()


@mcp.tool()
def reauthenticate() -> dict:
    """Deprecated alias for `reload_credentials`. Kept for backward compatibility.

    Was misleading when the active credential is a Service Account (JWT-based,
    no re-auth handshake exists). Use `reload_credentials` going forward.
    """
    return auth_module.reset_clients()


@mcp.tool()
def get_capabilities() -> dict:
    """List all tools exposed by this MCP and current auth status. Call FIRST.

    Returns the tool catalog grouped by category, plus a quick check of whether
    credentials are reachable for both Google Search Console and Google Analytics 4.

    Also returns `mcp_version` and `credential_type` so the operator can verify
    which version is actually loaded in memory and which auth method is active —
    independent of what external tooling (pip show, env files) reports.
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
        "mcp_version": _resolve_mcp_version(),
        "auth": {
            "gsc": {"ok": gsc_ok, "error": gsc_err},
            "ga4": {"ok": ga4_ok, "error": ga4_err},
            "credential_type": auth_module.current_credential_type(),
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
                "ga4_landing_page_health", "ga4_event_volume_comparison",
                "ga4_conversion_funnel",  # deprecated alias of event_volume_comparison
                "ga4_cohort_retention", "ga4_channel_attribution",
                "ga4_content_decay",
            ],
            "cross_platform": [
                "cross_gsc_to_ga4_journey",
                "cross_traffic_health_check",
                "cross_opportunity_matrix",
                "cross_seo_to_revenue_attribution",
                "cross_landing_page_full_diagnosis",
                "cross_multi_property_comparison",
            ],
            "lighthouse": [
                "lighthouse_audit", "lighthouse_core_web_vitals",
                "lighthouse_lcp_opportunities", "lighthouse_compare_mobile_desktop",
                "lighthouse_seo_score",
            ],
            "crux": ["crux_current", "crux_history", "crux_compare_origins"],
            "schema": [
                "schema_extract_url", "schema_validate_url", "schema_suggest_for_page",
            ],
            "indexing": [
                "indexnow_generate_key", "indexnow_submit", "indexnow_submit_sitemap",
                "google_indexing_publish", "google_indexing_delete",
            ],
            "trends": [
                "google_suggest", "google_suggest_alphabet",
                "google_trends_keyword", "google_trends_related",
                "alerts_rss_parse",
            ],
            "migration": [
                "migration_wp_audit_site",
                "migration_wp_extract_redirects",
                "migration_wp_internal_links_graph",
                "migration_prerender_check",
                "migration_prerender_vs_hydrated",
                "migration_googlebot_diff",
                "migration_multi_bot_diff",
                "migration_verify_googlebot_ip",
                "migration_sitemap_diff",
                "migration_sitemap_validate",
                "migration_redirects_plan",
                "migration_export_redirects_nginx",
                "migration_export_redirects_apache",
                "migration_export_redirects_cloudflare",
                "migration_seo_equity_report",
                "migration_wayback_baseline",
                "migration_schema_parity_check",
                "migration_hreflang_cluster_audit",
                "migration_indexation_recovery_monitor",
            ],
            "meta": ["get_capabilities", "reauthenticate"],
            "resources": ["google-seo://algorithm-updates"],
        },
        "tip": (
            "Swiss-knife workflow: (1) `gsc_list_sites` + `ga4_list_properties` to "
            "enumerate. (2) `cross_traffic_health_check` to verify tracking. "
            "(3) `lighthouse_audit` + `crux_current` for performance health. "
            "(4) `cross_opportunity_matrix` for prioritisation. (5) `schema_validate_url` "
            "to find rich-result gaps. (6) `google_suggest_alphabet` to discover "
            "long-tails. (7) `indexnow_submit` to ping Bing/Yandex on changes."
        ),
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
