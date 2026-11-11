---
name: odoo-addon-diff
argument-hint: "[business domain] [version]"
description: >-
  Compares Odoo editions (CE vs EE) for a domain or module
---

## Role
Marketer / Sales Engineer

## Out of Scope

- Single feature availability check → use `odoo-feature-check`
- Marketing copy for feature highlights → use `odoo-feature-highlights`
- Pre-sales RFP evidence package → use `odoo-capability-proof`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `set_active_version` ☆ - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- `set_active_profile` ☆ - Pin tenant profile for the session so subsequent calls scope to one customer profile.
- `list_available_profiles` ☆ - Enumerate which tenant profiles exist in the server index.
- `entity_lookup` ★ - Single-entity drill-down by kind discriminator: model, field, method, view, module, pattern, or report - with full inheritance chain and source module.
- `profile_inspect` - Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
<!-- END GENERATED TOOLS -->

## Context

| Edition | Model |
|---|---|
| CE (Community) | Open-source, free, core ERP flows |
| EE (Enterprise) | Proprietary add-ons, subscription required |
| Custom/Partner | Commercial add-ons on CE, may overlap with EE |

CE/EE distinction exists since v9 (v8 was "OpenERP Enterprise", different structure). Version matters. **Data priority:** MCP results are ground truth - training data about edition boundaries is frequently outdated.

**Scope is elastic.** "Business domain" (the `argument-hint`) is not limited to a broad area like
"Accounting" - it can be as narrow as a single named feature (e.g. `odoo-position-feature`
dispatches this skill for one feature's CE/EE comparison). Scale the table to whatever scope was
asked for - one row for a single feature, 10+ for a broad domain.

## Instructions

Use parallel MCP calls - a CE/EE comparison covers 10+ modules across 5+ domains.

**Round 0 - Pin + scope:** `set_active_version(odoo_version=…)` then `list_available_profiles()`. For each side: `profile_inspect(method='repos', name=<profile>, odoo_version='<version>')` to get real repo coverage (CE vs EE vs distribution) as ground truth.

**Round 1 - Parallel:** `check_module_exists` for ALL modules simultaneously.

**Round 2 - Parallel:** For modules with differing depth across editions: `model_inspect(model=…, method='fields')` on all relevant models simultaneously. For doubtful field origin: `entity_lookup(kind='field', model=…, field=…, odoo_version='<version>')` → attribute CE vs EE from index, not training memory.

Never claim EE-only without tool verification. Write for non-technical decision-makers - translate field names to business language; keep technical names in footnotes. Group by domain. For EE-only/distribution features: add one-line business value note.

## Standalone-first fallback

When OSM is unreachable, follow `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

1. **Tier 2:** `WebFetch` raw manifests (CE: `https://raw.githubusercontent.com/odoo/odoo/<version>/addons/<module>/__manifest__.py`; EE: `.../odoo/enterprise/<version>/...`) and official release notes. Use local `Read`/`Grep` if a source tree is present. Label artifact `grounded: local-source - not OSM-indexed`.
2. **Tier 3 (both fail):** Generate from training knowledge; prepend `grounded: ungrounded - OSM unavailable`; note "field-level details unverified". Never ask caller to paste manifests.

## Output format

```
## Odoo CE vs EE Comparison

**Business domain:** <domain>
**Odoo version:** <version>
**Editions compared:** CE / EE / Custom distribution (specify which apply)

| Feature | CE | EE | Your distribution | Business value |
|---------|:--:|:--:|:-----------------:|----------------|
| ...     | ✓/✗/Partial | ✓/✗ | ✓/✗ | ... |

### EE-only highlights
- **<Feature>**: <why it matters for this client type>

### CE strengths
- <what CE does well>

### Upgrade recommendation
<1 sentence: when should this client consider upgrading to EE or a custom distribution?>
```

## Examples

**Example 1 - manufacturing client:**
Prompt: "compare CE vs EE for a manufacturing client considering Odoo 17"
Output: Side-by-side table for Manufacturing, Inventory, MRP features; EE-only highlights (e.g. PLM, Maintenance Advanced); custom distribution column if relevant; tailored upgrade recommendation.

**Example 2 - accounting focus:**
Prompt: "compare CE and EE for an accounting-focused customer"
Output: Table covering Accounting, Invoicing, Tax; note specialized localization modules which may exist in custom distributions but not Odoo EE base.

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next) - additive plan-runner output, changes nothing above.
