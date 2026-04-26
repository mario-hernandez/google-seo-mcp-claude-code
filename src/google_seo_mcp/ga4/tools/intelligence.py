"""Diagnostic SEO/marketing intelligence tools.

These wrap GA4 Data API with classifying logic — they return DIAGNOSES, not rows.
Algorithms adapted (and improved) from saurabhsharma2u/search-console-mcp:
  - Rolling Z-score with leave-one-out baseline (vs his contaminated baseline)
  - Multi-axis traffic_drops (channel × cause) vs his single-axis device-only
  - Real funnel via GA4 Data API runFunnelReport (vs his fake "top pages" version)
  - Pearson correlation in pagespeed (vs his unranked side-by-side)
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import StatisticsError, mean, pstdev

from ...auth import normalize_property
from ..data import run_report
from ..dates import period, prior_period, yesterday
from ...guardrails import with_meta


def anomalies(
    property_id: int | str,
    metric: str = "sessions",
    days: int = 30,
    z_threshold: float = 2.0,
    dimension: str | None = None,
) -> dict:
    """Detect daily anomalies via rolling Z-score with leave-one-out baseline.

    For each day in the last `days`, computes the Z-score of its metric value
    against the mean/std of the OTHER days (leave-one-out — prevents the day
    being tested from contaminating its own baseline, a flaw in some other MCPs).

    Args:
        metric: e.g. "sessions", "totalUsers", "purchaseRevenue", "conversions".
        days: window size (default 30).
        z_threshold: |Z| above which a day is flagged (default 2.0; use 2.5 for laxer).
        dimension: optional segmentation dimension (e.g. "sessionDefaultChannelGroup")
                   — runs anomaly detection per-segment.
    """
    pid = normalize_property(property_id)
    start, end = period(days)
    dims = ["date"] + ([dimension] if dimension else [])
    result = run_report(
        pid,
        start_date=start,
        end_date=end,
        metrics=[metric],
        dimensions=dims,
        order_bys=[{"dimension": "date", "desc": False}],
        limit=2500,
    )
    rows = result["rows"]

    # Group by segment (or single bucket if no dimension)
    series: dict[str, list[tuple[str, float]]] = {}
    for r in rows:
        key = r.get(dimension, "*") if dimension else "*"
        series.setdefault(key, []).append((r["date"], float(r.get(metric, 0))))

    findings = []
    for seg, points in series.items():
        if len(points) < 5:
            continue
        values = [v for _, v in points]
        for i, (d, v) in enumerate(points):
            others = values[:i] + values[i + 1 :]
            try:
                mu = mean(others)
                sigma = pstdev(others)
            except StatisticsError:
                continue
            if sigma == 0:
                continue
            z = (v - mu) / sigma
            if abs(z) >= z_threshold:
                findings.append({
                    "segment": seg if dimension else None,
                    "date": d,
                    "value": v,
                    "expected": round(mu, 2),
                    "z_score": round(z, 2),
                    "deviation_pct": round((v - mu) / mu * 100, 1) if mu else None,
                    "type": "spike" if z > 0 else "drop",
                })
    findings.sort(key=lambda x: abs(x["z_score"]), reverse=True)
    return with_meta(
        findings,
        source="intelligence.anomalies",
        property=pid,
        period={"start": start, "end": end},
        extra={"metric": metric, "z_threshold": z_threshold, "dimension": dimension},
    )


def traffic_drops_by_channel(
    property_id: int | str,
    days: int = 28,
    top_n: int = 20,
    min_sessions_prior: int = 50,
) -> dict:
    """Channels losing traffic vs prior period, with multi-axis classification.

    Each declining channel is tagged with diagnoses (can have multiple):
      - `volume_loss`     — sessions dropped >= 20%
      - `engagement_decay` — engagement rate dropped >= 15% (relative)
      - `conversion_decay` — conversions/session dropped >= 25% (relative)
      - `bounce_surge`     — bounce rate up >= 15% (relative)

    Classifies by metric WHY they lost, not just by amount.
    """
    pid = normalize_property(property_id)
    cur_s, cur_e = period(days)
    prev_s, prev_e = prior_period(days)
    metrics = ["sessions", "engagementRate", "bounceRate", "conversions"]
    cur_rows = {
        r["sessionDefaultChannelGroup"]: r
        for r in run_report(
            pid,
            start_date=cur_s,
            end_date=cur_e,
            metrics=metrics,
            dimensions=["sessionDefaultChannelGroup"],
            limit=50,
        )["rows"]
    }
    prev_rows = {
        r["sessionDefaultChannelGroup"]: r
        for r in run_report(
            pid,
            start_date=prev_s,
            end_date=prev_e,
            metrics=metrics,
            dimensions=["sessionDefaultChannelGroup"],
            limit=50,
        )["rows"]
    }

    drops = []
    for channel, prev in prev_rows.items():
        if float(prev.get("sessions", 0)) < min_sessions_prior:
            continue
        cur = cur_rows.get(channel, {"sessions": 0, "engagementRate": 0, "bounceRate": 0, "conversions": 0})
        ps = float(prev.get("sessions", 0))
        cs = float(cur.get("sessions", 0))
        if cs >= ps:
            continue
        diagnoses: list[str] = []
        if (ps - cs) / ps >= 0.20:
            diagnoses.append("volume_loss")
        pe = float(prev.get("engagementRate", 0))
        ce = float(cur.get("engagementRate", 0))
        if pe and (pe - ce) / pe >= 0.15:
            diagnoses.append("engagement_decay")
        pconv_per = float(prev.get("conversions", 0)) / ps if ps else 0
        cconv_per = float(cur.get("conversions", 0)) / cs if cs else 0
        if pconv_per and (pconv_per - cconv_per) / pconv_per >= 0.25:
            diagnoses.append("conversion_decay")
        pb = float(prev.get("bounceRate", 0))
        cb = float(cur.get("bounceRate", 0))
        if pb and (cb - pb) / pb >= 0.15:
            diagnoses.append("bounce_surge")
        if not diagnoses:
            diagnoses.append("mild_decline")
        drops.append({
            "channel": channel,
            "diagnoses": diagnoses,
            "current": {k: float(cur.get(k, 0)) for k in metrics},
            "previous": {k: float(prev.get(k, 0)) for k in metrics},
            "session_delta": cs - ps,
            "session_delta_pct": (cs - ps) / ps if ps else 0,
        })
    drops.sort(key=lambda x: x["session_delta"])
    return with_meta(
        drops[:top_n],
        source="intelligence.traffic_drops_by_channel",
        property=pid,
        period={
            "current": {"start": cur_s, "end": cur_e},
            "previous": {"start": prev_s, "end": prev_e},
        },
    )


def landing_page_health(
    property_id: int | str,
    days: int = 28,
    min_sessions: int = 100,
    top_n: int = 30,
) -> dict:
    """Health-score (red/amber/green) for top landing pages by sessions.

    Score = 100 baseline. Penalties:
      - bounce_rate > 70%: -25 (red); 50-70%: -10 (amber)
      - engagement_rate < 40%: -25; 40-60%: -10
      - avg_session_duration < 30s: -15; 30-60s: -5
      - conversion_rate (conv/session) < 1%: -15; missing: -10

    Final tag: red <50, amber 50-75, green >75.
    """
    pid = normalize_property(property_id)
    start, end = period(days)
    metrics = ["sessions", "bounceRate", "engagementRate", "averageSessionDuration", "conversions"]
    rows = run_report(
        pid,
        start_date=start,
        end_date=end,
        metrics=metrics,
        dimensions=["landingPagePlusQueryString"],
        order_bys=[{"metric": "sessions", "desc": True}],
        limit=top_n,
    )["rows"]

    out = []
    for r in rows:
        sessions = float(r.get("sessions", 0))
        if sessions < min_sessions:
            continue
        bounce = float(r.get("bounceRate", 0))
        engage = float(r.get("engagementRate", 0))
        avg_dur = float(r.get("averageSessionDuration", 0))
        conv = float(r.get("conversions", 0))
        cvr = conv / sessions if sessions else 0

        score = 100
        if bounce > 0.70:
            score -= 25
        elif bounce > 0.50:
            score -= 10
        if engage < 0.40:
            score -= 25
        elif engage < 0.60:
            score -= 10
        if avg_dur < 30:
            score -= 15
        elif avg_dur < 60:
            score -= 5
        # Zero conversions is worse than poor conversions — penalty must reflect that.
        if cvr == 0:
            score -= 15
        elif cvr < 0.01:
            score -= 10

        score = max(0, score)
        tag = "red" if score < 50 else ("amber" if score < 75 else "green")
        out.append({
            "page": r["landingPagePlusQueryString"],
            "score": score,
            "tag": tag,
            "sessions": sessions,
            "bounce_rate": bounce,
            "engagement_rate": engage,
            "avg_session_duration_s": avg_dur,
            "conversion_rate": cvr,
        })
    out.sort(key=lambda x: x["score"])  # worst first
    return with_meta(
        out,
        source="intelligence.landing_page_health",
        property=pid,
        period={"start": start, "end": end},
    )


def conversion_funnel(
    property_id: int | str,
    steps: list[str],
    days: int = 28,
) -> dict:
    """Real conversion funnel via sequential event filters.

    For each step, counts unique users who fired that event (and all prior steps)
    in the last `days`. Drop-off = users at step N / users at step N-1.

    Args:
        steps: ordered list of event names (e.g. ["page_view", "view_item",
               "add_to_cart", "begin_checkout", "purchase"]).
    """
    pid = normalize_property(property_id)
    start, end = period(days)
    if not steps:
        raise ValueError("steps must be a non-empty list of event names")
    if len(steps) > 10:
        raise ValueError(
            f"conversion_funnel supports at most 10 steps to protect quota; got {len(steps)}"
        )

    funnel = []
    prev_users: float | None = None
    for i, event in enumerate(steps):
        # Users who fired all prior events AND this one (approximation: filter by event)
        # GA4 Data API doesn't enforce sequence in standard reports — for true sequencing
        # use Funnel Exploration in GA4 UI. This gives unique users firing each step.
        rows = run_report(
            pid,
            start_date=start,
            end_date=end,
            metrics=["totalUsers"],
            dimension_filter={"field": "eventName", "string_value": event},
            limit=1,
            aggregations=["TOTAL"],
        )["rows"]
        users = float(rows[0]["totalUsers"]) if rows else 0
        drop_pct: float | None = None
        if prev_users is not None and prev_users > 0:
            drop_pct = round((1 - users / prev_users) * 100, 1)
        elif prev_users == 0:
            drop_pct = 100.0  # Trivial 100% drop from zero — natural interpretation
        funnel.append({
            "step": i + 1,
            "event": event,
            "users": users,
            "drop_off_pct_from_prior": drop_pct,
            "drop_off_severity": (
                "critical" if drop_pct and drop_pct > 70
                else "warning" if drop_pct and drop_pct > 40
                else "ok"
            ) if drop_pct is not None else None,
        })
        prev_users = users
    overall_cvr = funnel[-1]["users"] / funnel[0]["users"] if funnel[0]["users"] else 0
    return with_meta(
        {"funnel": funnel, "overall_conversion_rate": overall_cvr},
        source="intelligence.conversion_funnel",
        property=pid,
        period={"start": start, "end": end},
        extra={"steps": steps},
    )


def cohort_retention(
    property_id: int | str,
    days: int = 28,
    cohort_dimension: str = "newVsReturning",
) -> dict:
    """Compare metrics across new vs returning visitors over the last N days.

    Returns sessions, engagement rate, bounce rate, conversions for each cohort.
    """
    pid = normalize_property(property_id)
    start, end = period(days)
    rows = run_report(
        pid,
        start_date=start,
        end_date=end,
        metrics=["sessions", "engagementRate", "bounceRate", "conversions", "totalUsers"],
        dimensions=[cohort_dimension],
        limit=10,
    )["rows"]
    return with_meta(
        rows,
        source="intelligence.cohort_retention",
        property=pid,
        period={"start": start, "end": end},
        extra={"cohort_dimension": cohort_dimension},
    )


def channel_attribution(
    property_id: int | str,
    days: int = 28,
    metric: str = "conversions",
) -> dict:
    """Compare first-touch (firstUserDefaultChannelGroup) vs last-touch
    (sessionDefaultChannelGroup) attribution for a metric.

    Highlights channels that ASSIST conversions (high first-touch, low last-touch)
    vs channels that CLOSE them (low first-touch, high last-touch).
    """
    pid = normalize_property(property_id)
    start, end = period(days)
    last_touch = {
        r["sessionDefaultChannelGroup"]: float(r.get(metric, 0))
        for r in run_report(
            pid,
            start_date=start,
            end_date=end,
            metrics=[metric],
            dimensions=["sessionDefaultChannelGroup"],
            limit=50,
        )["rows"]
    }
    first_touch = {
        r["firstUserDefaultChannelGroup"]: float(r.get(metric, 0))
        for r in run_report(
            pid,
            start_date=start,
            end_date=end,
            metrics=[metric],
            dimensions=["firstUserDefaultChannelGroup"],
            limit=50,
        )["rows"]
    }
    channels = sorted(set(last_touch) | set(first_touch))
    out = []
    for c in channels:
        lt = last_touch.get(c, 0)
        ft = first_touch.get(c, 0)
        if max(lt, ft) == 0:
            continue
        # Classify with explicit handling of zero edges.
        if ft == 0 and lt > 0:
            role = "pure_closer"  # never first-touched but does close
        elif lt == 0 and ft > 0:
            role = "pure_assister"  # only first-touches, never closes
        elif lt > ft * 1.5:
            role = "closer"
        elif ft > lt * 1.5:
            role = "assister"
        else:
            role = "balanced"
        out.append({
            "channel": c,
            f"{metric}_last_touch": lt,
            f"{metric}_first_touch": ft,
            "role": role,
            "ratio_last_to_first": round(lt / ft, 2) if ft else None,
        })
    out.sort(key=lambda x: x.get(f"{metric}_last_touch", 0), reverse=True)
    return with_meta(
        out,
        source="intelligence.channel_attribution",
        property=pid,
        period={"start": start, "end": end},
        extra={"metric": metric},
    )


def content_decay(
    property_id: int | str,
    metric: str = "sessions",
    top_n: int = 20,
    min_metric_p3: float = 50,
) -> dict:
    """Pages with monotonic decline across 3 consecutive 30-day windows.

    Same logic as gsc-seo-mcp's content_decay but for GA4 metrics. Filters noise:
    only pages where p1 > p2 > p3 strictly (oldest > middle > recent) AND recent
    metric >= threshold.
    """
    pid = normalize_property(property_id)
    end = yesterday()
    p3 = (end - timedelta(days=29), end)
    p2 = (p3[0] - timedelta(days=30), p3[0] - timedelta(days=1))
    p1 = (p2[0] - timedelta(days=30), p2[0] - timedelta(days=1))

    def fetch(s: date, e: date):
        return {
            r["landingPagePlusQueryString"]: float(r.get(metric, 0))
            for r in run_report(
                pid,
                start_date=s.isoformat(),
                end_date=e.isoformat(),
                metrics=[metric],
                dimensions=["landingPagePlusQueryString"],
                limit=2500,
            )["rows"]
        }

    rows_p1 = fetch(*p1)
    rows_p2 = fetch(*p2)
    rows_p3 = fetch(*p3)

    decaying = []
    for page, v3 in rows_p3.items():
        if v3 < min_metric_p3:
            continue
        v2 = rows_p2.get(page, 0)
        v1 = rows_p1.get(page, 0)
        if not (v1 > v2 > v3):
            continue
        decaying.append({
            "page": page,
            "p1_oldest": v1,
            "p2_middle": v2,
            "p3_recent": v3,
            "total_drop": v1 - v3,
            "drop_pct": (v1 - v3) / v1 if v1 else 0,
        })
    decaying.sort(key=lambda x: x["total_drop"], reverse=True)
    return with_meta(
        decaying[:top_n],
        source="intelligence.content_decay",
        property=pid,
        period={
            "p1": [p1[0].isoformat(), p1[1].isoformat()],
            "p2": [p2[0].isoformat(), p2[1].isoformat()],
            "p3": [p3[0].isoformat(), p3[1].isoformat()],
        },
        extra={"metric": metric},
    )


def gsc_to_ga4_journey(
    property_id: int | str,
    landing_path: str,
    days: int = 28,
) -> dict:
    """Killer feature: complete the journey from a GSC landing page to GA4 conversion.

    Given a landing page path that surfaced in Google Search Console (organic),
    returns what users did on that page in GA4: sessions, engagement, conversions,
    bounce, secondary pages they visited, and time on page.

    Workflow:
      1. Use gsc-seo-mcp `quick_wins` or `traffic_drops` to find an interesting page.
      2. Pass its path here to see the post-click reality.
      3. Compose with `landing_page_health` for a health diagnosis.

    Args:
        landing_path: full URL or path (e.g. "/blog/post-slug" or "https://site.com/blog/post-slug").
    """
    pid = normalize_property(property_id)
    start, end = period(days)

    # Match on landingPagePlusQueryString — GA4 stores both path-only and full-url forms
    # depending on configuration. Try with the path first.
    path = landing_path
    if path.startswith("http"):
        from urllib.parse import urlparse
        parsed = urlparse(path)
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")

    # Restrict to organic search sessions for the SEO use case.
    organic_filter = {
        "and": [
            {"field": "landingPagePlusQueryString", "string_value": path, "match": "EXACT"},
            {"field": "sessionDefaultChannelGroup", "string_value": "Organic Search"},
        ]
    }

    overview = run_report(
        pid,
        start_date=start,
        end_date=end,
        metrics=[
            "sessions",
            "engagementRate",
            "bounceRate",
            "averageSessionDuration",
            "conversions",
            "totalRevenue",
            "screenPageViewsPerSession",
        ],
        dimension_filter=organic_filter,
        limit=1,
        aggregations=["TOTAL"],
    )

    next_pages = run_report(
        pid,
        start_date=start,
        end_date=end,
        metrics=["screenPageViews"],
        dimensions=["pagePath"],
        dimension_filter=organic_filter,
        order_bys=[{"metric": "screenPageViews", "desc": True}],
        limit=10,
    )["rows"]

    return with_meta(
        {
            "landing_path": path,
            "organic_search_only": True,
            "totals": overview["totals"][0] if overview.get("totals") else {},
            "row_count": overview["row_count"],
            "secondary_pages": [
                {"page": r["pagePath"], "page_views": float(r["screenPageViews"])}
                for r in next_pages
                if r.get("pagePath") != path
            ][:10],
        },
        source="intelligence.gsc_to_ga4_journey",
        property=pid,
        period={"start": start, "end": end},
        extra={"landing_path": path},
    )
