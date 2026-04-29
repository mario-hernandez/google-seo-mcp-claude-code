"""Cloaking / Googlebot UA diff detection — with 5 anti-false-positive guards.

Compares HTML served to Googlebot vs to a normal user. Detects accidental
cloaking (WAF blocking bots, A/B test active in bots only, schema only in
one variant).

The 5 anti-FP guards (avoiding the false-positive-storm typical of naive
cloaking detectors):

  G1. Entity-encoding equivalence — `&iquest;` vs `¿` are NOT cloaking. We
      decode HTML entities before comparing every textual field.
  G2. Cloudflare Bot Fight Mode — if status 503/403 with `cf-mitigated`
      header, the result is `inconclusive`, not `cloaking`. WAF blocking
      isn't the same as the server intentionally serving different content.
  G3. Vary header — if the response doesn't list `User-Agent` in `Vary`, the
      CDN can't legitimately differentiate by UA. We surface this as a
      caveat before flagging cloaking.
  G4. A/B test threshold — many sites legitimately A/B test layouts. We
      require >30% structural divergence AND missing critical meta to
      escalate; below that we report `warning`, not `critical`.
  G5. Cache miss vs hit — first request may hit cold cache, second warm. We
      double-fetch with 5s gap and inspect `cf-cache-status`; if the two
      responses diverge while cache state changes, we mark `cache_artifact`,
      not cloaking.
"""
from __future__ import annotations

import socket
import time
from typing import Any

from .prerender import _extract_signals, fetch_as_with_meta

# Mobile-first index has been the default since 2020. The bot UA we test
# against MUST be the smartphone variant — testing the desktop variant
# means testing the non-indexed copy. (Forensics review, P1.)
# Chrome major version is bumped periodically; W.X.Y.Z literal would be
# blocklisted by Cloudflare bot management as a spoof signature.
GOOGLEBOT_UA = (
    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.116 Mobile Safari/537.36 "
    "(compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)
GOOGLEBOT_DESKTOP_UA = (
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; "
    "Googlebot/2.1; +http://www.google.com/bot.html) "
    "Chrome/130.0.6723.116 Safari/537.36"
)
GOOGLEBOT_IMAGE_UA = (
    "Googlebot-Image/1.0"
)
GOOGLEBOT_NEWS_UA = (
    "Mozilla/5.0 (compatible; Googlebot-News; +http://www.google.com/bot.html)"
)
ADSBOT_UA = (
    "AdsBot-Google (+http://www.google.com/adsbot.html)"
)
ADSBOT_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.116 Mobile Safari/537.36 "
    "(compatible; AdsBot-Google-Mobile; +http://www.google.com/mobile/adsbot.html)"
)
USER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
BINGBOT_UA = (
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; "
    "bingbot/2.0; +http://www.bing.com/bingbot.htm) Chrome/116.0.0.0 Safari/537.36"
)
EMPTY_UA = "-"


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


def _meta_signature(sig: dict[str, Any]) -> tuple:
    """Stable hashable signature for cache-divergence detection.

    Includes meta_robots and the OG dict — high-value cloaking vectors
    (e.g. ``noindex`` injected only for users) that earlier versions missed.
    """
    og = sig.get("og") or {}
    og_frozen = tuple(sorted((og.items() if isinstance(og, dict) else [])))
    return (
        sig.get("title"),
        sig.get("meta_description"),
        sig.get("canonical"),
        sig.get("jsonld_blocks"),
        sig.get("og_count"),
        sig.get("html_size_bytes"),
        sig.get("meta_robots"),
        og_frozen,
    )


def _bfm_inconclusive(meta: dict[str, Any]) -> str | None:
    """G2: detect Cloudflare Bot Fight Mode interference."""
    if meta["status"] in (403, 503) and meta["cf"].get("mitigated"):
        return (
            f"Cloudflare Bot Fight Mode active (status={meta['status']}, "
            f"cf-mitigated={meta['cf'].get('mitigated')!r}). "
            "Result is INCONCLUSIVE, not cloaking — WAF is filtering the bot UA."
        )
    return None


def _vary_caveat(meta: dict[str, Any]) -> str | None:
    """G3: warn if Vary header doesn't include User-Agent."""
    vary = (meta["cf"].get("vary") or "").lower()
    if vary and "user-agent" not in vary:
        return (
            f"`Vary` header is {vary!r} (no User-Agent). The CDN cannot legitimately "
            "differentiate by UA — any divergence is suspicious."
        )
    return None


def googlebot_diff(url: str) -> dict[str, Any]:
    """Fetch URL with Googlebot UA and normal-user UA, diff the SEO signals.

    Reports differences in title/meta/canonical/JSON-LD count/HTML size, and
    flags severity. Applies the 5 anti-FP guards (see module docstring) so a
    `critical` verdict is genuine cloaking, not encoding-noise or WAF.
    """
    bot_meta = fetch_as_with_meta(url, GOOGLEBOT_UA)
    user_meta = fetch_as_with_meta(url, USER_UA)

    notes: list[str] = []
    fp_filters: list[str] = []

    # G2: Cloudflare BFM check (per UA)
    bfm_bot = _bfm_inconclusive(bot_meta)
    bfm_user = _bfm_inconclusive(user_meta)
    if bfm_bot or bfm_user:
        if bfm_bot:
            notes.append(bfm_bot)
            fp_filters.append("cloudflare_bfm_googlebot")
        if bfm_user:
            notes.append(bfm_user)
            fp_filters.append("cloudflare_bfm_user")
        return {
            "url": url,
            "severity": "inconclusive",
            "notes": notes,
            "fp_filters_applied": fp_filters,
            "googlebot_status": bot_meta["status"],
            "user_status": user_meta["status"],
            "cf": {"googlebot": bot_meta["cf"], "user": user_meta["cf"]},
        }

    # G3: Vary header caveat
    vary_warn = _vary_caveat(user_meta)
    if vary_warn:
        notes.append(vary_warn)

    bot_sig = _extract_signals(bot_meta["text"], url)
    user_sig = _extract_signals(user_meta["text"], url)

    # G5: cache divergence — if signatures differ, double-fetch user side
    # with a 5s gap and inspect cf-cache-status to detect a cache artifact.
    cache_artifact = False
    if _meta_signature(bot_sig) != _meta_signature(user_sig):
        time.sleep(5)
        user_meta_2 = fetch_as_with_meta(url, USER_UA)
        user_sig_2 = _extract_signals(user_meta_2["text"], url)
        cache_a = user_meta["cf"].get("cache_status")
        cache_b = user_meta_2["cf"].get("cache_status")
        if (
            cache_a != cache_b
            and _meta_signature(user_sig) != _meta_signature(user_sig_2)
        ):
            cache_artifact = True
            fp_filters.append("cache_status_changed_between_fetches")
            notes.append(
                f"Same UA produced different output across fetches (cf-cache-status: "
                f"{cache_a!r} → {cache_b!r}). Difference is a cache artifact, not cloaking."
            )
            # Use the second (warm) fetch as the user reference
            user_sig = user_sig_2

    # G1 already applied: _extract_signals decodes HTML entities via _decode().
    # Compare semantic fields after decoding.
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

    # Severity logic with G4 (A/B test threshold)
    severity = "ok"
    critical_meta_diff = any(diffs.get(k) for k in ("title", "meta_description", "canonical"))
    schema_diff = bool(diffs.get("jsonld_blocks"))
    big_size = size_pct > 30  # G4: stricter than 20% to filter A/B noise

    if cache_artifact and not (critical_meta_diff or schema_diff):
        severity = "ok"
    elif critical_meta_diff and (big_size or schema_diff):
        severity = "critical"
        notes.append("Critical SEO meta differs AND structural change — likely cloaking")
    elif critical_meta_diff:
        severity = "warning"
        notes.append(
            "Critical SEO meta differs but structural divergence under 30%. "
            "Likely A/B test or minor server template difference, not cloaking."
        )
        fp_filters.append("ab_test_threshold_30pct")
    elif schema_diff:
        severity = "warning"
        notes.append(
            "JSON-LD schema count differs. May be template-injected schema; "
            "verify which side is missing the structured data."
        )
    elif size_pct > 30:
        severity = "warning"
        notes.append(f"HTML size differs by {size_pct:.1f}% — investigate but no meta divergence")

    if not notes:
        notes.append("No significant differences detected.")

    return {
        "url": url,
        "differences": diffs,
        "html_size_delta_pct": round(size_pct, 1),
        "severity": severity,
        "notes": notes,
        "fp_filters_applied": fp_filters,
        "cache_artifact_detected": cache_artifact,
        "googlebot_signals": bot_sig,
        "user_signals": user_sig,
        "cf": {"googlebot": bot_meta["cf"], "user": user_meta["cf"]},
    }


def multi_bot_diff(url: str) -> dict[str, Any]:
    """Compare HTML served to Googlebot, Bingbot, and a normal user.

    Useful for sites that want to verify they don't favour Googlebot over
    other crawlers (which is itself a signal of cloaking). Applies G2/G3
    Cloudflare guards before classifying.
    """
    google_meta = fetch_as_with_meta(url, GOOGLEBOT_UA)
    bing_meta = fetch_as_with_meta(url, BINGBOT_UA)
    user_meta = fetch_as_with_meta(url, USER_UA)

    fp_filters: list[str] = []
    notes: list[str] = []

    # G2: BFM check on each agent
    bfm_warnings: dict[str, str] = {}
    for name, m in (("googlebot", google_meta), ("bingbot", bing_meta), ("user", user_meta)):
        warn = _bfm_inconclusive(m)
        if warn:
            bfm_warnings[name] = warn
            fp_filters.append(f"cloudflare_bfm_{name}")

    # G3: Vary
    vary_warn = _vary_caveat(user_meta)
    if vary_warn:
        notes.append(vary_warn)

    google = _extract_signals(google_meta["text"], url) if google_meta["status"] < 400 else None
    bing = _extract_signals(bing_meta["text"], url) if bing_meta["status"] < 400 else None
    user = _extract_signals(user_meta["text"], url) if user_meta["status"] < 400 else None

    sizes = {
        "googlebot": (google or {}).get("html_size_bytes", 0),
        "bingbot": (bing or {}).get("html_size_bytes", 0),
        "user": (user or {}).get("html_size_bytes", 0),
    }
    valid_sizes = [s for s in sizes.values() if s > 0]
    if len(valid_sizes) >= 2:
        spread_pct = (max(valid_sizes) - min(valid_sizes)) / max(valid_sizes) * 100
    else:
        spread_pct = 0.0

    # Cloaking score: 0-100, weighted by which axes diverge
    score = 0
    if spread_pct > 30:
        score += 30
        notes.append(f"HTML size spread {spread_pct:.1f}% across UAs (>30%)")
    if google and user and google.get("title") != user.get("title"):
        score += 25
        notes.append("Title differs between Googlebot and user")
    if google and user and google.get("jsonld_blocks") != user.get("jsonld_blocks"):
        score += 20
        notes.append("JSON-LD block count differs between Googlebot and user")
    if google and user and google.get("meta_description") != user.get("meta_description"):
        score += 15
        notes.append("Meta description differs between Googlebot and user")

    if bfm_warnings:
        # Cap the score when WAF is interfering
        score = min(score, 30)
        for w in bfm_warnings.values():
            notes.append(w)

    return {
        "url": url,
        "html_sizes": sizes,
        "size_spread_pct": round(spread_pct, 1),
        "cloaking_score": score,
        "by_agent": {
            "googlebot": google,
            "bingbot": bing,
            "user": user,
        },
        "statuses": {
            "googlebot": google_meta["status"],
            "bingbot": bing_meta["status"],
            "user": user_meta["status"],
        },
        "fp_filters_applied": fp_filters,
        "notes": notes or ["No significant divergence."],
        "cf": {
            "googlebot": google_meta["cf"],
            "bingbot": bing_meta["cf"],
            "user": user_meta["cf"],
        },
    }
