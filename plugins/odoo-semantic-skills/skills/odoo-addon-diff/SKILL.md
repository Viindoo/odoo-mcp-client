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
_Tool surface: server v0.11.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (24h TTL per API key) so subsequent calls can omit odoo_version.

**Primary tools:**
- `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, or a summary in one call.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, or module dependency chain in one call.
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

**Round 0 — Pin the version:** `set_active_version(odoo_version=…)`.

**Round 1 — Parallel:** Call `check_module_exists` for ALL modules and features in the
comparison request simultaneously. Each call is independent; no need to wait for any result
before firing the next.

**Round 2 — Parallel:** For every module that exists in both CE and EE but with different
depth, call `model_inspect(model=…, method='fields')` on all relevant models simultaneously to
extract field-level differences (e.g. EE adds `forecast_date`, `analytic_account_id`). These
calls are independent of each other.

Never claim a feature is EE-only without tool verification — incorrect claims damage credibility.

Write for a non-technical decision-maker. Translate field names to business language in the main table. Keep technical field names only in footnotes or appendices.

Group by business domain: Sales, Accounting, Inventory, Manufacturing, HR, etc.

For EE-only and distribution-specific features, add a brief business value note ("why does this matter for this client type?").

## Standalone-first fallback

When OSM is unreachable, the skill asks the user to paste manifest + relevant changelog/release notes from each edition. The skill still produces a comparison table based on changelog text parsing — with note "field-level details not yet verified; check again when OSM is back online".

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
