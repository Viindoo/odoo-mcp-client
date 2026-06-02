---
name: odoo-feature-highlights
description: >
  Generate marketing-friendly feature highlights for a specific Odoo version or distribution
  — for sales decks, blog posts, announcements, or release notes. Output: business-language
  (+ technical-notes appendix). Version-aware: uses MCP api_version_diff; confirm version
  when unspecified. Use this ANY time someone needs "what's new" for an audience not reading
  source code. Trigger on: "highlight new features in version X", "write highlight copy for
  the new features", "marketing highlights for the new modules", "what's exciting in this
  release?", "feature comparison for sales deck", "release notes for non-developers".
  Trigger even when the user says "just summarize what's new" without mentioning marketing.
  When the user asks for source-level developer diff (signatures, removed APIs), route to
  odoo-version-diff. When they want proof a platform can do a SPECIFIC capability, route to
  odoo-capability-proof
---

## Persona
Marketer / Product Manager

## Out of Scope

- Source-level API diff for developers → use `odoo-version-diff`
- Proof of a specific capability requirement → use `odoo-capability-proof`
- Single feature availability lookup → use `odoo-feature-check`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.11.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (24h TTL per API key) so subsequent calls can omit odoo_version.

**Primary tools:**
- `api_version_diff` — Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, or a summary in one call.
<!-- END GENERATED TOOLS -->

## Context

Odoo major releases ship annually. Each version brings API changes (developer-facing) and
user-facing improvements (business-facing). Marketers need business language; developers need
technical details. This skill serves both.

**Key version leaps worth highlighting:**
- v9: First CE/EE split — major positioning story
- v10: Odoo rebranding from OpenERP, full Python 3 migration start
- v11/v12: Community stabilization, major accounting improvements
- v13: OWL introduced as new JS framework — lays groundwork for future UX improvements, but
  most views still use legacy widget system in this version
- v14: OWL becomes primary frontend framework — dramatic UX improvement, relevant for "modern
  UI" messaging; `web.Widget` deprecated
- v15: OWL 2.0 (breaking changes in OWL API), spreadsheet integration, sign module matured
- v16: Full OWL stable, `web.Widget` removed completely, accounting localization improvements,
  new field types
- v17: Performance improvements, Python 3.10+, many UX refinements
- v18+: ORM enhancements, ongoing module restructuring

Custom distributions track Odoo versions. When highlighting distribution-specific features,
distinguish what's from Odoo CE base vs. custom or distribution-specific add-ons.

**Data priority:** MCP `api_version_diff` results are ground truth for which APIs and modules
actually changed between versions. Use training knowledge for business-language narrative and
historical context, but never assert a feature "was added in v17" without MCP confirmation.

## Instructions

**Round 1:** Call `api_version_diff` first — this drives which features to highlight.

**Round 2 — Parallel:** After Round 1 results arrive, call `find_examples` (for top impactful
models: `sale.order`, `account.move`, `mrp.production`, `hr.leave`) +
`model_inspect(model=…, method='fields')` (for headline feature key models) + `check_module_exists`
(for all modules being highlighted) all simultaneously. None of these depend on each other —
batch them in one round to cut total latency from 4 sequential calls to 2 total rounds.

**Writing rules:**
- Lead with business outcomes, not technical mechanisms
- Use concrete numbers where available: "new `amount_by_group` field enables automatic tax
  grouping across N tax brackets"
- Avoid acronyms, file paths, developer jargon in the main highlights section
- Keep a separate "Technical notes" section for developers
- For Vietnamese market: mention localization features (VAS accounting, Vietnamese tax) prominently

## Standalone-first fallback

When OSM is unreachable, the skill asks the user to provide official Odoo release notes or changelog. The skill still produces marketing highlights based on changelog text parsing + training knowledge, with business-language narrative — with caveat "not yet verified against the code index; check details when OSM is back online".

## Output format

```
## Feature Highlights: Odoo <version>
*<Optional: custom distribution <version> highlights if applicable>*

### Headline features (top 3–5)
1. **<Feature name>** — <1–2 sentence business value description>
2. **<Feature name>** — <1–2 sentence business value description>
3. **<Feature name>** — <1–2 sentence business value description>

### Feature comparison: <prev version> vs <version>
| Capability | <prev> | <version> | Business impact |
|------------|--------|-----------|-----------------|
| ...        | ...    | ...       | ...             |

### Vietnamese market highlights (if applicable)
- <localization or regulatory feature relevant to Vietnam>

### Technical notes (for developers)
- <API change 1>
- <API change 2>

### Use in sales deck
**Slide title:** <suggested title>
**Talking points:**
- <point 1>
- <point 2>
- <point 3>
```

## Examples

**Example 1:**
Prompt: "create feature highlights for Odoo 17 for our sales deck"
Output: 3–5 headline features with business-value descriptions, comparison table vs Odoo 16,
suggested talking points for a sales deck slide.

**Example 2:**
Prompt: "write feature highlights for your custom distribution version 17 for marketing blog"
Output: Headline features in business language, emphasis on custom or distribution-specific
add-ons, comparison table vs prior version, talking points for target audience.
