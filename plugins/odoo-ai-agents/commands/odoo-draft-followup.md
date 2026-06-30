---
name: odoo-draft-followup
argument-hint: "[deal/customer]"
description: |
  Draft a follow-up email for a stalled or at-risk deal. Wraps the odoo-deal-followup skill with explicit save-to-disk step. Type this slash command when you have a specific deal needing a follow-up email today
---
# /odoo-draft-followup

Single-purpose slash command for sales follow-up email drafting. Chains the `odoo-deal-followup` skill with an explicit save-to-file step, gating on user approval before writing to disk.

## When to use

Invoke when you have a stalled or at-risk deal and need a follow-up email **today**. The skill analyzes deal context, assesses risk, suggests a next-best action, then drafts an email for review before sending.

Type: `/odoo-draft-followup [customer-label]`

Optional: supply customer label on the command line (e.g., `Customer A`). If omitted, the command will prompt you for it.

## Hard rules

- **Read context first**: Check `.odoo-ai/context.md` for CRM metadata and pipeline rules before drafting. This ensures the drafted email aligns with your deal context.
- **Use what the caller already gave, then ask only for gaps**: deal details are usually already in the request (orchestrator structured data, or the sales user stating it) or in `.odoo-ai/context.md`. Never make a human retype what is present. Optionally enrich from a live CRM/ERP/email integration if one exists - but never assume one; this command must work for an agent with only the request text and local files. Ask **only** for fields still unresolved:
  - Customer label or short name (e.g., "ABC Manufacturing")
  - Last touch date - only if not already provided
  - Current pipeline stage - only if not already provided
  - Prior commitments or blockers (e.g., "waiting on PO", "evaluating competing offer")
- **Gate before saving**: Display the drafted email to the user. Explicitly ask: "Email draft OK? (yes / iterate / cancel)". Do not write to disk unless the user confirms "yes".
- **No auto-send**: This command **only drafts**. It does not send email, update CRM systems, or trigger workflows.

## Phases

### Phase 0: Parse inputs and gather deal context
1. Parse `$ARGUMENTS` for an optional customer label.
2. Read `.odoo-ai/context.md` to load CRM metadata, pipeline rules, and any standing objection handlers.
3. Pull deal details already present in the invocation context (caller-provided data, prior conversation) and pre-fill everything available. Optionally enrich from a live CRM/email integration only if one exists - never assume it.
4. If the customer label is still unknown, ask: "Customer name or label?" Ask for any remaining unresolved field (last touch, stage, blockers) in a single batched message - never for data already supplied.

### Phase 1: Trigger odoo-deal-followup skill
Invoke the `odoo-deal-followup` skill via natural-language prompt. Supply:
- Customer label, last touch date, pipeline stage, prior commitments.
- Request: risk score + next-best-action recommendation + draft email (tone: professional, warm, concise).

The skill outputs:
- **Risk score**: LOW / MEDIUM / HIGH (how likely is this deal to churn or stall further?)
- **Next-best-action**: specific action the customer or you should take next (e.g., "schedule call", "send spec sheet", "escalate to manager").
- **Draft email**: 3-5 paragraph follow-up email, subject line included, ready for review.

### Phase 2: Display and gate
Show the draft to the user in a readable format:
```
Subject: [subject line from draft]

[email body]

---
Risk Score: [MEDIUM]
Next-Best-Action: [Schedule a 30-min call next week]
```

Ask explicitly: **"Email draft OK? Reply with `yes` to save, `iterate` to refine, or `cancel` to discard."**

- **`yes`** → Phase 3.
- **`iterate`** → Ask what to change (tone, specifics, objection, next action), invoke skill again with updated context, loop back to Phase 2.
- **`cancel`** → End command, discard draft.

### Phase 3: Write to disk and confirm
On user "yes":
1. Create directory `.odoo-ai/followups/` if it does not exist.
2. Slugify customer-label: lowercase, replace whitespace and non-alphanumeric with `-`, collapse repeats. Example: `ABC Manufacturing` → `abc-manufacturing`.
3. Derive filename: `<slugified-customer-label>-<YYYY-MM-DD>.md` (e.g., `abc-manufacturing-2026-05-28.md`). If a file for today already exists for this customer, append a short suffix (e.g., `-v2`) or ask the user for a unique name.
3. Write the draft to the file in Markdown format:
   ```markdown
   # Follow-up Draft: [Customer Label]
   
   **Date:** 2026-05-28
   **Last Touch:** [user-supplied date]
   **Pipeline Stage:** [user-supplied stage]
   **Risk Score:** [MEDIUM]
   **Next-Best-Action:** [action from skill]
   
   ## Email Draft
   
   **Subject:** [subject line]
   
   [email body]
   ```
4. Confirm to user: `✓ Draft saved to .odoo-ai/followups/abc-manufacturing-2026-05-28.md`.

## Examples

**Example 1 (abstract):** Customer: "Customer A"; last touch: 2026-04-30 (28 days ago); pipeline stage: "Proposal sent"; blocker: "waiting on technical evaluation from customer's IT team". Skill assesses **HIGH risk** (customer is silent, evaluating alternatives), recommends **"schedule a 30-min call to unblock evaluation"**, drafts a warm but concise email offering technical support and a concrete call time.

## Standalone fallback

If `odoo-deal-followup` skill is unavailable, do not hand the work back to the user: synthesize the follow-up yourself from the deal data already in context, inferring an urgency level from days-since-last-touch versus stage and choosing a CTA accordingly. Mark the draft `risk: agent-inferred (skill offline)`. Only ask the user for a field no source provided.

## What this command does NOT do

- **Does NOT auto-send email**: it drafts to `.odoo-ai/followups/<slug>.md` and emits the path. Sending/queuing is the orchestrator/environment's job (whatever email integration it has) and always requires explicit confirmation.
- **Does NOT change CRM/opportunity fields** (amount, stage) and assumes no live CRM. Logging back to a CRM, if desired, is the orchestrator's call.
- **Does NOT handle objections directly**: for a technical/pricing objection use the `odoo-objection-handling` skill separately.
- **Does NOT escalate**: no manager notification or workflow trigger.

## See also

- `/odoo-respond-bid` - full proposal chain (RFQ → draft proposal → email → CRM sync).
- `odoo-deal-followup` skill - direct invocation for deal risk assessment without email drafting.
- `odoo-objection-handling` skill - for handling customer objections in follow-up threads.
