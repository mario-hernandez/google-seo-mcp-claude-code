# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- This CHANGELOG.

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
