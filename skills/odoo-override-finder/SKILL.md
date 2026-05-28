---
name: odoo-override-finder
description: >
  Find the correct override point and pattern to extend Odoo behavior safely — including the
  exact method name, the module/file where to add the override, a ready-to-paste code
  template with proper `super()` call, the existing override chain (so you know who else is
  touching this hook), and version-specific compatibility notes. Use this skill ANY time
  someone wants to inject custom behavior into an existing Odoo flow, even when they only
  describe the BEHAVIOR they want to change without naming a method. Pushy trigger: fire
  whenever the request matches "I want to do X when Y happens in Odoo" — even informally.
  Realistic phrases this should catch include "where to hook into sale order confirmation",
  "khi xác nhận đơn hàng tao muốn chạy thêm validation", "best place to extend partner
  creation", "I need to run my code when an invoice is posted", "muốn override
  method gì để thay đổi giá khi tạo PO?", "extend the credit-limit check on customers",
  "trước khi gửi email, tôi muốn chèn thêm logic", "after a purchase order is approved I
  want to update a custom field", "what's the safest method to override for adding a
  discount calculation?", "tôi muốn thêm bước duyệt trước khi confirm", "khi user click
  nút post, override chỗ nào?", "where do I extend the picking validate flow?", "is there
  already someone overriding this method?". When the user wants to CHECK if code looks
  right rather than find a hook point, route to odoo-code-reviewer. When they want to know
  what changed between versions (rather than where to extend), route to odoo-version-diff
  or odoo-deprecation-audit.
---

## Persona
Developer

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.8.0. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (24h TTL per API key) so subsequent calls can omit odoo_version.

**Primary tools:**
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, or a summary in one call.
- `find_override_point` — Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior.
- `entity_lookup` ★ — Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `suggest_pattern` — Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
<!-- END GENERATED TOOLS -->

## Context

Getting the override location wrong causes subtle, hard-to-debug issues:
- Overriding at the wrong level (patching internal methods instead of public API)
- Missing `super()` calls in override chains
- Using deprecated override conventions (`@api.multi`, `@api.one`, OpenERP `_constraints`)
- Conflicting with existing overrides in multi-module stacks

**Era-specific override patterns:**

- **v8/v9 (OpenERP):** Use `osv.osv` or `orm.TransientModel`. Constraints via `_constraints` list.
  No `super()` — use `SUPERCLASS._method(self, cr, uid, ids, ...)`. `@api.*` decorators don't exist.
- **v10–v12 (transition):** `models.Model`, `@api.multi`, `@api.one`, `@api.one` deprecated v13.
  `super()` with new API: `super(MyModel, self).method(...)`.
- **v13+ (modern):** `@api.multi` and `@api.one` removed. All methods implicitly recordset-aware.
  `super()` standard Python 3 style: `super().method(...)`.
- **Frontend/JS v14+ (OWL primary):** Override via `patch()` utility: `import { patch } from "@web/core/utils/patch"`.
  Old `web.Widget` `.include()` pattern deprecated in v14, removed completely in v16+.
  In v13, OWL was introduced but `web.Widget` still coexisted — use `patch()` only for v14+.
- **XML/QWeb:** Override via `xpath` in XML with `position="replace|before|after|attributes"` on
  `<template>` or `<record>` with `inherit_id`.

**Data priority:** `find_override_point` and `entity_lookup(kind='method')` results reflect
the actual indexed codebase. If MCP says a method's override chain has 4 entries but training
knowledge only knows 2, trust MCP — it has the current state of all indexed repos.

## Instructions

### Round 0 — Pin the version

`set_active_version(odoo_version=…)` once.

### Round 1 — Enumerate methods (before drilling in)

Call `model_inspect(model=…, method='methods')` to get the full list of methods on the target
model with their override counts. This step is critical when the user describes *behavior*
they want to change (e.g. "when an invoice is confirmed") but hasn't named the exact method
yet — the enumeration surfaces the candidate names and shows which methods already have
overrides in the stack. Pick the best candidate method from this list before proceeding.

Example:
```
model_inspect(model="account.move", method="methods")
```

Output rows look like `action_post : 6 overrides` — a count ≥ 3 is a conflict-risk signal.

If the user has already named an exact method, you may skip this round and go directly to Round 2.

### Round 2 — Parallel

Call `model_inspect(model=…, method='summary')` + `find_override_point(model=…, method=…)`
simultaneously. Both take the model and method name from the user's request — they are
independent of each other.

### Round 3 — Parallel

Call `entity_lookup(kind='method', model=…, method_name=…)` + `suggest_pattern` simultaneously.
Both can be formulated after Round 2 and are independent of each other. `entity_lookup`
reveals the full override chain; `suggest_pattern` recommends the correct Odoo pattern.
Different scenarios call for different patterns:
   - Business logic change → `_inherit` + `super()` override
   - New computed value → `@api.depends` compute field
   - Pre/post hook → `create`/`write` override
   - Wizard step injection → `TransientModel` with `target_model_id`
   - JS behavior → OWL `patch()` utility (v14+; v13 introduced OWL but `web.Widget` still primary)

Present a concrete code snippet template pre-filled with the correct class name, method signature,
`super()` call, and proper decorator. Include compatibility note for which Odoo versions this
pattern is stable in.

**Warn explicitly** when:
- The override chain already has 3+ overrides (high conflict risk)
- The target method is marked as internal/private (`_` prefix but not double-underscore)
- The method has changed signature between versions in the user's range

## Output format

```
## Override Point: `<method_name>` in `<model_name>`

**Recommended location:** `<module>/<file>.py` (line ~<N>)
**Pattern:** <pattern name>
**Odoo version compatibility:** <version range>
**Era:** <OpenERP v8-9 / Legacy v10-12 / Modern v13+>

### Code template
```python
from odoo import models, api

class <ClassName>(models.Model):
    _inherit = '<model.name>'

    def <method_name>(self, <args>):
        # <brief comment explaining why this override exists>
        result = super().<method_name>(<args>)
        # <custom logic>
        return result
```

### Existing overrides in chain
| Module | File | Notes |
|--------|------|-------|
| ...    | ...  | ...   |

### Conflict risks
<Any conflicts or call-order issues to watch for>

### Compatibility notes
<Version-specific notes — e.g., "super() syntax differs in v8/v9">
```

## Examples

**Example 1:**
Prompt: "where to hook into sale order confirmation to add custom validation"
Output: `_action_confirm` in `sale.order`, code template with `super()` chain, list of existing
overrides (e.g. `sale_stock`, `sale_payment`), warning if chain is long.

**Example 2:**
Prompt: "tôi muốn thêm logic tính thuế tùy chỉnh khi lưu hóa đơn Odoo 17"
Output: Override `_compute_tax_id` or `write` on `account.move`, code template in Vietnamese
context, note about VAS tax constraints in `viin_account_vat` if installed.
