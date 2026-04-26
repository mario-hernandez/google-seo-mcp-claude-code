# Why no GSC or GA4 MCP alone is enough — and what cross-platform tools unlock

> Status: DRAFT — to be reviewed before publishing on dev.to + LinkedIn.

---

I spent a weekend auditing seven open-source MCP servers for Google Search Console and Google Analytics 4. They're all built by competent people. They all do roughly the same thing: wrap one Google API as an MCP server so Claude or Cursor can query it.

And every single one of them is missing the same five things — because **those five things require both APIs in the same process**.

## The question that breaks every single-source MCP

Imagine you're a SEO consultant. Your client asks:

> *"My organic traffic is down 18% this month. What's broken?"*

With a GSC MCP, Claude can tell you:

- Page X dropped 7 ranking positions on its main query (`ranking_loss`)
- Page Y kept its position but its CTR collapsed (likely a SERP feature)
- Three queries are cannibalizing each other

Useful. But also: incomplete.

Because the question that *actually* matters is:

> *"Are these the pages and queries that drive revenue?"*

Without GA4 conversion data, GSC tells you what's broken — but not which broken thing **costs money**. A page that dropped from #4 to #11 is bad if it converts at 5%; it's irrelevant if it converts at 0% with 80% bounce rate.

The reverse is also true. A GA4 MCP can spot that organic conversions cratered, but cannot tell you whether the cause is ranking loss, CTR collapse, demand decline, or a tracking break that makes GA4 misclassify visits.

You need both. And you need the agent to reason **across both**, in one tool call, without hallucinating the join.

## The six tools that only exist when GSC and GA4 share auth

I unified my own GSC and GA4 MCPs into one (`google-seo-mcp-claude-code`). The merge unlocked five tools that none of the seven competitors expose, because none of them speak both APIs:

### 1. `cross_traffic_health_check`

Compares GSC organic clicks vs GA4 organic sessions over the same period. Returns a diagnosis:

- **`tracking_gap`** (ratio < 0.6): GA4 missing organic traffic. Consent banner blocking on first page-view, channel-group rules wrong, broken JS on landings.
- **`filter_issue`** (ratio > 1.4): GA4 reports more sessions than searches. Bot traffic, internal traffic, mis-classified organic.
- **`healthy`** (0.6–1.4): both systems agree.

This is the **first** tool I'd run on any new client. It tells you whether the data you're about to analyze is even real.

### 2. `cross_opportunity_matrix`

Pages ranking 4–15 in GSC are "quick wins". Pages with high GA4 conversion rate are "valuable". The intersection is gold:

- **`high_impact`**: high opportunity AND high conversion → rank these up first.
- **`worth_optimizing`**: high opportunity, low conversion → rank up + improve the page.
- **`good_but_capped`**: already converting, GSC ceiling hit → leave alone.
- **`low_priority`**: low on both → ignore.

A pure-GSC quick_wins tool ranks pages by *potential clicks*. A cross-platform matrix ranks them by *potential revenue*. Different list, every time.

### 3. `cross_seo_to_revenue_attribution`

For each top organic query, distributes GA4 revenue proportionally by GSC click-share on the landing page. Approximate, but it answers the holy-grail question:

> *"Which keywords actually pay?"*

A query with 5,000 monthly clicks but landing on a page that converts at 0.2% is worth less than a query with 200 clicks landing on a page that converts at 4%. Without crossing the data, you'd never see it.

### 4. `cross_gsc_to_ga4_journey`

Given an organic landing path, returns:

- **GSC side**: top queries that drove clicks, their CTR/position
- **GA4 side**: sessions, engagement, bounce, conversions, revenue, secondary pages users visited after landing

A complete behavioral profile for one URL. You start from "this page is bleeding rankings" and end at "users who do land bounce 75% of the time and never reach checkout" — three sentences that locate the problem precisely.

### 5. `cross_landing_page_full_diagnosis`

The triage tool. One call, end-to-end:

- GSC ranking signals + cannibalization check
- GA4 behavior + conversion rate
- Composite health score 0–100
- Specific issue flags: `low_ctr`, `cannibalized:N`, `high_bounce`, `low_engagement`, `no_conversions`

Built for the moment a client says "look at /this/page" and you have 60 seconds to diagnose.

## Why nobody has built these

Building cross-platform tools requires:

1. **Both Google APIs authorized in the same OAuth flow.** Each existing MCP requests one scope. Asking the user to re-auth with a wider scope set is friction most authors avoid.
2. **Path normalization between GSC's `page` (absolute URL) and GA4's `landingPagePlusQueryString` (path-only).** Easy to get subtly wrong; silent failures look like "page has no data" when really the filter never matched.
3. **Lag awareness.** GSC reports with 3-day delay; GA4 with 1-day. Cross-platform tools must include both periods in their provenance metadata so the LLM doesn't quote a single misleading window.
4. **Restraint.** It's tempting to ship 90 tools. Five well-designed tools that compose with the 25 single-source tools beats forty tools that overlap.

## The unintended bonus: anti-hallucination

Every tool in the unified MCP wraps its response in `_meta` provenance:

```json
{
  "data": [...],
  "_meta": {
    "source": "crossplatform.traffic_health_check",
    "site_url": "https://www.example.com/",
    "property": "properties/123456",
    "period": {
      "gsc": { "start": "2026-03-27", "end": "2026-04-23" },
      "ga4": { "start": "2026-03-29", "end": "2026-04-25" }
    },
    "fetched_at": "2026-04-26T19:15:46Z"
  }
}
```

With both sources cited and both lag-corrected periods explicit, the agent can write reports that humans can audit. It can also self-correct: if turn 7 contradicts turn 1, the contradiction is visible because both turns cited specific dates.

## Try it

Repo: https://github.com/mario-hernandez/google-seo-mcp-claude-code

```bash
pipx install git+https://github.com/mario-hernandez/google-seo-mcp-claude-code

gcloud auth application-default login \
  --scopes=https://www.googleapis.com/auth/webmasters.readonly,https://www.googleapis.com/auth/analytics.readonly

claude mcp add google-seo-mcp -- $(which google-seo-mcp)
```

Then ask Claude: *"Run a traffic health check on \[your site\] property \[your GA4 ID\]. If it's healthy, run the opportunity matrix."*

Issues, ideas, "your matrix threshold doesn't work for my niche" replies welcome.

---

*Mario Hernández builds open-source tools for SEO and self-hosted analytics. Follow on [GitHub](https://github.com/mario-hernandez).*
