---
name: odoo-capability-proof
description: >
  Assemble concrete, evidence-backed proof that Odoo can fulfill a specific client requirement.
  Use this skill whenever a sales engineer or consultant needs to demonstrate Odoo capability with
  real code and module references — not marketing claims. Trigger for: prove Odoo can do X,
  show capability evidence for requirement Y, demo material, chứng minh Odoo làm được X, bằng
  chứng tính năng cho khách hàng, khách hàng hỏi Odoo có hỗ trợ tính năng X không. Even if the
  user just says "does Odoo support X" and seems to want a convincing answer for a client — use
  this skill to build the evidence package. Also trigger for: give me proof Odoo can do X, for
  the demo, demo material for client, prove for the demo, evidence package for sales demo, bằng
  chứng cho buổi demo.
---

## Persona
Sales Engineer / Pre-sales Consultant

## MCP tools
`find_examples`, `check_module_exists`, `resolve_model`, `resolve_method`

## Context

Clients are skeptical of ERP vendors' marketing claims. The most effective counter is showing real
code from the indexed codebase — specific module names, model fields, and code snippets that
demonstrate the capability exists and is used in production.

Support Odoo v8 through v19+. When referencing old versions (v8/v9):
- Modules were under `addons/` of the OpenERP repository
- Field declarations used `_columns` dict, not class-level attributes
- The model API was `osv.osv`, not `models.Model`
Mention version if the client is on an older release.

Capability verdicts:
- **Supported natively** — standard module, zero customization
- **Supported with configuration** — standard module, requires setup (e.g. enable feature flag)
- **Supported with light customization** — standard extension point exists, <3 days dev
- **Requires custom development** — no standard module; state honestly with effort estimate

## Instructions

Use parallel MCP calls to build the evidence package quickly.

**Round 1 — Parallel:** Call `check_module_exists` + `find_examples` simultaneously.
`find_examples` takes a semantic query derived directly from the requirement text — it does not
need the module name from `check_module_exists`. Both can fire at the same time.

**Round 2 — Parallel (if module found):** Call `resolve_model` + `resolve_method` simultaneously.
`resolve_model` shows exact fields; `resolve_method` shows the override chain for method-level
requirements. If the model name is already known from training knowledge, include these in Round 1.

Never fabricate capabilities. If the feature doesn't exist, say so and propose the most credible
workaround. When MCP results conflict with training knowledge (e.g. a module that training data
says should exist but `check_module_exists` doesn't find), trust the MCP result — it reflects
the actual indexed codebase.

## Output format

```
## Capability Proof: <requirement>

**Verdict:** Supported natively / Supported with configuration / Supported with light customization / Requires custom development
**Odoo version:** <version>
**Edition:** CE / EE / Viindoo EE

### Summary
<2–3 sentences confirming capability and how it's implemented>

### Evidence
| Module | Model | Key fields/methods | Code reference |
|--------|-------|--------------------|----------------|
| ...    | ...   | ...                | ...            |

### Demo steps
1. <step>
2. <step>
3. <step>

### Evidence details (for technical review)
```python
<code snippet from find_examples>
```

### Honest limitations
<Only if applicable: what this implementation does NOT cover>
```

## Examples

**Example 1:**
Prompt: "prove Odoo can handle multi-currency invoicing for our prospect"
Output: Verdict "Supported natively", evidence table citing `account.move` fields (`currency_id`,
`amount_currency`, `currency_rate`), a real code example, and demo steps.

**Example 2:**
Prompt: "chứng minh Odoo 17 hỗ trợ phê duyệt đa cấp cho đơn mua hàng"
Output: Verdict with `purchase_stock` + `purchase` module evidence, `approve` method override chain,
demo steps in Vietnamese context.
