---
name: odoo-code-reviewer
description: >
  Review Odoo code (Python, JavaScript, XML) for bugs, convention violations, security issues,
  and performance problems. Use this skill whenever a developer shares code and wants feedback —
  even implicitly. Trigger for: review this code, kiểm tra code này, có lỗi gì không, check my
  implementation, this doesn't work, review my Odoo code, is this correct, xem giúp tao đoạn
  này, tại sao code này không chạy, code review Odoo, review Python model, check XML view,
  review OWL component, review JS widget, check for security issues, performance review, is this
  the right Odoo pattern, convention check, audit this implementation. Always trigger when the
  user pastes code AND asks for review/check/audit — whether the request is explicit ("review
  this") or implicit ("why isn't this working?", "is this the right way?", "does this look
  correct to you?"). When in doubt, trigger: a false positive here is much less costly than
  missing a critical bug in production Odoo code.
---

## Persona
Developer / Tech Lead

## MCP tools (odoo-semantic)
`resolve_model`, `resolve_field`, `resolve_method`, `lint_check`, `lookup_core_api`, `suggest_pattern`

## Additional tools (ollama-delegate)
`mcp__ollama-delegate__review_code`

## Context

Odoo code has specific failure modes that generic code review misses. Understanding these
patterns is what separates a useful review from a surface-level style check.

### Python model failure modes

- **Missing `@api.depends` fields** — computed field never updates when upstream data changes.
  The compute method runs once on creation, then becomes stale silently.
- **ORM call inside a loop** — `_compute_*` iterating `self` and calling `record.field` or
  `self.env[model].search(…)` per iteration triggers N separate SQL queries. Always read fields
  outside the loop or use `mapped()`.
- **`write()` calling `self.write()`** — creates an infinite recursion that raises
  `RecursionError` only at runtime, not at import time. The fix is always to call
  `super().write(vals)`.
- **`_sql_constraints` missing `company_id`** — a `UNIQUE(name)` constraint in a
  multi-company setup allows the same name across companies, bypassing the intended guard.
- **`@api.constrains` on relational fields** — Odoo only triggers `@api.constrains` when the
  *decorated model's* fields are written. Writing to the related model (e.g., a `One2many`
  child) does NOT trigger the constraint. Use `_sql_constraints` or a `write` override instead.
- **Missing `super()` in `create` / `write`** — breaks Odoo's internal pipeline: field tracking,
  compute triggers, mail tracking, and downstream module overrides all rely on the super chain.
  This is always CRITICAL.
- **Deprecated API** — `@api.multi`, `@api.one`, `@api.cr`, `@api.v7`, `ids.browse()` were
  removed in v13/v14. Code that uses them imports without error but raises at call time.

### JavaScript (legacy v8–v14) failure modes

- **`this._super()` with wrong arguments** — breaks the mixin chain; arguments must match the
  parent signature exactly.
- **QWeb template name mismatch** — `this._template` or `xmlid` pointing at a non-existent
  template causes a silent render failure (empty widget, no JS error in some versions).
- **Missing `destroy()` override** — event listeners attached in `start()` leak indefinitely
  if not torn down in `destroy()`.
- **jQuery `.on()` without `.off()`** — accumulates handlers on long-lived views; each
  navigation adds another handler without removing the previous one.

### OWL issues (v15+)

- **Direct `useState` mutation** — `this.state.items.push(x)` bypasses OWL's reactivity
  system. Always assign a new value: `this.state.items = [...this.state.items, x]`.
- **Missing `onWillDestroy` cleanup** — timers, external event listeners, and subscriptions
  registered in `setup()` must be cleaned up or they persist across component unmounts.
- **`patch()` targeting wrong level** — OWL 1.x patches the prototype; OWL 2.x patches the
  class. Patching a prototype in OWL 2.x results in a runtime crash, not a load-time error.
- **`t-name` mismatch with JS import** — template referenced by a name that doesn't match
  the actual `t-name` attribute causes a runtime error when the component mounts.

### XML view failure modes

- **`position="replace"` breaking override chains** — if another module also overrides the
  same node, `replace` destroys its changes. Prefer `inside`, `before`, `after`, or targeted
  `attributes` + `attribute` elements.
- **Wrong `inherit_id` ref format** — should be `module.view_xml_id`, not just `view_xml_id`.
  A missing module prefix fails silently if another module happens to define the same id, or
  raises `ValueError` at install if not.
- **Hard-coded database `id` in record data** — using `id=` in `<record>` data creates a
  fixed integer id that conflicts on migration or cross-database restore.
- **Missing `noupdate="1"`** — records that should survive module updates (configuration data,
  default records) will be overwritten on every `odoo-bin -u` if not wrapped in
  `<data noupdate="1">`.

### Data-driven verification priority

The MCP tools make it possible to verify field names, model names, and method signatures
against the actual indexed codebase — not documentation or memory. A `resolve_field` that
returns "not found" is proof of a typo or a wrong model, not a documentation gap. Treat it
as CRITICAL.

## Instructions

Work in four steps. Fire parallel MCP calls within each step — they are independent.

### Step 1 — First-pass review (immediate)

Call `mcp__ollama-delegate__review_code` on the full pasted code:

```
mcp__ollama-delegate__review_code(
    code="<full pasted code>",
    focus="odoo conventions, logic bugs, missing super() calls, N+1 queries, deprecated API"
)
```

This surfaces issues quickly without waiting for MCP round-trips. Keep the raw findings — you
will merge them with MCP results in Step 4.

### Step 2 — Verify existence (parallel, as applicable)

Identify all non-trivial identifiers in the code and verify them against the index. Fire all
calls in parallel since they are independent:

- **`resolve_model(model_name)`** — if code declares `_inherit` or `_name`, verify the model
  exists and note its field list for cross-checking field references.
- **`resolve_field(field_name, model_name)`** — for every field that isn't obviously a new
  declaration (i.e., any field *read or written* in a method body, `@api.depends` path, or
  `related=` chain). A "not found" here is CRITICAL.
- **`resolve_method(method_name, model_name)`** — for every method the code overrides (e.g.,
  `create`, `write`, `unlink`, or a custom method from a base module). Confirms signature and
  that it is actually defined on the model.
- **`lint_check(code_snippet, odoo_version)`** — if the Odoo version is known or inferable,
  run to detect deprecated decorators and signatures.

If Odoo version is not stated, infer from context (profile name, repo path, `_inherit` of a
version-specific model). Default to 17.0 and note the assumption.

### Step 3 — Pattern check

If the code implements a recognizable Odoo pattern (computed field, SQL constraint, wizard,
create override, OWL component, etc.), call:

```
suggest_pattern(feature_description="<what this code is doing>")
```

This confirms whether the developer used the canonical pattern, or an older/incorrect variant.
A mismatch between the code's approach and the suggested pattern is a MED severity finding.

### Step 4 — Compile and present findings

Merge the three sources: ollama review (Step 1), MCP existence checks (Step 2), pattern check
(Step 3). Deduplicate overlapping findings. Assign severity using the rules below. Present in
the standard output format.

## Severity rules

| Severity | Criteria |
|----------|----------|
| CRITICAL | Field or method does not exist in the indexed codebase; infinite recursion risk; missing `super()` in `create`/`write`/`unlink`; direct SQL bypass without `env.cr.execute` sanitization |
| HIGH | N+1 query in a loop; deprecated API that will raise at call time; wrong `@api.depends` path causing stale compute; memory leak (listener not cleaned up) |
| MED | Odoo convention violation (naming, placement); missing error handling at a system boundary; suboptimal pattern when a canonical one exists; `@api.constrains` on relational field (silently skipped) |
| LOW | Cosmetic issues; non-translated user-facing strings; naming style; minor readability |

A review with zero CRITICAL/HIGH findings should say so clearly — it is valuable information
that the developer's implementation is structurally correct.

## Output format

```
## Code Review: `<brief description of what the code does>`

### Issues Found
| Severity | Location | Issue | Fix |
|----------|----------|-------|-----|
| CRITICAL | line N   | `field_name` does not exist on `model.name` | Use `actual_field_name` |
| HIGH     | line N   | N+1 query: ORM call inside `for rec in self` loop | Move search outside loop or use `mapped()` |
| MED      | line N   | `@api.depends('partner_id')` missing transitive path | Add `'partner_id.name'` |
| LOW      | line N   | String not translatable | Wrap in `_('...')` |

### Fixed Code
```python
# or ```xml or ```js — match the input language
<corrected implementation with issues fixed>
```

### What's Good
<One short paragraph noting what the code does correctly — even a buggy implementation often
has structural strengths worth acknowledging.>

### Suggested Pattern
<Only include this section if suggest_pattern returned a materially different approach.
Reference the pattern name and explain briefly why it is preferred.>
```

If there are no issues, say so:
```
### Issues Found
No CRITICAL or HIGH issues found. Code follows Odoo conventions correctly.
```

## Examples

**Example 1 — computed field with typo and missing `@api.depends`:**

User pastes a `_compute_total` method that reads `self.amout_total` (typo).

- Step 1: `review_code` catches missing `@api.depends` decorator.
- Step 2 (parallel): `resolve_field('amout_total', 'sale.order')` → NOT FOUND → CRITICAL.
  `resolve_model('sale.order')` → confirms `amount_total` is the correct name.
- Step 3: `suggest_pattern('computed field monetary')` → confirms `@api.depends` + `currency_field` pattern.
- Output: CRITICAL (typo `amout_total`) + HIGH (missing `@api.depends`) + corrected code with
  both fixes applied.

**Example 2 — OWL component with direct state mutation:**

User pastes an OWL component `setup()` that does `this.state.items.push(newItem)`.

- Step 1: `review_code` catches direct mutation as reactivity bug.
- Step 2: `resolve_model` not applicable (JS, no `_inherit`). Skip.
- Step 3: `suggest_pattern('OWL component useState list update')` → confirms immutable update pattern.
- Output: HIGH (reactivity lost — OWL won't re-render) + MED (missing `onWillDestroy` if
  timers present) + corrected OWL code using `this.state = { ...this.state, items: [...] }`.

**Example 3 — `write()` override with self-call:**

User pastes `def write(self, vals): … self.write({'state': 'done'}) … return super().write(vals)`.

- Step 1: `review_code` flags possible recursion.
- Step 2: `resolve_method('write', model_name)` → confirms override target exists.
- Step 3: Not applicable (override pattern is correct structurally, issue is the internal call).
- Output: CRITICAL (infinite recursion — `self.write()` inside `write()`) + fixed code using
  direct field assignment `self.state = 'done'` instead of calling `self.write()`.
