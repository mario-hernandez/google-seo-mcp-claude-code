# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.1] — 2026-04-30

### Stability hardening — multi-client production readiness

A 5-reviewer panel (Edge Cases QA, Exception Handling, Concurrency,
Test Coverage, MCP Protocol Hygiene) audited v0.7.0 with one mandate:
**no new features, only bugs and instabilities**. They returned ~80
findings; the P0 / P1 ones (real crashes and silent-wrong-data risks)
are fixed below. Tools registered: still 78. Tests: 74 → 92.

### P0 — guaranteed crashes fixed

- `lighthouse_core_web_vitals` raised ``KeyError`` on every call: it
  asked for the key ``core_web_vitals`` after v0.5 renamed it to
  ``core_web_vitals_lab``. Now returns lab + field + lab_metrics
  together.
- `migration/sitemap_diff.py` had ``time.sleep`` referenced before
  ``import time`` (later in the same function) → ``NameError`` on the
  first ``sitemap_validate`` call. Moved import to module top.
- `migration/redirects_plan.py` unpacked ``rapidfuzz.process.extractOne``
  output as ``(slug, score, idx)`` without guarding against the API
  returning a different tuple length (rapidfuzz < 3) → ``ValueError``.

### P0 — silent wrong data fixed

- **Account rotation across clients no longer leaks data**. The auth
  module hashes ``GOOGLE_APPLICATION_CREDENTIALS`` /
  ``GOOGLE_SEO_SERVICE_ACCOUNT_FILE`` / ``GOOGLE_SEO_OAUTH_CLIENT_FILE``
  paths, their mtimes, and the OAuth ``token.json`` mtime into a
  fingerprint. When the operator runs a different ``gcloud auth
  application-default login`` mid-session (Sofrocay → cliente B →
  cliente C), the singletons are transparently invalidated. The
  previous behaviour silently kept returning data from the previous
  account.
- ``float("")`` crash on empty GA4 metric values fixed in
  ``crossplatform/health.py``, ``crossplatform/multi_property.py``,
  and 9 places in ``ga4/tools/intelligence.py``.
- ``KeyError`` on raw ``p["ctr"]`` / ``c["position"]`` subscripts in
  ``gsc/tools/intelligence.py`` (lines 104, 327, 342). Some GSC rows
  omit ``ctr``/``position`` even when filters pass; every accessor now
  uses ``.get()`` with a 0 default.
- ``ctr_benchmarks()`` env override with fewer than 10 floats now pads
  with the defaults so ``expected_ctr(position)`` never IndexErrors
  for positions 6–10.
- ``equity_report`` URL normalisation: GSC normalises with trailing
  slash, crawl/REST often omit it. The same logical URL was scored as
  two duplicates and equity assigned to the wrong row. New ``_norm_url``
  collapses host case + trailing slash + fragment.

### P1 — concurrency & state correctness

- Thread-safe singletons. ``auth.get_searchconsole/_webmasters/_data_client/_admin_client``
  are now wrapped in a module-level ``threading.Lock`` with a double-
  checked-locking pattern. FastMCP runs tool handlers concurrently;
  without this, two parallel calls could each pass the ``is None``
  check and run a fresh OAuth consent flow simultaneously.
- ``reset_clients()`` also takes the lock so it cannot nuke a
  half-built singleton in the middle of another thread's getter.
- Atomic ``token.json`` write: a same-directory tempfile +
  ``os.replace`` replaces ``token_path.write_text(...)``. Eliminates
  the half-written-JSON failure mode after SIGINT or two concurrent
  OAuth flows.
- ``RefreshError`` from ``creds.refresh(Request())`` is now caught and
  falls through to a fresh consent flow instead of escaping as a raw
  traceback to the LLM.

### P1 — MCP protocol hygiene

- ``logging.basicConfig`` now explicitly uses ``stream=sys.stderr,
  force=True``. Without ``force=True``, libraries imported earlier
  could have already attached a handler to root and ``basicConfig``
  silently no-op'd; without ``stream=sys.stderr`` any log line could
  corrupt the JSON-RPC stdio channel.
- advertools / Scrapy now run with ``LOG_ENABLED=False``,
  ``LOG_STDOUT=False``, ``TELNETCONSOLE_ENABLED=False`` and an explicit
  ``contextlib.redirect_stdout(io.StringIO())`` belt-and-braces around
  ``adv.crawl``. Stops Scrapy's banner / stats prints from corrupting
  the MCP transport.
- ``with_meta`` now passes ``data``/``extra``/``period`` through a
  ``_json_safe`` recursive coercer that handles ``datetime``, ``date``,
  ``Decimal``, ``set``/``frozenset``, ``Path``, ``bytes``, numpy/pandas
  scalars (``.item()``) and falls back to ``str(...)`` rather than
  letting the JSON-RPC encoder explode.

### P1 — Edge / Cloudflare hygiene

- ``cloaking.googlebot_diff`` cache-converge default lowered from 30 s
  to 5 s (still configurable via ``CLOAKING_CACHE_CONVERGE_S``). 30 s
  blocked the FastMCP worker thread for half a minute on every
  divergent fetch — a single cloaking audit could starve every other
  tool call.

### Tests added (regression coverage)

- ``tests/test_stability_fixes.py`` (18 tests): ``_json_safe``
  coercion against datetime / Decimal / set / Path / bytes / numpy /
  weird types; ``with_meta`` payload pass-through; ``health.py`` and
  ``multi_property.py`` ``float("")`` regression with mocked GA4
  responses; auth atomic write success + temp cleanup on failure;
  credentials fingerprint changes on env swap; equity URL
  normalisation; rapidfuzz no-match graceful path.
- ``test_ctr_benchmarks_short_env_does_not_indexerror`` regression
  for the IndexError on padded benchmarks.

## [0.6.0] — 2026-04-29

### 11 fixes from a second senior SEO panel review

Hired a fresh 4-reviewer panel (Enterprise SEO Architect, Multi-region/i18n,
Edge/CDN, Adversarial Security) for a brutal second-opinion audit of v0.5.0.
Verdicts averaged 5.0/10 (range 4.0–5.5) — harder than the first panel
because they attacked angles the first panel didn't touch (enterprise
scale, i18n at scale, multi-CDN, security).

### Security (Adversarial review, 5.0 → 8.0)

THREE CVE-grade vulnerabilities found and fixed:

- **`google_seo_mcp/security.py` (new)** — centralised SSRF guard.
  `assert_url_is_public(url)` resolves the host's A/AAAA records and
  rejects RFC1918, loopback, link-local, AWS/GCP/Azure metadata IPs,
  cloud metadata hostnames, decimal-IP loopback (`http://2130706433`),
  CGNAT, multicast, IPv6 ULA. Override with
  `GOOGLE_SEO_ALLOW_PRIVATE_FETCH=true` only on trusted networks. Hooked
  into every public fetch helper: `prerender.fetch_as_with_meta`,
  `schema.fetch_html`, `migration.sitemap_diff.parse_sitemap`,
  `migration.wp_audit.wp_summary`, `migration.wayback.wayback_baseline`,
  `migration.hreflang._fetch`, `migration.schema_parity._fetch_jsonld`,
  `indexing.tools.indexnow_submit_sitemap`.
- **defusedxml replaces `xml.etree.ElementTree`** in
  `migration/sitemap_diff.py`, `indexing/tools.py`, and `trends/tools.py`.
  Blocks billion-laughs, quadratic blowup, and external-entity attacks
  on attacker-controlled XML feeds.
- **Untrusted-content wrapper** — `security.wrap_untrusted()` and
  `mark_third_party_strings()` envelop scraped HTML title /
  meta_description / OG / h1 strings with
  `<untrusted-third-party-content>...</untrusted-third-party-content>`
  markers and a 10 KB length cap. Blunts prompt-injection attacks where
  a malicious page tries to hijack the LLM by embedding instructions in
  meta tags. Applied to `prerender_signals` outputs.

### Edge/CDN (5.5 → 8.0)

- **Cache convergence flow rewritten** in `cloaking.googlebot_diff`:
  - Wait time now 30 s by default (was 5 s) — `CLOAKING_CACHE_CONVERGE_S`
    env override. CF Tiered Cache + Cache Reserve take 30–90 s to
    converge between POPs; 5 s misclassified warm-up as cloaking.
  - Forces a deterministic origin hit on the second fetch via random
    cache-bust query parameter, so we observe the real origin response
    instead of a HIT/HIT artifact.
- **`cf-cache-status` mapper** — `_cf_cache_status_meaning()` now exposes
  human-readable interpretation for HIT / MISS / EXPIRED / STALE / BYPASS
  / DYNAMIC / REVALIDATED / UPDATING in every fetch result. Decisions
  based on the raw header without semantics produced statistics without
  context.
- **Multi-CDN headers parser** — `fetch_as_with_meta` now also returns
  an `edge` block with Akamai (`X-Akamai-Cache-Status`, `X-Cache`),
  Fastly (`X-Served-By`, `Fastly-Debug-*`), Vercel (`x-vercel-cache`),
  Netlify (`X-Nf-Request-Id`), CloudFront (`X-Amz-Cf-Pop`, `X-Amz-Cf-Id`)
  signals. Cloudflare-only was 2026 myopia.
- **Redirect chain capture** — opt-in `capture_redirects=True` returns a
  `redirects[]` list with every hop's URL, status, location, cf_ray, and
  cf_cache_status. Without it, CF/Workers redirect chains were invisible.
- **Cloudflare Bulk Redirects export schema fixed** —
  `export_redirects_cloudflare()` now emits the official Lists API JSON
  (`{"redirect": {"source_url": "https://...", "target_url": "...",
  "status_code": 301, "include_subdomains": false, ...}}`). Previous
  output (netloc + path, no scheme) was rejected by the Cloudflare
  dashboard import and `wrangler`.
- **`sitemap_validate` concurrent + retry-on-503/504** — was serial
  HEAD; now parallel GET with `Range: bytes=0-0`, ThreadPoolExecutor 10×,
  one retry on 503/504. HEAD-only failed silently against Workers that
  don't route HEAD.

### Multi-region / i18n (5.5 → 8.0)

- **`parse_sitemap_with_alternates()` (new)** in `sitemap_diff.py` —
  parses `<xhtml:link rel="alternate" hreflang="...">` siblings inside
  each `<url>` entry. Sites at IKEA / Booking scale serve hreflang
  exclusively in the sitemap to keep HTML thin; the previous parser
  treated those sitemaps as monolingual. `parse_sitemap()` keeps its
  original return type for back-compat.
- **`gsc_search_analytics` country + device filters** — new params
  `country` (ISO-3166 alpha-3, e.g. `"esp"`, `"mex"`) and `device`
  (`"DESKTOP"|"MOBILE"|"TABLET"`). Critical for post-migration audits
  ("did I lose LATAM?") which were impossible before.

### Migration tools polish

- `prerender.fetch_as_with_meta` now accepts an `accept_language`
  parameter (was hardcoded `en-US,en;q=0.9`). Locale-redirect sites
  forced the wrong variant on every cloaking and SSR audit.

### Dependencies

- Added `defusedxml>=0.7.1` (XXE-safe XML parsing).
- Added `tenacity` to the dev environment for incoming retry/backoff
  work. (Not yet hooked into hot paths — landing in v0.6.1.)

### Tests

- 74 passing (was 57). +17 dedicated to SSRF / untrusted / XXE
  regression in `tests/test_security.py`.

## [0.5.0] — 2026-04-29

### 10 fixes from a senior SEO panel review

Hired four senior reviewers (Tech SEO Lead, Migration Specialist, Performance
Engineer, Cloaking Forensics) who line-by-line audited the codebase and
returned 6.0–7.0/10 verdicts. The fixes below address every consensus
finding without breaking back-compat.

### Fixed — Cloaking detector (Forensics review, 6.5→8.5)

- **Mobile-first index by default**: `GOOGLEBOT_UA` is now the smartphone
  variant Chrome/130 — Google has been mobile-first since 2020, the
  desktop UA we shipped tested the *non-indexed* variant. Killed the
  literal `Chrome/W.X.Y.Z` placeholder that Cloudflare bot management
  blocklists as a spoof signature. Added `GOOGLEBOT_DESKTOP_UA`,
  `GOOGLEBOT_IMAGE_UA`, `GOOGLEBOT_NEWS_UA`, `ADSBOT_UA`, `ADSBOT_MOBILE_UA`
  for completeness.
- **`_meta_signature` now includes `meta_robots` and the OG dict**. The
  highest-value cloaking vector — `noindex` injected only for users — was
  invisible to cache-divergence detection.

### Fixed — Lighthouse / PSI tools (CWV review, 6.0→8.0)

- **`loadingExperience` and `originLoadingExperience` field data are now
  surfaced** in every Lighthouse audit response. PSI embeds them for free
  in the same JSON we already fetch; the previous version threw it away
  and shipped lab-only audits. Added `extract_field_data()` helper.
- **Renamed `core_web_vitals` → `core_web_vitals_lab`**, kept only LCP/CLS
  there (INP is field-only, Lighthouse can't measure it directly). TBT,
  FCP, Speed Index, TTI moved under `lab_metrics` with TBT explicitly
  labelled `tbt_proxy_for_inp`. The official CWV trio in 2026 is
  LCP + INP + CLS, not the six-pack we were exposing.
- **`lighthouse_lcp_opportunities` now filters by `auditRefs.relevantAudits`**
  so only LCP-impacting audits are returned in
  `lcp_relevant_opportunities`. Other performance opportunities go into
  `other_performance_opportunities` — separated, not blended.

### Fixed — CrUX tools

- **`crux_current` auto-falls back to origin** when the URL is not in the
  public dataset. Output gains `scope: "url" | "origin_fallback"` so the
  agent can disclose that it's looking at origin-aggregated data.
- **`crux_compare_origins` now returns `winner`, `metric_unit`, and
  `interpretation`**. Lower p75 is better; the previous version reported a
  raw delta with no semantics — a 0.05 delta is brutal for CLS and
  irrelevant for LCP.

### Fixed — Migration redirects plan (Migration Specialist review, 6.5→8.0)

- **Collision detection**: when N old URLs map to the same target, the
  output now reports them under `collisions[]` so the human can
  disambiguate before deploy.
- **Self-redirect detection**: where `from == to`, the entry goes to
  `self_redirects[]` — these would loop in production.
- **Exact-path lookup is now O(1) via dict index**, not O(N×M). The
  module is now usable on 10k×10k URL migrations.

### Fixed — Hreflang region-awareness

- `hreflang_cluster_audit` no longer treats `es-ES` and `es-MX` as
  interchangeable. When the user specifies a region tag, the matcher
  requires an EXACT region match — the old `startswith(lang+"-")` accepted
  any region and produced false-greens on multi-region clusters.

### Fixed — `crossplatform/diagnosis.py` cannibalization data truncation

- `query_search_analytics` for the cannibalization scan now uses
  `row_limit=25000, fetch_all=True` (was 5000 single-page). Mid-traffic
  sites hit the 5000 cap silently and produced false-negative
  cannibalization reports.

### Fixed — `landingPagePlusQueryString` UTM cardinality bomb

- Switched all four cross-platform tools (`diagnosis`, `journey`, `matrix`,
  `attribution`) from `landingPagePlusQueryString` to `landingPage` for
  EXACT-match filters. Sites with paid traffic explode the former
  dimension's cardinality (one page → 50+ entries) and EXACT match
  silently misses real organic sessions.

### Fixed — `cross_seo_to_revenue_attribution` honesty

- Renamed the output key `attributed_revenue` → `revenue_share_estimate`
  with `revenue_estimate_low` / `_high` (50 % band). Added a top-level
  `caveat` explaining that share-based distribution assumes revenue
  follows clicks, which is false in real e-commerce (transactional
  queries convert 5–10× more on the same page). The old key remains as a
  back-compat alias.

### Fixed — `ga4_conversion_funnel` is now `event_volume_comparison`

- The original docstring admitted the GA4 Data API doesn't enforce
  sequence, but the output presented `drop_off_pct` as if it were a real
  funnel. Renamed to `event_volume_comparison` with explicit warnings;
  output keys are `series` and `last_to_first_user_ratio`. Pointers to
  GA4 `runFunnelReport` (Data API v1alpha) for true sequencing. Old
  `conversion_funnel` remains as a deprecated alias.

### Fixed — Schema fetch UA

- `schema/__init__.py:fetch_html` now uses a real Chrome 130 UA instead
  of the custom `google-seo-mcp/x.y` string that Cloudflare / DataDome /
  Akamai bot management would challenge or A/B-route.

## [0.4.0] — 2026-04-29

### Added — Migration module v2 (4 new tools, 69 → 73 total)

Driven by an independent design review (a fresh team of Ralph Loop iterators
delegated via `docs/delegations/wp-to-jsstack-migration-brief.md`). Their
output proposed several capabilities the original v0.3.0 implementation
missed. Four were integrated:

- `migration_wayback_baseline` — anchor what existed BEFORE migration via
  the Internet Archive CDX API. Free, no key. Use as step 1 of any migration
  workflow so you can prove "what we had" months later.
- `migration_schema_parity_check` — compare JSON-LD between old (WP) and
  new (SSR) URLs. Reports missing types, lost critical properties (e.g.
  `Article.headline`, `Product.offers`), and a `parity_score` 0..1. Catches
  rich-result regressions before Google reindexes.
- `migration_hreflang_cluster_audit` — verify reciprocity across multi-
  language clusters. Cross-domain support (e.g. example.com ES ↔
  example.org FR, which the test surfaced as a real
  gap on the live site).
- `migration_indexation_recovery_monitor` — post-launch monitoring via GSC
  URL Inspection API (NOT the Indexing API, which is officially restricted
  to JobPosting). Aggregates URLs into INDEXED / DISCOVERED / SOFT_404 /
  BLOCKED / ERROR / UNKNOWN with a health classification.

### Improved — `migration_googlebot_diff` and `migration_multi_bot_diff`

The original cloaking detectors were prone to false positives. Added 5
anti-FP guards (also from the fresh-team review):

1. **Entity-encoding equivalence** — `&iquest;` vs `¿` no longer trigger.
   `_extract_signals` already decoded these via `_decode()`; this is now
   documented as the official guard.
2. **Cloudflare Bot Fight Mode** — when a bot UA receives 503/403 with
   `cf-mitigated` header, the verdict is `inconclusive`, not `cloaking`.
3. **Vary header caveat** — if the response doesn't list `User-Agent` in
   `Vary`, the CDN can't legitimately differentiate by UA; surfaced as a
   note before any cloaking flag.
4. **A/B test threshold** — escalation to `critical` now requires both meta
   divergence AND >30% size spread (was 20%). Below: `warning`, not
   `critical`. Filters legitimate A/B tests.
5. **Cache miss vs hit** — when bot/user diverge, double-fetch the user side
   with a 5s gap. If `cf-cache-status` changes between fetches AND content
   changes, mark `cache_artifact_detected: true` and don't flag cloaking.

The output now includes `fp_filters_applied: []`, `cache_artifact_detected`,
and per-UA `cf` metadata (status, ray, cache, vary, server) so you can
trust the `severity` field.

### Added — `fetch_as_with_meta` (internal)

`prerender.py` now exports `fetch_as_with_meta(url, ua)` returning
`{text, status, headers, cf{...}}`. The legacy `fetch_as()` remains as a
backwards-compatible thin wrapper.

### Dependencies

- New: `waybackpy>=3.0.6` (used internally; we hit CDX directly via httpx
  but pin the lib for reference parity with the brief).

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
