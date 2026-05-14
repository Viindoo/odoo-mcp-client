---
name: odoo-gap-analysis
description: >
  Perform a structured gap analysis comparing client requirements against Odoo standard
  functionality, producing a concrete effort matrix. Use this skill for: gap analysis for client
  requirements, what needs to be customized, standard vs custom feature map, phân tích gap giữa
  yêu cầu và Odoo standard, tính năng nào cần custom, scoping workshop for Odoo implementation,
  estimate customization effort, what's out of the box vs needs development. This is the core
  consulting deliverable for presales scoping. Trigger whenever someone lists requirements and
  asks what Odoo covers — even informally. Also trigger for: project estimate, scope for project
  estimate, ước lượng customization, scope cho estimate, before we give the project estimate,
  effort matrix for proposal.
---

## Persona
Consultant / Project Manager

## MCP tools
`check_module_exists`, `resolve_model`, `find_examples`, `lookup_core_api`, `suggest_pattern`

## Context

Gap analysis is the most important consulting deliverable — it sets client expectations and
determines project budget. Errors in either direction are costly:
- Under-estimating gaps → budget overruns, unhappy clients
- Over-estimating gaps → losing deals, recommending custom dev for standard features

**Effort classification:**
- **Standard** — exists in CE or EE, zero development needed. Mention if EE license required.
- **Configuration** — standard module exists but requires setup (multi-company, tax config,
  workflow rules). < 1 day effort.
- **Extension** — existing model/method can be extended with `_inherit`. Standard ORM extension
  patterns apply. 1–5 days per requirement.
- **Custom** — no standard module; requires new model, complex logic, or integration.
  5+ days per requirement.

**Viindoo caveat:** Before classifying as "Custom", check Viindoo modules (`viin_*`) — they often
cover Vietnamese-specific requirements (VAS accounting, labor law, tax) that Odoo CE/EE doesn't.

**Version matters:** A feature classified "Custom" on v12 may be "Standard" on v16. Always note
the target version. For v8/v9 migrations, effort is higher — Python 2 syntax, `_columns` dict,
`osv.osv` all need full rewrites.

**Data priority:** MCP tool results are ground truth for Standard vs Custom classification.
If `check_module_exists` says a module doesn't exist but training knowledge says it should,
trust the MCP result. Use training knowledge only for effort estimation and business context.

## Instructions

Use parallel MCP calls to minimize latency — a gap analysis covering 10+ requirements can
complete in 3 rounds instead of 30+ sequential calls.

**Round 1 — Parallel:** Call `check_module_exists` for ALL requirements simultaneously.
Each call is independent; there is no reason to wait for one before firing the next.

**Round 2 — Parallel:** For all requirements where coverage is partial (module exists but incomplete),
call `resolve_model` on each relevant model simultaneously. These calls don't depend on each other.

**Round 3 — Parallel:** For all Extension/Custom gap items, call `find_examples` + `lookup_core_api`
+ `suggest_pattern` simultaneously — one batch for all remaining gaps at once.

Decision logic per requirement (applied after Round 1 results arrive):
- Full module match → mark Standard or Config; no further calls needed
- Partial coverage → escalate to Round 2 resolve_model
- No match → mark Custom; queue for Round 3 suggest_pattern + lookup_core_api

**Be conservative**: if in doubt, upgrade the effort tier. It's easier to reduce scope than
explain overruns.

## Output format

```
## Gap Analysis Report

**Client:** <client name or "Client">
**Target Odoo version:** <version>
**Requirements analyzed:** <N>
**Analysis date:** <date>

| # | Requirement | Standard coverage | Module | Effort type | Effort | Notes |
|---|-------------|------------------|--------|-------------|--------|-------|
| 1 | ...         | Full/Partial/None | ...   | Standard/Config/Extension/Custom | S/M/L/XL | ... |

**Effort legend:** S = <1d · M = 1–3d · L = 3–10d · XL = >10d

### Effort summary
- **Standard** (no dev): <N> requirements — <list>
- **Configuration only**: <N> requirements — <list>
- **Extension** (custom field/method): <N> requirements
- **Full custom development**: <N> requirements

### Total estimated effort
**<Low/Medium/High/Very High>**

<Rationale paragraph: what drives the total, which items have highest uncertainty>

### Risk flags
- <Item at risk of scope creep or hidden complexity>

### Recommended phasing
Phase 1 (must-have): ...
Phase 2 (nice-to-have): ...
```

## Examples

**Example 1:**
Prompt: "gap analysis for a client who needs multi-company invoicing, approval workflows, and a
custom loyalty program"
Output: Multi-company invoicing → Standard (CE) S; Approval workflows → Extension M (using
`mail.activity.mixin`); Custom loyalty → Custom XL. Total effort: Medium. Suggested phasing.

**Example 2:**
Prompt: "phân tích gap cho khách hàng sản xuất, cần MRP, kế hoạch sản xuất theo lô, và tích hợp
máy CNC qua IoT"
Output: MRP → Standard CE; Lô sản xuất → Standard CE (lot/serial tracking); IoT CNC integration
→ Custom XL (EE IoT module exists nhưng custom adapter cần thiết). Total effort: High.
