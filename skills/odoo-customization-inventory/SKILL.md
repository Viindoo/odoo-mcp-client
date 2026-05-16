---
name: odoo-customization-inventory
description: >
  Generate a structured inventory of all custom Odoo modules and what they do for executive
  decision-making. Use this skill whenever someone asks: list all our Odoo customizations,
  inventory of custom modules, what have we built on top of Odoo, liệt kê tất cả customization,
  bản kiểm kê module tùy chỉnh, chúng ta đang custom những gì, scope of customization before
  upgrade or audit. Trigger even if the user just provides a list of module names and asks
  "what do these do" or "are these standard or custom".
---

## Persona
CEO / CTO / Project Manager

## MCP tools
`check_module_exists`, `resolve_model`, `impact_analysis`, `describe_module`

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

**Round 1 — Parallel:** Call `check_module_exists` for ALL modules simultaneously. Each call is
independent. Result: classify each module as Standard (exclude), Viindoo, or Custom.

**Round 2 — Parallel:** Call `resolve_model` for ALL Viindoo + Custom modules simultaneously.
For each, extract: the base Odoo model being extended, up to 5 most important custom fields,
and whether key methods are overridden. These calls are independent of each other.

**Round 2.5 — Per-module architecture drill-down (parallel):** For each Viindoo or Custom module
that the executive wants to understand more deeply, call `describe_module(name, odoo_version)`.
This returns a concise tree showing the module's manifest metadata, which models it defines vs
extends, and counts of views and JS patches — giving the executive a one-glance architecture
picture without reading source code. Fire all `describe_module` calls in parallel (one per module
of interest). The tree output is ~10–15 lines per module and is safe to include verbatim in the
inventory report.

Example — understanding `custom_loyalty` on Odoo 17:
```
describe_module(name="custom_loyalty", odoo_version="17.0")
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
