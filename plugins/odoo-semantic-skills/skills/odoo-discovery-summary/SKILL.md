---
name: odoo-discovery-summary
description: >
  Transform raw discovery meeting notes (pasted or free-form) into a structured customer
  profile for proposal drafting — industry, current ERP, verbatim pain quotes, budget signal,
  timeline urgency, fit-score (1-5). Use ANY time a Sales AE or Pre-Sales Consultant finishes
  a discovery call and needs to synthesize notes. Fire on "synthesize discovery notes",
  "extract customer profile", "discovery call recap", "meeting notes to customer profile",
  "we had a discovery call — analyze", "tóm tắt notes cuộc họp tìm hiểu khách hàng",
  "vừa họp khách xong giúp tóm tắt thành hồ sơ". Trigger even on a business name +
  "we had a meeting". Also fires when given a file path to the notes/transcript.
  DO NOT trigger for internal team retrospectives, sprint planning, or
  developer standups with no customer prospect. When user wants to WRITE a follow-up email
  route to `odoo-deal-followup`; for a full effort matrix (Standard/Custom/days) route to
  `odoo-gap-analysis`; to handle an objection route to `odoo-objection-handling`
---

## Persona

Sales AE (Account Executive) + Pre-Sales Consultant (dual persona). Primary output
audience is AEs who need to hand a structured brief to a solution architect or manager,
and pre-sales consultants who need to qualify fit before investing demo time.

## Out of Scope

- Drafting the proposal/quote itself → use `odoo-gap-analysis` (effort matrix) and
  `odoo-respond-bid` (Phase C, not yet available)
- Writing the follow-up email to the prospect → use `odoo-deal-followup`
- Responding to a specific objection raised during or after discovery → use
  `odoo-objection-handling`
- Checking whether a single Odoo feature exists (outside discovery context) → use
  `odoo-feature-check`

## MCP tools

<!-- BEGIN MANUAL TOOLS — odoo-discovery-summary -->
_Tool surface: server v0.13.1. OSM is OPTIONAL — this skill is standalone-first. Only
call OSM tools when the user explicitly wants to verify Odoo can address a stated pain,
or requests "double-check with Odoo" / "kiem tra Odoo co chua"._

**Optional — pain-point verification:**
- `check_module_exists` — When a customer named a specific feature need (e.g., "lot
  traceability", "subscription billing"), call to verify whether Odoo has a standard
  module for it and which edition. Include result in the Fit Assessment table.
- `find_examples` — When the customer wants proof-of-concept evidence during or after
  discovery ("can you show me how Odoo does X?"), use to surface real indexed code
  snippets or UI evidence. Only call if user explicitly requests it.
- `profile_inspect` — When several Confidence-Low fit rows turn on "does the Viindoo profile
  cover this vertical" (e.g. is there a `viin_mrp_*` family?), call
  `profile_inspect(method='modules', name=<profile>, odoo_version='auto')` once to list the
  profile-owned modules — this resolves several fit rows in a single call instead of one
  `check_module_exists` per module.

**Do NOT call** `set_active_profile`, `model_inspect`, `lint_check`, or any
developer-oriented tools — this skill outputs business analysis, not code.
<!-- END MANUAL TOOLS -->

## Standalone-first fallback

This skill produces a full Discovery Profile without OSM. Follow rounds in sequence.

### Round 0 — Session context bootstrap

Follow `${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md` before asking the caller
for any project fact:

1. **Read `.odoo-ai/context.md`** if present. Extract `odoo_version` and `profile_name`
   as authoritative defaults; these are used automatically when `check_module_exists` is
   called in Rounds 3 and 3.5.
2. If the file is absent, derive version from manifest files on disk; if still unresolved,
   default to `odoo_version=17.0` and proceed.
3. Ask the caller only for context genuinely missing after steps 1-2.

### Round 1 — Parse the raw input

Read the user-pasted text carefully. Categorize every sentence or bullet into one or
more of the following slots. Preserve verbatim quotes where the user has transcribed
the prospect's words in quotation marks or after a dash.

| Slot | What to look for |
|---|---|
| **Industry vertical** | Sector keywords (manufacturing, retail, distribution, F&B, healthcare, education, professional services, etc.) |
| **Headcount band** | Employee count, team size, office count. Map to S (<50), M (50-200), L (200-1000), XL (>1000) |
| **Current system** | Any named ERP, accounting software, or "Excel / Google Sheets / manual" mentions |
| **Pain points** | Problems, frustrations, bottlenecks. Capture verbatim quote if available |
| **Success criteria** | What does "done" look like for them? KPIs, deadlines, "we need X by Y" |
| **Decision process** | Single owner vs. committee vs. board approval required |
| **Budget signal** | Any number, range, "tight budget", "we have approval", "waiting for Q3 budget" |
| **Timeline urgency** | Immediate / specific quarter / "no rush" / "must go live by date" |
| **Other** | Anything that does not fit above but may be relevant (regulatory, language, integration partners) |

If a slot has NO data in the notes, mark it `[not stated]` — never invent values.

### Round 2 — Build the customer profile

Assemble the parsed data into the Output Format template (see `## Output format`).
Use the customer name or company if given; otherwise label as "Prospect (unnamed)".

### Round 3 — Fit assessment

For each pain point identified, assign one of four Odoo path labels:

| Label | Meaning |
|---|---|
| **Standard** | Odoo CE or EE ships this out of the box, zero dev needed |
| **Config** | Standard module exists; requires setup (multi-company, rules, etc.), <1 day |
| **Custom build** | Requires developer effort — new model, significant override, or integration |
| **Cannot / Refer** | Odoo has no viable path; recommend alternative or specialized vendor |

Assign a Confidence level (High / Med / Low) reflecting certainty in the path label.
Confidence is Low when the pain is ambiguous or cross-module complexity is unknown.

**Round 3.5 - Proactive OSM verification (no user prompt needed):** For every pain row
where Confidence is Low OR where the label is uncertain (e.g., a domain-specific module
whose existence you cannot confirm from training memory alone), call `check_module_exists`
automatically when OSM is reachable. Do not wait for the user to ask. Update the table
row with `(OSM-verified)` or `(OSM: not found - revise to Custom)`.

Compute the overall fit score:
- **5/5** — All pains map to Standard or Config; no Cannot.
- **4/5** — One pain needs Custom build; none in Cannot.
- **3/5** — Two pains need Custom build, OR one Cannot with a workaround.
- **2/5** — Multiple pains need Custom build + one Cannot, OR complex integration
  required.
- **1/5** — Core requirement is in Cannot / fundamentally out of scope for Odoo.

State the reasoning explicitly: "Fit 4/5 because lot traceability (Standard) and
multi-currency (Config) are covered, but the EDI integration with their 3PL is Custom."

### Round 4 — Open questions

Identify the top 3 discovery gaps most likely to change the fit score or proposal
scope. Common high-value questions:

- Integration scope (which external systems must connect, and who owns the API?)
- Multi-company / multi-branch requirements (separate ledgers? consolidated reporting?)
- Regulatory / audit requirements (VAS accounting, e-invoice mandate, FDA traceability?)
- User count and concurrent-user peak (affects hosting and license cost)
- Data migration scope (years of history, legacy format, owner of extraction)

Select the 3 most relevant to THIS prospect based on their industry and stated pains.

## Output format

Render the Discovery Profile as markdown using this template exactly:

```
# Discovery Profile — <Customer label>

## Snapshot
- Industry: <vertical, e.g., "Manufacturing — automotive parts">
- Headcount band: <S / M / L / XL> (<raw figure if stated>)
- Current system: <name + edition / "Excel/manual" / [not stated]>
- Decision process: <single owner / committee / board approval / [not stated]>
- Timeline urgency: <immediate / Q<N> YYYY / undefined>
- Budget signal: <figure or range / "approved" / "tight" / [not stated]>

## Pain points
1. <pain label> — "<verbatim quote if available>"
2. <pain label> — "<verbatim quote if available>"
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

Overall fit: <N>/5 — <one-sentence reasoning>

## Open questions for next call
1. <question 1>
2. <question 2>
3. <question 3>

## Suggested next skills
- `odoo-gap-analysis` — Convert fit assessment into a full effort matrix for the proposal
- `odoo-deal-followup` — Draft a follow-up email referencing this discovery profile
- `odoo-objection-handling` — Prepare rebuttals if prospect raised doubts during the call
```

Do not add sections not in the template. Do not reorder sections. The profile must
be self-contained — a colleague who was not on the call should understand the full
picture by reading it alone.

## Examples

### Example 1 — Customer A (manufacturing SME, traceability need)

**User input (VI):**
> "Họp với Customer A hôm nay. Sản xuất linh kiện nhựa, khoảng 80 người, đang dùng
> Excel + phần mềm kế toán cũ. Họ nói 'chúng tôi không biết lô nào gây ra lỗi trả về
> vì không có trace'. Muốn quản lý lô hàng, truy xuất nguồn gốc, báo cáo sản xuất.
> Ngân sách chưa chốt, cần demo trước. Quyết định do giám đốc sản xuất + CFO."

**Expected profile (excerpt):**

```
# Discovery Profile — Customer A

## Snapshot
- Industry: Manufacturing — plastic components
- Headcount band: M (80 employees)
- Current system: Excel + legacy accounting software
- Decision process: Committee (Production Director + CFO)
- Timeline urgency: undefined (demo first)
- Budget signal: [not stated — approval pending demo]

## Pain points
1. Lot traceability gap — "chúng tôi không biết lô nào gây ra lỗi trả về vì không có trace"
2. No production reporting visibility

## Fit assessment
| Pain | Odoo path | Confidence |
|------|-----------|------------|
| Lot traceability | Standard (stock.lot + MRP) | High |
| Production reporting | Config (mrp module dashboards) | Med |

Overall fit: 5/5 — Both pains are covered by standard MRP/inventory modules; main risk
is data migration from legacy accounting.

## Open questions for next call
1. Does the accounting migration need to carry historical transactions (GL balance only vs. full journal)?
2. Are there regulatory traceability requirements (ISO, customer audit mandates)?
3. How many concurrent warehouse users at peak picking time?
```

### Example 2 — Customer B (multi-store retail, POS + inventory sync)

**User input (EN):**
> "Discovery call with Customer B. They run 5 retail stores + 1 online shop. ~200 staff
> total. Using a legacy POS that doesn't sync with their warehouse. Quote: 'We lose at
> least 3 hours a day reconciling stock between stores manually.' Want real-time stock
> visibility across locations and loyalty points that work both in-store and online.
> Budget approved up to USD 40k. Must go live Q1 next year. Owner decides alone."

**Expected profile (excerpt):**

```
# Discovery Profile — Customer B

## Snapshot
- Industry: Retail — multi-store + e-commerce
- Headcount band: M (200 employees)
- Current system: Legacy POS (vendor unspecified), separate warehouse system
- Decision process: Single owner
- Timeline urgency: Q1 <next year>
- Budget signal: Approved up to USD 40k

## Pain points
1. Real-time cross-location stock sync — "We lose at least 3 hours a day reconciling
   stock between stores manually."
2. Unified loyalty programme (in-store + online)

## Fit assessment
| Pain | Odoo path | Confidence |
|------|-----------|------------|
| Cross-location stock sync | Standard (multi-warehouse + POS module) | High |
| Unified loyalty (POS + eCommerce) | Config (loyalty.card + eCommerce bridge) | Med |

Overall fit: 4/5 — Core pain is standard; loyalty cross-channel sync may need config
tuning. USD 40k budget is tight if data migration from 5 legacy POS instances is needed.

## Open questions for next call
1. What is the current loyalty card data format — can it be exported for migration?
2. Does the online shop run on a third-party platform (Shopify, WooCommerce) or is a new
   Odoo eCommerce site also in scope?
3. Are the 5 stores on separate tax jurisdictions requiring different fiscal positions?
```

## Notes

### `.odoo-ai/context.md` integration

Handled by Round 0 (see `${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md`). The
file is read automatically at session start; `odoo_version` and `profile_name` are used
as authoritative defaults for all OSM calls. If the file is absent the skill derives
version from disk and defaults to v17.0 - no error, no prompt to the user.

### Cross-skill handoff

The Discovery Profile is designed as the INPUT to `odoo-gap-analysis`. After producing
the profile, always suggest `odoo-gap-analysis` as the next step if the user wants to
turn the Fit Assessment table into a full effort matrix (day estimates, dev cost,
Standard vs. Custom classification with granularity). The two skills form a natural
pre-sales pipeline: `odoo-discovery-summary` (qualify) → `odoo-gap-analysis` (scope)
→ `odoo-deal-followup` (follow up) → `odoo-respond-bid` (proposal, Phase C).
