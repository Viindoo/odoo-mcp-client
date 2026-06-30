---
name: odoo-addon-diff
argument-hint: "[business domain] [version]"
description: >
  Produce a CE vs EE vs custom-distribution comparison for a business domain - feature table,
  EE-only business-value notes, and an upgrade recommendation ready for a proposal.
  Version-aware: uses MCP check_module_exists/model_inspect; confirm version when unspecified.
  Trigger when edition differences come up, even in passing.
  Trigger on: "CE vs EE feature table", "edition comparison", "which modules are EE-only?",
  "is X a CE or EE feature?", "upsell argument for EE", "PLM / Studio / Maintenance - which
  edition?", "which edition is module X in?".
  Also fires on Vietnamese: "so sánh CE và EE", "tính năng nào chỉ có ở Enterprise",
  "module X thuộc bản nào", "cần bản Community hay Enterprise".
  Trigger even when the user names a specific feature/module and asks "what edition do I need?".
  When the user asks about ONE feature's availability (not a comparison), route to
  odoo-feature-check. When they want marketing copy for the Enterprise features themselves,
  route to odoo-feature-highlights
---

## Persona
Marketer / Sales Engineer

## Out of Scope

- Single feature availability check → use `odoo-feature-check`
- Marketing copy for feature highlights → use `odoo-feature-highlights`
- Pre-sales RFP evidence package → use `odoo-capability-proof`

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
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- `set_active_profile(profile_name='<viindoo_profile from .odoo-ai/context.md>')` - Pin tenant profile for the session so subsequent calls scope to one customer profile.

**Primary tools:**
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `list_available_profiles` ☆ - Enumerate which tenant profiles exist in the server index.
- `entity_lookup` ★ - Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `profile_inspect` - Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
<!-- END GENERATED TOOLS -->

## Context

| Edition | Model |
|---|---|
| CE (Community) | Open-source, free, core ERP flows |
| EE (Enterprise) | Proprietary add-ons, subscription required |
| Custom/Partner | Commercial add-ons on CE, may overlap with EE |

CE/EE distinction exists since v9 (v8 was "OpenERP Enterprise", different structure). Version matters. **Data priority:** MCP results are ground truth - training data about edition boundaries is frequently outdated.

## Instructions

Use parallel MCP calls - a CE/EE comparison covers 10+ modules across 5+ domains.

**Round 0 - Pin + scope:** `set_active_version(odoo_version=…)` then `list_available_profiles()`. For each side: `profile_inspect(method='repos', name=<profile>, odoo_version='<version>')` to get real repo coverage (CE vs EE vs distribution) as ground truth.

**Round 1 - Parallel:** `check_module_exists` for ALL modules simultaneously.

**Round 2 - Parallel:** For modules with differing depth across editions: `model_inspect(model=…, method='fields')` on all relevant models simultaneously. For doubtful field origin: `entity_lookup(kind='field', model=…, field=…, odoo_version='<version>')` → attribute CE vs EE from index, not training memory.

Never claim EE-only without tool verification. Write for non-technical decision-makers - translate field names to business language; keep technical names in footnotes. Group by domain. For EE-only/distribution features: add one-line business value note.

## Standalone-first fallback

When OSM is unreachable, follow `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

1. **Tier 2:** `WebFetch` raw manifests (CE: `https://raw.githubusercontent.com/odoo/odoo/<version>/addons/<module>/__manifest__.py`; EE: `.../odoo/enterprise/<version>/...`) and official release notes. Use local `Read`/`Grep` if a source tree is present. Label artifact `grounded: local-source (not OSM-indexed)`.
2. **Tier 3 (both fail):** Generate from training knowledge; prepend `OSM unavailable - ungrounded`; note "field-level details unverified". Never ask caller to paste manifests.

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
(status / produced / next) - additive run-harness output, changes nothing above.
