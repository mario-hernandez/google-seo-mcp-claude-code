# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-04-29

### Added — Migration module (15 new tools, 54 → 69 total)

A new module `migration/` for sites moving from WordPress to a modern JS
stack (React + Node SSR + pre-render). All tools are read-only on the
source site. Designed around three real workflows:

**WordPress equity extraction (3 tools)**:
- `migration_wp_audit_site` — REST API inventory: post types, taxonomies,
  plugin probes (Redirection / RankMath / Yoast Premium), URL list
- `migration_wp_extract_redirects` — enumerate redirects from common plugins
- `migration_wp_internal_links_graph` — advertools crawl + in/out degree
  per page, orphan detection, top hubs

**SSR / pre-render verification (5 tools)**:
- `migration_prerender_check` — fetch URL without JS, verify SEO signals
  (title, meta, OG, schema, canonical, h1, visible text)
- `migration_prerender_vs_hydrated` — diff curl HTML vs Playwright DOM
  after hydration (lazy import; install `playwright` extra)
- `migration_googlebot_diff` — UA diff Googlebot vs user, detects cloaking
- `migration_multi_bot_diff` — three-way diff (Googlebot / Bingbot / user)
- `migration_verify_googlebot_ip` — reverse-DNS check per Google's spec

**Sitemap diff + 301 redirects planner (7 tools)**:
- `migration_sitemap_diff` — URLs added/removed/common between two sitemaps
- `migration_sitemap_validate` — HEAD-check sample of URLs, status dist
- `migration_redirects_plan` — fuzz-match old → new URLs (rapidfuzz)
- `migration_export_redirects_nginx` / `_apache` / `_cloudflare` — render
  the plan as deployable config

**Composer**:
- `migration_seo_equity_report` — combines WP inventory + advertools crawl +
  GSC clicks + internal-link graph into a 0-100 equity score per URL with
  classification (MUST_PRESERVE / WORTH_PRESERVING / LOW_VALUE / DEPRECATE)

### New deps

- `advertools>=0.16.0` (Scrapy-based crawler, 1.4k stars OSS)
- `rapidfuzz>=3.0.0` (slug similarity, 1MB)
- `playwright>=1.40.0` (optional, only for `prerender_vs_hydrated` —
  install with `pip install google-seo-mcp[ssr]`)

### Bug fixed pre-release

- `_extract_signals` now decodes HTML entities (`&iquest;` → `¿`) before
  comparison so encoding differences don't trigger false-positive cloaking
  alerts. Detected during smoke test against example.com (WordPress
  serves entity-encoded vs UTF-8 to different UAs but both are
  semantically identical).

## [0.2.1] — 2026-04-27

### Documentation
- README and AGENTS.md now mention the optional `PAGESPEED_API_KEY` env var
  required to use Lighthouse and CrUX tools beyond the anonymous quota
  (which is shared and tends to be 429-throttled). Same key works for both
  APIs when the GCP project has them enabled.

## [0.2.0] — 2026-04-27

### Added — SEO swiss-knife expansion (21 new tools, 33 → 54)

**Lighthouse / PageSpeed Insights v5** (5 tools, free 25k req/day):
- `lighthouse_audit` — full mobile/desktop audit with perf/a11y/best-practices/SEO scores + CWV
- `lighthouse_core_web_vitals` — LCP/CLS/TBT/FCP/Speed Index/TTI only
- `lighthouse_lcp_opportunities` — actionable improvements ranked by estimated savings ms
- `lighthouse_compare_mobile_desktop` — side-by-side delta (mobile regressions are common)
- `lighthouse_seo_score` — SEO-category breakdown (meta descriptions, viewport, hreflang, etc.)

**Chrome UX Report (real-user CWV)** (3 tools, free 150 QPS):
- `crux_current` — latest 28-day field data for URL or origin
- `crux_history` — up to 25 weekly snapshots (~6 months) of one metric, to correlate
  with `gsc_traffic_drops` dates
- `crux_compare_origins` — your origin vs a competitor

**Schema.org / structured data** (3 tools, fully offline):
- `schema_extract_url` — fetch URL + extract JSON-LD/microdata/RDFa via `extruct`
- `schema_validate_url` — pre-flight checks for Article/Product/FAQPage/HowTo/Breadcrumb
  (without external validator)
- `schema_suggest_for_page` — recommend schemas given page intent

**Sitemap & indexing submission** (5 tools):
- `indexnow_generate_key` — 32-char ownership key for IndexNow
- `indexnow_submit` — push URLs to Bing/Yandex/Seznam
- `indexnow_submit_sitemap` — fetch sitemap.xml and chunk-submit (max 10k/chunk)
- `google_indexing_publish` / `google_indexing_delete` — Google Indexing API
  (gated by `GSC_ALLOW_DESTRUCTIVE=true`, requires `indexing` OAuth scope)

**Trends / Suggest / Alerts** (5 tools, free):
- `google_suggest` — autocomplete suggestions for one keyword
- `google_suggest_alphabet` — 26-letter expansion (`keyword + a..z`) for long-tail discovery
- `google_trends_keyword` — relative search interest timeline (pytrends)
- `google_trends_related` — top + rising related queries
- `alerts_rss_parse` — parse a Google Alerts RSS feed

### Updated
- `get_capabilities` now surfaces all 7 categories with the swiss-knife workflow tip
- `pyproject.toml` adds deps: `httpx`, `extruct`, `pytrends`
- 57 tests passing (1 updated count assertion)

## [0.1.1] — 2026-04-27

### Added
- This CHANGELOG.

### Removed
- A personal session-resume markdown note accidentally tracked in v0.1.0;
  now in `.gitignore`. Contained only a local home-directory path and a
  public OSS email — no credentials.

### Changed
- README example anonymised to use generic `example.com` / `properties/123456789`
  placeholders instead of identifiers from the author's employer. The previous
  values were valid public identifiers, not credentials; this is just hygiene.
- Git history rewritten on 2026-04-27 to remove the same identifiers from
  past commits. Tag `v0.1.1` was force-updated to point at the cleaned history.

### Fixed
- **`gsc_traffic_drops`** now correctly classifies pages absent from the current
  period as `"disappeared"` (previously fell through to `ctr_collapse`).
- **`ga4_anomalies`** Z-score now skips segments with near-zero variance to
  prevent false positives on near-constant series with a single outlier
  (sigma must be ≥ max(0.5, |μ|·0.01)).
- **`cross_opportunity_matrix`** auto-calibration uses `statistics.median` and
  falls back to a 25th-percentile threshold for fewer than 4 candidates
  (previously degenerated to a single-element "high" group with N=2).
- **`ga4_traffic_drops_by_channel`** classifications now require both relative
  *and* absolute deltas (engagement ≥ 0.02 absolute, bounce ≥ 0.05 absolute)
  to avoid trivial false positives on near-zero rates.
- **`cross_traffic_health_check`** aligns both windows to GSC's 3-day lag so
  the GSC/GA4 ratio compares the same calendar dates.
- **`cross_gsc_to_ga4_journey`** now normalises path-only `landing_path` to a
  single leading slash, preventing malformed concatenation
  (`https://x.comblog/post`) and protocol-relative confusion.
- **`reauthenticate`** now also deletes the cached OAuth `token.json` (opt-out
  via `drop_oauth_token=False` keyword on the underlying helper).
- **`gsc/analytics.py`** 401 error message renamed `GSC_OAUTH_CLIENT_FILE` →
  `GOOGLE_SEO_OAUTH_CLIENT_FILE` to match the actual env var.
- **Documentation** counts corrected: 6 cross-platform tools (was 5), 12 GSC
  (was 14), 13 GA4 (was 14). README JSON example wrapped in
  `{"data": ..., "_meta": ...}` (was unwrapped, invalid JSON).

## [0.1.0] — 2026-04-26

### Added
- Initial public release.
- 33 tools: 12 GSC, 13 GA4, 6 cross-platform, 2 meta.
- 1 MCP resource: `google-seo://algorithm-updates` (2023–2026 update reference).
- Unified auth requesting both `webmasters.readonly` and `analytics.readonly`
  scopes in a single OAuth flow.
- 42 unit tests (auth scopes, normalize_property, GA4 filter builder including
  NumericValue regression, date adjacency, GSC analytics totals, server
  registration).
- `scripts/smoke_test.py` for end-to-end validation against real Google APIs.
- AGENTS.md operator guide synthesised from three specialist perspectives
  (technical SEO, local SEO + SERP, marketing growth analytics).
- Predecessor repos archived with redirect READMEs:
  `google-search-console-mcp-claude-code`,
  `google-analytics-mcp-claude-code`.

[Unreleased]: https://github.com/mario-hernandez/google-seo-mcp-claude-code/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mario-hernandez/google-seo-mcp-claude-code/releases/tag/v0.1.0
