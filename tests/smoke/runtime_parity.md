# Runtime Parity Smoke Test — odoo-mcp-client

Manual checklist to certify that the 10 representative `odoo-*` skills produce
functionally equivalent output across all three supported runtimes: Claude Code,
Codex CLI, and Gemini CLI. This document is the AC-D1 acceptance artifact for
Phase D multi-runtime parity. A human tester walks through the 30 cells
(10 skills x 3 runtimes), marks pass/fail, and records findings. The completed
copy becomes a dated snapshot of parity status at a specific release.

---

## Scope

### Skills under test (10)

Selected to cover the full persona spectrum and varying levels of MCP
dependency:

| # | Skill | Phase introduced | Persona | MCP dependency |
|---|-------|-----------------|---------|---------------|
| 1 | `intake` | A | All — universal front door / brainstorm + route | None (pure text routing) |
| 2 | `odoo-onboard` | A | All — context bootstrap | Read-only: `list_available_versions`, `list_available_profiles`, `set_active_version`, `set_active_profile` |
| 3 | `odoo-feature-check` | A | Pre-Sales Consultant | `check_module_exists`, `model_inspect`, `find_examples`, `suggest_pattern` |
| 4 | `odoo-gap-analysis` | A | Pre-Sales Consultant | `check_module_exists`, `model_inspect`, `find_examples`, `lookup_core_api`, `suggest_pattern` |
| 5 | `odoo-objection-handler` | A | Sales AE | `check_module_exists`, `find_examples`, `model_inspect`, `suggest_pattern` |
| 6 | `odoo-deal-followup` | B | Sales AE | None (deal context is user-provided) |
| 7 | `odoo-feature-highlights` | B | Marketer | `api_version_diff`, `find_examples` |
| 8 | `odoo-content-draft` | B | Marketer | Optional: `find_examples` (standalone-first capable) |
| 9 | `odoo-version-diff` | A | Engineer + Marketer | `api_version_diff`, `entity_lookup`, `lookup_core_api`, `model_inspect` |
| 10 | `odoo-deprecation-audit` | A | Engineer | `api_version_diff`, `entity_lookup`, `find_deprecated_usage`, `lookup_core_api`, `module_inspect` |

### Runtimes under test (3)

- **Claude Code (CC)** — primary runtime; skills auto-fire on description match
  via Anthropic harness.
- **Codex CLI** — OpenAI Codex CLI with plugin manifest loaded; skill invocation
  via prompt injection (no guaranteed description-match — see Known Gaps).
- **Gemini CLI** — Google Gemini CLI with plugin manifest loaded; similar
  invocation caveat.

### Coverage

**30 cells total** (10 skills x 3 runtimes). Each cell is independently
pass/fail. Results are recorded in the matrix tables below.

### NOT tested in this smoke

- **Commands** (`commands/*.md`): CC-only by design. `plugin.json` `commands:`
  key is a CC-specific harness concept. Codex/Gemini users must invoke the
  equivalent skill chain manually. Documented in Known Gaps.
- **Agent bundles**: depend on the Agent tool which is CC-native. Codex may
  support subagent spawn natively; Gemini typically does not. Documented in
  Known Gaps.
- **Eval harness** (`evals/*.json`): automated scoring requires `run_loop.py`
  (AC-D6, separate from this smoke).

---

## Prerequisites

Before beginning this checklist, confirm all of the following:

1. **Plugin installed in each runtime** per `docs/setup.md`:
   - Claude Code: `plugin.json` registered under `.claude-plugin/`.
   - Codex CLI: plugin directory referenced in `~/.codex/AGENTS.md` or
     runtime config.
   - Gemini CLI: plugin directory referenced in `~/.gemini/GEMINI.md`.

2. **OSM MCP server reachable**:
   - `mcp__odoo-semantic__list_available_versions` returns a non-empty list.
   - API key is valid (test with one quick `cli_help` call).

3. **`.odoo-ai/context.md` populated** in the test working directory (run
   `odoo-onboard` first, or manually create with target version and profile).
   This is required for skills that read Round -1 context.

4. **Test working directory** contains at least one `__manifest__.py` at depth
   1-3 (needed for onboard skill Step 1 manifest discovery).

5. **Tester has read access** to this file and write access to create a dated
   copy at the end (see Reporting section).

---

## Test protocol

### How to run a cell

1. Open the target runtime in a fresh session (no prior context for the skill).
2. Paste the canonical trigger prompt (VI or EN — pick one; both should work).
3. Observe the output. Do NOT prompt-engineer beyond the canonical prompt.
4. Score the cell against all four pass criteria (a-d below).
5. Mark `[x]` in the corresponding checkbox; record freeform notes if anything
   is unexpected.

### Pass criteria (all four must hold)

| Criterion | Description |
|-----------|-------------|
| **(a) Trigger fires** | The skill activates (CC: description-match auto-fire; Codex/Gemini: prompt injection invokes the skill body). |
| **(b) Output structure** | Output contains the key H2/H3 sections listed under "Expected output" for that skill. |
| **(c) No error / no hallucination** | No unhandled exception, no hallucinated tool name, no fabricated module/field that doesn't exist. |
| **(d) MCP resolves cleanly** | All MCP tool calls return a result (not a timeout or auth error); standalone-first fallback is acceptable only if OSM is explicitly unreachable. |

### Runtime-specific invocation notes

- **Claude Code**: trigger prompt is typed as-is into the Claude Code REPL.
  Description match is automatic.
- **Codex CLI**: prepend the skill name as a system cue if auto-match is absent.
  Example: `[odoo-feature-check] Customer asks whether Odoo supports multi-warehouse management`.
  If the runtime does not support description-match, criterion (a) is PASS if
  the skill body executes correctly after the cue — document the cue in Notes.
- **Gemini CLI**: same approach as Codex. Document any prompt prefix needed in
  Notes.

---

## Skill checklist (10 x 3)

---

### Skill 1: `intake`

> Phase A — universal front door / brainstorm + 4-tier route + soft-plan-gate. No MCP calls.

**Trigger prompt (VI)**: "I have a prompt to handle but I'm not sure which skill to use — Customer A has a question about Odoo manufacturing"

**Trigger prompt (EN)**: "I'm not sure which skill to use — Customer A has a question about Odoo manufacturing"

**Expected output**:
- Recommended skill name (exactly ONE, e.g. `odoo-feature-check`) OR brainstorm clarifying options if vague
- One-sentence justification citing the intent signal
- Proposed Plan gate: `approve / refine / cancel`
- NO actual work output (intake does not execute the target skill)

| Runtime | Pass? | Notes |
|---------|-------|-------|
| Claude Code | [ ] | |
| Codex CLI | [ ] | (does description auto-match fire? if not, note which prefix was needed) |
| Gemini CLI | [ ] | |

---

### Skill 2: `odoo-onboard`

> Phase A — project context bootstrap. Read-only MCP: `list_available_versions`,
> `list_available_profiles`, `set_active_version`, `set_active_profile`.

**Trigger prompt (VI)**: "I just cloned an Odoo repo, help me set up the context"

**Trigger prompt (EN)**: "first time using Odoo for this project — initialize Odoo context"

**Expected output**:
- Pre-flight check result (context present or absent)
- Available Odoo versions list from `list_available_versions`
- Detected module list (at least one `__manifest__.py` found)
- Conventions summary (module prefix, field naming, branch pattern)
- Confirmation that `.odoo-ai/context.md` was written and `.gitignore` updated
- "Suggest next" line pointing to a follow-up skill

| Runtime | Pass? | Notes |
|---------|-------|-------|
| Claude Code | [ ] | |
| Codex CLI | [ ] | |
| Gemini CLI | [ ] | |

---

### Skill 3: `odoo-feature-check`

> Phase A — Pre-Sales. MCP: `check_module_exists`, `model_inspect`,
> `find_examples`, `suggest_pattern`.

**Trigger prompt (VI)**: "Customer A asks whether Odoo supports multi-warehouse management, including in CE"

**Trigger prompt (EN)**: "Customer A asks whether Odoo supports multi-warehouse management in CE"

**Expected output**:
- `## Feature Availability Check` header with feature + version stated
- CE / EE / Viindoo edition matrix table (at least 3 columns)
- `### Verdict` block (Available / Partial / Not available)
- `### Evidence` block with module name, primary model, key fields
- `### Recommendation` block (1-2 sentences for client communication)

| Runtime | Pass? | Notes |
|---------|-------|-------|
| Claude Code | [ ] | |
| Codex CLI | [ ] | |
| Gemini CLI | [ ] | |

---

### Skill 4: `odoo-gap-analysis`

> Phase A — Pre-Sales. MCP: `check_module_exists`, `model_inspect`,
> `find_examples`, `lookup_core_api`, `suggest_pattern`.

**Trigger prompt (VI)**: "Customer A requires 3 features: (1) multi-level purchase approval, (2) serial number management, (3) e-signature integration — what does Odoo cover out of the box?"

**Trigger prompt (EN)**: "Customer A needs: (1) multi-level purchase approval, (2) serial number tracking, (3) e-signature integration — what does Odoo cover out of the box?"

**Expected output**:
- `## Gap Analysis Report` header with client label, version, requirement count
- Requirements matrix table with Standard coverage, Module, Effort type, Effort columns
- `### Effort summary` block grouping Standard / Config / Extension / Custom
- `### Total estimated effort` block with rationale paragraph
- `### Risk flags` section (at least one flag or explicit "none")

| Runtime | Pass? | Notes |
|---------|-------|-------|
| Claude Code | [ ] | |
| Codex CLI | [ ] | |
| Gemini CLI | [ ] | |

---

### Skill 5: `odoo-objection-handler`

> Phase A — Sales AE. MCP: `check_module_exists`, `find_examples`,
> `model_inspect`, `suggest_pattern`.

**Trigger prompt (VI)**: "Customer A says Odoo can't do multi-level approval — help me write a counter-response"

**Trigger prompt (EN)**: "Customer A says Odoo can't do multi-level approval — help me write a counter-response"

**Expected output**:
- `## Objection Response: "<objection>"` header
- `### Acknowledge` block (1 sentence)
- `### Counter-evidence` table (module exists, code example, key fields)
- `### Talking points` list (at least 2 concrete points)
- `### Suggested response (verbatim)` block — a ready-to-paste client paragraph

| Runtime | Pass? | Notes |
|---------|-------|-------|
| Claude Code | [ ] | |
| Codex CLI | [ ] | |
| Gemini CLI | [ ] | |

---

### Skill 6: `odoo-deal-followup`

> Phase B — Sales AE. No MCP dependency (deal context is user-provided).

**Trigger prompt (VI)**: "Customer A hasn't replied in a long time, the deal is stalled — help me write a follow-up"

**Trigger prompt (EN)**: "Customer A hasn't replied in a while, deal is stalled — help me draft a follow-up email"

**Expected output**:
- `## Deal status` block with risk level (red/yellow/green) + last touch + stage health
- `## Tags` line (ghosting, competitor-present, or other relevant tags)
- `## Next-best action` — one specific, actionable line
- `## Draft email (in Vietnamese)` with Subject line and four-paragraph structure:
  Warm reopener / Value reinforcement / Clear ask / CTA + close

| Runtime | Pass? | Notes |
|---------|-------|-------|
| Claude Code | [ ] | |
| Codex CLI | [ ] | |
| Gemini CLI | [ ] | |

---

### Skill 7: `odoo-feature-highlights`

> Phase B — Marketer. MCP: `api_version_diff`, `find_examples`.

**Trigger prompt (VI)**: "summarize the headline features of Odoo 17 for an internal slide deck next week, compared to Odoo 16"

**Trigger prompt (EN)**: "summarize Odoo 17 headline features for an internal slide deck, compared to Odoo 16"

**Expected output**:
- `## Feature Highlights: Odoo <version>` header
- `### Headline features` list with top 3-5 features, each with a business value sentence
- `### Feature comparison: <prev> vs <version>` table (Capability / prev / version / Business impact)
- `### Vietnamese market highlights` section (at least one Vietnam-relevant note or explicit "n/a")
- `### Use in sales deck` block with slide title suggestion and talking points

| Runtime | Pass? | Notes |
|---------|-------|-------|
| Claude Code | [ ] | |
| Codex CLI | [ ] | |
| Gemini CLI | [ ] | |

---

### Skill 8: `odoo-content-draft`

> Phase B — Marketer. Standalone-first: OSM optional (`find_examples`).

**Trigger prompt (VI)**: "write a LinkedIn post about project management features in Odoo 17, from the perspective of Vietnamese SMEs"

**Trigger prompt (EN)**: "draft a LinkedIn post about Odoo 17 project management features, targeting Vietnamese SMEs"

**Expected output**:
- Correct channel-native format (LinkedIn: single plain-text block + hashtags on last line)
- Content covers stated feature/topic with business angle (not generic marketing filler)
- `<TBD: verify ...>` placeholder present if OSM is unreachable (standalone fallback)
- `---` separator followed by `Suggestions for next steps` section (1-3 bullets)

| Runtime | Pass? | Notes |
|---------|-------|-------|
| Claude Code | [ ] | |
| Codex CLI | [ ] | |
| Gemini CLI | [ ] | |

---

### Skill 9: `odoo-version-diff`

> Phase A — Developer + Marketer cross-cutting. MCP: `api_version_diff`,
> `entity_lookup`, `lookup_core_api`, `model_inspect`.

**Trigger prompt (VI)**: "which APIs changed from Odoo v16 to v17, what should developers know before upgrading"

**Trigger prompt (EN)**: "which APIs changed between Odoo v16 and v17 — what should a developer know before upgrading"

**Expected output**:
- `## Version Diff: Odoo <from> → <to>` header with era label + migration complexity rating
- `### Added APIs` table (Symbol / Kind / Module / Description)
- `### Removed APIs` table (Symbol / Last version / Replacement / Migration note)
- `### Deprecated APIs` table (Symbol / Deprecation message / Replacement)
- `### Changed signatures` table (at least one row or explicit "none")

| Runtime | Pass? | Notes |
|---------|-------|-------|
| Claude Code | [ ] | |
| Codex CLI | [ ] | |
| Gemini CLI | [ ] | |

---

### Skill 10: `odoo-deprecation-audit`

> Phase A — Developer. MCP: `api_version_diff`, `entity_lookup`,
> `find_deprecated_usage`, `lookup_core_api`, `module_inspect`.

**Trigger prompt (VI)**: "audit our Odoo codebase before upgrading from v16 to v17 — find everything that will break"

**Trigger prompt (EN)**: "audit our Odoo codebase before upgrading from v16 to v17 — find everything that will break"

**Expected output**:
- `## Deprecation Audit Report` header with source/target version, era, file count, issue count
- Issues table (File / Line / Deprecated symbol / Replacement / Urgency) with BREAKING/WARN/STYLE tags
- `### Migration notes` section (at least 2 key patterns)
- `### Estimated migration effort` block with Low/Medium/High/Very High rating + rationale
- `### Recommended sprint plan` section (phased approach or single-sprint recommendation)

| Runtime | Pass? | Notes |
|---------|-------|-------|
| Claude Code | [ ] | |
| Codex CLI | [ ] | |
| Gemini CLI | [ ] | |

---

## Known multi-runtime gaps

The following features are **intentionally not parity** across runtimes. These
are not failures — they are architectural boundaries that should be documented,
not closed.

### Gap 1 — Commands (Claude Code only)

Files under `commands/*.md` define slash-command chains (`/odoo-bid-respond`,
`/odoo-customer-followup-draft`, `/odoo-discovery-quick`, etc.). The
`commands:` key in `.claude-plugin/plugin.json` is a CC-specific harness
concept.

**Impact on Codex/Gemini users**: commands are not available as slash entries.
Users must invoke the underlying skill chain manually in sequence, or use the
README "Use case" section as a scripted walkthrough.

**Mitigation (planned)**: README examples for each command show the equivalent
manual multi-turn sequence. These work across all runtimes.

### Gap 2 — Agent bundles

Agent workflows (e.g., multi-step proposal pipeline) depend on the Agent tool
which is native to Claude Code's harness. Codex CLI may support subagent
spawn via its own API; Gemini CLI typically does not expose an equivalent.

**Impact**: agent-bundle orchestration cannot be certified for parity. Tester
should mark agent-bundle cells as "N/A — Agent tool not available" rather than
FAIL.

**Mitigation**: agents are not included in this 10-skill smoke test. The gap is
noted here for completeness.

### Gap 3 — `/skill-creator` Mode 5 trigger optimization

The `run_loop.py` trigger eval harness invokes `claude -p` as a subprocess.
This is CC-specific. Codex/Gemini runtimes do not have an equivalent
`claude -p` subprocess API.

**Impact**: AC-D6 (trigger accuracy scoring) is CC-only. Parity check for
trigger optimization must be done manually using the canonical prompts in this
document.

### Gap 4 — Pre-commit hook (`.githooks/pre-commit`)

The bash pre-commit hook validates skill format before each commit. It requires
bash + git hooks infrastructure. Windows users without WSL cannot run it
natively.

**Impact**: Windows-native Codex/Gemini users need to manually run the
equivalent check (`python test_skill_format.py`) or rely on CI.

**Mitigation**: CI runs the same check on every push. The hook is advisory on
developer machines; CI is authoritative.

### Gap 5 — `.odoo-ai/context.md` write step (onboard skill)

`odoo-onboard` writes `.odoo-ai/context.md` to the local filesystem. All
three runtimes can execute this write via their respective file-write tool.
However, the exact tool name differs (CC: `Write`; Codex: file-write API;
Gemini: file-write API). If a runtime does not expose a file-write tool, the
onboard skill falls back to displaying the context block in-chat for the user
to save manually.

**Impact**: onboard skill body is portable; the write mechanism may vary.
Tester should accept in-chat display as PASS for criterion (b) if the runtime
lacks file-write.

---

## Reporting

### How to record results

1. At the start of a test session, copy this file to:
   ```
   tests/smoke/runtime_parity-<YYYY-MM-DD>-<tester-initials>.md
   ```
   Example: `tests/smoke/runtime_parity-2026-06-01-DT.md`

2. Fill in all checkboxes (`[ ]` → `[x]`) and add Notes as you go.

3. Tally results at the end:
   - Count `[x]` cells across all 10 skill tables (3 cells per skill = 30 total).
   - Record per-runtime subtotals (10 cells each for CC / Codex / Gemini).

4. If any cell fails, open a GitHub issue with:
   - Title: `[Parity] <runtime>: <skill-name> fails smoke test <YYYY-MM-DD>`
   - Body: link to the dated copy of this file + paste the Notes from the
     failing cell.

5. If ≥25/30 cells pass, close the Phase D AC-D1 tracker issue as PASS and
   attach the dated copy.

### Scoring summary template

Add this block at the top of your dated copy after completing the walk-through:

```
## Results summary

| Runtime | Cells passed | Cells failed | Cells skipped (N/A) |
|---------|-------------|-------------|---------------------|
| Claude Code | /10 | /10 | /10 |
| Codex CLI | /10 | /10 | /10 |
| Gemini CLI | /10 | /10 | /10 |
| **Total** | **/30** | **/30** | **/30** |

**Verdict**: PASS / PARTIAL / FAIL (see AC-D1 verdict criteria below)

**Tester**: <name>
**Date**: <YYYY-MM-DD>
**OSM server version**: <version from `api_version_diff` or `cli_help`>
**Plugin commit**: <git SHA of odoo-mcp-client at time of test>
```

---

## AC-D1 verdict criteria

### PASS

All three conditions must hold:

1. **≥25 / 30 cells** marked pass (across all runtimes).
2. **All 10 Claude Code cells** pass (CC is the primary runtime — any CC failure
   is blocking regardless of total count).
3. **No P0 failure** in any runtime: a P0 failure means a skill produces output
   that is factually incorrect AND would be surfaced to a customer without
   further review (e.g., wrong verdict in `odoo-feature-check`, fabricated
   module name in `odoo-objection-handler`).

Outcome: Phase D AC-D1 is closed PASS. Attach dated copy to the tracker issue.

### PARTIAL

Conditions:

- **20-24 / 30 cells** pass, OR
- All CC cells pass but Codex or Gemini has ≥3 failures.

Outcome: document specific failing cells + root cause. Open per-runtime fix
issues. Phase D AC-D1 stays open until either the gaps are fixed or explicitly
accepted as Known Gaps (with product owner sign-off).

### FAIL

Any one of:

- **<20 / 30 cells** pass, OR
- **Any Claude Code cell** fails, OR
- **Any single skill fails on all 3 runtimes** (indicates a skill-level defect,
  not a runtime-parity issue).

Outcome: blocking issue. Do not proceed to Phase D integration review until the
root cause is identified and a fix is in place. Reference the dated copy in the
blocking issue.

---

*This checklist was authored for Phase D, AC-D1. Maintainers: update canonical
trigger prompts when skill descriptions change (especially after `/skill-creator`
Mode 5 trigger optimization runs in AC-D6). Keep Known Gaps in sync with
`docs/setup.md` runtime-specific notes.*
