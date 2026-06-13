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
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_profile(profile_name='<viindoo_profile from .odoo-ai/context.md>')` — Pin tenant profile for the session so subsequent calls scope to one customer profile.
- `set_active_version(odoo_version='17.0')` — Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `impact_analysis` — Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
- `list_available_profiles` ☆ — Enumerate which tenant profiles exist in the server index.
- `find_deprecated_usage` — Scan the indexed codebase for usages of deprecated API patterns.
- `profile_inspect` — Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
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

**Round 0 — Pin version/profile + enumerate:** `list_available_profiles()` first to get the valid
profile name (the server registers versioned names like `viindoo_internal_17` / `odoo_17` — never
assume a hyphenated or unversioned one), then `set_active_version(...)` + `set_active_profile(profile_name=<profile>)`
so every subsequent call targets the same customer baseline. Then
`profile_inspect(method='modules', name=<profile>, odoo_version='<version>')` to enumerate the profile's own
modules in one call — this is the inventory backbone, so you don't depend on the user pasting a module list.

**Round 1 — Parallel:** Call `check_module_exists` for ALL modules simultaneously. Each call is
independent. Result: classify each module as Standard (exclude), Distribution-maintained, or Custom.

**Round 2 — Parallel:** Call `model_inspect(model=…, method='fields')` for ALL distribution-maintained + Custom
modules simultaneously. For each, extract: the base Odoo model being extended, up to 5 most
important custom fields, and whether key methods are overridden. These calls are independent
of each other.

**Round 2.5 — Per-module architecture drill-down (parallel):** For each distribution-maintained or Custom
module that the executive wants to understand more deeply, call
`module_inspect(name=<name>, method='summary', odoo_version='<version>')`. This returns a concise tree showing the
module's manifest metadata, which models it defines vs extends, and counts of views and JS
patches — giving the executive a one-glance architecture picture without reading source code.
Fire all `module_inspect(method='summary', odoo_version='<version>')` calls in parallel (one per module of interest).
The tree output is ~10–15 lines per module and is safe to include verbatim in the inventory
report.

> Resource shortcut: when a module name is already known, `odoo://{version}/module/{name}` returns the same
summary as a `module_inspect` summary call without a tool round-trip.

Example — understanding `custom_loyalty` on Odoo 17:
```
module_inspect(name="custom_loyalty", method="summary", odoo_version='<version>')
```

**Round 3 — Parallel:** Call `impact_analysis` for modules flagged as high-usage or high-risk
based on Round 2 results. Fire all high-risk `impact_analysis` calls in one batch.

Write "Business purpose" in plain language. Infer from field names and module name — e.g., a module
adding `vat_number`, `tax_id_file` to `res.partner` is clearly "Vietnamese tax compliance".

Flag modules with many deprecated API calls or overrides of unstable methods as "upgrade risk".
Ground this with `find_deprecated_usage(odoo_version='<version>', profile_name=<profile>)` (scoped to the
customer profile) instead of inferring from names — the scan returns the real deprecated-API hits per
module; pair it with `module_inspect(name=<module>, method='dependencies', odoo_version='<version>')` to get
the real dependency chain that determines a module's upgrade blast radius.

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

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
