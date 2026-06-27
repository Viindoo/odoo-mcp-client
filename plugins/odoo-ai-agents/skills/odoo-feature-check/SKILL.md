---
name: odoo-feature-check
description: >
  Answer "does standard Odoo already do this?" with evidence - module name, edition (CE / EE),
  key fields/models, and a one-line verdict ready for a client email. Version-aware: uses MCP
  check_module_exists/find_examples; confirm version when unspecified. Fire before answering
  from memory - training data about Odoo modules drifts fast.
  Trigger on: "does Odoo have…", "is X available out of the box?", "do we need to build this
  or is it already there?", "what edition do I need for Z?".
  Also fires on Vietnamese: "Odoo có sẵn tính năng này không", "cần code thêm hay đã có sẵn",
  "cần bản CE hay EE cho Z".
  Use this when the user is asking about ONE feature/module; when they list MANY requirements
  at once route to odoo-gap-analysis instead. When they want to see real source-code examples
  of X being used, route to odoo-feature-highlights or odoo-capability-proof
---

## Persona
Consultant / Developer

## Out of Scope

- Multi-requirement effort matrix → use `odoo-gap-analysis`
- CE vs EE three-way comparison → use `odoo-addon-diff`
- Customer-facing objection response → use `odoo-objection-handling`

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

**Primary tools:**
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `describe_module` - Module manifest + defined/extended model counts + view/JS inventory in one call.
- `find_examples` - Semantic code search returning real indexed code snippets from the Odoo codebase.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `profile_inspect` - Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
- `suggest_pattern` - Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
<!-- END GENERATED TOOLS -->

## Context

Coverage levels: (1) **CE native** - free, zero customization; (2) **EE only** - paid subscription; (3) **App Store / third-party** - not officially supported.

Version matters: v12+ feature may not exist in v8/v9 (OpenERP era - different module names, `_columns` dict, etc.). Always resolve the target version.

**Data priority:** MCP results over training knowledge - training data about Odoo module names/versions drifts fast.

**Index coverage is not ground truth.** A module ABSENT from the OSM index is NOT proof the product lacks the feature - profile/index coverage is incomplete for commercial layers. Surface coverage with a `profile_inspect(method='repos', …)` repo check and tag unknowns `[inferred]` rather than asserting absence.

## Instructions

**Round 0 - Pin the version (once):** `set_active_version(odoo_version=…)`.

**Round 1 - Parallel:** `check_module_exists` + `find_examples` simultaneously (independent).

**Round 2 - Parallel (after Round 1):** `model_inspect(model=…, method='fields')` + `suggest_pattern` simultaneously (independent).

**Round 3 - Deep dive (module confirmed):** `module_inspect(name=<name>, method='summary', odoo_version='<version>')` - manifest summary, models defined/extended, view count, JS patch count. For exact field/view coverage, follow up with `module_inspect(method='fields', …)` or `module_inspect(method='views', …)`.

**Verdict levels:** `Available in CE` (zero cost) / `Available in Odoo EE only` (subscription) / `Partial - standard covers X, custom needed for Y` (specify gap) / `Not available - custom development required` (with effort note). Always cite the exact module name.

**Never infer brand from slug.** A module's technical slug is NOT evidence of its provider/brand/integrated vendor - a vendor-like token in the slug is not proof of that vendor. Take module identity only from OSM `check_module_exists` / `describe_module` / `module_inspect` output (`author`, and `shortdesc` when present). If neither is available, tag the claim `[inferred]` and do NOT assert a provider/brand.

## Standalone-first fallback

When OSM is unreachable, follow `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

- **Tier 2 - WebFetch:** `WebFetch("https://raw.githubusercontent.com/odoo/odoo/<version>/addons/<module>/__manifest__.py")` + key model files. EE: try `odoo/enterprise/<version>/...`. Local source tree: `find . -maxdepth 4 -name "__manifest__.py"` then `Read`.
- **Tier 3 (last resort):** derive from training knowledge; label `OSM unavailable - ungrounded`.
- `NEEDS_CONTEXT` only if both version AND feature name are unresolvable. Never ask for content WebFetch can supply.

## Output format

```
## Feature Availability Check

**Feature requested:** <feature description>
**Odoo version:** <version>

| Feature aspect | CE | Odoo EE | Module | Source | Notes |
|---------------|:--:|:-------:|--------|--------|-------|
| ...           | ✓/✗ | ✓/✗ | ...  | [OSM-index] / [inferred] | ...   |

### Verdict
**<Available in CE / Available in EE only / Partial / Not available>**

### Evidence
- **Module:** `<module_name>`
- **Primary model:** `<model_name>`
- **Module scope:** <N> models defined, <N> models extended, <N> views, <N> JS patches (from module_inspect describe)
- **Key fields:** `<field1>`, `<field2>` - <what they implement>
- **Example:** <brief description from find_examples>

### Custom development needed (if partial)
- **Gap:** <what standard doesn't cover>
- **Extension pattern:** <from suggest_pattern>
- **Estimated effort:** <S/M/L>

### Recommendation
<1-2 sentences for the client>
```

**Provenance rules:**
- Tag each table row `[OSM-index]` (found in the indexed source) or `[inferred]` (reasoned, not grounded).
- Downgrade customer-facing wording for any `[inferred]` claim - use "likely / typically / to be confirmed", never "verified / guaranteed".
- OSM index is a static source index - necessary but NOT sufficient proof a shipped product does X; live verification is out of scope here, so never phrase an `[OSM-index]` hit as "verified available".

## Examples

**Example 1:** "does Odoo have a subscription billing module?" → `sale_subscription` EE-only, verdict "Available in Odoo EE only".

**Example 2:** "fixed asset management?" → `account_asset` EE-only; `model_inspect(model='account.asset', method='fields', odoo_version='<version>')` shows key fields; recommendation provided.

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next) - additive run-driver output, changes nothing above.
