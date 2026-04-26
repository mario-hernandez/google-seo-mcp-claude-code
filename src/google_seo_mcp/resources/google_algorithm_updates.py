"""Google Search algorithm updates — exposed as an MCP resource.

When an agent investigates a traffic drop, knowing which Google updates rolled out
on or around the drop date is half the diagnosis. This resource is intentionally
data-only (not a tool) so the LLM can reference it without issuing a tool call.

Updates are sourced from public Google Search Status announcements. Update this
file as new ones are confirmed; the resource is regenerated on each MCP boot.
"""
from __future__ import annotations

from datetime import date

# Format: (start_date_iso, end_date_iso, name, category, notes)
# Categories: core, spam, helpful_content, product_reviews, system, other
ALGORITHM_UPDATES: list[dict] = [
    # 2026
    {
        "start": "2026-03-05", "end": "2026-03-25",
        "name": "March 2026 Core Update",
        "category": "core",
        "notes": "Broad core update; volatility across most categories.",
    },
    # 2025
    {
        "start": "2025-12-12", "end": "2025-12-22",
        "name": "December 2025 Core Update",
        "category": "core",
        "notes": "Year-end core update; YMYL niches reportedly more affected.",
    },
    {
        "start": "2025-11-19", "end": "2025-11-26",
        "name": "November 2025 Core Update",
        "category": "core",
        "notes": "Broad core update; one-week rollout.",
    },
    {
        "start": "2025-08-15", "end": "2025-09-03",
        "name": "August 2025 Core Update",
        "category": "core",
        "notes": "Major core update; significant SERP volatility.",
    },
    {
        "start": "2025-06-30", "end": "2025-07-17",
        "name": "June 2025 Core Update",
        "category": "core",
        "notes": "Slow-rolling core update with knock-on effects through July.",
    },
    {
        "start": "2025-03-13", "end": "2025-03-27",
        "name": "March 2025 Core Update",
        "category": "core",
        "notes": "Q1 core update.",
    },
    # 2024
    {
        "start": "2024-12-12", "end": "2024-12-18",
        "name": "December 2024 Spam Update",
        "category": "spam",
        "notes": "Targeted scaled content abuse and expired-domain abuse.",
    },
    {
        "start": "2024-11-11", "end": "2024-12-05",
        "name": "November 2024 Core Update",
        "category": "core",
        "notes": "Long rollout (~24 days); affiliate and review sites notably impacted.",
    },
    {
        "start": "2024-08-15", "end": "2024-09-03",
        "name": "August 2024 Core Update",
        "category": "core",
        "notes": "First core update aiming to reduce 'unhelpful' content; partial reversal of Sept 2023 HCU.",
    },
    {
        "start": "2024-06-20", "end": "2024-06-27",
        "name": "June 2024 Spam Update",
        "category": "spam",
        "notes": "Scaled content abuse + site reputation abuse signals strengthened.",
    },
    {
        "start": "2024-05-14", "end": "2024-05-14",
        "name": "AI Overviews launch (US)",
        "category": "system",
        "notes": "AI Overviews replaced SGE; widespread CTR shifts on informational queries.",
    },
    {
        "start": "2024-03-05", "end": "2024-04-19",
        "name": "March 2024 Core Update + Spam Update",
        "category": "core",
        "notes": "Largest core update on record; ~40% reduction of low-quality content claimed by Google.",
    },
    # 2023
    {
        "start": "2023-11-02", "end": "2023-11-28",
        "name": "November 2023 Core Update",
        "category": "core",
        "notes": "Two consecutive core updates (Nov core + Reviews update).",
    },
    {
        "start": "2023-09-14", "end": "2023-09-28",
        "name": "September 2023 Helpful Content Update",
        "category": "helpful_content",
        "notes": "Extreme volatility; many independent sites lost 50%+ traffic.",
    },
    {
        "start": "2023-08-22", "end": "2023-09-07",
        "name": "August 2023 Core Update",
        "category": "core",
        "notes": "Standard core update; ~16-day rollout.",
    },
]


def algorithm_updates_text() -> str:
    """Return a human-readable text representation suitable for an MCP resource."""
    lines = [
        "# Google Search Algorithm Updates (2023–2026)",
        "",
        "Reference list of confirmed Google Search algorithm updates. Use this to",
        "correlate traffic drops detected by `gsc_traffic_drops` or `ga4_anomalies`",
        "with known industry-wide events. A drop coinciding with a core update",
        "rollout date is much more likely to be Google-driven than site-specific.",
        "",
        "Format: dates are inclusive; some updates have a multi-week rollout.",
        "",
    ]
    for u in ALGORITHM_UPDATES:
        line = f"- **{u['start']}** → **{u['end']}** | {u['name']} ({u['category']})"
        if u.get("notes"):
            line += f" — {u['notes']}"
        lines.append(line)
    lines.extend([
        "",
        "Updates are sourced from public Google Search Status announcements.",
        "This list is point-in-time; consult https://status.search.google.com/ for live status.",
    ])
    return "\n".join(lines)


def updates_overlapping(d: str | date) -> list[dict]:
    """Return updates whose rollout window overlaps the given date.

    Useful for tools to call internally — given a detected anomaly date,
    list any concurrent Google updates that might explain it.
    """
    if isinstance(d, str):
        d = date.fromisoformat(d)
    out = []
    for u in ALGORITHM_UPDATES:
        s = date.fromisoformat(u["start"])
        e = date.fromisoformat(u["end"])
        if s <= d <= e:
            out.append(u)
    return out
