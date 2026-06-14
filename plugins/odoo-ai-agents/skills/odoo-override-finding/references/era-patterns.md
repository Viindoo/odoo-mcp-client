# odoo-override-finding — Era Override Patterns + Output Format

## Era-specific override patterns

- **v8/v9 (OpenERP):** Use `osv.osv` or `orm.TransientModel`. Constraints via `_constraints` list. No `super()` — use `SUPERCLASS._method(self, cr, uid, ids, ...)`. `@api.*` decorators don't exist.
- **v10-v12 (transition):** `models.Model`, `@api.multi`, `@api.one` (deprecated v13). `super()` with new API: `super(MyModel, self).method(...)`.
- **v13+ (modern):** `@api.multi` and `@api.one` removed. All methods implicitly recordset-aware. `super()` standard Python 3 style: `super().method(...)`.
- **Frontend/JS v14+ (OWL primary):** Override via `patch()` utility: `import { patch } from "@web/core/utils/patch"`. Old `web.Widget` `.include()` pattern deprecated in v14, removed completely in v16+. In v13, OWL was introduced but `web.Widget` still coexisted — use `patch()` only for v14+.
- **XML/QWeb:** Override via `xpath` in XML with `position="replace|before|after|attributes"` on `<template>` or `<record>` with `inherit_id`.

**Data priority:** `find_override_point` and `entity_lookup(kind='method', odoo_version='<version>')` results reflect the actual indexed codebase. If MCP says a method's override chain has 4 entries but training knowledge only knows 2, trust MCP.

## Pattern scenarios

| Intent | Pattern |
|--------|---------|
| Business logic change | `_inherit` + `super()` override |
| New computed value | `@api.depends` compute field |
| Pre/post hook | `create`/`write` override |
| Wizard step injection | `TransientModel` with `target_model_id` |
| JS behavior | OWL `patch()` utility (v14+) |

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
Output: `_action_confirm` in `sale.order`, code template with `super()` chain, list of existing overrides (e.g. `sale_stock`, `sale_payment`), warning if chain is long.

**Example 2:**
Prompt: "I want to add custom tax calculation logic when saving an invoice in Odoo 17"
Output: Override `_compute_tax_id` or `write` on `account.move`, code template with usage context, note about tax constraints if custom tax modules are installed.
