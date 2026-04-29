"""Structured-data extraction & validation.

Uses `extruct` to extract JSON-LD/microdata/RDFa from a live URL, plus a light
type/property check against the Schema.org type tree. No external service.
"""
from __future__ import annotations

from typing import Any

import httpx

COMMON_TYPES = {
    "Article", "BlogPosting", "NewsArticle", "WebPage", "WebSite",
    "Organization", "LocalBusiness", "Person", "Product", "Offer",
    "Event", "Course", "Recipe", "VideoObject", "FAQPage", "HowTo",
    "Question", "Answer", "BreadcrumbList", "ItemList", "Review",
    "AggregateRating", "MedicalEntity", "MedicalTherapy", "MedicalCondition",
    "Service", "ProfessionalService", "EducationalOrganization",
}


_REAL_USER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def fetch_html(url: str, timeout: float = 30.0, user_agent: str | None = None) -> str:
    """Fetch a URL's HTML using a realistic browser User-Agent.

    Schema extraction MUST see the same HTML a real user / Googlebot sees.
    A custom UA like ``google-seo-mcp/x.y`` would trip Cloudflare /
    DataDome / Akamai bot management and serve a challenge page or a
    different variant — so we default to a current Chrome desktop UA and
    let callers override only when they need a specific bot UA (passed by
    the cloaking module).
    """
    headers = {
        "User-Agent": user_agent or _REAL_USER_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
    except httpx.HTTPError as e:
        raise RuntimeError(f"Fetch failed: {type(e).__name__}: {e}") from None
    if resp.status_code >= 400:
        raise RuntimeError(f"Fetch returned {resp.status_code} for {url}")
    return resp.text


def extract_structured_data(html: str, url: str) -> dict[str, Any]:
    """Extract JSON-LD, microdata, and RDFa from HTML."""
    try:
        import extruct  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "Schema tools require `extruct`. Install: pip install extruct"
        ) from e
    return extruct.extract(html, base_url=url, syntaxes=["json-ld", "microdata", "rdfa"])
