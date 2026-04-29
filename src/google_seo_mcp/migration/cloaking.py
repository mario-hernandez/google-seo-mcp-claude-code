"""Cloaking / Googlebot UA diff detection.

Compares HTML served to Googlebot vs to a normal user. Detects accidental
cloaking (Cloudflare WAF blocking bots, A/B test active in bots only,
schema only in one variant, etc.).
"""
from __future__ import annotations

import socket
from typing import Any

from .prerender import _extract_signals, fetch_as

GOOGLEBOT_UA = (
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; "
    "Googlebot/2.1; +http://www.google.com/bot.html) "
    "Chrome/W.X.Y.Z Safari/537.36"
)
USER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
BINGBOT_UA = (
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; "
    "bingbot/2.0; +http://www.bing.com/bingbot.htm) Chrome/116.0.0.0 Safari/537.36"
)


def verify_googlebot_ip(ip: str) -> dict[str, Any]:
    """Reverse-DNS check that an IP is actually a legitimate Googlebot.

    Google's official guidance: a legitimate Googlebot's IP must reverse-DNS
    to *.googlebot.com or *.google.com, and that hostname must forward-DNS
    back to the same IP.
    """
    out: dict[str, Any] = {"ip": ip, "is_googlebot": False, "details": {}}
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        out["details"]["hostname"] = hostname
    except (socket.herror, socket.gaierror) as e:
        out["details"]["error"] = f"reverse-DNS failed: {e}"
        return out

    if not (hostname.endswith(".googlebot.com") or hostname.endswith(".google.com")):
        out["details"]["reason"] = (
            f"Hostname {hostname!r} does not end with .googlebot.com or .google.com"
        )
        return out

    try:
        forward_ip = socket.gethostbyname(hostname)
        out["details"]["forward_ip"] = forward_ip
    except socket.gaierror as e:
        out["details"]["forward_dns_error"] = str(e)
        return out

    if forward_ip != ip:
        out["details"]["reason"] = f"Forward DNS mismatch: {forward_ip} != {ip}"
        return out

    out["is_googlebot"] = True
    return out


def googlebot_diff(url: str) -> dict[str, Any]:
    """Fetch URL with Googlebot UA and normal-user UA, diff the SEO signals.

    Reports differences in title/meta/canonical/JSON-LD count/HTML size, and
    flags severity. A critical finding is title or schema differing — that's
    accidental cloaking that ranks-killing.
    """
    bot_html = fetch_as(url, GOOGLEBOT_UA)
    user_html = fetch_as(url, USER_UA)

    bot_sig = _extract_signals(bot_html, url)
    user_sig = _extract_signals(user_html, url)

    diffs: dict[str, Any] = {}
    for k in (
        "title", "meta_description", "canonical",
        "og_count", "twitter_count", "jsonld_blocks",
        "p_tag_count", "hreflang_count",
    ):
        if bot_sig.get(k) != user_sig.get(k):
            diffs[k] = {"googlebot": bot_sig.get(k), "user": user_sig.get(k)}

    size_a = bot_sig["html_size_bytes"]
    size_b = user_sig["html_size_bytes"]
    size_pct = abs(size_a - size_b) / max(size_a, size_b, 1) * 100

    severity = "ok"
    notes: list[str] = []
    if size_pct > 20:
        severity = "warning"
        notes.append(
            f"HTML size differs by {size_pct:.1f}% — possible cloaking, A/B test, or WAF interference"
        )
    if diffs.get("jsonld_blocks"):
        severity = "critical"
        notes.append(
            "JSON-LD schema count differs between bot and user — Googlebot may not see your structured data"
        )
    if any(diffs.get(k) for k in ("title", "meta_description", "canonical")):
        severity = "critical"
        notes.append("Critical SEO meta differs — likely accidental cloaking")
    if not notes:
        notes.append("No significant differences detected.")

    return {
        "url": url,
        "differences": diffs,
        "html_size_delta_pct": round(size_pct, 1),
        "severity": severity,
        "notes": notes,
        "googlebot_signals": bot_sig,
        "user_signals": user_sig,
    }


def multi_bot_diff(url: str) -> dict[str, Any]:
    """Compare HTML served to Googlebot, Bingbot, and a normal user.

    Useful for sites that want to verify they don't favour Googlebot over
    other crawlers (which is itself a signal of cloaking).
    """
    googlebot = _extract_signals(fetch_as(url, GOOGLEBOT_UA), url)
    bingbot = _extract_signals(fetch_as(url, BINGBOT_UA), url)
    user = _extract_signals(fetch_as(url, USER_UA), url)

    sizes = {
        "googlebot": googlebot["html_size_bytes"],
        "bingbot": bingbot["html_size_bytes"],
        "user": user["html_size_bytes"],
    }
    max_size = max(sizes.values())
    min_size = min(sizes.values())
    spread_pct = (max_size - min_size) / max(max_size, 1) * 100

    notes: list[str] = []
    if spread_pct > 30:
        notes.append(
            f"HTML size differs by {spread_pct:.1f}% across UAs — investigate for differential serving"
        )

    return {
        "url": url,
        "html_sizes": sizes,
        "size_spread_pct": round(spread_pct, 1),
        "googlebot": googlebot,
        "bingbot": bingbot,
        "user": user,
        "notes": notes,
    }
