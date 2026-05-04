"""Advanced technical crawl — beyond `migration_wp_audit_site`.

Detects redirect chains, broken internal links, response-time per URL,
image alt coverage. Fills the gap with a Screaming Frog-class crawl
report without leaving Python.
"""
from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from ..security import assert_url_is_public

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def crawl_redirect_chains(
    urls: list[str],
    max_hops: int = 10,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """For each input URL, follow redirects up to ``max_hops`` and report
    the full chain.

    Detects:
      - Long chains (≥3 hops) — Google penalises link-equity transfer
      - Redirect loops — A → B → A
      - URLs that redirect to non-2xx (broken final destination)
      - Cross-domain redirects (often unintentional)
    """
    results = []
    long_chains = 0
    loops = 0
    broken = 0
    for url in urls:
        try:
            assert_url_is_public(url)
        except Exception as e:
            results.append({"url": url, "error": f"ssrf_blocked: {e}"})
            continue

        chain: list[dict] = []
        seen: set[str] = set()
        current = url
        loop = False
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False, headers={"User-Agent": UA}) as c:
                for _ in range(max_hops + 1):
                    if current in seen:
                        loop = True
                        break
                    seen.add(current)
                    r = c.get(current)
                    next_loc: str | None = None
                    if 300 <= r.status_code < 400 and "location" in r.headers:
                        next_loc = urljoin(current, r.headers["location"])
                    # Each hop now carries its `location` (the absolute URL of
                    # the next hop) so an agent can read it directly without
                    # cross-referencing chain[i+1].url. For terminal hops
                    # (2xx, 4xx, 5xx) location is null.
                    chain.append({
                        "url": current,
                        "status": r.status_code,
                        "location": next_loc,
                    })
                    if next_loc is None:
                        break
                    current = next_loc
        except httpx.HTTPError as e:
            chain.append({
                "url": current,
                "status": None,
                "location": None,
                "error": f"{type(e).__name__}: {str(e)[:120]}",
            })

        is_long = len(chain) > 3
        final_status = chain[-1].get("status") if chain else None
        # final_url at top-level: the URL of the last hop (where the chain
        # actually settled). Saves the agent from reading chain[-1].url on
        # every call. For loops, it's the URL where the loop closed.
        final_url = chain[-1].get("url") if chain else None
        is_broken = (final_status is None) or (final_status and final_status >= 400)

        if is_long:
            long_chains += 1
        if loop:
            loops += 1
        if is_broken and not loop:
            broken += 1

        # Cross-domain detection
        domains = {urlparse(h["url"]).netloc for h in chain if "url" in h}
        cross_domain = len(domains) > 1

        results.append({
            "url": url,
            "chain": chain,
            "hops": len(chain) - 1,
            "final_url": final_url,
            "final_status": final_status,
            "loop": loop,
            "broken": is_broken,
            "cross_domain": cross_domain,
        })

    return {
        "total_checked": len(urls),
        "long_chains_count": long_chains,
        "loops_count": loops,
        "broken_count": broken,
        "results": results,
    }


def check_broken_internal_links(
    pages: list[str],
    timeout: float = 15.0,
    max_pages: int = 50,
    max_links_per_page: int = 200,
) -> dict[str, Any]:
    """For each page, extract its internal `<a href>` links and HEAD-check
    each one. Reports 4xx / 5xx / unreachable links per page.

    Computes coverage: pages with at least one broken link, percentage of
    broken links across all pages.
    """
    pages = pages[:max_pages]
    href_re = re.compile(r'<a[^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
    page_results = []
    broken_total = 0
    checked_total = 0

    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": UA}) as c:
        for page_url in pages:
            try:
                assert_url_is_public(page_url)
            except Exception as e:
                page_results.append({"page": page_url, "error": f"ssrf_blocked: {e}"})
                continue
            try:
                r = c.get(page_url)
            except httpx.HTTPError as e:
                page_results.append({"page": page_url, "error": f"fetch_failed: {e}"})
                continue
            if r.status_code >= 400:
                page_results.append({"page": page_url, "error": f"page_status_{r.status_code}"})
                continue

            origin = urlparse(page_url).netloc
            hrefs = href_re.findall(r.text)
            internal_hrefs: list[str] = []
            seen: set[str] = set()
            for h in hrefs:
                # Skip anchors, mailto, tel, javascript
                if not h or h.startswith(("#", "mailto:", "tel:", "javascript:")):
                    continue
                full = urljoin(page_url, h.split("#")[0])
                if not full.startswith("http"):
                    continue
                if urlparse(full).netloc != origin:
                    continue
                if full in seen:
                    continue
                seen.add(full)
                internal_hrefs.append(full)
                if len(internal_hrefs) >= max_links_per_page:
                    break

            broken: list[dict] = []
            for h in internal_hrefs:
                checked_total += 1
                try:
                    head = c.head(h)
                    if head.status_code >= 400:
                        # Some servers reject HEAD; retry with GET Range 0-0
                        if head.status_code in (405, 403):
                            head = c.get(h, headers={"Range": "bytes=0-0"})
                        if head.status_code >= 400:
                            broken.append({"href": h, "status": head.status_code})
                            broken_total += 1
                except httpx.HTTPError as e:
                    broken.append({"href": h, "error": f"{type(e).__name__}"})
                    broken_total += 1

            page_results.append({
                "page": page_url,
                "internal_links_total": len(internal_hrefs),
                "broken_count": len(broken),
                "broken": broken,
            })

    pages_with_broken = sum(1 for p in page_results if p.get("broken_count", 0) > 0)
    return {
        "pages_checked": len(page_results),
        "links_checked_total": checked_total,
        "broken_links_total": broken_total,
        "pages_with_broken": pages_with_broken,
        "broken_rate_pct": round(broken_total / checked_total * 100, 2) if checked_total else 0,
        "page_results": page_results,
    }


def measure_response_times(
    urls: list[str],
    samples: int = 3,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Per-URL TTFB + total response time, ``samples`` runs each.

    Reports min/median/max per URL. Identifies slow tail-latency that
    Lighthouse single-shot misses.
    """
    results = []
    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": UA}) as c:
        for url in urls:
            try:
                assert_url_is_public(url)
            except Exception as e:
                results.append({"url": url, "error": f"ssrf_blocked: {e}"})
                continue
            timings: list[float] = []
            statuses: list[int] = []
            for _ in range(samples):
                t0 = time.perf_counter()
                try:
                    r = c.get(url)
                    elapsed = (time.perf_counter() - t0) * 1000
                    timings.append(elapsed)
                    statuses.append(r.status_code)
                except httpx.HTTPError:
                    timings.append(float("inf"))
                    statuses.append(0)
            ok_timings = [t for t in timings if t != float("inf")]
            if ok_timings:
                ok_timings.sort()
                median = ok_timings[len(ok_timings) // 2]
                results.append({
                    "url": url,
                    "samples": samples,
                    "min_ms": round(min(ok_timings), 1),
                    "median_ms": round(median, 1),
                    "max_ms": round(max(ok_timings), 1),
                    "status_codes": statuses,
                })
            else:
                results.append({"url": url, "error": "all_samples_failed", "status_codes": statuses})
    return {
        "total_urls": len(urls),
        "samples_per_url": samples,
        "results": results,
    }


def check_image_alt_coverage(
    pages: list[str],
    timeout: float = 15.0,
    max_pages: int = 50,
) -> dict[str, Any]:
    """For each page, report image alt coverage.

    Returns count of ``<img>`` total, count with non-empty ``alt`` attr,
    coverage percent, and per-page list of images missing alt (top 10).
    """
    pages = pages[:max_pages]
    img_re = re.compile(r'<img\s+([^>]+)>', re.IGNORECASE)
    alt_re = re.compile(r'\balt\s*=\s*"([^"]*)"', re.IGNORECASE)
    src_re = re.compile(r'\bsrc\s*=\s*"([^"]+)"', re.IGNORECASE)
    page_results = []
    total_imgs = 0
    total_with_alt = 0

    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": UA}) as c:
        for page_url in pages:
            try:
                assert_url_is_public(page_url)
                r = c.get(page_url)
            except (httpx.HTTPError, RuntimeError) as e:
                page_results.append({"page": page_url, "error": str(e)[:150]})
                continue
            if r.status_code >= 400:
                page_results.append({"page": page_url, "error": f"status_{r.status_code}"})
                continue

            imgs = img_re.findall(r.text)
            page_total = len(imgs)
            page_with_alt = 0
            missing_alt: list[str] = []
            for img_attrs in imgs:
                alt_match = alt_re.search(img_attrs)
                src_match = src_re.search(img_attrs)
                src = src_match.group(1) if src_match else "(no src)"
                if alt_match and alt_match.group(1).strip():
                    page_with_alt += 1
                else:
                    if len(missing_alt) < 10:
                        missing_alt.append(src)
            total_imgs += page_total
            total_with_alt += page_with_alt
            page_results.append({
                "page": page_url,
                "img_count": page_total,
                "img_with_alt": page_with_alt,
                "coverage_pct": round(page_with_alt / page_total * 100, 1) if page_total else 100,
                "missing_alt_sample": missing_alt,
            })

    overall = round(total_with_alt / total_imgs * 100, 1) if total_imgs else 100
    return {
        "pages_checked": len(page_results),
        "total_images": total_imgs,
        "images_with_alt": total_with_alt,
        "coverage_pct": overall,
        "page_results": page_results,
    }
