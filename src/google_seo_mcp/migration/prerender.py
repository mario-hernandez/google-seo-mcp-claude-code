"""SSR / pre-render verification for JS-heavy sites (React/Vue/Svelte SSR).

Verifies that the HTML served BEFORE JavaScript executes contains the SEO
signals Googlebot needs (meta tags, schema, OG, real text content). The
hydrated comparison detects bugs where SSR is incomplete and content only
appears after JS.
"""
from __future__ import annotations

import html as _html
import re
from typing import Any

import httpx

from ..security import assert_url_is_public


def _decode(s: str | None) -> str | None:
    """Decode HTML entities (&iquest; → ¿) so semantic comparisons aren't fooled
    by mere encoding differences."""
    if s is None:
        return None
    return _html.unescape(s)

USER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

META_TAG_RE = re.compile(r"<meta\s+(?P<attrs>[^>]*?)/?>", re.IGNORECASE | re.DOTALL)
ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"', re.IGNORECASE)


def _extract_signals(html: str, url: str) -> dict[str, Any]:
    """Pure-Python extraction of SEO signals (no BeautifulSoup needed)."""
    signals: dict[str, Any] = {"url": url, "html_size_bytes": len(html)}

    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    signals["title"] = _decode(m.group(1).strip()) if m else None

    og: dict[str, str] = {}
    twitter: dict[str, str] = {}
    others: dict[str, str] = {}
    for tag in META_TAG_RE.finditer(html):
        attrs = dict(ATTR_RE.findall(tag.group("attrs") or ""))
        name = attrs.get("name") or attrs.get("property") or attrs.get("http-equiv")
        content = attrs.get("content")
        if not (name and content is not None):
            continue
        ln = name.lower()
        if ln.startswith("og:"):
            og[ln[3:]] = content
        elif ln.startswith("twitter:"):
            twitter[ln[8:]] = content
        else:
            others[ln] = content
    signals["meta_description"] = _decode(others.get("description"))
    signals["meta_robots"] = others.get("robots")
    signals["og"] = {k: _decode(v) for k, v in og.items()}
    signals["twitter"] = {k: _decode(v) for k, v in twitter.items()}
    signals["og_count"] = len(og)
    signals["twitter_count"] = len(twitter)

    m = re.search(
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    signals["canonical"] = _decode(m.group(1)) if m else None

    hreflangs = re.findall(
        r'<link[^>]+rel=["\']alternate["\'][^>]+hreflang=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    signals["hreflang_count"] = len(hreflangs)

    h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    signals["h1"] = [_decode(re.sub(r"<[^>]+>", "", h).strip()) for h in h1s]

    jsonld = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.+?)</script>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    signals["jsonld_blocks"] = len(jsonld)

    p_count = len(re.findall(r"<p[\s>]", html, re.IGNORECASE))
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    signals["p_tag_count"] = p_count
    signals["visible_text_chars"] = len(text)

    return signals


# Cloudflare cache status interpretation. Without this the double-fetch
# logic in cloaking.py treats a HIT/MISS swap (normal cache lifecycle) as
# divergence (cloaking artifact). Edge engineer demanded an explicit map.
_CF_CACHE_STATUS_DOC = {
    "HIT": "Served from cache",
    "MISS": "Cache miss, proxied to origin and not (yet) cached",
    "EXPIRED": "Cache hit but stale, revalidated against origin",
    "STALE": "Stale cache hit served while revalidating (SWR)",
    "BYPASS": "Page Rule / Worker / Cache-Control forced cache bypass",
    "DYNAMIC": "Asset deemed uncacheable; never cached",
    "REVALIDATED": "Cached copy revalidated and reused (304)",
    "UPDATING": "Stale served while a fresh copy is being fetched",
    "NONE/UNKNOWN": "Cloudflare did not classify (rare)",
}


def _cf_cache_status_meaning(value: str | None) -> str | None:
    if not value:
        return None
    return _CF_CACHE_STATUS_DOC.get(value.upper(), f"Unrecognised: {value!r}")


def fetch_as(url: str, ua: str, timeout: float = 30.0) -> str:
    """Fetch URL with a specific User-Agent. Raises RuntimeError on HTTP errors."""
    return fetch_as_with_meta(url, ua, timeout=timeout, raise_on_error=True)["text"]


def fetch_as_with_meta(
    url: str,
    ua: str,
    timeout: float = 30.0,
    raise_on_error: bool = False,
    accept_language: str = "en-US,en;q=0.9",
    capture_redirects: bool = False,
) -> dict[str, Any]:
    """Fetch URL with a UA and return text + status + headers + Cloudflare metadata.

    Returns ``{"text": str, "status": int, "headers": dict, "cf": {...}}``.
    Set ``capture_redirects=True`` to also return a ``redirects`` list with
    every hop (so a migration tool can audit chains that CF/Workers add).
    Use ``raise_on_error=True`` to mimic ``fetch_as`` legacy behaviour.
    """
    assert_url_is_public(url)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": accept_language,
    }
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
    except httpx.HTTPError as e:
        raise RuntimeError(f"Fetch failed: {type(e).__name__}: {e}") from None
    if raise_on_error and resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code} at {url}")
    h = {k.lower(): v for k, v in resp.headers.items()}
    redirect_chain: list[dict[str, Any]] = []
    if capture_redirects:
        for hop in list(resp.history) + [resp]:
            hh = {k.lower(): v for k, v in hop.headers.items()}
            redirect_chain.append({
                "url": str(hop.url),
                "status": hop.status_code,
                "location": hh.get("location"),
                "cf_ray": hh.get("cf-ray"),
                "cf_cache_status": hh.get("cf-cache-status"),
                "cf_mitigated": hh.get("cf-mitigated"),
                "x_amz_cf_pop": hh.get("x-amz-cf-pop"),
                "x_served_by": hh.get("x-served-by"),
                "x_vercel_cache": hh.get("x-vercel-cache"),
                "x_akamai_cache_status": hh.get("x-akamai-cache-status"),
            })
    return {
        "text": resp.text,
        "status": resp.status_code,
        "headers": h,
        "redirects": redirect_chain,
        "redirect_chain_length": len(resp.history),
        "cf": {
            "mitigated": h.get("cf-mitigated"),
            "cache_status": h.get("cf-cache-status"),
            "cache_status_meaning": _cf_cache_status_meaning(h.get("cf-cache-status")),
            "ray": h.get("cf-ray"),
            "vary": h.get("vary", ""),
            "server": h.get("server", ""),
        },
        # Multi-CDN signals — present when the upstream CDN sets them
        "edge": {
            "akamai_cache_status": h.get("x-akamai-cache-status"),
            "akamai_x_cache": h.get("x-cache"),
            "fastly_served_by": h.get("x-served-by"),
            "fastly_cache": h.get("x-cache"),
            "fastly_debug": h.get("fastly-debug-digest"),
            "vercel_cache": h.get("x-vercel-cache"),
            "vercel_id": h.get("x-vercel-id"),
            "netlify_request_id": h.get("x-nf-request-id"),
            "cloudfront_pop": h.get("x-amz-cf-pop"),
            "cloudfront_id": h.get("x-amz-cf-id"),
        },
    }


def prerender_signals(url: str) -> dict[str, Any]:
    """Fetch URL without executing JS and report SEO signals + health.

    Use this to validate the pre-rendered output of an SSR pipeline before
    React/Vue/Svelte hydration. Detects missing meta, missing schema, SPA
    shell pages (no real content), etc.

    Third-party text fields (title, meta_description, og, h1) are wrapped
    as ``<untrusted-third-party-content>...</untrusted-third-party-content>``
    so an LLM consuming this output cannot be hijacked by prompt-injection
    payloads embedded in the page metadata.

    Also detects the *shell-only soft-404* pattern (200 status with body
    containing only a JS root mount + meta tags) — the failure mode of
    Next.js / Nuxt / SvelteKit deployments that forget SSR.
    """
    from ..security import mark_third_party_strings

    html = fetch_as(url, USER_UA)
    sig = _extract_signals(html, url)

    # Shell-only soft-404 detection: when the body is essentially just a
    # JS root and the page reports rich meta, a naive parser could call
    # this ``green``. Signal it as ``red`` so the agent doesn't ship.
    body_text_chars = sig.get("visible_text_chars", 0)
    body_text_to_html_ratio = (
        body_text_chars / max(sig.get("html_size_bytes", 1), 1)
    )
    is_shell = (
        body_text_chars < 200
        and body_text_to_html_ratio < 0.05
        and any(
            f'id="{root}"' in html or f"id='{root}'" in html
            for root in ("__next", "root", "app", "svelte", "__nuxt")
        )
    )
    if is_shell:
        sig.setdefault("issues", []).append("shell_only_soft_404")
        sig["health"] = "red"
        sig["soft_404_pattern"] = (
            "Body is a JS root mount (#__next/#root/#app/#svelte) with "
            "<200 chars of visible text. Page returns 200 but is a soft 404 "
            "for non-JS crawlers — fix SSR before relaunch."
        )
    sig = mark_third_party_strings(sig)

    issues: list[str] = []
    if not sig["title"]:
        issues.append("missing_title")
    if not sig["meta_description"]:
        issues.append("missing_meta_description")
    if not sig["canonical"]:
        issues.append("missing_canonical")
    if sig["jsonld_blocks"] == 0:
        issues.append("no_jsonld_schema")
    if sig["og_count"] < 3:
        issues.append("insufficient_open_graph")
    if sig["p_tag_count"] < 3:
        issues.append("looks_like_spa_shell")
    if sig["visible_text_chars"] < 500:
        issues.append("very_low_visible_text")
    if not sig["h1"]:
        issues.append("missing_h1")

    sig["issues"] = issues
    if not issues:
        sig["health"] = "green"
    elif "looks_like_spa_shell" in issues or "very_low_visible_text" in issues:
        sig["health"] = "red"
    else:
        sig["health"] = "amber"
    return sig


def prerender_vs_hydrated(
    url: str,
    wait_ms: int = 2000,
    wrs_realistic: bool = False,
) -> dict[str, Any]:
    """Compare pre-rendered HTML (no JS) vs DOM after JS hydration.

    Detects:
      - Content visible to user but missing in pre-render → bad SSR
      - JS-injected meta/schema → Googlebot may not see them
      - Heavy hydration changes → fragile SSR
      - **Hydration mismatch warnings** (React #418/#423/#425) — invisible
        to HTML diffs but kill SEO when they break the hydrated tree
      - **Page errors / failed requests** during hydration

    Args:
        wait_ms: extra delay after the wait condition (default 2000ms).
        wrs_realistic: when True, model Googlebot's Web Rendering Service
            faithfully — ``domcontentloaded`` instead of ``networkidle``,
            5-second budget, headless Chromium. The default ``False``
            keeps the lenient developer-friendly behaviour for backward
            compatibility, but ``wrs_realistic=True`` is what you should
            ship to QA for migration sign-off.

    Requires Playwright (lazy import). If not installed:
        pip install playwright && playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "prerender_vs_hydrated requires Playwright. Install:\n"
            "  pip install playwright && playwright install chromium"
        ) from e

    pre_html = fetch_as(url, USER_UA)
    pre_sig = _extract_signals(pre_html, url)

    console_messages: list[dict[str, str]] = []
    page_errors: list[str] = []
    failed_requests: list[dict[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_UA)
            page.on(
                "console",
                lambda msg: console_messages.append(
                    {"type": msg.type, "text": msg.text[:300]}
                ),
            )
            page.on("pageerror", lambda exc: page_errors.append(str(exc)[:400]))
            page.on(
                "requestfailed",
                lambda req: failed_requests.append({
                    "url": req.url[:200],
                    "method": req.method,
                    "failure": (req.failure or "")[:120],
                }),
            )
            if wrs_realistic:
                # Match Googlebot WRS budget — domcontentloaded + 5 s hard cap.
                page.goto(url, wait_until="domcontentloaded", timeout=10_000)
                page.wait_for_timeout(min(wait_ms, 5_000))
            else:
                page.goto(url, wait_until="networkidle", timeout=45_000)
                if wait_ms:
                    page.wait_for_timeout(wait_ms)
            hydrated_html = page.content()
        finally:
            browser.close()

    post_sig = _extract_signals(hydrated_html, url)

    # Look for the React hydration mismatch family in console output.
    hydration_warnings = [
        m for m in console_messages
        if any(
            tok in (m.get("text") or "")
            for tok in (
                "Hydration", "hydration",
                "did not match", "Minified React error #418",
                "Minified React error #423", "Minified React error #425",
            )
        )
    ]

    diffs: dict[str, Any] = {}
    for k in (
        "title", "meta_description", "canonical",
        "og_count", "twitter_count", "jsonld_blocks",
        "p_tag_count", "visible_text_chars",
    ):
        if pre_sig.get(k) != post_sig.get(k):
            diffs[k] = {"pre_render": pre_sig.get(k), "after_js": post_sig.get(k)}

    issues: list[str] = []
    pre_text = max(pre_sig["visible_text_chars"], 1)
    text_delta_pct = (post_sig["visible_text_chars"] - pre_sig["visible_text_chars"]) / pre_text * 100
    if text_delta_pct > 50:
        issues.append("massive_content_added_post_hydration")
    if pre_sig["jsonld_blocks"] == 0 and post_sig["jsonld_blocks"] > 0:
        issues.append("schema_only_visible_after_js")
    if not pre_sig["title"] and post_sig["title"]:
        issues.append("title_only_set_after_js")
    if not pre_sig["meta_description"] and post_sig["meta_description"]:
        issues.append("description_only_set_after_js")
    if hydration_warnings:
        issues.append("react_hydration_mismatch")
    if page_errors:
        issues.append("javascript_errors_during_hydration")

    return {
        "url": url,
        "pre_render_signals": pre_sig,
        "after_js_signals": post_sig,
        "differences": diffs,
        "visible_text_delta_pct": round(text_delta_pct, 1),
        "issues": issues,
        "verdict": "ok" if not issues else "ssr_problem",
        "wrs_realistic_mode": wrs_realistic,
        "hydration_warnings": hydration_warnings[:20],
        "page_errors": page_errors[:20],
        "failed_requests": failed_requests[:20],
        "console_message_count": len(console_messages),
    }
