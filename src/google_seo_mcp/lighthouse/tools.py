"""Lighthouse / PSI tools registered with the MCP server."""
from __future__ import annotations

from typing import Any

from ..guardrails import with_meta
from . import call_psi, extract_field_data


def _audit_summary(psi: dict[str, Any]) -> dict[str, Any]:
    """Extract the high-signal numbers from a PSI response.

    Reports CrUX field data (real users, p75) alongside the lab metrics —
    PSI embeds it for free in `loadingExperience` / `originLoadingExperience`
    and ignoring it gives lab-only audits, which mislead decision making.

    Only LCP/INP/CLS are reported as Core Web Vitals (the official set since
    March 2024 when INP replaced FID). TBT/FCP/SI/TTI are surfaced under
    `lab_metrics` instead — they are diagnostic, not ranking signals.
    """
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
        "core_web_vitals_lab": {
            # LCP/CLS are CWV. INP comes from field only — Lighthouse cannot
            # measure it directly. TBT is its lab proxy and lives under
            # lab_metrics, NOT here.
            "lcp": _audit_value("largest-contentful-paint"),
            "cls": _audit_value("cumulative-layout-shift"),
        },
        "core_web_vitals_field": extract_field_data(psi),
        "lab_metrics": {
            "tbt_proxy_for_inp": _audit_value("total-blocking-time"),
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
    summary = _audit_summary(psi)
    cwv = {
        "core_web_vitals_lab": summary["core_web_vitals_lab"],
        "core_web_vitals_field": summary["core_web_vitals_field"],
        "lab_metrics": summary["lab_metrics"],
    }
    return with_meta(cwv, source=f"pagespeed_insights_v5.cwv.{strategy}", site_url=url)


def lighthouse_lcp_opportunities(url: str, strategy: str = "mobile") -> dict:
    """List the audits that, if fixed, would improve LCP the most.

    Filters to audits actually relevant to LCP (via Lighthouse's
    ``auditRefs[*].relevantAudits``). Earlier versions returned every
    opportunity which surfaced unused-css-rules / efficient-animated-content
    even when LCP didn't depend on them.
    """
    psi = call_psi(url, strategy=strategy, categories=["performance"])
    lr = psi.get("lighthouseResult", {})
    audits = lr.get("audits", {})
    perf_cat = lr.get("categories", {}).get("performance", {})
    refs = perf_cat.get("auditRefs", [])

    # The audit IDs that Lighthouse declares as relevant to LCP
    lcp_relevant_ids: set[str] = set()
    for ref in refs:
        if ref.get("id") == "largest-contentful-paint":
            continue
        relevant = ref.get("relevantAudits") or []
        if "largest-contentful-paint" in relevant:
            lcp_relevant_ids.add(ref["id"])

    opportunities = []
    other_perf_opps = []
    for aid, a in audits.items():
        if a.get("details", {}).get("type") != "opportunity":
            continue
        savings = a.get("details", {}).get("overallSavingsMs", 0)
        if savings <= 0:
            continue
        item = {
            "id": aid,
            "title": a.get("title"),
            "description": a.get("description"),
            "estimated_savings_ms": savings,
            "score": a.get("score"),
            "lcp_relevant": aid in lcp_relevant_ids,
        }
        if aid in lcp_relevant_ids:
            opportunities.append(item)
        else:
            other_perf_opps.append(item)

    opportunities.sort(key=lambda x: x["estimated_savings_ms"], reverse=True)
    other_perf_opps.sort(key=lambda x: x["estimated_savings_ms"], reverse=True)
    return with_meta(
        {
            "lcp_relevant_opportunities": opportunities,
            "other_performance_opportunities": other_perf_opps,
        },
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
