#!/usr/bin/env python3
"""End-to-end smoke test against real Google APIs.

Run after a code change to confirm the MCP still works end-to-end:
  python scripts/smoke_test.py

Requires `GOOGLE_APPLICATION_CREDENTIALS` env (or `gcloud auth application-default
login` already done) with both `webmasters.readonly` and `analytics.readonly` scopes.

Probes the following layers:
  1. Auth: build both clients without errors
  2. Admin: list GSC sites + GA4 properties
  3. Reporting: tiny GSC + GA4 queries
  4. Intelligence: anomalies on first GA4 property
  5. Cross-platform: traffic_health_check on a matched site/property pair
  6. Resource: algorithm updates overlap check
"""
from __future__ import annotations

import os
import sys
from typing import Any


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m"


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m"


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m"


def step(name: str, fn) -> Any:
    print(f"  {name}…", end=" ", flush=True)
    try:
        result = fn()
    except Exception as e:
        print(_red(f"FAIL ({type(e).__name__}: {str(e)[:120]})"))
        raise
    print(_green("OK"))
    return result


def main() -> int:
    os.environ.setdefault("GOOGLE_SEO_LOG_LEVEL", "WARNING")
    failures = 0

    print(_bold("\n[1/6] Auth"))
    try:
        from google_seo_mcp import auth

        step("build webmasters client", auth.get_webmasters)
        step("build searchconsole client", auth.get_searchconsole)
        step("build GA4 data client", auth.get_data_client)
        step("build GA4 admin client", auth.get_admin_client)
    except Exception:
        failures += 1

    print(_bold("\n[2/6] Admin discovery"))
    sites: list[dict] = []
    properties: list[dict] = []
    try:
        from google_seo_mcp.gsc.tools.sites import list_sites
        from google_seo_mcp.ga4.tools.admin import list_properties

        sites = step("list GSC sites", lambda: list_sites()["data"])
        properties = step("list GA4 properties", lambda: list_properties()["data"])
        print(f"     → {len(sites)} GSC sites · {len(properties)} GA4 properties")
    except Exception:
        failures += 1

    if not sites or not properties:
        print(_red("\n  Skipping further tests — no sites or properties accessible"))
        return 1

    sample_site = sites[0]["site_url"]
    sample_property = properties[0]["property"]
    print(f"\n  Using sample site: {sample_site}")
    print(f"  Using sample property: {sample_property}")

    print(_bold("\n[3/6] Reporting"))
    try:
        from google_seo_mcp.gsc.tools.analytics import site_snapshot
        from google_seo_mcp.ga4.tools.reporting import query_ga4

        step("gsc_site_snapshot", lambda: site_snapshot(sample_site, days=7))
        step(
            "ga4_query",
            lambda: query_ga4(
                sample_property,
                start_date="7daysAgo",
                end_date="yesterday",
                metrics=["sessions"],
                limit=1,
            ),
        )
    except Exception:
        failures += 1

    print(_bold("\n[4/6] Intelligence"))
    try:
        from google_seo_mcp.ga4.tools.intelligence import anomalies

        step("ga4_anomalies", lambda: anomalies(sample_property, days=14, z_threshold=2.0))
    except Exception:
        failures += 1

    print(_bold("\n[5/6] Cross-platform"))
    try:
        from google_seo_mcp.crossplatform.health import traffic_health_check

        step(
            "cross_traffic_health_check",
            lambda: traffic_health_check(sample_site, sample_property, days=14),
        )
    except Exception:
        failures += 1

    print(_bold("\n[6/6] Resource"))
    try:
        from google_seo_mcp.resources.google_algorithm_updates import (
            algorithm_updates_text,
            updates_overlapping,
        )

        step("algorithm updates text", lambda: algorithm_updates_text())
        step(
            "updates overlap with 2024-08-20",
            lambda: updates_overlapping("2024-08-20") or [{"name": "(none)"}],
        )
    except Exception:
        failures += 1

    print()
    if failures == 0:
        print(_green(_bold("✓ All smoke checks passed.")))
        return 0
    else:
        print(_red(_bold(f"✗ {failures} step(s) failed.")))
        return 1


if __name__ == "__main__":
    sys.exit(main())
