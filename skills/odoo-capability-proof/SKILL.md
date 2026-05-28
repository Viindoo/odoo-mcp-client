---
name: odoo-capability-proof
description: >
  Assemble an evidence-backed proof package that Odoo can fulfill a specific client
  requirement — citing real module names, model fields, and code snippets from the indexed
  codebase, not marketing claims. Use this skill ANY time a sales engineer, consultant, or
  account manager needs to convince a skeptical client/prospect that "yes, Odoo really does
  this — here's the proof". Pushy trigger: fire on "prove Odoo can do X", "show capability
  evidence for requirement Y", "for the demo, give me proof that…", "demo material",
  "chứng minh Odoo làm được X", "bằng chứng tính năng cho khách hàng", "khách hỏi Odoo có
  hỗ trợ X không (tôi cần show được code)", "client doesn't believe Odoo handles Z — help
  me build the evidence", "for the buy-side technical review, evidence of multi-currency
  invoicing", "before the demo this Friday, package proof of approval workflows",
  "trước buổi demo cho khách F&B — chứng minh Odoo làm được lot tracking",
  "RFP response — need to back up every yes with module + code", "competitor said Odoo
  can't do X — what's our counter-evidence?". Trigger especially when there's a deadline
  signal ("for the demo", "before Friday", "in the RFP", "buổi demo tuần sau") because the
  user needs real artifacts fast. When the user only wants a yes/no answer on availability
  (no proof package needed), route to odoo-feature-check. When they're scoping MANY
  requirements at once for a quote, route to odoo-gap-analysis
---

## Persona
Sales Engineer / Pre-sales Consultant

## Out of Scope

- Single feature availability (no proof needed) → use `odoo-feature-check`
- Multi-requirement scope + effort quote → use `odoo-gap-analysis`
- Customer-facing objection response paragraph → use `odoo-objection-handler`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.11.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (24h TTL per API key) so subsequent calls can omit odoo_version.

**Primary tools:**
- `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `entity_lookup` ★ — Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, or a summary in one call.
<!-- END GENERATED TOOLS -->

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

**Round 0 — Pin the version:** `set_active_version(odoo_version=…)`.

**Round 1 — Parallel:** Call `check_module_exists` + `find_examples` simultaneously.
`find_examples` takes a semantic query derived directly from the requirement text — it does not
need the module name from `check_module_exists`. Both can fire at the same time.

**Round 2 — Parallel (if module found):** Call `model_inspect(model=…, method='fields')` +
`entity_lookup(kind='method', model=…, method_name=…)` simultaneously. `model_inspect` shows
exact fields; `entity_lookup` shows the override chain for method-level requirements. If the
model name is already known from training knowledge, include these in Round 1.

Never fabricate capabilities. If the feature doesn't exist, say so and propose the most credible
workaround. When MCP results conflict with training knowledge (e.g. a module that training data
says should exist but `check_module_exists` doesn't find), trust the MCP result — it reflects
the actual indexed codebase.

## Standalone-first fallback

Khi OSM unreachable, skill yêu cầu user cung cấp requirement trong dạng natural language + bất kỳ tài liệu khách cung cấp (proposal, RFP excerpt). Skill vẫn sản sinh evidence package dựa trên kiến thức cơ bản về Odoo (module + model architecture từ training), nhưng không có code snippet thực tế — kèm caveat "chưa verify qua codebase index, hãy check lại chi tiết code khi OSM online".

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
`amount_currency`, `currency_rate`) from `model_inspect(model='account.move', method='fields')`, a
real code example, and demo steps.

**Example 2:**
Prompt: "chứng minh Odoo 17 hỗ trợ phê duyệt đa cấp cho đơn mua hàng"
Output: Verdict with `purchase_stock` + `purchase` module evidence,
`entity_lookup(kind='method', model='purchase.order', method_name='button_approve')` override
chain, demo steps in Vietnamese context.
