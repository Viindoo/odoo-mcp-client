---
name: odoo-version-diff
description: >
  Produce a comprehensive diff of API and feature changes between two Odoo versions (v8 through
  v19+). Use this skill for: what changed between Odoo 16 and 17, new API in version 17, breaking
  changes in upgrade, API nào thay đổi từ v16 sang v17, tính năng mới Odoo 17, what's different
  in this version, migration guide between versions, what was removed in v13, what's new for
  developers in v16. Trigger for developer questions about version differences and for marketer
  questions about "what's new" — this skill serves both audiences with separate sections.
---

## Persona
Developer + Marketer

## MCP tools
`api_version_diff`, `lookup_core_api`, `resolve_method`

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
Changed signature symbol) + ALL `resolve_method` calls (for every changed-signature method that
is commonly overridden) simultaneously. These are independent of each other — firing them as a
single batch cuts the total round trips dramatically for large version gaps.

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
