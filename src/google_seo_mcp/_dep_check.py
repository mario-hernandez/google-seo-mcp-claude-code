"""Optional-dependency probing — surfaces missing extras to the operator
*before* they invoke a tool that depends on them.

Real-world papercut: a forensic auditor running ``prerender_vs_hydrated`` in
parallel with three other tools discovered mid-execution that Playwright
wasn't installed. The error message was actionable but it surfaced too late.
The agent should be able to plan around missing deps **before** invoking
anything.

Each entry below documents one optional dependency:
    name           — the package import name to probe.
    installs       — the pip extra (``pip install google-seo-mcp[ssr]``)
                     OR the bare pip install command if no extra is defined.
    extra_command  — extra setup beyond pip (e.g. Playwright needs a browser
                     download after the python package is installed).
    affected_tools — exact tool names that fail when this dep is absent.

The probe is import-only (no execution), so it's safe and fast — runs in
~5ms total even when probing all entries.
"""
from __future__ import annotations

import importlib.util
from typing import Any


# Single source of truth: each optional dep plus what it powers.
_OPTIONAL_DEPS: list[dict[str, Any]] = [
    {
        "name": "playwright",
        "import_module": "playwright",
        "installs": "pip install google-seo-mcp[ssr]",
        "extra_command": "playwright install chromium",
        "reason_when_missing": "Playwright is required to drive a real headless browser for hydration diffs.",
        "affected_tools": [
            "migration_prerender_vs_hydrated",
        ],
    },
    {
        "name": "statsmodels + scipy",
        "import_module": "statsmodels",
        "installs": "pip install google-seo-mcp[stats]",
        "extra_command": None,
        "reason_when_missing": "STL deseasonalisation and BH-FDR multiple-testing correction in ga4_anomalies fall back to plain leave-one-out Z-score without these.",
        "affected_tools": [
            "ga4_anomalies",  # degraded — legacy path still works
        ],
        "degraded_not_broken": True,
    },
    {
        "name": "advertools (Scrapy crawler)",
        "import_module": "advertools",
        "installs": "pip install google-seo-mcp",  # already in core deps
        "extra_command": None,
        "reason_when_missing": "Internal-links graph crawler depends on advertools/Scrapy.",
        "affected_tools": [
            "migration_wp_internal_links_graph",
            "migration_seo_equity_report",  # uses the graph
        ],
    },
    {
        "name": "extruct",
        "import_module": "extruct",
        "installs": "pip install google-seo-mcp",  # core dep
        "extra_command": None,
        "reason_when_missing": "Schema extraction uses extruct for JSON-LD/microdata/RDFa parsing.",
        "affected_tools": [
            "schema_extract_url",
            "schema_validate_url",
            "migration_schema_parity_check",
        ],
    },
    {
        "name": "rapidfuzz",
        "import_module": "rapidfuzz",
        "installs": "pip install google-seo-mcp",  # core dep
        "extra_command": None,
        "reason_when_missing": "Slug similarity scoring in migration_redirects_plan needs rapidfuzz.",
        "affected_tools": [
            "migration_redirects_plan",
        ],
    },
    {
        "name": "pytrends",
        "import_module": "pytrends",
        "installs": "pip install google-seo-mcp",  # core dep
        "extra_command": None,
        "reason_when_missing": "Google Trends queries fall through to errors.",
        "affected_tools": [
            "google_trends_keyword",
            "google_trends_related",
        ],
    },
    {
        "name": "waybackpy",
        "import_module": "waybackpy",
        "installs": "pip install google-seo-mcp",  # core dep
        "extra_command": None,
        "reason_when_missing": "Wayback Machine baseline can't fetch archived snapshots.",
        "affected_tools": [
            "migration_wayback_baseline",
        ],
    },
    {
        "name": "defusedxml",
        "import_module": "defusedxml",
        "installs": "pip install google-seo-mcp",  # core dep
        "extra_command": None,
        "reason_when_missing": "XML parsing falls back to stdlib (XXE risk in sitemap diffs).",
        "affected_tools": [
            "migration_sitemap_diff",
            "migration_sitemap_validate",
            "indexnow_submit_sitemap",
        ],
        "degraded_not_broken": True,
    },
]


def _is_importable(module_name: str) -> bool:
    """Fast probe — does NOT execute the module's top-level code."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def probe_optional_deps() -> dict[str, Any]:
    """Returns a structured report of which optional deps are missing.

    Shape (designed to be the ``deps`` field of ``get_capabilities``)::

        {
            "all_available": false,
            "missing_count": 1,
            "unavailable": [
                {
                    "name": "playwright",
                    "reason": "Playwright is required to drive a real ...",
                    "install_cmd": "pip install google-seo-mcp[ssr]",
                    "extra_cmd": "playwright install chromium",
                    "affected_tools": ["migration_prerender_vs_hydrated"],
                    "degraded_not_broken": false
                }
            ],
            "available": ["statsmodels + scipy", "advertools (Scrapy crawler)", ...]
        }

    The agent reads ``unavailable[*].affected_tools`` to know which tools
    will fail BEFORE invoking them — and can either skip them, ask the
    human to install, or plan around the gap.
    """
    available: list[str] = []
    unavailable: list[dict[str, Any]] = []
    for dep in _OPTIONAL_DEPS:
        if _is_importable(dep["import_module"]):
            available.append(dep["name"])
            continue
        unavailable.append({
            "name": dep["name"],
            "reason": dep["reason_when_missing"],
            "install_cmd": dep["installs"],
            "extra_cmd": dep.get("extra_command"),
            "affected_tools": dep["affected_tools"],
            "degraded_not_broken": dep.get("degraded_not_broken", False),
        })
    return {
        "all_available": len(unavailable) == 0,
        "missing_count": len(unavailable),
        "unavailable": unavailable,
        "available": available,
    }
