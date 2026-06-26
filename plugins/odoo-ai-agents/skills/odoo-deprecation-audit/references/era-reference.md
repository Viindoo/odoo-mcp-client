# odoo-deprecation-audit - Era Reference + Output Format

> **Scan at TARGET, not source.** This file seeds well-known pivots; it is NOT exhaustive.
> Always verify each symbol at the TARGET version via OSM `api_version_diff` /
> `find_deprecated_usage` before concluding BREAKING/WARN/STYLE. If OSM returns a result that
> contradicts training knowledge, trust OSM. Ground truth = OSM result > this table > memory.
>
> **OSM caveat:** underscore-renamed methods (`_has_cycle`, `_filtered_access`) and
> `res.users.has_group`/`has_groups` are NOT resolved by OSM (server bugs #2/#3). For those
> symbols, this file (and `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md`) is the
> authoritative fallback. Do not report OSM-NOT-FOUND for those as "absent at target" - consult
> the pivot table instead.

---

## Deprecation layers

- **Deprecated** - still works, emits a DeprecationWarning, will be removed in N+1 or N+2
- **Removed** - raises `AttributeError`, `ImportError`, or `ValidationError` at the target version
- **Changed signature** - same name, different parameters or semantics; can be silent breakage

---

## Era quick-ref (version-range)

> **Rows below cover v8-v18 only.** For v19+ pivots, consult
> `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` directly (SSOT).

Full canonical table with version ranges: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md`.
The rows below are the high-frequency BREAKING pivots organized by era. Cross-check each against
the pivot table before citing a version.

### v8-v9 (OpenERP era) - full model rewrite required

| Symbol / pattern | Status | Replacement |
|---|---|---|
| `osv.osv`, `orm.TransientModel` | **REMOVED v13** | `models.Model`, `models.TransientModel` |
| `_columns = {}` dict | **REMOVED v13** | Field declarations as class attributes |
| `fields.function(...)` | **REMOVED v13** | `fields.Float(compute=...)` etc. |
| `_constraints = [...]` | **REMOVED v13** | `@api.constrains` |
| `pool.get('model.name')` | **REMOVED v13** | `self.env['model.name']` |
| `cr.execute` without context manager | WARN | Use `with self.env.cr.savepoint():` idiom |

Migrating FROM v8/v9: expect full Python 2→3 rewrite + full model API rewrite. Effort: **Very High**.

### v10-v12 (legacy API era)

| Symbol / pattern | Status | Replacement |
|---|---|---|
| `@api.multi` | **REMOVED v13** | Plain multi-record method (no decorator) |
| `@api.one` | **REMOVED v13** | `@api.model_create_multi` or plain loop |
| `old ir.values` | **REMOVED v12** | `ir.default` + `ir.config_parameter` |
| `name_get()` override | Deprecated v17, **REMOVED v18** | `_compute_display_name` (from v12) |

### v13-v15 (OWL transition era)

| Symbol / pattern | Status | Replacement |
|---|---|---|
| `web.Widget` (JS) | Deprecated v14, **REMOVED v16** | OWL `Component` + `registry.category(...)` |
| `AbstractField` (JS) | **REMOVED v16** | `registry.category('fields').get(...)` override |
| `web.field_registry` | **REMOVED v16** | `registry.category('fields')` |
| `odoo.define(name, fn)` (AMD) | Shim-only from v17 | `/** @odoo-module **/` + ES modules |
| Manifest `qweb` key | Deprecated v15 | `assets` key (from v15) |

### v16-v17 (ORM cache + view pivot era)

| Symbol / pattern | Status | Replacement |
|---|---|---|
| `self.flush()` | **REMOVED v17** | `Model.flush_model()` / `records.flush_recordset()` (from v16) |
| `self.invalidate_cache()` | **REMOVED v17** | `Model.invalidate_model()` / `records.invalidate_recordset()` (from v16) |
| `record.get_xml_id()` | **REMOVED v17** | `record.get_external_id()` (from v16) |
| `fields_view_get()` | **REMOVED v17** | `env['ir.ui.view'].get_views(...)` (from v16) |
| `fields_get_keys()` | **REMOVED v17** | direct `_fields` dict access |
| `registry.clear_caches()` | alias (v17+) | `registry.clear_cache()` (from v17) |
| `attrs=` / `states=` in views | **ValidationError from v17** | inline Python modifier `invisible="record.x == 'y'"` |
| QUnit JS tests | **REMOVED v18** | `@odoo/hoot` (from v18) |

### v18+ (unified API era)

| Symbol / pattern | Status | Replacement |
|---|---|---|
| `check_access_rights(mode)` | alias (DeprecationWarning v18+) | `check_access(mode)` (from v18) |
| `check_access_rule(mode)` | alias (DeprecationWarning v18+) | `check_access(mode)` (from v18) |
| `has_access(mode)` | new shorthand (v18) | -- |
| `_filter_access_rules()` | alias | `_filtered_access(mode)` (from v18) |
| `user_has_groups(xmlid)` | **REMOVED v18** | `user.has_groups('mod.xmlid')` (from v18) |
| `user.has_group(xmlid)` | kept (from v8) | -- |
| `_check_recursion(field)` | alias | `_has_cycle(field)` (from v18) |
| `name_get()` | **REMOVED v18** | `_compute_display_name` (from v12) |
| `<tree>` view arch tag | still accepted; `<list>` is canonical from v18 | `<list>` |
| `<div class="oe_chatter">` | deprecated | `<chatter/>` (from v18) |
| Always-invisible field without XML comment | fails `TestInvisibleField` from v18 | add `<!-- invisible: reason -->` after field |
| `/** @odoo-module **/` header | optional from v18 (auto-detected) | omit or use `/** @odoo-module ignore **/` to opt out |

---

## Output format

```
## Deprecation Audit Report

**Source version:** <from>
**Target version:** <to>
**Era:** <OpenERP v8-9 / Legacy v10-12 / Transition v13-15 / ORM-pivot v16-17 / Unified v18+>
**Files scanned:** <N>
**Issues found:** <N total> (<N> BREAKING / <N> WARN / <N> STYLE)

| File | Line | Deprecated symbol | Replacement | Urgency |
|------|------|-------------------|-------------|---------|
| ...  | ...  | ...               | ...         | BREAKING/WARN/STYLE |

### Migration notes
- <key migration pattern 1>
- <key migration pattern 2>

### Legacy JS patches requiring OWL rewrite (v8-v13 source → v14+ target only)
| Patch target | Module | Era | Replacement pattern |
|--------------|--------|-----|---------------------|
| ...          | ...    | era | OWL Component / patch() |

### OpenERP era rewrites (v8/v9 source only)
<List modules needing full Python 2→3 + model API rewrite>

### Estimated migration effort
<Low/Medium/High/Very High> - <rationale: BREAKING count, era complexity, OWL rewrite scope>

### Recommended sprint plan
1. <fix BREAKING issues in this order>
2. <fix WARN in next sprint>
```

---

## Examples

**Example 1:**
Prompt: "audit deprecated API usage before we upgrade from Odoo 16 to 17"
Output: Table of deprecated/removed APIs by file (flush/invalidate/fields_view_get removals,
attrs= ValidationError), urgency ratings, migration notes for v16→v17 breaking changes,
effort estimate.

**Example 2:**
Prompt: "We are running Odoo 12 and want to upgrade to v18 - what needs to be fixed?"
Output: Multi-era analysis: v12→v13 (@api.multi removal), v13→v15 (OWL transition, web.Widget
deprecated), v16 (flush/invalidate split, web.Widget removed), v17 (attrs= ValidationError,
flush/invalidate removed), v18 (unified ACL, name_get removed, chatter tag). Effort estimate:
Very High. Includes sprint planning recommendations and JavaScript OWL rewrite scope.
