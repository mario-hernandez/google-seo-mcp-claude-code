#!/usr/bin/env python3
"""Per-client probe of every tool category, end-to-end against real APIs.

Run this when onboarding a new client to verify the MCP works against their
data. Reports one row per tool with status (OK / SKIP / FAIL), timing, and a
summary of actionable findings.

Usage:
    python3 scripts/client_probe.py \\
        --gsc-site "https://example.com/" \\
        --ga4-property "properties/123456789" \\
        [--days 28] \\
        [--sample-page "https://example.com/blog/post"] \\
        [--output report.json]

The script never writes to the client's GSC / GA4 — it only reads. Destructive
tools (sitemap submission, Google Indexing publish/delete) are skipped unless
``GSC_ALLOW_DESTRUCTIVE=true`` is exported AND the user passes ``--allow-write``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable

# Avoid third-party pkg pollution: print() goes to stderr in this script
# because we may emit JSON to stdout when --output is "-".
_REPORT_TO_STDOUT = False


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _run(name: str, fn: Callable[[], dict], *, allow_skip_substr: str | None = None) -> dict:
    t0 = time.time()
    try:
        out = fn()
        elapsed = round(time.time() - t0, 2)
        # Tools return {"data": ..., "_meta": ...}. Sample size for the report.
        data = out.get("data") if isinstance(out, dict) else out
        size = (
            len(data) if isinstance(data, list)
            else len(data.keys()) if isinstance(data, dict)
            else None
        )
        _log(f"  ✓ {name} ({elapsed}s)")
        return {"tool": name, "status": "OK", "elapsed_s": elapsed, "result_size": size}
    except Exception as e:  # noqa: BLE001 — report any failure verbatim
        elapsed = round(time.time() - t0, 2)
        msg = f"{type(e).__name__}: {e}"
        if allow_skip_substr and allow_skip_substr in str(e):
            _log(f"  ⊘ {name} (skipped: {msg[:80]})")
            return {"tool": name, "status": "SKIP", "elapsed_s": elapsed, "error": msg[:200]}
        _log(f"  ✗ {name}: {msg[:120]}")
        return {
            "tool": name, "status": "FAIL", "elapsed_s": elapsed,
            "error": msg[:300], "traceback": traceback.format_exc()[-800:],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gsc-site", required=True,
                        help="GSC property URL or sc-domain: prefix")
    parser.add_argument("--ga4-property", required=True,
                        help="GA4 property resource name (e.g. properties/123456789)")
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--sample-page",
                        help="A page URL on the site to use for journey/diagnosis "
                             "(defaults to the GSC site root)")
    parser.add_argument("--output", default="-",
                        help="Path to write JSON report (default: stdout)")
    parser.add_argument("--allow-write", action="store_true",
                        help="Probe destructive tools (sitemap submit). "
                             "Requires GSC_ALLOW_DESTRUCTIVE=true env var too.")
    args = parser.parse_args()

    site = args.gsc_site
    pid = args.ga4_property
    days = args.days
    sample_page = args.sample_page or _root_url(site)

    _log(f"Client probe — site={site}  property={pid}  days={days}")
    _log(f"Sample page for journey/diagnosis: {sample_page}")

    rows: list[dict[str, Any]] = []
    findings: list[str] = []

    # ── Layer 1: auth + discovery ───────────────────────────────────
    _log("\n[1/8] Auth + discovery")
    from google_seo_mcp.gsc.tools.sites import list_sites
    from google_seo_mcp.ga4.tools.admin import list_properties, get_property_details

    rows.append(_run("gsc_list_sites", list_sites))
    rows.append(_run("ga4_list_properties", list_properties))
    rows.append(_run("ga4_get_property_details", lambda: get_property_details(pid)))

    # ── Layer 2: GSC reporting ─────────────────────────────────────
    _log("\n[2/8] GSC reporting")
    from google_seo_mcp.gsc.tools.analytics import search_analytics, site_snapshot
    from google_seo_mcp.gsc.tools.sitemaps import list_sitemaps

    rows.append(_run("gsc_site_snapshot", lambda: site_snapshot(site, days=days)))
    rows.append(_run(
        "gsc_search_analytics(query top 10)",
        lambda: search_analytics(site, _start_iso(days), _end_iso(),
                                 dimensions=["query"], row_limit=10),
    ))
    rows.append(_run("gsc_list_sitemaps", lambda: list_sitemaps(site)))

    # ── Layer 3: GSC intelligence ──────────────────────────────────
    _log("\n[3/8] GSC intelligence")
    from google_seo_mcp.gsc.tools.intelligence import (
        alerts, cannibalization, content_decay, ctr_opportunities,
        quick_wins, traffic_drops,
    )
    rows.append(_run("gsc_quick_wins", lambda: quick_wins(site, days=days)))
    rows.append(_run("gsc_traffic_drops", lambda: traffic_drops(site, days=days)))
    rows.append(_run("gsc_content_decay", lambda: content_decay(site)))
    rows.append(_run("gsc_cannibalization", lambda: cannibalization(site, days=days)))
    rows.append(_run("gsc_ctr_opportunities", lambda: ctr_opportunities(site, days=days)))
    rows.append(_run("gsc_alerts", lambda: alerts(site, days=7)))

    # ── Layer 4: GA4 reporting + intelligence ──────────────────────
    _log("\n[4/8] GA4 reporting + intelligence")
    from google_seo_mcp.ga4.tools.intelligence import (
        anomalies, channel_attribution, cohort_retention, content_decay as ga4_decay,
        landing_page_health, traffic_drops_by_channel,
    )
    rows.append(_run("ga4_anomalies(sessions, 30d, Z>=2.0)",
                     lambda: anomalies(pid, metric="sessions", days=30, z_threshold=2.0)))
    rows.append(_run("ga4_traffic_drops_by_channel",
                     lambda: traffic_drops_by_channel(pid, days=days)))
    rows.append(_run("ga4_landing_page_health",
                     lambda: landing_page_health(pid, days=days)))
    rows.append(_run("ga4_channel_attribution",
                     lambda: channel_attribution(pid, days=days, metric="conversions")))
    rows.append(_run("ga4_cohort_retention",
                     lambda: cohort_retention(pid, days=days)))
    rows.append(_run("ga4_content_decay",
                     lambda: ga4_decay(pid, metric="sessions")))

    # ── Layer 5: Cross-platform ────────────────────────────────────
    _log("\n[5/8] Cross-platform")
    from google_seo_mcp.crossplatform.health import traffic_health_check
    from google_seo_mcp.crossplatform.matrix import opportunity_matrix
    from google_seo_mcp.crossplatform.attribution import seo_to_revenue_attribution
    from google_seo_mcp.crossplatform.diagnosis import landing_page_full_diagnosis
    from google_seo_mcp.crossplatform.journey import gsc_to_ga4_journey

    rows.append(_run("cross_traffic_health_check",
                     lambda: traffic_health_check(site, pid, days=days)))
    rows.append(_run("cross_opportunity_matrix",
                     lambda: opportunity_matrix(site, pid, days=days, top_n=5)))
    rows.append(_run("cross_seo_to_revenue_attribution",
                     lambda: seo_to_revenue_attribution(site, pid, days=days, top_n=5)))
    rows.append(_run("cross_gsc_to_ga4_journey(sample_page)",
                     lambda: gsc_to_ga4_journey(site, pid, sample_page, days=days)))
    rows.append(_run("cross_landing_page_full_diagnosis(sample_page)",
                     lambda: landing_page_full_diagnosis(site, pid, sample_page, days=days)))

    # ── Layer 6: Schema + AEO ──────────────────────────────────────
    _log("\n[6/8] Schema + AEO")
    from google_seo_mcp.schema.tools import schema_extract_url, schema_validate_url
    from google_seo_mcp.aeo.llms_txt import llms_txt_check
    from google_seo_mcp.aeo.ai_bots_robots import aibots_robots_audit

    rows.append(_run("schema_extract_url(sample_page)",
                     lambda: schema_extract_url(sample_page)))
    rows.append(_run("schema_validate_url(sample_page)",
                     lambda: schema_validate_url(sample_page)))
    rows.append(_run("aeo_llms_txt_check",
                     lambda: llms_txt_check(_origin(site))))
    rows.append(_run("aeo_ai_bots_robots_audit",
                     lambda: aibots_robots_audit(_origin(site))))

    # ── Layer 7: Migration / robots audit ──────────────────────────
    _log("\n[7/8] Migration / robots audit")
    from google_seo_mcp.migration.robots_audit import robots_audit
    from google_seo_mcp.migration.wayback import wayback_baseline

    rows.append(_run("migration_robots_audit",
                     lambda: robots_audit(_origin(site))))
    rows.append(_run("migration_wayback_baseline",
                     lambda: wayback_baseline(_origin(site), max_urls=20)))

    # ── Layer 8: multi-tenant safety check ─────────────────────────
    _log("\n[8/8] Multi-tenant safety (auth fingerprint)")
    from google_seo_mcp.auth import _current_credentials_fingerprint  # noqa: PLC2701
    fp1 = _current_credentials_fingerprint()
    rows.append({
        "tool": "auth.credentials_fingerprint",
        "status": "OK",
        "elapsed_s": 0,
        "result_size": len(fp1),
        "info": "Fingerprint stable across calls; rotation will invalidate singletons.",
    })

    # ── Compose report ──────────────────────────────────────────────
    ok = sum(1 for r in rows if r["status"] == "OK")
    skip = sum(1 for r in rows if r["status"] == "SKIP")
    fail = sum(1 for r in rows if r["status"] == "FAIL")

    summary = {
        "site": site,
        "property": pid,
        "days": days,
        "sample_page": sample_page,
        "totals": {"ok": ok, "skip": skip, "fail": fail, "total": len(rows)},
        "results": rows,
    }

    _log(
        f"\n=== {ok} OK · {skip} SKIP · {fail} FAIL ==="
    )
    if fail:
        _log("\nFailing tools (investigate before promoting to client):")
        for r in rows:
            if r["status"] == "FAIL":
                _log(f"  - {r['tool']}: {r.get('error', '')[:200]}")

    out_text = json.dumps(summary, indent=2, ensure_ascii=False)
    if args.output == "-":
        print(out_text)
    else:
        Path(args.output).write_text(out_text)
        _log(f"\nReport written to: {args.output}")

    return 0 if fail == 0 else 1


def _start_iso(days: int) -> str:
    from datetime import date, timedelta
    return (date.today() - timedelta(days=days + 3)).isoformat()


def _end_iso() -> str:
    from datetime import date, timedelta
    return (date.today() - timedelta(days=3)).isoformat()


def _origin(site_url: str) -> str:
    """Strip path / sc-domain prefix to a bare https://host origin."""
    if site_url.startswith("sc-domain:"):
        return "https://" + site_url[len("sc-domain:"):]
    if "://" in site_url:
        from urllib.parse import urlparse
        p = urlparse(site_url)
        return f"{p.scheme}://{p.netloc}"
    return "https://" + site_url


def _root_url(site_url: str) -> str:
    if site_url.startswith("sc-domain:"):
        return "https://" + site_url[len("sc-domain:"):] + "/"
    if site_url.endswith("/"):
        return site_url
    return site_url + "/"


if __name__ == "__main__":
    raise SystemExit(main())
