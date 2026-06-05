---
name: odoo-customization-inventory
description: >
  Generate a structured executive-level inventory of all custom + distribution modules in an
  Odoo deployment — classifying each as Standard / Distribution-maintained / True custom,
  surfacing business purpose, base model extended, key custom fields, and upgrade risk flag.
  Use this skill ANY time a CEO/CTO/PM needs to understand the scope of their Odoo investment,
  even if they only paste a list of module names. Trigger on: "what have we built on top of
  Odoo?", "scope of customization before upgrade", "M&A due diligence list our extensions",
  "what's safe to keep vs deprecate?". Also fires on Vietnamese: "đã tuỳ biến những gì trên
  Odoo", "phạm vi customization trước khi nâng cấp", "module nào nên giữ module nào nên bỏ".
  Trigger even if the user dumps a list of names with
  no context — that's the signal to enumerate. Upgrade risk scoring → odoo-deprecation-audit.
  Marketing feature highlights → odoo-feature-highlights
---

## Persona
CEO / CTO / Project Manager

## Out of Scope

- Upgrade risk scoring + deprecated API scan → use `odoo-deprecation-audit`
- Executive 1-page risk dashboard → use `odoo-risk-overview`
- Marketing highlights of features → use `odoo-feature-highlights`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.11.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Session bootstrap** (call once at session start):
- `set_active_profile(profile_name='<viindoo_profile from .odoo-ai/context.md>')` — Pin tenant profile for the session so subsequent calls scope to one customer profile.
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (per live MCP session, 24h idle TTL; resets on server restart); pass a CONCRETE version here (sentinels like 'auto' are rejected), then subsequent OTHER tool calls pass odoo_version='auto' to reuse the pin instead of repeating the version (it can no longer be omitted).

**Primary tools:**
- `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `impact_analysis` — Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, or a summary in one call.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
<!-- END GENERATED TOOLS -->

## Context

Executives need to understand the scope of their Odoo investment before strategic decisions:
upgrades, migrations, vendor changes, or compliance audits. They need business language, not
technical jargon.

Custom modules in Odoo typically:
- Inherit and extend standard models (`_inherit`)
- Add new models with `_name`
- Override methods (business logic changes)
- Add computed fields, constraints, or security rules

Distribution-specific: distinguish between distribution-maintained base modules and true custom
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
independent. Result: classify each module as Standard (exclude), Distribution-maintained, or Custom.

**Round 2 — Parallel:** Call `model_inspect(model=…, method='fields')` for ALL distribution-maintained + Custom
modules simultaneously. For each, extract: the base Odoo model being extended, up to 5 most
important custom fields, and whether key methods are overridden. These calls are independent
of each other.

**Round 2.5 — Per-module architecture drill-down (parallel):** For each distribution-maintained or Custom
module that the executive wants to understand more deeply, call
`module_inspect(name=<name>, method='summary', odoo_version='auto')`. This returns a concise tree showing the
module's manifest metadata, which models it defines vs extends, and counts of views and JS
patches — giving the executive a one-glance architecture picture without reading source code.
Fire all `module_inspect(method='summary', odoo_version='auto')` calls in parallel (one per module of interest).
The tree output is ~10–15 lines per module and is safe to include verbatim in the inventory
report.

Example — understanding `custom_loyalty` on Odoo 17:
```
module_inspect(name="custom_loyalty", method="summary", odoo_version='auto')
```

**Round 3 — Parallel:** Call `impact_analysis` for modules flagged as high-usage or high-risk
based on Round 2 results. Fire all high-risk `impact_analysis` calls in one batch.

Write "Business purpose" in plain language. Infer from field names and module name — e.g., a module
adding `vat_number`, `tax_id_file` to `res.partner` is clearly "Vietnamese tax compliance".

Flag modules with many deprecated API calls or overrides of unstable methods as "upgrade risk".

## Standalone-first fallback

When OSM unreachable, follow the three-tier grounding protocol defined in
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`. Specifically:

- **Tier 2 (disk):** Run `find . -maxdepth 3 -name "__manifest__.py"` (also
  `__openerp__.py` for legacy modules), then `Read` each manifest to extract `name`,
  `summary`, `depends`, and `version`. Build the inventory from those files directly.
  Only ask the user if the working directory is not an Odoo repo and no manifests are
  found anywhere within 3 levels.
- **Tier 3 (training):** If no readable manifests exist, classify modules from
  training knowledge with caveat `OSM unavailable - ungrounded` and
  "detailed code & inheritance not yet scanned - verify when OSM is back online".

## Output format

```
## Odoo Customization Inventory

**Total modules reviewed:** <N>
**Standard Odoo modules:** <N> (excluded from inventory)
**Distribution-maintained modules:** <N>
**True custom modules:** <N>
**Base Odoo models extended:** <N distinct>

| Module | Type | Base model | Key custom fields | Business purpose | Upgrade risk |
|--------|------|-----------|-------------------|-----------------|--------------|
| ...    | Custom/Distribution | ... | ... | ... | Low/Med/High |

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
Prompt: "we have modules: dist_sale_advance, dist_account_vat, custom_loyalty — list them"
Output: `dist_sale_advance` → Distribution-maintained (sale management), `dist_account_vat` → Distribution-maintained
(tax compliance), `custom_loyalty` → Custom (loyalty program) — with field details and business purpose.
