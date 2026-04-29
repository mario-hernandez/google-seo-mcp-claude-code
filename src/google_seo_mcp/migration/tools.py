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
