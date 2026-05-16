---
name: odoo-coder
description: >
  Write complete, production-ready Python/XML Odoo backend code. Use this skill any time a
  developer wants to generate or extend Odoo backend features — even if they describe the
  business requirement without using technical terms. Trigger for: tạo computed field, viết
  onchange, thêm SQL constraint, tạo model mới, viết form view, viết unit test, tạo security
  rule, viết migration script, implement create/write override, thêm field vào model, write a
  computed field for, create a new model, add a method to, implement business logic in Odoo,
  viết code Odoo, làm thế nào để thêm trường, tôi muốn tạo model mới, how to create an Odoo
  model, write ORM query, create XML view for model. Also trigger when someone describes an
  Odoo business rule they want to enforce, a calculation they want to automate, or a UI change
  they want to make on an Odoo form — these are always backend code tasks even without explicit
  technical vocabulary.
---

## Persona
Developer

## MCP tools (odoo-semantic)
`resolve_model`, `list_fields`, `resolve_field`, `suggest_pattern`, `find_examples`, `lint_check`, `lookup_core_api`

## Additional tools (ollama-delegate)
`mcp__ollama-delegate__generate_code`, `mcp__ollama-delegate__complete_code`, `mcp__ollama-delegate__review_code`

## Context

Writing Odoo code correctly from the start prevents costly refactors. The main failure modes are:

- **Wrong field types or paths** — always call `resolve_field` before adding a Related or
  inherited field; the source field type determines what yours must be.
- **Stale compute cache** — `@api.depends` must list every field path accessed inside the
  compute method, including transitive paths (e.g. `order_line.product_id.categ_id`).
- **Multi-company isolation** — SQL constraints and Python `@api.constrains` must scope to
  `company_id` where applicable, otherwise cross-company duplicates bypass the guard.
- **Era-specific API** — Odoo's ORM API changed across major versions:
  - v8/v9: `_columns = {…}` dict, `_constraints = […]` list, `def write(self, cr, uid, ids, vals, context=None)`
  - v10–v12: class attributes + `@api.multi` + `self` is recordset but `@api.multi` required
  - v13+: recordset-aware by default, `super()` without arguments, `@api.multi` removed
- **Silent XML failures** — XML views reference `ir.model.fields` by technical name; a wrong
  `string` attribute on a `<field>` tag loads silently but shows the wrong label or breaks
  optional columns.

### Boilerplate vs logic split

Delegate **boilerplate** to `mcp__ollama-delegate__generate_code` — it is fast and cheap for:
computed field skeletons, form/tree/kanban view shells, unit test `setUp`, security CSV rows,
migration script stubs, `default_get` / `_get_default_*` patterns.

Write **non-trivial logic directly** with Claude when: the logic crosses multiple models, the
constraint reasoning requires understanding of existing fields, or the override must call
`super()` in a specific position relative to side-effects.

## Instructions

Work in four rounds. Always fire parallel MCP calls within a round — they are independent.

### Round 1 — Gather context (parallel)

Call all three simultaneously:
1. `resolve_model(model_name, odoo_version)` — get field list, method list, inheritance chain,
   and `Defined in` module so you know the authoritative source.
2. `list_fields(model=model_name, odoo_version=odoo_version)` — enumerate all fields currently
   on the model to catch name conflicts before writing a new field. Compare against the new
   field name the user wants to add; if a match exists, use `resolve_field` in Round 2 to
   check type compatibility instead of declaring a duplicate.
3. `suggest_pattern(feature_description)` — get the canonical Odoo pattern for the feature
   type (computed field, SQL constraint, wizard, etc.).

If you do not yet know the target model name, ask the user before proceeding.

### Round 2 — Resolve specifics (parallel when both apply)

- **Extending an existing field** → call `resolve_field(field_name, model_name, odoo_version)`
  to confirm type, whether it is stored/computed, and which module declares it.
- **Overriding an existing method** → call `lint_check(method_name, odoo_version)` to detect
  deprecated signatures (e.g. `@api.multi`, old-style `cr, uid` arguments).

Both calls are independent — fire in parallel if the task requires both.

### Round 3 — Generate code

Choose based on complexity:

**Boilerplate path** — call:
```
mcp__ollama-delegate__generate_code(
    task="<precise feature description including field names and types from Rounds 1-2>",
    context="<model class header + relevant fields from resolve_model output>"
)
```

**FIM path** — when you can write the code before and after the gap, use:
```
mcp__ollama-delegate__complete_code(
    prefix="<exact Python/XML before the gap>",
    suffix="<exact Python/XML after the gap>"
)
```
This is more precise than `generate_code` when you already know the surrounding structure.

**Direct Claude path** — write the code yourself when:
- Cross-model logic (e.g. compute that reads from a related model's method)
- Constraint must reason about multi-company or multi-currency scenarios
- `super()` call position relative to field assignment matters for correctness

### Round 4 — Inline review

Before presenting anything to the user, call:
```
mcp__ollama-delegate__review_code(
    code="<full generated code block>",
    focus="odoo conventions, logic bugs, missing super() calls, missing @api.depends paths"
)
```

Apply any HIGH or MEDIUM severity findings from the review before presenting. Mention LOW
severity findings as notes to the user ("the reviewer flagged X — worth keeping in mind").

### Era detection

Infer the Odoo version from context (user stated version, profile, or repo name). Apply:

| Version | Field declaration | Constraint style | Method signature |
|---------|------------------|-----------------|-----------------|
| v8–v9 | `_columns = {'field': fields.char(…)}` | `_constraints = [(fn, msg, fields)]` | `def write(self, cr, uid, ids, vals, context=None)` |
| v10–v12 | Class attribute + `fields.Char(…)` | `@api.constrains` | `@api.multi` required |
| v13+ | Class attribute + `fields.Char(…)` | `@api.constrains` | Recordset-aware, `super()` no args |

When version is ambiguous, default to v17 (current Viindoo primary) and note the assumption.

### Module structure

Always tell the user where to place each file and what to add to `__manifest__.py`. Do not
leave them guessing about the import chain (`__init__.py` at module and subdirectory level).

## Output format

```
## Implementation: <feature name>

### File: `<module>/<path>/<file>.py`
```python
<complete Python code>
```

### File: `<module>/views/<model>_views.xml` (if view needed)
```xml
<complete XML>
```

### File: `<module>/security/ir.model.access.csv` (if new model)
```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
```

### `__manifest__.py` additions
```python
# In 'depends' list (if new dependency):
'<module_name>',
# In 'data' list:
'views/<model>_views.xml',
'security/ir.model.access.csv',
```

### Self-review checklist
- [ ] @api.depends covers all fields accessed in _compute_* (including transitive paths)
- [ ] super() called where applicable and positioned correctly relative to side-effects
- [ ] No deprecated API for target Odoo version
- [ ] Field strings use _('…') for translatability
- [ ] SQL constraint message is user-readable and translated
- [ ] Multi-company scope applied where business logic requires it
```

## Examples

**Example 1 — computed field:**
Prompt: "tạo computed field `amount_vat` tính VAT 10% từ `amount_subtotal` trên `purchase.order`"

- Round 1 (parallel): `resolve_model('purchase.order', '17.0')` → confirm `amount_subtotal` exists and is Float; `suggest_pattern('computed field monetary')` → get `@api.depends` + `currency_field` pattern.
- Round 2: `resolve_field('amount_subtotal', 'purchase.order', '17.0')` → type=Monetary, currency via `currency_id`.
- Round 3: `generate_code(task="Computed Monetary field amount_vat = amount_subtotal * 0.1 on purchase.order", context="class PurchaseOrder(models.Model): _inherit = 'purchase.order'\n  amount_subtotal: Monetary, currency_id: Many2one")`
- Round 4: `review_code(…)` → confirm `@api.depends('amount_subtotal')` present, `currency_field='currency_id'` set.
- Output: full Python class + XPath to add `amount_vat` after `amount_subtotal` in purchase form view.

**Example 2 — SQL constraint:**
Prompt: "add SQL constraint to prevent duplicate partner name within same company"

- Round 1 (parallel): `resolve_model('res.partner', '17.0')` → confirm `company_id` field; `suggest_pattern('sql constraint unique multi-company')` → get pattern.
- Round 3: `generate_code(task="SQL constraint unique (name, company_id) on res.partner", context="…")`
- Output: `_sql_constraints` list with `UNIQUE(name, company_id)` + translated error message.

**Example 3 — create override:**
Prompt: "override `create` on `sale.order` to auto-assign a sequence ref from `ir.sequence`"

- Round 1 (parallel): `resolve_model('sale.order', '17.0')` + `suggest_pattern('create override sequence')`.
- Round 2: `lint_check('create', '17.0')` → confirm no deprecated signature.
- Round 3: Direct Claude (cross-model + `super()` position matters — must call `super().create(vals)` first, then update the returned record).
- Round 4: `review_code(…)` → confirm `super()` present and `vals` not mutated after super call.
