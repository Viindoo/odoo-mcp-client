---
name: odoo-addon-diff
description: >
  Produce a side-by-side comparison of Odoo Community (CE) vs Odoo Enterprise (EE) vs
  Viindoo Enterprise for a specific business domain — with a feature table, business-value
  notes for EE-only highlights, and a tailored upgrade recommendation ready to paste into a
  proposal. Use this skill ANY time the conversation touches edition differences, even in
  passing. Pushy trigger: fire on "what modules are in Enterprise edition?", "CE vs EE
  feature table", "compare Community and Enterprise for a client", "so sánh CE và EE",
  "module nào chỉ có trong Enterprise?", "tính năng nào cần mua EE?", "Viindoo so với Odoo
  Enterprise", "is X a CE or EE feature?", "khách hỏi nâng từ CE lên EE có gì khác?",
  "before quoting EE license fee, what extra do they actually get?", "for a manufacturing
  client — what would EE add?", "for accounting in Vietnam — Odoo EE đủ chưa hay cần
  Viindoo EE?", "what's Viindoo-only that's not in either Odoo edition?", "client running
  CE — what's the upsell argument for EE?", "PLM, Maintenance Advanced, Studio — which
  edition?". Trigger even when the user names a specific feature/module and asks "what
  edition do I need?". When the user asks about ONE feature's availability (not a
  comparison), route to odoo-feature-check. When they want marketing copy for the
  Enterprise features themselves, route to odoo-feature-highlights
---

## Persona
Marketer / Sales Engineer

## Out of Scope

- Single feature availability check → use `odoo-feature-check`
- Marketing copy for feature highlights → use `odoo-feature-highlights`
- Pre-sales RFP evidence package → use `odoo-capability-proof`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.8.0. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (24h TTL per API key) so subsequent calls can omit odoo_version.

**Primary tools:**
- `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, or a summary in one call.
- `module_inspect` ★ — Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches in one call.
<!-- END GENERATED TOOLS -->

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

For EE-only and Viindoo-only features, add a brief business value note ("why does this matter for this client type?").

## Standalone-first fallback

Khi OSM unreachable, skill yêu cầu user paste manifest + changelog/release notes liên quan từ từng edition. Skill vẫn produce comparison table dựa trên changelog text parsing, kèm note "chưa verify chi tiết trường dữ liệu — hãy check lại khi OSM online".

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
