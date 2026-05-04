"""Migration tools registered with the MCP server."""
from __future__ import annotations

from typing import Any

from ..guardrails import with_meta
from . import cloaking as ck
from . import equity_report as er
from . import hreflang as hl
from . import indexation as ix
from . import prerender as pr
from . import redirects_plan as rp
from . import schema_parity as sp
from . import sitemap_diff as sd
from . import wayback as wb
from . import wp_audit as wa


# ─── WordPress audit (read-only) ─────────────────────────────

def wp_audit_site(wp_url: str, max_pages: int = 200) -> dict:
    """Inventory a WordPress site: REST API summary + advertools crawl.

    Returns post types, taxonomies, plugin probes, and crawl rows containing
    title/meta/h1/canonical/schema for each page (up to `max_pages`).

    Used as the foundation for migration planning. Read-only.
    """
    summary = wa.wp_summary(wp_url)
    rest_urls = wa.wp_iterate_urls(wp_url, max_pages=max_pages)
    return with_meta(
        {
            "summary": summary,
            "rest_urls_count": len(rest_urls),
            "rest_urls_sample": rest_urls[:50],
        },
        source="migration.wp_audit_site",
        site_url=wp_url,
    )


def wp_extract_redirects(
    wp_url: str,
    auth_user: str | None = None,
    auth_pass: str | None = None,
) -> dict:
    """Enumerate existing redirects from WordPress plugins (Redirection / RankMath).

    Most plugins require admin auth — pass `auth_user` and `auth_pass`
    (an app-password from WP user profile, NOT the login password).
    """
    auth = (auth_user, auth_pass) if (auth_user and auth_pass) else None
    redirects = wa.fetch_wp_redirects(wp_url, auth=auth)
    return with_meta(
        {
            "redirects": redirects,
            "count": len(redirects),
            "by_plugin": _group_by_plugin(redirects),
        },
        source="migration.wp_extract_redirects",
        site_url=wp_url,
    )


def _group_by_plugin(redirects: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in redirects:
        out[r.get("plugin", "unknown")] = out.get(r.get("plugin", "unknown"), 0) + 1
    return out


def wp_internal_links_graph(wp_url: str, max_pages: int = 200) -> dict:
    """Build internal-links graph for a WordPress site (advertools crawl).

    Returns nodes with in/out degree, edge list, orphan pages (in_degree=0),
    and the top 10 internal hubs (highest in_degree).
    """
    rows = wa.crawl_site_advertools(wp_url, max_pages=max_pages)
    graph = wa.internal_links_graph_from_crawl(rows)
    return with_meta(
        graph,
        source="migration.wp_internal_links_graph",
        site_url=wp_url,
        extra={"crawled_pages": len(rows)},
    )


# ─── Pre-render / SSR verification ───────────────────────────

def prerender_check(url: str) -> dict:
    """Fetch a URL without executing JS and report SEO signal health.

    Use on JS-SSR sites (React/Vue/Svelte) to confirm Googlebot receives
    real pre-rendered HTML — meta tags, schema, OG, visible content —
    before client hydration. Returns a `health` of green / amber / red.
    """
    return with_meta(pr.prerender_signals(url), source="migration.prerender_check", site_url=url)


# ─── Calibration check golden set ───────────────────────────────────────
# Curated public sites with known prerender behaviour, used as control
# samples when verifying the detector hasn't drifted. The version stamp
# below is BUMPED whenever the dev rotates the set — so an operator who
# sees a `drift_detected` after a long gap can compare their installed
# version against the latest README to know whether the failure is an
# instrument regression OR a stale benchmark.
#
# **Maintenance note for the dev**: re-validate this set roughly every
# 6-12 months. Vercel/Cloudflare/etc. rotate their stacks (RSC,
# streaming, ISR) and a target that was `ssr` last quarter may be
# something else next quarter. If you hit a false `drift_detected`,
# refresh the set, bump `_GOLDEN_SET_VERSION`, document the change in
# CHANGELOG, and ship. See issue tracker for the `meta_validate_golden_set`
# proposal — an internal job to auto-detect benchmark rot.
_GOLDEN_SET_VERSION = "2026-Q2.1"
_GOLDEN_SET: dict[str, str] = {
    # Production SSR sites — independently validated 2026-05-04 by
    # `meta_validate_golden_set`. Each scores 7000+ chars of pre-rendered
    # visible text with 3-4/4 head signals (title, meta description,
    # canonical, og). All four hosted on different stacks so a single
    # vendor outage doesn't break all probes.
    "https://nextjs.org/": "ssr",          # Next.js + Vercel
    "https://www.cloudflare.com/": "ssr",  # Workers + Cloudflare edge
    "https://reactjs.org/": "ssr",         # Gatsby SSG (under Meta)
    "https://vercel.com/": "ssr",          # replaced create-react-app.dev (drifted to ambiguous 2026-05-04 — its docs page leaned too thin)
    "https://nuxt.com/": "ssr",            # Nuxt 3 SSR (5th probe, redundancy)
}


def _independent_macro_classify(html: str) -> dict[str, Any]:
    """Macroscopic-property classification of an HTML body.

    INDEPENDENT from ``prerender._extract_signals`` — uses different regex
    patterns AND different thresholds. This is what makes
    ``meta_validate_golden_set`` non-tautological: if both the production
    classifier AND this validator drift in lockstep, the divergence
    triggers a flag (because they should agree on benchmarks but their
    independent paths catch each other).

    Heuristic thresholds are deliberately wider than the production
    classifier (>2KB visible text vs production's >500 chars) so that
    a marginal classification in production still validates here when
    the page is unambiguously one mode.

    Returns dict with: ``mode``, ``visible_text_chars``, ``head_signals``,
    ``debug`` for forensic inspection.
    """
    import re as _re

    # Independent visible-text extraction: strip script/style/template/svg
    # and tags. Different regex order than _extract_signals — strip order
    # matters because Vue/Svelte put template content INSIDE templates.
    stripped = _re.sub(r"<template\b[^>]*>.*?</template>", " ", html, flags=_re.DOTALL | _re.IGNORECASE)
    stripped = _re.sub(r"<script\b[^>]*>.*?</script\s*>", " ", stripped, flags=_re.DOTALL | _re.IGNORECASE)
    stripped = _re.sub(r"<style\b[^>]*>.*?</style\s*>", " ", stripped, flags=_re.DOTALL | _re.IGNORECASE)
    stripped = _re.sub(r"<svg\b[^>]*>.*?</svg>", " ", stripped, flags=_re.DOTALL | _re.IGNORECASE)
    stripped = _re.sub(r"<noscript\b[^>]*>.*?</noscript>", " ", stripped, flags=_re.DOTALL | _re.IGNORECASE)
    stripped = _re.sub(r"<[^>]+>", " ", stripped)
    stripped = _re.sub(r"\s+", " ", stripped).strip()
    text_chars = len(stripped)

    # Independent head-signal detection (different regex from production).
    has_title = bool(_re.search(r"<title\b[^>]*>\s*[^<\s][^<]*</title", html, _re.IGNORECASE))
    has_meta_desc = bool(_re.search(
        r"<meta\b[^>]*\bname\s*=\s*[\"']?description[\"']?[^>]*\bcontent\s*=\s*[\"'][^\"']+",
        html, _re.IGNORECASE,
    ))
    has_canonical = bool(_re.search(
        r"<link\b[^>]*\brel\s*=\s*[\"']?canonical[\"']?", html, _re.IGNORECASE,
    ))
    has_og = bool(_re.search(
        r"<meta\b[^>]*\bproperty\s*=\s*[\"']?og:", html, _re.IGNORECASE,
    ))
    head_signals = sum([has_title, has_meta_desc, has_canonical, has_og])

    # Macroscopic thresholds — wider than production. Disagreement vs
    # production = real signal that something rotated.
    SSR_TEXT_THRESHOLD = 2000      # production uses 500
    SHELL_TEXT_THRESHOLD = 300
    HEAD_SIGNALS_REQUIRED = 3      # title + meta_desc + (canonical OR og)

    if text_chars > SSR_TEXT_THRESHOLD and head_signals >= HEAD_SIGNALS_REQUIRED:
        mode = "ssr"
    elif head_signals >= HEAD_SIGNALS_REQUIRED and text_chars < SHELL_TEXT_THRESHOLD:
        mode = "head_only"
    elif head_signals < 2 and text_chars < SHELL_TEXT_THRESHOLD:
        mode = "csr"
    else:
        # Marginal — could be ssr-with-thin-content, or partial pre-render.
        # Fail open: report ambiguous so the operator sees the macro
        # numbers and decides.
        mode = "ambiguous"

    return {
        "mode": mode,
        "visible_text_chars": text_chars,
        "head_signals_count": head_signals,
        "debug": {
            "has_title": has_title,
            "has_meta_description": has_meta_desc,
            "has_canonical": has_canonical,
            "has_open_graph": has_og,
        },
    }


def meta_validate_golden_set() -> dict:
    """**Internal maintenance tool** — verifies the calibration golden set
    itself hasn't aged out.

    Different from ``calibration_check``: that one tests whether the
    PRODUCTION classifier (``prerender_signals``) still agrees with the
    benchmarks. THIS one tests whether the BENCHMARKS still represent
    what they claim, using a classifier that does NOT share regexes or
    thresholds with production.

    The two are complementary:

    - Both pass            → benchmark + classifier are aligned with reality.
    - Calibration fails, meta passes  → classifier regression. Fix code.
    - Calibration passes, meta fails  → classifier matches benchmark, but
                                        benchmark may be aligned with stale
                                        web behaviour. Investigate.
    - Both fail            → benchmark rot. Site rotated its stack. Refresh
                             the golden set, bump ``_GOLDEN_SET_VERSION``,
                             ship a release.

    This is the proactive guard against benchmark rot. The dev should run
    it monthly (or before each release) so the calibration fixture doesn't
    become a reliable false alarm. The result includes
    ``rotation_recommended`` per target so the dev knows exactly which
    entries to swap.

    Returns:
        ``targets`` — per-target {url, claimed_mode, observed_mode,
            agrees, rotation_recommended, observation_details}.
        ``benchmark_health`` — "fresh" / "partially_stale" / "stale".
        ``rotation_recommended_for`` — list of URLs to swap.
        ``golden_set_version`` — current version stamp.
    """
    import httpx as _httpx

    UA = (
        "Mozilla/5.0 (compatible; google-seo-mcp/0.8 meta-validator; "
        "+https://github.com/mario-hernandez/google-seo-mcp-claude-code)"
    )
    targets: list[dict[str, Any]] = []
    rotation_for: list[str] = []
    fetch_errors = 0
    headers = {"User-Agent": UA}

    for url, claimed in _GOLDEN_SET.items():
        try:
            with _httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as c:
                r = c.get(url)
                html = r.text
            obs = _independent_macro_classify(html)
            agrees = obs["mode"] == claimed
            if not agrees:
                rotation_for.append(url)
            targets.append({
                "url": url,
                "claimed_mode": claimed,
                "observed_mode": obs["mode"],
                "agrees": agrees,
                "rotation_recommended": not agrees,
                "observation_details": {
                    "visible_text_chars": obs["visible_text_chars"],
                    "head_signals_count": obs["head_signals_count"],
                    **obs["debug"],
                },
            })
        except Exception as e:
            fetch_errors += 1
            targets.append({
                "url": url,
                "claimed_mode": claimed,
                "observed_mode": "fetch_error",
                "agrees": False,
                "rotation_recommended": False,  # don't recommend swap on transient network error
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            })

    if fetch_errors == len(_GOLDEN_SET):
        benchmark_health = "unknown"
        recommendation = (
            "All probes failed with network errors — connectivity issue, "
            "not benchmark rot. Re-run when network recovers."
        )
    elif rotation_for:
        if len(rotation_for) >= len(_GOLDEN_SET) // 2:
            benchmark_health = "stale"
            recommendation = (
                f"{len(rotation_for)} of {len(_GOLDEN_SET)} benchmark targets "
                "no longer match their claimed mode. Refresh the golden set: "
                "investigate each `rotation_recommended_for` URL manually, "
                "swap or update its `claimed_mode`, bump `_GOLDEN_SET_VERSION` "
                "to the next quarter, document in CHANGELOG, and ship."
            )
        else:
            benchmark_health = "partially_stale"
            recommendation = (
                f"{len(rotation_for)} target(s) drifted: {rotation_for}. "
                "Most of the set is still valid. Swap the drifted entries, "
                "bump version, ship a patch release."
            )
    else:
        benchmark_health = "fresh"
        recommendation = (
            "All targets agree with their claimed mode under the independent "
            "macroscopic classifier. Benchmark is still representative. "
            "Re-run in ~3 months."
        )

    return with_meta(
        {
            "targets": targets,
            "summary": {
                "total": len(_GOLDEN_SET),
                "agreed": sum(1 for t in targets if t.get("agrees")),
                "drifted": len(rotation_for),
                "fetch_errors": fetch_errors,
            },
            "benchmark_health": benchmark_health,
            "rotation_recommended_for": rotation_for,
            "recommendation": recommendation,
            "golden_set_version": _GOLDEN_SET_VERSION,
        },
        source="migration.meta_validate_golden_set",
        extra={"golden_set_version": _GOLDEN_SET_VERSION},
    )


def calibration_check(extra_targets: dict[str, str] | None = None) -> dict:
    """Run ``prerender_signals`` against a curated set of public sites with
    known prerender behaviour, to verify the detector is actually working
    before you base cutover decisions on its output.

    Use this BEFORE a high-stakes forensic audit. If the detector mis-classifies
    nextjs.org as something other than ``ssr``, the regex/parser has drifted
    against current web layout — DO NOT trust the rest of the audit until it's
    fixed.

    The default golden set covers the three modes the tool distinguishes:

    - ``ssr``        — Next.js / Cloudflare / official React docs (Gatsby SSG)
    - ``head_only``  — a deliberately client-rendered SPA exposing only
                       meta/og pre-injected. Uses a known public sample.
    - ``csr``        — a pure CSR demo page.

    A pass means: every site classifies as expected → instrument is calibrated.
    A fail means: at least one site mis-classifies → either the detector has
    drifted OR the benchmark has aged out. The response includes
    ``golden_set_version`` (e.g. ``"2026-Q2"``); compare against the latest
    release CHANGELOG to tell which it is. If the benchmark has rotated since
    your version, upgrade the MCP. If versions match and probes still fail,
    the detector has a real regression — file an issue.

    Args:
        extra_targets: optional ``{url: expected_mode}`` to extend the golden
            set with your own curated controls (e.g. add staging sites whose
            mode you've verified manually). Recommended: pin a couple of YOUR
            sites with known behaviour as a sanity check independent of the
            public benchmarks.

    Returns:
        ``results`` — per-target {url, expected, got, pass, sample_signals}
        ``all_pass`` — bool. True iff every target classified correctly.
        ``instrument_status`` — "calibrated" / "drift_detected" / "partial"
        ``recommendation`` — human-readable next action when not calibrated.
        ``golden_set_version`` — version stamp of the bundled benchmark, so
            an operator can tell whether a failure is from instrument drift
            or from stale benchmarks.
    """
    GOLDEN_SET: dict[str, str] = dict(_GOLDEN_SET)  # copy so extras don't mutate the module-level set
    if extra_targets:
        GOLDEN_SET.update(extra_targets)

    results = []
    passes = 0
    fails = 0
    errors = 0
    for url, expected in GOLDEN_SET.items():
        try:
            sig = pr.prerender_signals(url)
            got = sig.get("prerender_mode", "unknown")
            ok = got == expected
            results.append({
                "url": url,
                "expected": expected,
                "got": got,
                "pass": ok,
                "health": sig.get("health"),
                "viability_score": sum(
                    1 for v in (sig.get("prerender_mode_viability") or {}).values()
                    if v is True
                ),
            })
            if ok:
                passes += 1
            else:
                fails += 1
        except Exception as e:
            errors += 1
            results.append({
                "url": url,
                "expected": expected,
                "got": "error",
                "pass": False,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            })

    total = len(results)
    if errors == total:
        status = "drift_detected"
        recommendation = (
            "Every probe failed with an exception — connectivity issue or major "
            "regex/parser drift. Check internet access from this machine, then "
            "re-run. If errors persist, file an issue with the exception message."
        )
    elif fails > 0 or errors > 0:
        status = "drift_detected"
        recommendation = (
            f"{fails + errors} of {total} probes mis-classified or errored. "
            "TWO possible causes — check both before assuming a real bug:\n"
            "  (1) **Benchmark rot**: the public targets in the golden set "
            f"(version {_GOLDEN_SET_VERSION}) may have rotated their stack. "
            "Vercel/Cloudflare swap RSC/streaming/ISR every few quarters. "
            "If your installed version is older than the latest CHANGELOG, "
            "upgrade the MCP — a fresh benchmark may already exist.\n"
            "  (2) **Detector drift**: if you're on the latest version and "
            "calibration still fails, the prerender_signals classification "
            "logic has a real regression. Open an issue with the per-probe "
            "results below — DO NOT run forensic audits until fixed. "
            "Re-check `_extract_signals` and the prerender_mode rules in "
            "src/google_seo_mcp/migration/prerender.py."
        )
    elif passes == total:
        status = "calibrated"
        recommendation = (
            "All probes classified as expected. Detector is calibrated — "
            "forensic audits can proceed."
        )
    else:
        status = "partial"
        recommendation = "Mixed results — review per-probe details."

    return with_meta(
        {
            "results": results,
            "summary": {
                "total": total,
                "pass": passes,
                "fail": fails,
                "error": errors,
            },
            "all_pass": fails == 0 and errors == 0,
            "instrument_status": status,
            "recommendation": recommendation,
            "golden_set_version": _GOLDEN_SET_VERSION,
            "golden_set_targets": list(_GOLDEN_SET.keys()),
        },
        source="migration.calibration_check",
        extra={"golden_set_version": _GOLDEN_SET_VERSION},
    )


def prerender_check_batch(urls: list[str], concurrency: int = 8) -> dict:
    """Run ``prerender_check`` over a list of URLs in parallel.

    For multi-URL audits (e.g. confirming every page of a freshly-deployed
    site is properly pre-rendered before flipping DNS), serialised calls take
    minutes — most of it network wait. This runs them concurrently with a
    rate-limit and returns a per-URL result list plus a summary the agent
    can read in a single glance to decide "is the site ready to ship?".

    Args:
        urls: list of URLs to audit. Each is fetched without executing JS
            and run through the full ``prerender_signals`` analysis.
        concurrency: max parallel HTTP fetches. Default 8 is a polite ceiling
            for a single origin under your control. Bump to 16 on a CDN.

    Returns:
        ``results``: list of per-URL outputs (same shape as ``prerender_check``).
        ``summary``: aggregate counts so the agent can branch on a single
            field — ``ssr``/``head_only``/``csr``/``unknown``/``errors``,
            plus convenience flags ``any_red``, ``any_head_only``, ``all_ssr``.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: list[dict] = []
    errors_count = 0

    def _one(u: str) -> dict:
        try:
            return pr.prerender_signals(u)
        except Exception as e:
            return {
                "url": u,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
                "prerender_mode": "unknown",
                "health": "red",
            }

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {pool.submit(_one, u): u for u in urls}
        for fut in as_completed(futures):
            results.append(fut.result())

    # Preserve input order in the output (futures complete out of order).
    by_url = {r.get("url") or futures_url: r for r, futures_url in zip(results, urls)}
    ordered = [by_url.get(u, {"url": u, "error": "missing"}) for u in urls]

    mode_counts = {"ssr": 0, "head_only": 0, "csr": 0, "unknown": 0}
    health_counts = {"green": 0, "amber": 0, "red": 0}
    for r in ordered:
        mode = r.get("prerender_mode", "unknown")
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        h = r.get("health", "red")
        health_counts[h] = health_counts.get(h, 0) + 1
        if "error" in r:
            errors_count += 1

    summary = {
        "total": len(urls),
        **mode_counts,
        "errors": errors_count,
        "health_green": health_counts.get("green", 0),
        "health_amber": health_counts.get("amber", 0),
        "health_red": health_counts.get("red", 0),
        "any_red": health_counts.get("red", 0) > 0,
        "any_head_only": mode_counts.get("head_only", 0) > 0,
        "all_ssr": mode_counts.get("ssr", 0) == len(urls),
    }

    return with_meta(
        {"results": ordered, "summary": summary},
        source="migration.prerender_check_batch",
        extra={"concurrency": concurrency},
    )


def prerender_vs_hydrated(url: str, wait_ms: int = 2000) -> dict:
    """Compare pre-rendered HTML (no JS) vs DOM after hydration.

    Detects: content-only-after-JS, schema-injected-by-client, title set
    only after hydration. Critical for verifying SSR quality. Uses Playwright;
    install with `pip install playwright && playwright install chromium`.
    """
    return with_meta(
        pr.prerender_vs_hydrated(url, wait_ms=wait_ms),
        source="migration.prerender_vs_hydrated",
        site_url=url,
    )


def googlebot_diff(url: str) -> dict:
    """Diff HTML served to Googlebot UA vs to a normal user UA.

    Detects accidental cloaking, WAF interference, A/B tests targeting bots,
    and schema differences between bot and human. Critical-severity findings
    are real ranking risks.
    """
    return with_meta(ck.googlebot_diff(url), source="migration.googlebot_diff", site_url=url)


def multi_bot_diff(url: str) -> dict:
    """Diff HTML served to Googlebot, Bingbot, and a normal user. Three-way."""
    return with_meta(ck.multi_bot_diff(url), source="migration.multi_bot_diff", site_url=url)


def verify_googlebot_ip(ip: str) -> dict:
    """Verify a server-log IP is a legitimate Googlebot via reverse-DNS check.

    Per Google's official guidance: legitimate Googlebot IPs reverse-DNS to
    *.googlebot.com / *.google.com, and that hostname forward-DNS-es back
    to the same IP. Use this to filter your access logs / bot detection.
    """
    return with_meta(ck.verify_googlebot_ip(ip), source="migration.verify_googlebot_ip")


# ─── Sitemap diff / migration redirects ──────────────────────

def sitemap_diff(old_sitemap_url: str, new_sitemap_url: str) -> dict:
    """Compare two sitemaps. Returns added / removed / common URL counts + samples.

    Use during/after migration: confirm the new site exposes everything the
    old one did. Missing URLs need explicit 301 redirects.
    """
    return with_meta(
        sd.sitemap_diff(old_sitemap_url, new_sitemap_url),
        source="migration.sitemap_diff",
    )


def sitemap_validate(sitemap_url: str, sample_size: int = 50) -> dict:
    """Parse a sitemap and HEAD-check a sample of URLs.

    Returns status code distribution (2xx / 3xx / 4xx / 5xx / error) plus a
    list of failures. Run on a freshly deployed sitemap to catch dead links
    before Googlebot does.
    """
    return with_meta(
        sd.sitemap_validate(sitemap_url, sample_size=sample_size),
        source="migration.sitemap_validate",
    )


def migration_redirects_plan(
    old_urls: list[str],
    new_urls: list[str],
    min_score: float = 70.0,
) -> dict:
    """Suggest 301 redirect mappings from old URLs to new URLs.

    Strategy: exact-path match first, then fuzzy slug-similarity (rapidfuzz
    Jaro-Winkler / token_set_ratio). Below `min_score` (0-100), URLs are
    flagged as unmatched for manual review.

    Useful inputs come from `sitemap_diff(...)["only_in_old_sample"]` and
    `parse_sitemap(new_sitemap_url)`.
    """
    plan = rp.migration_redirects_plan(old_urls, new_urls, min_score=min_score)
    return with_meta(plan, source="migration.migration_redirects_plan")


def export_redirects_nginx(plan: list[dict]) -> dict:
    """Render a redirects plan as Nginx 301 rules text."""
    return with_meta(
        {"nginx_config": rp.export_redirects_nginx(plan)},
        source="migration.export_redirects_nginx",
    )


def export_redirects_apache(plan: list[dict]) -> dict:
    """Render a redirects plan as Apache .htaccess 301 rules text."""
    return with_meta(
        {"apache_config": rp.export_redirects_apache(plan)},
        source="migration.export_redirects_apache",
    )


def export_redirects_cloudflare(plan: list[dict]) -> dict:
    """Render a redirects plan as Cloudflare Bulk Redirects JSON list."""
    return with_meta(
        {"cloudflare_rules": rp.export_redirects_cloudflare(plan)},
        source="migration.export_redirects_cloudflare",
    )


# ─── SEO equity report (composer) ────────────────────────────

def seo_equity_report(
    wp_url: str,
    gsc_site_url: str | None = None,
    days: int = 90,
    max_pages: int = 200,
) -> dict:
    """The killer composer. Builds a complete SEO equity report combining
    WP REST inventory + advertools crawl + GSC clicks/impressions + internal
    link graph + plugin redirects.

    Each URL gets a 0-100 equity score and a classification:
      - MUST_PRESERVE (≥70)
      - WORTH_PRESERVING (30-69)
      - LOW_VALUE (1-29)
      - DEPRECATE (0)

    Use this BEFORE migrating from WordPress to a new stack — gives you the
    list of URLs that absolutely need redirects, plus what can be deprecated
    without ranking loss.
    """
    return with_meta(
        er.build_equity_report(wp_url, gsc_site_url=gsc_site_url, days=days, max_pages=max_pages),
        source="migration.seo_equity_report",
        site_url=wp_url,
    )


# ─── v0.4.0 additions ─────────────────────────────────────────

def wayback_baseline(
    origin_url: str,
    snapshot_date: str | None = None,
    max_urls: int = 500,
) -> dict:
    """Anchor what the public archive saw BEFORE migration.

    Step 1 of any migration workflow. Queries the Internet Archive's CDX API
    (free, no key) and returns the inventory of HTML snapshots Google /
    archivists captured for this origin. Use the returned ``anchor_url`` as
    a public reference 6 months later if traffic drops are blamed on
    something else.
    """
    return with_meta(
        wb.wayback_baseline(origin_url, snapshot_date=snapshot_date, max_urls=max_urls),
        source="migration.wayback_baseline",
        site_url=origin_url,
    )


def schema_parity_check(old_url: str, new_url: str) -> dict:
    """Compare JSON-LD schema between an old (WP) URL and new (SSR) URL.

    Reports types missing on the new side, types added, and lost critical
    properties (e.g. Article.headline, Product.offers). Returns a
    ``parity_score`` 0..1 and a severity (ok / warning / critical). Catch
    rich-result regressions BEFORE Google reindexes.
    """
    return with_meta(
        sp.schema_parity_check(old_url, new_url),
        source="migration.schema_parity_check",
    )


def hreflang_cluster_audit(
    cluster: dict | None = None,
    urls_es: list[str] | None = None,
    urls_fr: list[str] | None = None,
) -> dict:
    """Verify hreflang reciprocity across a multi-language URL cluster.

    Each URL in the cluster must self-reference, list all siblings with
    correct hreflang, and agree on x-default. Works across domains too
    (e.g. example.com ES ↔ example.org FR).

    Pass ``cluster={"es-ES": [...], "fr-FR": [...]}`` (preferred), or use
    the legacy ``urls_es=..., urls_fr=...`` shortcut.
    """
    return with_meta(
        hl.hreflang_cluster_audit(cluster=cluster, urls_es=urls_es, urls_fr=urls_fr),
        source="migration.hreflang_cluster_audit",
    )


def indexation_recovery_monitor(
    site_url: str,
    urls: list[str],
    days_after_launch: int | None = None,
    pause_ms: int = 100,
) -> dict:
    """Inspect post-migration URLs via GSC URL Inspection API.

    Calls ``gsc_inspect_url`` per URL and aggregates results into categories
    (INDEXED / DISCOVERED / SOFT_404 / BLOCKED / ERROR / UNKNOWN). Returns
    an ``indexation_rate`` and a ``health`` of green / amber / red. Use 14
    and 30 days after launch to track recovery.
    """
    return with_meta(
        ix.indexation_recovery_monitor(
            site_url, urls, days_after_launch=days_after_launch, pause_ms=pause_ms,
        ),
        source="migration.indexation_recovery_monitor",
        site_url=site_url,
    )
