---
name: odoo-feature-highlights
description: >
  Generate marketing-friendly feature highlights for a specific Odoo version or distribution
  - for sales decks, blog posts, announcements, or release notes. Output: business-language
  (+ technical-notes appendix). Version-aware: uses MCP api_version_diff; confirm version
  when unspecified. Use this ANY time someone needs "what's new" for an audience not reading
  source code. Trigger on: "highlight new features in version X", "write highlight copy for
  the new features", "marketing highlights for the new modules", "what's exciting in this
  release?", "feature comparison for sales deck", "release notes for non-developers".
  Trigger even when the user says "just summarize what's new" without mentioning marketing.
  Also fires on Vietnamese: "điểm nổi bật bản mới", "tính năng mới cho slide bán hàng", "có gì hay ở bản này".
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
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `find_examples` - Semantic code search returning real indexed code snippets from the Odoo codebase.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
<!-- END GENERATED TOOLS -->

## Context

Odoo ships annual major releases - each brings API changes (developer-facing) and user-facing improvements. This skill serves both audiences.

**Key version leaps:**

| Version | Highlight |
|---|---|
| v9 | First CE/EE split |
| v10 | Odoo rebranding from OpenERP; Python 3 migration start |
| v11/v12 | Community stabilization; major accounting improvements |
| v13 | OWL introduced (most views still use legacy widgets) |
| v14 | OWL becomes primary framework; `web.Widget` deprecated |
| v15 | OWL 2.0 (breaking OWL API); spreadsheet; sign matured |
| v16 | Full OWL stable; `web.Widget` removed; new field types |
| v17 | Performance; Python 3.10+; UX refinements |
| v18+ | ORM enhancements; module restructuring |

Custom distributions track Odoo versions - distinguish CE base from distribution-specific add-ons. **Data priority:** `api_version_diff` is ground truth - never assert "added in vX" without MCP confirmation.

## Instructions

**Round 1:** `api_version_diff` first - drives which features to highlight.

**Round 2 - Parallel (after Round 1):** Batch all of the following simultaneously:
- `find_examples` for top models (`sale.order`, `account.move`, `mrp.production`, `hr.leave`)
- `model_inspect(model=…, method='fields')` for headline feature models
- `check_module_exists` for all modules being highlighted
- `module_inspect(name=<module>, method='summary', odoo_version='<version>')` for those same modules

`module_inspect` summary gives concrete numbers ("adds 3 models and 12 views") instead of bare "module exists".

**Writing rules:**
- Lead with business outcomes, not technical mechanisms
- Use concrete numbers where available; avoid acronyms/jargon in main section
- Keep a separate "Technical notes" section for developers
- Vietnamese market: mention VAS accounting and Vietnamese tax features prominently

## Standalone-first fallback

When OSM is unreachable, follow `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

1. **Tier 2:** `WebFetch` `https://www.odoo.com/odoo-<version>/release-notes`; if that fails, `WebFetch` GitHub CHANGELOG (`https://github.com/odoo/odoo/blob/<version>/CHANGELOG.rst`) or releases page. Label artifact `grounded: local-source (not OSM-indexed)`.
2. **Tier 3 (both fail):** Generate from training knowledge; prepend `OSM unavailable - ungrounded`; add caveat. Never ask caller to paste release notes.

## Output format

```
## Feature Highlights: Odoo <version>
*<Optional: custom distribution <version> highlights if applicable>*

### Headline features (top 3-5)
1. **<Feature name>** - <1-2 sentence business value description>
2. **<Feature name>** - <1-2 sentence business value description>
3. **<Feature name>** - <1-2 sentence business value description>

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

**Example 1:** "feature highlights for Odoo 17 sales deck" → 3-5 headlines with business-value descriptions, comparison table vs Odoo 16, deck talking points.

**Example 2:** "highlights for custom distribution v17 marketing blog" → headlines in business language, emphasis on distribution-specific add-ons, comparison table vs prior version.

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next) - additive run-driver output, changes nothing above.

In the `next` field, include optional suggestions:
- skill: odoo-doc-illustration
  confidence: 0.5
  risk_level: L1
  reason: illustrate new features with annotated screenshots for sales deck or blog post (use when static images are needed, not a recorded video)
