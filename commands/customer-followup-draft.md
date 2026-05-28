---
name: odoo-customer-followup-draft
description: |
  Draft a follow-up email for a stalled or at-risk deal. Wraps the odoo-deal-followup skill with explicit save-to-disk step. Type this slash command when you have a specific deal needing a follow-up email today.
---
# /odoo-customer-followup-draft

Single-purpose slash command for sales follow-up email drafting. Chains the `odoo-deal-followup` skill with an explicit save-to-file step, gating on user approval before writing to disk.

## When to use

Invoke this command when you have a stalled or at-risk deal and need to compose a follow-up email **today**. The skill will analyze deal context, assess risk, and suggest a next-best action, then draft an email ready for review before you send.

Type: `/odoo-customer-followup-draft [customer-label]`

Optional: supply customer label on the command line (e.g., `Khách A`). If omitted, the command will prompt you for it.

## Hard rules

- **Read context first**: Check `.odoo-ai/context.md` for CRM metadata and pipeline rules before drafting. This ensures the drafted email aligns with your deal context.
- **Gather deal inputs**: Ask the user for required information:
  - Customer label or short name (e.g., "ABC Manufacturing")
  - Last touch date (when you last communicated with the customer)
  - Current pipeline stage (e.g., "Proposal", "Negotiation", "Stalled")
  - Prior commitments or blockers (e.g., "waiting on PO", "evaluating competing offer")
  - Optional: paste a snippet or subject of the prior email thread (for tone continuity)
- **Gate before saving**: Display the drafted email to the user. Explicitly ask: "Email draft OK? (yes / iterate / cancel)". Do not write to disk unless the user confirms "yes".
- **No auto-send**: This command **only drafts**. It does not send email, update CRM systems, or trigger workflows.

## Phases

### Phase 0: Parse inputs and gather deal context
1. Parse `$ARGUMENTS` for an optional customer label.
2. If not provided, ask: "Customer name or label?"
3. Ask for: last touch date, pipeline stage, prior commitments/blockers, optional prior email thread (for tone).
4. Read `.odoo-ai/context.md` to load CRM metadata, pipeline rules, and any standing objection handlers.

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

**Example 1 (abstract):** Customer: "Khách A" (Vietnam-based); last touch: 2026-04-30 (28 days ago); pipeline stage: "Proposal sent"; blocker: "waiting on technical evaluation from customer's IT team". Skill assesses **HIGH risk** (customer is silent, evaluating alternatives), recommends **"schedule a 30-min call to unblock evaluation"**, drafts a warm but concise email offering technical support and a concrete call time.

## Standalone fallback

If `odoo-deal-followup` skill is unavailable, prompt the user to manually paste the deal context (customer label, last touch date, prior commitments) and any prior email thread. Command produces a basic follow-up draft from those inputs without risk-score heuristics. User must manually compute urgency and choose CTA.

## What this command does NOT do

- **Does NOT send email**: only drafts to disk. You copy-paste or forward from the draft file to your email client.
- **Does NOT update CRM**: no Viindoo ERP, Salesforce, or HubSpot sync. Manual step required.
- **Does NOT handle objections directly**: if the customer raises a technical or pricing objection, use the `odoo-objection-handler` skill separately for a deeper response.
- **Does NOT escalate**: no manager notification or workflow trigger.

## See also

- `/odoo-bid-respond` — full proposal chain (RFQ → draft proposal → email → CRM sync).
- `odoo-deal-followup` skill — direct invocation for deal risk assessment without email drafting.
- `odoo-objection-handler` skill — for handling customer objections in follow-up threads.
