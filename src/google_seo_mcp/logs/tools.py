"""Log analysis tools registered with the MCP server.

Three layers of log work:
  1. Parse local file → normalised rows (parse_log_file).
  2. Aggregate (crawl_budget, bot_ratio, spider_traps, crawl_waste, status_distribution).
  3. Verify a specific IP is real Googlebot via rDNS (verify_googlebot_ip).
"""
from __future__ import annotations

from typing import Any

from ..guardrails import with_meta
from . import (
    bot_ratio,
    crawl_budget,
    crawl_waste,
    parse_log_file,
    spider_traps,
    status_distribution,
    verify_googlebot_ip,
)


def logs_parse(path: str, fmt: str = "auto", max_rows: int = 1_000_000) -> dict:
    """Parse an access log file into normalised records.

    Supports NCSA / Apache / Nginx Combined Log Format and JSON
    (Cloudflare Logpush, Fastly, structured logs). Auto-sniffs the format
    from the first non-empty line. Plain text or .gz both work.

    Returns ``{rows: [...], skipped: int, fmt_detected: ..., row_count}``.
    Use the ``rows`` output as input for the aggregator tools below.

    Args:
        path: local file path (download Cloudflare Logpush bundles first).
        fmt: "auto" (default) | "combined" | "json".
        max_rows: cap to avoid OOM (default 1M ≈ 100-300 MB log).
    """
    return with_meta(
        parse_log_file(path, fmt=fmt, max_rows=max_rows),
        source="logs.parse_log_file",
        extra={"path": path},
    )


def logs_googlebot_crawl_budget(rows: list[dict]) -> dict:
    """Per-URL Googlebot crawl frequency from parsed log rows.

    Surfaces top URLs Googlebot is hitting + their status mix + last-seen
    timestamp + URLs rarely crawled (≤2 hits in the period).

    Args:
        rows: output of ``logs_parse(...)["data"]["rows"]``.
    """
    return with_meta(crawl_budget(rows), source="logs.crawl_budget")


def logs_bot_ratio(rows: list[dict]) -> dict:
    """Distribution of UA classes: Googlebot vs Bingbot vs ClaudeBot vs
    GPTBot vs PerplexityBot vs CCBot vs Bytespider vs humans vs unknown.

    The 2026 question: how much of your bandwidth is feeding LLM training
    (CCBot, Bytespider, GPTBot) vs actual indexing (Googlebot, Bingbot)?
    """
    return with_meta(bot_ratio(rows), source="logs.bot_ratio")


def logs_spider_trap_detector(rows: list[dict], threshold: int = 100) -> dict:
    """URLs Googlebot revisits excessively (default ≥100 hits in period).

    Common offenders: ``/calendar/2026/04/29/``, faceted nav with
    ``?color=red&size=M&sort=...`` combinations, infinite pagination.
    Each trap costs crawl budget that should be spent on indexable pages.
    """
    return with_meta(
        spider_traps(rows, threshold=threshold),
        source="logs.spider_traps",
    )


def logs_crawl_waste(rows: list[dict], sitemap_urls: list[str]) -> dict:
    """URLs Googlebot is crawling that are NOT in your sitemap.

    These are orphans + taxonomy pages + parameter URLs eating crawl
    budget. Pair with ``migration_sitemap_diff`` to feed the sitemap_urls.
    """
    return with_meta(
        crawl_waste(rows, sitemap_urls),
        source="logs.crawl_waste",
    )


def logs_status_distribution(rows: list[dict]) -> dict:
    """HTTP status code mix for Googlebot vs everyone else.

    A 5xx storm against Googlebot during a deploy de-indexes pages within
    48h. This tool surfaces it from the logs alone.
    """
    return with_meta(status_distribution(rows), source="logs.status_distribution")


def logs_verify_googlebot_ip(ip: str) -> dict:
    """rDNS check that an IP is a real Googlebot (forward+reverse DNS).

    UA-only Googlebot detection is spoofed by 90% of malicious bots. The
    only definitive check is: reverse-DNS the IP, get hostname under
    ``*.google.com`` / ``*.googlebot.com``, then forward-DNS that hostname
    and confirm it returns the same IP.
    """
    return with_meta(verify_googlebot_ip(ip), source="logs.verify_googlebot_ip")
