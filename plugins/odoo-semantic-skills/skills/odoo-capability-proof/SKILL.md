---
name: odoo-capability-proof
description: >
  Assemble an evidence-backed proof package that Odoo can fulfill a specific client
  requirement — citing real module names, model fields, and code snippets from the indexed
  codebase, not marketing claims. Use this skill ANY time a sales engineer, consultant, or
  account manager needs to convince a skeptical client/prospect that "yes, Odoo really does
  this — here's the proof". Fire on "prove Odoo can do X", "feature evidence for customer
  requirement Y", "customer asks does Odoo support X — I need to show the code", "client
  doesn't believe Odoo handles Z — build the evidence", "RFP response — back up every yes
  with module + code". Trigger especially on deadline signals ("for the demo", "before
  Friday", "in the RFP") — user needs real artifacts fast. Also fires on Vietnamese:
  "chứng minh Odoo làm được X cho khách". When the user only wants a yes/no
  answer on availability (no proof package needed), route to odoo-feature-check. When they're
  scoping MANY requirements at once for a quote, route to odoo-gap-analysis
---

## Persona
Sales Engineer / Pre-sales Consultant

## Out of Scope

- Single feature availability (no proof needed) → use `odoo-feature-check`
- Multi-requirement scope + effort quote → use `odoo-gap-analysis`
- Customer-facing objection response paragraph → use `odoo-objection-handler`
- A REAL recorded video/screencast of the flow (not text/code evidence) → use `odoo-demo-recorder`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.11.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (24h TTL per API key); subsequent calls pass odoo_version='auto' to reuse it instead of repeating the version (it can no longer be omitted).

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

When OSM is unreachable, the skill asks the user to provide the requirement in natural language + any customer-supplied documents (proposal, RFP excerpt). The skill still produces an evidence package based on core Odoo knowledge (module + model architecture from training), but without real code snippets — with caveat "not yet verified against the codebase index; double-check code details when OSM is back online".

## Output format

```
## Capability Proof: <requirement>

**Verdict:** Supported natively / Supported with configuration / Supported with light customization / Requires custom development
**Odoo version:** <version>
**Edition:** CE / EE / Custom distribution

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
Prompt: "prove Odoo 17 supports multi-level approval for purchase orders"
Output: Verdict with `purchase_stock` + `purchase` module evidence,
`entity_lookup(kind='method', model='purchase.order', method_name='button_approve')` override
chain, and demo steps.

## Notes / Integration

- This skill produces TEXT/code evidence and written demo steps — not a video. To turn the
  written demo steps above into a REAL screencast running on a live instance, hand them to
  `odoo-demo-recorder` (which drives the instance through the same steps and saves an MP4/GIF).
  Mention this as an optional next step; do not invoke it from here (depth rule).
