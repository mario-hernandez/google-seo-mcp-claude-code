"""Server access log analysis — what Googlebot is really crawling.

Reads NCSA / Combined / JSON / Cloudflare Logpush formats. The MCP only
needs a parser; the logs themselves are local files. Cero coste API.

This is the layer GSC URL Inspection cannot reach: real Googlebot crawl
frequency per URL, spider traps, soft-404s cross-referenced with GSC,
crawl waste (URLs hit but not in sitemap), bot-vs-human ratio.
"""
from __future__ import annotations

import gzip
import json
import re
import socket
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

# Combined / NCSA Common log line:
# 1.2.3.4 - - [29/Apr/2026:10:00:00 +0000] "GET /path HTTP/1.1" 200 1234 "ref" "ua"
_COMBINED_RE = re.compile(
    r'(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<ts>[^\]]+)\]\s+'
    r'"(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+HTTP/[\d.]+"\s+'
    r'(?P<status>\d+)\s+(?P<bytes>\d+|-)'
    r'(?:\s+"(?P<ref>[^"]*)"\s+"(?P<ua>[^"]*)")?'
)


def _parse_combined_line(line: str) -> dict[str, Any] | None:
    m = _COMBINED_RE.match(line)
    if not m:
        return None
    d = m.groupdict()
    try:
        ts = datetime.strptime(d["ts"].split(" ")[0], "%d/%b/%Y:%H:%M:%S")
    except ValueError:
        ts = None
    bytes_val = d["bytes"]
    return {
        "ip": d["ip"],
        "ts": ts.isoformat() if ts else d["ts"],
        "method": d["method"],
        "path": d["path"],
        "status": int(d["status"]),
        "bytes": int(bytes_val) if bytes_val and bytes_val != "-" else 0,
        "referer": d.get("ref") or "",
        "user_agent": d.get("ua") or "",
    }


def _parse_json_line(line: str) -> dict[str, Any] | None:
    """Cloudflare Logpush + many JSON access logs.

    Maps common field names to our normalised shape. Cloudflare uses
    ``ClientRequestPath`` / ``EdgeStartTimestamp`` / ``ClientIP``;
    custom JSON logs vary — we try several aliases.
    """
    try:
        d = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(d, dict):
        return None
    ts = (
        d.get("EdgeStartTimestamp") or d.get("timestamp")
        or d.get("ts") or d.get("@timestamp")
    )
    return {
        "ip": d.get("ClientIP") or d.get("ip") or d.get("remote_addr") or "",
        "ts": str(ts) if ts is not None else "",
        "method": d.get("ClientRequestMethod") or d.get("method") or d.get("request_method") or "GET",
        "path": d.get("ClientRequestPath") or d.get("path") or d.get("request_uri") or "/",
        "status": int(d.get("EdgeResponseStatus") or d.get("status") or d.get("response_status") or 0),
        "bytes": int(d.get("EdgeResponseBytes") or d.get("bytes") or d.get("body_bytes_sent") or 0),
        "referer": d.get("ClientRequestReferer") or d.get("referer") or "",
        "user_agent": d.get("ClientRequestUserAgent") or d.get("user_agent") or d.get("http_user_agent") or "",
    }


def _open_log(path: str | Path) -> Iterable[str]:
    """Open a log file (plain text or .gz) and yield lines."""
    p = Path(path)
    if str(p).endswith(".gz"):
        with gzip.open(p, "rt", errors="replace") as f:
            for ln in f:
                yield ln.rstrip("\n")
    else:
        with open(p, errors="replace") as f:
            for ln in f:
                yield ln.rstrip("\n")


def parse_log_file(
    path: str | Path,
    fmt: str = "auto",
    max_rows: int = 1_000_000,
) -> dict[str, Any]:
    """Parse a server log file into normalised records.

    Args:
        path: local file (.log or .log.gz). Cloudflare Logpush bundles in
            R2/S3 should be downloaded first.
        fmt: ``"auto"`` (sniff first non-empty line), ``"combined"`` (NCSA /
            Apache / Nginx default), or ``"json"`` (Cloudflare Logpush /
            structured JSON).
        max_rows: cap to avoid OOM. 1M rows ≈ 100-300 MB log.

    Returns ``{"rows": [...], "skipped": int, "fmt_detected": str, "path": ...}``.
    """
    rows: list[dict[str, Any]] = []
    skipped = 0
    detected = fmt
    parser = None

    for ln in _open_log(path):
        if not ln.strip():
            continue
        if parser is None:
            # Sniff format from first non-empty line
            if fmt == "auto":
                if ln.lstrip().startswith("{"):
                    detected = "json"
                else:
                    detected = "combined"
            parser = _parse_json_line if detected == "json" else _parse_combined_line

        rec = parser(ln)
        if rec is None:
            skipped += 1
            continue
        rows.append(rec)
        if len(rows) >= max_rows:
            break

    return {
        "path": str(path),
        "fmt_detected": detected,
        "row_count": len(rows),
        "skipped": skipped,
        "rows": rows,
    }


# ── Googlebot verification ──────────────────────────────────────────

_GOOGLEBOT_UA_RE = re.compile(r"\bGooglebot\b|AdsBot|Mediapartners-Google", re.IGNORECASE)


def is_googlebot_ua(ua: str) -> bool:
    return bool(_GOOGLEBOT_UA_RE.search(ua or ""))


def verify_googlebot_ip(ip: str) -> dict[str, Any]:
    """rDNS check that an IP is a real Googlebot.

    Real Googlebots reverse-DNS to ``*.google.com`` / ``*.googlebot.com``,
    and that hostname forward-DNS-es back to the same IP. UA-only checks
    are spoofed by 90% of malicious bots.
    """
    out: dict[str, Any] = {"ip": ip, "is_googlebot": False, "details": {}}
    try:
        host, _, _ = socket.gethostbyaddr(ip)
        out["details"]["hostname"] = host
    except (socket.herror, socket.gaierror) as e:
        out["details"]["error"] = f"reverse-DNS failed: {e}"
        return out
    if not (host.endswith(".googlebot.com") or host.endswith(".google.com")):
        out["details"]["reason"] = f"Hostname {host!r} not under googlebot.com / google.com"
        return out
    try:
        forward = socket.gethostbyname(host)
        out["details"]["forward_ip"] = forward
    except socket.gaierror as e:
        out["details"]["forward_dns_error"] = str(e)
        return out
    if forward != ip:
        out["details"]["reason"] = f"Forward DNS mismatch: {forward} != {ip}"
        return out
    out["is_googlebot"] = True
    return out


# ── Aggregations ────────────────────────────────────────────────────

def crawl_budget(rows: list[dict], days: int | None = None) -> dict[str, Any]:
    """Per-URL Googlebot crawl frequency + status distribution.

    Returns top URLs by Googlebot hits, infrequent crawls, status code mix.
    """
    by_path: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not is_googlebot_ua(r.get("user_agent", "")):
            continue
        path = r.get("path", "/")
        d = by_path.setdefault(path, {"hits": 0, "by_status": {}, "last_seen": None})
        d["hits"] += 1
        st = str(r.get("status", 0))
        d["by_status"][st] = d["by_status"].get(st, 0) + 1
        ts = r.get("ts")
        if ts and (d["last_seen"] is None or ts > d["last_seen"]):
            d["last_seen"] = ts
    ranked = sorted(by_path.items(), key=lambda x: x[1]["hits"], reverse=True)
    return {
        "total_googlebot_hits": sum(d["hits"] for _, d in ranked),
        "unique_paths_crawled": len(ranked),
        "top_crawled": [{"path": p, **d} for p, d in ranked[:50]],
        "rarely_crawled": [
            {"path": p, **d} for p, d in ranked if d["hits"] <= 2
        ][:50],
    }


def bot_ratio(rows: list[dict]) -> dict[str, Any]:
    """Distribution of UA patterns: Googlebot, Bingbot, ClaudeBot, GPTBot,
    PerplexityBot, CCBot, Bytespider, humans, unknown."""
    patterns = {
        "Googlebot": re.compile(r"\bGooglebot\b|AdsBot|Mediapartners-Google", re.I),
        "Bingbot": re.compile(r"\bbingbot\b", re.I),
        "ClaudeBot": re.compile(r"ClaudeBot|Claude-Web|anthropic-ai", re.I),
        "GPTBot": re.compile(r"GPTBot|ChatGPT-User|OAI-SearchBot", re.I),
        "PerplexityBot": re.compile(r"PerplexityBot|Perplexity-User", re.I),
        "CCBot": re.compile(r"\bCCBot\b", re.I),
        "Bytespider": re.compile(r"Bytespider", re.I),
        "FacebookBot": re.compile(r"FacebookBot|Meta-ExternalAgent", re.I),
        "Yandex": re.compile(r"YandexBot", re.I),
        "DuckDuckBot": re.compile(r"DuckDuckBot", re.I),
    }
    counts = {k: 0 for k in patterns}
    counts["human_like"] = 0
    counts["unknown"] = 0
    for r in rows:
        ua = r.get("user_agent", "")
        matched = False
        for name, pat in patterns.items():
            if pat.search(ua):
                counts[name] += 1
                matched = True
                break
        if not matched:
            if "Mozilla" in ua:
                counts["human_like"] += 1
            else:
                counts["unknown"] += 1
    total = sum(counts.values())
    return {
        "total_requests": total,
        "by_user_agent_class": counts,
        "by_user_agent_class_pct": {
            k: round(v / total * 100, 2) if total else 0 for k, v in counts.items()
        },
    }


def spider_traps(rows: list[dict], threshold: int = 100) -> dict[str, Any]:
    """Detect URLs revisited many times in the period — calendar traps,
    faceted nav explosions, infinite paginations.

    A URL hit ``threshold``+ times is flagged. Returns top offenders.
    """
    by_path: dict[str, int] = {}
    for r in rows:
        if not is_googlebot_ua(r.get("user_agent", "")):
            continue
        by_path[r.get("path", "/")] = by_path.get(r.get("path", "/"), 0) + 1
    traps = [(p, c) for p, c in by_path.items() if c >= threshold]
    traps.sort(key=lambda x: x[1], reverse=True)
    return {
        "threshold": threshold,
        "trap_count": len(traps),
        "traps": [{"path": p, "googlebot_hits": c} for p, c in traps[:50]],
    }


def crawl_waste(rows: list[dict], sitemap_urls: list[str], origin: str = "") -> dict[str, Any]:
    """URLs Googlebot is crawling that are NOT in the sitemap.

    These are crawl-budget waste (orphans, taxonomy pages, parameter URLs).
    Pair with ``sitemap_diff`` output: the ``urls`` arg should be the result
    of ``parse_sitemap``.
    """
    sitemap_set = set()
    for u in sitemap_urls:
        # Normalise: keep only path
        if u.startswith("http"):
            from urllib.parse import urlparse
            sitemap_set.add(urlparse(u).path.rstrip("/") or "/")
        else:
            sitemap_set.add(u.rstrip("/") or "/")

    crawled_paths: dict[str, int] = {}
    for r in rows:
        if not is_googlebot_ua(r.get("user_agent", "")):
            continue
        path = r.get("path", "/").split("?")[0].rstrip("/") or "/"
        crawled_paths[path] = crawled_paths.get(path, 0) + 1

    waste = [
        {"path": p, "googlebot_hits": c}
        for p, c in crawled_paths.items() if p not in sitemap_set
    ]
    waste.sort(key=lambda x: x["googlebot_hits"], reverse=True)

    return {
        "sitemap_url_count": len(sitemap_set),
        "crawled_url_count": len(crawled_paths),
        "wasted_url_count": len(waste),
        "wasted_hits_total": sum(w["googlebot_hits"] for w in waste),
        "top_wasted": waste[:50],
    }


def status_distribution(rows: list[dict]) -> dict[str, Any]:
    """Status code mix per UA class. Detects 5xx storms hitting Googlebot."""
    by_class_status: dict[str, dict[str, int]] = {}
    for r in rows:
        ua = r.get("user_agent", "")
        cls = "Googlebot" if is_googlebot_ua(ua) else "other"
        st = str(r.get("status", 0))
        d = by_class_status.setdefault(cls, {})
        d[st] = d.get(st, 0) + 1
    return {"by_class": by_class_status}
