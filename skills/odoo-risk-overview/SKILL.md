---
name: odoo-risk-overview
description: >
  Produce an executive-level risk overview of an organization's Odoo customizations — where
  technical debt and upgrade risk are concentrated. Use this skill for: give me a risk overview of
  our Odoo customization, what's the upgrade risk for our system, business risk report for Odoo
  changes, tổng quan rủi ro customization Odoo, báo cáo rủi ro upgrade, chúng ta có bao nhiêu rủi
  ro khi nâng cấp Odoo, đánh giá rủi ro trước khi thay đổi hệ thống. Trigger for any C-level
  or manager question about Odoo health, upgrade readiness, or "how risky is it to change X".
---

## Persona
CEO / CTO / Project Sponsor

## MCP tools
`find_deprecated_usage`, `impact_analysis`, `check_module_exists`, `resolve_model`

## Context

Executives need a high-signal risk picture without reading code. The risk picture has three
dimensions:
1. **Upgrade risk** — how many deprecated APIs will break when upgrading to a newer version
2. **Change blast radius** — how many places in the system are affected when a key field/model
   is modified
3. **Dependency health** — whether custom modules depend on third-party or platform-specific
   features that may disappear

**Risk levels:**
- **Low** — 0–2 deprecated APIs, no high-impact fields, all dependencies stable
- **Medium** — 3–10 deprecated APIs, or 1–2 high-impact fields, manageable migration
- **High** — 10+ deprecated APIs, or critical business field with wide blast radius, requires
  dedicated migration project

**Version era multiplier:** Migrating across era boundaries amplifies risk:
- Within same era (e.g. v16→v17): Low multiplier
- Cross-era (e.g. v12→v16, crosses v13 `@api.multi` removal + v14 OWL-becomes-primary migration): Medium multiplier
- OpenERP to modern (v8/v9→v12+): Very High multiplier (Python 2→3, full rewrite required)

Viindoo note: `viin_*` modules are maintained by Viindoo for each major version. Risk for
Viindoo modules is generally lower than truly custom modules — flag them separately.

**Data priority:** MCP tool results are ground truth for deprecated API counts and blast radius.
Use training knowledge for interpreting business impact and recommending remediation approaches.

## Instructions

Use parallel MCP calls — steps 1, 2, and 3 are fully independent. Fire them simultaneously.

**Round 1 — Parallel:** Call `find_deprecated_usage` + `impact_analysis` (on highest-usage
custom fields known from context) + `check_module_exists` (for all custom module dependencies)
all at once. None of these depend on each other's results.

**Round 2:** Call `resolve_model` on the most heavily customized models identified from Round 1
results. If hotspot models are already known from the user's context, include `resolve_model`
calls in Round 1 as well to reduce to a single round.

Focus `impact_analysis` on fields referenced by many other modules (high `used_by` count).
Count BREAKING vs WARN severity from `find_deprecated_usage` results.

Synthesize findings into a concise executive table. Keep prose minimal — let the table carry
the data. Always close with a one-sentence recommended action tied to the highest-risk item.

## Output format

```
## Odoo Customization Risk Overview

**Assessment date:** <date>
**Current Odoo version:** <version>
**Target upgrade version:** <version or "Not specified">
**Modules assessed:** <N>

| Module | Type | Deprecated APIs | High-impact fields | Upgrade risk | Priority |
|--------|------|:---------------:|:------------------:|:------------:|:--------:|
| ...    | Custom/Viindoo | ... | ... | Low/Med/High | 1/2/3 |

### Key findings
- <finding 1 — most important risk with module name>
- <finding 2>
- <finding 3>

### Risk summary by category
- **Upgrade risk (deprecated APIs):** <Low/Med/High> — <N> BREAKING issues across <N> modules
- **Change blast radius:** <Low/Med/High> — <field/method> affects <N> downstream points
- **Dependency health:** <Low/Med/High> — <N> dependencies unverified in target version

### Version migration complexity
<Low/Medium/High/Very High> — <rationale based on era and version gap>

### Recommended action
<One concrete, specific sentence: "Prioritize migration of `module_x` before the v17 upgrade window
because it has N breaking changes in core method Y.">
```

## Examples

**Example 1:**
Prompt: "give me a risk overview of our Odoo customization before we upgrade to v17"
Output: Table of custom modules with deprecated API counts, blast radius for critical fields,
migration complexity note (e.g. from v16 = Low multiplier), recommended action.

**Example 2:**
Prompt: "tổng quan rủi ro trước khi chúng tôi nâng cấp từ Viindoo 14 lên 17"
Output: Phân tích rủi ro cho từng module `viin_*` vs custom modules, xác định module nào cần
migration chuyên sâu (v13 `@api.multi` removal + v14 OWL-becomes-primary + v15 OWL 2.0), ước
tính timeline và recommended action bằng tiếng Việt.
