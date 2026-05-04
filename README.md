<!-- mcp-name: io.github.mario-hernandez/google-seo-mcp-claude-code -->

# Google SEO MCP for Claude — the complete Search Console + Analytics 4 suite

<p align="center">
  <img src="docs/hero.png" alt="Google SEO MCP for Claude — Search Console + Analytics 4 unified with cross-platform diagnostic intelligence (GSC↔GA4 journey, opportunity matrix, traffic health check, revenue attribution)" width="100%">
</p>

<p align="center">
  <b>Ask Claude <i>"which organic keywords actually generate revenue, and which pages should I rank up first?"</i> and get a real answer — Search Console rankings, Analytics 4 conversions, and the cross-platform tools that connect them, all in one MCP. Not a CSV dump. Not a hallucination. A diagnosis.</b>
</p>

<p align="center">
  <a href="https://github.com/mario-hernandez/google-seo-mcp-claude-code/stargazers"><img src="https://img.shields.io/github/stars/mario-hernandez/google-seo-mcp-claude-code?style=flat&color=10b981" alt="Stars"></a>
  <img src="https://img.shields.io/badge/python-3.11+-3776ab?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/MCP-compatible-7c3aed" alt="MCP compatible">
  <img src="https://img.shields.io/badge/no--telemetry-10b981" alt="No telemetry">
  <img src="https://img.shields.io/badge/read--only_by_default-10b981" alt="Read-only">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-10b981" alt="MIT"></a>
</p>

> Stop running two MCPs. Stop pasting reports into ChatGPT. Connect both Google Search Console and Google Analytics 4 to Claude as native tools — with the cross-platform diagnostics that actually matter for SEO: which pages would convert if they ranked higher, which queries pay, where tracking is broken, and what the full journey looks like from organic click to revenue.

> **v0.8.0** — four new modules (history persistence, SERP intelligence via DataForSEO, server log analysis, advanced technical crawl) bring the catalog to **97 tools**. v0.7.x stability and multi-client hardening preserved. **97 tools, 92 regression tests, 0 known crashes, multi-tenant safe, Service Account first-class.** See [`CHANGELOG.md`](CHANGELOG.md) for the line-by-line trail.

<p align="center">
  <img src="docs/why-unified.png" alt="Two isolated MCP servers vs one unified MCP — unified unlocks cross-platform tools (journey, opportunity matrix, traffic health check)" width="100%">
</p>

## 30-second quickstart

```bash
# 1. Install (Python 3.11+)
pipx install git+https://github.com/mario-hernandez/google-seo-mcp-claude-code

# 2. Add to Claude Code
claude mcp add google-seo-mcp -- $(which google-seo-mcp)

# 3. Authenticate — choose ONE method (see decision matrix below)
```

Then ask Claude: *"List all my GSC sites and GA4 properties, then run the opportunity matrix for example.com to surface pages where ranking up would also convert."*

Works with **Claude Code**, **Claude Desktop**, **Cursor**, **Windsurf**, and any other MCP-compatible client.

### Pick your auth method (this matters)

| If you are… | Use this | One-line setup |
|-------------|----------|----------------|
| **Anything except a developer on a desktop with a working browser** (Claude Code, headless servers, agents IA, CI, multi-client agencies, Workspace accounts where the admin hasn't approved unverified apps…) | **Service Account** ✅ default | Create a SA JSON in Cloud Console → grant the SA email read access on each GSC site + GA4 property → `export GOOGLE_SEO_SERVICE_ACCOUNT_FILE=/path/to/sa.json` |
| Single dev on a desktop, OAuth client already verified or your email registered as test user | ADC | `gcloud auth application-default login --scopes=https://www.googleapis.com/auth/webmasters.readonly,https://www.googleapis.com/auth/analytics.readonly` |
| You have an OAuth Desktop client JSON and a working browser | OAuth Desktop flow | `export GOOGLE_SEO_OAUTH_CLIENT_FILE=/path/to/client.json` |

> **Recommended default is Service Account.** It's the only method that survives across all environments: no token expiration, no consent screen, no "App is blocked" issues, no reconsent every few weeks when Google revokes inactive tokens, no browser. The `gcloud` flow that the Google docs lead with is fragile in real production. Detailed walkthrough: [Service Account setup](#service-account-setup-recommended-default).

If something fails on first call (`invalid_grant`, `App is blocked`, empty results, permission denied) jump to [Troubleshooting](#troubleshooting) — every common error has a documented fix.

## Questions you can actually ask

Real prompts that fire real tool sequences (full playbook list in [`AGENTS.md`](AGENTS.md)):

| You ask | The agent runs |
|---------|----------------|
| *"What's our SEO ROI this month?"* | `cross_seo_to_revenue_attribution` (90-day window) → returns top queries with attributed revenue |
| *"Why did organic traffic drop?"* | `cross_traffic_health_check` (rule out tracking) → `gsc_traffic_drops` (classify as ranking_loss / ctr_collapse / demand_decline) → `resource://algorithm-updates` for the drop date |
| *"Where should I invest SEO budget this quarter?"* | `cross_opportunity_matrix` → 4 quadrants (`high_impact` / `worth_optimizing` / `good_but_capped` / `low_priority`) auto-calibrated to your traffic |
| *"Are old blog posts decaying?"* | `gsc_content_decay` AND `ga4_content_decay` — pages flagged in BOTH = refresh priority |
| *"Compare my 12 store locations by organic traffic"* | `cross_multi_property_comparison` (parallel fan-out, up to 50 properties) |

## What you actually get

**97 tools + 1 reference resource** across ten categories. Six of them are impossible without unified GSC+GA4 auth; the rest stitch in Lighthouse, CrUX, Schema validation, IndexNow, Google Trends/Suggest/Alerts, full WordPress→JS migration tooling, AEO (`llms.txt` + AI bot policy), and crawl-budget audits — the SEO swiss knife in one binary, no SaaS subscription needed for the 95% case.

- 🔄 **Cross-platform tools that nobody else has** — the whole reason this exists. `gsc_to_ga4_journey` traces an organic click to its conversion. `opportunity_matrix` scores pages by *both* "could rank higher" AND "would convert if it did". `traffic_health_check` detects when GSC and GA4 disagree (broken tracking). `seo_to_revenue_attribution` tells you which queries actually pay (with a 50% confidence band, not as a measurement).
- 🩺 **Diagnoses, not data dumps** — `gsc_traffic_drops` classifies pages as `ranking_loss` / `ctr_collapse` / `demand_decline` / `disappeared`. `ga4_traffic_drops_by_channel` classifies channels as `volume_loss` / `engagement_decay` / `conversion_decay` / `bounce_surge`. Multi-axis taxonomy improved over the existing OSS competitors.
- 🔍 **Anti-hallucination guardrails** — every response is wrapped with `_meta` provenance (source, site_url, property, period, fetched_at) and passed through a `_json_safe` coercer that handles datetime / Decimal / set / Path / numpy / pandas scalars before the JSON-RPC transport sees them. Your agent literally cannot make up the numbers when reporting to clients. <img src="docs/spot-provenance.png" alt="Provenance shield — verifiable source, period, and fetched_at on every response" width="60" align="right">
- 📐 **Rigorous statistics** — `ga4_anomalies` runs STL deseasonalisation (period=7) before a leave-one-out rolling Z-score, then applies Benjamini–Hochberg FDR correction when a dimension is set. `gsc_content_decay` requires 3 monotonic 30-day windows before flagging. Real funnels via sequential filters. Pearson correlation in pagespeed analyses.
- 🛡️ **Read-only by default** — destructive operations (sitemap submission, Google Indexing API publish/delete) require an explicit `GSC_ALLOW_DESTRUCTIVE=true` flag.
- 🔐 **Hardened for multi-client work (v0.7.1)** — SSRF guard rejects RFC1918 / loopback / cloud-metadata IPs (override with `GOOGLE_SEO_ALLOW_PRIVATE_FETCH=true` if needed). XML parsing via `defusedxml` (XXE-safe). Scraped HTML / OG / meta returned to the LLM is wrapped in `<untrusted-third-party-content>` markers. Auth singletons are thread-safe with double-checked locking, and a credentials fingerprint detects account rotation between clients so tools never silently keep returning data from the previous tenant.

## The six cross-platform killers

These tools require both GSC and GA4 auth in the same process — which is exactly why they only exist here.

<p align="center">
  <img src="docs/journey-flow.png" alt="The complete journey: search → click → engagement → funnel → revenue, all instrumented end-to-end" width="100%">
</p>

| Tool | What it does | Why it matters |
|------|--------------|----------------|
| `cross_gsc_to_ga4_journey` | Given an organic landing path, returns top GSC queries that drove clicks AND the GA4 behavior on that page (sessions, engagement, bounce, conversions, revenue, secondary pages). | Closes the loop from "what they searched for" to "what they did". |
| `cross_opportunity_matrix` | Identifies GSC quick-win pages (ranking 4-15) AND fetches their GA4 conversion rate. Classifies into 4 quadrants: `high_impact` / `worth_optimizing` / `good_but_capped` / `low_priority`. | Prioritization that nobody can do with single-source MCPs. Tells you WHICH pages to rank up first, not just which COULD rank up. |
| `cross_traffic_health_check` | Compares GSC organic clicks vs GA4 organic sessions. Diagnoses `tracking_gap` / `filter_issue` / `healthy` based on the ratio. | Detects broken tracking, consent banner problems, bot traffic, channel mis-classification — invisible to either MCP alone. |
| `cross_seo_to_revenue_attribution` | For each top organic query, attributes GA4 revenue proportionally by GSC click-share on the landing page. | Approximate but powerful: "which queries actually pay" — a question pure-GSC cannot answer and pure-GA4 cannot connect to keywords. |
| `cross_landing_page_full_diagnosis` | One call → GSC ranking signals + cannibalization check + GA4 behavior + composite health score (0-100, red/amber/green) + specific issue flags. | End-to-end triage of one page. The single tool you'd use during a client review. |
| `cross_multi_property_comparison` | Fans out to N GA4 properties (up to 50) in parallel, comparing a single metric. Returns sorted totals with optional dimension breakdown. | For agencies / multi-site owners: one call, all properties, one shared scope of auth. |

<p align="center">
  <img src="docs/opportunity-matrix.png" alt="The opportunity matrix — pages classified into four quadrants by GSC ranking opportunity vs GA4 conversion potential" width="80%">
</p>

The `cross_opportunity_matrix` quadrant model: pages in the **green high_impact** corner are where SEO effort pays off twice — they're close enough to top positions that a small ranking push will move them, AND once there they convert. The amber **worth_optimizing** zone needs both a ranking push AND on-page work. The cyan **good_but_capped** is already converting; leave them alone. The slate **low_priority** is where most pages live; ignore them.

## Real example — `cross_traffic_health_check`

Ask Claude: *"Is the tracking healthy on example.com?"*

```json
{
  "data": {
    "diagnosis": "healthy",
    "ratio_ga4_to_gsc": 0.608,
    "gsc_organic_clicks": 477,
    "ga4_organic_sessions": 290,
    "interpretation": "GA4 reports 61% of GSC organic clicks — within the expected 0.6-1.4 range. Tracking is consistent."
  },
  "_meta": {
    "source": "crossplatform.traffic_health_check",
    "site_url": "https://www.example.com/",
    "property": "properties/123456789",
    "period": {
      "gsc": { "start": "2026-03-27", "end": "2026-04-23" },
      "ga4": { "start": "2026-03-27", "end": "2026-04-23" }
    },
    "fetched_at": "2026-04-26T22:00:00Z"
  }
}
```

Claude can now *explain* the health: GA4 sees 61% of GSC clicks, which is normal because GSC counts every search-result-click while GA4 counts unique sessions (some users navigate away before analytics fires). Both periods are aligned to GSC's 3-day reporting lag so the comparison is apples-to-apples — the LLM can quote exact dates without making them up.

## All 97 tools

11 categories. Bold counts — verified against `mcp._tool_manager.list_tools()` on the v0.7.1 release.

<details open>
<summary><b>🔄 Cross-platform (6 — the unique selling proposition)</b></summary>

| Tool | What it does |
|------|--------------|
| `cross_gsc_to_ga4_journey` | Given a landing path, returns GSC top queries + GA4 behavior on that page |
| `cross_opportunity_matrix` | GSC quick-win pages ranked by GA4 conversion potential, in 4 quadrants |
| `cross_traffic_health_check` | GSC clicks vs GA4 sessions ratio with `tracking_gap` / `filter_issue` / `healthy` diagnosis |
| `cross_seo_to_revenue_attribution` | Top organic queries attributed to GA4 revenue by click-share (with 50% confidence band) |
| `cross_landing_page_full_diagnosis` | End-to-end page diagnosis: GSC + GA4 + cannibalization + score + issues |
| `cross_multi_property_comparison` | Parallel fan-out for ≤50 GA4 properties (multi-location dashboards) |

</details>

<details>
<summary><b>🔎 Google Search Console (12)</b></summary>

| Tool | What it does |
|------|--------------|
| `gsc_list_sites` | Verified properties + permission level + property type |
| `gsc_inspect_url` | URL Inspection API — index status, canonical, mobile, rich results |
| `gsc_list_sitemaps` | Sitemaps with errors / warnings / last-submitted |
| `gsc_submit_sitemap` | Submit a sitemap (gated by `GSC_ALLOW_DESTRUCTIVE=true`) |
| `gsc_search_analytics` | Custom Search Analytics query — supports `country` (ISO-3166 alpha-3) and `device` filters |
| `gsc_site_snapshot` | Aggregated totals last N days vs prior period |
| `gsc_quick_wins` | Queries in positions 4-15, scored by `impressions × CTR-gap-to-pos-3` |
| `gsc_traffic_drops` | Pages losing traffic, classified `ranking_loss` / `ctr_collapse` / `demand_decline` / `disappeared` |
| `gsc_content_decay` | Pages with monotonic decline across 3 consecutive 30-day windows |
| `gsc_cannibalization` | Queries where ≥2 pages on your site compete |
| `gsc_ctr_opportunities` | Pages with CTR far below the expected for their position |
| `gsc_alerts` | Position drops / CTR collapses / click drops / disappeared queries with severity dedup |

</details>

<details>
<summary><b>📈 Google Analytics 4 (14)</b></summary>

| Tool | What it does |
|------|--------------|
| `ga4_list_properties` | Every GA4 property the auth account can access |
| `ga4_get_property_details` | Timezone, currency, industry, service level for one property |
| `ga4_search_schema` | TF-IDF keyword search over GA4 dimensions/metrics (top-N, avoids 10k token dump) |
| `ga4_list_schema_categories` | Cheap discovery of available dim/metric categories |
| `ga4_estimate_query_size` | Anti-context-blowup probe (`limit=1` → reads `row_count` for free) |
| `ga4_query` | Full Data API report with filters, order_bys, aggregations |
| `ga4_anomalies` | STL-deseasonalised + leave-one-out Z-score + Benjamini–Hochberg FDR correction |
| `ga4_traffic_drops_by_channel` | Channels in decline, multi-axis: volume / engagement / conversion / bounce |
| `ga4_landing_page_health` | Health score (red/amber/green) for top landing pages |
| `ga4_event_volume_comparison` | Per-event unique-user counts (was `conversion_funnel`; renamed for honesty — GA4 Data API can't enforce sequence) |
| `ga4_conversion_funnel` | Deprecated alias of `event_volume_comparison` (kept for back-compat) |
| `ga4_cohort_retention` | New vs returning visitor metrics |
| `ga4_channel_attribution` | First-touch vs last-touch comparison; classifies as assister / closer / balanced |
| `ga4_content_decay` | GA4 metric decline across 3 consecutive 30-day windows (any metric) |

</details>

<details>
<summary><b>🚚 Migration (21 — WordPress → JS stack equity preservation)</b></summary>

| Tool | What it does |
|------|--------------|
| `migration_seo_equity_report` | Composer: WP REST + crawl + GSC + internal-link graph → equity score per URL with `MUST_PRESERVE` / `WORTH_PRESERVING` / `LOW_VALUE` / `DEPRECATE` tags |
| `migration_wp_audit_site` | WordPress REST inventory: post types, taxonomies, plugin probes |
| `migration_wp_extract_redirects` | Enumerate redirects from Redirection / RankMath / Yoast Premium |
| `migration_wp_internal_links_graph` | advertools crawl → in/out degree, orphans, top hubs |
| `migration_sitemap_diff` | Old vs new sitemap with `xhtml:link` hreflang alternate parsing |
| `migration_sitemap_validate` | Concurrent GET (Range: bytes=0-0) + retry on 503/504 |
| `migration_redirects_plan` | Hybrid exact + rapidfuzz match with collision + self-redirect detection |
| `migration_export_redirects_nginx` / `_apache` / `_cloudflare` | 301 rules in three formats (CF schema follows official Lists API) |
| `migration_googlebot_diff` | Mobile-first Googlebot UA vs user UA with 5 anti-FP guards (cf-mitigated, Vary, html.unescape, A/B threshold 30%, cache-bust double-fetch) |
| `migration_multi_bot_diff` | Same diff across Googlebot + Bingbot + user UAs |
| `migration_verify_googlebot_ip` | rDNS forward+backward validation of a server-log IP |
| `migration_prerender_check` | Pre-JS HTML SEO signals + shell-only soft-404 detection |
| `migration_prerender_vs_hydrated` | Playwright DOM diff with optional `wrs_realistic=True` (5s budget, console errors, hydration mismatches) |
| `migration_schema_parity_check` | JSON-LD types + critical props old vs new with parity_score |
| `migration_hreflang_cluster_audit` | Reciprocity + region-aware (es-ES ≠ es-MX) cross-domain support |
| `migration_indexation_recovery_monitor` | Post-launch GSC URL Inspection batch with INDEXED / DISCOVERED / SOFT_404 / BLOCKED classification |
| `migration_wayback_baseline` | Internet Archive CDX snapshot inventory as historical anchor |
| `migration_robots_audit` | robots.txt sitemaps declared, crawl-delay, disallow counts, sample-path verdicts |
| `migration_robots_diff` | Old vs new robots.txt × GSC ranked paths → `newly_blocked` flag |

</details>

<details>
<summary><b>⚡ Lighthouse / PageSpeed Insights (5)</b></summary>

| Tool | What it does |
|------|--------------|
| `lighthouse_audit` | Full PSI audit; surfaces lab + CrUX field data (`loadingExperience`) |
| `lighthouse_core_web_vitals` | LCP + CLS lab + INP/LCP/CLS field + TBT/FCP/SI/TTI under `lab_metrics` |
| `lighthouse_lcp_opportunities` | Filtered to LCP-relevant audits via `auditRefs.relevantAudits` |
| `lighthouse_compare_mobile_desktop` | Side-by-side perf score delta |
| `lighthouse_seo_score` | Lighthouse SEO category breakdown |

</details>

<details>
<summary><b>📊 CrUX — Chrome User Experience Report (3)</b></summary>

| Tool | What it does |
|------|--------------|
| `crux_current` | Latest 28-day p75 with auto-fallback URL→origin and `scope` tag |
| `crux_history` | Up to 25 weekly snapshots (~6 months) for one metric |
| `crux_compare_origins` | Side-by-side with `winner` / `metric_unit` / interpretation |

</details>

<details>
<summary><b>🏷️ Schema.org / JSON-LD (3)</b></summary>

| Tool | What it does |
|------|--------------|
| `schema_extract_url` | Extract JSON-LD + microdata + RDFa via extruct |
| `schema_validate_url` | Lightweight validation against 40+ types (incl. `MedicalWebPage`, `ClaimReview`, `DefinedTerm`, `JobPosting`) |
| `schema_suggest_for_page` | Heuristic schema suggestions by content_type |

</details>

<details>
<summary><b>📝 Indexing (5)</b></summary>

| Tool | What it does |
|------|--------------|
| `indexnow_generate_key` | 32-char key for Bing/Yandex IndexNow |
| `indexnow_submit` | Submit a list of URLs |
| `indexnow_submit_sitemap` | Parse sitemap and submit (chunked at 10k URLs) |
| `google_indexing_publish` | URL_UPDATED notification (gated by `GSC_ALLOW_DESTRUCTIVE=true`) |
| `google_indexing_delete` | URL_DELETED notification (gated) |

</details>

<details>
<summary><b>📈 Trends / Suggest / Alerts (5)</b></summary>

| Tool | What it does |
|------|--------------|
| `google_suggest` | Google autocomplete for a seed query |
| `google_suggest_alphabet` | Seed × A-Z fan-out (~110 long-tails per seed) |
| `google_trends_keyword` | pytrends interest-over-time + region |
| `google_trends_related` | Top + rising related queries |
| `alerts_rss_parse` | Parse a Google Alerts RSS feed for brand mentions |

</details>

<details>
<summary><b>🤖 AEO — Answer Engine Optimisation (2)</b></summary>

| Tool | What it does |
|------|--------------|
| `aeo_llms_txt_check` | Verify `/llms.txt` + `/llms-full.txt` against the [llmstxt.org](https://llmstxt.org) spec |
| `aeo_ai_bots_robots_audit` | Per-bot allow/block for 16 AI/LLM crawlers (GPTBot, ClaudeBot, PerplexityBot, Google-Extended, CCBot, Bytespider, etc.) with vendor + purpose + docs |

</details>

<details>
<summary><b>🛠️ Meta (2)</b></summary>

| Tool | What it does |
|------|--------------|
| `get_capabilities` | Tool catalog + auth status for both GSC and GA4 (call this first) |
| `reauthenticate` | Reset in-process auth clients for both APIs |

</details>

### MCP Resource

The server exposes one read-only resource — accessible to the LLM without issuing a tool call:

- **`google-seo://algorithm-updates`** — reference list of confirmed Google Search algorithm updates from 2023 to today (core updates, spam updates, helpful content, AI Overviews, etc.) with start/end dates and notes. Use this to correlate `gsc_traffic_drops` or `ga4_anomalies` findings with industry-wide events. A drop on a core-update rollout date is much more likely Google-driven than site-specific.

## Compared to other Google MCP servers

The OSS landscape has split GSC and GA4 into separate MCPs. This one unifies them — and adds the cross-platform tools none of the others can deliver.

| You should use… | If you want… |
|-----------------|--------------|
| [**`googleanalytics/google-analytics-mcp`**](https://github.com/googleanalytics/google-analytics-mcp) (Google official) | The most polished raw GA4 API bridge maintained by Google. No GSC, no diagnostic logic, no provenance. |
| [**`AminForou/mcp-gsc`**](https://github.com/AminForou/mcp-gsc) (Python) | The popular general-purpose GSC bridge. No GA4, no cross-platform. |
| [**`Suganthan-Mohanadasan/Suganthans-GSC-MCP`**](https://github.com/Suganthan-Mohanadasan/Suganthans-GSC-MCP) (TypeScript) | Maximum tool surface for GSC alone. No GA4 integration. |
| [**`saurabhsharma2u/search-console-mcp`**](https://github.com/saurabhsharma2u/search-console-mcp) (TypeScript) | The closest competitor: GSC + GA4 + Bing in 90+ tools. Pick if you live in TypeScript or need Bing. Z-score baseline contamination, fake funnel, no `_meta` provenance. |
| [**`surendranb/google-analytics-mcp`**](https://github.com/surendranb/google-analytics-mcp) (Python) | Schema-discovery + row-count-probe for raw GA4. Single-property only, no diagnostic logic, no GSC. |
| **This MCP** | **The unified Python SEO swiss-knife: GSC + GA4 + 6 unique cross-platform tools + Lighthouse/PSI + CrUX + Schema validation + IndexNow/Google Indexing + Google Trends/Suggest/Alerts + DataForSEO SERP + server log analysis + persistence. 97 tools, anti-hallucination provenance on every response, leave-one-out Z-score, real funnels, read-only-by-default.** Pick if you want one binary to cover the whole audit-to-action loop without paying SaaS for what's just a free Google API away. |

This MCP started as a security-audited synthesis of seven open-source projects — credits at the bottom.

## FAQ

**Why use this over the official Google MCP?** The official MCP is a transport layer — wrappers around `runReport` and `searchanalytics.query`. Useful if you're building your own logic. This MCP adds 25+ tools with diagnostic logic baked in (classifications, scoring, anti-hallucination provenance) plus the 6 cross-platform tools that no single-source MCP can provide.

**My site has very little traffic. Will this work?** Yes, but lower the thresholds. For sites under 500 clicks/mo, set `min_impressions=25-50` on `gsc_quick_wins` and `min_clicks_prior=5-10` on `gsc_traffic_drops`. Below ~100 clicks/mo, the issue is usually content/indexation rather than optimization — pivot to `gsc_inspect_url` and `gsc_list_sitemaps`. Don't fabricate recommendations from empty data; the agent should explicitly say *"insufficient sample for trend detection"* when thresholds aren't met. See [`AGENTS.md`](AGENTS.md) §9 for full edge-case handling.

**Does this measure AI Overview impact?** Not directly — it's GSC + GA4 only, no SERP scraping. But the inference is reliable: pages ranking 1-3 with CTR collapse vs historical baseline are high-confidence AIO hits, especially when correlated with rollout dates from `resource://algorithm-updates`. See [`AGENTS.md`](AGENTS.md) §7 for the full inference protocol.

**My GA4 has no ecommerce — will revenue tools still work?** They run, but `attributed_revenue` will be 0 across the board. **Don't conclude SEO has no ROI** — the agent should flag this as a tracking-config gap and suggest `ga4_search_schema(keyword='revenue')` to confirm what fields are available.

**What about ad-blocker traffic?** Common in DACH/tech audiences. `cross_traffic_health_check` will flag `tracking_gap` when GA4 systematically under-reports vs GSC. Apply +15-30% upward correction on GA4 organic and disclose to the user.

**Does it work with `sc-domain:` properties?** Yes — but the `site_url` string must match exactly what `gsc_list_sites` returns. Don't manually compose `https://example.com/` if the registered property is `sc-domain:example.com` — cross-platform path normalization handles both internally, but the join key requires the canonical form.

## Authentication

The MCP supports three credential methods. The cascade order in `auth.py` is:
**ADC (`GOOGLE_APPLICATION_CREDENTIALS`) → Service Account (`GOOGLE_SEO_SERVICE_ACCOUNT_FILE`) → OAuth Desktop flow**. Set the env var corresponding to the method you choose; **leave the others unset** so the cascade picks the right one.

> **Important about the cascade order**: ADC is checked first because it's gcloud's default and exists implicitly on most developer machines. If you have BOTH `GOOGLE_APPLICATION_CREDENTIALS` (or a stale `~/.config/gcloud/application_default_credentials.json`) AND a working SA, the cascade tries ADC first. Since v0.7.3 it auto-validates the ADC refresh token and silently falls through to the SA if revoked — but it's cleaner to **unset `GOOGLE_APPLICATION_CREDENTIALS` and remove the stale ADC file when running on Service Account**, so you skip a network round-trip on every cold start.

### Service Account setup (recommended default)

Best for: anything that isn't an interactive desktop session. **No browser, no token expiration, no consent screen issues, no reconsent every few weeks.** This is the production-grade option.

**Step 1 — Create the Service Account in Google Cloud Console**

1. Open `https://console.cloud.google.com/iam-admin/serviceaccounts?project=YOUR_PROJECT_ID` (use any GCP project where you have Owner/Editor access — APIs are billed to this project).
2. **Create Service Account**:
   - Name: `google-seo-mcp-readonly`
   - Description: "Read-only access to GSC + GA4 for the SEO MCP"
   - **Grant no IAM roles** (GSC and GA4 don't use IAM, they use their own ACLs).
3. Click the SA → **Keys** tab → **Add Key** → **Create new key** → **JSON** → Download.
4. Move and lock down the file:
   ```bash
   mkdir -p ~/.config/gcloud
   mv ~/Downloads/<your-project>-*.json ~/.config/gcloud/google-seo-mcp-sa.json
   chmod 600 ~/.config/gcloud/google-seo-mcp-sa.json
   ```
5. Note the SA email — it has the format `google-seo-mcp-readonly@YOUR_PROJECT_ID.iam.gserviceaccount.com`.

**Step 2 — Enable the required APIs in your project (one-time)**

```bash
gcloud services enable \
  searchconsole.googleapis.com \
  analyticsadmin.googleapis.com \
  analyticsdata.googleapis.com \
  --project=YOUR_PROJECT_ID
```

(Or enable from the web: `https://console.cloud.google.com/apis/library/searchconsole.googleapis.com?project=YOUR_PROJECT_ID`.)

**Step 3 — Grant the SA access to each GSC site and GA4 property**

The SA email behaves like a user. Add it explicitly to each property you want to access:

- **GA4** (per property) — `https://analytics.google.com` → Admin → Property → **Property Access Management** → **+** (top right) → **Add user** → SA email → role **Viewer**. Works straight from the UI.

- **Search Console** (per site) — `https://search.google.com/search-console` → Settings (gear icon) → **Users and permissions** → **Add user** → paste the SA email → permission **Restricted** (read-only) or **Full**.

> ⚠️ **Search Console + Service Account: Google's UI may reject the SA email** with "user not found" or similar. This is a known Google quirk — GSC's user picker validates that the email belongs to a Google identity that has logged into Google products, which a service account never does. Three workarounds, in order of preference:
>
> 1. **Use a Domain-wide Delegation SA** (Google Workspace customers only) — set up DwD in Cloud Console + Workspace admin and the SA can impersonate a real user.
> 2. **Add the SA as a verified property owner via DNS or HTML file verification** — works for any account, but you need DNS/file access. Add a TXT record `google-site-verification=...` keyed to the SA email. Once verified the SA gets owner-level access.
> 3. **Use a different SA that is already verified for the property** (common in agencies that have a "house" SA per client).
>
> If you hit the `gsc_list_sites` empty-list problem after granting permissions and it persists for >5 minutes (GSC user grants take time to propagate), this is the most likely root cause. Check the [Google Cloud documentation on SA + GSC](https://developers.google.com/webmaster-tools/v1/how-tos/authorizing#service-account) for the exact verification flow.

For multi-client agencies, this is one-time per client. Subsequent property additions just need this single email added.

**Step 4 — Configure the env var**

In `~/.claude.json` (or your MCP client config), set:

```json
{
  "mcpServers": {
    "google-seo-mcp": {
      "type": "stdio",
      "command": "google-seo-mcp",
      "env": {
        "GOOGLE_SEO_SERVICE_ACCOUNT_FILE": "/Users/YOU/.config/gcloud/google-seo-mcp-sa.json"
      }
    }
  }
}
```

Or via shell:

```bash
export GOOGLE_SEO_SERVICE_ACCOUNT_FILE=~/.config/gcloud/google-seo-mcp-sa.json
```

**Step 5 — Restart your MCP client and verify**

Quit the client fully (Cmd+Q in Claude Code, not just close window) and reopen. Then:

```
Run gsc_list_sites and ga4_list_properties.
```

You should see all properties where the SA email was granted access.

> **Important**: if you also have `GOOGLE_APPLICATION_CREDENTIALS` set or a stale `~/.config/gcloud/application_default_credentials.json` file, the cascade tries ADC **first** and tries to refresh it on every cold start. Since v0.7.3 it auto-falls-through to the SA if the ADC refresh token is revoked, but the cleaner setup is to **unset `GOOGLE_APPLICATION_CREDENTIALS` and rename the stale ADC file**: `mv ~/.config/gcloud/application_default_credentials.json{,.bak}`. That skips the network round-trip entirely.

### ADC — Application Default Credentials

Best for: a single developer on a desktop with a working browser and an OAuth client that's either fully verified by Google or whose consent screen lists your email as test user.

```bash
gcloud auth application-default login \
  --scopes=https://www.googleapis.com/auth/webmasters.readonly,https://www.googleapis.com/auth/analytics.readonly
```

The authenticated Google account must be a verified user in **both**:
- **Search Console** for each property (Property → Settings → Users and permissions)
- **Analytics 4** for each property (Admin → Property → Property Access Management)

**Known limitations**:
- Requires interactive browser (won't work in Claude Code shells, agents, CI).
- OAuth client must be either fully App-Verified by Google or include your email as test user (max 100 lifetime test users in External + Testing mode).
- Refresh tokens get silently revoked by Google after periods of inactivity, security policy changes, or cross-machine reuse.
- Workspace-managed accounts often have admin policy that blocks unverified apps entirely with "This app is blocked".

If any of those bite you, **switch to a Service Account** — that's why it's the recommended default.

### OAuth Desktop flow (interactive)

Best for: developers running the MCP from a desktop terminal with a Google Cloud project where they don't want to provision a SA.

```bash
export GOOGLE_SEO_OAUTH_CLIENT_FILE=/path/to/client_secret.json
```

The first call opens a browser; the token is cached at `~/Library/Application Support/google-seo-mcp/token.json` (macOS) or the equivalent `XDG_CONFIG_HOME` location.

**Note**: requires the OAuth Desktop client to either be App-Verified by Google or to have your email registered as a test user in the OAuth consent screen. Otherwise you'll see "This app is blocked" — see [Troubleshooting](#troubleshooting).

## Troubleshooting

### `invalid_grant: Token has been expired or revoked.`

Your ADC refresh token has been revoked by Google (common after periods of inactivity, security policy changes, or if you authenticated with the same client across multiple machines).

**Since v0.7.3 this should auto-recover** if you have a Service Account configured: the cascade detects the dead refresh token and silently falls through to `GOOGLE_SEO_SERVICE_ACCOUNT_FILE`. You'll see a warning in the logs. **If you still see the raw `invalid_grant` error**, it means there's no SA fallback configured — set one up.

**Fix**: switch to a Service Account ([Service Account setup](#service-account-setup-recommended-default)). It eliminates token expiration entirely. Don't waste time re-running `gcloud auth application-default login` — the underlying OAuth client may be flagged for blocking.

If you still want to retry ADC: `gcloud auth application-default revoke && gcloud auth application-default login --scopes=...`

**Cleanest setup once you've migrated to SA**: unset `GOOGLE_APPLICATION_CREDENTIALS` and rename the stale ADC file:
```bash
unset GOOGLE_APPLICATION_CREDENTIALS  # in your shell config
mv ~/.config/gcloud/application_default_credentials.json{,.bak}
```
This skips the ADC validation round-trip on every cold start.

### `This app is blocked — This app tried to access sensitive info in your Google Account.`

Google blocks OAuth flows for clients that request sensitive scopes (`webmasters`, `analytics.readonly`) and are either unverified or whose verification has lapsed. Common with the default `gcloud` client and with custom OAuth Desktop clients in **External + Testing** consent mode.

**Fix options** (best to worst):
1. **Switch to Service Account** — bypasses OAuth entirely. This is the recommended path for any production / agent / multi-client workflow.
2. **Add your email as test user** — Cloud Console → APIs & Services → OAuth consent screen → Audience → Test users → add your email. Limited to 100 test users lifecycle, only works in External + Testing.
3. **Submit OAuth consent screen for verification** — Google's official path, takes weeks, not worth it for self-hosted SEO tooling.

### `EOFError: EOF when reading a line` during `--no-browser` flow

The `gcloud auth application-default login --no-browser` flow needs an interactive shell to paste the verification code. Claude Code, Cursor, agents, and CI shells are non-interactive — the prompt fails immediately.

**Fix**: do not use OAuth flow in non-interactive environments. Use a Service Account.

### `ga4_list_properties` returns an empty list

The authenticated identity (your Google account or the SA email) doesn't have access to any GA4 property.

**Fix**: open `https://analytics.google.com` → Admin → Property Access Management for each property, and explicitly grant the auth identity at least the **Viewer** role.

### `gsc_list_sites` returns an empty list

The auth identity has no access to any GSC site, OR you tried to add a Service Account email and Google Search Console rejected it.

**Common case A — using ADC / OAuth**: each site has its own ACL.
**Fix**: `https://search.google.com/search-console` → site → Settings → Users and permissions → **Add user** → grant Restricted or Full to the auth identity.

**Common case B — using Service Account**: GSC's "Add user" UI may reject the SA email with "user not found". This is a Google quirk: SA emails can't be added through the user picker because they've never logged into Google products. Three workarounds:

1. **Domain-wide Delegation** (Google Workspace customers only) — set up DwD in Cloud Console + Workspace admin so the SA can impersonate a real user.
2. **Verify the SA as a property owner via DNS or HTML file**:
   - Add a `TXT` record `google-site-verification=<token>` to your domain.
   - The token is generated when you start the verification flow with the SA credentials, NOT through the GSC UI. Use the [GSC Site Verification API](https://developers.google.com/site-verification/v1/getting_started).
   - Once verified, the SA gets owner-level access automatically.
3. **Reuse a SA already verified for the property** (common in agencies — one "house" SA per client domain).

After granting permissions, GSC user grants can take 5-15 minutes to propagate. If `gsc_list_sites` is still empty after that, double-check using the GSC UI — log into `https://search.google.com/search-console` as the SA email (you can't, that's the point) OR check the property's "Users and permissions" list to see whether the SA email appears there.

Reference: [Google docs on SA + GSC authorization](https://developers.google.com/webmaster-tools/v1/how-tos/authorizing#service-account).

### `403 PERMISSION_DENIED — Google Analytics Admin API has not been used in project X`

The GCP project hosting the auth identity (the project where the SA was created, or the project tied to your ADC) doesn't have the required APIs enabled.

**Fix**:
```bash
gcloud services enable searchconsole.googleapis.com analyticsadmin.googleapis.com analyticsdata.googleapis.com --project=YOUR_PROJECT_ID
```

Or enable each from the web console.

### Tools return data from the wrong client (multi-tenant)

You rotated `gcloud` accounts or swapped the SA file but the MCP keeps returning data from the previous identity.

**Fix**: this should NOT happen since v0.7.1 — the auth singletons detect a credentials fingerprint change and rebuild the clients automatically. If you observe this, file an issue. As a workaround, call the `reauthenticate` tool from your agent, or restart the MCP client.

### `App is blocked` even after adding test user

If you completed step "add test user" but Google still blocks the flow, your client may be in **Production** mode without verification. Check Cloud Console → APIs & Services → OAuth consent screen → Publishing status. Either:
- Switch to **Testing** + ensure test user is added, or
- Use a **Service Account** (no consent screen involved).

## Configure with your client

<details open>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add google-seo-mcp -- $(which google-seo-mcp)
```

Or manually in `~/.claude.json`:

```json
{
  "mcpServers": {
    "google-seo-mcp": {
      "type": "stdio",
      "command": "google-seo-mcp"
    }
  }
}
```

</details>

<details>
<summary><b>Claude Desktop</b></summary>

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "google-seo-mcp": {
      "command": "google-seo-mcp"
    }
  }
}
```

</details>

<details>
<summary><b>Cursor / Windsurf / Zed</b></summary>

```json
{
  "google-seo-mcp": { "command": "google-seo-mcp" }
}
```

</details>

## Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `GOOGLE_APPLICATION_CREDENTIALS` | gcloud ADC default | ADC file path. Set this **only** if you're explicitly using ADC. The cascade tries it first, so leaving a stale value here makes every cold start slower (one extra refresh round-trip) and triggers a warning log. |
| `GOOGLE_SEO_OAUTH_CLIENT_FILE` | — | Desktop OAuth client JSON. Triggers interactive browser flow on first call. |
| `GOOGLE_SEO_SERVICE_ACCOUNT_FILE` | — | Service account key path. **Recommended default**. Self-issued JWTs, no expiration, works headless. |
| `GOOGLE_PROJECT_ID` | — | **Optional, fingerprint-only**. Used exclusively as part of the credentials fingerprint that detects multi-tenant rotation between calls. **It does NOT route requests to a specific GCP project** — the actual project is inferred from the active credential (the SA's own JSON, or the ADC's `quota_project_id`). Leaving it empty is fine. Setting it wrong does NOT break anything (the credential still works); it just slightly degrades the fingerprint's ability to detect account rotation. If you swap your SA file to one in a different GCP project, the fingerprint changes anyway via the file's `mtime`. |
| `GOOGLE_SEO_ALLOW_PRIVATE_FETCH` | `false` | If `true`, the SSRF guard accepts RFC1918 / loopback / cloud-metadata URLs in `fetch_url` family tools. Use only on trusted intranets. |
| `GSC_ALLOW_DESTRUCTIVE` | `false` | Enables sitemap submission and write-scope OAuth. |
| `GSC_CTR_BENCHMARKS` | conservative defaults | Comma-separated 10 floats overriding per-position expected CTR. |
| `PAGESPEED_API_KEY` | — | API key for Lighthouse/PSI **and** CrUX. Without it, the anonymous quota is shared and frequently 429-throttled. Create one at [console.cloud.google.com](https://console.cloud.google.com) — enable PageSpeed Insights API + Chrome UX Report API, then create an API key restricted to those two services. The same key works for both. |
| `CRUX_API_KEY` | (falls back to `PAGESPEED_API_KEY`) | Alternative if you prefer separate keys. |
| `DATAFORSEO_LOGIN` | — | Required only by the `serp_*` tools. Sign up at [dataforseo.com](https://dataforseo.com) (pay-as-you-go, ~$0.0006 per Live SERP call). Tools fail gracefully (no exception) when credentials absent — they return `{"error": "credentials_missing", "fix": ...}`. |
| `DATAFORSEO_PASSWORD` | — | Pair with `DATAFORSEO_LOGIN`. Store in macOS Keychain or your secrets manager rather than `.env` files. |
| `GOOGLE_SEO_HISTORY_DIR` | `~/.google-seo-mcp/history` | Filesystem location where `history_save_snapshot` writes per-client snapshots. Override if you want them on a synced drive (iCloud, Dropbox) for cross-device continuity. |
| `GOOGLE_SEO_LOG_LEVEL` | `INFO` | Python log level. |

## Design principles

- **One install, one auth, both APIs.** Single OAuth flow requests both `webmasters.readonly` and `analytics.readonly`. No double setup.
- **Read-only.** Destructive operations behind explicit `GSC_ALLOW_DESTRUCTIVE` flag.
- **Provenance always included.** Every response is wrapped in `{"data": ..., "_meta": {source, site_url|property, period, fetched_at}}`. Cross-platform tools include both site_url AND property AND separate periods (GSC and GA4 have different lags).
- **Diagnoses, not data dumps.** All intelligence tools classify findings rather than handing the LLM thousands of rows.
- **Anti-context-blowup.** GA4 has `estimate_query_size` and `search_ga4_schema` so the LLM can size queries cheaply before fetching.
- **Multi-property by parameter, not env.** Pass any `property_id` to any tool — no need to restart with a different property.
- **Statistical rigor.** Leave-one-out Z baselines, monotonic-window decay detection, real funnels via sequential filters.

## For agents — operator's guide

If you're using this MCP through Claude Code / Cursor / Windsurf and want to get the most out of it, drop **[`AGENTS.md`](AGENTS.md)** into your agent's context. It's a synthesis of three expert perspectives (technical SEO, local SEO + SERP intent, marketing/growth analytics) into a single operating manual:

- 25+ playbooks mapping common user questions to exact tool sequences
- 3 decision trees (drop diagnosis, ROI/prioritization, local-specific)
- 12 anti-patterns to avoid hallucinations and context blowup
- Argument cookbook tuned by site profile (small/medium/enterprise/local)
- Inference workarounds for what the MCP doesn't measure directly (AI Overview impact, brand vs non-brand, featured snippets)
- 3 ready-to-paste reporting templates (weekly digest, monthly CMO report, agency multi-client dashboard)
- Edge cases for small sites, multi-language, ad-blocker-heavy traffic, GA4 misconfig, holidays

The file is designed to be pasted directly into the system prompt or attached as a context document.

## Testing

Three layers of tests, run them in order on any new client setup:

### 1. Unit tests (no network, ~3 seconds)

```bash
.venv/bin/pytest tests/ -q
```

92 tests covering auth fingerprint detection, atomic token writes, `_json_safe` JSON-RPC coercion (datetime / Decimal / set / Path / numpy / bytes / weird types), `float("")` regression on empty GA4 metrics, KeyError regression on raw GSC subscripts, SSRF guard against RFC1918/loopback/cloud-metadata, XXE protection in sitemap parsing, equity URL normalisation, rapidfuzz no-match graceful path, etc.

### 2. Integration smoke against your real Google APIs (~30 seconds)

```bash
.venv/bin/python scripts/smoke_test.py
```

Probes all six layers of the MCP (auth, admin discovery, reporting, intelligence, cross-platform, resource) using the first GSC site / GA4 property your account can see. It's the first thing to run after any code change or before promoting to a new client.

### 3. Per-client validation (~2 minutes)

When onboarding a new client, run the full client probe to verify every tool category responds against their data:

```bash
.venv/bin/python scripts/client_probe.py \
    --gsc-site "https://example.com/" \
    --ga4-property "properties/123456789"
```

Outputs a JSON report with one row per tool, status `OK` / `SKIP` (gated/optional) / `FAIL` (real bug to investigate), timing, and a summary of any actionable findings against the client's data (CTR opportunities, traffic drops, indexation gaps, AEO gaps, multi-tenant safety check).

## Predecessors

This unified suite supersedes two previous repos that were split by API:
- ~~[`google-search-console-mcp-claude-code`](https://github.com/mario-hernandez/google-search-console-mcp-claude-code)~~ → archived; install this instead.
- ~~[`google-analytics-mcp-claude-code`](https://github.com/mario-hernandez/google-analytics-mcp-claude-code)~~ → archived; install this instead.

If you're already using either of them, migrate by:
1. `pipx uninstall gsc-seo-mcp` (or `ga4-seo-mcp`)
2. `pipx install git+https://github.com/mario-hernandez/google-seo-mcp-claude-code`
3. Update your Claude config to point to the new `google-seo-mcp` binary.

Tool names are similar but **prefixed** now (`gsc_*`, `ga4_*`, `cross_*`) — your prompts may need light adjustments.

## Credits & inspiration

Independent implementation that synthesizes the strongest ideas from seven open-source projects, all of which were security-audited and found clean before being studied:

**GSC sources:**
- [`AminForou/mcp-gsc`](https://github.com/AminForou/mcp-gsc) — LLM-friendly errors, destructive-flag gating, capability discovery
- [`Suganthan-Mohanadasan/Suganthans-GSC-MCP`](https://github.com/Suganthan-Mohanadasan/Suganthans-GSC-MCP) — diagnostic SEO logic (quick-wins scoring, traffic-drop classification, content-decay 3-window)
- [`acamolese/google-search-console-mcp`](https://github.com/acamolese/google-search-console-mcp) — three-tier credential cascade
- [`surendranb/google-search-console-mcp`](https://github.com/surendranb/google-search-console-mcp) — minimal FastMCP boilerplate

**GA4 sources:**
- [`googleanalytics/google-analytics-mcp`](https://github.com/googleanalytics/google-analytics-mcp) — proto-serialized examples in docstrings, inputSchema sanitization
- [`surendranb/google-analytics-mcp`](https://github.com/surendranb/google-analytics-mcp) — schema cache + TF-IDF search, row-count probe
- [`saurabhsharma2u/search-console-mcp`](https://github.com/saurabhsharma2u/search-console-mcp) — diagnostic philosophy (improved here with statistical rigor)

If those projects fit your workflow better, use them — they're great in their own right.

## Security notes

- **No telemetry.** Zero outbound traffic to anything other than `googleapis.com` / `accounts.google.com` / `oauth2.googleapis.com`.
- **No credentials in the repo.** `.gitignore` excludes `*.json` by default.
- **Read-only OAuth scopes** unless `GSC_ALLOW_DESTRUCTIVE=true`.

## License

MIT — see [LICENSE](LICENSE).
