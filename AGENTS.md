# AGENTS.md — Operator's Guide

> Drop this file into your agent's context (Claude Code, Cursor, Windsurf) to maximize what the MCP can do. It's the synthesis of three expert perspectives — technical SEO, local SEO + SERP intent, and marketing/growth analytics — into one operating manual.

## Table of contents

1. [Mental model — the seven commandments](#1-mental-model--the-seven-commandments)
2. [Tool inventory](#2-tool-inventory)
3. [Playbooks — when the user says X, run Y](#3-playbooks--when-the-user-says-x-run-y)
4. [Decision trees](#4-decision-trees)
5. [Anti-patterns — what the agent must NOT do](#5-anti-patterns--what-the-agent-must-not-do)
6. [Argument cookbook](#6-argument-cookbook)
7. [Inference workarounds — what this MCP doesn't measure but you can infer](#7-inference-workarounds)
8. [Reporting templates](#8-reporting-templates)
9. [Edge cases](#9-edge-cases)
10. [Output formatting rules](#10-output-formatting-rules)

---

## 1. Mental model — the seven commandments

1. **Provenance first.** Every tool returns `{"data": ..., "_meta": {source, site_url|property, period, fetched_at}}`. Quote a number → quote its `_meta.period` and `_meta.source` with it. Cross-platform tools cite TWO periods (GSC has 3-day lag, GA4 has 1-day lag) — quote both.
2. **Cross-platform > single-source.** The 6 `cross_*` tools are the differentiators. Use them first for anything multi-faceted (ROI, attribution, journey, prioritization). Drop into `gsc_*` / `ga4_*` only for surgical follow-up.
3. **Diagnoses, not data dumps.** Tools like `gsc_traffic_drops` return classifications (`ranking_loss`, `ctr_collapse`, `demand_decline`). Pass these through; don't replace with your own narrative.
4. **Sessions are vanity. Revenue is sanity.** Never report "organic up 40%" without `cross_seo_to_revenue_attribution`. If revenue didn't move, the win isn't real — it's brand search, bots, or misattributed direct.
5. **Don't extrapolate.** GSC 3-day lag means a 7-day window is really 4 usable days. If a tool returns `min_metric_p3 < threshold`, the row is statistical noise — flag it, don't rank it.
6. **Read-only by default.** Destructive ops (sitemap submission) require `GSC_ALLOW_DESTRUCTIVE=true`. Even when enabled, ask the user before submitting.
7. **This MCP is GSC + GA4 only.** No GMB API, no SERP scraper, no AI Overview detector. SERP feature impact must be **inferred** from click-impression-CTR patterns combined with `resource://algorithm-updates` — see [§7 workarounds](#7-inference-workarounds).

---

## 2. Tool inventory

**33 tools + 1 reference resource**. One-line *use-when* per tool. Full signatures in source.

### 🔄 Cross-platform (6) — the differentiators
| Tool | Use when |
|---|---|
| `cross_traffic_health_check` | First call for any new site; verifies tracking before further analysis. |
| `cross_opportunity_matrix` | "Where do I invest SEO budget?" Auto-calibrated 4-quadrant prioritization. |
| `cross_seo_to_revenue_attribution` | "What's our SEO ROI?" / "Which queries pay?" |
| `cross_landing_page_full_diagnosis` | One-call triage of a single page (GSC ranking + cannibalization + GA4 behavior + score). |
| `cross_gsc_to_ga4_journey` | "What did users do after they clicked?" |
| `cross_multi_property_comparison` | Multi-location / agency dashboards (up to 50 properties in parallel). |

### 🔎 GSC (12)
| Tool | Use when |
|---|---|
| `gsc_list_sites` | Discovery / first call to enumerate. |
| `gsc_inspect_url` | Indexing diagnosis on a single URL. |
| `gsc_list_sitemaps` | Verify sitemap coverage. |
| `gsc_submit_sitemap` | (gated, destructive) Submit new sitemap. |
| `gsc_search_analytics` | Custom query — generic escape hatch. |
| `gsc_site_snapshot` | KPI block for monthly reports (clicks/impressions/CTR/pos vs prior). |
| `gsc_quick_wins` | "Where can I rank a position higher?" |
| `gsc_traffic_drops` | Classifies pages losing traffic into `ranking_loss`/`ctr_collapse`/`demand_decline`. |
| `gsc_content_decay` | Pages with monotonic 3-window decline (filters single-week noise). |
| `gsc_cannibalization` | ≥2 pages competing for the same query. |
| `gsc_ctr_opportunities` | Pages with CTR far below position-expected. |
| `gsc_alerts` | Position drops, CTR collapses, disappeared queries (last 7 days). |

### 📈 GA4 (13)
| Tool | Use when |
|---|---|
| `ga4_list_properties` | Discovery / first call. |
| `ga4_get_property_details` | Timezone, currency, service level. |
| `ga4_search_schema` | Find dim/metric names by keyword (avoids dumping ~10k tokens). |
| `ga4_list_schema_categories` | Cheap discovery of available schema. |
| `ga4_estimate_query_size` | **ALWAYS** run before any wide `ga4_query` (cheap row-count probe). |
| `ga4_query` | Generic escape hatch — prefer specialized tools first. |
| `ga4_anomalies` | Daily spikes/drops via leave-one-out rolling Z-score. |
| `ga4_traffic_drops_by_channel` | Channels in decline, multi-axis (volume / engagement / conversion / bounce). |
| `ga4_landing_page_health` | Health score (red/amber/green) per landing page. |
| `ga4_conversion_funnel` | Step-by-step user counts with severity-tagged drop-off (max 10 steps). |
| `ga4_cohort_retention` | New vs returning visitor metrics. |
| `ga4_channel_attribution` | First-touch vs last-touch (assister/closer/balanced). |
| `ga4_content_decay` | Pages with 3-window monotonic decline on any GA4 metric. |

### 🛠️ Meta (2)
| Tool | Use when |
|---|---|
| `get_capabilities` | First call when auth is uncertain — also returns the tool catalog. |
| `reauthenticate` | Reset clients after credential changes. |

### 📚 MCP Resource (1)
| Resource | Use when |
|---|---|
| `google-seo://algorithm-updates` | Correlate detected drops/anomalies with confirmed Google updates 2023-2026 (core, spam, helpful content, AI Overviews launches). |

---

## 3. Playbooks — when the user says X, run Y

### Discovery & onboarding
| User says | Agent runs |
|---|---|
| "Audit this new site" | `get_capabilities` → `gsc_list_sites` + `ga4_list_properties` → `cross_traffic_health_check(days=28)` → `gsc_site_snapshot(days=28)` → `cross_opportunity_matrix(days=28, top_n=20)` → `gsc_alerts(days=7)` |
| "Verify tracking is healthy" | `cross_traffic_health_check(days=28)` — if not `healthy`, STOP all analysis until tracking is fixed |

### Diagnostics — drops, anomalies, technical issues
| User says | Agent runs |
|---|---|
| "Why did organic traffic drop?" | `cross_traffic_health_check` → `gsc_traffic_drops(min_clicks_prior=20)` → `ga4_traffic_drops_by_channel` → for top 3 affected pages: `gsc_inspect_url` + read `resource://algorithm-updates` for the drop date |
| "Is this spike/dip real?" | `ga4_anomalies(z_threshold=2.0)` → if anomaly date confirmed: `resource://algorithm-updates` + `gsc_search_analytics` for the same date |
| "Are old blog posts decaying?" | `gsc_content_decay` AND `ga4_content_decay` — pages flagged by BOTH = refresh priority |
| "Cannibalization between pages?" | `gsc_cannibalization(min_impressions=50)` → for top conflicts: `gsc_search_analytics(dimensions=['query','page'])` filtered to those URLs → `cross_landing_page_full_diagnosis` for both |
| "Is this page indexed / why isn't it ranking?" | `gsc_inspect_url` → if indexed: `gsc_search_analytics` filtered to the page → `cross_landing_page_full_diagnosis` |
| "Did we lose a featured snippet?" | `gsc_traffic_drops(min_clicks_prior=20)` looking for queries with stable impressions but halved clicks AND position 1-3 |

### Prioritization & opportunities
| User says | Agent runs |
|---|---|
| "Where should I invest SEO budget?" | `cross_opportunity_matrix(days=28, top_n=20)` → `cross_seo_to_revenue_attribution(days=90, top_n=30)` → `gsc_quick_wins(days=28)` → rank by revenue × effort |
| "Page X has CTR 1.2% in pos 2 — what do I do?" | `gsc_ctr_opportunities` → `cross_landing_page_full_diagnosis(page_url=X)` → recommend SERP/title/meta rewrite |

### Conversion & ROI (the C-suite questions)
| User says | Agent runs |
|---|---|
| "What's our SEO ROI this month?" | `cross_seo_to_revenue_attribution(days=28, top_n=50, min_clicks=10)` → sum `attributed_revenue`. If user knows monthly SEO spend, compute ROI. **Cite both periods.** |
| "Brand vs non-brand split + which converts" | `gsc_search_analytics(dimensions=['query'], row_limit=25000)` → partition locally with brand regex → cross with `ga4_query(dimensions=['firstUserSource','sessionDefaultChannelGroup'])` filtered to organic |
| "Conversion funnel: where do users drop?" | `ga4_conversion_funnel(steps=[...])` (max 10) → focus on `drop_off_severity = critical` |
| "New vs returning — who pays?" | `ga4_cohort_retention(cohort_dimension='newVsReturning')` + `ga4_query` segmenting `purchaseRevenue` |
| "Channels: assister vs closer?" | `ga4_channel_attribution(metric='conversions')` THEN `metric='totalRevenue'` |
| "Is organic cannibalizing paid?" | `ga4_query(dimensions=['sessionDefaultChannelGroup','landingPagePlusQueryString'])` — same landings paid vs organic; cross with `gsc_cannibalization` |

### Multi-location / agency
| User says | Agent runs |
|---|---|
| "Compare 12 locations by organic traffic" | `cross_multi_property_comparison(property_ids=[...], metric='sessions', dimension='sessionDefaultChannelGroup', days=28)` → filter `Organic Search` |
| "Worst performer of all my clients" | `cross_traffic_health_check` for each → tier red/amber/green → for red ones: `cross_opportunity_matrix(top_n=10)` |

### Specific page / query deep-dives
| User says | Agent runs |
|---|---|
| "Full diagnosis on /this-page" | `cross_landing_page_full_diagnosis(page_url=...)` (one shot, returns score+issues) |
| "What did users do after they clicked on /this-page?" | `cross_gsc_to_ga4_journey(landing_path=..., days=28)` |

---

## 4. Decision trees

### When the user mentions "drop / lost traffic / down"
```
1. cross_traffic_health_check
   if tracking_gap:    STOP. Report tracking issue. Don't diagnose SEO.
   if filter_issue:    Flag the data integrity issue, then proceed cautiously.
   if no_organic_data: Confirm with the user; site may be too new.
2. gsc_traffic_drops(min_clicks_prior=20)
   if ranking_loss in N pages:
       → check resource://algorithm-updates for the drop date
       → gsc_inspect_url on the worst 3 pages
   if ctr_collapse:
       → likely SERP feature change (snippet lost, AI Overview), see §7
3. ga4_traffic_drops_by_channel  → confirms which channel axis
4. Compose answer with diagnoses + provenance citations.
```

### When the user asks "is X working / ROI / where to invest"
```
1. NEVER answer with sessions alone.
2. cross_seo_to_revenue_attribution(days=90)  # 90d for stable attribution
3. If revenue == 0 across the board:
       a. ga4_conversion_funnel with hypothesized steps
       b. If funnel returns 0 users at step 1 → events don't fire, GA4 misconfig.
          STOP. Tell user. DON'T conclude SEO has no ROI.
4. cross_opportunity_matrix(top_n=20) for forward-looking priorities
5. gsc_quick_wins for low-effort wins
6. Rank tasks by revenue_per_click × traffic_potential / effort_estimate
```

### When the user asks Local-specific questions
```
Has client lost organic traffic?
├─ YES → gsc_traffic_drops(min_clicks_prior=20)
│   ├─ Drop concentrated in 1-3 URLs → cross_landing_page_full_diagnosis(each)
│   ├─ Drop across all locations evenly → resource://algorithm-updates (core update?)
│   └─ Drop only in branded queries → GMB/reputation issue (out of MCP scope)
└─ NO → opportunities mode
    ├─ Multi-location → cross_multi_property_comparison → rank by deficit
    └─ Single location → cross_opportunity_matrix(min_impressions=100)
```

---

## 5. Anti-patterns — what the agent must NOT do

1. **Don't quote a number without `_meta.period` and `_meta.source`.** "Clicks dropped 30%" is useless without the comparison window cited inline.
2. **Don't run `gsc_search_analytics` with no dimensions and `row_limit=25000` blindly.** Use `gsc_site_snapshot` for totals, `ga4_estimate_query_size` to budget GA4 queries.
3. **Don't extrapolate trends from <14 days.** Tell the user when sample is thin.
4. **Don't run destructive tools without explicit confirmation.** `gsc_submit_sitemap` is gated for a reason.
5. **Don't conflate GSC `page` (absolute URL) with GA4 `landingPagePlusQueryString` (path-only)** when reasoning manually. The `cross_*` tools normalize internally — use them.
6. **Don't ignore `cross_traffic_health_check` warnings.** If GA4 stopped receiving organic, every downstream diagnosis is wrong.
7. **Don't recommend action from rows below `min_*` thresholds.** Defaults exist for statistical reasons.
8. **Don't claim cannibalization from a single query.** Trust the tool's flag, not raw `search_analytics` rows.
9. **Don't use `ga4_query` when a specialized tool exists.** Anomalies → `ga4_anomalies`. Funnel → `ga4_conversion_funnel`. Generic `ga4_query` is the escape hatch, not the default.
10. **Don't dump `ga4_list_schema_categories` output into the answer.** Use `ga4_search_schema(keyword=...)` for the 5-10 fields actually relevant.
11. **Don't conclude "SEO has no ROI" when revenue=0 across the board.** Check the funnel first — 70% of those cases are GA4 misconfig.
12. **Don't fabricate AI Overview presence.** This MCP can't measure it directly. Use the inference protocol in §7.

---

## 6. Argument cookbook

Tunings by site profile. Override defaults only when the site profile justifies it.

### `gsc_quick_wins(min_impressions=N, top_n=M)`
- New/niche/local (<500 clicks/mo): `min_impressions=25-50`
- Medium SaaS/ecommerce (1k-50k clicks/mo): default `100`
- Enterprise (>50k clicks/mo): `min_impressions=500` to cut noise

### `gsc_traffic_drops(min_clicks_prior=N)`
- Small sites: `5-10`
- Medium: default `20`
- Enterprise: `50-100`

### `gsc_cannibalization(min_impressions=50)`
- Default works for most.
- Ecommerce with 1000+ category pages: `top_n=50`.

### `gsc_content_decay(min_clicks_p3=10)`
- Below 10 the p3 window is noise.
- Sites >10k clicks/mo: raise to `25`.

### `gsc_ctr_opportunities(min_impressions=200, days=28)`
- 200 is the floor for CTR being statistically meaningful.
- For local: extend `days=90` (impression volume per query is lower).

### `ga4_anomalies(metric=..., z_threshold=N)`
- Sessions: default `2.0`. High-volume sites: `2.5`. Tiny sites: `1.8`.
- For growth alerting, prefer `metric='purchaseRevenue'` or `metric='conversions'` over sessions.
- Segment with `dimension='sessionDefaultChannelGroup'` to catch "paid drop hidden by organic spike".
- Local: `dimension='deviceCategory'` because mobile is far more volatile.

### `ga4_landing_page_health(min_sessions=100)`
- Drop to `30` for medium sites; `500+` for enterprise.

### `cross_opportunity_matrix(top_n=20)`
- The tool **auto-calibrates** the impression threshold by median. Don't override `min_impressions` unless you have <50 candidates.

### `cross_seo_to_revenue_attribution(days=90, min_clicks=10)`
- Use 90 days, not 28. Revenue attribution needs sample.
- Drop `min_clicks` to 5 for sites <50k monthly clicks; raise to 50 for enterprise.

### `cross_multi_property_comparison(max_concurrent=5)`
- Default 5 is safe. Raise carefully — GA4 rate-limits per-property tokens, not globally.

### `gsc_search_analytics(search_type=...)`
- Default `"web"`. For visual verticals (restaurants, hotels, real estate) **always run `"image"` in parallel** — image SERP traffic is often 30-40% of discovery.

### `ga4_query` — always pre-budget
- Run `ga4_estimate_query_size` BEFORE any query with >5 dimensions or >30 days.

---

## 7. Inference workarounds

What the MCP doesn't measure but you can infer.

### AI Overview impact (no SERP API)
1. `gsc_search_analytics` for a pre-AIO baseline period (before May 14 2024 US, or before the relevant rollout from `resource://algorithm-updates`).
2. Same call for a post-AIO period.
3. Filter both to `position ≤ 3` AND `impressions ≥ 200`.
4. Inner-join on `(query, page)`. Compute `ctr_delta = ctr_post - ctr_pre`.
5. Queries with `ctr_delta < -0.05` AND impressions stable (±15%) = **high-confidence AIO hits**.
6. Tag and surface in `gsc_ctr_opportunities` follow-up.

### Brand vs non-brand
1. Get a brand regex confirmed by the user (don't guess).
2. `gsc_search_analytics(dimensions=['query'], row_limit=25000)`.
3. Partition rows locally by regex match.
4. For per-bucket revenue: `ga4_query` filtered to organic + landing page; cross with `cross_seo_to_revenue_attribution` per landing-page partition.
5. Brand traffic typically converts 3-8× non-brand. If brand >70% of revenue, "SEO" is mostly demand capture, not generation — set CMO expectations.

### Featured snippet / SERP feature won-or-lost
- `gsc_traffic_drops(min_clicks_prior=20)` looking for queries where impressions stayed flat but clicks halved AND position is 1-3 → **snippet lost**.
- Inverse pattern (clicks doubled at stable impressions) → **snippet won**.

### Multi-location with single property
If URLs are city-slugged (`/madrid/`, `/barcelona/`):
- `gsc_search_analytics(dimensions=['page'])` then group by slug.
- For GA4: use `dimensions=['city','landingPagePlusQueryString']` and segment.

### "Near me" query isolation
GSC doesn't return user location. Proxy: `gsc_search_analytics(dimensions=['query','country'])` + post-filter for tokens (`near me`, `cerca`, `[city]`, `open now`). Imperfect but directional.

### Local pack ranking
`position` in `gsc_search_analytics` is **web ranking only** — does not reflect map-pack position. To estimate map-pack health, use `gsc_inspect_url` on each location page combined with `cross_landing_page_full_diagnosis`.

---

## 8. Reporting templates

Three ready-to-paste prompts. Replace `{site}` and `{property}` with the user's actual values.

### Weekly growth digest

```
You are running a weekly growth digest for site_url={site} and property_id={property}.

Pipeline (run in order):
1. cross_traffic_health_check(site_url, property_id, days=7)  — output must include "healthy"/"warning"/"critical"
2. ga4_anomalies(property_id, metric='conversions', days=7, z_threshold=2.5)
3. ga4_anomalies(property_id, metric='purchaseRevenue', days=7, z_threshold=2.5)
4. ga4_traffic_drops_by_channel(property_id, days=7)
5. cross_seo_to_revenue_attribution(site_url, property_id, days=7, top_n=10)

Compose a 5-bullet digest:
- WoW revenue delta with attribution split
- Top assister channel
- Top decaying page
- Top SEO winner
- One risk to watch

Cite _meta on every number. Do not extrapolate beyond the periods reported. No emojis.
```

### Monthly executive report (CMO-ready)

```
Build a CMO-ready monthly SEO report for site_url={site} and property_id={property} covering the last 30 days.

Pipeline (run sequentially):
1. cross_traffic_health_check(days=30)               — confirm no tracking gaps
2. gsc_site_snapshot(days=30)                        — top-line KPIs
3. cross_seo_to_revenue_attribution(days=90, top_n=50)  — revenue context (90d window)
4. ga4_channel_attribution(days=30, metric='totalRevenue')
5. ga4_channel_attribution(days=30, metric='conversions')
6. ga4_landing_page_health(days=30, min_sessions=100)
7. cross_opportunity_matrix(days=30, top_n=10)       — top priorities
8. gsc_content_decay(top_n=10)                       — risks
9. gsc_quick_wins(days=30, top_n=15)                 — wins ranked by impact
10. ga4_anomalies(days=30, z_threshold=2.0)          — outliers
11. gsc_alerts(days=30, severity_threshold='warning')

Output structure (≤800 words):
- Executive summary (3 sentences, period cited)
- 5 KPIs: clicks, impressions, avg position, conversions, revenue with WoW/MoM delta
- Revenue attribution split (organic vs others, brand vs non-brand if confirmed)
- Top 3 priorities with $ impact estimate and effort
- 2 technical findings (alerts + indexing)
- Next-month plan (3 actions tied to specific tool data)

Rules: cite _meta.period for every number. Don't extrapolate. Flag anything with insufficient sample. No emojis.
```

### Local agency dashboard (multi-client)

```
Build an agency-wide weekly dashboard for clients=[{name, site_url, property_id}, ...].

Step 1 — Health snapshot:
  for each client: cross_traffic_health_check(site_url, property_id, days=7)
  Tier red/amber/green

Step 2 — Per-client opportunities (red + amber tiers):
  for each: cross_opportunity_matrix(days=28, top_n=10)

Step 3 — Multi-location chains (clients with multiple GA4 properties):
  cross_multi_property_comparison(property_ids=client.locations, metric='sessions', dimension='sessionDefaultChannelGroup', days=28)
  Identify worst-performing location per chain.

Step 4 — Algorithm context:
  read resource://algorithm-updates  → tag drops to known updates

Step 5 — Compose dashboard rows:
  one row per client × {sessions Δ, organic Δ, top quick win, top decay, alerts count, tier}
  Cite _meta.period.gsc and _meta.period.ga4 separately for each row.
```

---

## 9. Edge cases

### Small / new sites (<100 clicks/mo)
- Most threshold-based tools return empty. Lower `min_impressions` to `25-50`, `min_clicks_prior` to `5-10`.
- If still empty: the issue is **content/indexation**, not optimization. Pivot to `gsc_inspect_url` on key pages and `gsc_list_sitemaps`.
- Don't fabricate recommendations from empty data. Say *"no statistically meaningful opportunities at current traffic levels; baseline established for re-audit in 60 days"* and cite `_meta.period`.

### Enterprise sites (>100k clicks/mo)
- Raise thresholds to cut noise: `min_impressions=500`, `min_clicks_prior=100`, `z_threshold=2.5`.
- ALWAYS pre-budget GA4 queries with `ga4_estimate_query_size`.
- For per-property rate limits, use `cross_multi_property_comparison(max_concurrent=3)` instead of 5 to avoid quota exhaustion.

### Multi-language sites (es/en/fr)
- Filter post-call by URL prefix (`page.startswith("/es/")`).
- Don't trust automatic query-language detection — many "Spanish" queries are actually Catalan or Portuguese.

### GA4 without ecommerce config
- `purchaseRevenue` and `totalRevenue` always 0.
- `cross_seo_to_revenue_attribution` returns rows with $0 attribution.
- **Don't conclude "SEO has no ROI"** — flag the gap, suggest GA4 ecommerce setup.

### Heavy ad-blocker traffic (DACH, tech audiences)
- Systematic gap: GSC organic clicks > GA4 organic sessions.
- `cross_traffic_health_check` flags this as `tracking_gap`.
- Apply +15-30% upward correction on GA4 organic when discussing with the user, **and disclose**.

### Mis-named conversion events
- `ga4_conversion_funnel` silently returns 0 users on bad step names.
- Pre-validate with `ga4_search_schema(keyword='<event>')` before composing the funnel call.

### Consent Mode v2 modeled data
- GA4 returns blended modeled+observed.
- Don't reconcile to penny-level with backend revenue. Expect 5-15% drift.

### GSC property type mismatch
- Domain (`sc-domain:example.com`) vs URL-prefix (`https://example.com/`) properties have different data.
- Cross-platform path normalization handles both, but if `site_url` doesn't match the registered property, attribution joins return empty.
- Always start a new site with `gsc_list_sites()` and **copy the exact `site_url` string returned**.

### Holiday seasonality
- `ga4_anomalies` with leave-one-out Z-score handles baseline well, but 7-day windows during holidays produce false positives.
- Always cross-check `resource://algorithm-updates` AND a manual seasonality calendar before flagging an anomaly as algorithmic.

### Image-heavy verticals
- Restaurants, hotels, real estate, salons can have 30-40% of discovery via Google Images.
- ALWAYS run `gsc_search_analytics(search_type='image')` in parallel to `'web'` for these verticals. Default `'web'` undercounts dramatically.

---

## 10. Output formatting rules

When composing user-facing answers:

1. **Cite `_meta` inline.** Numbers + period + source. Example: *"Organic clicks down 27% (`gsc_site_snapshot`, period 2026-03-27→2026-04-23)."*
2. **For cross-platform claims, cite both periods.** Example: *"GSC clicks 477 (period 2026-03-27→2026-04-23) vs GA4 sessions 290 (period 2026-03-29→2026-04-25), ratio 0.61 — `healthy`."*
3. **Use the diagnosis labels verbatim.** `ranking_loss` not "ranking lost". `ctr_collapse` not "CTR fell". The agent's job is to pass through tool output, not paraphrase.
4. **Flag insufficient sample.** Example: *"3 quick wins found, but min_impressions threshold reached only by edge cases — directional, not statistical."*
5. **Tag inferences explicitly.** *"AI Overview presence is **inferred**, not measured."* (per §7).
6. **End with provenance footer.** *"Numbers cited from `_meta.period.gsc=[..]` / `_meta.period.ga4=[..]`, fetched_at=[..]."*
7. **No emojis in client-facing reports.** Reserve for internal/dev contexts.

---

_Generated from a synthesis of three specialist perspectives: technical SEO/SaaS (Aleyda Solis mode), local SEO + SERP intent (Joy Hawkins mode), marketing & growth analytics (Avinash Kaushik mode). Last updated: 2026-04-26._
