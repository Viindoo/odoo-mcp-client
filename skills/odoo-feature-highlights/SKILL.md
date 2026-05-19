---
name: odoo-feature-highlights
description: >
  Generate marketing-friendly feature highlights for a specific Odoo or Viindoo version —
  ready for sales decks, blog posts, product announcements, release notes, or competitive
  comparisons. Output is business-language by default (with a separate technical-notes
  appendix for developers). Use this skill ANY time someone needs to talk about "what's
  new" or "what's exciting" in an Odoo/Viindoo release for an audience that isn't reading
  source code. Pushy trigger: fire on "highlight new features in Odoo 17", "what's
  exciting in this version?", "feature comparison for sales deck", "tính năng nổi bật Odoo
  17", "nêu điểm mạnh so với phiên bản trước", "what's new for customers in this release?",
  "viết nội dung marketing về tính năng Odoo", "blog post about Viindoo 17", "release
  notes in Vietnamese for our customers", "release notes for non-developers", "khách hỏi
  Odoo 17 có gì hot — tóm tắt giúp", "for the newsletter — what to feature about Odoo 18?",
  "competitive talk track — why upgrade from v15 to v17?", "headline value of v18 vs
  SAP/Microsoft for accounting", "summarize what's new for customers", "talking points for
  Friday's sales pitch". Trigger even when the user says "just summarize what's new" without
  mentioning marketing — that's still this skill. When the user asks for source-level
  developer diff (signatures, removed APIs), route to odoo-version-diff. When they want
  proof Odoo can do a SPECIFIC capability they care about, route to odoo-capability-proof.
---

## Persona
Marketer / Product Manager

## MCP tools
At session start: `set_active_version(odoo_version=<target_release_version>)` so subsequent
calls use the release version being highlighted (the diff tool itself takes both versions
explicitly).

Primary tools:
- `api_version_diff(scope, from_version, to_version)` — the symbol-level delta driving the
  highlight selection.
- `find_examples(query)` — real-world implementations to ground each highlight in actual
  shipped code rather than spec text.
- `model_inspect(model, method='all')` — headline-feature key models, surfaces field set for
  business-language description.
- `check_module_exists(module, …)` — confirms a module being highlighted is actually present
  in the target version.

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

Viindoo versions track Odoo versions (e.g. Viindoo 17 ≈ Odoo 17 CE + Viindoo add-ons). When
highlighting Viindoo features, distinguish what's from Odoo CE base vs. Viindoo add-ons.

**Data priority:** MCP `api_version_diff` results are ground truth for which APIs and modules
actually changed between versions. Use training knowledge for business-language narrative and
historical context, but never assert a feature "was added in v17" without MCP confirmation.

## Instructions

**Round 1:** Call `api_version_diff` first — this drives which features to highlight.

**Round 2 — Parallel:** After Round 1 results arrive, call `find_examples` (for top impactful
models: `sale.order`, `account.move`, `mrp.production`, `hr.leave`) +
`model_inspect(model=…, method='all')` (for headline feature key models) + `check_module_exists`
(for all modules being highlighted) all simultaneously. None of these depend on each other —
batch them in one round to cut total latency from 4 sequential calls to 2 total rounds.

**Writing rules:**
- Lead with business outcomes, not technical mechanisms
- Use concrete numbers where available: "new `amount_by_group` field enables automatic tax
  grouping across N tax brackets"
- Avoid acronyms, file paths, developer jargon in the main highlights section
- Keep a separate "Technical notes" section for developers
- For Vietnamese market: mention localization features (VAS accounting, Vietnamese tax) prominently

## Output format

```
## Feature Highlights: Odoo <version>
*<Optional: Viindoo <version> highlights if applicable>*

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
Prompt: "viết nội dung về tính năng nổi bật Viindoo 17 cho blog marketing"
Output: Headline features in Vietnamese, emphasis on Viindoo-specific add-ons (VAS accounting,
Vietnamese HR), comparison table vs v16, talking points for Vietnamese SMB audience.
