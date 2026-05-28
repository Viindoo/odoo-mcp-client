---
name: odoo-coder
description: >
  Write complete, production-ready Python/XML Odoo backend code — from a single computed
  field up to a full new module. Use this skill ANY time someone asks for backend changes to
  an Odoo addon, even if they only describe the business outcome ("khách muốn lock đơn hàng
  khi tổng > 100 triệu", "I need to auto-fill the delivery address from the partner") and
  never mention "code", "field", "model", or "Python". Pushy trigger: if the request involves
  changing what an Odoo record stores, how it computes a value, what it validates, who can
  read or write it, how it appears on a form, or how it migrates between versions — this
  skill should fire. Realistic phrases this should catch include "tạo computed field tính VAT
  10%", "viết onchange cho field partner_id", "thêm SQL constraint unique theo công ty",
  "tôi muốn tạo model wizard cho việc duyệt đơn", "add a stored field x to sale order line",
  "override create method on res.partner so it sets default ref", "cần migration script chạy
  khi nâng cấp từ v15 lên v17", "làm sao set required cho field này khi state = draft",
  "create a server action that…", "viết unit test cho method này", "add a new model and
  link it to sale.order via many2many", "khách yêu cầu thêm cột trên form…", "I want the
  delivery date to default to today + 3 working days", "implement a domain filter that…",
  plus business-rule descriptions with NO technical vocabulary at all (e.g. "discount can
  never exceed 20% of unit price"). When the user is asking how to LOOK UP existing code
  rather than write new code, route to odoo-feature-check or odoo-override-finder instead.
---

## Persona
Developer

## MCP tools (odoo-semantic)

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.8.0. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (24h TTL per API key) so subsequent calls can omit odoo_version.

**Primary tools:**
- `entity_lookup` ★ — Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `lint_check` — Validate code against Odoo-specific lint rules (Python/JavaScript), or return corpus-level XML RelaxNG violation nodes (language='xml', server v0.9.1+).
- `lookup_core_api` — Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, or a summary in one call.
- `resolve_orm_chain` ⊕ — Walk a dotted ORM field path hop by hop to the terminal field type or the exact hop where it breaks.
- `suggest_pattern` — Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
- `validate_depends` ⊕ — Validate compute method's `@api.depends('a.b', ...)` paths; flag `id` and suggest typos.
- `validate_domain` ⊕ — Validate search domain terms: field-path resolution and operator version-awareness.
- `validate_relation` ⊕ — Assert a relational field points at the expected comodel (many2one/one2many/many2many).

**Ollama-delegate tools** (local model, cost-free):
- `mcp__ollama-delegate__complete_code`
- `mcp__ollama-delegate__generate_code`
- `mcp__ollama-delegate__review_code`
<!-- END GENERATED TOOLS -->

## Context

Writing Odoo code correctly from the start prevents costly refactors. The main failure modes are:

- **Wrong field types or paths** — always call `entity_lookup(kind='field', …)` before adding
  a Related or inherited field; the source field type determines what yours must be.
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

### Round 0 — Pin the version (once per session)

`set_active_version(odoo_version='17.0')` — every subsequent tool call inherits this version.
Skip if already set this session.

### Round 1 — Gather context (parallel)

Call all three simultaneously:
1. `model_inspect(model='<target_model>', method='fields')` — returns the field list and
   authoritative source module. Combine with `method='methods'` if you also need the method
   list, or `method='summary'` for the full inheritance chain overview.
2. (Skipped — use `model_inspect(method='fields')` for the field list. Use
   `model_inspect(method='summary')` when you need the inheritance chain and module overview.)
3. `suggest_pattern(feature_description)` — get the canonical Odoo pattern for the feature
   type (computed field, SQL constraint, wizard, etc.).

If you do not yet know the target model name, ask the user before proceeding.

### Round 2 — Resolve specifics (parallel when both apply)

- **Extending an existing field** → call `entity_lookup(kind='field', model='<model>', field='<name>')`
  to confirm type, whether it is stored/computed, and which module declares it.
- **Overriding an existing method** → call `lint_check(code=<the method source>)` to detect
  deprecated signatures (e.g. `@api.multi`, old-style `cr, uid` arguments).

Both calls are independent — fire in parallel if the task requires both.

### Round 3 — Generate code

Choose based on complexity:

**Boilerplate path** — call:
```
mcp__ollama-delegate__generate_code(
    task="<precise feature description including field names and types from Rounds 1-2>",
    context="<model class header + relevant fields from model_inspect output>"
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

**ORM validation gate (v0.8).** If the generated code contains any of the following, validate
it against the index before presenting — these calls are cheap and catch the exact failure
modes the reviewer can only guess at:
- a computed field → `validate_depends(model, '<_compute_method>')` (after the field is
  indexed) or `resolve_orm_chain(model, '<each depends path>')` for not-yet-indexed code;
- a search domain / `ir.rule` / `domain=[…]` → `validate_domain(model, '<domain literal>')`;
- a `related=` chain → `resolve_orm_chain(model, '<related path>')`;
- a relational field assertion → `validate_relation(model, '<field>', '<expected comodel>')`.

Any `BROKEN` / `ERROR` / `MISMATCH` result is a blocker — fix the path/operator/comodel before
presenting, do not ship it.

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

- Round 0: `set_active_version('17.0')` (once per session).
- Round 1 (parallel): `model_inspect(model='purchase.order', method='fields')` → confirm
  `amount_subtotal` exists and is Float; `suggest_pattern('computed field monetary')` → get
  `@api.depends` + `currency_field` pattern.
- Round 2: `entity_lookup(kind='field', model='purchase.order', field='amount_subtotal')` →
  type=Monetary, currency via `currency_id`.
- Round 3: `generate_code(task="Computed Monetary field amount_vat = amount_subtotal * 0.1 on purchase.order", context="class PurchaseOrder(models.Model): _inherit = 'purchase.order'\n  amount_subtotal: Monetary, currency_id: Many2one")`
- Round 4: `review_code(…)` → confirm `@api.depends('amount_subtotal')` present, `currency_field='currency_id'` set.
- Output: full Python class + XPath to add `amount_vat` after `amount_subtotal` in purchase form view.

**Example 2 — SQL constraint:**
Prompt: "add SQL constraint to prevent duplicate partner name within same company"

- Round 1 (parallel): `model_inspect(model='res.partner', method='fields')` → confirm
  `company_id` field; `suggest_pattern('sql constraint unique multi-company')` → get pattern.
- Round 3: `generate_code(task="SQL constraint unique (name, company_id) on res.partner", context="…")`
- Output: `_sql_constraints` list with `UNIQUE(name, company_id)` + translated error message.

**Example 3 — create override:**
Prompt: "override `create` on `sale.order` to auto-assign a sequence ref from `ir.sequence`"

- Round 1 (parallel): `model_inspect(model='sale.order', method='summary')` + `suggest_pattern('create override sequence')`.
- Round 2: `lint_check('create')` → confirm no deprecated signature.
- Round 3: Direct Claude (cross-model + `super()` position matters — must call `super().create(vals)` first, then update the returned record).
- Round 4: `review_code(…)` → confirm `super()` present and `vals` not mutated after super call.
