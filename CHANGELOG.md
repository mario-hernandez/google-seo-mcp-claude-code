# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.5] — 2026-05-04

### Benchmark rot defense — versioned golden set + meta-validator

The forensic auditor flagged a real maintenance risk in v0.8.4:
``migration_calibration_check``'s golden set (nextjs.org, cloudflare.com,
reactjs.org, create-react-app.dev) could rot silently as those sites
rotate their stacks. A false ``drift_detected`` would then look like a
detector regression when in fact the *benchmark* aged out — wasting
the operator's debugging time. Fixed proactively, not deferred.

### Added

**`_GOLDEN_SET_VERSION` stamp** in every `migration_calibration_check`
response. When an operator sees a ``drift_detected``, the version
field tells them whether their installed MCP has the latest
benchmarks. Mismatch + drift = upgrade. Match + drift = real
detector regression. The version follows a quarterly schema
(``"2026-Q2.1"``) bumped each time the dev rotates entries.

**`migration_meta_validate_golden_set` tool** — a maintenance probe
that verifies the BENCHMARKS still represent what they claim, using
a classifier that does NOT share regexes or thresholds with the
production ``prerender_signals``. The two are complementary:
- Both pass → benchmark + classifier aligned with reality.
- Calibration fails / meta passes → real classifier regression.
- Calibration passes / meta fails → classifier drifted in lockstep
  with the benchmark; reality has moved.
- Both fail → benchmark rot. Site rotated its stack; refresh the
  set, bump version, ship.

The validator uses **macroscopic-property classification**:
independent regex patterns + wider thresholds (>2KB visible text vs
production's >500 chars). This makes it non-tautological — a drift
in either path is caught by the other.

**Updated golden set to v2026-Q2.1** after the new validator caught
real benchmark rot on first run. ``create-react-app.dev`` had drifted
into ``ambiguous`` (1463 chars of pre-rendered text — Docusaurus thin
docs page). Replaced with ``vercel.com`` (Next.js + Vercel,
7000+ chars) and added ``nuxt.com`` as a fifth probe for stack
diversity. Now five different deployment stacks: Next.js, Cloudflare
Workers, Gatsby, Vercel marketing, Nuxt 3.

**Recommended workflow** (in calibration_check docstring): when
``drift_detected``, the response now lists TWO possible causes —
benchmark rot vs detector regression — and tells the operator how to
distinguish them by checking ``golden_set_version`` against the latest
CHANGELOG. Plus an inline maintenance note pointing devs to
``meta_validate_golden_set`` as the proactive guard (run it monthly
or before each release).

### Tool count: 101 → 102.

### Tests
103/103 pass. ``test_tool_count`` updated 101 → 102.

### Backward compatibility
Strictly additive. Existing ``calibration_check`` callers see the
new ``golden_set_version`` field in the response; nothing else
changed. The set rotation (``create-react-app.dev`` → ``vercel.com``
+ ``nuxt.com``) is internal — only matters if someone pinned the old
URL list, which no documented call did.

---

## [0.8.4] — 2026-05-04

### 4 fixes from a third real-world feedback pass (forensic audit consultant)

A migration consultant ran v0.8.3 through a forensic audit of a live SSR
site and returned a precise feedback list. Each addresses an
operational gap that bites the agent at the *worst* possible moment —
mid-audit. All four fixed.

### Added

**`get_capabilities` now exposes `tools_unavailable` and `deps`**. The
forensic auditor was launching `migration_prerender_vs_hydrated` in
parallel with three other audits and discovered Playwright wasn't
installed mid-execution. Now the agent can plan around missing deps
**before** invoking. Probe runs at module import time (~5ms total),
covers Playwright, statsmodels+scipy, advertools, extruct, rapidfuzz,
pytrends, waybackpy, defusedxml. Each unavailable dep documents
`install_cmd` + `extra_cmd` + `affected_tools` + whether the absence
is fatal or just degraded. New module: `_dep_check.py`.

**Per-facet `health_breakdown` in `prerender_signals`**. The auditor
flagged a real conceptual confusion: nextjs.org returns
`prerender_mode=ssr, viability=6/6` but `health=amber`. The agent
reading just `health` couldn't tell whether rendering was broken
(cutover blocker) or merely canonical/schema were missing (post-launch
fix). Now the response includes:
```json
"health_breakdown": {
  "rendering": "green",       ← derived from prerender_mode only
  "title": "green",
  "meta_description": "green",
  "canonical": "amber",       ← THIS is why overall health is amber
  "schema": "amber",          ← AND this
  "open_graph": "green",
  "h1": "green",
  "visible_text": "green"
}
```
The aggregate `health` semaphore is preserved; the breakdown makes the
*why* explicit so an agent can branch on rendering specifically.

**Contextual `notes` + `cf`/`server`/`http_status` in `prerender_signals`**.
The auditor specifically called out `migration_googlebot_diff` as
"bordada" (impeccable) for emitting heuristic annotations like
*"\`Vary\` header is 'accept-encoding' (no User-Agent). The CDN cannot
legitimately differentiate by UA"* — exactly what an agent needs to
interpret a result without inferring. Now `prerender_signals` emits
the same caliber:
- Framework detection (`#__next`, `#__nuxt`, react-helmet-async, Vite)
- Cloudflare cache awareness (`cf-cache-status: DYNAMIC` vs `HIT`)
- Vary header sanity check (mirrors googlebot_diff pattern)
- Schema absence escalation
- Soft-404 callout
- Forensic surface: `cf.cache_status`, `cf.ray`, `cf.vary`, `server`,
  `http_status` — same shape as googlebot_diff so the two tools cross-reference cleanly.

**New tool: `migration_calibration_check`**. The auditor today had to
manually probe nextjs.org as a control sample to verify the SSR
detector wasn't drifting. Now the MCP can do that itself: runs
`prerender_signals` against a curated set of public sites with known
prerender behaviour (nextjs.org, cloudflare.com, reactjs.org,
create-react-app.dev — all SSR/SSG). Returns
`instrument_status: calibrated | drift_detected | partial` plus a
human-readable `recommendation`. Use this BEFORE high-stakes forensic
audits to confirm the detector is working. Optional `extra_targets`
parameter to extend the golden set with your own controls.

### Tool count: 100 → 101.

### Tests
103/103 pass. `test_tool_count` updated 100 → 101.

### Backward compatibility
All v0.8.3 fields and tools preserved. New fields added alongside.
`prerender_signals` now also emits `cf`/`server`/`http_status` because
it switched from `fetch_as` to `fetch_as_with_meta` internally — same
HTTP fetch, additional headers preserved.

---

## [0.8.3] — 2026-05-04

### 4 refinements after deeper real-world use of v0.8.2

A migration consultant returned a second pass of feedback after running
the full v0.8.2 audit on a live site. Three precise refinements + one
hypothesis-testable bonus. All four fixed.

### Fixed

**`migration_redirect_chain` now includes `location` per hop and
`final_url` top-level**. The docstring promised `{url, status, location}`
but only `{url, status}` was emitted, forcing agents to write
`chain[chain.length-1].url` to recover what should have been a sibling
field. Now each hop carries `location` (the absolute URL of the next
hop, or `null` on terminal hops) and the top-level result includes
`final_url` alongside `final_status`. Spec now matches reality:

```json
{
  "chain": [
    {"url": "/foo/", "status": 301, "location": "https://.../foo"},
    {"url": "/foo",  "status": 301, "location": "https://.../bar"},
    {"url": "/bar",  "status": 200, "location": null}
  ],
  "hops": 2,
  "final_url": "https://.../bar",
  "final_status": 200,
  "loop": false, "broken": false, "cross_domain": false
}
```

**`prerender_mode_viability` — structured per-crawler boolean matrix**
sits next to the human-prose `prerender_mode_explanation`. The
explanation text described which crawlers fail in each mode, but an
agent that wants to gate a cutover decision (`if not viability.aeo_bots:
block_cutover()`) had to parse natural language. Now both layers exist:

```json
"prerender_mode": "head_only",
"prerender_mode_explanation": "<human prose>",
"prerender_mode_viability": {
  "googlebot_with_js": true,
  "googlebot_without_js": false,
  "bingbot": false,
  "aeo_bots": false,
  "social_scrapers": false,
  "wayback_machine": false
}
```

The matrix is keyed on the actual crawl behaviour of each agent class:
Googlebot (with/without JS), Bingbot, AEO bots (ChatGPT/Claude/Perplexity),
social scrapers (Facebook/Twitter/LinkedIn), Wayback Machine. For
`unknown` mode all values are `null` (don't make assumptions).

**New tool `migration_prerender_check_batch`** for paralleled multi-URL
audits. The single-URL `migration_prerender_check` was forcing serial
loops over 70+ URL audits, taking 5+ minutes most of which was network
wait. Batch version runs concurrent fetches with a configurable
`concurrency` parameter (default 8) and returns a `summary` aggregate
the agent can read in one glance to decide ship/no-ship:

```json
"summary": {
  "total": 73,
  "ssr": 0, "head_only": 73, "csr": 0, "unknown": 0,
  "errors": 0,
  "any_red": true, "any_head_only": true, "all_ssr": false
}
```

**Hardened JSON-LD detector regex** in `prerender_signals`. The original
pattern was strict enough to miss real-world variants:
- whitespace around `type =` (some prettifiers emit this)
- whitespace before the closing `>` of `</script >`
- extra attributes before `type=` (data-react-helmet, nonce, async, defer)

Now tolerant of all three. New `tests/test_jsonld_detector.py` locks
in 11 cases covering the variants seen in the wild plus the false-positive
guards (no match for `application/json` or plain `<script>`). For
rigorous parsing use `schema_extract_url` (extruct-based); this regex
remains a fast heuristic count for `prerender_signals`.

### Tests
103/103 pass (was 92; +11 new in `test_jsonld_detector.py`).
`test_tool_count` updated 99 → 100.

### Backward compatibility
Strictly additive. All v0.8.2 fields and tools preserved; new fields
added alongside existing ones; the new batch tool sits next to the
single-URL one (both work).

---

## [0.8.2] — 2026-05-04

### 4 fixes from a real-world technical review during a live migration

A migration consultant ran the MCP through a full SEO migration audit and
returned a precise, prioritised feedback list. All four findings fixed
without breaking changes.

### Fixed

**`get_capabilities` no longer drifts from registered tools** (the most
serious of the four — it caused all the others). The previous version
hardcoded a `categories` dict that hadn't been updated since v0.6.x, so
~30 tools were registered but invisible to anyone discovering the MCP
via `get_capabilities` (`aeo_*`, `history_*`, `serp_*`, `logs_*`, the
new `migration_redirect_chain`/`_chains`, `migration_image_alts`/
`_coverage`, `migration_robots_audit`/`_diff`, `reload_credentials`).
Replaced with `_categorize_registered_tools()` which derives categories
**dynamically** from the actual registered tools using a
prefix→category rules table. New tools land in their category
automatically; unknown prefixes fall back to `meta` so the operator
still sees them and can file a PR to add the rule. The output now
includes `tools_total` so callers can sanity-check the count.

**`migration_prerender_check` distinguishes 3 prerender modes**.
Previously the only output was `health: green/amber/red` plus a flat
`looks_like_spa_shell` issue tag, conflating two operationally
different states: a project with head-only injection (head OK but body
empty — works for Googlebot's JS-rendering pipeline, fails for
Bingbot/AEO bots/social scrapers) was indistinguishable from a pure
CSR catastrophe. Added a `prerender_mode` field with values
`ssr` / `head_only` / `csr` / `unknown` plus a
`prerender_mode_explanation` describing what each means for which
crawlers. `health` semaphore preserved for at-a-glance verdict.

**Untrusted-content wrapping is now targeted, not blanket**.
`prerender_signals` previously wrapped every string field
(`title`, `meta_description`, `og.*`, `canonical`, `h1`,
`visible_text`, etc.) in `<untrusted-third-party-content>` markers
as defense against prompt injection. The reviewer pointed out
correctly that meta tags are short literal strings constrained by
HTML parsing rules, and wrapping them made LLMs quote them
literally to users instead of treating them as data. Now only
`body_excerpt` (free-form scraped paragraphs) gets the wrapper.
Structural meta fields are returned bare. Prompt-injection defense
preserved where it actually matters.

**GA4 tools now expose `property_timezone` and `property_currency`**.
The `RunReportResponse.metadata` from GA4 Data API carries the
property's configured timezone (e.g. `Europe/Madrid`) and currency
(`EUR`), but the MCP was discarding both. For queries with relative
dates (`yesterday`, `last_7_days`), the result silently depended on
the property's TZ — invisible to the agent. Now `_serialize_response`
captures them and `query_ga4` propagates them into `_meta` via
`extra`. The agent can now interpret dates against the right zone
instead of guessing UTC.

### Tests
92/92 pass. No new tests needed — fixes are additive metadata exposure
and stricter classification, not behavior change to existing flows.

### Backward compatibility
Strictly additive. All existing fields in `get_capabilities`,
`prerender_signals`, and `query_ga4` outputs preserved; new fields
added alongside.

### Acknowledgment
The `get_capabilities` drift bug had been silently degrading the MCP
since v0.6.x. The technical review made it visible. **Get_capabilities
auth status (`gsc.ok` + `ga4.ok` + `credential_type`)** was
specifically called out as helpful — keeping that contract going forward.

---

## [0.8.1] — 2026-05-04

### Singular convenience wrappers for two batch tools

Triggered by a real user (technical migration consultant) who tried to
call `migration_redirect_chain` (singular) — a name several internal
playbooks had standardized on — and found that only the plural
`migration_redirect_chains` (which takes a URL list) existed. The
consultant fell back to `curl -ILs` manually rather than discover the
real name. Same papercut existed with `migration_image_alts` (docs)
vs `migration_image_alt_coverage` (code).

### Added
- `migration_redirect_chain` — singular convenience wrapper. Takes a
  single URL string (not a list), returns the chain dict directly
  (not nested inside `results[0]`). Internally calls the plural
  batch version with a list of one.
- `migration_image_alts` — singular convenience wrapper for
  `migration_image_alt_coverage`. Same pattern.

Both plural batch tools (`migration_redirect_chains`,
`migration_image_alt_coverage`) remain unchanged and recommended for
URL-list workflows. Tool count: 97 → 99.

### Why both names exist
The plural names are correct for the *underlying* operation (the
implementation crawls a list and returns a list of results). But
operators reaching for these tools usually have ONE URL in mind and
expect a singular result. Forcing them to wrap in `[url]` and unwrap
`results[0]` is friction. Keeping both names gives the agent a clean
choice — singular for one, plural for many — without renaming and
breaking existing playbooks.

### Tests
92/92 pass. `test_tool_count` updated 97 → 99.

### Backward compatibility
Strictly additive. No behavior change to existing tools.

---

## [0.8.0] — 2026-05-04

### Four new modules: persistence, SERP intelligence, server log analysis, advanced technical crawl

This is the largest tool surface bump in the project's history: **18 new
tools across 4 new modules**, taking the catalog from 79 → 97. All new
modules follow the same `_meta` provenance contract, anti-hallucination
guardrails, and cascade-aware authentication as the existing tools.
Read-only by default. Service Account authentication supported across
the board.

### Added — `history/` module (3 tools, free)

Turns one-shot queries into a longitudinal monitor. Persists tool outputs
to a per-client filesystem store (`~/.google-seo-mcp/history/`) and
diffs them across snapshots so the agent can answer "what changed since
last week?" without re-running the analysis.

- `history_save_snapshot` — persist any tool output (typically
  `gsc_site_snapshot`, `cross_traffic_health_check`, `cross_opportunity_matrix`)
  to a per-client filesystem store. Idempotent, content-hashed.
- `history_diff` — compare two snapshots, classify field changes, emit
  alerts on critical drops (clicks, impressions, position).
- `history_list` — enumerate stored snapshots per client / tool.

### Added — `serp/` module (4 tools, DataForSEO-backed)

Direct SERP queries to confirm AI Overview presence, People Also Ask,
featured snippets, and competitor intersection — the layer that pure
GSC + GA4 cannot reach. Requires `DATAFORSEO_LOGIN` and
`DATAFORSEO_PASSWORD` env vars. Pay-as-you-go (~\$0.0006 per Live SERP
call); ~\$0.20 / year for a typical small client doing monthly audits.
Tools degrade gracefully (no exception, returns
`{"error": "credentials_missing", "fix": ...}`) when credentials absent.

- `serp_check` — single Live SERP query, returns organic + AI Overview
  + PAA + featured snippet + sitelinks.
- `serp_aio_monitor` — batch of queries → which have AI Overview now.
  Use to confirm whether a CTR-collapsing query is being eaten by AIO.
- `serp_paa_extractor` — extract PAA questions to inform FAQPage schema
  authoring.
- `serp_competitor_intersect` — top 10 organic competitors for a query
  and where your domain ranks within it.

### Added — `logs/` module (7 tools, free)

Server-side access log analysis. Parses NCSA Combined / JSON / Cloudflare
Logpush from local files; cross-references with GSC sitemaps to surface
crawl waste; verifies Googlebot IPs via official ranges + reverse DNS.
This is the layer GSC URL Inspection cannot reach — "what is Googlebot
*actually* fetching, at what frequency, and what fraction returns 5xx?"

- `logs_parse` — parse a log file (Combined / JSON / Cloudflare) into
  normalized rows. Auto-detects format by default.
- `logs_googlebot_crawl_budget` — per-URL Googlebot fetch frequency
  + status code distribution.
- `logs_bot_ratio` — Googlebot vs Bingbot vs other-bots vs human ratios.
- `logs_spider_trap_detector` — URLs hit excessively (default >100×)
  by any single bot — likely a faceted-search trap or session-id leak.
- `logs_crawl_waste` — URLs Googlebot fetches that are NOT in any
  configured sitemap. Classic finding for "stop crawling the search
  page, it's eating budget".
- `logs_status_distribution` — 2xx / 3xx / 4xx / 5xx breakdown by
  bot identity.
- `logs_verify_googlebot_ip` — checks an IP against Google's
  published JSON ranges + does forward+reverse DNS validation.
  Catches User-Agent spoofers.

### Added — `migration/crawl_advanced.py` (4 tools)

Pre-cutover technical audit: redirect chain depth, broken internal
links, response-time distribution, image alt coverage. Used in tandem
with the existing migration tools when the migration is complex enough
to need pre-flight assurance beyond the usual sitemap diff.

- `migration_redirect_chains` — for a list of URLs, return the full
  301/302 chain depth. Flags chains > 2 hops (Googlebot drops at 5).
- `migration_broken_internal_links` — crawls a homepage one level
  deep and reports any internal `<a href>` returning 4xx/5xx.
- `migration_response_times` — p50 / p95 / p99 server response time
  per URL. Sample-based.
- `migration_image_alt_coverage` — fraction of `<img>` tags missing
  `alt`. Per-page and aggregated across the crawl.

### Tool count: 79 → 97 (+18)

### Tests
92/92 pass. `test_tool_count` updated 79 → 97.

### Backward compatibility
All v0.7.x tools and behaviors unchanged. New env vars are opt-in:
- `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` — required only if you
  use any `serp_*` tool. Tools fail gracefully (no exception) if absent.
- `GOOGLE_SEO_HISTORY_DIR` — overrides the default
  `~/.google-seo-mcp/history/` location for `history_*`.

---

## [0.7.4] — 2026-05-04

### `get_capabilities` now exposes `mcp_version` and `credential_type`

Triggered by a real-world papercut during the v0.7.3 rollout: an operator
reinstalled an editable venv after a `git pull` and `pip show` reported
the OLD version (0.7.0) because metadata is cached at install time. The
operator had no in-band way to verify which version of the code the MCP
process was actually executing in memory.

### Added

- **`get_capabilities` returns `mcp_version`**. Resolved at runtime via
  `importlib.metadata.version("google-seo-mcp")`. Returns
  `"unknown (not installed as a package)"` if the package isn't
  resolvable. Lets agents and operators verify in-band — no `pip show`,
  no checking the binary path with `ps aux`, no guessing.

- **`get_capabilities.auth` now includes `credential_type`**. Mirrors
  the cascade order in `auth.py` so callers can confirm which method is
  active (`'service_account'` / `'adc'` / `'oauth_flow'` / `'none'`).
  Same value also returned by `reload_credentials`.

### Why this matters operationally

Editable installs (`pip install -e .`) execute code directly from the
source path, so the live MCP process runs whatever's currently on disk.
But `pip show` reads the wheel metadata cached at install time, which
diverges as soon as you `git pull` without reinstalling. The new
`mcp_version` field reads the metadata fresh on every `get_capabilities`
call, eliminating the divergence as a source of confusion.

### Tests
92/92 pass. No new test required — the field is a pure read of
`importlib.metadata`.

### Backward compatibility
`get_capabilities` schema is additive (new fields, no removals). All
existing callers keep working.

---

## [0.7.3] — 2026-05-04

### Auth UX hardening based on real-world setup feedback

A user finished a fresh setup with `v0.8.0`-class binary on a new machine
(ADC revoked + OAuth blocked by Workspace + new Service Account). The
v0.7.2 doc improvements helped them eventually reach a working state,
but they hit four runtime / UX issues during the journey. All four fixed.

### Runtime fixes

- **`auth.py` — proactive ADC refresh validation**. `_from_adc()` now
  ALWAYS attempts a `creds.refresh()` (not just when `creds.expired`)
  whenever the ADC has a refresh token. This catches the case where
  `creds.expired = False` but the underlying refresh token has been
  silently revoked by Google — previously surfaced as a confusing
  `invalid_grant` 503 deep inside the first tool call. Cost: ~100ms
  one-time RPC at MCP cold start. Benefit: fail-fast with a clean
  fallback to the configured Service Account, or an actionable error.

- **`reset_clients()` and the new `reload_credentials` tool**. The old
  `reauthenticate` name was misleading when the active credential is a
  Service Account (SA tokens are self-issued JWTs — there's no
  "re-auth" handshake to perform). The function now:
  - Detects the active credential method (service_account / adc /
    oauth_flow / none).
  - Returns a credential-aware message explaining what just happened.
  - Returns the credential_type in the response so the agent IA can
    set expectations appropriately.

- **New tool: `reload_credentials`**. Cleaner name for the operation.
  `reauthenticate` kept as deprecated alias for backward-compat.
  Total tool count: 78 → 79.

### Documentation fixes

- **README.md decision matrix and Authentication section reordered**.
  Service Account is now the recommended default, listed first and
  fully expanded. ADC and OAuth Desktop flow demoted to secondary
  options with clear conditions ("if you're a single dev with a
  working browser AND your OAuth client is verified"). The previous
  ordering (ADC first, SA hidden in `<details>`) led real users to
  pick the wrong method for their environment.

- **README.md GOOGLE_PROJECT_ID**: documented that this var is
  fingerprint-only — does NOT route requests to a specific GCP
  project. The actual project is inferred from the active credential.
  Setting it wrong does not break anything.

- **README.md GSC + Service Account UI rejection**: documented that
  Search Console's "Add user" picker often rejects SA emails with
  "user not found", with three workarounds in order of preference
  (Domain-Wide Delegation, DNS TXT verification, reusing a verified
  SA). One real user wasted 10 minutes on this — now documented.

- **README.md cleaner setup recommendation**: when running on Service
  Account, explicitly recommend unsetting `GOOGLE_APPLICATION_CREDENTIALS`
  and renaming the stale ADC file. Saves a network round-trip on every
  cold start.

- **AGENTS.md § 8b updated**: triage table includes the GSC + SA edge
  case (don't tell users to "just add the SA email" — it usually fails)
  and references the new `reload_credentials` tool.

### Backward compatibility
- `reauthenticate` tool still works (now an alias).
- ADC users see no behavior change unless their token is revoked
  (in which case the failure now surfaces ~100ms after MCP startup
  instead of inside the first tool call).
- No new env vars required. Existing configs work unchanged.

### Tests
92/92 pass. `test_tool_count` updated 78 → 79; `test_diagnostic_tools_have_guardrail_suffix`
adds `reload_credentials` to the meta-tool exclusion set.

---

## [0.7.2] — 2026-05-04

### Documentation & auth UX hardening (no feature changes, no breaking changes)

Triggered by a real user incident: a webmaster trying to set up the MCP on
a headless agent IA hit `invalid_grant: Token has been expired or revoked`
followed by `This app is blocked` when re-running OAuth — and was unsure
whether Service Account was a supported alternative because the docs
buried it inside a collapsed `<details>` block. Fixed three documentation
gaps and one runtime UX issue so this scenario is unambiguous next time.

### Documentation

- **README.md § Quickstart**: added an upfront decision matrix (ADC vs
  Service Account vs OAuth) so the user picks the right method *before*
  hitting an error. Service Account is now explicitly recommended for
  headless / multi-client / agent IA contexts.
- **README.md § Authentication**: removed the `<details>` collapse hiding
  Service Account. Promoted to a first-class section with full
  step-by-step setup (Cloud Console → SA → JSON → grant SA email Viewer
  on each GSC site + GA4 property → env var → restart). 80 lines of
  actionable instructions where there used to be 4.
- **README.md § Troubleshooting** (NEW): documented the 8 most common
  errors with exact root cause + fix, including `invalid_grant`,
  `This app is blocked`, `EOFError EOF when reading a line`,
  `403 PERMISSION_DENIED`, empty `list_sites` / `list_properties`,
  multi-tenant data leak symptoms, post-test-user `App is blocked`.
- **AGENTS.md § 8b Authentication failures** (NEW): triage table for the
  agent IA. Maps each error fragment to a recommended action. Strong
  default: in headless / agent / VPS contexts, recommend Service Account
  rather than improvising OAuth retries.

### Runtime UX

- **`auth.py` — proactive ADC validation**: `_from_adc()` now performs a
  refresh test on cached credentials. If the refresh token is revoked
  AND a Service Account is configured (`GOOGLE_SEO_SERVICE_ACCOUNT_FILE`),
  silently falls through to it — no more confusing 503 from inside the
  first tool call when the cascade *should* work. If no SA fallback is
  configured, raises an actionable `RuntimeError` pointing the user to
  the README troubleshooting section, not the raw `invalid_grant` from
  google-auth.
- **`auth.py` — improved "no credentials" message**: when none of the
  three methods is configured, the error now lists the 3 options with
  their exact env vars + a hint to read README § Troubleshooting if
  ADC was tried and failed with `invalid_grant` or `App is blocked`.

### Tests
92/92 pass. No new tests required — runtime change is defensive only,
existing auth tests cover the cascade order.

---

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
  application-default login`` mid-session (cliente A → cliente B →
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
