---
name: odoo-version-diff
description: >
  Version-aware diff of API + feature changes between two Odoo versions, split into a
  developer track (added/removed/deprecated/changed signatures + migration notes) and a
  marketer track (business-language highlights). Serves BOTH developer and marketer
  questions. Resolve the target version from context; if unstated, confirm it. Use ANY time
  someone compares two Odoo versions: "what changed between these versions", "what's new in
  Odoo N", "what was removed", era-boundary probes ("when did OWL become default").
  Also fires on Vietnamese: "khác nhau giữa hai phiên bản", "có gì mới ở Odoo N", "cái gì bị
  bỏ đi", "khi nào OWL thành mặc định". When the
  user asks to audit THEIR code for deprecation (not just see the version-to-version delta),
  route to odoo-deprecation-audit. When they want marketing-only highlights, route to
  odoo-feature-highlights. When they want to migrate one specific model field-by-field,
  route to odoo-coder with the field list
---

## Persona
Developer + Marketer

## Out of Scope

- Audit user's codebase for deprecated API usage → use `odoo-deprecation-audit`
- Marketing highlights (business language only) → use `odoo-feature-highlights`
- Single-feature availability lookup → use `odoo-feature-check`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.13.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (per live MCP session, 24h idle TTL; resets on server restart); pass a CONCRETE version here (sentinels like 'auto' are rejected), then subsequent OTHER tool calls pass odoo_version='auto' to reuse the pin instead of repeating the version (it can no longer be omitted).

**Primary tools:**
- `api_version_diff` — Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `entity_lookup` ★ — Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `lookup_core_api` — Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
<!-- END GENERATED TOOLS -->

## Context

Odoo version diff has two audiences with different needs:
- **Developers**: need file paths, method signatures, migration instructions for breaking changes
- **Marketers**: need business-language feature highlights for sales/marketing content

**Major breaking points in Odoo history (v8 onward):**

| Version jump | Key breaking changes |
|-------------|---------------------|
| v8 → v10 | Python 2→3, `__openerp__.py` → `__manifest__.py`, `osv.osv` → `models.Model`, `_columns` → class attributes, `pool.get()` removed |
| v12 → v13 | `@api.multi`, `@api.one` removed; OWL introduced as new JS framework (alongside old `web.Widget` — NOT yet primary) |
| v13 → v14 | OWL becomes primary frontend framework; `web.Widget` deprecated (still present) |
| v14 → v15 | OWL 2.0 migration; many widget APIs changed; `AbstractModel`, `AbstractRenderer` removed |
| v15 → v16 | `web.Widget` removed completely; `fields.Text` with `widget='html'` replaced by `fields.Html`; new `HtmlField` widget; `body_html` field type changes; accounting model restructure |
| v16 → v17 | Python 3.10+ required; performance improvements; several `tools.*` cleanup |
| v17 → v18+ | ORM enhancements; module restructuring (ongoing) |

> Not exhaustive. Odoo ships a new major roughly yearly; this table captures the historical
> breaking points only. For any target newer than the last row, resolve the real diff via OSM
> (`api_version_diff`) and the release notes rather than assuming.

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
large version gaps. For the **Added** symbols `api_version_diff` reports, also batch
`find_examples(query=<new API>, odoo_version=<to_version>)` so the "Added APIs" section shows real
indexed usage of each new symbol rather than a bare description generated from memory.

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

## Standalone-first fallback

When OSM is unreachable, follow the three-tier grounding order from
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

1. **Tier 2 - self-serve first:**
   - `WebFetch` the GitHub release/tag page or CHANGELOG for each version, e.g.
     `https://github.com/odoo/odoo/releases/tag/<version>` or
     `https://github.com/odoo/odoo/blob/<version>/CHANGELOG.rst`.
   - `WebFetch` official release notes at
     `https://www.odoo.com/odoo-<version>/release-notes` for business-language content.
   - Use local `Read`/`Grep` on a local source tree when present.
   - Label artifacts `grounded: local-source (not OSM-indexed)`.
2. **Tier 3 - only if both version fetches fail:** produce the diff from training
   knowledge of era-level changes (Python 2→3, `@api.multi` removal, OWL adoption
   timeline) and prepend `OSM unavailable - ungrounded`; add caveat "not yet verified
   against the API index; double-check signature details when OSM is back online". Never
   ask the caller to paste or supply release notes - those are Tier-2 fetches.

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
Prompt: "compare API changes between Odoo 12 and 16, we need to migrate"
Output: Cross-era diff (v12→v13: `@api.multi` removal + OWL introduced; v13→v14: OWL becomes
primary + `web.Widget` deprecated; v14→v16: OWL 2.0 + `web.Widget` removed). Era migration
section prominent. Complexity: Very High. Sprint plan with phased migration approach.
