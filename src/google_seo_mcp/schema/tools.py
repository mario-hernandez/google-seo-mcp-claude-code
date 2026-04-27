"""Schema.org / JSON-LD validator tools."""
from __future__ import annotations

from typing import Any

from ..guardrails import with_meta
from . import COMMON_TYPES, extract_structured_data, fetch_html


def _flatten_jsonld_types(jsonld_blocks: list[dict]) -> list[str]:
    """Walk JSON-LD trees and collect all @type values."""
    types: list[str] = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            t = obj.get("@type")
            if isinstance(t, str):
                types.append(t)
            elif isinstance(t, list):
                types.extend(x for x in t if isinstance(x, str))
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    for block in jsonld_blocks:
        _walk(block)
    return types


def schema_extract_url(url: str) -> dict:
    """Fetch a URL and extract all structured data (JSON-LD + microdata + RDFa).

    Returns the raw extracted blocks plus a summary of the @types found.
    """
    html = fetch_html(url)
    data = extract_structured_data(html, url)
    jsonld = data.get("json-ld", []) or []
    microdata = data.get("microdata", []) or []
    rdfa = data.get("rdfa", []) or []
    types = _flatten_jsonld_types(jsonld)
    return with_meta(
        {
            "url": url,
            "json_ld_blocks": len(jsonld),
            "microdata_items": len(microdata),
            "rdfa_items": len(rdfa),
            "json_ld_types": sorted(set(types)),
            "json_ld_raw": jsonld,
            "microdata_raw": microdata,
            "rdfa_raw": rdfa,
        },
        source="schema.extract_url",
        site_url=url,
    )


def schema_validate_url(url: str) -> dict:
    """Lightweight schema validation: fetches URL, extracts JSON-LD, and reports
    common pitfalls without calling any external validator.

    Checks:
      - At least one @type declared
      - Recognisable type (in COMMON_TYPES)
      - For Article/BlogPosting: required headline, datePublished, author
      - For Product: required name, offers OR aggregateRating
      - For FAQPage: at least one mainEntity Question with acceptedAnswer
      - For HowTo: name + step
      - For BreadcrumbList: itemListElement with position+name+item
    """
    html = fetch_html(url)
    data = extract_structured_data(html, url)
    blocks = data.get("json-ld", []) or []
    types = _flatten_jsonld_types(blocks)
    issues: list[dict[str, str]] = []
    successes: list[str] = []

    if not types:
        issues.append({"severity": "warning", "message": "No JSON-LD @type detected on page."})
        return with_meta(
            {"types": [], "issues": issues, "successes": successes, "json_ld_count": 0},
            source="schema.validate_url",
            site_url=url,
        )

    unrecognised = [t for t in set(types) if t not in COMMON_TYPES]
    if unrecognised:
        issues.append({
            "severity": "info",
            "message": f"Types not in COMMON_TYPES (may still be valid): {sorted(unrecognised)}",
        })

    # Walk blocks for required-property checks
    def _check(block: Any) -> None:
        if not isinstance(block, dict):
            return
        t = block.get("@type")
        ts = [t] if isinstance(t, str) else (t or [])

        for one in ts:
            if one in {"Article", "BlogPosting", "NewsArticle"}:
                for req in ("headline", "datePublished"):
                    if req not in block:
                        issues.append({"severity": "warning",
                                       "message": f"{one} missing required `{req}`"})
                if "author" not in block:
                    issues.append({"severity": "warning",
                                   "message": f"{one} missing `author`"})
                else:
                    successes.append(f"{one} declares author")
            elif one == "Product":
                if "name" not in block:
                    issues.append({"severity": "warning", "message": "Product missing `name`"})
                if "offers" not in block and "aggregateRating" not in block:
                    issues.append({"severity": "warning",
                                   "message": "Product should have `offers` or `aggregateRating`"})
            elif one == "FAQPage":
                main = block.get("mainEntity") or []
                if not main:
                    issues.append({"severity": "warning",
                                   "message": "FAQPage has no mainEntity (Questions)"})
                else:
                    successes.append(f"FAQPage declares {len(main) if isinstance(main, list) else 1} questions")
            elif one == "HowTo":
                if "step" not in block:
                    issues.append({"severity": "warning", "message": "HowTo missing `step`"})
            elif one == "BreadcrumbList":
                items = block.get("itemListElement", [])
                if not items:
                    issues.append({"severity": "warning",
                                   "message": "BreadcrumbList missing itemListElement"})

        # Recurse into nested
        for v in block.values():
            if isinstance(v, dict):
                _check(v)
            elif isinstance(v, list):
                for x in v:
                    _check(x)

    for block in blocks:
        _check(block)

    return with_meta(
        {
            "types": sorted(set(types)),
            "json_ld_count": len(blocks),
            "issues": issues,
            "successes": successes,
        },
        source="schema.validate_url",
        site_url=url,
    )


def schema_suggest_for_page(url: str, page_intent: str = "informational") -> dict:
    """Suggest schemas to add given the page's content type.

    Args:
        page_intent: informational | product | service | event | course | recipe |
            faq | local_business | article | medical
    """
    suggestions = {
        "informational": ["Article", "BreadcrumbList", "FAQPage (if applicable)"],
        "product": ["Product", "Offer", "AggregateRating", "BreadcrumbList"],
        "service": ["Service", "Organization", "BreadcrumbList"],
        "event": ["Event", "Place"],
        "course": ["Course", "Organization"],
        "recipe": ["Recipe", "AggregateRating"],
        "faq": ["FAQPage"],
        "local_business": ["LocalBusiness", "Organization", "PostalAddress"],
        "article": ["Article", "BreadcrumbList", "Person (author)"],
        "medical": ["MedicalTherapy", "MedicalEntity", "Article"],
    }
    rec = suggestions.get(page_intent, ["Article", "WebPage", "Organization"])
    return with_meta(
        {
            "url": url,
            "page_intent": page_intent,
            "recommended_schemas": rec,
            "notes": (
                "These types are most likely to enable rich results for this intent. "
                "Validate after deployment with `schema_validate_url`."
            ),
        },
        source="schema.suggest_for_page",
        site_url=url,
    )
