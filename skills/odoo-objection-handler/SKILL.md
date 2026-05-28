---
name: odoo-objection-handler
description: >
  Craft evidence-based responses to client objections about Odoo's capabilities — using the
  ACA framework (Acknowledge / Counter / Affirm) backed by indexed-codebase evidence rather
  than marketing claims. Output includes a ready-to-paste verbatim response paragraph. Use
  this skill ANY time a sales engineer, account executive, or pre-sales consultant needs to
  push back on a doubt or competitive claim about Odoo. Pushy trigger: fire on "handle the
  objection that Odoo can't do X", "counter for the limitation concern about Y", "respond
  to 'Odoo doesn't support Z'", "phản bác lo ngại về tính năng X", "khách hàng nói Odoo
  không làm được", "competitor said SAP/Microsoft does X better", "we heard Odoo doesn't
  handle Y well", "khách phản đối Odoo về…", "prospect doubts Odoo can do multi-level
  approvals", "client says Odoo's reporting is weak — counter for me", "trước buổi meeting
  thứ Sáu, giúp tôi chuẩn bị phản hồi cho lo ngại về…", "RFP scoring tool gave Odoo low on
  X — defend", "competitor pitch said Odoo can't scale beyond 100 users — fact-check",
  "rep is on the call and the client just said 'Odoo's accounting isn't VAS-compliant'",
  "I need a confident answer for Friday's QA session — they'll ask about lot tracking".
  Trigger especially when there's an URGENCY signal ("for the meeting today", "client is
  on the call", "RFP due tomorrow"). When the objection requires proof artifacts (code +
  modules + demo steps), route to odoo-capability-proof. When user simply wants to know if
  a feature exists (not defend it), route to odoo-feature-check.
---

## Persona
Sales Engineer / Account Executive

## Out of Scope

- Full evidence package (modules + code + demo steps) → use `odoo-capability-proof`
- Simple feature availability lookup → use `odoo-feature-check`
- Effort estimate & scope for proposal → use `odoo-gap-analysis`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.8.0. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` — Pin Odoo version for the session (24h TTL per API key) so subsequent calls can omit odoo_version.

**Primary tools:**
- `check_module_exists` — Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, or a summary in one call.
- `suggest_pattern` — Find curated Odoo design patterns from the catalogue with gotchas and anti-patterns.
<!-- END GENERATED TOOLS -->

## Context

Client objections about Odoo capabilities fall into four categories:
1. **False** — the feature exists and works well. Counter with evidence.
2. **Partially true** — standard coverage is limited; custom development closes the gap easily.
   Frame as "standard practice, not a gap."
3. **True but mitigated** — Odoo doesn't support it natively, but an OCA module, Viindoo module,
   or well-established integration pattern exists.
4. **True and significant** — honestly acknowledge and propose the workaround or alternative.

**Never fabricate capabilities.** Intellectual honesty builds more long-term trust than overselling.
If the objection is valid, say so clearly and pivot to how the gap is handled in practice.

**Viindoo advantage cases:** Many objections about "Odoo lacks X for Vietnamese market" are
countered by Viindoo-specific modules (`viin_*`) that cover VAS accounting, Vietnamese HR/payroll,
Vietnamese tax/e-invoice compliance — things Odoo CE/EE doesn't have.

**Data priority:** MCP tool results determine whether the objection is True, False, or Partially
true. If `check_module_exists` or `find_examples` confirms a feature exists but training knowledge
was uncertain, use the MCP result to counter the objection with confidence.

**Framework — ACA:**
- **A**cknowledge: validate the concern as a legitimate question, not a attack
- **C**ounter: present evidence-backed response
- **A**ffirm: close with confident capability statement or honest workaround

## Instructions

**Round 0 — Pin the version:** `set_active_version(odoo_version=…)`.

**Round 1 — Parallel:** Call `check_module_exists` + `find_examples` +
`model_inspect(model=…, method='fields')` simultaneously. All three are independent —
`find_examples` uses the objection text as its semantic query and doesn't need the module
check result; `model_inspect` uses the known model name from training knowledge or the
objection text.

**Round 2 (conditional):** Call `suggest_pattern` only if Round 1 confirms the feature requires
customization. If the feature exists natively (`check_module_exists` returns CE or EE hit),
skip `suggest_pattern` entirely.

The "Suggested response (verbatim)" section should be ready to use in a client meeting without
editing. Keep it professional but conversational.

## Standalone-first fallback

Khi OSM unreachable, skill yêu cầu user cung cấp objection text chi tiết + context khách hàng (industry, Odoo version). Skill vẫn generate ACA response dựa trên training knowledge về Odoo capabilities, mô hình phổ biến, và pattern quen thuộc, kèm caveat "chưa verify qua codebase — hãy fact-check evidence khi OSM online".

## Output format

```
## Objection Response: "<objection>"

### Acknowledge
<1 sentence acknowledging the concern as a legitimate question>

### Counter-evidence
| Evidence type | Detail | Source |
|--------------|--------|--------|
| Module exists | `<module_name>` — <edition> | `check_module_exists` |
| Code example | <description of what it demonstrates> | `find_examples` |
| Key fields | `<field1>`, `<field2>` on `<model>` | `model_inspect` |
| Extension pattern | <pattern name, ~N days effort> | `suggest_pattern` |

### Talking points
1. <concrete talking point backed by evidence>
2. <concrete talking point>
3. <concrete talking point>

### If partial support (honest workaround)
**What standard covers:** <...>
**What requires customization:** <...>
**Effort estimate:** <N days> using <pattern>
**Who has done it:** <reference to existing implementation if found>

### Suggested response (verbatim)
"<Ready-to-use client-facing paragraph. Professional, confident, honest.>"
```

## Examples

**Example 1:**
Prompt: "handle the objection that Odoo doesn't support complex approval workflows"
Output: Counter-evidence citing `approval` module (EE) or `mail.activity.mixin` pattern (CE
extension); code example of multi-level approval; talking points; verbatim response.

**Example 2:**
Prompt: "khách hàng nói Odoo không có kế toán theo chuẩn Việt Nam (VAS)"
Output: Counter: Viindoo `viin_account_vat` + `l10n_vn` modules exist;
`model_inspect(model='account.move', method='fields')` shows VAS-specific fields; verbatim
response in Vietnamese noting Viindoo Enterprise solution.
