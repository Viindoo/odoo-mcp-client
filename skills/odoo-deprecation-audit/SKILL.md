---
name: odoo-deprecation-audit
description: >
  Systematic audit of deprecated Odoo API usage in a codebase to prepare for version upgrade.
  Use this skill whenever someone needs to find deprecated code before upgrading Odoo, audit API
  usage for a migration, check upgrade readiness, kiểm tra deprecated API, chuẩn bị upgrade Odoo,
  tìm code cũ trước khi nâng cấp, migration readiness check. Trigger even for informal questions
  like "is our code ready for v17" or "what will break when we upgrade".
---

## Persona
Developer / Tech Lead

## MCP tools
`find_deprecated_usage`, `api_version_diff`, `lookup_core_api`, `resolve_method`, `list_js_patches`

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

**Data priority:** MCP tool results are ground truth. If `find_deprecated_usage` or `api_version_diff`
returns a symbol that training knowledge says is still valid, trust the MCP result — it reflects
the actually indexed codebase. Supplement MCP data with training knowledge for business context
and effort estimation.

## Instructions

Use parallel MCP calls to minimize round trips — the full audit can complete in 3 rounds.

**Round 1 — Parallel:** Call `find_deprecated_usage` + `api_version_diff` simultaneously.
These are completely independent: one scans the codebase, the other fetches the version spec.
No dependency between them.

**Round 2 — Parallel:** Merge the symbol lists from Round 1. Call `lookup_core_api` for ALL
deprecated/removed symbols in one batch. Every call is independent — fire them all together.

**Round 3 — Parallel:** Call `resolve_method` for ALL changed-signature methods simultaneously.
These calls are independent of each other and of Round 2 lookups.

**Round 3b — JS patch audit (when migrating from v8–v13):** Call
`list_js_patches(odoo_version=<source_version>, era='era1')` to enumerate all legacy
`web.Widget`-based patches in scope. Era1 covers v8–v13; these patches require manual OWL
rewrites because the Widget API was removed in v16. Flag each patch as BREAKING if the target
version is v14+ and the patch still references `AbstractField`, `FieldWidget`, or
`web.Widget`. This call is independent of Rounds 1–3 — fire it in parallel with Round 3 if
both apply.

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
Prompt: "chúng tôi đang dùng Odoo 12, muốn nâng lên 16 — cần sửa những gì"
Output: Phân tích ba giai đoạn: v12→v13 (@api.multi removal, OWL introduced), v13→v15 (OWL
becomes primary in v14, OWL 2.0 in v15, web.Widget deprecated then removed), và v15→v16 (Html
field, web.Widget fully removed), ước tính effort tổng thể là Very High, sprint plan chi tiết.
