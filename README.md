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

<p align="center">
  <img src="docs/why-unified.png" alt="Two isolated MCP servers vs one unified MCP — unified unlocks cross-platform tools (journey, opportunity matrix, traffic health check)" width="100%">
</p>

## 30-second quickstart

```bash
# 1. Install (Python 3.11+)
pipx install git+https://github.com/mario-hernandez/google-seo-mcp-claude-code

# 2. Authenticate ONCE for both APIs (one-time, opens browser)
gcloud auth application-default login \
  --scopes=https://www.googleapis.com/auth/webmasters.readonly,https://www.googleapis.com/auth/analytics.readonly

# 3. Add to Claude Code
claude mcp add google-seo-mcp -- $(which google-seo-mcp)
```

Then ask Claude: *"List all my GSC sites and GA4 properties, then run the opportunity matrix for example.com to surface pages where ranking up would also convert."*

Works with **Claude Code**, **Claude Desktop**, **Cursor**, **Windsurf**, and any other MCP-compatible client.

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

**33 tools + 1 reference resource** across three categories — and six of them are impossible without unified auth.

- 🔄 **Cross-platform tools that nobody else has** — the whole reason this exists. `gsc_to_ga4_journey` traces an organic click to its conversion. `opportunity_matrix` scores pages by *both* "could rank higher" AND "would convert if it did". `traffic_health_check` detects when GSC and GA4 disagree (broken tracking). `seo_to_revenue_attribution` tells you which queries actually pay.
- 🩺 **Diagnoses, not data dumps** — `gsc_traffic_drops` classifies pages as ranking_loss / CTR_collapse / demand_decline. `ga4_traffic_drops_by_channel` classifies channels as volume_loss / engagement_decay / conversion_decay / bounce_surge. Multi-axis taxonomy improved over the existing OSS competitors.
- 🔍 **Anti-hallucination guardrails** — every response is wrapped with `_meta` provenance (source, site_url, property, period, fetched_at). Your agent literally cannot make up the numbers when reporting to clients. <img src="docs/spot-provenance.png" alt="Provenance shield — verifiable source, period, and fetched_at on every response" width="60" align="right">
- 📐 **Rigorous statistics** — `ga4_anomalies` uses leave-one-out rolling Z-score (vs the contaminated-baseline approach in some other MCPs). `gsc_content_decay` requires 3 monotonic 30-day windows before flagging. Real funnels via sequential filters. Pearson correlation in pagespeed analyses.
- 🛡️ **Read-only by default** — destructive operations (sitemap submission, etc.) require an explicit `GSC_ALLOW_DESTRUCTIVE=true` flag.

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
    "ga4": { "start": "2026-03-29", "end": "2026-04-25" }
  }
}
```

Claude can now *explain* the health: GA4 sees 61% of GSC clicks, which is normal because GSC counts every search-result-click while GA4 counts unique sessions (some users navigate away before analytics fires). Note how `_meta.period` cites both periods separately because GSC has a 3-day reporting lag while GA4 has only 1 day — the LLM can quote the exact dates without making them up.

## All 33 tools

<details open>
<summary><b>🔄 Cross-platform (5 — the unique selling proposition)</b></summary>

| Tool | What it does |
|------|--------------|
| `cross_gsc_to_ga4_journey` | Given a landing path, returns GSC top queries + GA4 behavior on that page |
| `cross_opportunity_matrix` | GSC quick-win pages ranked by GA4 conversion potential, in 4 quadrants |
| `cross_traffic_health_check` | GSC clicks vs GA4 sessions ratio with `tracking_gap` / `filter_issue` / `healthy` diagnosis |
| `cross_seo_to_revenue_attribution` | Top organic queries attributed to GA4 revenue by click-share |
| `cross_landing_page_full_diagnosis` | End-to-end page diagnosis: GSC + GA4 + cannibalization + score + issues |

</details>

<details>
<summary><b>🔎 Google Search Console (14)</b></summary>

| Tool | What it does |
|------|--------------|
| `gsc_list_sites` | Verified properties + permission level + property type |
| `gsc_inspect_url` | URL Inspection API — index status, canonical, mobile, rich results |
| `gsc_list_sitemaps` | Sitemaps with errors / warnings / last-submitted |
| `gsc_submit_sitemap` | Submit a sitemap (gated by `GSC_ALLOW_DESTRUCTIVE=true`) |
| `gsc_search_analytics` | Custom Search Analytics query |
| `gsc_site_snapshot` | Aggregated totals last N days vs prior period |
| `gsc_quick_wins` | Queries in positions 4-15, scored by `impressions × CTR-gap-to-pos-3` |
| `gsc_traffic_drops` | Pages losing traffic, classified `ranking_loss` / `ctr_collapse` / `demand_decline` |
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
| `ga4_anomalies` | Daily spikes/drops via leave-one-out Z-score, optionally segmented |
| `ga4_traffic_drops_by_channel` | Channels in decline, multi-axis: volume / engagement / conversion / bounce |
| `ga4_landing_page_health` | Health score (red/amber/green) for top landing pages |
| `ga4_conversion_funnel` | Step-by-step user counts with severity-tagged drop-off |
| `ga4_cohort_retention` | New vs returning visitor metrics |
| `ga4_channel_attribution` | First-touch vs last-touch comparison; classifies as assister / closer / balanced |
| `ga4_content_decay` | GA4 metric decline across 3 consecutive 30-day windows (any metric) |

</details>

<details>
<summary><b>🛠️ Meta</b></summary>

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
| **This MCP** | **The unified Python suite: GSC + GA4 + 5 unique cross-platform tools (journey, opportunity matrix, health check, attribution, full diagnosis), with anti-hallucination provenance, leave-one-out Z-score, real funnels, and read-only-by-default safety.** Pick if your agent reports to clients and you can't afford a hallucinated number — or a missed cross-source insight. |

This MCP started as a security-audited synthesis of seven open-source projects — credits at the bottom.

## FAQ

**Why use this over the official Google MCP?** The official MCP is a transport layer — wrappers around `runReport` and `searchanalytics.query`. Useful if you're building your own logic. This MCP adds 25+ tools with diagnostic logic baked in (classifications, scoring, anti-hallucination provenance) plus the 6 cross-platform tools that no single-source MCP can provide.

**My site has very little traffic. Will this work?** Yes, but lower the thresholds. For sites under 500 clicks/mo, set `min_impressions=25-50` on `gsc_quick_wins` and `min_clicks_prior=5-10` on `gsc_traffic_drops`. Below ~100 clicks/mo, the issue is usually content/indexation rather than optimization — pivot to `gsc_inspect_url` and `gsc_list_sitemaps`. Don't fabricate recommendations from empty data; the agent should explicitly say *"insufficient sample for trend detection"* when thresholds aren't met. See [`AGENTS.md`](AGENTS.md) §9 for full edge-case handling.

**Does this measure AI Overview impact?** Not directly — it's GSC + GA4 only, no SERP scraping. But the inference is reliable: pages ranking 1-3 with CTR collapse vs historical baseline are high-confidence AIO hits, especially when correlated with rollout dates from `resource://algorithm-updates`. See [`AGENTS.md`](AGENTS.md) §7 for the full inference protocol.

**My GA4 has no ecommerce — will revenue tools still work?** They run, but `attributed_revenue` will be 0 across the board. **Don't conclude SEO has no ROI** — the agent should flag this as a tracking-config gap and suggest `ga4_search_schema(keyword='revenue')` to confirm what fields are available.

**What about ad-blocker traffic?** Common in DACH/tech audiences. `cross_traffic_health_check` will flag `tracking_gap` when GA4 systematically under-reports vs GSC. Apply +15-30% upward correction on GA4 organic and disclose to the user.

**Does it work with `sc-domain:` properties?** Yes — but the `site_url` string must match exactly what `gsc_list_sites` returns. Don't manually compose `https://example.com/` if the registered property is `sc-domain:example.com` — cross-platform path normalization handles both internally, but the join key requires the canonical form.

## Authentication

### Default — Application Default Credentials (recommended)

```bash
gcloud auth application-default login \
  --scopes=https://www.googleapis.com/auth/webmasters.readonly,https://www.googleapis.com/auth/analytics.readonly
```

The authenticated Google account must be a verified user in **both**:
- **Search Console** for each property (Property → Settings → Users and permissions)
- **Analytics 4** for each property (Admin → Property → Property Access Management)

<details>
<summary><b>Advanced auth methods</b> — Service account / OAuth flow</summary>

### Service account (headless servers)

```bash
export GOOGLE_SEO_SERVICE_ACCOUNT_FILE=/path/to/sa-key.json
```

The service account email must be added as a user in both GSC and GA4 for each property.

### OAuth user flow (interactive)

```bash
export GOOGLE_SEO_OAUTH_CLIENT_FILE=/path/to/client_secret.json
```

The first call opens a browser; the token is cached at `~/Library/Application Support/google-seo-mcp/token.json` (macOS) or the equivalent `XDG_CONFIG_HOME` location.

</details>

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
| `GOOGLE_APPLICATION_CREDENTIALS` | gcloud ADC default | ADC file path |
| `GOOGLE_SEO_OAUTH_CLIENT_FILE` | — | Desktop OAuth client JSON |
| `GOOGLE_SEO_SERVICE_ACCOUNT_FILE` | — | Service account key path |
| `GSC_ALLOW_DESTRUCTIVE` | `false` | Enables sitemap submission and write-scope OAuth |
| `GSC_CTR_BENCHMARKS` | conservative defaults | Comma-separated 10 floats overriding per-position expected CTR |
| `GOOGLE_SEO_LOG_LEVEL` | `INFO` | Python log level |

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

```bash
# Unit tests with mocks (no network)
.venv/bin/pytest tests/ -v

# End-to-end smoke test against your real Google APIs
.venv/bin/python scripts/smoke_test.py
```

The smoke test probes all six layers of the MCP (auth, admin discovery, reporting, intelligence, cross-platform, resource) and surfaces real bugs the way they'll appear in production. It's the first thing to run after any code change.

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
