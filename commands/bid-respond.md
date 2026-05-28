---
name: odoo-bid-respond
description: |
  Generate a complete Odoo bid response package from raw prospect input. Chains discovery synthesis → gap analysis → capability proof → objection pre-empt → proposal draft. Invoke when responding to an RFP, proposal request, or post-discovery synthesis needs
---
# /odoo-bid-respond

Command-level recipe (depth 0) that transforms raw prospect input - pasted email, meeting notes, or a requirements list - into a complete, ready-to-send bid response package: customer profile, effort matrix, capability evidence, counter-talking-points, and a draft proposal document.

## When to use

Type `/odoo-bid-respond` immediately after receiving any prospect communication that requires a structured response: an RFP, a "can Odoo do X?" email, post-demo follow-up notes, or a shortlist questionnaire. Optional `$ARGUMENTS` = a short customer label (e.g., `Customer-A`, `CustomerA`). If omitted, the command prompts for one.

This command is a recipe, not a single skill. It chains five downstream skills in sequence, gating each phase with explicit user approval. Each gate keeps you in control: wrong direction? Edit the draft before advancing. OSM unreachable? The command degrades gracefully (see Standalone fallback).

## Hard rules

1. **Phase gate mandatory.** Each phase ends with a binary gate shown to the user. The command MUST NOT advance to the next phase until the user explicitly confirms (yes / y / proceed). On "edit" the agent revises the current phase output inline. On "cancel" the agent stops and reports progress so far.
2. **Context check.** At startup, check for `.odoo-ai/context.md` in the working directory. If found, load it as project context. If missing, suggest the user run `/odoo-onboard` first, then allow them to continue with manually supplied context.
3. **Abstract labels.** Use the customer label provided by the user (or the default "Customer-A") throughout all internal summaries and the saved document. Never log real company names, contact names, or pricing in any file committed to this repo.
4. **Skill invocation via natural language.** Each phase instructs the main agent to produce a natural-language prompt whose phrasing auto-fires the target skill via the skill's description match. Do NOT use the Agent tool to invoke skills; the skill harness handles dispatch in the main context.
5. **Agent tool scope.** The main agent MAY use the Agent tool only for `odoo-coder` or `odoo-code-reviewer` bundle invocations when Phase 3 requires technical code evidence. Those subagent prompts MUST include the line: `Do NOT invoke Skill tool. Do NOT spawn sub-agent. Only Read/Grep/Glob/Edit/Write.`
6. **No external writes before gate 5.** Writing files to `.odoo-ai/bids/` happens only after the user confirms Phase 5 output. No side effects before then.
7. **Public repo safety.** This file is in a public repo. No real customer names, deal sizes in currency, or pricing tables in examples or defaults.

## Phases

### Phase 0 — Parse arguments + check context

1. Parse `$ARGUMENTS` for a customer label token. If found, store as `CUSTOMER_LABEL`. If absent, ask: "Customer label (e.g., Customer-A)? [default: Customer-A]". Accept the user's answer or use the default.
2. Check for `.odoo-ai/context.md`:
   - Found → load and summarize its Odoo version + active modules in one line. Confirm: "Using context: <version> / <modules>. Continue? [y/n]"
   - Not found → show warning: "`.odoo-ai/context.md` not found. Consider running `/odoo-onboard` first. Continue manually? [y/n]". On `n`, stop.
3. Collect the following from the user in one message (list all four prompts together so the user can answer in one block):
   - **(a)** Raw prospect input — paste email, meeting notes, or requirements list.
   - **(b)** Target close date (approximate, e.g., "end of Q3 2026").
   - **(c)** Deal size category: **S** (1-5 users, simple), **M** (6-30 users, multi-dept), or **L** (30+ users, enterprise).
   - **(d)** Primary contact role (e.g., IT manager, CFO, CEO) — used to calibrate language register.
4. Store inputs. Proceed to Phase 1.

### Phase 1 — Discovery synthesis

Goal: produce a structured customer profile from the raw prospect input.

Invoke by producing the following natural-language prompt to auto-fire the `odoo-discovery-summarize` skill (or equivalent discovery/summarize skill in the active plugin set):

> "Summarize the customer profile from the following raw input. Identify: industry, size, key pain points (max 5), success criteria (max 3), relevant Odoo modules, and deployment risk. Input: [paste raw prospect input here]"

If the skill is not installed or returns an error, degrade: ask the user to fill in the profile fields manually (see Standalone fallback).

**Phase 1 output (show to user):**

```
CUSTOMER PROFILE — [CUSTOMER_LABEL]
------------------------------------
Industry       : <value>
Size           : <value>
Pain points    : 1. ... / 2. ... / 3. ...
Success criteria: 1. ... / 2. ...
Relevant modules: <list>
Deployment risk : <low|medium|high> — <one-line reason>
```

**Gate 1:** "Is the profile accurate? (yes / edit / cancel)"
- yes → proceed to Phase 2
- edit → revise specific fields inline, re-show, re-gate
- cancel → stop, output progress so far

### Phase 2 — Gap analysis

Goal: produce an effort matrix from the profile's pain points and success criteria.

Use the profile from Phase 1 as input. Invoke by producing the following natural-language prompt to auto-fire the `odoo-gap-analysis` skill:

> "Analyze the gap between [CUSTOMER_LABEL]'s requirements and standard Odoo capabilities. For each pain point and success criterion, classify as: Standard / Config / Extension / Custom. Estimate effort: S (<3 days) / M (3-10 days) / L (10-30 days) / XL (>30 days). Input pain points: [list from Phase 1]. Success criteria: [list from Phase 1]."

**Phase 2 output (show to user as table):**

```
GAP MATRIX — [CUSTOMER_LABEL]
------------------------------------------------------
Requirement         | Type       | Effort | Notes
--------------------|------------|--------|------------------
<requirement 1>     | Standard   | S      | Core module X
<requirement 2>     | Config     | M      | Workflow config
<requirement 3>     | Extension  | L      | Custom field + UI
<requirement 4>     | Custom     | XL     | To quote separately
...
------------------------------------------------------
TOTALS: Standard: N | Config: N | Extension: N | Custom: N
```

Note: Custom items are flagged "to be quoted separately" and excluded from the capability proof phase.

**Gate 2:** "Is the effort matrix accurate? (yes / edit / cancel)"

### Phase 3 — Capability proof

Goal: for each Standard or Config item in the gap matrix, collect concrete evidence (module name, model/field, demo step or screenshot reference).

For each Standard/Config item, invoke by producing:

> "Prove that Odoo supports the requirement: [requirement text]. Provide: module name, relevant model/field, concrete demo steps (max 3). Odoo version: [from context or ask user]."

This auto-fires the `odoo-capability-proof` skill (or `odoo-feature-check` as fallback). Batch all Standard/Config items; show consolidated proof list.

If technical code evidence is needed for an Extension-level item (user requests it), the main agent MAY spawn an odoo-coder subagent:

> Agent tool brief: "Do NOT invoke Skill tool. Do NOT spawn sub-agent. Only Read/Grep/Glob/Edit/Write. Task: generate a minimal Odoo 17 Python snippet demonstrating [capability]. Context: [item context]."

**Phase 3 output:**

```
CAPABILITY PROOF — [CUSTOMER_LABEL]
--------------------------------------------
Requirement         | Module          | Evidence
--------------------|-----------------|----------------------------------
<requirement 1>     | sale            | sale.order → amount_total; Demo: ...
<requirement 2>     | account         | account.move; Config: journal types
...
Custom items (N):   [list] → "To be quoted separately in commercial proposal"
```

**Gate 3:** "Is the proof package complete? (yes / iterate / cancel)"
- iterate → specify which item needs more evidence; re-run that item only

### Phase 4 — Objection pre-empt

Goal: anticipate 2-3 likely objections from the prospect and prepare counter-talking-points.

Based on the raw prospect input + gap matrix, identify the most probable objections. Common archetypes (adapt to actual input):
- "Odoo lacks enterprise-grade features / missing capability X"
- "No regional data residency / GDPR-class compliance support"
- "Total cost of ownership (TCO) is higher than current solution"
- "Data migration risk from legacy systems"
- "Local implementation capacity / support availability"

For each identified objection (2-3 max), invoke:

> "The prospect objects: [objection text]. Prepare a counter-talking-point: acknowledge the concern, provide concrete evidence, propose a de-risk next step. Tone calibrated to: [primary contact role from Phase 0]."

This auto-fires the `odoo-objection-handler` skill.

**Phase 4 output:**

```
OBJECTION PLAYBOOK — [CUSTOMER_LABEL]
-----------------------------------------
Objection 1: [text]
  Acknowledgment : ...
  Evidence       : ...
  Next step      : ...

Objection 2: [text]
  ...
```

**Gate 4:** "Are the counter-talking-points ready? (yes / edit / cancel)"

### Phase 5 — Assemble proposal draft

Goal: produce the complete bid response document.

Using all Phase 1-4 outputs, compose the full proposal. Structure:

```
1. Cover letter                  — 1 paragraph, addressed to primary contact role
2. Executive summary             — Pain points understood, proposed solution summary
3. Gap matrix table              — Phase 2 output, formatted as Markdown table
4. Capability evidence list      — Phase 3 output, grouped by module
5. Anticipated objection responses — Phase 4 objection playbook, inline
6. Roadmap and cost tier         — Timeline estimate (S/M/L weeks from gap matrix) + cost tier label (S/M/L, NO currency figures)
7. Next steps                    — CTA: book demo / technical workshop / commercial proposal
```

For Extension/Custom items, include a note: "Custom development items will be quoted separately after technical scope confirmation."

**Phase 5 output:** Show full draft inline (collapsible if long). Confirm close date and cost tier label are consistent with Phase 0 inputs.

**Gate 5:** "Is the proposal ready to send? (yes — save file + export / iterate / cancel)"
- iterate → specify section to revise; re-draft that section only, re-gate

### Phase 6 — Output

On user confirming Gate 5:

1. Determine output path: `.odoo-ai/bids/<CUSTOMER_LABEL>-<YYYY-MM-DD>.md` (use today's date). Create directory if needed.
2. Write the proposal file using the Write tool.
3. Print the full proposal to terminal for user copy-paste.
4. Show summary line:

```
Bid response saved: .odoo-ai/bids/<CUSTOMER_LABEL>-<YYYY-MM-DD>.md
Next step: review + send manually. /odoo-bid-respond does NOT send emails.
```

Note: `.odoo-ai/` should be in `.gitignore`. If not, remind the user to add it before committing.

## Standalone fallback

If any skill invocation fails (OSM unreachable, skill not installed, network timeout):

1. Note the failure inline: "[Skill name] unavailable. Continuing with manual input."
2. Show the expected output template for that phase as an empty form.
3. Ask the user to fill in the blanks directly in the conversation.
4. Mark all manually supplied items as `[unverified — manual input]` in the proposal output.
5. Continue to the next phase as normal.

The proposal is still produced; unverified items are clearly flagged so the user knows which claims need additional substantiation before sending.

## Examples

### Example 1 — SME distribution company (deal size M)

**User types:**
```
/odoo-bid-respond Customer-A
```

**Phase 0:** Command reads no `.odoo-ai/context.md`. User confirms manual mode. User pastes email: "We are looking for a solution to manage sales, warehouse, and accounting for 15 employees. Currently using Excel. Need regional e-invoice compliance support."

Phase 0 collects: close date Q4 2026, size M, primary contact CFO.

**Phase 1 output (summary):**
- Industry: Distribution
- Pain points: Manual Excel, no warehouse automation, no e-invoice compliance
- Success criteria: E-invoice compliance, real-time inventory reporting
- Relevant modules: sale, stock, account, l10n_*
- Risk: medium - Excel data migration

**Gate 1:** User confirms.

**Phase 2 output (excerpt):**
| Requirement | Type | Effort |
|---|---|---|
| Sales management | Standard | S |
| Regional e-invoice compliance | Config | M |
| Real-time inventory reporting | Standard | S |

**Gate 2-5:** User confirms each. Final proposal written to `.odoo-ai/bids/Customer-A-2026-05-28.md`.

---

### Example 2 — Manufacturing prospect, objection-heavy (deal size L)

**User types:**
```
/odoo-bid-respond Customer-B
```

User pastes meeting notes raising objections: "Odoo MRP is not as strong as SAP, concerns about regional data residency / GDPR-class compliance, and total implementation cost."

**Phase 4 objections identified:**
1. "MRP not strong enough compared to SAP"
2. "Regional data residency / GDPR-class compliance"
3. "High TCO"

`odoo-objection-handler` fires for each. Counter-talking-points:
- MRP: mrp + quality + maintenance modules; reference manufacturing customer (abstract: Customer-ref-1).
- Regional data residency: Odoo 17 data residency + consent fields; consider managed-hosting options for compliance-sensitive regions.
- TCO: 3-year TCO model vs. legacy - license + implementation + support tier.

Final proposal includes all three rebuttals inline.

## What this command does NOT do

- Does NOT send emails. Phase 6 saves a draft file; the user sends it manually.
- Does NOT access or modify Odoo source code, CRM databases, or live ERP instances.
- Does NOT persist prospect data across sessions. Re-run from Phase 0 in a new session if needed (or supply `.odoo-ai/context.md` as a warm-start).
- Does NOT replace human judgment on commercial pricing, discount authority, or go/no-go strategic decisions.
- Does NOT guarantee OSM tool availability. All phases degrade gracefully to manual input when OSM is unreachable.
