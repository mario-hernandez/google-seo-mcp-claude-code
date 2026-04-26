---
name: Bug report
about: Something doesn't work as documented
labels: bug
---

**What did you run?**
The exact tool name and arguments. Cite `_meta.source` from the response if you have it.

**What did you expect?**

**What actually happened?**
Paste the error or surprising output. Redact any URLs/queries that contain PII.

**Reproduction**
Minimum steps that trigger the bug. If it requires real GSC/GA4 data, describe the property profile (size of site, sc-domain vs URL-prefix, GA4 with/without ecommerce).

**Environment**
- OS: (macOS / Linux / Windows + version)
- Python: `python --version`
- MCP version: `pipx list | grep google-seo` or git commit SHA
- Auth method: (ADC / service account / OAuth user flow)

**Logs**
Set `GOOGLE_SEO_LOG_LEVEL=DEBUG` and paste the relevant lines (redacted).
