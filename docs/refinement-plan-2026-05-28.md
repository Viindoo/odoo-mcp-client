# Plan: Refine `odoo-mcp-client` into an Odoo/Viindoo AI Workforce Toolkit

> **Date:** 2026-05-28
> **Owner:** main agent (orchestrator) + human (David Tran, CEO Viindoo)
> **Plan ID:** curious-riding-lemon
> **Repo target:** `odoo-mcp-client` (this repo, v0.8.0 → v1.0.0)
> **Plan file (post-approval, in-repo):** `docs/refinement-plan-2026-05-28.md` (mirror of this file, committed)
> **Survey ground truth:** `/tmp/odoo-mcp-client-survey/01-07.md`

---

## Context

### Vấn đề

`odoo-mcp-client` hôm nay là thin client mirror cho server-side OSM (24 tool + 7 resource), với 15 skill rất lệch về engineering (19/24 tool là dev-only). Vision sản phẩm: biến nó thành "AI workforce" toolkit nơi mỗi AI agent đóng vai một specialist (engineer / sales / marketing / strategy / operations / customer-success) để một-người-công-ty Odoo/Viindoo có thể chạy end-to-end mọi việc, không chỉ coding.

### Tại sao bây giờ

1. Production server OSM đã live + ổn định (v0.8.0, 24 tool + 7 resource).
2. Khoảng trống lớn nhất theo Top-3 leverage analysis: **Sales** (zero AI, mất deal hằng ngày), **Strategy** (CEO làm 1 mình), **Engineering** (đã memory-rich → ROI nhân lên).
3. KWP của Anthropic (11 plugin production) là precedent rõ ràng cho cách build "AI workforce" với skill-only architecture, an toàn depth-rule.

### Outcome mong muốn

- Mỗi prompt thô của user (VI/EN tự nhiên, không cần biết tên skill) đi qua main agent → match skill description → chạy specialist phù hợp.
- 8 specialist persona phủ đủ work-domain quan trọng của Viindoo SME.
- Maintenance debt giảm: 1 server-surface schema sinh ra routing matrix + IDE snippet + dep map (thay vì sửa tay ≥5 file).
- Bảo mật: pre-commit hook + CI grep ngăn rò 8 nhóm thông tin nhạy cảm.
- Multi-runtime parity: Claude Code (primary) + Codex + Gemini.

### Quyết định kiến trúc đã chốt với human

1. **Persona = skill-default** (theo precedent KWP: 100% production plugin là skill-only, depth 1). **2 ngoại lệ bundle (agent+skill)**: `odoo-coder` + `odoo-code-reviewer` — cần restricted-tool autonomy.
2. **8 persona**: Engineer + Coder + Code-Reviewer + Pre-Sales + Sales AE + Marketer + Strategist + Onboarding-Concierge (đảm nhiệm cả Customer-Success + Ops cho one-man-company).
3. **Depth rule**: main → skill/command → subagent (subagent KHÔNG invoke skill, KHÔNG spawn nested). Mọi subagent prompt phải có dòng chỉ thị này.
4. **Plan file** committed vào repo (`docs/refinement-plan-2026-05-28.md`) để cross-runtime đều đọc được.

### Phasing

| Phase | Tên | Goal | Effort estimate |
|---|---|---|---|
| **A** | Foundation | Generator SSOT + dep map + router skill + onboarding skill | 1-2 phiên |
| **B** | Specialists | Restructure 15 skill + add 7-8 skill mới cho persona thiếu | 2-3 phiên |
| **C** | Workflows | ≥5 slash command chain skill thành recipe | 1-2 phiên |
| **D** | Polish | Multi-runtime smoke test + VI sweep + confidentiality CI + README | 1 phiên |

Sau mỗi phase: human approve → commit + push → next phase.

---

## Subagent orchestration ground rules (áp dụng mọi phase)

### Depth-rule contract (BẮT BUỘC chèn vào mọi subagent prompt)

```
DEPTH RULE: Bạn là subagent ở depth 1. KHÔNG được:
- Invoke Skill tool
- Spawn nested subagent (Agent tool)
- Gọi /skill-creator hoặc bất kỳ slash command nào tự launch subagent

ĐƯỢC dùng: Read, Grep, Glob, Bash (read-only trừ khi prompt cho phép), Edit, Write, WebFetch, mcp__odoo-semantic__*, mcp__ollama-delegate__*.
```

### File-ownership preflight (BẮT BUỘC mọi parallel wave)

Trước khi launch parallel subagent, main phải verify mỗi subagent có disjoint file-write set (không 2 subagent cùng ghi 1 file). Nếu trùng → serialize hoặc merge subagent.

### Git Discipline (đã có trong CLAUDE.md, nhắc lại)

- Principal branch lock: KHÔNG `git checkout/switch/commit/rebase` trên `master` của `odoo-mcp-client` trừ khi human nêu tên branch.
- Mọi subagent prompt: "DO NOT git checkout/switch/commit; use existing branch or worktree as instructed".
- Phase work làm trên feature branch (vd `refine/phase-a-foundation`) hoặc trên master sau human approve — main agent xin xác nhận trước commit.

### Model-tier rule of thumb

- **Sonnet** (default): viết SKILL.md mới, generator Python, code logic, persona skill có domain knowledge.
- **Haiku**: inventory, grep audit, sửa boilerplate, validate format, đọc nhiều file rút context, sửa nhỏ kiểu add `## Out of Scope` section.
- **Opus**: không dùng trong plan này (không có cross-file refactor lớn đến mức cần Opus).

### Confidentiality brief (BẮT BUỘC mọi subagent động Viindoo content)

```
Bạn đang làm việc trong repo PUBLIC (odoo-mcp-client). CẤM write/commit 8 nhóm:
1. CEO info (David Tran personal details, salary, equity)
2. Customer (tên thật, deal size, ACV)
3. Market (pricing figures, revenue numbers)
4. Pricing (specific VND/USD figures)
5. Roadmap (unannounced features, dates)
6. Marketing (unpublished campaign, draft messaging)
7. OKR (KR numbers, target figures)
8. Vault path (/home/tuan/git/obsidian-vault/, /home/tuan/...)

Đọc nội bộ OK; output ghi vào repo public chỉ được aggregate/abstract.
```

---

## Phase A — Foundation

### Goal

Đặt nền tảng kỹ thuật trước khi đụng vào skill persona: generator SSOT, dependency map, router skill, onboarding skill.

### Artifacts

| # | File path | Purpose |
|---|---|---|
| A1 | `generator/server-surface.json` | SSOT cho 24 tool + 7 resource (schema theo `07-mcp-client-pattern-deep.md` §"SSOT generator schema") |
| A1 | `generator/gen_surface.py` | Đọc `server-surface.json` → emit routing matrix + per-skill `## MCP tools` section (markers `<!-- BEGIN GENERATED TOOLS -->` / `<!-- END GENERATED TOOLS -->`) + IDE snippet tool list |
| A1 | `Makefile` (extend) | Target `make gen` chạy `gen_surface.py`; `make gen-check` so sánh `git diff` |
| A2 | `generator/skill_tool_deps.json` | Map skill → list MCP tool dùng + min_server_version (schema xem `07-mcp-client-pattern-deep.md` §"Skill↔tool dependency map") |
| A2 | `generator/check_deps.py` | CI script: fail nếu skill ref tool không có trong surface |
| A2 | `.github/workflows/validate.yml` (extend) | Thêm step "Dependency check" gọi `check_deps.py` |
| A3 | `skills/odoo-router/SKILL.md` | Silent disambiguation concierge với routing table ≥15 entry (sẽ grow ở Phase B); pushy trigger cho vague intent |
| A4 | `skills/odoo-onboard/SKILL.md` | Bootstrap context → `.odoo-ai/context.md`; add `.gitignore` entry; probe version/profile/modules |
| A4 | `tests/test_onboard_context_schema.py` | Validate `.odoo-ai/context.md` schema |

### Topology + DAG

```
                  [Main orchestrator (depth 0)]
                            |
              +-------------+--------------+
              |             |              |
        Wave A.1 (parallel, disjoint files)
              |             |              |
          A1 sonnet     A3 sonnet      A4 sonnet
          (generator) (router skill) (onboard skill)
              |             |              |
              +------+------+------+-------+
                            |
                  Wave A.2 (sequential, after A1)
                            |
                       A2 haiku
                     (deps map + CI)
                            |
                  Wave A.3 (verify, main read-only)
                            |
                    make gen + make gen-check
                            |
                  Human approve → commit feature branch
```

### Subagent briefs (template — dùng /skill-creator cho A3+A4 ở Wave A.1)

**Quan trọng**: `/skill-creator` là skill self-launch subagent → CHỈ gọi từ main (depth 0). Vì main muốn produce A3+A4 ở wave parallel, main có 2 lựa chọn:
- **Option X (đề xuất)**: Main invoke `/skill-creator` 1 lần cho A3, 1 lần cho A4, sequentially (mỗi /skill-creator block khoảng 10-15 phút). Trong khi đó A1 chạy nền (Sonnet subagent background). A2 chạy sau A1.
- **Option Y**: Main launch A3+A4 dưới dạng plain Sonnet subagent (bypass /skill-creator), không có eval/benchmark. Nhanh hơn nhưng skip quality gate. Có thể chạy /skill-creator optimize ở Phase D.

→ **Đề xuất Option X** vì A3 (router) và A4 (onboard) là 2 skill foundation, sai trigger description sẽ phá toàn bộ Phase B. Eval/benchmark đáng tiền.

#### A1 — Generator (Sonnet subagent, background)

Brief skeleton:
```
Context: Build SSOT generator for odoo-mcp-client tool surface. Source: server-surface.json (you'll create the initial version by parsing existing docs/reference/mcp-tool-routing.md + 15 skills' ## MCP tools sections). Output: gen_surface.py + initial server-surface.json + Makefile targets.

Schema spec: see /tmp/odoo-mcp-client-survey/07-mcp-client-pattern-deep.md §"SSOT generator schema".

Tasks:
1. Read all 15 skills' ## MCP tools section + docs/reference/mcp-tool-routing.md → extract 24 tools + 7 resources.
2. Build server-surface.json with per-tool record (name, version_added, description, persona_tags, params, example, routing_keywords).
3. Write gen_surface.py: read server-surface.json, emit:
   - docs/reference/mcp-tool-routing.md (replace hand-written)
   - Per-skill ## MCP tools section (use marker pattern, NEVER touch other sections)
   - snippets/cursor-rules.md, snippets/openai-gpt-instructions.md, snippets/gemini-gem-instructions.md tool list
4. Extend Makefile: `make gen` runs generator; `make gen-check` runs gen + git diff --exit-code.
5. Run `make gen` once; verify idempotent (run twice → same output).

Constraints: [DEPTH RULE] [CONFIDENTIALITY BRIEF] [GIT DISCIPLINE — no commits].

File write set: generator/server-surface.json, generator/gen_surface.py, Makefile (edit), docs/reference/mcp-tool-routing.md (regen), skills/*/SKILL.md (only between markers), snippets/cursor-rules.md, snippets/openai-gpt-instructions.md, snippets/gemini-gem-instructions.md (only between markers).

Report back ≤300 words: schema decisions, marker convention, idempotency proof, files changed.
```

#### A2 — Dependency map (Haiku subagent, after A1)

Brief skeleton:
```
Context: A1 has produced generator/server-surface.json + 15 skills with regenerated ## MCP tools sections. Build skill↔tool dependency map for CI assertion.

Tasks:
1. Read generator/server-surface.json + each skills/*/SKILL.md ## MCP tools section.
2. Generate generator/skill_tool_deps.json per schema in /tmp/odoo-mcp-client-survey/07-mcp-client-pattern-deep.md §"Skill↔tool dependency map".
3. Write generator/check_deps.py per spec in same file.
4. Extend .github/workflows/validate.yml with "Dependency check" step.
5. Verify check_deps.py exits 0 on current state, exits 1 if we simulate a tool removal.

Constraints: [DEPTH RULE] [CONFIDENTIALITY BRIEF] [GIT DISCIPLINE].

File write set: generator/skill_tool_deps.json, generator/check_deps.py, .github/workflows/validate.yml (edit).

Report back ≤200 words: deps count, simulated-removal verification result.
```

#### A3 — Router skill (Main invokes /skill-creator)

`/skill-creator` brief (Mode 1: Create Skill from Scratch):
```
SKILL-NAME: odoo-router
INTENT: Silent disambiguation concierge — match vague Odoo/Viindoo intent (VI+EN) to exactly ONE target skill, recommend with one-sentence justification, ask confirmation before triggering. Does NO work itself.

TRIGGER_PHRASES (should-fire):
- "tư vấn Odoo", "Odoo có gì không", "check our Odoo system", "help with Odoo"
- "tao có 1 prompt cần xử lý nhưng không rõ skill nào"
- Any prompt where ≥2 of these skill descriptions could plausibly match: odoo-version-diff vs odoo-feature-highlights vs odoo-deprecation-audit vs odoo-capability-proof vs odoo-objection-handler
- Pushy: if user prompt is short (<10 words) AND mentions Odoo/Viindoo AND no specific intent keyword → fire router

SHOULD-NOT-FIRE:
- Clear specific intent already matched by 1 skill (e.g., "viết computed field cho sale.order" → odoo-coder directly)
- Non-Odoo questions
- Explicit slash command from user

OUTPUT_FORMAT: 1 recommended skill name + 1 one-sentence rationale + 1 confirmation question to user. NO actual work output.

SUCCESS_CRITERIA:
- Eval test: 10 ambiguous VI+EN prompts → router picks correct skill on ≥8/10
- Collision tests: 3 known collision pairs resolved correctly:
  - "viết phản hồi khách bảo Odoo không X" → odoo-objection-handler (not odoo-capability-proof)
  - "khách hỏi gì khác v16 v17" → odoo-version-diff (not odoo-feature-highlights/odoo-deprecation-audit)
  - "tóm tắt tính năng Odoo 18 cho slide" → odoo-feature-highlights (not odoo-version-diff)

Routing table (full 15-entry table from /tmp/odoo-mcp-client-survey/07-mcp-client-pattern-deep.md §A3) embedded in SKILL.md body.

DEPTH RULE: router skill itself does NOT invoke Skill tool, NOT spawn subagent. Just text-output recommendation.
```

#### A4 — Onboarding skill (Main invokes /skill-creator)

`/skill-creator` brief (Mode 1: Create Skill from Scratch):
```
SKILL-NAME: odoo-onboard
INTENT: Bootstrap Odoo project context on first use. Probe Odoo environment (version, custom modules, active profile), persist findings to .odoo-ai/context.md, add .gitignore entry. Makes all subsequent skills context-aware.

TRIGGER_PHRASES:
- "set up odoo-semantic for this project", "initialize Odoo context", "first time setup"
- "tao mới clone repo Odoo về", "project mới, setup context"
- Any skill that needs .odoo-ai/context.md and finds it missing should output "Run odoo-onboard first"

SHOULD-NOT-FIRE:
- If .odoo-ai/context.md already exists AND last_updated < 30 days old → suggest "refresh context?" instead of full re-onboard
- For non-Odoo projects

OUTPUT_FORMAT: .odoo-ai/context.md (markdown with structured fields), .gitignore entry, summary report to user.

Context file schema (from /tmp/odoo-mcp-client-survey/07-mcp-client-pattern-deep.md §A4):
- odoo_version (probed via list_available_versions + user confirm)
- viindoo_profile (probed via list_available_profiles + user confirm)
- custom_modules (probed via check_module_exists on heuristic list from grep manifest files)
- team_prefix (extracted from custom module naming pattern)
- last_updated (ISO8601)

SUCCESS_CRITERIA:
- Eval: run onboard with mocked MCP responses → correct context.md
- Idempotent: run twice → no duplicate, last_updated refreshed
- .gitignore entry added if not present
- All 15 existing skills can be updated (Phase B) to read .odoo-ai/context.md as Round -1 (before Round 0: set_active_version)

DEPTH RULE: onboard skill calls MCP tools directly + writes file. NO subagent spawn.
```

### Acceptance criteria — Phase A

- **AC-A1**: `make gen` chạy idempotent. `git diff` rỗng sau khi chạy lần 2.
- **AC-A2**: `python3 generator/check_deps.py` exit 0. Simulate tool removal (xoá 1 entry trong surface) → exit 1.
- **AC-A3**: `odoo-router` skill pass 8/10 eval prompt + 3/3 collision test. Có routing table 15 entry.
- **AC-A4**: `odoo-onboard` skill create đúng `.odoo-ai/context.md` schema; idempotent; thêm `.gitignore` entry.
- **AC-A5**: 15 skill cũ vẫn pass `make test` sau khi A1 regen `## MCP tools` section.
- **AC-A6**: CI green trên feature branch `refine/phase-a-foundation`.

### Risk + mitigation — Phase A

| Risk | Mitigation |
|---|---|
| A1 generator phá nội dung handwritten trong `## MCP tools` section (vd routing hint vào skill khác) | Marker pattern (`<!-- BEGIN GENERATED TOOLS -->`/`<!-- END GENERATED TOOLS -->`); generator chỉ ghi giữa marker. Diff review trước commit. |
| A3 router fire quá rộng → over-triggering, fire trên prompt rõ ràng | `/skill-creator` Mode 5 (description optimization) ở Phase D. Set should-not-trigger queries cẩn thận. |
| A4 onboard ghi file vào root project Odoo của user → pollute git status | Schema bắt buộc `.odoo-ai/` (gitignored); kiểm tra `.gitignore` trước write. |
| A2 deps map manual với 15 skill → sai sót | Generator A1 auto-emit deps từ marker-parsed tool list (best); fallback hand-write nếu A1 chưa support. |

---

## Phase B — Specialists (8 persona)

### Goal

Restructure 15 skill hiện có + bổ sung skill mới cho 3 persona đang thiếu (Sales AE / Marketer / Strategist) để đủ 8 persona.

### Mapping persona → skill

| Persona | Skill set (sau Phase B) | Trạng thái |
|---|---|---|
| **1. Engineer** (general dev workflow) | `odoo-override-finder`, `odoo-deprecation-audit`, `odoo-deploy-checklist` (NEW) | 2 stay + 1 new |
| **2. Coder** (write code) | `odoo-coder` (upgrade to agent+skill bundle), `odoo-frontend-coder` (merge js+owl) | 1 bundle + 1 merge |
| **3. Code-Reviewer** (review code) | `odoo-code-reviewer` (upgrade to agent+skill bundle) | 1 bundle |
| **4. Pre-Sales Consultant** | `odoo-feature-check`, `odoo-gap-analysis`, `odoo-capability-proof`, `odoo-addon-diff` | 4 stay |
| **5. Sales AE** | `odoo-objection-handler`, `odoo-deal-followup` (NEW), `odoo-discovery-summarize` (NEW) | 1 stay + 2 new |
| **6. Marketer** | `odoo-feature-highlights`, `odoo-content-draft` (NEW), `odoo-campaign-plan` (NEW) | 1 stay + 2 new |
| **7. Strategist** | `odoo-risk-overview`, `odoo-customization-inventory`, `odoo-competitive-brief` (NEW) | 2 stay + 1 new |
| **8. Onboarding-Concierge** | `odoo-onboard` (từ Phase A), `odoo-router` (từ Phase A) | đã có |
| Bonus (cross-cutting) | `odoo-version-diff` (dual-persona Dev+Marketer, stay) | stay |

**Tổng skill sau Phase B**: 13 stay-restructured + 2 bundle + 7 new = **22 skill + 2 agent** (so với 15 skill + 1 agent ban đầu).

### Artifacts

| Wave | Sub-task | File path |
|---|---|---|
| B.1 | Merge js+owl → frontend-coder | `skills/odoo-frontend-coder/SKILL.md` (new), delete `skills/odoo-js-coder/`, `skills/odoo-owl-coder/` |
| B.1 | Upgrade odoo-coder to bundle | `skills/odoo-coder/SKILL.md` (slim down to routing+context), `agents/odoo-coder.md` (new — restricted tools: Read, Grep, mcp__odoo-semantic__*, mcp__ollama-delegate__*) |
| B.1 | Upgrade odoo-code-reviewer to bundle | `skills/odoo-code-reviewer/SKILL.md` (slim), `agents/odoo-code-reviewer.md` (new) |
| B.1 | Add standalone-first fallback + Out-of-Scope section | All 13 existing skills (edit body) |
| B.2 | New Sales AE skills | `skills/odoo-deal-followup/SKILL.md`, `skills/odoo-discovery-summarize/SKILL.md` |
| B.2 | New Marketer skills | `skills/odoo-content-draft/SKILL.md`, `skills/odoo-campaign-plan/SKILL.md` |
| B.2 | New Strategist skill | `skills/odoo-competitive-brief/SKILL.md` |
| B.2 | New Engineer skill | `skills/odoo-deploy-checklist/SKILL.md` |
| B.3 | Regen routing matrix + deps | `make gen` (auto via A1) |
| B.3 | Update router routing table | `skills/odoo-router/SKILL.md` (add 7 new entries) |
| B.3 | Update tests | `tests/test_skill_format.py` extend (check Out-of-Scope + Persona section) |

### Topology + DAG

```
                 [Main orchestrator]
                       |
        Wave B.1 (parallel, 4 sonnet)
        |              |              |              |
   B.1a merge      B.1b bundle    B.1c bundle    B.1d standalone-first
   frontend-coder  odoo-coder     odoo-reviewer  audit (haiku)
        |              |              |              |
        +-----+--------+------+-------+--------+-----+
                       |
        Wave B.2 (parallel, 6 sonnet — 1 per new skill)
        |    |    |    |    |    |
       B.2a B.2b B.2c B.2d B.2e B.2f
        |    |    |    |    |    |
        +----+----+----+----+----+
                       |
        Wave B.3 (sequential, main + haiku)
        |              |
    regen +        update router
    deps           routing table
        |              |
                  Human approve → commit
```

**File-ownership preflight check** (mỗi wave):
- Wave B.1: 4 subagent ghi DISJOINT skill files. B.1d (standalone-first) edit body của 13 file CŨ — phải tránh đụng skill nào đang trong wave B.1a-c (frontend-coder, odoo-coder, odoo-code-reviewer). → Mitigation: B.1d edit 10 skill (loại trừ 3 đang restructure); 3 skill restructure tự thêm standalone-first trong process B.1a-c.
- Wave B.2: 6 subagent ghi 6 file MỚI — disjoint.
- Wave B.3: serialize (main coordinate).

### Subagent briefs

Mỗi new skill (B.2a-f) dùng `/skill-creator` Mode 1 với template:
```
SKILL-NAME: odoo-<persona>-<specialty>
INTENT: <one sentence>
TRIGGER_PHRASES: <8-10 VI + 8-10 EN>
SHOULD-NOT-TRIGGER: <near-miss phrases>
OUTPUT_FORMAT: <markdown template>
SUCCESS_CRITERIA:
- Eval 5 prompts → correct output structure
- Standalone-first: skill works when OSM unreachable (manual paste fallback)
- Has ## Out of Scope section naming adjacent skill
- Has ## Persona section

DEPTH RULE: skill calls MCP tools directly. NO subagent spawn. NO skill invoke.

CONFIDENTIALITY: Examples may use Viindoo context but abstract (no real customer name, real pricing, real OKR figure).
```

Mỗi bundle (B.1b, B.1c) brief:
```
Context: Upgrade existing skill (odoo-coder OR odoo-code-reviewer) to agent+skill bundle.

Tasks:
1. Read existing skills/<name>/SKILL.md fully.
2. SKILL.md SLIM DOWN: keep trigger description + routing logic + ## Out of Scope + brief context. Move execution detail (Round 0-4) to agent.
3. CREATE agents/<name>.md per schema in /tmp/odoo-mcp-client-survey/06-kwp-harness-deep.md §Appendix.
   - Restricted tools: Read, Grep, Bash (read-only), mcp__odoo-semantic__*, mcp__ollama-delegate__* (no Write/Edit unless explicitly write-mode)
   - System prompt = full execution detail (rounds, MCP call sequence, output format)
   - MUST NOT contain instructions to spawn subagents or invoke skills (depth rule!)
4. SKILL.md ends with: "When user confirms intent, main agent invokes the `<name>` agent via Agent tool."
5. Run `make test` to verify skill format still passes.

CONSTRAINTS: [DEPTH RULE] [CONFIDENTIALITY BRIEF] [GIT DISCIPLINE].

Report back ≤250 words: line count delta (skill before/after), agent file structure, tests passing.
```

### Acceptance criteria — Phase B

- **AC-B1**: 22 skill + 2 agent tồn tại; `make test` pass.
- **AC-B2**: Mỗi skill có `## Persona` + `## Out of Scope` section (CI check trong `test_skill_format.py`).
- **AC-B3**: 2 agent bundle (`odoo-coder` + `odoo-code-reviewer`) chạy được qua Agent tool invocation; system prompt KHÔNG chứa skill/subagent instruction.
- **AC-B4**: `odoo-frontend-coder` xử lý cả v8-14 (legacy) lẫn v15+ (OWL) qua internal version gate.
- **AC-B5**: Router routing table được mở rộng thêm 7 entry cho skill mới.
- **AC-B6**: `make gen` regen deps map bao gồm 22 skill + 2 agent.
- **AC-B7**: Mỗi skill có "standalone fallback" branch (test bằng cách mock OSM unreachable → skill vẫn produce useful output từ user paste).

### Risk + mitigation — Phase B

| Risk | Mitigation |
|---|---|
| 6 new skill có trigger phrase trùng với 13 skill cũ → router confusion | `/skill-creator` Mode 3 (eval+benchmark) trên router sau Phase B; phase D có Mode 5 (description optimization). |
| Bundle agent vô tình có instruction "Spawn subagent" | Code review human-confirm trước commit; CI grep `agents/*.md` cho keyword "Agent tool" / "subagent" / "skill". |
| Standalone-first audit (B.1d) sửa nội dung skill mâu thuẫn với B.1a-c | File-ownership preflight loại trừ; B.1d chạy SAU B.1a-c hoàn tất (serialize chứ không parallel). |

---

## Phase C — Command-recipes (workflows)

### Goal

≥5 slash command chain skill thành recipe đa bước cho workflow phức tạp.

### Artifacts

| # | Command | Chain | File |
|---|---|---|---|
| C1 | `/odoo-bid-respond` | router → discovery-summarize → gap-analysis → capability-proof → proposal draft | `commands/bid-respond.md` |
| C2 | `/odoo-discovery-summarize` | (single skill wrapped — quick path) | `commands/discovery-summarize.md` |
| C3 | `/odoo-customer-followup-draft` | deal-followup → draft email | `commands/customer-followup-draft.md` |
| C4 | `/odoo-upgrade-plan-full` | risk-overview → deprecation-audit → version-diff → upgrade plan synthesis | `commands/upgrade-plan-full.md` (replaces `agents/odoo-upgrade-planner.md` — agent deprecated) |
| C5 | `/odoo-feature-positioning` | feature-check → addon-diff → competitive-brief → positioning copy | `commands/feature-positioning.md` |

### Topology

```
Wave C.1 (parallel, 5 sonnet — 1 per command)
  C1, C2, C3, C4, C5 (disjoint files)
        |
Wave C.2 (sequential, haiku)
  Deprecate old agents/odoo-upgrade-planner.md (mark stale + redirect to /odoo-upgrade-plan-full)
        |
Human approve → commit
```

### Subagent brief template (per command)

```
Context: Build slash command /odoo-<name> as a recipe chaining N skills with checkpoint gates.

Per KWP Pattern P5 (Command-as-Recipe): command body = imperative instructions for main agent to run sequentially through skills, with explicit user approval gate before each side-effect.

Tasks:
1. Read commands/connect.md as format reference (134 lines, hard rules style).
2. Write commands/<name>.md per spec:
   - YAML frontmatter (name, description, args if any)
   - Phase 0: parse $ARGUMENTS or prompt user
   - Phase 1-N: each phase invokes ONE skill (via natural-language trigger that fires that skill's description match)
   - Between phases: show summary + ask "continue?" if side-effect ahead
   - Final phase: assemble + output
3. Add to plugin.json commands list.
4. Smoke test: type the slash command with sample args, verify expected skill chain triggered.

CONSTRAINTS: [DEPTH RULE — command can spawn subagent via Agent tool but skills it invokes must not] [CONFIDENTIALITY BRIEF] [GIT DISCIPLINE].

Report back ≤200 words: command flow chain, args spec, smoke test result.
```

### Acceptance criteria — Phase C

- **AC-C1**: 5 command tồn tại trong `commands/` + declared trong `.claude-plugin/plugin.json`.
- **AC-C2**: Mỗi command có happy-path smoke test (manual: type command, verify chain).
- **AC-C3**: Standalone-fallback test (1 command, mock OSM offline → vẫn produce output từ user paste).
- **AC-C4**: `agents/odoo-upgrade-planner.md` deprecate (file giữ lại nhưng có dòng `<!-- DEPRECATED: use /odoo-upgrade-plan-full -->`).
- **AC-C5**: `make test` + `make gen-check` green.

### Risk + mitigation — Phase C

| Risk | Mitigation |
|---|---|
| Command body trở thành nơi nhồi domain knowledge → phá pattern KWP (skill = knowledge, command = recipe) | Code review: command body chỉ chứa flow control + approval gate; mọi domain knowledge ở skill referenced. |
| Approval gate mệt user (5 gate liên tiếp = annoying) | Gộp gate: chỉ gate trước side-effect (write file, send email); intermediate read-only step auto-pass. |

---

## Phase D — Multi-runtime parity + VI polish + docs

### Goal

Sản phẩm-ready: chạy được trên Claude Code + Codex + Gemini; user-facing VI; confidentiality enforced; README có section "Một-người-công-ty".

### Artifacts

| # | Sub-task | File |
|---|---|---|
| D1 | Multi-runtime smoke test | `tests/smoke/runtime_parity.md` (manual checklist for 10 representative skill on CC + Codex + Gemini) |
| D2 | VI polish sweep | All user-facing strings in 22 skill + 5 command + README (audit cho VI tiếng Việt đầy đủ dấu) |
| D3 | README "Một-người-công-ty" section | `README.md` (extend) |
| D4 | Confidentiality pre-commit hook | `.githooks/pre-commit` (grep 8 nhóm cấm) |
| D5 | Confidentiality CI workflow | `.github/workflows/confidentiality-scan.yml` |
| D6 | Description optimization (Mode 5) cho router | Run `/skill-creator` Mode 5 trên `odoo-router` với 20 eval prompt |
| D7 | CHANGELOG entry v1.0.0 | `CHANGELOG.md` |
| D8 | Bump VERSION + plugin.json | 0.8.0 → 1.0.0 |

### Confidentiality CI grep patterns (D4 + D5)

Pre-commit + CI:
```bash
# Hardcoded path leakage
grep -rE "(/home/tuan/git/obsidian-vault|/home/tuan/\.|davidtran\.hp@gmail\.com)" \
  --include="*.md" --include="*.py" --include="*.json" --include="*.yaml" \
  . && exit 1 || true

# Customer/pricing/OKR numerics (soft check — informational, allow override)
grep -rE "(\\\$[0-9]{4,}|[0-9]{1,3}([,.][0-9]{3}){2,}\\s*(VND|USD)|OKR.*[0-9]{2}%)" \
  --include="*.md" \
  . && echo "WARNING: possible sensitive number" || true

# Vault wikilink leakage
grep -rE "\\[\\[(?!.*Viindoo Repo Map)" \
  --include="*.md" \
  . && echo "WARNING: vault wikilink in public repo" || true
```

Pre-commit hook: lệnh đầu tiên là hard-fail; 2 lệnh sau là warning.

### Topology

```
Wave D.1 (parallel, 2 sonnet + 1 haiku)
  D1 (smoke test author)  D2 (VI sweep)  D4+D5 (confidentiality hook + CI)
        |                      |                       |
        +----------+-----------+-----------+-----------+
                   |
Wave D.2 (main invokes /skill-creator Mode 5 for router)
                   |
              D6 (router desc optim)
                   |
Wave D.3 (haiku, sequential)
              D3 (README section) + D7 (CHANGELOG) + D8 (bump version)
                   |
              Human approve → commit + push + tag v1.0.0
```

### Acceptance criteria — Phase D

- **AC-D1**: 10 skill đại diện chạy được trên CC + Codex + Gemini (manual smoke checklist passes).
- **AC-D2**: VI sweep complete (audit log + sample-checked 5 random skill có VI đầy đủ dấu).
- **AC-D3**: README có section H2 "Một-người-công-ty: cách dùng AI specialist" với ≥3 use-case cụ thể.
- **AC-D4**: Pre-commit hook block commit nếu có hardcoded vault path.
- **AC-D5**: CI workflow confidentiality-scan green on master.
- **AC-D6**: Router skill description optimized — eval score ≥0.85 trên 20-query trigger set.
- **AC-D7**: CHANGELOG có entry v1.0.0 với mục Added/Changed/Removed.
- **AC-D8**: VERSION + plugin.json version đồng bộ 1.0.0; CI check version-sync green.

### Risk + mitigation — Phase D

| Risk | Mitigation |
|---|---|
| Codex/Gemini không hỗ trợ feature Claude Code (hook, skill-creator) → parity fail | Multi-runtime test chỉ check 10 skill core (trigger + execute + output); skip Claude-Code-specific features. Documented gap trong README. |
| VI sweep miss dấu ở deep section | Spot-check 5 random skill manually + grep `unicodedata` patterns nếu cần. |
| Confidentiality grep false-positive block commit hợp lệ | Hook có escape: commit message chứa `[allow-confidentiality-warning]` → bypass số/warning patterns. Hard-fail (vault path) không có bypass. |

---

## Verification — end-to-end test plan

Sau khi xong cả 4 phase, làm full E2E test:

### Test scenario 1 — "Sales AE flow"

```
User (raw VI prompt): "khách Acme muốn xem demo Odoo có làm được phê duyệt đa cấp cho mua hàng, đang dùng SAP, muốn so sánh effort migration. Mai có meeting."

Expected harness flow:
1. Main agent → match odoo-router (vague + multi-intent)
2. Router → recommend /odoo-bid-respond + ask confirm
3. User confirms → command runs:
   a. odoo-discovery-summarize (parse the prompt → discovery note)
   b. odoo-capability-proof (multi-level approval evidence)
   c. odoo-gap-analysis (SAP-to-Odoo migration effort)
   d. odoo-objection-handler (write VI response paragraph)
   e. Assemble proposal email + technical evidence + demo script

Pass: All 5 skill fire correctly, output is structured + VI + cite evidence.
```

### Test scenario 2 — "Engineering flow"

```
User: "client v15 muốn lên v17, cho tao plan upgrade chi tiết"

Expected:
1. Direct match: /odoo-upgrade-plan-full
2. Chain: odoo-risk-overview → odoo-deprecation-audit → odoo-version-diff → synthesize
3. Output: structured plan + effort estimate + risk table
```

### Test scenario 3 — "Strategy flow"

```
User: "viết board brief tháng 5 cho tình hình product"

Expected:
1. Router → odoo-competitive-brief OR odoo-business-pulse-equivalent
2. Single skill output: brief with sections (market, product, risks, asks)

(Phase B chỉ tạo 1 strategist skill mới; nếu user muốn /board-brief command thì add Phase C+ extension.)
```

### Test scenario 4 — "Onboarding flow"

```
User: "tao mới clone repo Odoo về"
Expected:
1. odoo-onboard fires
2. Probe + ask version → "17.0"
3. Probe modules → user confirms list
4. Write .odoo-ai/context.md
5. Suggest follow-up: "run /odoo-deploy-checklist next?"
```

### Verification commands

```bash
# Phase A
cd <repo-root>
make validate && make test && make gen-check && python3 generator/check_deps.py

# Phase B
# (run inside Claude Code session) - manual trigger test for each new skill

# Phase C
# (manual: type each /command, verify chain)

# Phase D
.githooks/pre-commit  # should pass on clean commit
# Manual: run 10 skills on Codex CLI + Gemini CLI

# Version sync check
test "$(cat VERSION)" = "$(jq -r .version .claude-plugin/plugin.json)"
```

---

## Memory writeback (post-execution)

Sau khi mỗi phase xong:
- **Phase A**: `vault-session-end` log → engineering domain, mention "Phase A foundation: generator SSOT + router + onboard delivered".
- **Phase B**: `vault-session-end` log + nếu pattern persona-bundle hữu ích → `vault-pattern-extract`.
- **Phase C**: `vault-orchestration-log` cho wave C.1 pattern (5-parallel-sonnet-command-recipe).
- **Phase D**: `vault-session-end` log + ghi note v1.0.0 release.

Mọi log: agent=`claude-code`, domain=`engineering`, link survey files trong evidence section.

---

## Open questions for future review (out-of-scope cho phase này)

1. **Hook**: KWP 0 production plugin dùng hook. Có nên add hook cho confidentiality check trước Write (PreToolUse)? → Phase E future scope.
2. **MCP for Viindoo ERP runtime**: ngoài OSM (static analysis), một MCP cho Viindoo live instance (XML-RPC) sẽ supercharge nhiều skill. → Roadmap.
3. **Vault MCP**: hiện tại skill không đọc được vault trực tiếp. Có nên có 1 read-only vault MCP cho Strategist/Sales? → Roadmap (cẩn thận confidentiality).
4. **Auto-billing per persona usage**: nếu một-người-công-ty thật sự thuê AI specialist, có nên có usage analytics per skill? → Out of scope, server team concern.

---

## Critical files — reuse map

Đã có sẵn (KHÔNG tạo mới, reuse):
- `Makefile` — extend với `gen` + `gen-check` target
- `tests/test_skill_format.py` — extend với check `## Persona` + `## Out of Scope`
- `.github/workflows/validate.yml` — add dep check step
- `docs/reference/mcp-tool-routing.md` — replaced by generator output
- `commands/connect.md` — format reference cho Phase C command structure
- 15 skill hiện có trong `skills/` — 11 stay-restructured, 2 merge, 2 upgrade-to-bundle

Existing patterns / utilities to reuse:
- Marker-based regen pattern (cần invent ở A1)
- DCO + CI workflow ở `.github/workflows/`
- Snippet self-containment pattern ở `snippets/` (regen via A1)
- Test skill format pattern ở `tests/test_skill_format.py`

---

## End-state inventory (sau khi xong Phase A-D)

| Component | Trước | Sau |
|---|---|---|
| Skills | 15 | 22 (13 restructured + 7 new + 2 from Phase A) |
| Agents | 1 (upgrade-planner, deprecate) | 2 (odoo-coder, odoo-code-reviewer bundle agents) |
| Commands | 1 (/connect) | 6 (/connect + 5 recipe) |
| Generators | 0 | 1 (gen_surface.py) |
| Dep maps | 0 | 1 (skill_tool_deps.json + CI check) |
| Hooks | 0 | 1 (pre-commit confidentiality) |
| CI workflows | 2 | 3 (+ confidentiality-scan) |
| Personas formalized | 5 (in docs/personas) | 8 (in code + docs) |
| Multi-runtime | CC primary | CC + Codex + Gemini |
| Version | 0.8.0 | 1.0.0 |

---

*End of plan. Awaiting human approval via ExitPlanMode.*
