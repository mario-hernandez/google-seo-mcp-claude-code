"""SEO intelligence tools — quick wins, traffic drops, decay, cannibalization, alerts.

These tools wrap the raw Search Analytics API with diagnostic logic that surfaces
actionable findings instead of dumping rows. Ideas adapted (re-implemented) from
Suganthan's GSC MCP (TypeScript) — credit in README.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..analytics import expected_ctr, query_search_analytics
from ...auth import get_webmasters
from ..dates import lag_days, period, prior_period
from ...guardrails import with_meta


def quick_wins(site_url: str, days: int = 28, min_impressions: int = 100, top_n: int = 30) -> dict:
    """Queries currently ranking position 4-15 with highest "lift opportunity".

    Opportunity score = impressions × (CTR_at_pos3 - CTR_actual). Highlights queries
    where a small ranking improvement could yield disproportionate traffic gains.
    """
    start, end = period(days)
    rows = query_search_analytics(
        get_webmasters(), site_url, start, end,
        dimensions=["query"], row_limit=25000, fetch_all=True,
    )
    target_ctr = expected_ctr(3)
    candidates = []
    for r in rows:
        keys = r.get("keys", [])
        impr = r.get("impressions", 0)
        pos = r.get("position", 0)
        ctr = r.get("ctr", 0)
        if impr < min_impressions or pos < 4 or pos > 15:
            continue
        gap = max(0, target_ctr - ctr)
        opportunity = impr * gap
        candidates.append({
            "query": keys[0] if keys else "",
            "impressions": impr,
            "clicks": r.get("clicks", 0),
            "ctr": ctr,
            "position": pos,
            "opportunity_score": opportunity,
            "estimated_extra_clicks_at_pos3": int(round(gap * impr)),
        })
    candidates.sort(key=lambda x: x["opportunity_score"], reverse=True)
    return with_meta(
        candidates[:top_n],
        source="intelligence.quick_wins",
        site_url=site_url,
        period={"start": start, "end": end},
    )


def traffic_drops(
    site_url: str, days: int = 28, top_n: int = 20, min_clicks_prior: int = 20
) -> dict:
    """Pages that lost traffic, classified into Ranking-loss / CTR-collapse / Demand-decline.

    - Ranking loss: avg position got worse by >2 positions.
    - CTR collapse: position stable but CTR < 70% of prior CTR.
    - Demand decline: rankings & CTR roughly stable but impressions dropped >30%.
    """
    cur_s, cur_e = period(days)
    prev_s, prev_e = prior_period(days)
    wm = get_webmasters()
    cur = {tuple(r.get("keys", [])): r for r in query_search_analytics(
        wm, site_url, cur_s, cur_e, dimensions=["page"], row_limit=25000, fetch_all=True,
    )}
    prev = {tuple(r.get("keys", [])): r for r in query_search_analytics(
        wm, site_url, prev_s, prev_e, dimensions=["page"], row_limit=25000, fetch_all=True,
    )}

    drops = []
    for key, p in prev.items():
        if p.get("clicks", 0) < min_clicks_prior:
            continue
        # A page that was in `prev` but not in `cur` has DISAPPEARED — it stopped
        # appearing for any query. Diagnose explicitly; otherwise the default-fill
        # below would mask it as ctr_collapse (zero CTR vs prior CTR).
        if key not in cur:
            drops.append({
                "page": key[0] if key else "",
                "diagnosis": "disappeared",
                "current": {"clicks": 0, "impressions": 0, "ctr": 0, "position": None},
                "previous": {k: p.get(k, 0) for k in ("clicks", "impressions", "ctr", "position")},
                "click_delta": -p.get("clicks", 0),
                "position_delta": None,
                "impressions_delta_pct": -1.0,
            })
            continue

        c = cur[key]
        click_delta = c.get("clicks", 0) - p.get("clicks", 0)
        if click_delta >= 0:
            continue
        delta_pos = c.get("position", 99) - p.get("position", 0)
        prev_impr = p.get("impressions", 0)
        delta_impr_pct = (
            (c.get("impressions", 0) - prev_impr) / prev_impr if prev_impr else 0.0
        )
        ctr_ratio = (c.get("ctr", 0) / p["ctr"]) if p.get("ctr") else 1.0

        if delta_pos > 2:
            cls = "ranking_loss"
        elif ctr_ratio < 0.7 and abs(delta_pos) <= 2:
            cls = "ctr_collapse"
        elif delta_impr_pct < -0.3:
            cls = "demand_decline"
        else:
            cls = "mixed"

        drops.append({
            "page": key[0] if key else "",
            "diagnosis": cls,
            "current": {k: c.get(k, 0) for k in ("clicks", "impressions", "ctr", "position")},
            "previous": {k: p.get(k, 0) for k in ("clicks", "impressions", "ctr", "position")},
            "click_delta": click_delta,
            "position_delta": delta_pos,
            "impressions_delta_pct": delta_impr_pct,
        })
    drops.sort(key=lambda x: x["click_delta"])
    return with_meta(
        drops[:top_n],
        source="intelligence.traffic_drops",
        site_url=site_url,
        period={
            "current": {"start": cur_s, "end": cur_e},
            "previous": {"start": prev_s, "end": prev_e},
        },
    )


def content_decay(site_url: str, top_n: int = 20, min_clicks_p3: int = 10) -> dict:
    """Pages with monotonic decline across 3 consecutive 30-day windows.

    Filters noise: only pages where clicks_p3 > clicks_p2 > clicks_p1 AND clicks_p3 >= threshold.
    Indicates real content decay, not a single-week dip.
    """
    end = lag_days()
    p3 = (end - timedelta(days=29), end)
    p2 = (p3[0] - timedelta(days=30), p3[0] - timedelta(days=1))
    p1 = (p2[0] - timedelta(days=30), p2[0] - timedelta(days=1))

    wm = get_webmasters()

    def fetch(s: date, e: date):
        return {tuple(r.get("keys", [])): r for r in query_search_analytics(
            wm, site_url, s.isoformat(), e.isoformat(),
            dimensions=["page"], row_limit=25000, fetch_all=True,
        )}

    rows_p3 = fetch(*p3)
    rows_p2 = fetch(*p2)
    rows_p1 = fetch(*p1)

    decaying = []
    for key, r3 in rows_p3.items():
        c3 = r3.get("clicks", 0)
        if c3 < min_clicks_p3:
            continue
        r2 = rows_p2.get(key, {})
        r1 = rows_p1.get(key, {})
        c2 = r2.get("clicks", 0)
        c1 = r1.get("clicks", 0)
        # monotonic: most-recent < middle < oldest (decline over time)
        if not (c1 > c2 > c3):
            continue
        decaying.append({
            "page": key[0] if key else "",
            "p1_oldest": {"clicks": c1, "period": [p1[0].isoformat(), p1[1].isoformat()]},
            "p2_middle": {"clicks": c2, "period": [p2[0].isoformat(), p2[1].isoformat()]},
            "p3_recent": {"clicks": c3, "period": [p3[0].isoformat(), p3[1].isoformat()]},
            "total_drop": c1 - c3,
            "drop_pct": (c1 - c3) / c1 if c1 else 0,
        })
    decaying.sort(key=lambda x: x["total_drop"], reverse=True)
    return with_meta(
        decaying[:top_n],
        source="intelligence.content_decay",
        site_url=site_url,
        period={
            "p1": [p1[0].isoformat(), p1[1].isoformat()],
            "p2": [p2[0].isoformat(), p2[1].isoformat()],
            "p3": [p3[0].isoformat(), p3[1].isoformat()],
        },
    )


def cannibalization(
    site_url: str, days: int = 28, min_impressions: int = 50, top_n: int = 20
) -> dict:
    """Queries where >=2 pages on the same site are competing in search results.

    `min_impressions` is applied to the AGGREGATED total per query (not per row),
    so a query with two pages at 30 impressions each (60 total = real cannibalization)
    is not silently filtered out.
    """
    start, end = period(days)
    rows = query_search_analytics(
        get_webmasters(), site_url, start, end,
        dimensions=["query", "page"], row_limit=25000, fetch_all=True,
    )
    bucket: dict[str, list[dict]] = {}
    for r in rows:
        keys = r.get("keys", [])
        if len(keys) < 2:
            continue
        q, p = keys[0], keys[1]
        bucket.setdefault(q, []).append({
            "page": p,
            "clicks": r.get("clicks", 0),
            "impressions": r.get("impressions", 0),
            "ctr": r.get("ctr", 0),
            "position": r.get("position", 0),
        })
    conflicts = []
    for q, pages in bucket.items():
        if len(pages) < 2:
            continue
        total_impr = sum(p["impressions"] for p in pages)
        if total_impr < min_impressions:
            continue
        pages.sort(key=lambda x: x["impressions"], reverse=True)
        conflicts.append({
            "query": q,
            "competing_pages": pages,
            "total_impressions": total_impr,
            "total_clicks": sum(p["clicks"] for p in pages),
        })
    conflicts.sort(key=lambda x: x["total_impressions"], reverse=True)
    return with_meta(
        conflicts[:top_n],
        source="intelligence.cannibalization",
        site_url=site_url,
        period={"start": start, "end": end},
    )


def ctr_opportunities(
    site_url: str, days: int = 28, min_impressions: int = 200, top_n: int = 20
) -> dict:
    """Pages whose CTR is significantly below the expected CTR for their position.

    CTR gap = expected_ctr(pos) - actual_ctr. Tipo "title/meta needs improvement".
    """
    start, end = period(days)
    rows = query_search_analytics(
        get_webmasters(), site_url, start, end,
        dimensions=["page"], row_limit=25000, fetch_all=True,
    )
    out = []
    for r in rows:
        impr = r.get("impressions", 0)
        if impr < min_impressions:
            continue
        pos = r.get("position", 0)
        if pos < 1 or pos > 10:
            continue
        actual = r.get("ctr", 0)
        target = expected_ctr(pos)
        gap = target - actual
        if gap <= 0:
            continue
        out.append({
            "page": r.get("keys", [""])[0],
            "position": pos,
            "actual_ctr": actual,
            "expected_ctr": target,
            "ctr_gap": gap,
            "impressions": impr,
            "potential_extra_clicks": int(round(gap * impr)),
        })
    out.sort(key=lambda x: x["potential_extra_clicks"], reverse=True)
    return with_meta(
        out[:top_n],
        source="intelligence.ctr_opportunities",
        site_url=site_url,
        period={"start": start, "end": end},
    )


def alerts(site_url: str, days: int = 7, severity_threshold: str = "warning") -> dict:
    """Detects regressions in last N days vs prior N days.

    Emits per-entity (query+page) alerts: position_drop, ctr_collapse, click_drop, disappeared.
    Severity: critical (≥2× threshold) > warning. Dedup keeps highest severity per entity.
    """
    cur_s, cur_e = period(days)
    prev_s, prev_e = prior_period(days)
    wm = get_webmasters()
    cur = {tuple(r.get("keys", [])): r for r in query_search_analytics(
        wm, site_url, cur_s, cur_e,
        dimensions=["query", "page"], row_limit=25000, fetch_all=True,
    )}
    prev = {tuple(r.get("keys", [])): r for r in query_search_analytics(
        wm, site_url, prev_s, prev_e,
        dimensions=["query", "page"], row_limit=25000, fetch_all=True,
    )}

    alerts_by_entity: dict[tuple, dict] = {}

    def push(entity: tuple, alert: dict) -> None:
        existing = alerts_by_entity.get(entity)
        rank = {"critical": 2, "warning": 1}
        if not existing or rank[alert["severity"]] > rank[existing["severity"]]:
            alerts_by_entity[entity] = alert

    for entity, p in prev.items():
        if p.get("clicks", 0) < 10 and p.get("impressions", 0) < 100:
            continue
        c = cur.get(entity, {"clicks": 0, "impressions": 0, "ctr": 0, "position": 99})
        if entity not in cur:
            push(entity, {
                "type": "disappeared",
                "severity": "critical",
                "query": entity[0], "page": entity[1],
                "previous": p,
            })
            continue
        # position drop
        d_pos = c["position"] - p["position"]
        if d_pos > 5:
            push(entity, {
                "type": "position_drop", "severity": "critical",
                "query": entity[0], "page": entity[1],
                "delta_position": d_pos, "current": c, "previous": p,
            })
        elif d_pos > 2:
            push(entity, {
                "type": "position_drop", "severity": "warning",
                "query": entity[0], "page": entity[1],
                "delta_position": d_pos, "current": c, "previous": p,
            })
        # ctr collapse (position stable)
        if abs(d_pos) <= 2 and p.get("ctr", 0) > 0:
            ratio = c["ctr"] / p["ctr"]
            if ratio < 0.5:
                push(entity, {
                    "type": "ctr_collapse", "severity": "critical",
                    "query": entity[0], "page": entity[1],
                    "ctr_ratio": ratio, "current": c, "previous": p,
                })
            elif ratio < 0.7:
                push(entity, {
                    "type": "ctr_collapse", "severity": "warning",
                    "query": entity[0], "page": entity[1],
                    "ctr_ratio": ratio, "current": c, "previous": p,
                })
        # click drop
        c_delta = c.get("clicks", 0) - p.get("clicks", 0)
        if c_delta < -50:
            push(entity, {
                "type": "click_drop", "severity": "critical",
                "query": entity[0], "page": entity[1],
                "click_delta": c_delta, "current": c, "previous": p,
            })

    rank = {"critical": 2, "warning": 1}
    threshold_rank = rank.get(severity_threshold, 1)
    filtered = [a for a in alerts_by_entity.values() if rank[a["severity"]] >= threshold_rank]
    filtered.sort(key=lambda x: rank[x["severity"]], reverse=True)
    return with_meta(
        filtered,
        source="intelligence.alerts",
        site_url=site_url,
        period={
            "current": {"start": cur_s, "end": cur_e},
            "previous": {"start": prev_s, "end": prev_e},
        },
    )
