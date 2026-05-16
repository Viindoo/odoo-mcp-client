---
name: odoo-feature-check
description: >
  Quickly determine whether a client requirement is covered by standard Odoo functionality —
  and at what edition level (CE, Odoo EE, or Viindoo EE). Use this skill for: does Odoo have
  module X built-in, check if feature Y exists in standard, is this available out of the box,
  Odoo có sẵn tính năng X không, module X có trong Odoo CE không, tính năng này có cần custom
  không, what does standard Odoo cover for requirement Z. Trigger any time a consultant or
  developer needs to know "is this standard or custom" — even if the question is informal.
  Prevents the expensive mistake of recommending custom development for features that already exist.
  Also trigger for: tính năng X có trong Odoo không, có trong Odoo standard không, feature X có
  trong Odoo CE không, does Odoo standard have X built-in.
---

## Persona
Consultant / Developer

## MCP tools
`check_module_exists`, `describe_module`, `resolve_model`, `find_examples`, `suggest_pattern`

## Context

Standard Odoo coverage exists at four levels:
1. **CE native** — free, zero customization needed
2. **Odoo EE only** — requires paid Odoo Enterprise subscription
3. **Viindoo EE** — available via Viindoo Enterprise, may overlap with Odoo EE
4. **Community App Store** — third-party OCA or Viindoo modules (note: not officially supported)

Version matters — a feature in v17 may not exist in v12. Always ask or infer the target version.

For v8/v9 (OpenERP era): module names and features differ significantly. The `sale` module in v8
has a very different field set than v16. When checking features for legacy versions, note that
many "new" features in v12+ didn't exist at all in v8/v9.

Viindoo note: Viindoo modules prefixed `viin_` cover many Vietnamese-specific requirements
(VAS accounting, Vietnamese tax, HR Vietnamese labor law) that neither CE nor Odoo EE provide.

**Data priority:** When `check_module_exists` result conflicts with training knowledge about
whether a feature exists, trust the MCP result. MCP reflects the indexed codebase; training
data about specific Odoo module names and versions is frequently outdated.

## Instructions

**Round 1 — Parallel:** Call `check_module_exists` + `find_examples` simultaneously.
`find_examples` takes a semantic query from the requirement text and does not need the
module check result. Both are independent — fire together.

**Round 2 — Parallel (after Round 1):** Call `resolve_model` (needs module/model name from
Round 1) + `suggest_pattern` simultaneously. `suggest_pattern` can be formulated from the
requirement even if Round 1 shows partial coverage — they are independent of each other.

**Round 3 — Deep dive (when `check_module_exists` confirms presence):** Call
`describe_module(name=<module_name>, odoo_version=<version>)` to surface the module's full
architecture: manifest summary, which models it defines vs extends, view count, and JS patch
count. This gives the consultant a confident, evidence-backed answer about what the module
actually covers — beyond the bare "exists / does not exist" signal. If the module is confirmed
to exist, also consider drilling into specifics with `list_fields` or `list_views` in a
subsequent call if the client asks about exact field coverage.

**Verdict levels:**
- `Available in CE` — standard, zero cost
- `Available in Odoo EE only` — requires Enterprise subscription
- `Available in Viindoo EE` — available via Viindoo commercial
- `Partial — standard covers X, custom needed for Y` — specify the gap precisely
- `Not available — custom development required` — honest assessment with effort note

Always cite the exact module name so clients can verify independently.

## Output format

```
## Feature Availability Check

**Feature requested:** <feature description>
**Odoo version:** <version>

| Feature aspect | CE | Odoo EE | Viindoo EE | Module | Notes |
|---------------|:--:|:-------:|:----------:|--------|-------|
| ...           | ✓/✗ | ✓/✗ | ✓/✗ | ...  | ...   |

### Verdict
**<Available in CE / Available in EE only / Available in Viindoo EE / Partial / Not available>**

### Evidence
- **Module:** `<module_name>`
- **Primary model:** `<model_name>`
- **Module scope:** <N> models defined, <N> models extended, <N> views, <N> JS patches (from describe_module)
- **Key fields:** `<field1>`, `<field2>` — <what they implement>
- **Example:** <brief description from find_examples>

### Custom development needed (if partial)
- **Gap:** <what standard doesn't cover>
- **Extension pattern:** <from suggest_pattern>
- **Estimated effort:** <S/M/L>

### Recommendation
<1–2 sentences for the client>
```

## Examples

**Example 1:**
Prompt: "does Odoo have a subscription billing module built in?"
Output: Feature table showing `sale_subscription` exists in EE only (not CE), key model
`sale.order` with `subscription_id` field, verdict "Available in Odoo EE only", plus note that
Viindoo has `viin_sale_subscription` covering similar needs.

**Example 2:**
Prompt: "Odoo 17 có sẵn module quản lý tài sản cố định không?"
Output: `account_asset` exists in EE, not CE. Viindoo EE has `viin_account_asset`. Resolve model
shows key fields. Recommendation in Vietnamese context.
