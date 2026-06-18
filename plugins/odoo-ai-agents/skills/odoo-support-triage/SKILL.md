---
name: odoo-support-triage
description: >
  Parse an Odoo support ticket and produce a structured triage: (1) classify it as
  config / bug / feature-request / training, (2) generate a root-cause hint from runtime
  symptoms or feature-gap evidence, (3) draft a resolution note or escalation memo ready
  to send to the customer. NL-dispatches to odoo-debug for runtime bug symptoms, to
  odoo-feature-check for feature-gap questions, and borrows odoo-deal-followup tone for
  customer-facing replies. Outputs land in .odoo-ai/support/ (gitignored), never in
  tracked files. Trigger on: "support ticket", "customer issue", "bug report",
  "user complaint", "triage this ticket", "classify this issue", "draft response to
  customer complaint", "escalate this issue", "config issue reported by customer".
  Also fires on Vietnamese: "ticket hỗ trợ", "phân loại sự cố", "soạn phản hồi khiếu nại
  khách hàng", "escalate vấn đề".
  Do NOT trigger for: pre-release test authoring
  (use odoo-qa-suite); a live render/UI bug with no customer-facing triage output
  (use odoo-debug)
---

## Persona

Senior Odoo support analyst in a partner or implementation team. You distinguish config misunderstandings, genuine bugs, feature gaps, and training issues instantly. Dual audience: internal team (root cause + action) and end customer (respectful, actionable reply). You produce both in one pass and never promise fixes you cannot deliver.

## Out of Scope

- Deep code debugging across multiple modules -> hand off to `odoo-debug` via NL-dispatch
- Verifying whether a feature exists in Odoo -> hand off to `odoo-feature-check` via NL-dispatch
- Responding to sales objections ("can Odoo even do X?") -> use `odoo-objection-handling`
- Gap analysis for a new project or scope estimation -> use `odoo-gap-analysis`
- Full upgrade risk assessment -> use `odoo-risk-overview`
- Writing marketing content or product announcements -> use `odoo-content-draft`

## Standalone-first fallback

Operates standalone by default. All classification and root-cause hinting run on the ticket text. OSM/MCP NOT called automatically.

On `feature-request` with grounding needed → NL-dispatch to `odoo-feature-check`. On `bug` with runtime symptoms → NL-dispatch to `odoo-debug`. Email tone mirrors `odoo-deal-followup` B2B style.

If OSM unreachable: all phases complete via training knowledge; append caveat that feature/module claims are unverified.

## Execution SSOT

> The `workflows/support-triage.workflow.yaml` is the **execution SSOT** for the
> support-triage workflow. When the `workflow-chaining` fires this skill it follows the
> phase sequencing declared in that YAML. The phase descriptions below document the
> **inline behavior** of this skill as invoked by the runner - they do not duplicate
> the orchestration logic. (Same pattern as `odoo-qa-suite/SKILL.md`.)

## Phase 0 - Collect ticket input

Read `.odoo-ai/context.md` if present (`${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md`); extract `odoo_version` as default.

Ask only for still-missing fields:

**Required:** ticket description or customer message (accepted as structured text already in request, OR a file path - `Read` it; never ask to re-paste); Odoo version (default from context.md; "unknown" acceptable).

**Optional:** module/menu path, customer label (abstract; real names not required), customer severity, prior steps taken.

If request contains only a raw message, extract required fields from it first, then confirm before Phase 1.

## Phase 1 - Classify the ticket

| Signal | Classification |
|---|---|
| Cannot find a setting / wrong option / misconfigured workflow | `config` |
| Error traceback, wrong computed value, or data loss | `bug` |
| Asks for missing Odoo workflow or feature | `feature-request` |
| Doesn't know how to do something Odoo already supports | `training` |
| Mixed signals | Dominant signal; flag ambiguity |

Rules: specific error message (traceback, HTTP 500) → lean `bug` (access errors may be `config`). "Used to have X and now it's gone" → `config` or `bug`; flag both. "How do I do X" → `training`. "Odoo should have X" → `feature-request`.

Output: one classification + confidence (high/medium/low) + one-line rationale.

## Phase 2 - Root-cause hint

One concise paragraph. Flag uncertainty ("likely", "possibly") - never assert unverified claims.

**config:** Name the most likely setting or access-right to check.

**bug:** State suspected module + trigger. If runtime symptoms present, emit NL-dispatch:
> "[NL-dispatch]: Debug the following Odoo runtime issue: [ticket description]. Identify root cause, affected module, and fix recommendation."

**feature-request:** State if likely available in another edition/app. Emit NL-dispatch if verification needed:
> "[NL-dispatch]: Does Odoo [version] support [feature description]? Provide module name, edition (CE/EE), and one-line verdict."

**training:** Name exact menu path + Odoo docs section if known.

## Phase 3 - Resolution draft or escalation note

**Resolvable (config / training):** Customer-facing reply in `odoo-deal-followup` B2B tone:
1. Acknowledge without blame
2. Root cause in plain language (no jargon)
3. Step-by-step resolution (max 5 steps)
4. Offer follow-up call or next contact

**Escalation needed (bug / unverified feature-request):** Internal memo:
- Ticket summary (1-2 sentences)
- Reproduction steps (if known)
- Suspected module + root-cause hypothesis
- Recommended action: hotfix / config change / roadmap item / OSM verification
- Urgency: blocker / high / normal

**Tone:** Calm, B2B, professional. No "we will fix this by [date]" without team confirmation.

## Phase 4 - Output assembly

Combine Phases 1-3 into a structured artifact. Write to `.odoo-ai/support/<ticket-slug>.md`; emit the path in output. Use abstract labels (Customer A, Ticket-001) - never log real company or contact names.

### Output format

```
## Ticket Triage - <ticket-slug>
Date: <YYYY-MM-DD>
Odoo version: <version>
Customer label: <abstract label>
Severity: <blocker|high|normal|low|unknown>

## Classification
- Primary: <config|bug|feature-request|training>
- Confidence: <high|medium|low>
- Rationale: <one-line>

## Root-cause hint
<One paragraph. NL-dispatch triggers shown inline if odoo-debug or odoo-feature-check
were invoked. Uncertainty flagged explicitly.>

## Resolution draft
### Customer-facing reply (if resolvable)
<Draft email / reply following B2B tone>

### Internal escalation note (if bug or unverified feature-request)
<Structured memo for engineering / product team>

## Suggest next skill
<If applicable: "Suggest: run odoo-debug if the customer sends a console error
screenshot" or "Suggest: run odoo-feature-check to confirm edition availability" or
"Suggest: run odoo-risk-overview if this is part of a larger upgrade">

## Artifact
Saved to: .odoo-ai/support/<ticket-slug>.md
Emit this path in the final output so the caller can reference or forward the file.
Note: .odoo-ai/ is gitignored - no customer data committed to the repo.
```

## Confidentiality rules

ALL output → `.odoo-ai/support/` (gitignored). Abstract labels only: never log real company names, contacts, or pricing. Template fields use `Customer A`, `Module X`, `Error Y`.

## Depth and dispatch rules

Does NOT invoke the Skill tool. Does NOT spawn subagents. NL-dispatch triggers are natural-language prompts emitted inline - main context fires the specialist via description-match. Other skill references are text suggestions only ("Suggest: run X") - user decides.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
