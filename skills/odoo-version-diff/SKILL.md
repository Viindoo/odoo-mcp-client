---
name: odoo-version-diff
description: >
  Produce a comprehensive diff of API + feature changes between two Odoo versions (v8 →
  v19+), split into a developer track (added/removed/deprecated/changed signatures with
  migration notes) and a marketer track (business-language feature highlights). Use this
  skill ANY time someone is comparing two Odoo versions — whether they want a migration
  plan, marketing talking points, or just to understand what's new. Pushy trigger: fire on
  "what changed between v16 and v17?", "new in Odoo 17", "tính năng mới Odoo 17", "API nào
  thay đổi từ v16 sang v17", "v18 release notes for developers", "what was removed in v13?",
  "Odoo 14 vs Odoo 16 for our team", "from v12 to v16 — diff", "what's the headline news in
  v18 for marketing?", "client running v15 — what would v17 give them?", "khách hỏi sự khác
  biệt giữa v16 và v17", "Odoo 19 có gì mới?", "is the v17 ORM faster?", "between which
  versions did OWL become default?", "khi nào @api.multi bị remove?". This skill serves
  BOTH developer and marketer questions — the developer section is in source-level English,
  the marketer section is in business-value language. When the user asks to audit THEIR
  code for deprecation (not just see the version-to-version delta), route to
  odoo-deprecation-audit. When they want to migrate one specific model field-by-field,
  route to odoo-coder with the field list.
---

## Persona
Developer + Marketer

## MCP tools
At session start: `set_active_version(odoo_version=…)` for the FROM version (subsequent
inspection calls inherit it; the diff tool itself takes both versions explicitly).

Primary tools:
- `api_version_diff(symbol | scope, from_version, to_version)` — the core symbol-level delta.
- `lookup_core_api(symbol)` — confirms existence + signature of a symbol in a given version.
- `entity_lookup(kind='method', model=…, method=…)` — drill into a specific method's
  signature changes.
- `model_inspect(model, method='fields')` — enumerate fields in one version for diffing
  against the same call in another version.
- `model_inspect(model, method='views')` — same, for views.

## Context

Odoo version diff has two audiences with different needs:
- **Developers**: need file paths, method signatures, migration instructions for breaking changes
- **Marketers**: need business-language feature highlights for sales/marketing content

**Major breaking points in Odoo history (v8 → v19+):**

| Version jump | Key breaking changes |
|-------------|---------------------|
| v8 → v10 | Python 2→3, `__openerp__.py` → `__manifest__.py`, `osv.osv` → `models.Model`, `_columns` → class attributes, `pool.get()` removed |
| v12 → v13 | `@api.multi`, `@api.one` removed; OWL introduced as new JS framework (alongside old `web.Widget` — NOT yet primary) |
| v13 → v14 | OWL becomes primary frontend framework; `web.Widget` deprecated (still present) |
| v14 → v15 | OWL 2.0 migration; many widget APIs changed; `AbstractModel`, `AbstractRenderer` removed |
| v15 → v16 | `web.Widget` removed completely; `fields.Text` with `widget='html'` replaced by `fields.Html`; new `HtmlField` widget; `body_html` field type changes; accounting model restructure |
| v16 → v17 | Python 3.10+ required; performance improvements; several `tools.*` cleanup |
| v17 → v18+ | ORM enhancements; module restructuring (ongoing) |

Always specify if the diff spans an **era boundary** (OpenERP → Odoo, or pre-OWL → post-OWL)
because these require significantly more migration work than within-era upgrades.

**Data priority:** `api_version_diff` results are ground truth for what actually changed between
the indexed versions. Use training knowledge for era-level historical context (Python 2→3,
`@api.multi` removal history) but never assert specific API changes without MCP confirmation.

## Instructions

**Round 1:** Call `api_version_diff` first — this is the prerequisite that supplies the symbol
list for all subsequent calls.

**Round 2 — Parallel:** After Round 1, batch ALL `lookup_core_api` calls (for every Removed /
Changed signature symbol) + ALL `entity_lookup(kind='method', …)` calls (for every
changed-signature method that is commonly overridden) simultaneously. These are independent
of each other — firing them as a single batch cuts the total round trips dramatically for
large version gaps.

**Round 2b — Structural diff (when the user names a specific model):** Call
`model_inspect(model=<name>, method='fields', odoo_version=<from_version>)` and
`model_inspect(model=<name>, method='fields', odoo_version=<to_version>)` simultaneously,
then diff the results to surface field additions and removals between the two versions. Do
the same with `model_inspect(method='views', …)` to identify view-level structural changes.
These four calls are all independent — fire them as a single batch alongside Round 2.

Categorize findings by impact:
   - **Module developer** changes (APIs used in `_inherit` classes, model definitions)
   - **End-user functionality** changes (new features visible in the UI)

**Cross-era note:** If the jump spans v8/v9→v10+ or v12→v13, add a special "Era migration" section
explaining the magnitude: Python 2→3 rewrite, decorator removal, frontend framework replacement.

## Output format

```
## Version Diff: Odoo <from> → <to>

**Era:** <Within-era / Cross-era — specify which eras>
**Migration complexity:** <Low (within-era, <2 versions) / Medium / High / Very High (cross-era)>

### Added APIs (<N> new)
| Symbol | Kind | Module | Description |
|--------|------|--------|-------------|
| ...    | field/method/class | ... | ... |

### Removed APIs (<N> breaking)
| Symbol | Last version | Replacement | Migration note |
|--------|-------------|-------------|---------------|
| ...    | ...         | ...         | ...            |

### Deprecated APIs (<N> warnings)
| Symbol | Deprecation message | Replacement |
|--------|--------------------|----|
| ...    | ...                | ...|

### Changed signatures (<N>)
| Symbol | Old signature | New signature | Impact |
|--------|--------------|---------------|--------|
| ...    | ...          | ...           | ...    |

### Era migration (if cross-era)
<Explanation of the broader migration work required beyond API changes>

### Structural diff — `<model>` (when model-specific diff requested)
**Fields added:** `<field1>`, `<field2>` …
**Fields removed:** `<field3>` …
**Views added:** `<view_id>` (<type>) …
**Views removed:** `<view_id>` …

### Feature highlights (business value — for marketers)
- **<Feature>**: <business-language description>
- **<Feature>**: <business-language description>

### Developer sprint plan
1. Fix BREAKING issues (Removed APIs): <priority order>
2. Update Changed signatures: <modules to check>
3. Migrate Deprecated (next sprint): <list>
```

## Examples

**Example 1:**
Prompt: "what changed between Odoo 16 and 17 for module developers?"
Output: Categorized diff with Added/Removed/Deprecated/Changed sections, migration notes for
each breaking change, feature highlights, developer sprint plan.

**Example 2:**
Prompt: "so sánh API Odoo 12 và 16, chúng tôi cần migrate"
Output: Cross-era diff (v12→v13: `@api.multi` removal + OWL introduced; v13→v14: OWL becomes
primary + `web.Widget` deprecated; v14→v16: OWL 2.0 + `web.Widget` removed). Era migration
section prominent. Complexity: Very High. Sprint plan in Vietnamese.
