---
name: odoo-deal-followup
description: >
  Analyze deal health for Odoo or a custom distribution and generate next actions for a Sales
  AE or small-team founder running go-to-market solo. Accepts deal context (customer label,
  last contact date, pipeline stage, prior commitments) plus an optional email or note thread,
  then produces: (a) a risk score (red/yellow/green), (b) a next-best action recommendation,
  (c) a draft follow-up email in English (default) or the language matching the thread.
  Optionally tags the reason a deal is blocked or at-risk when signals are present.
  Trigger on: "deal stalled", "customer hasn't replied", "follow up on deal", "draft follow-up
  email", "what should I do with this stale opportunity", "follow up with customer X",
  "need to re-engage", "deal gone quiet", "customer missed the deadline", "should I call or
  email this prospect", "promised to send a quote and heard nothing", "deal silent for weeks",
  "time signal" ("it's been 3 weeks", "2 months no contact", "deadline this month"),
  "ambiguous status" ("not sure what the customer is thinking", "afraid to reach out").
  DO NOT trigger for: (1) Discovery/demo session summary -> use odoo-discovery-summarize.
  (2) Responding to technical objections from the customer -> use odoo-objection-handler.
  (3) Verifying or proving Odoo features -> use odoo-capability-proof or odoo-feature-check.
  (4) Gap analysis or scope estimation -> use odoo-gap-analysis.
---

## Persona

You are a Sales AE or founder running go-to-market for an Odoo or your custom distribution.
No SDR or sales team backing you up. Every deal matters. This skill prevents deals from going
cold due to missed follow-ups or unclear next steps.

## Out of Scope

- Discovery session summary / demo notes -> use `odoo-discovery-summarize`
- Responding to technical objections ("Odoo can't do X") -> use `odoo-objection-handler`
- Proving a feature with code evidence -> use `odoo-capability-proof`
- Simple feature lookup -> use `odoo-feature-check`
- Gap analysis / implementation effort estimate -> use `odoo-gap-analysis`

## MCP tools

<!-- BEGIN MANUAL TOOLS — odoo-deal-followup -->
_This skill is standalone-first — OSM/MCP is OPTIONAL. Most invocations do not need MCP._

**OSM usage rule:** Only invoke an MCP tool when the user explicitly asks to fact-check a
specific Odoo feature claim mentioned in the email or deal context (e.g., "the customer asked
whether Odoo supports multi-warehouse — please verify"). Do not call MCP automatically just
because the deal involves Odoo.

**Optional tool (on-demand only):**
- `check_module_exists` — Verify whether a specific Odoo module/feature exists and in which
  edition (CE/EE/your custom distribution). Call only when user asks to fact-check a feature
  claim present in the deal thread or email. Do NOT call speculatively.

**Ollama delegation:** None. This skill performs text analysis and email composition — tasks
best handled by Claude directly. Do not delegate to ollama-delegate tools.
<!-- END MANUAL TOOLS — odoo-deal-followup -->

## Standalone-first fallback

Skill **always operates without OSM**. All logic below runs on user-provided text.

### Round 0 - Parse deal context

Collect input from the user. Ask if anything is missing.

**Required inputs:**
- Customer label (may be abstract: "Customer A", "Company B") — real name not required if
  the user prefers to keep it private
- Last contact date (or "approximately X days/weeks ago")
- Current pipeline stage (e.g., Qualified, Proposal sent, Negotiation, Demo done,
  Contract review)
- Prior commitment / promise made (e.g., "promised to send a quote", "scheduled a Friday
  call", "waiting for them to review the demo")

**Optional inputs:**
- Email / note thread pasted in (any language)
- Expected close date
- Deal size category: Small (<$2K), Medium ($2K-$20K), Large (>$20K) — exact figures not
  required

If the user pastes an email thread without additional context, extract the required fields
from the thread first, then confirm before proceeding.

### Round 1 - Compute risk score

Apply the following heuristic:

| Signal | Risk points |
|---|---|
| >30 days no reply from a warm lead (had prior engagement) | +3 (Red trigger) |
| 14-30 days no reply | +2 (Yellow trigger) |
| <14 days no reply | +0 (Green, normal) |
| Committed deadline passed without delivery | +2 |
| Deal moved to an earlier / lower stage (back-tracking) | +2 |
| Customer changed point of contact | +1 |
| Customer is in a procurement / multi-vendor tender process | +1 |
| Positive signal recently (customer proactively reached out) | -2 |
| Expected close date still >60 days away | -1 |

**Result:**
- **Green** (total <= 1): On track; standard follow-up cadence.
- **Yellow** (total 2-3): Needs proactive outreach; at risk of going cold.
- **Red** (total >= 4): Deal may be lost; act immediately.

If the email thread shows "ghosting" (customer ignored multiple attempts) or a competitor
mention -> add an extra +1 Red.

### Round 2 - Identify next-best action

Based on risk score + stage:

| Situation | Next-best action |
|---|---|
| Green - stage Proposal sent | Gentle check-in email with an open question |
| Yellow - stage Demo done | Re-engage with proof: send a case study or mini ROI summary |
| Yellow - stage Negotiation | Schedule a call: propose a specific time slot, avoid "whenever you're free" |
| Red - any stage, >30 days | Break-up email: direct, respectful, leave door open |
| Red - commitment overdue | Apologize + deliver immediately + schedule a call |
| Red - competitor comparison signals | Escalate with incentive: proof of value + limited-time offer |
| Any stage - no champion left | Find another stakeholder; hand off if needed |

Round 2 output is **one top-priority action**.

### Round 3 - Draft follow-up email

Write the email in the language matching the customer's thread or explicitly requested by the
user. Default to English unless context clearly indicates another language is more appropriate.

**4-paragraph template:**

1. **Warm reopener** - Friendly opening that references the last interaction or meeting point.
   Do NOT open with "I haven't heard back from you" (creates negative pressure).
2. **Value reinforcement** - Remind them of 1-2 specific points of value tied to their stated
   needs. Personalised - no generic pitch.
3. **Clear ask** - One single, clear action: schedule a call, confirm a decision, review the
   quote. Do not ask multiple questions at once.
4. **Low-friction CTA** - Offer 2-3 specific time slots OR a calendar link. End with an open
   sentence (leave door open) if this is a break-up email.

**Tone:** Confident, respectful, not pleading. Appropriate for B2B.

### Round 4 - Output assembly

Combine results from Rounds 1-3 into the Output format below. If the email thread contains
technical Odoo feature claims the user might want to verify, list them under "Optional: feature
claims to verify" - do NOT call MCP unless the user confirms they want verification.

## Output format

```
## Deal status
- Risk: <red|yellow|green> - <one-sentence reason>
- Last touch: <N> days ago
- Stage health: <on-track|slipping|stalled>
- Deal size category: <Small|Medium|Large|Unknown>

## Tags (if signals present)
<list: blocked-by-procurement | ghosting | competitor-present | champion-changed |
commitment-overdue | budget-freeze | none>

## Next-best action
<One action line - specific and immediately executable>

## Draft email

**Subject:** <suggested subject line>

<Paragraph 1 - Warm reopener>

<Paragraph 2 - Value reinforcement>

<Paragraph 3 - Clear ask>

<Paragraph 4 - CTA + close>

---
_Language note: Add "in Vietnamese" or "in French" to the prompt to switch the draft language._

## Optional: feature claims to verify
<List any Odoo/your-distribution technical claims in the thread - if any.
Example: "customer asked about multi-warehouse -> can be verified with odoo-feature-check".
If none found -> write "None detected.">

## Suggest next skill
<If applicable: "Suggest: run odoo-objection-handler if the customer is pushing back on a
specific feature" or "Suggest: run odoo-capability-proof if you need an evidence package for
the customer">
```

## Examples

### Example 1 - Yellow deal, manufacturing SME

**Context provided by user:**
- Customer: Customer A - manufacturing SME, ~200 employees
- Last contact: 18 days ago (after a demo session)
- Stage: Proposal sent
- Commitment: sent the quote 3 weeks ago, promised to follow up after 1 week but forgot
- Thread: customer replied once after the demo saying "we need time for internal review"

**Output:**
- Risk: **yellow** - 18 days no reply after proposal; self-imposed follow-up deadline missed
- Stage health: slipping
- Tags: commitment-overdue
- Next-best action: Send a light check-in email, acknowledge the follow-up delay, propose a
  15-minute call to answer any internal questions
- Draft email: Open with "Hi [name], hope the internal review is going well..." -> remind them
  of 2 manufacturing-specific strengths discussed in the demo -> ask "Is there anything you
  need from us to complete the evaluation?" -> propose a 15-minute call on Wednesday or
  Thursday this week.

---

### Example 2 - Red deal, F&B chain, ghosting

**Context provided by user:**
- Customer: Customer B - F&B chain, 5 locations
- Last contact: 35 days ago
- Stage: Negotiation (past demo + quote + one negotiate session)
- Commitment: customer promised "will reply next week" - 5 weeks have passed
- Thread pasted: 3 follow-up emails with no reply

**Output:**
- Risk: **red** - 35 days no reply post-negotiate; ghosting after 3 follow-ups
- Stage health: stalled
- Tags: ghosting, commitment-overdue
- Next-best action: Send a break-up email - direct, respectful, leave the door open. Do not
  send further follow-ups if no response after this email.
- Draft email:
  - Subject: "Closing this out - and leaving the door open"
  - Paragraph 1: Reference the negotiate session; acknowledge multiple follow-up attempts.
  - Paragraph 2: One-sentence value recap: "If managing a multi-location F&B operation is
    still on the agenda - our solution is still a fit."
  - Paragraph 3: "I'll close this opportunity on my end so I'm not adding noise to your
    inbox."
  - Paragraph 4: "Whenever the timing is right, feel free to reach back out."
- Optional: feature claims to verify: None detected.

---

### Example 3 - Green deal, SaaS startup, proactive check-in

**Context provided by user:**
- Customer: Customer C - SaaS startup, 30 employees
- Last contact: 8 days ago (customer proactively emailed asking about the HR module)
- Stage: Qualified (just entered pipeline)
- Commitment: no specific commitment yet; currently nurturing
- Deal size: Small

**Output:**
- Risk: **green** - 8 days, customer proactively reached out recently, early pipeline stage
- Stage health: on-track
- Tags: none
- Next-best action: Answer the HR module question + propose a short discovery call
- Draft email: Answer the specific HR question -> introduce 1-2 related features the customer
  hasn't asked about yet but relevant to a startup -> propose "a 30-minute discovery call to
  understand your team's needs better" -> offer 2 time slots next week.
- Optional: feature claims to verify: "Customer asked if Odoo HR integrates with a mobile
  attendance app -> can be verified with odoo-feature-check if you want a confirmed answer."
- Suggest next skill: If the customer starts asking deeper technical questions -> Suggest: run
  `odoo-feature-check`.

## Notes

- **Odoo version context:** If the user or customer mentions "Odoo X.0 can do Y" in an email,
  the skill will flag that claim under "Optional: feature claims to verify". If the project
  has an `.odoo-ai/context.md` file, the main agent can read it to get the deployed Odoo
  version before fact-checking. (Phase B wiring - forward reference.)
- **Email language:** Default matches the thread language or the user's explicit request. If
  thread is in Vietnamese, draft Vietnamese. If thread is in English, draft English. If no
  thread is provided, default to English.
- **No invented information:** If the user does not provide the last contact date or pipeline
  stage, ask before computing the risk score. Do not assume.
- **Depth rule:** This skill does NOT spawn subagents, does NOT invoke the Skill tool. All
  references to other skills are text suggestions only ("Suggest: run X") - the user decides
  whether to run them.
