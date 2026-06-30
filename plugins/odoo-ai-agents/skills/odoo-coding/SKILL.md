---
name: odoo-coding
argument-hint: "[what to build or change]"
description: >
  Write complete, production-ready Odoo code end-to-end - Python/XML backend AND
  JavaScript/OWL/QWeb/SCSS frontend - from a single computed field up to a multi-module
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

Developer - full-stack Odoo coder (all versions, v8 onward). Orchestrates two specialist agents:
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

## Phase 0 - Scope + module graph (1-turn gate, mandatory)

This is the single confirmation checkpoint. It applies even when the request arrived directly
(e.g. intake bypass) - **unless your brief carries the AUTONOMOUS FIX sentinel (see the exception
immediately below), in which case you skip this gate entirely.**

**Autonomous-fix exception - SKIP this gate entirely** when your brief contains
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

**Plan-provided fast-path - CONSUME the plan, do NOT re-derive (inter-module layer).** When the
caller hands you a PLAN's already-computed inter-module results - via the Continuation-Contract
`inputs` on a `run-harness`, `odoo-planning`, or `odoo-wave` handoff (`odoo-wave` is the git-executor
that INVOKES this skill per WI from its orchestrating context, passing one WI's slice + that WI's
worktree path - see WORKTREE_PATH below): the **target module set**, the **wave-batched module-DAG**,
the **wave / topology**, and the **design pointers** (`design_index` / `design_doc` / `design_docs`,
carrying the per-module stack split + effort) - CONSUME them verbatim
and SKIP the self-derivation steps that would recompute them: the design-gate (step 1), the design
detection / glob below, the module-set step (2), and the dependency-order +
wave derivation (step 4). **Stack tag (step 3) - consume, else infer (never silently skip):** take
each module's stack from the WI brief's `STACK` field (or the design pointers' per-module stack
split) when provided; when the plan carries `DESIGN_DOC: none` and no `STACK` (e.g. an `odoo-wave` WI
with no design doc), the stack is not yet known - retain step 3's file-based inference (`models/` /
`views/` / `security/` / `*.csv` => backend; `static/src` JS/SCSS/QWeb => frontend; both =>
fullstack) rather than skipping it. The plan is the SSOT for the inter-module layer
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md`: `odoo-planning` is the canonical
producer of the wave-batched module-DAG; `odoo-coding` runs the module-graph algorithm itself ONLY
when standalone). You STILL run the intra-skill steps this skill owns at runtime - **step 5**
(model tier per module) and **step 6** (test-first per module) - plus the backend-first dispatch
ordering; the plan binds WHICH modules build in WHAT order, never how many agents or which model
(the plan's `est_agents` / `effort` is ADVISORY - this skill decides the actual count + tier at
runtime). Trust-but-verify: if a fed module / DAG node cannot be resolved on disk, STOP and report
BLOCKED - never silently self-derive a different graph. When dispatched under an active run-harness
(a named `run-<id>`) OR with a `WORKTREE_PATH` (the pre-approved git-executor / `odoo-wave` path -
see WORKTREE_PATH below) the upstream approval (`odoo-planning` ExitPlanMode / the driver L2 gate)
already stands, so do not re-emit the Phase-0 confirmation gate - a per-WI gate here would stall
`odoo-wave`'s sequential loop; otherwise (a plan fed to a standalone invocation with no worktree)
proceed to the gate below.

**WORKTREE_PATH (git-executor invocations only).** When the caller is `odoo-wave`, the brief ALSO
carries a per-WI `WORKTREE_PATH` (an absolute isolated worktree on a WI branch). Treat it as the
working root: the coders author + commit ALL their work INSIDE that worktree (`cd` to it before any
Bash; own-worktree `git add`/`git commit` are allowed per
`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`) and must NOT touch the principal checkout or run any
integration op (cherry-pick/merge/rebase/push) - `odoo-wave` integrates. Return the commit SHA(s) on
the WI branch so `odoo-wave` can cherry-pick them. When no `WORKTREE_PATH` is provided (run-harness /
odoo-planning / standalone), author in the current checkout exactly as today.
Git-mutation safety (S9): commit ONLY inside the provided worktree; never write to, commit on, or switch the principal checkout. See `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` (S9).

**No plan provided (standalone invocation) - self-derive exactly as below.** The design-gate,
design detection, module set, stack tags, and dependency order are all computed here; the
standalone fallback is unchanged.

**1. Design-gate first (safety net).** Judge whether the change is **non-trivial** - the set
`odoo-solution-design` defines: Extension-L/Custom-XL, a new module/model or restructuring, a
core `create`/`write`/`unlink` override or a ≥3-override-chain method, a >1-strategy migration, a
cross-model computed chain or multi-company logic, a full-stack feature, or a refactor. If it is
non-trivial AND no approved design exists, recommend `SUGGESTED_NEXT: odoo-solution-design` first -
a recommendation, not a hard block, so the user may still say "code it directly". **Trivial** work
(a single field, boilerplate, a one-approach fix) skips design.

**Design detection - index-first, backward-compat.** Resolve before step 2.
When a `design_doc` is already provided by the caller (via Continuation Contract `inputs.design_doc` / `inputs.design_docs`, e.g. a `return_to` or run-harness handoff), use it directly as `DESIGN_DOC` and build to it - skip steps 1-3 below. Otherwise:
1. **Master-child (priority):** glob `.odoo-ai/designs/*/index.yaml`. If found, read the matching
   `index.yaml` per `${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md` - routing SSOT.
   When glob returns >1 file, apply the tie-break in `§Index selection` of that snippet (largest
   module-intersection → newest `created:` → alphabetical slug → emit `design_doc_ambiguity: true`
   when still tied). Resolve `master` and each `child_path` to ABSOLUTE paths (join the index
   directory + the relative value) before use. Per module: `DESIGN_DOC` = resolved absolute child
   path; `MASTER_DESIGN_DOC` = resolved absolute master path. Never let the flat glob below match
   inside a master-child subdir.
2. **Single (fallback):** no `index.yaml` found - glob `.odoo-ai/designs/<slug>-*.md`. If found:
   `DESIGN_DOC` = that path; `MASTER_DESIGN_DOC` = `none`. Behavior identical to pre-master-child.
3. **None:** neither found - "no approved design" (gate above).

When `DESIGN_DOC` is resolved, read it and **build to it** - do not re-derive the approach. When
`MASTER_DESIGN_DOC` is not `none`, it is the HARD constraint layer: ownership, dep-direction, and
§10 cross-module contracts in the master TDD are non-negotiable; a child that violates them is a
CRITICAL defect.

**2. Determine the target module set.** Derive the modules the change will touch from the design
doc / the request (coding *creates* the change, so there is no git diff to read - unlike
`odoo-code-review`). A "module" is the directory holding `__manifest__.py`.

**3. Tag each module's stack-need** - `backend`, `frontend`, or `fullstack`. Take it from the
design doc when it already splits the work; otherwise infer: touching `models/` `views/`
`security/` `*.csv` ⇒ backend; touching `static/src` JS/SCSS/QWeb ⇒ frontend; both ⇒ fullstack.

**4. Compute the dependency order (OSM is ground truth).** Follow
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md` - the SSOT for the module DAG, shared
with `odoo-wave` so both order work the same way. In short: call
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
| 2 | Design doc grades it Extension-L; OR it overrides core `create`/`write`/`unlink`; OR the override chain has >=3 entries (`find_override_point`); OR cross-model computed chain / multi-company logic; OR a migration with >1 viable strategy; OR full-stack module with >5 intended files; OR the work-item is LARGE by size or surrounding-codebase load - net-new-or-changed >=~200 LOC, OR >=~5 intended files, OR a large / high-blast-radius target module (many existing methods or downstream dependents to hold in context, e.g. `impact_analysis`/`model_inspect` shows a wide method surface or ripple) even when the change is single-stack | **opus** |
| 3 | Design doc grades it Standard or Config; OR (single-stack AND <=2 intended files AND ~<=50 LOC AND no method override): one field/attr, boilerplate XML view shell, label/string change, security CSV row | **haiku** |
| 4 | Everything else - Extension-M, normal computed/onchange/constraint, single-method override, standard OWL widget, mid-size single-stack module BELOW the Row-2 size/scope thresholds (<~200 LOC AND <5 files AND not a large/high-blast-radius module) - and ANY genuinely ambiguous case you cannot classify confidently | **sonnet** (default) |

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

**Coverage pre-flight (run before assigning test mode).** For each non-trivial module, query OSM
to ground the test scope - only write what is NOT already covered:
- `tests_covering(model='<primary_model>', odoo_version='<version>')` - lists every TestMethod
  already exercising that model; carry this list forward into the test-author brief so the author
  writes additive tests only, never re-invents existing ones.
- `test_coverage_audit(module='<module>', odoo_version='<version>')` - surfaces fields with zero/partial static-reference coverage (field-level only; does NOT report method gaps and is NOT executed coverage); use this to bound the scope (test only the field gaps).
- `test_base_classes(odoo_version='<version>')` - retrieves the authoritative base class menu
  (TransactionCase, SavepointCase, HttpCase, ...) with the hard rule that **`cr.commit()` is
  FORBIDDEN inside TransactionCase / SavepointCase - isolation is savepoint rollback**. Include
  the matching base class in the test-author brief so the author never has to guess.

Skip the coverage pre-flight only when OSM is unreachable (standalone/disk fallback, same flag
as step 4); in that case the test-author works from disk context alone.

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
Design: <DESIGN_DOC child path | none> [Master: <MASTER_DESIGN_DOC path | none>]
OSM: backed | standalone
Dispatch: subagent launch model-weighted batches
Proceed? (yes / refine: [feedback] / cancel)
```

The `wave` column stays for the reader's benefit (it shows depends-on), but the
executor does not barrier on waves - dependency order is enforced per-module
during execution.

On `yes`, execute; on `refine: …`, update and re-emit; on `cancel`, stop.

## Execution - dispatch the coders (subagent launch, model-weighted batches)

The coders run as autonomous agents - never inline codegen in main, never via the Skill tool.
Launch them as subagents: `agentType: odoo-coder` (backend) / `agentType:
odoo-frontend-coder` (frontend); if a short name fails to resolve, retry with the plugin-qualified
form `odoo-ai-agents:odoo-coder` / `odoo-ai-agents:odoo-frontend-coder`. Do NOT build a Claude Code
Workflow (JS) script for this - all fan-out is real subagent launches; narrating a dispatch in prose
instead of calling the tool is not allowed.

Concurrency/OOM rule (SSOT: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`, Mode B):
model-weighted budget - WEIGHT haiku=1, sonnet=2, opus=4, fable=8; at most 8 weight-units in flight
at once (keeps opus <=2 and fable exclusive while haiku/sonnet flow freely - the OOM risk comes from
opus-class fan-out, so heavier tiers weigh more).

Instance-allocation rule (SSOT: same `concurrency-guard.md` § Odoo instance allocation): a coder or
test-author that runs `odoo-bin` against a database (tests via `--test-enable`, `-i`/`-u`, or
scaffolding into a DB) acquires an ISOLATED instance via `scripts/lib/allocator.py` (a unique
ephemeral DB) instead of the single declared db/port - the coder agents already do this from their
system prompt, so the brief never passes a shared db/port.

### Dispatch loop - model-weighted batches

The Phase 0 plan carries, per module: name, path on disk, stack, model (and `frontendModel` when
split), the in-set dependency edges (the "(depends on ...)" in the gate table), whether it is a new
module, the test-mode (`test-author | self`), and the per-module request (+ a frontendRequest for
the UI leg). Resolve ONE Odoo version for the whole run; carry the design-doc path, the runSlug
(scopes the shared worklog dir) and - when the user is not working in English - the userLanguage.

0. Context-handoff probe (run ONCE per run, before the first batch fires). Follow
   `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md`: run the capability probe a single
   time and cache the result for the whole run. When Tier A is available, spawn each coder with a
   stable `name` (e.g. `coder-<module-slug>`), and - as the LEAD and sole address authority - capture
   the `agentId` the Agent launch returns and record it per work-item in plan.md (the coder never
   self-IDs). When Tier A is NOT available, proceed exactly as today (Tier C: fresh Agent calls,
   worklog for context). Tier C is always correct; Tier A is an optional optimization that degrades
   silently to Tier C. When the CHP capability probe is positive (Agent Team mode on), TaskCreate
   one task per dispatched work-item, inject TASK_ID + REPLY_TO: main + NOTIFY: <dependent names>
   into each teammate brief, poll TaskList/TaskGet for status, and read each result from the
   teammate's SendMessage push (NEVER from the .output transcript) - per
   `${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md`. When off, dispatch + collect as today.
1. Order modules so every module appears after its in-set dependencies (the wave column already
   encodes this).
2. Greedily pack the next batch: take modules in order whose dependencies are all done (done = BOTH
   legs of the dependency finished successfully) and whose summed WEIGHT stays <= 8. A fable item
   always forms a batch of ONE.
3. Fire the whole batch as parallel subagent launches in a SINGLE message; per module fire only the
   backend leg first, then after it returns fire that module's frontend leg in the next batch round.
   When Tier A is in effect, give each launch its stable `name` and record the returned `agentId` in
   plan.md as you go.
4. Wait for the batch, then pack the next. This is a batch barrier each round - the accepted
   trade-off of dropping the JS dispatch engine: an independent module may wait on a heavier sibling
   in the same batch. A later step re-dispatches a BLOCKED module at the SAME recorded tier: under
   Tier A, resume the recorded `agentId` by `SendMessage` when it is still addressable; otherwise
   (Tier C, the always-correct fallback) make a fresh Agent call. Either way the worklog stays the
   always-correct context layer the re-dispatched worker reads.
5. Each subagent launch sets BOTH the `model` parameter AND the first prompt line
   `DISPATCH MODEL: <haiku|sonnet|opus|fable>` (belt and braces, mirroring `odoo-debug`).
6. fable -> opus downgrade: if a fable dispatch fails (insufficient usage credit, model unavailable,
   subagent error), retry that work-item ONCE at `model: opus` and record the downgrade in plan.md
   (`opus (fable unavailable)`).
7. Test-first (red before green) for a module marked `test: test-author`: dispatch a SEPARATE
   test-author FIRST - per stack (the backend test before the backend coder; the frontend test
   before the frontend coder) - so the test author is not the code author (independence keeps the
   test honest). Hand the returned RED test paths to that module's coder. A `test: self` module
   skips this: its coder writes its own red test first, then the code.

### Per-module briefs

Each subagent launch carries the brief below as its `prompt`. The brief is **run-specific inputs
only**: every procedure (OSM grounding, coding guidelines, worklog read/append, ORM + static gates,
demo data, output format, test-first) already lives in the coder's system prompt, so do NOT re-teach
it here - a re-taught copy duplicates the SSOT and drifts. Keep identifiers verbatim.

Coder (`agentType: odoo-coder` for a backend leg / `odoo-frontend-coder` for a frontend leg):

```
DISPATCH MODEL: <tier>
REQUEST: <the change for this module: target model + constraints; for a frontend leg use the module's frontendRequest, falling back to its request>
MODULE SCOPE: <name> @ <path> - write ONLY within this module (+ its __manifest__.py / static assets).
WORKTREE_PATH: <absolute worktree path | none> - when set (git-executor / `odoo-wave` path): `cd` here and author ALL work in this worktree; `git add` + `git commit` your work; RETURN the commit SHA(s) on the WI branch (do NOT cherry-pick/merge/push - `odoo-wave` integrates). `none` -> author in the current checkout as usual, no commit.
NEW MODULE: <yes - ALWAYS scaffold with `odoo-bin scaffold` first; edit only needed keys and KEEP scaffold's commented placeholders; keep its short version default, do NOT rewrite to `<series>.x.y.z` | no>
ODOO VERSION: <version>
INSTANCE_HANDLE: <the run's provisioned instance handle from a prior odoo-instance step, when present - db_name/http_port/addons_path/venv/lease_token; omit when the run provisioned none>
DESIGN_DOC: <child TDD path | none> - per-module spec; if present, build to it; do not re-derive.
MASTER_DESIGN_DOC: <master TDD path | none> - hard constraints (ownership, dep-direction, §10 contracts); `none` in single mode.
TEST: <test-author -> "FAILING TEST (RED, written by a separate author): <paths> - implement until they pass; do NOT edit the tests." | self -> "write the failing test FIRST, confirm RED, then code to green - never weaken it">
WORKLOG: <runSlug> - read it, then append your significant decisions.
USER LANGUAGE: <lang | omit when the user works in English> - write the summary in this language; keep identifiers verbatim.
Follow the Rounds in your system prompt - it owns every procedure; do not re-derive what it already specifies.
GUIDELINES: Round 1 owns this - open `coding_guidelines/<version>/INDEX.md` first, consult the "By task" table, read ONLY the mapped files (not the whole directory).
```

- When an `INSTANCE_HANDLE` is present in the brief, the coder MUST use it for confirm-by-toggle
  and `--test-enable` runs and MUST NOT self-provision a DB / port / addons_path; absent a handle
  it falls back to its own isolated ephemeral instance (`skills/_shared/concurrency-guard.md`
  § Odoo instance allocation). Contract: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`.
- To run `odoo-bin` (scaffold, or tests via `--test-enable`), resolve the interpreter per
  `snippets/venv-resolution.md` - never assume system `python3`.
- Frontend leg only: ground styling tokens against `skills/_shared/odoo-frontend-fidelity.md`
  (no hardcoded hex for themeable colors, no self-referential `--bs-*` shim) - the full method lives
  in the agent's system prompt.

Test-author (`agentType` = `odoo-coder` for a backend leg / `odoo-frontend-coder` for a frontend
leg, in TEST-AUTHOR mode - this mode is NOT in the agent's own system prompt, so the brief defines
it):

```
DISPATCH MODEL: <tier>
TEST-AUTHOR MODE: write ONLY the failing test(s) protecting the business behavior below - do NOT write the implementation.
REQUEST: <the business rule to protect>
MODULE SCOPE: <name> @ <path> - test files only (`tests/` or `static/tests/`).
ODOO VERSION: <version>
EXISTING COVERAGE: <output of tests_covering(model='<primary_model>', odoo_version='<version>')
  listing TestMethods already covering this model - write ADDITIVE tests only, never re-invent these>
COVERAGE GAPS: <fields flagged by test_coverage_audit(module='<module>', odoo_version='<version>')
  as having zero/partial static-reference coverage (field-level only; NOT method gaps, NOT executed coverage) - prioritise these field gaps in the new tests>
BASE CLASS: <base class selected from test_base_classes(odoo_version='<version>') output, e.g.
  TransactionCase - HARD RULE: cr.commit() is FORBIDDEN inside TransactionCase/SavepointCase;
  isolation is savepoint rollback>
WORKLOG: <runSlug> - read, then append; return the test paths + a one-line RED confirmation.
```

Follow `snippets/test-first-contract.md` (red-before-green) and `snippets/test-behavior-contract.md`
(drive the real workflow - action_confirm/action_validate/button_validate, Form() for onchange,
with_user() not sudo(); never seed the terminal state with create({state:...})): assert observable
behavior not internals; ONE intent per test; confirm each goes RED.

Each agent locates files via Read/Grep, writes its output, and reports the files written plus
`__manifest__.py` changes. **When `WORKTREE_PATH` was provided (git-executor / `odoo-wave` path), the
coder MUST ALSO `git add` + `git commit` its work inside that worktree and return the commit SHA(s)
on the WI branch so `odoo-wave` can cherry-pick them - a DONE with no SHA in the git-executor path is
a failed contract.** Without `WORKTREE_PATH` (standalone / run-harness / `odoo-planning`) no commit is
made.

## Artifacts - persist the coding plan

Write the orchestration plan to `.odoo-ai/coding/<slug>-<YYYY-MM-DD>/plan.md` (`.odoo-ai/` is
gitignored): the module/stack/wave/**model** table, the computed dependency order, and the design
doc referenced. The agents write source directly; `plan.md` records what was built so a later
review / fix / resume step can pick up without recomputing the graph. `<slug>` derives from the
change (branch, feature name, or the module set).

plan.md MUST record, per work-item: module, stack, wave, the model tier chosen
(and frontendModel when split), the dispatch path (subagent launch), the per-module
result status, and the `agentId` (when CHP Tier A is in effect - plan.md is the agentId
registry per `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md`; omit when Tier C).
A later review / fix / resume step re-dispatches BLOCKED modules at the SAME recorded tier
(unless the human changes it) via the Tier-A/Tier-C rule in § Dispatch loop step 4.

## Standalone-first fallback

When OSM (the odoo-semantic-mcp server) is unreachable, the dependency graph and stack tags come
from disk - read each `__manifest__.py` `depends` and scan `static/src` (or the haiku reader
above) - and each agent falls back to its own disk-grounded mode per
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`, still writing files to their correct
locations. Label the plan "graph from disk (OSM unavailable)"; the wave/pair topology is
unchanged, only the grounding degrades. Never ask a human to paste code, field lists, or manifests.

## Agent-managed tools

This skill is part of an agent+skill bundle. The codegen tool lists live on the two agents -
see `agents/odoo-coder.md` (backend) and `agents/odoo-frontend-coder.md` (frontend) for the full
restricted allowlists and execution detail.

## The code -> review+test -> code loop (bounded)

Coding is not one-shot. After this skill writes code (each non-trivial module implemented to a
separately-authored failing test), the **code -> review+test -> code** round-trip runs:
`odoo-code-review` reviews AND checks the tests cover the behavior, looping back on a CRITICAL/HIGH
issue or a red/missing test.

**Drive it yourself when there is no run-harness (mandatory).** The Skill tool is available here.
After writing, **IMMEDIATELY invoke `odoo-code-review` via the Skill tool yourself** - a
passive `next: odoo-code-review` is not advanced without an active run-harness (the common case: direct
invocation, intake fast-path, autonomous fix), so verification would silently never happen. ONLY
exception: dispatched by an active run-harness (a `run-<id>` is named) - then emit
`next: odoo-code-review` and let it advance, do not double-dispatch. Emit the Continuation Contract either way.

Bound the loop to **3 iterations** per `${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`; still
not green-and-clean after 3 -> STOP and escalate (bad work is worse than no work). Each iteration's
outcome goes in the worklog.

## Continuation Contract

When the bundle finishes, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Set
`produced` to the source + test files written, plus `.odoo-ai/coding/<slug>-<date>/plan.md` and the
`.odoo-ai/worklog/<slug>/` entries, and emit `next: odoo-code-review` so the just-written code is
reviewed (that skill now scales to the same multi-module set). Additionally, when any module in the
run is new (`NEW MODULE: yes`) OR the change introduces user-facing translatable strings
(`_("...")` / `string=` field attr), also add `SUGGESTED_NEXT: odoo-i18n` so the module's
`.pot` / `.po` files are generated and translated via the dedicated i18n skill. Additive output for the
run-harness - it does not change anything produced above.
