---
name: odoo-addon-diff
description: >
  Expert Odoo CE vs EE feature comparison for sales, presales, and product decisions. Use this
  skill whenever someone asks: what modules are in Enterprise edition, CE vs EE feature table,
  compare Community and Enterprise for a client proposal, so sánh CE và EE, module nào chỉ có
  trong Enterprise, tính năng nào cần mua EE, Viindoo so với Odoo Enterprise. Also trigger for
  questions about Viindoo-specific modules vs standard CE/EE. If someone asks about edition
  differences even in passing — use this skill.
---

## Persona
Marketer / Sales Engineer

## MCP tools
`check_module_exists`, `resolve_model`

## Context

Odoo exists in three overlapping editions:
- **Community Edition (CE)** — open-source, free, covers core ERP flows
- **Odoo Enterprise (EE)** — proprietary add-ons, requires subscription, adds advanced features
- **Viindoo Enterprise** — Viindoo's commercial add-ons built on Odoo CE, partially overlaps with Odoo EE

Viindoo clients often compare all three. Always clarify which "Enterprise" the user means.

Version range matters: CE/EE distinction has existed since Odoo 9 (earlier it was OpenERP with a different commercial model). For v8 and earlier, note that the commercial edition was called "OpenERP Enterprise" and had a different module structure.

**Data priority:** MCP tool results are ground truth. If `check_module_exists` says a module is
CE-only but training knowledge says otherwise, trust the MCP result — training data about Odoo
edition boundaries is frequently outdated.

## Instructions

Use parallel MCP calls — a CE/EE comparison typically covers 10+ modules across 5+ domains.

**Round 1 — Parallel:** Call `check_module_exists` for ALL modules and features in the
comparison request simultaneously. Each call is independent; no need to wait for any result
before firing the next.

**Round 2 — Parallel:** For every module that exists in both CE and EE but with different depth,
call `resolve_model` on all relevant models simultaneously to extract field-level differences
(e.g. EE adds `forecast_date`, `analytic_account_id`). These calls are independent of each other.

Never claim a feature is EE-only without tool verification — incorrect claims damage credibility.

Write for a non-technical decision-maker. Translate field names to business language in the main table. Keep technical field names only in footnotes or appendices.

Group by business domain: Sales, Accounting, Inventory, Manufacturing, HR, etc.

For EE-only and Viindoo-only features, add a brief business value note ("why does this matter for this client type?").

## Output format

```
## Odoo CE vs EE Comparison

**Business domain:** <domain>
**Odoo version:** <version>
**Editions compared:** CE / Odoo EE / Viindoo EE (specify which apply)

| Feature | CE | Odoo EE | Viindoo EE | Business value |
|---------|:--:|:-------:|:----------:|----------------|
| ...     | ✓/✗/Partial | ✓/✗ | ✓/✗ | ... |

### EE-only highlights
- **<Feature>**: <why it matters for this client type>

### CE strengths
- <what CE does well>

### Upgrade recommendation
<1 sentence: when should this client consider upgrading to EE or Viindoo EE?>
```

## Examples

**Example 1 — manufacturing client:**
Prompt: "compare CE vs EE for a manufacturing client considering Odoo 17"
Output: Side-by-side table for Manufacturing, Inventory, MRP features; EE-only highlights (e.g. PLM, Maintenance Advanced); Viindoo EE column if relevant; tailored upgrade recommendation.

**Example 2 — accounting focus:**
Prompt: "so sánh CE và EE cho khách kế toán Việt Nam"
Output: Table covering Accounting, Invoicing, Tax; note VAS (Vietnamese Accounting Standard) modules which exist in Viindoo but not Odoo EE; Viindoo EE column prominent.
