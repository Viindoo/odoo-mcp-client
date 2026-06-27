---
name: odoo-deal-followup
description: >
  Analyze deal health for Odoo or a custom distribution and generate next actions for a Sales
  AE or small-team founder running go-to-market solo. Accepts deal context (label, last
  contact, stage, prior commitments) + an optional email/note thread; produces (a) a risk
  score (red/yellow/green), (b) a next-best action, (c) a draft follow-up email in English or
  the thread's language.
  Trigger on: "deal stalled", "customer hasn't replied", "draft follow-up email", time
  signals ("it's been 3 weeks", "deadline this month"), ambiguous-status signals ("not sure
  what the customer is thinking"). Also fires on Vietnamese: "deal đang đứng im", "khách
  chưa trả lời", "soạn email follow-up", "cần hâm nóng lại deal". DO NOT trigger for: (1) Discovery/demo session summary
  -> use odoo-discovery-summary. (2) Responding to technical objections -> use
  odoo-objection-handling. (3) Verifying or proving Odoo features -> use
  odoo-capability-proof or odoo-feature-check. (4) Gap analysis or scope estimation -> use
  odoo-gap-analysis
---

## Persona

Sales AE or founder running go-to-market solo. No SDR or sales team. Every deal matters.
This skill prevents deals going cold due to missed follow-ups or unclear next steps.

## Out of Scope

- Discovery session summary / demo notes → `odoo-discovery-summary`
- Responding to technical objections → `odoo-objection-handling`
- Proving a feature with code evidence → `odoo-capability-proof`
- Simple feature lookup → `odoo-feature-check`
- Gap analysis / effort estimate → `odoo-gap-analysis`

## MCP tools

<!-- BEGIN MANUAL TOOLS - odoo-deal-followup -->
_This skill is standalone-first - OSM/MCP is OPTIONAL. Most invocations do not need MCP._

**OSM usage rule:** Only invoke when the user explicitly asks to fact-check a specific Odoo
feature claim in the email or deal context. Do not call MCP automatically just because the deal involves Odoo.

**Optional tool (on-demand only):**
- `check_module_exists` - Verify whether a specific Odoo module/feature exists and in which
  edition (CE/EE/your custom distribution). Call only when user asks to fact-check a feature
  claim present in the deal thread or email. Do NOT call speculatively.

This skill performs text analysis and email composition directly - no code generation or
external model delegation is involved.
<!-- END MANUAL TOOLS - odoo-deal-followup -->

## Standalone-first fallback

Skill **always operates without OSM**. All logic runs on user-provided text.

### Round 0 - Bootstrap context, then ask only for gaps

1. **Use the invocation context first.** Deal details are usually already in the request - do not re-ask for anything already provided.
2. **Read `.odoo-ai/context.md`** if present - extract `odoo_version` and any CRM defaults.
3. **Optional enrichment:** If a live CRM/email integration is available, enrich from it - but treat as a bonus, never required. Skill must work with only request text + local files.
4. Ask only for fields still unresolved after steps 1-3, in one message.

**Required inputs:**
- Customer label (may be abstract: "Customer A")
- Last contact date (or "approximately X days/weeks ago")
- Current pipeline stage (Qualified / Proposal sent / Negotiation / Demo done / Contract review)
- Prior commitment / promise made

**Optional inputs:** email/note thread; expected close date; deal size category (Small <$2K / Medium $2K-$20K / Large >$20K); existing Odoo license; multi-year preference.

If the user pastes an email thread without context, extract required fields from it first, then confirm before proceeding.

### Round 1 - Compute risk score

| Signal | Risk points |
|---|---|
| >30 days no reply from a warm lead | +3 (Red trigger) |
| 14-30 days no reply | +2 (Yellow trigger) |
| <14 days no reply | +0 (Green) |
| Committed deadline passed without delivery | +2 |
| Deal moved to earlier / lower stage | +2 |
| Customer changed point of contact | +1 |
| Customer in procurement / multi-vendor tender | +1 |
| Positive signal: customer proactively reached out | -2 |
| Expected close date still >60 days away | -1 |

**Result:** Green (<=1) / Yellow (2-3) / Red (>=4). Ghosting or competitor mention adds +1 Red.

### Round 2 - Identify next-best action

| Situation | Next-best action |
|---|---|
| Green - Proposal sent | Gentle check-in with an open question |
| Yellow - Demo done | Re-engage with proof: case study or mini ROI summary |
| Yellow - Negotiation | Schedule a call: propose a specific time slot |
| Red - any stage, >30 days | Break-up email: direct, respectful, leave door open |
| Red - commitment overdue | Apologize + deliver immediately + schedule a call |
| Red - competitor comparison | Escalate with incentive: proof of value + limited-time offer |
| Any stage - no champion left | Find another stakeholder; hand off if needed |

Round 2 output is **one top-priority action**.

### Round 3 - Draft follow-up email

Write in the language matching the customer's thread or the user's request. Default: English.

**4-paragraph template:**
1. **Warm reopener** - Reference the last interaction. Do NOT open with "I haven't heard back from you."
2. **Value reinforcement** - 1-2 specific points of value tied to their stated needs. Personalised, not generic.
3. **Clear ask** - One single action: schedule a call, confirm a decision, review the quote. No multiple questions.
4. **Low-friction CTA** - 2-3 specific time slots OR a calendar link. Open sentence if break-up email.

**Tone:** Confident, respectful, not pleading. Appropriate for B2B.

### Round 4 - Output assembly

Combine Rounds 1-3 into the Output format. If the thread contains technical Odoo claims the user might want to verify, list under "Optional: feature claims to verify" - do NOT call MCP unless the user confirms.

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
<If applicable: "Suggest: run odoo-objection-handling if the customer is pushing back on a
specific feature" or "Suggest: run odoo-capability-proof if you need an evidence package for
the customer">
```

**Worked examples:** `${CLAUDE_PLUGIN_ROOT}/skills/odoo-deal-followup/references/examples.md`

## Notes

- **Odoo version context:** Feature claims in an email thread are flagged under "Optional: feature claims to verify". Version resolved from `.odoo-ai/context.md` in Round 0.
- **Email language:** Matches thread language or explicit request. No thread → default English.
- **No invented information:** Missing last contact date or pipeline stage → ask before computing risk score.
- **Leaf skill.** Does NOT spawn subagents, does NOT invoke the Skill tool. References to other skills are text suggestions only.

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next) - additive run-driver output, changes nothing above.
