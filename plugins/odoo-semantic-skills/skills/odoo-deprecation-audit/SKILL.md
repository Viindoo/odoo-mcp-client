---
name: odoo-deprecation-audit
description: >
  Systematic audit of deprecated Odoo API usage in a codebase before a version upgrade —
  finds `@api.multi`, `osv.osv`, `_columns`, `web.Widget`, `fields.Html` and other
  era-specific APIs that break or warn in the target version, grouped by file with the exact
  replacement and urgency (BREAKING / WARN / STYLE). Resolve the target version from context;
  if unstated, confirm it. Pushy trigger: "upgrade", "migration", "is our code ready for vN",
  "what will break when we move from X to Y", "audit before upgrade", deprecated-symbol
  mentions ("we still have @api.multi everywhere", "ir.values is still used", "OWL migration
  needed"). Also fires on Vietnamese: "rà API lỗi thời trước khi nâng cấp", "code chạy được
  trên vN không", "cái gì sẽ vỡ khi nâng cấp". Trigger even without the word "deprecation". When the user asks ONLY what changed
  between two versions (without auditing their code), route to odoo-version-diff instead. When
  they want to write fresh upgrade-safe code in the target version, route to odoo-coder
---

## Persona
Developer / Tech Lead

## Out of Scope

- Version API diff without code scan → use `odoo-version-diff`
- Fresh code generation in target version → use `odoo-coder`
- Executive risk dashboard → use `odoo-risk-overview`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.11.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (24h TTL per API key); subsequent calls pass odoo_version='auto' to reuse it instead of repeating the version (it can no longer be omitted).

**Primary tools:**
- `api_version_diff` — Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `entity_lookup` ★ — Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `find_deprecated_usage` — Scan the indexed codebase for usages of deprecated API patterns.
- `lookup_core_api` — Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
<!-- END GENERATED TOOLS -->

## Context

Odoo deprecation happens in layers:
- **Deprecated** — still works, emits a warning, will be removed in N+1 or N+2
- **Removed** — will throw `AttributeError` or `ImportError` in the target version
- **Changed signature** — same name, different parameters; silent breakage

**Era-specific knowledge:**
- **v8/v9 (OpenERP era)**: `osv.osv`, `orm.TransientModel`, `_columns` dict, `fields.function`,
  `_constraints`, `cr.execute` without context manager, `pool.get()`. Migrating from v8/v9
  requires rewriting models entirely — effort is significantly higher.
- **v10–v12**: `@api.multi`, `@api.one`, `self.env.cr`, old `ir.values`. The `@api.multi`/
  `@api.one` decorators were removed in v13. This is a major breaking point.
- **v13**: OWL introduced as new JS framework alongside old `web.Widget` — NOT yet the primary
  framework. Most views still use the legacy widget system in v13.
- **v14**: OWL becomes the primary frontend framework. `web.Widget` deprecated (still present).
- **v15**: OWL 2.0 migration. Many JS `AbstractModel`, `AbstractRenderer` patterns removed.
- **v16**: `web.Widget` removed completely.
- **v16+**: `fields.Char(string=...)` positional arg removed; `Html` → `HtmlField`; old
  `_inherits` patterns deprecated. Python 3.10+ required.
- **v17+**: `float_round` deprecation, `tools.config` partial changes, OWL 2.x stable.

**Data priority:** MCP tool results are ground truth. If `find_deprecated_usage` or
`api_version_diff` returns a symbol that training knowledge says is still valid, trust the
MCP result — it reflects the actually indexed codebase. Supplement MCP data with training
knowledge for business context and effort estimation.

## Instructions

Use parallel MCP calls to minimize round trips — the full audit can complete in 3 rounds.

**Round 0 — Pin the source version:** `set_active_version(odoo_version=<source_version>)`.

**Round 1 — Parallel:** Call `find_deprecated_usage` + `api_version_diff` simultaneously.
These are completely independent: one scans the codebase, the other fetches the version spec.
No dependency between them.

**Round 2 — Parallel:** Merge the symbol lists from Round 1. Call `lookup_core_api` for ALL
deprecated/removed symbols in one batch. Every call is independent — fire them all together.

**Round 3 — Parallel:** Call `entity_lookup(kind='method', …)` for ALL changed-signature
methods simultaneously. These calls are independent of each other and of Round 2 lookups.

**Round 3b — JS patch audit (when migrating from v8–v13):** Call
`module_inspect(name=<scope>, method='js', odoo_version='auto')` to enumerate all legacy `web.Widget`-based
patches in scope. Era1 (v8–v13) patches require manual OWL rewrites because the Widget API
was removed in v16. Flag each patch as BREAKING if the target version is v14+ and the patch
still references `AbstractField`, `FieldWidget`, or `web.Widget`. This call is independent of
Rounds 1–3 — fire it in parallel with Round 3 if both apply.

Capture file, line, symbol name, and deprecation message from Round 1 results; merge with
Round 2 replacement info before building the output table.

**Prioritization:**
- BREAKING (target version removes symbol) → must fix before upgrade
- WARN (deprecated in target, removed in next) → fix in same sprint
- STYLE (old patterns that still work) → fix in follow-up

Group findings by file so developers can batch-fix one file at a time. Include the exact
replacement API with a one-line migration note.

**Era upgrade note:** If migrating from v8/v9, add a separate section "OpenERP Era Rewrites"
listing modules that require full Python 2 → 3 syntax migration, not just API replacements.

## Standalone-first fallback

When OSM is unreachable, ask the user to provide the module list to audit plus source code (or grep output of suspected deprecated patterns). The skill will still create an audit report using static text analysis — searching for patterns like `@api.multi`, `_columns`, `osv.osv`, `web.Widget` via regex — and suggest replacements from Odoo knowledge, with a caveat: "Classification not yet verified against the codebase index; confirm findings once OSM is online."

## Output format

```
## Deprecation Audit Report

**Source version:** <from>
**Target version:** <to>
**Era:** <OpenERP v8-9 / Legacy v10-12 / Modern v13+>
**Files scanned:** <N>
**Issues found:** <N total> (<N> BREAKING / <N> WARN / <N> STYLE)

| File | Line | Deprecated symbol | Replacement | Urgency |
|------|------|-------------------|-------------|---------|
| ...  | ...  | ...               | ...         | BREAKING/WARN/STYLE |

### Migration notes
- <key migration pattern 1>
- <key migration pattern 2>

### Legacy JS patches requiring OWL rewrite (v8–v13 → v14+ only)
| Patch target | Module | Era | Replacement pattern |
|--------------|--------|-----|---------------------|
| ...          | ...    | era1 | OWL Component / patch() |

### OpenERP era rewrites (v8/v9 only)
<List modules needing full Python 2→3 rewrite if applicable>

### Estimated migration effort
<Low/Medium/High/Very High> — <rationale: number of BREAKING issues, era complexity>

### Recommended sprint plan
1. <fix BREAKING issues in this order>
2. <fix WARN in next sprint>
```

## Examples

**Example 1:**
Prompt: "audit deprecated API usage before we upgrade from Odoo 16 to 17"
Output: Table of deprecated/removed APIs by file, urgency ratings, migration notes for v16→v17
breaking changes (e.g. `fields.Html` rename, `amount_by_group` signature), effort estimate.

**Example 2:**
Prompt: "We are running Odoo 12 and want to upgrade to v16 — what needs to be fixed?"
Output: Three-phase analysis: v12→v13 (@api.multi removal, OWL introduced), v13→v15 (OWL
becomes primary in v14, OWL 2.0 in v15, web.Widget deprecated then removed), v15→v16 (Html
field rename, web.Widget fully removed). Effort estimate: Very High. Includes sprint planning
recommendations.
