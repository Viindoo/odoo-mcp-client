---
name: odoo-coding
description: >
  Write complete, production-ready Odoo code end-to-end — Python/XML backend AND
  JavaScript/OWL/QWeb/SCSS frontend — from a single computed field up to a multi-module
  full-stack feature. The single front door for ALL coding: it works out which modules the
  change touches and their dependency order, then dispatches the odoo-coder (backend) and
  odoo-frontend-coder (frontend) agents in the right sequence. Fire ANY time someone asks to
  build or change Odoo behavior, even with no technical words (e.g. "discount can never exceed
  20% of unit price", "add a field and show it in a widget"). Also fires on Vietnamese:
  "thêm trường / model", "computed field / ràng buộc / onchange", "override create/write",
  "phân quyền đọc ghi", "viết migration", "viết widget OWL / sửa giao diện form", "sửa SCSS
  theme". Review existing code → odoo-code-review. Find a hook point → odoo-override-finding.
  Design before coding (non-trivial) → odoo-solution-design. Verify a rendered screen →
  odoo-ui-review / odoo-debug
---

## Persona

Developer — full-stack Odoo coder (all versions, v8 onward). Orchestrates two specialist agents:
`odoo-coder` for Python/XML backend and `odoo-frontend-coder` for JS/OWL/QWeb/SCSS frontend.
Pair-works with `odoo-code-review` for review.

## Out of Scope

- **Reviewing / auditing existing code (not writing)** → `odoo-code-review`
- **Locating where to hook into core logic (one method)** → `odoo-override-finding`
- **Deprecation analysis / upgrade planning** → `odoo-deprecation-audit` / `odoo-version-diff`
- **Designing the approach before any code (non-trivial)** → `odoo-solution-design`
- **Verifying the rendered UI / a runtime render error / image regression** → `odoo-ui-review` / `odoo-debug` / `odoo-visual-regression`

## Why one skill, two agents

An Odoo job often spans both stacks (a field/model plus its widget/view). This is the only coding
entry point: it figures out per-module whether work is backend / frontend / fullstack and dispatches
just the agents needed. The agents stay specialists; this skill owns orchestration (module set,
dependency order, sequencing), not codegen.

## Phase 0 — Scope + module graph (1-turn gate, mandatory)

This is the single confirmation checkpoint. It applies even when the request arrived directly
(e.g. intake bypass) — **unless your brief carries the AUTONOMOUS FIX sentinel (see the exception
immediately below), in which case you skip this gate entirely.**

**Autonomous-fix exception — SKIP this gate entirely** when your brief contains
**"AUTONOMOUS FIX (review-driven)"** or **"AUTONOMOUS FIX (debug-driven)"**: the human already
opted into the autonomous review/debug fix loop, so do NOT stop for a confirmation. Read the worklog
+ the review report / proven root cause passed in, fix directly to those findings, and the moment
you finish writing **IMMEDIATELY invoke `odoo-code-review` via the Skill tool yourself** to verify
(§ The code -> review+test -> code loop). Bound to 3 iterations, then STOP and escalate.

Otherwise (normal invocation), First READ any existing worklog for this run
(`.odoo-ai/worklog/<run-or-slug>/*.md`, oldest-first) per
`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md` so you build on the decisions an upstream
phase (e.g. `odoo-solution-design`) already recorded instead of re-deriving them. Then do six
things, then stop for the user's reply.

**1. Design-gate first (safety net).** Judge whether the change is **non-trivial** — the set
`odoo-solution-design` defines: Extension-L/Custom-XL, a new module/model or restructuring, a
core `create`/`write`/`unlink` override or a ≥3-override-chain method, a >1-strategy migration, a
cross-model computed chain or multi-company logic, a full-stack feature, or a refactor. If it is
non-trivial AND no approved design exists (no `.odoo-ai/designs/<slug>-*.md`, and none passed in
via a `design_doc` input), recommend `SUGGESTED_NEXT: odoo-solution-design` first — a
recommendation, not a hard block, so the user may still say "code it directly". When a
`design_doc` IS present, read it and **build to it** — do not re-derive the approach. **Trivial**
work (a single field, boilerplate, a one-approach fix) skips design.

**2. Determine the target module set.** Derive the modules the change will touch from the design
doc / the request (coding *creates* the change, so there is no git diff to read — unlike
`odoo-code-review`). A "module" is the directory holding `__manifest__.py`.

**3. Tag each module's stack-need** — `backend`, `frontend`, or `fullstack`. Take it from the
design doc when it already splits the work; otherwise infer: touching `models/` `views/`
`security/` `*.csv` ⇒ backend; touching `static/src` JS/SCSS/QWeb ⇒ frontend; both ⇒ fullstack.

**4. Compute the dependency order (OSM is ground truth).** Follow
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md` - the SSOT for the module DAG, shared
with `wave` so both order work the same way. In short: call
`module_inspect(name=<m>, method='dependencies', odoo_version='[resolved version]')` per target
module (concrete version - the pin is per-API-key and racy, see
`skills/_shared/concurrency-guard.md` "OSM version-pin race"), build the sub-graph restricted to the
target set, and topologically order it - independent modules share a **wave** (parallel), a
dependent module runs in a **later wave**. The disk fallback (haiku reader of each
`__manifest__.py` `depends` + `static/src` scan, labelled "graph from disk (OSM unavailable)")
lives in that SSOT.

**5. Assign a model tier per module (deterministic - no judgment call mid-flow).**
Every dispatch in this skill passes an explicit `model`. Resolve the tier for each
module's work-item by walking this table TOP-DOWN and stopping at the FIRST match.
When a design doc is present, its effort tier takes precedence over the heuristics.

| # | Condition (first match wins) | Tier |
|---|---|---|
| 1 | Design doc grades it Custom-XL; OR the work-item spans >=3 modules of the set AND is full-stack AND estimated >800 LOC; OR it changes an inheritance axis across modules | **fable** |
| 2 | Design doc grades it Extension-L; OR it overrides core `create`/`write`/`unlink`; OR the override chain has >=3 entries (`find_override_point`); OR cross-model computed chain / multi-company logic; OR a migration with >1 viable strategy; OR full-stack module with >5 intended files | **opus** |
| 3 | Design doc grades it Standard or Config; OR (single-stack AND <=2 intended files AND ~<=50 LOC AND no method override): one field/attr, boilerplate XML view shell, label/string change, security CSV row | **haiku** |
| 4 | Everything else - Extension-M, normal computed/onchange/constraint, single-method override, standard OWL widget, mid-size single-stack module - and ANY case you cannot classify confidently | **sonnet** (default) |

Constraints on the table:
- **sonnet is the ambiguous-case default.** If two rows seem to apply, the higher
  row (smaller #) wins; if NO row clearly applies, use sonnet.
- **fable is never a default and ALWAYS needs explicit human confirmation.** It is
  the rare top band (~2x opus price). When any row resolves to fable, the gate
  message must call it out on its own line - tier, cost, and a one-line why
  (e.g. `Fable row: <m2> - Custom-XL cross-module inheritance change (~2x opus
  cost). Confirm fable?`) - and the human's yes covers it. If the human declines
  fable, downgrade that row to **opus** before dispatch and record the downgrade
  in plan.md (`<m2>: opus (fable declined)`). If the work is fable-grade but NO
  approved design doc exists, recommend `SUGGESTED_NEXT: odoo-solution-design`
  first (Custom-XL work is design-first).
- A fullstack module gets ONE tier applied to both legs by default; you MAY set a
  lower `frontendModel` when the design doc splits effort (e.g. opus backend +
  sonnet frontend). Never set the frontend leg HIGHER than the module tier.
- Record the chosen tier in the gate table and later in plan.md - the tier is part
  of the approved plan, not a runtime improvisation.

**6. Decide test-first authorship per module (red before green).** The test protects the business
behavior and is written BEFORE the code (`${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`).
Choose per module, hybrid by complexity:
- **non-trivial** module (anything the design gate flags non-trivial - core override, cross-model
  chain, multi-company logic, new model, full-stack) → `test: test-author`: a SEPARATE author
  writes the failing test first, so the test author is not the code author (independence keeps the
  test honest). Execution runs that test-author before the coder, per stack.
- **trivial** module (single field, boilerplate, one-approach fix) → `test: self`: the coder writes
  its own red test first, then the code - a separate author is not worth the round-trip at that
  size.

Then emit the gate and wait. Write the gate message in the USER'S language (translate
labels and prose; keep module names, paths, and the reply keywords verbatim - SSOT:
`${CLAUDE_PLUGIN_ROOT}/snippets/language-mirroring.md`), and when the user is not
working in English pass `userLanguage` in the coder brief so the coder agents
return their summaries pre-mirrored:

```
Proposed: <one-line summary of the change>.
Plan:
  | module | stack     | wave | model  | test        | files (intended) |
  | <m1>   | backend   | 1    | haiku  | self        | <m1>/models/*.py, __manifest__.py |
  | <m2>   | fullstack | 1    | opus   | test-author | <m2>/models/*.py, <m2>/static/src/*.js, __manifest__.py |
  | <m3>   | frontend  | 2    | sonnet | test-author | <m3>/static/src/*.js (depends on <m1>) |
Design: <path to approved design doc | none (trivial)>
OSM: backed | standalone
Dispatch: Agent-tool model-weighted batches
Proceed? (yes / refine: [feedback] / cancel)
```

The `wave` column stays for the reader's benefit (it shows depends-on), but the
executor does not barrier on waves - dependency order is enforced per-module
during execution.

On `yes`, execute; on `refine: …`, update and re-emit; on `cancel`, stop.

## Execution - dispatch the coders (Agent-tool, model-weighted batches)

The coders run as autonomous agents - never inline codegen in main, never via the Skill tool.
Dispatch them with the **Agent tool**: `agentType: odoo-coder` (backend) / `agentType:
odoo-frontend-coder` (frontend); if a short name fails to resolve, retry with the plugin-qualified
form `odoo-ai-agents:odoo-coder` / `odoo-ai-agents:odoo-frontend-coder`. Do NOT build a Claude Code
Workflow (JS) script for this - all fan-out is real Agent-tool calls; narrating a dispatch in prose
instead of calling the tool is not allowed.

Concurrency/OOM rule (SSOT: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`, Mode B):
model-weighted budget - WEIGHT haiku=1, sonnet=2, opus=4, fable=8; at most 8 weight-units in flight
at once (keeps opus <=2 and fable exclusive while haiku/sonnet flow freely - the OOM risk comes from
opus-class fan-out, so heavier tiers weigh more).

### Dispatch loop - model-weighted batches

The Phase 0 plan carries, per module: name, path on disk, stack, model (and `frontendModel` when
split), the in-set dependency edges (the "(depends on ...)" in the gate table), whether it is a new
module, the test-mode (`test-author | self`), and the per-module request (+ a frontendRequest for
the UI leg). Resolve ONE Odoo version for the whole run; carry the design-doc path, the runSlug
(scopes the shared worklog dir) and - when the user is not working in English - the userLanguage.

1. Order modules so every module appears after its in-set dependencies (the wave column already
   encodes this).
2. Greedily pack the next batch: take modules in order whose dependencies are all done (done = BOTH
   legs of the dependency finished successfully) and whose summed WEIGHT stays <= 8. A fable item
   always forms a batch of ONE.
3. Fire the whole batch as parallel Agent-tool calls in a SINGLE message; per module fire only the
   backend leg first, then after it returns fire that module's frontend leg in the next batch round.
4. Wait for the batch, then pack the next. This is a batch barrier each round - the accepted
   trade-off of dropping the JS dispatch engine: an independent module may wait on a heavier sibling
   in the same batch. There is no cached run to resume; a later step re-dispatches a BLOCKED module
   as a fresh Agent call.
5. Each Agent-tool call sets BOTH the `model` parameter AND the first prompt line
   `DISPATCH MODEL: <haiku|sonnet|opus|fable>` (belt and braces, mirroring `odoo-debug`).
6. fable -> opus downgrade: if a fable dispatch fails (insufficient usage credit, model unavailable,
   Agent-tool error), retry that work-item ONCE at `model: opus` and record the downgrade in plan.md
   (`opus (fable unavailable)`).
7. Test-first (red before green) for a module marked `test: test-author`: dispatch a SEPARATE
   test-author FIRST - per stack (the backend test before the backend coder; the frontend test
   before the frontend coder) - so the test author is not the code author (independence keeps the
   test honest). Hand the returned RED test paths to that module's coder. A `test: self` module
   skips this: its coder writes its own red test first, then the code.

### Per-module briefs

Each Agent-tool call carries the brief below as its `prompt`. Keep identifiers verbatim.

Backend coder (`agentType: odoo-coder`):

```
DISPATCH MODEL: <tier>
You are the odoo-coder agent. Produce production-ready Python/XML Odoo code.
REQUEST: <the change for this module, with target model + constraints>
MODULE SCOPE: <name> @ <path> - write ONLY within this module (+ its __manifest__.py).
NEW MODULE: <yes - scaffold the skeleton with `odoo-bin scaffold` first, then fill it in (do NOT hand-roll the skeleton) | no>.
ODOO VERSION: <version>
DESIGN_DOC: <path | none> - if present, build to it; do not re-derive.
TEST: <test-author -> "FAILING TEST (written by a separate author, currently RED): <paths> - implement until these pass; do NOT edit the tests to make them pass." | self -> "TEST-FIRST: write the failing test for the business rule FIRST and confirm it goes RED, then implement to green; never weaken the test. The test MUST drive the real workflow (action_confirm/action_validate/button_validate, Form() for onchange, with_user() not sudo()) - never seed the terminal state with create({state:...})."> See snippets/test-first-contract.md and snippets/test-behavior-contract.md.
GUIDELINES: before writing, read skills/_shared/coding_guidelines/<version>/INDEX.md and the by-task files for this change (python/naming/model-ordering for models, xml for views) - conform on the first pass. snippets/read-before-write-contract.md.
WORKLOG: read then append your significant decisions (approach, impact + mitigation, demo-data, tier) to .odoo-ai/worklog/<runSlug>/ per snippets/worklog-contract.md.
Step 0 (only if mcp__odoo-semantic__* is available): set_active_version('<version>'), then follow Rounds 1-4 from your system prompt. If OSM is down, use the disk-grounded fallback and still write files. If OSM answers but a specific module/model is not in the index (customer-local addon), Read/Grep the local addon for just that entity and ground hybrid (osm + local-source) - an index miss is not proof of absence. Do not spawn subagents or invoke skills.
USER LANGUAGE (omit when the user works in English): <lang> - write the summary in this language; keep identifiers verbatim.
```

Frontend coder (`agentType: odoo-frontend-coder`): the same brief shape, with `REQUEST` set to the
module's frontendRequest (fall back to its request), the MODULE SCOPE covering its
`__manifest__.py` assets, and two extra lines - "ground styling tokens against
skills/_shared/odoo-frontend-fidelity.md (no hardcoded hex for themeable colors, no self-referential
--bs-* shim)" and "if the Skill tool is unavailable, Read skills/odoo-frontend-design/SKILL.md
directly instead of invoking it".

Test-author (`agentType` = `odoo-coder` for a backend leg / `odoo-frontend-coder` for a frontend
leg, in TEST-AUTHOR mode): "Write ONLY the failing test(s) that protect the business behavior below
- do NOT write the implementation." Carry REQUEST / MODULE SCOPE (test files only: `tests/` or
`static/tests/`) / ODOO VERSION as above; follow snippets/test-first-contract.md (red-before-green)
AND snippets/test-behavior-contract.md (drive the real workflow: action_confirm/action_validate/
button_validate, Form() for onchange, with_user() not sudo(), never seed the terminal state with
create({state:...})): assert observable behavior, not internals; ONE intent per test; confirm each
test goes RED. Append to the worklog. Return the test file paths and a one-line RED confirmation.
Do not spawn subagents or invoke skills.

Each agent locates files via Read/Grep, writes the code, and reports the files it wrote plus
`__manifest__.py` changes.

## Artifacts — persist the coding plan

Write the orchestration plan to `.odoo-ai/coding/<slug>-<YYYY-MM-DD>/plan.md` (`.odoo-ai/` is
gitignored): the module/stack/wave/**model** table, the computed dependency order, and the design
doc referenced. The agents write source directly; `plan.md` records what was built so a later
review / fix / resume step can pick up without recomputing the graph. `<slug>` derives from the
change (branch, feature name, or the module set).

plan.md MUST record, per work-item: module, stack, wave, the model tier chosen
(and frontendModel when split), the dispatch path (agent-tool), and the per-module
result status. A later review / fix / resume step re-dispatches the BLOCKED modules
at the SAME recorded tier (a fresh Agent call - there is no cached run to resume)
unless the human changes it.

## Standalone-first fallback

When OSM (the odoo-semantic-mcp server) is unreachable, the dependency graph and stack tags come
from disk — read each `__manifest__.py` `depends` and scan `static/src` (or the haiku reader
above) — and each agent falls back to its own disk-grounded mode per
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`, still writing files to their correct
locations. Label the plan "graph from disk (OSM unavailable)"; the wave/pair topology is
unchanged, only the grounding degrades. Never ask a human to paste code, field lists, or manifests.

## Agent-managed tools

This skill is part of an agent+skill bundle. The codegen tool lists live on the two agents —
see `agents/odoo-coder.md` (backend) and `agents/odoo-frontend-coder.md` (frontend) for the full
restricted allowlists and execution detail.

## The code -> review+test -> code loop (bounded)

Coding is not one-shot. After this skill writes code (each non-trivial module implemented to a
separately-authored failing test), the **code -> review+test -> code** round-trip runs:
`odoo-code-review` reviews AND checks the tests cover the behavior, looping back on a CRITICAL/HIGH
issue or a red/missing test.

**Drive it yourself when there is no run-driver (mandatory).** You run at depth-0, so the Skill tool
is available. After writing, **IMMEDIATELY invoke `odoo-code-review` via the Skill tool yourself** - a
passive `next: odoo-code-review` is not advanced without an active run-driver (the common case: direct
invocation, intake fast-path, autonomous fix), so verification would silently never happen. ONLY
exception: dispatched by an active run-driver (a `run-<id>` is named) - then emit
`next: odoo-code-review` and let it advance, do not double-dispatch. Emit the Continuation Contract either way.

Bound the loop to **3 iterations** per `${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`; still
not green-and-clean after 3 -> STOP and escalate (bad work is worse than no work). Each iteration's
outcome goes in the worklog.

## Continuation Contract

When the bundle finishes, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Set
`produced` to the source + test files written, plus `.odoo-ai/coding/<slug>-<date>/plan.md` and the
`.odoo-ai/worklog/<slug>/` entries, and emit `next: odoo-code-review` so the just-written code is
reviewed (that skill now scales to the same multi-module set). Additive output for the depth-0
run-driver - it does not change anything produced above.
