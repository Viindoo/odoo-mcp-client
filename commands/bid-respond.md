---
name: odoo-bid-respond
description: |
  Generate a complete Odoo/Viindoo bid response package from raw prospect input. Chains discovery synthesis → gap analysis → capability proof → objection pre-empt → proposal draft. Invoke when responding to an RFP, proposal request, or post-discovery synthesis needs.
---
# /odoo-bid-respond

Command-level recipe (depth 0) that transforms raw prospect input — pasted email, meeting notes, or a requirements list — into a complete, ready-to-send bid response package: customer profile, effort matrix, capability evidence, counter-talking-points, and a draft proposal document.

## When to use

Type `/odoo-bid-respond` immediately after receiving any prospect communication that requires a structured response: an RFP, a "can Odoo do X?" email, post-demo follow-up notes, or a shortlist questionnaire. Optional `$ARGUMENTS` = a short customer label (e.g., `Khach-A`, `CustomerA`). If omitted, the command prompts for one.

This command is a recipe, not a single skill. It chains five downstream skills in sequence, gating each phase with explicit user approval. Each gate keeps you in control: wrong direction? Edit the draft before advancing. OSM unreachable? The command degrades gracefully (see Standalone fallback).

## Hard rules

1. **Phase gate mandatory.** Each phase ends with a binary gate shown to the user. The command MUST NOT advance to the next phase until the user explicitly confirms (yes / y / proceed). On "edit" the agent revises the current phase output inline. On "cancel" the agent stops and reports progress so far.
2. **Context check.** At startup, check for `.odoo-ai/context.md` in the working directory. If found, load it as project context. If missing, suggest the user run `/odoo-onboard` first, then allow them to continue with manually supplied context.
3. **Abstract labels.** Use the customer label provided by the user (or the default "Khach-A") throughout all internal summaries and the saved document. Never log real company names, contact names, or pricing in any file committed to this repo.
4. **Skill invocation via natural language.** Each phase instructs the main agent to produce a natural-language prompt whose phrasing auto-fires the target skill via the skill's description match. Do NOT use the Agent tool to invoke skills; the skill harness handles dispatch in the main context.
5. **Agent tool scope.** The main agent MAY use the Agent tool only for `odoo-coder` or `odoo-code-reviewer` bundle invocations when Phase 3 requires technical code evidence. Those subagent prompts MUST include the line: `KHÔNG invoke Skill tool. KHÔNG spawn sub-agent. CHỈ Read/Grep/Glob/Edit/Write.`
6. **No external writes before gate 5.** Writing files to `.odoo-ai/bids/` happens only after the user confirms Phase 5 output. No side effects before then.
7. **Public repo safety.** This file is in a public repo. No real customer names, deal sizes in currency, or pricing tables in examples or defaults.

## Phases

### Phase 0 — Parse arguments + check context

1. Parse `$ARGUMENTS` for a customer label token. If found, store as `CUSTOMER_LABEL`. If absent, ask: "Nhãn khách hàng (vd: Khach-A)? [default: Khach-A]". Accept the user's answer or use the default.
2. Check for `.odoo-ai/context.md`:
   - Found → load and summarize its Odoo version + active modules in one line. Confirm: "Đang dùng context: <version> / <modules>. Tiếp tục? [y/n]"
   - Not found → show warning: "`.odoo-ai/context.md` chưa có. Nên chạy `/odoo-onboard` trước. Tiếp tục thủ công? [y/n]". On `n`, stop.
3. Collect the following from the user in one message (list all four prompts together so the user can answer in one block):
   - **(a)** Raw prospect input — paste email, meeting notes, or requirements list.
   - **(b)** Target close date (approximate, e.g., "cuối Q3 2026").
   - **(c)** Deal size category: **S** (1-5 users, simple), **M** (6-30 users, multi-dept), or **L** (30+ users, enterprise).
   - **(d)** Primary contact role (e.g., IT manager, CFO, CEO) — used to calibrate language register.
4. Store inputs. Proceed to Phase 1.

### Phase 1 — Discovery synthesis

Goal: produce a structured customer profile from the raw prospect input.

Invoke by producing the following natural-language prompt to auto-fire the `odoo-discovery-summarize` skill (or equivalent discovery/summarize skill in the active plugin set):

> "Tóm tắt hồ sơ khách hàng từ đầu vào thô sau đây. Xác định: lĩnh vực kinh doanh, quy mô, pain points chính (tối đa 5), success criteria (tối đa 3), các module Odoo liên quan, và rủi ro triển khai. Đầu vào: [paste raw prospect input here]"

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

**Gate 1:** "Profile chính xác chưa? (yes / edit / cancel)"
- yes → proceed to Phase 2
- edit → revise specific fields inline, re-show, re-gate
- cancel → stop, output progress so far

### Phase 2 — Gap analysis

Goal: produce an effort matrix from the profile's pain points and success criteria.

Use the profile from Phase 1 as input. Invoke by producing the following natural-language prompt to auto-fire the `odoo-gap-analysis` skill:

> "Phân tích gap giữa yêu cầu của [CUSTOMER_LABEL] và năng lực Odoo tiêu chuẩn. Với mỗi pain point và success criterion, phân loại: Standard / Config / Extension / Custom. Ước tính công sức: S (<3 ngày) / M (3-10 ngày) / L (10-30 ngày) / XL (>30 ngày). Đầu vào pain points: [list from Phase 1]. Success criteria: [list from Phase 1]."

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

**Gate 2:** "Ma trận effort chính xác chưa? (yes / edit / cancel)"

### Phase 3 — Capability proof

Goal: for each Standard or Config item in the gap matrix, collect concrete evidence (module name, model/field, demo step or screenshot reference).

For each Standard/Config item, invoke by producing:

> "Chứng minh Odoo hỗ trợ yêu cầu: [requirement text]. Cung cấp: tên module, model/field liên quan, bước demo cụ thể (3 bước tối đa). Phiên bản Odoo: [from context or ask user]."

This auto-fires the `odoo-capability-proof` skill (or `odoo-feature-check` as fallback). Batch all Standard/Config items; show consolidated proof list.

If technical code evidence is needed for an Extension-level item (user requests it), the main agent MAY spawn an odoo-coder subagent:

> Agent tool brief: "KHÔNG invoke Skill tool. KHÔNG spawn sub-agent. CHỈ Read/Grep/Glob/Edit/Write. Task: generate a minimal Odoo 17 Python snippet demonstrating [capability]. Context: [item context]."

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

**Gate 3:** "Proof package đủ chưa? (yes / iterate / cancel)"
- iterate → specify which item needs more evidence; re-run that item only

### Phase 4 — Objection pre-empt

Goal: anticipate 2-3 likely objections from the prospect and prepare counter-talking-points.

Based on the raw prospect input + gap matrix, identify the most probable objections. Common archetypes (adapt to actual input):
- "Odoo không đủ enterprise / thiếu tính năng X"
- "Không có tuân thủ quy định Việt Nam (thuế, BVDLCN, hóa đơn điện tử)"
- "Chi phí tổng thể (TCO) cao hơn giải pháp hiện tại"
- "Rủi ro migration dữ liệu từ hệ thống cũ"
- "Năng lực triển khai / hỗ trợ địa phương"

For each identified objection (2-3 max), invoke:

> "Khách hàng phản đối: [objection text]. Chuẩn bị counter-talking-point: thừa nhận mối lo, cung cấp bằng chứng cụ thể, đề xuất bước tiếp theo giảm rủi ro. Phong cách: [primary contact role từ Phase 0]."

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

**Gate 4:** "Counter-talking-points đã ổn chưa? (yes / edit / cancel)"

### Phase 5 — Assemble proposal draft

Goal: produce the complete bid response document.

Using all Phase 1-4 outputs, compose the full proposal. Default language: Vietnamese. Structure:

```
1. Thư ngỏ (Cover letter)         — 1 paragraph, addressed to primary contact role
2. Tóm tắt điều hành              — Pain points understood, proposed solution summary
3. Bảng gap matrix (Phase 2 output, formatted as Markdown table)
4. Danh sách bằng chứng năng lực  — Phase 3 output, grouped by module
5. Phản hồi phản đối dự kiến      — Phase 4 objection playbook, inline
6. Lộ trình & hạng mức chi phí    — Timeline estimate (S/M/L weeks from gap matrix) + cost tier label (S/M/L, NO currency figures)
7. Bước tiếp theo                  — CTA: book demo / technical workshop / commercial proposal
```

For Extension/Custom items, include a note: "Các hạng mục phát triển tùy chỉnh sẽ được báo giá riêng sau khi xác nhận phạm vi kỹ thuật."

**Phase 5 output:** Show full draft inline (collapsible if long). Confirm close date and cost tier label are consistent with Phase 0 inputs.

**Gate 5:** "Proposal sẵn sàng gửi chưa? (yes — lưu file + xuất / iterate / cancel)"
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

1. Note the failure inline: "⚠ [Skill name] không khả dụng. Tiếp tục với nhập liệu thủ công."
2. Show the expected output template for that phase as an empty form.
3. Ask the user to fill in the blanks directly in the conversation.
4. Mark all manually supplied items as `[unverified — manual input]` in the proposal output.
5. Continue to the next phase as normal.

The proposal is still produced; unverified items are clearly flagged so the user knows which claims need additional substantiation before sending.

## Examples

### Example 1 — SME distribution company (deal size M)

**User types:**
```
/odoo-bid-respond Khach-A
```

**Phase 0:** Command reads no `.odoo-ai/context.md`. User confirms manual mode. User pastes email: "Công ty chúng tôi đang tìm giải pháp quản lý bán hàng, kho hàng, và kế toán cho 15 nhân viên. Hiện đang dùng Excel. Cần xuất hóa đơn điện tử theo TT78."

Phase 0 collects: close date Q4 2026, size M, primary contact CFO.

**Phase 1 output (summary):**
- Industry: Phân phối
- Pain points: Excel thủ công, thiếu tự động hóa kho, không có hóa đơn điện tử
- Success criteria: Hóa đơn điện tử TT78, báo cáo kho real-time
- Relevant modules: sale, stock, account, l10n_vn
- Risk: medium — dữ liệu Excel migration

**Gate 1:** User confirms.

**Phase 2 output (excerpt):**
| Requirement | Type | Effort |
|---|---|---|
| Quản lý bán hàng | Standard | S |
| Hóa đơn điện tử TT78 | Config | M |
| Báo cáo kho real-time | Standard | S |

**Gate 2-5:** User confirms each. Final proposal written to `.odoo-ai/bids/Khach-A-2026-05-28.md`.

---

### Example 2 — Manufacturing prospect, objection-heavy (deal size L)

**User types:**
```
/odoo-bid-respond Khach-B
```

User pastes meeting notes raising objections: "Odoo không có MRP mạnh như SAP, lo ngại về tuân thủ dữ liệu cá nhân (BVDLCN 91/2025), và chi phí triển khai."

**Phase 4 objections identified:**
1. "MRP không đủ mạnh so với SAP"
2. "Tuân thủ BVDLCN 91/2025"
3. "TCO cao"

`odoo-objection-handler` fires for each. Counter-talking-points:
- MRP: mrp + quality + maintenance modules; reference Viindoo manufacturing customer (abstract: Khach-ref-1).
- BVDLCN: Odoo 17 data residency + consent fields; Viindoo local hosting option.
- TCO: 3-year TCO model vs. legacy — license + implementation + support tier.

Final proposal includes all three rebuttals inline.

## What this command does NOT do

- Does NOT send emails. Phase 6 saves a draft file; the user sends it manually.
- Does NOT access or modify Odoo source code, CRM databases, or live ERP instances.
- Does NOT persist prospect data across sessions. Re-run from Phase 0 in a new session if needed (or supply `.odoo-ai/context.md` as a warm-start).
- Does NOT replace human judgment on commercial pricing, discount authority, or go/no-go strategic decisions.
- Does NOT guarantee OSM tool availability. All phases degrade gracefully to manual input when OSM is unreachable.
