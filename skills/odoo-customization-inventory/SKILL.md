---
name: odoo-customization-inventory
description: >
  Generate a structured executive-level inventory of all custom + Viindoo modules in an Odoo
  deployment — classifying each as Standard / Viindoo / True custom, surfacing business
  purpose in plain language, base model extended, key custom fields, and upgrade risk flag.
  Use this skill ANY time a CEO/CTO/PM needs to understand the scope of their Odoo
  investment, even if they only paste a list of module names. Pushy trigger: fire on "list
  all our Odoo customizations", "inventory of custom modules", "what have we built on top
  of Odoo?", "liệt kê tất cả customization", "bản kiểm kê module tùy chỉnh", "chúng ta đang
  custom những gì?", "scope of customization before we upgrade", "before the audit, can
  you summarize our customizations?", "I have a list of modules — what do they do?", "are
  these standard or custom?", "for the M&A due diligence, list our Odoo extensions", "tổng
  hợp module custom phục vụ báo cáo cho ban giám đốc", "we have 47 addons in production —
  what's actually in there?", "what's safe to keep vs deprecate after we move to v17?".
  Trigger even if the user just dumps a list of names with no other context — that's the
  signal to enumerate. When the user wants to assess UPGRADE risk specifically (rather than
  just inventory), route to odoo-deprecation-audit. When they want to see business value
  of features for marketing, route to odoo-feature-highlights.
---

## Persona
CEO / CTO / Project Manager

## MCP tools
At session start: `set_active_version(odoo_version=…)` and `set_active_profile(profile_name=…)`
so the inventory targets a specific customer profile + version. Both are sticky 24h per API
key — handy when iterating on a long module list.

Primary tools:
- `check_module_exists(module, …)` — first-pass classifier: Standard / Viindoo / Custom.
- `module_inspect(module, method='describe')` — full architecture overview per module
  (manifest, models defined vs extended, view + JS patch counts) — the headline executive
  summary tool.
- `module_inspect(module, method='fields')` — key custom fields summary when describe is too
  light.
- `model_inspect(model, method='all')` — when a module extends a single model and the
  executive wants to know which standard model is being touched.
- `impact_analysis(symbol | module)` — for modules flagged high-risk based on usage breadth.

For bookmark-stable cross-references: each module is also exposed as
`odoo://17.0/module/<name>` for direct linking in audit reports.

## Context

Executives need to understand the scope of their Odoo investment before strategic decisions:
upgrades, migrations, vendor changes, or compliance audits. They need business language, not
technical jargon.

Custom modules in Odoo typically:
- Inherit and extend standard models (`_inherit`)
- Add new models with `_name`
- Override methods (business logic changes)
- Add computed fields, constraints, or security rules

Viindoo-specific: distinguish between Viindoo base modules (prefix `viin_`) and true custom
modules written by the client's IT team or a system integrator.

Version caveat: In Odoo v8/v9, `__openerp__.py` was used instead of `__manifest__.py`. If modules
use the old manifest, note the OpenERP-era origin.

**Data priority:** MCP tool results are ground truth for module classification. If `check_module_exists`
returns a match but training knowledge says it's a custom module (or vice versa), trust the MCP result.

## Instructions

Use parallel MCP calls — for a list of N modules, sequential calls are N× slower than needed.

**Round 0 — Pin version/profile:** `set_active_version(...)` + `set_active_profile(...)` so
every subsequent call targets the same customer baseline.

**Round 1 — Parallel:** Call `check_module_exists` for ALL modules simultaneously. Each call is
independent. Result: classify each module as Standard (exclude), Viindoo, or Custom.

**Round 2 — Parallel:** Call `model_inspect(model=…, method='all')` for ALL Viindoo + Custom
modules simultaneously. For each, extract: the base Odoo model being extended, up to 5 most
important custom fields, and whether key methods are overridden. These calls are independent
of each other.

**Round 2.5 — Per-module architecture drill-down (parallel):** For each Viindoo or Custom
module that the executive wants to understand more deeply, call
`module_inspect(module=<name>, method='describe')`. This returns a concise tree showing the
module's manifest metadata, which models it defines vs extends, and counts of views and JS
patches — giving the executive a one-glance architecture picture without reading source code.
Fire all `module_inspect(method='describe')` calls in parallel (one per module of interest).
The tree output is ~10–15 lines per module and is safe to include verbatim in the inventory
report.

Example — understanding `custom_loyalty` on Odoo 17:
```
module_inspect(module="custom_loyalty", method="describe")
```

**Round 3 — Parallel:** Call `impact_analysis` for modules flagged as high-usage or high-risk
based on Round 2 results. Fire all high-risk `impact_analysis` calls in one batch.

Write "Business purpose" in plain language. Infer from field names and module name — e.g., a module
adding `vat_number`, `tax_id_file` to `res.partner` is clearly "Vietnamese tax compliance".

Flag modules with many deprecated API calls or overrides of unstable methods as "upgrade risk".

## Output format

```
## Odoo Customization Inventory

**Total modules reviewed:** <N>
**Standard Odoo modules:** <N> (excluded from inventory)
**Viindoo base modules:** <N>
**True custom modules:** <N>
**Base Odoo models extended:** <N distinct>

| Module | Type | Base model | Key custom fields | Business purpose | Upgrade risk |
|--------|------|-----------|-------------------|-----------------|--------------|
| ...    | Custom/Viindoo | ... | ... | ... | Low/Med/High |

### High-risk modules
<List modules with High risk and brief explanation>

### Executive summary
<2–3 sentence narrative: scope of customization, what's safe to upgrade, what needs attention>

### Recommended action
<1 sentence for the next step>
```

## Examples

**Example 1:**
Prompt: "list all our Odoo customizations and what they do"
Output: Inventory table, each module classified as custom or Viindoo, business purpose in plain
language, upgrade risk flag.

**Example 2:**
Prompt: "chúng tôi có các module: viin_sale_advance, viin_account_vat, custom_loyalty — liệt kê"
Output: `viin_sale_advance` → Viindoo (sale management), `viin_account_vat` → Viindoo (Vietnamese
tax), `custom_loyalty` → Custom (loyalty program) — with field details and business purpose.
