"""Lighthouse / PSI tools registered with the MCP server."""
from __future__ import annotations

from typing import Any

from ..guardrails import with_meta
from . import call_psi


def _audit_summary(psi: dict[str, Any]) -> dict[str, Any]:
    """Extract the high-signal numbers from a PSI response."""
    lr = psi.get("lighthouseResult", {})
    cats = lr.get("categories", {})
    audits = lr.get("audits", {})

    def _score(cat: str) -> float | None:
        c = cats.get(cat)
        return round(c["score"] * 100, 1) if c and c.get("score") is not None else None

    def _audit_value(audit_id: str) -> dict | None:
        a = audits.get(audit_id)
        if not a:
            return None
        return {
            "score": a.get("score"),
            "value": a.get("displayValue") or a.get("numericValue"),
            "title": a.get("title"),
        }

    return {
        "scores": {
            "performance": _score("performance"),
            "accessibility": _score("accessibility"),
            "best_practices": _score("best-practices"),
            "seo": _score("seo"),
        },
        "core_web_vitals": {
            "lcp": _audit_value("largest-contentful-paint"),
            "cls": _audit_value("cumulative-layout-shift"),
            "tbt": _audit_value("total-blocking-time"),
            "fcp": _audit_value("first-contentful-paint"),
            "speed_index": _audit_value("speed-index"),
            "tti": _audit_value("interactive"),
        },
        "fetch_time": lr.get("fetchTime"),
        "lighthouse_version": lr.get("lighthouseVersion"),
        "user_agent": lr.get("userAgent"),
    }


def lighthouse_audit(url: str, strategy: str = "mobile") -> dict:
    """Run a full Lighthouse audit (mobile or desktop) via PageSpeed Insights v5.

    Returns scores (perf/a11y/best-practices/SEO 0-100) + Core Web Vitals.

    Args:
        url: The page to audit (must be publicly reachable).
        strategy: "mobile" (default, what Google uses for ranking) or "desktop".
    """
    psi = call_psi(url, strategy=strategy)
    return with_meta(
        _audit_summary(psi),
        source=f"pagespeed_insights_v5.{strategy}",
        site_url=url,
    )


def lighthouse_core_web_vitals(url: str, strategy: str = "mobile") -> dict:
    """Get only Core Web Vitals (LCP, CLS, TBT, FCP, Speed Index, TTI). Faster than full audit.

    Useful for one-shot diagnosis of a page's performance health without the full
    accessibility/SEO/best-practices payload.
    """
    psi = call_psi(url, strategy=strategy, categories=["performance"])
    cwv = _audit_summary(psi)["core_web_vitals"]
    return with_meta(cwv, source=f"pagespeed_insights_v5.cwv.{strategy}", site_url=url)


def lighthouse_lcp_opportunities(url: str, strategy: str = "mobile") -> dict:
    """List the audits that, if fixed, would improve LCP the most.

    Returns the top "opportunities" (Lighthouse term for actionable improvements)
    sorted by estimated savings in ms.
    """
    psi = call_psi(url, strategy=strategy, categories=["performance"])
    audits = psi.get("lighthouseResult", {}).get("audits", {})
    opportunities = []
    for aid, a in audits.items():
        if a.get("details", {}).get("type") != "opportunity":
            continue
        savings = a.get("details", {}).get("overallSavingsMs", 0)
        if savings <= 0:
            continue
        opportunities.append({
            "id": aid,
            "title": a.get("title"),
            "description": a.get("description"),
            "estimated_savings_ms": savings,
            "score": a.get("score"),
        })
    opportunities.sort(key=lambda x: x["estimated_savings_ms"], reverse=True)
    return with_meta(
        opportunities,
        source=f"pagespeed_insights_v5.opportunities.{strategy}",
        site_url=url,
    )


def lighthouse_compare_mobile_desktop(url: str) -> dict:
    """Run audits for both strategies and return a side-by-side comparison.

    Useful to detect mobile-only regressions (very common: hero images served at
    desktop sizes, blocking JS that only fires on mobile, etc.).
    """
    mobile = _audit_summary(call_psi(url, strategy="mobile", categories=["performance"]))
    desktop = _audit_summary(call_psi(url, strategy="desktop", categories=["performance"]))
    return with_meta(
        {
            "mobile": mobile,
            "desktop": desktop,
            "delta_perf_score": (
                (mobile["scores"]["performance"] or 0)
                - (desktop["scores"]["performance"] or 0)
            ),
        },
        source="pagespeed_insights_v5.compare",
        site_url=url,
    )


def lighthouse_seo_score(url: str, strategy: str = "mobile") -> dict:
    """Lighthouse SEO category breakdown — which on-page SEO audits pass/fail.

    Lighthouse's SEO category checks: meta descriptions, viewport, crawlable links,
    HTTP status, hreflang, structured data presence (not validity), tap targets.
    """
    psi = call_psi(url, strategy=strategy, categories=["seo"])
    audits = psi.get("lighthouseResult", {}).get("audits", {})
    seo_cat = psi.get("lighthouseResult", {}).get("categories", {}).get("seo", {})
    refs = seo_cat.get("auditRefs", [])
    breakdown = []
    for ref in refs:
        a = audits.get(ref["id"], {})
        breakdown.append({
            "id": ref["id"],
            "title": a.get("title"),
            "score": a.get("score"),
            "display": a.get("displayValue") or a.get("explanation") or "",
        })
    return with_meta(
        {
            "score": round((seo_cat.get("score") or 0) * 100, 1),
            "audits": breakdown,
        },
        source=f"pagespeed_insights_v5.seo.{strategy}",
        site_url=url,
    )
