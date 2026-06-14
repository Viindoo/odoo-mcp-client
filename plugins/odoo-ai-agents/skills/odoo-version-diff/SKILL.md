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
  route to odoo-coding with the field list
---

## Persona
Developer + Marketer

## Out of Scope

- Audit user's codebase for deprecated API usage → use `odoo-deprecation-audit`
- Marketing highlights (business language only) → use `odoo-feature-highlights`
- Single-feature availability lookup → use `odoo-feature-check`

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
- `set_active_version(odoo_version='17.0')` — Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `api_version_diff` — Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `entity_lookup` ★ — Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `lookup_core_api` — Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
<!-- END GENERATED TOOLS -->

## Context

Two audiences: **Developers** (file paths, method signatures, migration instructions for breaking changes) and **Marketers** (business-language feature highlights for sales/marketing content).

Historical breaking points: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-version-diff/references/breaking-points-history.md`

Use training knowledge for era-level historical context (Python 2→3, `@api.multi` removal, OWL timeline) but never assert specific API changes without MCP confirmation. `api_version_diff` results are ground truth. Always flag when the diff spans an **era boundary** — these require significantly more migration work.

## Instructions

**Round 1:** Call `api_version_diff` first — this supplies the symbol list for all subsequent calls.

**Round 2 — Parallel:** After Round 1, batch ALL calls simultaneously (they are independent — one batch cuts round trips dramatically for large version gaps):
- `lookup_core_api` for every Removed/Changed signature symbol
- `entity_lookup(kind='method', …)` for every changed-signature method that is commonly overridden
- `find_examples(query=<new API>, odoo_version=<to_version>)` for Added symbols (shows real indexed usage rather than bare description)

**Round 2b — Structural diff (when user names a specific model):** Batch simultaneously:
- `model_inspect(model=<name>, method='fields', odoo_version=<from_version>)`
- `model_inspect(model=<name>, method='fields', odoo_version=<to_version>)`
- `model_inspect(model=<name>, method='views', odoo_version=<from_version>)`
- `model_inspect(model=<name>, method='views', odoo_version=<to_version>)`

Diff the results to surface field and view-level structural changes. Fire these alongside Round 2.

Categorize findings by impact: **Module developer** changes vs **End-user functionality** changes.

**Cross-era note:** If the jump spans v8/v9→v10+ or v12→v13, add a special "Era migration" section explaining the magnitude.

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
   knowledge of era-level changes and prepend `OSM unavailable - ungrounded`; add caveat
   "not yet verified against the API index; double-check signature details when OSM is back online".
   Never ask the caller to paste or supply release notes - those are Tier-2 fetches.

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

Examples: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-version-diff/references/examples.md`

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
