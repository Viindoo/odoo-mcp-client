---
name: odoo-gap-analysis
description: >
  Produce a structured gap analysis comparing client requirements against Odoo standard
  functionality, ending in a concrete effort matrix (Standard / Configuration / Extension /
  Custom + S/M/L/XL day estimates) ready to paste into a proposal. Use this skill ANY time
  someone is about to quote, scope, or estimate an Odoo project — even if they don't say the
  word "gap". Pushy trigger: if the conversation contains a list of customer requirements +
  any hint of "what does Odoo do natively?" / "what needs to be built?" / "how many days?" /
  "what should we charge?", fire this skill. Realistic phrases to catch include "khách yêu
  cầu A, B, C — Odoo có sẵn không?", "tính năng nào cần custom?", "trước khi báo giá cho
  prospect này, cái gì là standard, cái gì cần dev?", "before we send the project estimate
  on Monday, can you tell me what's out of the box?", "scope cho proposal", "ước lượng
  customization effort", "client wants multi-company invoicing + approval workflows + a
  custom loyalty program — what's the breakdown?", "phân tích gap cho khách sản xuất với
  MRP và lô…", "is this in standard Odoo or do we need to build it?", "list of features →
  effort matrix", "presales workshop notes ready, can you turn into a gap report?", "the
  RFP mentions 23 requirements — help me classify them". When the user asks about ONE
  specific feature ("does Odoo have lot tracking?") route to odoo-feature-check instead.
  When they want highlights for marketing copy ("what's the headline value of v18?")
  route to odoo-feature-highlights
---

## Persona
Consultant / Project Manager

## Out of Scope

- Single feature availability check → use `odoo-feature-check`
- Marketing highlights for version release → use `odoo-feature-highlights`
- Source-level API diff between versions → use `odoo-version-diff`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.11.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Session bootstrap** (call once at session start):
- `set_active_profile(profile_name='viindoo-internal')` — Pin tenant profile for the session so subsequent calls scope to one customer profile.
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (24h TTL per API key) so subsequent calls can omit odoo_version.

**Primary tools:**
- `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `lookup_core_api` — Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, or a summary in one call.
- `suggest_pattern` — Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
<!-- END GENERATED TOOLS -->

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

**Round 0 — Pin the version (once):** `set_active_version(odoo_version=…)` so every
subsequent call inherits it.

**Round 1 — Parallel:** Call `check_module_exists` for ALL requirements simultaneously.
Each call is independent; there is no reason to wait for one before firing the next.

**Round 2 — Parallel:** For all requirements where coverage is partial (module exists but
incomplete), call `model_inspect(model=…, method='fields')` on each relevant model
simultaneously. One call returns fields + methods + views + inheritance chain.

**Round 3 — Parallel:** For all Extension/Custom gap items, call `find_examples` +
`lookup_core_api` + `suggest_pattern` simultaneously — one batch for all remaining gaps at
once.

Decision logic per requirement (applied after Round 1 results arrive):
- Full module match → mark Standard or Config; no further calls needed
- Partial coverage → escalate to Round 2 model_inspect
- No match → mark Custom; queue for Round 3 suggest_pattern + lookup_core_api

**Be conservative**: if in doubt, upgrade the effort tier. It's easier to reduce scope than
explain overruns.

## Standalone-first fallback

Khi OSM unreachable, skill yêu cầu user cung cấp danh sách requirement + bất kỳ context khách cung cấp (workshop notes, RFP). Skill vẫn tạo gap analysis report dựa trên training knowledge Odoo (classify requirement thành Standard/Config/Extension/Custom dựa trên mô hình cơ sở), kèm effort estimate dựa trên heuristic, và caveat "chưa verify qua code examples — hãy double-check effort khi OSM online".

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
