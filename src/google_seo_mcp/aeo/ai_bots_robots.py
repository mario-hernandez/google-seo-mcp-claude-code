"""AI bot robots.txt audit.

Most ``robots.txt`` audits only check Googlebot. In 2026 the policy
question is: do we let GPTBot / ClaudeBot / PerplexityBot / Google-Extended
ingest us, and is that decision intentional? This tool reports the policy
for every major AI crawler so the agent can flag accidental blocks (or
accidental allows for sites that wanted to opt out).
"""
from __future__ import annotations

import urllib.robotparser
from typing import Any
from urllib.parse import urljoin

import httpx

from ..security import assert_url_is_public

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# Active AI / LLM crawlers in 2026. Names match the documented user-agent
# strings vendors publish.
AI_BOTS: dict[str, dict[str, str]] = {
    "GPTBot": {
        "vendor": "OpenAI",
        "purpose": "Train ChatGPT models. Not the same as ChatGPT-User (live answer).",
        "docs": "https://platform.openai.com/docs/gptbot",
    },
    "ChatGPT-User": {
        "vendor": "OpenAI",
        "purpose": "Live fetch when a ChatGPT user asks about your URL.",
        "docs": "https://platform.openai.com/docs/plugins/bot",
    },
    "OAI-SearchBot": {
        "vendor": "OpenAI",
        "purpose": "OpenAI search index crawler.",
        "docs": "https://platform.openai.com/docs/bots",
    },
    "ClaudeBot": {
        "vendor": "Anthropic",
        "purpose": "Train Claude models. Honors robots.txt.",
        "docs": "https://www.anthropic.com/news/web-crawlers",
    },
    "Claude-Web": {
        "vendor": "Anthropic",
        "purpose": "Live fetch when Claude users reference your URL.",
        "docs": "https://www.anthropic.com/news/web-crawlers",
    },
    "PerplexityBot": {
        "vendor": "Perplexity",
        "purpose": "Index for Perplexity answers.",
        "docs": "https://docs.perplexity.ai/guides/bots",
    },
    "Perplexity-User": {
        "vendor": "Perplexity",
        "purpose": "Live fetch when Perplexity users ask about your URL.",
        "docs": "https://docs.perplexity.ai/guides/bots",
    },
    "Google-Extended": {
        "vendor": "Google",
        "purpose": (
            "Opt-out token for Bard/Gemini training. Does NOT affect "
            "Google Search ranking or indexing."
        ),
        "docs": "https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers#google-extended",
    },
    "Applebot-Extended": {
        "vendor": "Apple",
        "purpose": "Apple Intelligence training opt-out.",
        "docs": "https://support.apple.com/en-us/119829",
    },
    "Bytespider": {
        "vendor": "ByteDance",
        "purpose": "TikTok / Doubao crawler. Often blocked.",
        "docs": "https://bytedance.com",
    },
    "CCBot": {
        "vendor": "Common Crawl",
        "purpose": (
            "Common Crawl corpus — feeds many LLM training datasets. "
            "Blocking CCBot is the most effective AI-train opt-out."
        ),
        "docs": "https://commoncrawl.org/big-picture/frequently-asked-questions/",
    },
    "FacebookBot": {
        "vendor": "Meta",
        "purpose": "Meta AI / LLaMA training crawler.",
        "docs": "https://developers.facebook.com/docs/sharing/bot/",
    },
    "Meta-ExternalAgent": {
        "vendor": "Meta",
        "purpose": "Meta agentic crawler.",
        "docs": "https://developers.facebook.com",
    },
    "Amazonbot": {
        "vendor": "Amazon",
        "purpose": "Alexa / Amazon AI ingestion.",
        "docs": "https://developer.amazon.com/en/amazonbot",
    },
    "Diffbot": {
        "vendor": "Diffbot",
        "purpose": "Knowledge graph / retrieval as a service.",
        "docs": "https://www.diffbot.com",
    },
    "anthropic-ai": {
        "vendor": "Anthropic (legacy)",
        "purpose": "Older Anthropic UA — keep in lists for compatibility.",
        "docs": "https://www.anthropic.com",
    },
}


def aibots_robots_audit(origin_url: str, sample_path: str = "/") -> dict[str, Any]:
    """Audit how every known AI bot is treated by robots.txt for a site.

    For each bot we report ``allowed`` (boolean for the sample path),
    plus the vendor / purpose / docs URL so the agent can explain to the
    operator the implications of allowing or blocking.
    """
    if not origin_url.startswith(("http://", "https://")):
        raise ValueError("origin_url must include scheme (https://...)")

    robots_url = urljoin(origin_url + "/", "robots.txt")
    assert_url_is_public(robots_url)

    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, headers={"User-Agent": UA}) as c:
            r = c.get(robots_url)
    except httpx.HTTPError as e:
        return {
            "origin": origin_url,
            "robots_txt": {"url": robots_url, "fetch_error": str(e)[:120]},
            "policy": {},
            "warnings": ["robots_txt_unreachable"],
        }

    if r.status_code >= 400:
        return {
            "origin": origin_url,
            "robots_txt": {"url": robots_url, "status": r.status_code},
            "policy": {},
            "warnings": [
                f"robots_txt_status_{r.status_code} — most crawlers treat "
                f"this as 'allow all'."
            ],
        }

    rp = urllib.robotparser.RobotFileParser()
    rp.parse(r.text.splitlines())

    sample_url = urljoin(origin_url + "/", sample_path.lstrip("/"))
    policy: dict[str, dict[str, Any]] = {}
    for bot, meta in AI_BOTS.items():
        allowed = rp.can_fetch(bot, sample_url)
        policy[bot] = {
            "allowed_for_sample_path": bool(allowed),
            "vendor": meta["vendor"],
            "purpose": meta["purpose"],
            "docs": meta["docs"],
        }

    # Heuristics: warn when site looks like it tried to block AI but missed
    # a major crawler.
    warnings: list[str] = []
    blocking_count = sum(1 for v in policy.values() if not v["allowed_for_sample_path"])
    if blocking_count >= 5 and policy.get("CCBot", {}).get("allowed_for_sample_path"):
        warnings.append(
            "Site blocks several AI bots but allows CCBot. Common Crawl "
            "feeds most LLM training corpora; blocking only the named bots "
            "leaves a large hole."
        )
    if (
        not policy.get("Google-Extended", {}).get("allowed_for_sample_path", True)
        and policy.get("Googlebot", True) is True
    ):
        # Just a friendly note — Google-Extended block is a legitimate
        # opt-out from Gemini training without affecting Search.
        warnings.append(
            "Google-Extended blocked. Confirms Gemini-training opt-out; "
            "Google Search ranking is unaffected."
        )

    return {
        "origin": origin_url,
        "robots_txt": {
            "url": robots_url,
            "status": r.status_code,
            "size_bytes": len(r.text),
        },
        "sample_path": sample_path,
        "policy": policy,
        "summary": {
            "total_ai_bots_checked": len(policy),
            "allowed": sum(1 for v in policy.values() if v["allowed_for_sample_path"]),
            "blocked": blocking_count,
        },
        "warnings": warnings,
    }
