---
name: odoo-addon-diff
description: >
  Produce a CE vs EE vs custom-distribution comparison for a business domain — feature table,
  EE-only business-value notes, and an upgrade recommendation ready for a proposal.
  Version-aware: uses MCP check_module_exists/model_inspect; confirm version when unspecified.
  Trigger when edition differences come up, even in passing.
  Trigger on: "CE vs EE feature table", "edition comparison", "which modules are EE-only?",
  "is X a CE or EE feature?", "upsell argument for EE", "PLM / Studio / Maintenance — which
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
_Tool surface: server v0.13.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across many versions (v8-v19) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, WITHOUT a local checkout or a running instance. Unique signature: cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
> - Files already in your own working tree - if the exact version is checked out locally and you want one file, your own file-read/grep tools are faster and authoritative for that checkout; use Odoo Semantic for cross-version / inheritance-resolved / whole-graph questions or when the code is not checked out.
> - Free-text or web documentation - Odoo Semantic returns structured graph facts, not prose; use a docs or web-search tool.
>
> Name the kind of truth you need: CODE/STRUCTURE that is cross-version + inheritance-resolved + needs no checkout -> use Odoo Semantic. LIVE DATA from a running instance -> use a live Odoo MCP server. One file from a checkout you already have -> use your own file tools.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (per live MCP session, 24h idle TTL; resets on server restart); pass a CONCRETE version here (sentinels like 'auto' are rejected), then subsequent OTHER tool calls pass odoo_version='auto' to reuse the pin instead of repeating the version (it can no longer be omitted).
- `set_active_profile(profile_name='<viindoo_profile from .odoo-ai/context.md>')` — Pin tenant profile for the session so subsequent calls scope to one customer profile.

**Primary tools:**
- `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
- `list_available_profiles` ☆ — Enumerate which tenant profiles exist in the server index.
- `entity_lookup` ★ — Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `profile_inspect` — Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
<!-- END GENERATED TOOLS -->

## Context

Odoo exists in multiple editions:
- **Community Edition (CE)** — open-source, free, covers core ERP flows
- **Odoo Enterprise (EE)** — proprietary add-ons, requires subscription, adds advanced features
- **Custom/Partner distributions** — commercial or specialized add-ons built on Odoo CE, may overlap with Odoo EE

Always clarify which edition or distribution the user means when comparing options.

Version range matters: CE/EE distinction has existed since Odoo 9 (earlier it was OpenERP with a different commercial model). For v8 and earlier, note that the commercial edition was called "OpenERP Enterprise" and had a different module structure.

**Data priority:** MCP tool results are ground truth. If `check_module_exists` says a module is
CE-only but training knowledge says otherwise, trust the MCP result — training data about Odoo
edition boundaries is frequently outdated.

## Instructions

Use parallel MCP calls — a CE/EE comparison typically covers 10+ modules across 5+ domains.

**Round 0 — Pin version + profile, scope each distribution:** `set_active_version(odoo_version=…)`, then
`list_available_profiles()` to get the valid profile names (versioned, e.g. `odoo_17` / `viindoo_internal_17`).
For each side of the comparison, `profile_inspect(method='repos', name=<profile>, odoo_version='auto')` to see
that profile's real repo coverage (CE vs EE vs distribution) before comparing — so the CE/EE scope is ground
truth, not an assumption about which module lives in which edition.

**Round 1 — Parallel:** Call `check_module_exists` for ALL modules and features in the
comparison request simultaneously. Each call is independent; no need to wait for any result
before firing the next.

**Round 2 — Parallel:** For every module that exists in both CE and EE but with different
depth, call `model_inspect(model=…, method='fields')` on all relevant models simultaneously to
extract field-level differences (e.g. EE adds `forecast_date`, `analytic_account_id`). These
calls are independent of each other. For a field whose edition origin is in doubt,
`entity_lookup(kind='field', model=…, field=…, odoo_version='auto')` returns its source module — attribute
a field to CE vs EE from the index instead of training memory.

Never claim a feature is EE-only without tool verification — incorrect claims damage credibility.

Write for a non-technical decision-maker. Translate field names to business language in the main table. Keep technical field names only in footnotes or appendices.

Group by business domain: Sales, Accounting, Inventory, Manufacturing, HR, etc.

For EE-only and distribution-specific features, add a brief business value note ("why does this matter for this client type?").

## Standalone-first fallback

When OSM is unreachable, follow the three-tier grounding order from
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

1. **Tier 2 - self-serve first:**
   - `WebFetch` the raw manifests for each edition/version directly, e.g.
     `https://raw.githubusercontent.com/odoo/odoo/<version>/addons/<module>/__manifest__.py`
     (CE) and `https://raw.githubusercontent.com/odoo/enterprise/<version>/<module>/__manifest__.py`
     (EE). Use `mcp__odoo-semantic__scan_addons_source` or local `Read`/`Grep` if a local
     source tree is present.
   - `WebFetch` the official release notes page for the version (e.g.
     `https://www.odoo.com/odoo-<version>/release-notes`) or the GitHub CHANGELOG to resolve
     edition-boundary changes.
   - Label any artifact built this way `grounded: local-source (not OSM-indexed)`.
2. **Tier 3 - only if both fetches fail:** generate the comparison from training knowledge
   and prepend `OSM unavailable - ungrounded`; add note "field-level details not yet verified;
   check again when OSM is back online". Never ask the caller to paste manifests or release
   notes - those are Tier-2 fetches.

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

**Example 1 — manufacturing client:**
Prompt: "compare CE vs EE for a manufacturing client considering Odoo 17"
Output: Side-by-side table for Manufacturing, Inventory, MRP features; EE-only highlights (e.g. PLM, Maintenance Advanced); custom distribution column if relevant; tailored upgrade recommendation.

**Example 2 — accounting focus:**
Prompt: "compare CE and EE for an accounting-focused customer"
Output: Table covering Accounting, Invoicing, Tax; note specialized localization modules which may exist in custom distributions but not Odoo EE base.
