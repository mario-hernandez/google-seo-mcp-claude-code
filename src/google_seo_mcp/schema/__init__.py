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


def fetch_html(url: str, timeout: float = 30.0) -> str:
    """Fetch a URL's HTML with a sensible UA string."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; google-seo-mcp/0.2; +https://github.com/"
            "mario-hernandez/google-seo-mcp-claude-code)"
        ),
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
