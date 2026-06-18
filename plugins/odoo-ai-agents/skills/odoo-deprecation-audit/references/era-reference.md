# odoo-deprecation-audit - Era Reference + Output Format

## Deprecation layers

- **Deprecated** - still works, emits a warning, will be removed in N+1 or N+2
- **Removed** - throws `AttributeError` or `ImportError` in the target version
- **Changed signature** - same name, different parameters; silent breakage

## Era-specific knowledge

- **v8/v9 (OpenERP era):** `osv.osv`, `orm.TransientModel`, `_columns` dict, `fields.function`, `_constraints`, `cr.execute` without context manager, `pool.get()`. Migrating from v8/v9 requires rewriting models entirely - effort significantly higher.
- **v10-v12:** `@api.multi`, `@api.one`, `self.env.cr`, old `ir.values`. The `@api.multi`/`@api.one` decorators removed in v13. Major breaking point.
- **v13:** OWL introduced alongside old `web.Widget` - NOT yet the primary framework. Most views still use legacy widget system.
- **v14:** OWL becomes primary frontend framework. `web.Widget` deprecated (still present).
- **v15:** OWL 2.0 migration. Many JS `AbstractModel`, `AbstractRenderer` patterns removed.
- **v16:** `web.Widget` removed completely.
- **v16+:** `fields.Char(string=...)` positional arg removed; `Html` → `HtmlField`; old `_inherits` patterns deprecated. Python 3.10+ required.
- **v17+:** `float_round` deprecation, `tools.config` partial changes, OWL 2.x stable.

**Data priority:** MCP tool results are ground truth. If `find_deprecated_usage` or `api_version_diff` returns a symbol that training knowledge says is still valid, trust the MCP result - it reflects the actually indexed codebase. Supplement MCP data with training knowledge for business context and effort estimation.

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

### Legacy JS patches requiring OWL rewrite (v8-v13 → v14+ only)
| Patch target | Module | Era | Replacement pattern |
|--------------|--------|-----|---------------------|
| ...          | ...    | era1 | OWL Component / patch() |

### OpenERP era rewrites (v8/v9 only)
<List modules needing full Python 2→3 rewrite if applicable>

### Estimated migration effort
<Low/Medium/High/Very High> - <rationale: number of BREAKING issues, era complexity>

### Recommended sprint plan
1. <fix BREAKING issues in this order>
2. <fix WARN in next sprint>
```

## Examples

**Example 1:**
Prompt: "audit deprecated API usage before we upgrade from Odoo 16 to 17"
Output: Table of deprecated/removed APIs by file, urgency ratings, migration notes for v16→v17 breaking changes (e.g. `fields.Html` rename, `amount_by_group` signature), effort estimate.

**Example 2:**
Prompt: "We are running Odoo 12 and want to upgrade to v16 - what needs to be fixed?"
Output: Three-phase analysis: v12→v13 (@api.multi removal, OWL introduced), v13→v15 (OWL becomes primary in v14, OWL 2.0 in v15, web.Widget deprecated then removed), v15→v16 (Html field rename, web.Widget fully removed). Effort estimate: Very High. Includes sprint planning recommendations.
