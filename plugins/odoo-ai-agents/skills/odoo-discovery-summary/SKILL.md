---
name: odoo-discovery-summary
description: >
  Transform raw discovery meeting notes (pasted or free-form) into a structured customer
  profile for proposal drafting - industry, current ERP, verbatim pain quotes, budget signal,
  timeline urgency, fit-score (1-5). Use ANY time a Sales AE or Pre-Sales Consultant finishes
  a discovery call and needs to synthesize notes. Fire on "synthesize discovery notes",
  "extract customer profile", "discovery call recap", "meeting notes to customer profile",
  "we had a discovery call - analyze", "tóm tắt notes cuộc họp tìm hiểu khách hàng",
  "vừa họp khách xong giúp tóm tắt thành hồ sơ". Trigger even on a business name +
  "we had a meeting". Also fires when given a file path to the notes/transcript.
  DO NOT trigger for internal team retrospectives, sprint planning, or
  developer standups with no customer prospect. When user wants to WRITE a follow-up email
  route to `odoo-deal-followup`; for a full effort matrix (Standard/Custom/days) route to
  `odoo-gap-analysis`; to handle an objection route to `odoo-objection-handling`
---

## Persona

Sales AE + Pre-Sales Consultant (dual persona). Output audience: AEs handing a brief to a
solution architect or manager, and pre-sales consultants qualifying fit before demo time.

## Out of Scope

- Proposal/quote → `odoo-gap-analysis` (effort matrix) / `odoo-respond-bid`
- Follow-up email to prospect → `odoo-deal-followup`
- Handling a specific objection → `odoo-objection-handling`
- Single feature lookup outside discovery → `odoo-feature-check`

## MCP tools

<!-- BEGIN MANUAL TOOLS - odoo-discovery-summary -->
_OSM is OPTIONAL - this skill is standalone-first. Only
call OSM tools when the user explicitly wants to verify Odoo can address a stated pain,
or requests "double-check with Odoo" / "kiem tra Odoo co chua"._

**Optional - pain-point verification:**
- `check_module_exists` - When a customer named a specific feature need (e.g., "lot
  traceability", "subscription billing"), call to verify whether Odoo has a standard
  module for it and which edition. Include result in the Fit Assessment table.
- `find_examples` - When the customer wants proof-of-concept evidence during or after
  discovery ("can you show me how Odoo does X?"), use to surface real indexed code
  snippets or UI evidence. Only call if user explicitly requests it.
- `profile_inspect` - When several Confidence-Low fit rows turn on "does the Viindoo profile
  cover this vertical" (e.g. is there a `viin_mrp_*` family?), call
  `profile_inspect(method='modules', name=<profile>, odoo_version='<version>')` once to list the
  profile-owned modules - this resolves several fit rows in a single call instead of one
  `check_module_exists` per module.

**Do NOT call** `set_active_profile`, `model_inspect`, `lint_check`, or any
developer-oriented tools - this skill outputs business analysis, not code.
<!-- END MANUAL TOOLS -->

## Standalone-first fallback

This skill produces a full Discovery Profile without OSM. Follow rounds in sequence.

### Round 0 - Session context bootstrap

Follow `${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md` before asking for any project fact:

1. **Read `.odoo-ai/context.md`** if present. Extract `odoo_version` and `profile_name` as
   authoritative defaults (used when `check_module_exists` is called in Rounds 3/3.5).
2. If absent, derive version from manifest files; default to `odoo_version=<version>` if still unresolved.
3. Ask the caller only for context genuinely missing after steps 1-2.

### Round 1 - Parse the raw input

Categorize every sentence/bullet into slots. Preserve verbatim quotes where the user transcribed the prospect's words.

| Slot | What to look for |
|---|---|
| **Industry vertical** | Sector keywords (manufacturing, retail, distribution, F&B, healthcare, education, professional services…) |
| **Headcount band** | Employee/team/office count → S (<50), M (50-200), L (200-1000), XL (>1000) |
| **Current system** | Named ERP, accounting software, or "Excel / Google Sheets / manual" |
| **Pain points** | Problems, frustrations, bottlenecks - verbatim quote if available |
| **Success criteria** | "Done" definition - KPIs, deadlines, "we need X by Y" |
| **Decision process** | Single owner / committee / board approval |
| **Budget signal** | Any number, range, "tight budget", "we have approval", "waiting for Q3 budget" |
| **Timeline urgency** | Immediate / specific quarter / "no rush" / "must go live by date" |
| **Other** | Regulatory, language, integration partners |

If a slot has NO data, mark `[not stated]` - never invent values.

### Round 2 - Build the customer profile

Assemble parsed data into the Output Format template. Use customer name if given; otherwise "Prospect (unnamed)".

### Round 3 - Fit assessment

For each pain point, assign one of four Odoo path labels:

| Label | Meaning |
|---|---|
| **Standard** | CE or EE ships this out of the box, zero dev needed |
| **Config** | Standard module exists; requires setup, <1 day |
| **Custom build** | Developer effort required - new model, significant override, or integration |
| **Cannot / Refer** | No viable Odoo path; recommend alternative or specialized vendor |

Assign Confidence (High / Med / Low) - Low when pain is ambiguous or cross-module complexity is unknown.

**Round 3.5 - Proactive OSM verification:** For every pain row where Confidence is Low OR label is uncertain, call `check_module_exists` automatically when OSM is reachable. Update the row with `(OSM-verified)` or `(OSM: not found - revise to Custom)`.

Fit score:
- **5/5** - All pains → Standard or Config; no Cannot.
- **4/5** - One pain → Custom build; none Cannot.
- **3/5** - Two pains → Custom build, OR one Cannot with workaround.
- **2/5** - Multiple Custom + one Cannot, OR complex integration required.
- **1/5** - Core requirement is Cannot / fundamentally out of scope.

State reasoning explicitly: "Fit 4/5 because lot traceability (Standard) and multi-currency (Config) are covered, but the EDI integration with their 3PL is Custom."

### Round 4 - Open questions

Identify top 3 discovery gaps most likely to change the fit score or proposal scope. Common high-value areas:
- Integration scope (which external systems, who owns the API?)
- Multi-company / multi-branch (separate ledgers? consolidated reporting?)
- Regulatory / audit requirements (VAS accounting, e-invoice, FDA traceability?)
- User count and concurrent-user peak (affects hosting + license cost)
- Data migration scope (years of history, legacy format, who extracts?)

Select the 3 most relevant to THIS prospect.

## Output format

Render the Discovery Profile as markdown using this template exactly:

```
# Discovery Profile - <Customer label>

## Snapshot
- Industry: <vertical, e.g., "Manufacturing - automotive parts">
- Headcount band: <S / M / L / XL> (<raw figure if stated>)
- Current system: <name + edition / "Excel/manual" / [not stated]>
- Decision process: <single owner / committee / board approval / [not stated]>
- Timeline urgency: <immediate / Q<N> YYYY / undefined>
- Budget signal: <figure or range / "approved" / "tight" / [not stated]>

## Pain points
1. <pain label> - "<verbatim quote if available>"
2. <pain label> - "<verbatim quote if available>"
3. ...

## Success criteria
- <criterion 1>
- <criterion 2>
- ...

## Fit assessment
| Pain | Odoo path | Confidence |
|------|-----------|------------|
| <pain 1> | Standard / Config / Custom build / Cannot | High / Med / Low |
| <pain 2> | ... | ... |

Overall fit: <N>/5 - <one-sentence reasoning>

## Open questions for next call
1. <question 1>
2. <question 2>
3. <question 3>

## Suggested next skills
- `odoo-gap-analysis` - Convert fit assessment into a full effort matrix for the proposal
- `odoo-deal-followup` - Draft a follow-up email referencing this discovery profile
- `odoo-objection-handling` - Prepare rebuttals if prospect raised doubts during the call
```

Do not add sections not in the template. Do not reorder sections. The profile must be
self-contained - a colleague who was not on the call should understand the full picture by reading it alone.

**Worked examples:** `${CLAUDE_PLUGIN_ROOT}/skills/odoo-discovery-summary/references/examples.md`

## Notes

- **`.odoo-ai/context.md` integration:** Handled by Round 0 (see context-bootstrap snippet). `odoo_version` and `profile_name` are used as authoritative defaults for all OSM calls. Absent → derive from disk, ask human for details.
- **Cross-skill handoff:** Discovery Profile is the INPUT to `odoo-gap-analysis`. Pipeline: `odoo-discovery-summary` (qualify) → `odoo-gap-analysis` (scope) → `odoo-deal-followup` (follow up) → `odoo-respond-bid` (proposal).

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the run-driver - it does not change anything produced above.
