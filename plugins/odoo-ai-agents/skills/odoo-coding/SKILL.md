---
name: odoo-coding
argument-hint: "[what to build or change]"
description: >
  Use when someone wants to build or change Odoo behavior and needs the code written - the
  single front door for ALL Odoo coding and the ONLY dispatcher of the per-module odoo-coder
  coordinator, scoping modules and ordering by dependency. Fire on ANY request to add or change
  something in an Odoo module, even with no technical words (e.g. "discount can never exceed 20%
  of unit price", "ticking urgent sets the deadline to tomorrow"): new model/field,
  computed/related field, constraint, onchange/auto-fill, create/write/unlink override, access
  rights, migration script, OWL/JS/QWeb/SCSS widget or form/list/kanban UI. Also Vietnamese:
  "thêm trường / model", "override create/write", "ràng buộc", "onchange tự điền", "phân quyền
  đọc ghi", "widget OWL / sửa form". DO NOT trigger for non-Odoo code. Review existing code →
  odoo-code-review. Hook point → odoo-override-finding. Design first → odoo-solution-design.
  Runtime/render bug → odoo-debug. Rate a screen → odoo-ui-review. Planning/estimate →
  odoo-planning
---

## Role

Developer - full-stack Odoo coder (all versions, v8 onward). Orchestrates by MODULE: it scopes the
touched modules, orders them by the module-DAG, assigns a model tier per module, and dispatches
**ONE `odoo-coder` COORDINATOR per module** (every module - backend-only, frontend-only, or
full-stack). The `odoo-coder` coordinator owns the module's INTERNAL work-item (WI) breakdown: for
its ONE module it splits the changes into 1..N WIs by DISJOINT file sets, schedules INDEPENDENT WIs
in PARALLEL and DEPENDENT WIs SEQUENTIALLY (a frontend WI that binds a backend WI runs after it - the
backend-before-frontend order), assigns each WI to the right worker (backend files ->
`odoo-backend-coder`, frontend files -> `odoo-frontend-coder`), and owns the integrated whole-module
test. This skill does NOT split a module into WIs and does NOT sequence backend/frontend - that is
`odoo-coder`'s job (SSOT for the two-tier axis:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md` § Two-tier decomposition axis - the
OUTER unit here is the module, the WI is `odoo-coder`'s INTERNAL unit).

Pair-works with `odoo-code-review` for review.

**Sole dispatcher (single source of truth for coding fan-out).** This skill is the ONLY component
that computes the module dependency order + the model tier and launches the `odoo-coder`
coordinator (one per module). Any other skill that needs Odoo code written routes its coding work
HERE via the Skill tool (passing its context in the brief) instead of launching the coder agents
itself. The intra-module WI split + the backend-before-frontend order are owned by the `odoo-coder`
coordinator, not here.

## Out of Scope

- **Reviewing / auditing existing code (not writing)** → `odoo-code-review`
- **Locating where to hook into core logic (one method)** → `odoo-override-finding`
- **Deprecation analysis / upgrade planning** → `odoo-deprecation-audit` / `odoo-version-diff`
- **Designing the approach before any code (non-trivial)** → `odoo-solution-design`
- **Verifying the rendered UI / a runtime render error / image regression** → `odoo-ui-review` / `odoo-debug` / `odoo-visual-regression`

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
`inputs` on a `run-harness` or `odoo-planning` handoff (`run-harness`'s between-wave integration
INVOKES this skill per MODULE from its orchestrating context, passing one module's slice + that module's
worktree path - see WORKTREE_PATH below): the **target module set**, the **wave-batched module-DAG**,
the **wave / topology**, and the **design pointers** (`design_index` / `design_doc` / `design_docs`,
carrying the per-module stack split + effort) - CONSUME them verbatim
and SKIP the self-derivation steps that would recompute them: the design-doc resolution (step 1),
the module-set step (2), and the dependency-order +
wave derivation (step 4). **Stack tag (step 3) - consume, else infer (never silently skip):** take
each module's stack from the module brief's `STACK` field (or the design pointers' per-module stack
split) when provided; when the plan carries `DESIGN_DOC: none` and no `STACK` (e.g. a between-wave module
with no design doc), the stack is not yet known - retain step 3's file-based inference (`models/` /
`views/` / `security/` / `*.csv` => backend; `static/src` JS/SCSS/QWeb => frontend; both =>
fullstack) rather than skipping it. The plan is the SSOT for the inter-module layer
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md`: `odoo-planning` is the canonical
producer of the wave-batched module-DAG; `odoo-coding` runs the module-graph algorithm itself ONLY
when standalone OR when the plan carries no dependency diagram to consume). You STILL run the intra-skill steps this skill owns at runtime - **step 5**
(model tier per module) and **step 6** (test-first per module) - plus the inter-module dependency
dispatch ordering (the intra-module WI split + the backend-before-frontend order is the
`odoo-coder` coordinator's, not this skill's); the plan binds WHICH modules build in WHAT order, never how many agents or which model
(the plan's `est_agents` / `effort` is ADVISORY - this skill decides the actual count + tier at
runtime). Trust-but-verify: if a fed module / DAG node cannot be resolved on disk, STOP and report
BLOCKED - never silently self-derive a different graph. When dispatched under an active run-harness
(a named `run-<id>`) OR with a `WORKTREE_PATH` (the pre-approved between-wave integration path -
see WORKTREE_PATH below) the upstream approval (`odoo-planning` ExitPlanMode / the driver L2 gate)
already stands, so do not re-emit the Phase-0 confirmation gate - a per-module gate here would stall
`run-harness`'s sequential between-wave loop; otherwise (a plan fed to a standalone invocation with no worktree)
proceed to the gate below.

**Worktree + commit (caller-agnostic; triggered by the WORKTREE_PATH field, not caller identity).**
Work ALWAYS lands COMMITTED inside an isolated worktree - never an uncommitted diff, never a write
to the principal checkout (S9). A `WORKTREE_PATH` reaches this skill from `run-harness`'s between-wave
integration (per-module) or the `odoo-intake -> Phase P -> run-harness` chain (run-harness Hard rule 6). The `odoo-coder`
COORDINATOR `cd`s there, its hard-leaf coders author + RETURN their file list (no git, per
`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`), then - once the integrated module test is green -
the COORDINATOR itself COMMITS the module by invoking `git-toolkit:git-ops` and returns the SHA.
THIS skill no longer re-commits: it COLLECTS the coordinator's returned SHA(s) and passes them up
(to `run-harness`'s between-wave integration for cherry-pick, or reports them). The coordinator can commit
directly because its worktree is dependency-correct - forked from the integrated state, the property
the planned worktree graph (Block 2W) guarantees. If invoked standalone with NO `WORKTREE_PATH`,
this skill FIRST invokes `git-toolkit:git-ops` to provision a worktree/branch (never the principal
checkout) and hands its path to the coordinator to author + commit in - a FALLBACK only, deliberately
NOT a member of `git-delegation.md` § Self-provisioning specialists, so an orchestrator dispatching
`odoo-coding` SHOULD still provision the worktree first per `run-harness` Hard rule 6. S9: every git
op is delegated to `git-toolkit:git-ops` and runs ONLY inside the worktree. See
`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.

**No plan provided (bare standalone invocation) - self-derive and proceed.** `odoo-coding` is a
pipeline stage, not an admission point: the mandatory-planning gate is enforced UPSTREAM at the
front door (`odoo-intake` / `odoo-brl` / the `odoo-implement-feature` workflow) per
`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Mandatory-planning rule, so this stage
never self-blocks for "no plan" - when given plan inputs / `run-<id>` / `WORKTREE_PATH` it consumes
them (fast-path above), and invoked standalone it self-derives the approach in the steps below.

**1. Resolve any existing design doc (index-first, backward-compat).**
When a `design_doc` is already provided by the caller (via Continuation Contract `inputs.design_doc` / `inputs.design_docs`, e.g. a `return_to` or run-harness handoff), use it directly as `DESIGN_DOC` and build to it - skip the resolution below. Otherwise:
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
3. **None:** neither found - no approved design in scope; self-derive the approach in the steps below (this is a normal standalone path - admission is the front door's job, not re-checked here).

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
with `run-harness`'s between-wave integration so both order work the same way. In short: call
`module_inspect(name=<m>, method='dependencies', odoo_version='[resolved version]')` per target
module (concrete version - the pin is per-API-key and racy, see
`skills/_shared/concurrency-guard.md` "OSM version-pin race"), build the sub-graph restricted to the
target set, and topologically order it - independent modules share a **wave** (parallel), a
dependent module runs in a **later wave**. The disk fallback (haiku reader of each
`__manifest__.py` `depends` + `static/src` scan, labelled "graph from disk (OSM unavailable)")
lives in that SSOT.

**5. Assign a model tier per module (deterministic - no judgment call mid-flow).**
Every dispatch in this skill passes an explicit `model`. Resolve the tier for each
module by walking this table TOP-DOWN and stopping at the FIRST match.
When a design doc is present, its effort tier takes precedence over the heuristics. The bar for
opus is DOMAIN complexity, not size: sonnet handles a large single-domain module; opus is reserved
for a change reasoning across MULTIPLE hard business domains AND entangled with many interacting
modules.

| # | Condition (first match wins) | Tier |
|---|---|---|
| 1 | Design doc grades it Custom-XL AND the change alters an inheritance axis across multiple modules - the apex of domain + structural complexity | **fable** |
| 2 | The module reasons across MULTIPLE hard business domains AND is coupled to many interacting modules (both together - not size alone). Qualifying signals: design doc Extension-L / Custom-XL with high cross-module coupling; a core `create`/`write`/`unlink` override whose correctness spans many dependents (`find_override_point` >=3-entry chain, OR `impact_analysis` shows a wide downstream ripple); a cross-model computed chain plus multi-company logic spanning modules; a migration with >1 viable strategy touching many modules | **opus** |
| 3 | Design doc grades it Standard or Config; OR (single-stack AND <=2 intended files AND ~<=50 LOC AND no method override): one field/attr, boilerplate XML view shell, label/string change, security CSV row | **haiku** |
| 4 | Everything else - and the RIGHT default for large-but-tractable work: a big single-domain module, high LOC or many files, a normal computed/onchange/constraint, a single-method override, a standard OWL widget, a full-stack module, even a large / high-blast-radius module that stays within one business domain - plus ANY genuinely ambiguous case you cannot classify confidently. Size, file count, and blast radius alone never escalate past sonnet; only Row-2 multi-domain + heavy-dependency complexity does | **sonnet** (default) |

Constraints on the table:
- **sonnet is the ambiguous-case default and the home of LARGE work.** If two rows
  seem to apply, the higher row (smaller #) wins; if NO row clearly applies, use
  sonnet. Do NOT escalate to opus for size, file count, or blast radius alone -
  Row 2 requires multi-domain difficulty AND cross-module entanglement together.
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

**6. Coverage pre-flight per module (red before green - authoring is universal).** The test protects
the business behavior and is written BEFORE the code
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`). Test authoring is UNIVERSAL and
context-isolated: the `odoo-coder` coordinator launches the `odoo-test-writer` agent FIRST per WI to
author the RED test, then the coder makes it green - so the test author is never the code author
(independence keeps the test honest). This skill does NOT launch `odoo-test-writer` and does NOT
choose a per-module test mode - it grounds the coverage scope here and forwards it to the
coordinator, which forwards it to `odoo-test-writer`.

**Coverage pre-flight (run before assigning test mode).** For each non-trivial module, query OSM
to ground the test scope - only write what is NOT already covered:
- `tests_covering(model='<primary_model>', odoo_version='<version>')` - lists every TestMethod
  already exercising that model; carry this list forward into the `odoo-test-writer` brief so the
  author writes additive tests only, never re-invents existing ones.
- `test_coverage_audit(module='<module>', odoo_version='<version>')` - surfaces fields with zero/partial static-reference coverage (field-level only; does NOT report method gaps and is NOT executed coverage); use this to bound the scope (test only the field gaps).
- `test_base_classes(odoo_version='<version>')` - retrieves the authoritative base class menu
  (TransactionCase, SavepointCase, HttpCase, ...) with the hard rule that **`cr.commit()` is
  FORBIDDEN inside TransactionCase / SavepointCase - isolation is savepoint rollback**. Include
  the matching base class in the `odoo-test-writer` brief so the author never has to guess.

Skip the coverage pre-flight only when OSM is unreachable (standalone/disk fallback, same flag
as step 4); in that case `odoo-test-writer` works from disk context alone.

Carry the coverage pre-flight results (`EXISTING COVERAGE` / `COVERAGE GAPS` / `BASE CLASS`) into
the coder brief so the coordinator seeds the `odoo-test-writer` brief with them (additive tests
only, never a duplicate). There is no per-module `test-author` vs `self` choice anymore - every
module's RED test is authored by the `odoo-test-writer` agent the coordinator launches first.

Then emit the gate and wait. Write the gate message in the USER'S language (translate
labels and prose; keep module names, paths, and the reply keywords verbatim - SSOT:
`${CLAUDE_PLUGIN_ROOT}/snippets/language-mirroring.md`), and when the user is not
working in English pass `userLanguage` in the coder brief so the coder agents
return their summaries pre-mirrored:

```
Proposed: <one-line summary of the change>.
Plan:
  | module | stack     | wave | model  | test        | files (intended) |
  | <m1>   | backend   | 1    | haiku  | test-writer | <m1>/models/*.py, __manifest__.py |
  | <m2>   | fullstack | 1    | opus   | test-writer | <m2>/models/*.py, <m2>/static/src/*.js, __manifest__.py |
  | <m3>   | frontend  | 2    | sonnet | test-writer | <m3>/static/src/*.js (depends on <m1>) |
Design: <DESIGN_DOC child path | none> [Master: <MASTER_DESIGN_DOC path | none>]
OSM: backed | standalone
Dispatch: subagent launch model-weighted batches
Proceed? (yes / refine: [feedback] / cancel)
```

The `wave` column stays for the reader's benefit (it shows depends-on), but the
executor does not barrier on waves - dependency order is enforced per-module
during execution.

On `yes`, execute; on `refine: …`, update and re-emit; on `cancel`, stop.

## Execution - dispatch ONE odoo-coder per module (model-weighted batches)

The coder agents run as autonomous agents - never inline codegen in main, never via the Skill tool.
Launch **ONE `odoo-coder` COORDINATOR PER MODULE** (every module, whatever its stack tag; launch the
agent by name; if a short name fails to resolve, retry with the plugin-qualified form
`odoo-ai-agents:odoo-coder`):

- **any module (backend-only, frontend-only, or fullstack)** -> launch ONE `odoo-coder` per-module
  COORDINATOR. It coordinates the module end to end: it splits the module into 1..N INTERNAL WIs by
  disjoint file sets, schedules independent WIs in parallel and dependent ones sequentially (backend
  before a frontend that binds it), launches `odoo-backend-coder` for each backend WI and
  `odoo-frontend-coder` for each frontend WI, owns the integrated whole-module test + the bounded fix
  loop, and RETURNS the aggregated file list to this skill. You do NOT launch the worker agents
  yourself and you do NOT decide the WI split - the coordinator does. The stack tag is passed to the
  coordinator as a hint; a single-stack module simply yields one-or-more same-stack WIs.

Do NOT build a Claude Code Workflow (JS) script for this - all fan-out is real agent launches;
narrating a dispatch in prose instead of launching the agent is not allowed.

Concurrency/OOM rule (SSOT: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`, Mode B):
model-weighted budget - WEIGHT haiku=1, sonnet=2, opus=4, fable=8; at most 8 weight-units in flight
at once (keeps opus <=2 and fable exclusive while haiku/sonnet flow freely).

Instance-allocation rule (SSOT: same `concurrency-guard.md` § Odoo instance allocation): a coder or
`odoo-test-writer` that runs `odoo-bin` against a database (tests via `--test-enable`, `-i`/`-u`, or
scaffolding into a DB) and was handed NO `INSTANCE_HANDLE` self-provisions an ISOLATED instance by
invoking `Skill(odoo-instance)` (a unique ephemeral DB acquired UNDER the HARD RULES),
never a bare `scripts/lib/allocator.py` call that would bypass them - so the brief never passes a
shared db/port. A provided handle always wins (consume, never re-provision).

### Dispatch loop - model-weighted batches

The Phase 0 plan carries, per module: name, path on disk, stack, model (and `frontendModel` when
split), the in-set dependency edges (the "(depends on ...)" in the gate table), whether it is a new
module, the coverage pre-flight (universal test-first via `odoo-test-writer`), and the per-module
request (+ a frontendRequest for the UI leg). Resolve ONE concrete Odoo version for the whole run via
`${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md` (read `.odoo-ai/context.md` -> manifest
`version` -> ask the user) - NEVER a silent default; when a plan/design fed `odoo_version` in the
Continuation-Contract `inputs`, consume it verbatim. Carry the design-doc path, the runSlug
(scopes the shared worklog dir) and - when the user is not working in English - the userLanguage.

0. Context-handoff probe (run ONCE per run, before the first batch fires). Follow
   `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md`: run the capability probe a single
   time and cache the result for the whole run. When Tier A is available, spawn each coder with a
   stable `name` (e.g. `coder-<module-slug>`), and - as the LEAD and sole address authority - capture
   the `agentId` the Agent launch returns and record it per module in plan.md (the coordinator never
   self-IDs). When Tier A is NOT available, proceed exactly as today (Tier C: fresh Agent calls,
   worklog for context). Tier C is always correct; Tier A is an optional optimization that degrades
   silently to Tier C. When the CHP capability probe is positive (Agent Team mode on), TaskCreate
   one task per dispatched module, inject TASK_ID + REPLY_TO: the current orchestrating context
   (`main` here) + NOTIFY: <dependent names> into each teammate brief, poll TaskList/TaskGet for
   status, and read each result from the
   teammate's SendMessage push (NEVER from the .output transcript) - per
   `${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md`. When off, dispatch + collect as today.
1. Order modules so every module appears after its in-set dependencies (the wave column already
   encodes this).
2. Greedily pack the next batch: take modules in order whose dependencies are all done (done = the
   dependency module's `odoo-coder` coordinator reported all its WIs green + the integrated
   whole-module test passed) and whose summed WEIGHT stays <= 8. A
   fable item always forms a batch of ONE.
3. Fire the whole batch as parallel agent launches in a SINGLE message, ONE `odoo-coder` coordinator
   per module (the coordinator internally splits the module into WIs, sequences backend-before-frontend,
   and runs the integrated test - you do not fire the worker agents or decide the WI split yourself).
   When Tier A is in effect, give each launch its stable `name` and record the returned `agentId` in
   plan.md as you go.
4. Wait for the batch (a batch barrier each round): after firing the parallel `odoo-coder` launches
   in step 3, hold until every coordinator task on the run's task list is `completed`/`blocked`
   before packing the next batch - the barrier is mechanical per
   `${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R1, not an assumption. A batch is
   done only when every coordinator returned DONE/BLOCKED (R2). A later step re-dispatches
   a BLOCKED module at the SAME recorded tier: under Tier A, resume the recorded `agentId` by
   `SendMessage` when it is still addressable; otherwise (Tier C fallback) make a fresh Agent call.
   The worklog stays the always-correct context layer the re-dispatched worker reads.
5. Each subagent launch sets BOTH the `model` parameter AND the first prompt line
   `DISPATCH MODEL: <haiku|sonnet|opus|fable>` (belt and braces, mirroring `odoo-debug`).
6. fable -> opus downgrade: if a fable dispatch fails (insufficient usage credit, model unavailable,
   subagent error), retry that module ONCE at `model: opus` and record the downgrade in plan.md
   (`opus (fable unavailable)`).
7. Test-first (red before green): pass each module's coverage pre-flight results to its `odoo-coder`
   coordinator. The coordinator owns the per-WI test-first for EVERY module: it launches the
   `odoo-test-writer` agent FIRST per WI (the dedicated context-isolated test author - never the code
   author, independence keeps the test honest) and hands the returned RED test paths to that WI's
   coder, which implements to green. THIS skill does NOT launch `odoo-test-writer` and the coders no
   longer author tests - the coordinator launches `odoo-test-writer`, and it is the ONLY test author.

### Dependency-BLOCKED handling + the module-coordination ledger

THIS skill (not the leaf coder) owns cross-module coordination for NEW modules - it alone holds the
batch map, the DONE barrier, and (now) the coordination ledger. Full contract:
`${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md` (do NOT restate it here).

**Write the ledger (only this skill writes it).** Resolve `LEDGER_ROOT` once per run via
`git rev-parse --git-common-dir` so it is shared across every linked worktree and concurrent run.
For each NEW in-scope module (a module resolving to neither OSM nor disk per
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md`), before dispatching its coder:

- CLAIM it with the atomic `mkdir "$LEDGER_ROOT/$MODULE"` (winner writes `entry.json` status
  `claimed`; a loser reads the existing entry and classifies via the decision table below);
- flip `claimed` -> `building` when its coder is dispatched, -> `done` on the module's DONE, ->
  `failed` on a terminal BLOCK;
- refresh `heartbeat_at` on EVERY dispatch-loop tick for each module this run is currently building.

The hard-leaf `odoo-backend-coder`/`odoo-frontend-coder` workers stay ledger-unaware; only the
`odoo-backend-coder` runs the dependency pre-flight and returns the RAW status below (the module's
`odoo-coder` coordinator relays its backend worker's raw status up unchanged - it does not classify
either).

**Classify a worker's `BLOCKED: manifest dependency <D> unresolved`.** When a dispatched worker (or
the coordinator relaying it) returns that raw status, run the 6-row decision table in the ledger snippet (case 1 on-path -> proceed; 2
in-set sibling of THIS run still claimed/building -> re-queue after the sibling reaches DONE, a
same-run `failed` sibling falls to case 5; 3 fresh claim/build by a DIFFERENT run -> WAIT bounded by
N barriers then demote to 6; 4 done-elsewhere-not-on-this-worktree -> BLOCKED integrate/rebase; 5
failed (own sibling or elsewhere) -> BLOCKED; 6 absent OR stale heartbeat -> clean BLOCKED missing
prerequisite). The worker (and the coordinator) NEVER perform this split - they cannot see the batch or the ledger. THIS
skill owns the case-3 N-barrier WAIT ENTIRELY and internally: it waits, bounded by N dispatch-loop
barriers, for the concurrent build to land, and on exhaustion returns a normal clean case-6 BLOCKED -
its caller (`run-harness`'s between-wave integration) never re-implements a barrier wait. Honesty invariant: a run that never
wrote the ledger, or a dead/stale run, lands in case 6 as a clean BLOCKED, never a false "in
progress"; absence is always the honest fallback.

### Per-module briefs

Each agent launch carries the brief below as its `prompt`. The brief is **run-specific inputs
only**: every procedure (OSM grounding, coding guidelines, worklog read/append, ORM + static gates,
demo data, output format, test-first) already lives in the launched agent's system prompt, so do NOT
re-teach it here - a re-taught copy duplicates the SSOT and drifts. Keep identifiers verbatim. The
brief goes to the `odoo-coder` COORDINATOR for EVERY module; the coordinator forwards the
module-scoped fields to whichever worker(s) each of its INTERNAL WIs needs (`odoo-backend-coder` for a
backend WI, `odoo-frontend-coder` for a frontend WI - it adds `frontendRequest` for a frontend WI).

**Dispatch-brief skeleton.** Fill the prompt below from the caller-side skeleton in
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` (read it by path) plus the Coder family delta;
never inline that file verbatim into a hard-leaf brief.

Coder brief (target = the `odoo-coder` coordinator for the module):

```
DISPATCH MODEL: <tier>
REQUEST: <the change for this module: target model + constraints (+ frontendRequest for a frontend WI)>
STACK: <backend | frontend | fullstack - hint for the coordinator's WI split; it decides the actual 1..N WIs>
MODULE SCOPE: <name> @ <path> - write ONLY within this module (+ its __manifest__.py / static assets).
WORKTREE_PATH: <absolute worktree path | none> - when set (run-harness between-wave integration path): `cd` here and write ALL your work in this worktree; your hard-leaf coders RETURN their file lists (no git), then YOU (the coordinator) COMMIT the module via `git-toolkit:git-ops` once the integrated test is green and RETURN the SHA - `odoo-coding` collects it and `run-harness`'s between-wave integration cherry-picks it. `none` -> author in the current checkout as usual, no git.
NEW MODULE: <yes - ALWAYS scaffold with `odoo-bin scaffold` first; edit only needed keys and KEEP scaffold's commented placeholders; keep its short version default, do NOT rewrite to `<series>.x.y.z` | no>
ODOO VERSION: <version>
INSTANCE_HANDLE: <the run's provisioned instance handle from a prior odoo-instance step, when present - db_name/http_port/addons_path/venv/lease_token; omit when the run provisioned none>
DESIGN_DOC: <child TDD path | none> - per-module spec; if present, build to it; do not re-derive.
MASTER_DESIGN_DOC: <master TDD path | none> - hard constraints (ownership, dep-direction, §10 contracts); `none` in single mode.
TEST: test-first (universal) - launch `odoo-test-writer` FIRST per WI to author the RED test, then the coder implements to green; the coders do NOT author tests. Forward the coverage pre-flight below to `odoo-test-writer`.
EXISTING COVERAGE: <tests_covering(model='<primary_model>', odoo_version='<version>') output - TestMethods already covering this model; author ADDITIVE tests only>
COVERAGE GAPS: <test_coverage_audit(module='<module>', odoo_version='<version>') output - fields with zero/partial static-reference coverage (field-level only); prioritise these gaps>
BASE CLASS: <base class from test_base_classes(odoo_version='<version>'), e.g. TransactionCase - cr.commit() FORBIDDEN, isolation is savepoint rollback>
WORKLOG: <runSlug> - read it, then append your significant decisions.
USER LANGUAGE: <lang | omit when the user works in English> - write the summary in this language; keep identifiers verbatim.
Follow the Rounds in your system prompt - it owns every procedure; do not re-derive what it already specifies.
GUIDELINES: Round 1 owns this - open `coding_guidelines/<version>/INDEX.md` first, consult the "By task" table, read ONLY the mapped files (not the whole directory).
```

- When an `INSTANCE_HANDLE` is present in the brief, the instance-touching agent MUST use it and
  MUST NOT self-provision a DB / port / addons_path. Absent a handle: the `odoo-backend-coder`
  self-provisions its bounded lint gate via `Skill(odoo-instance)`, and the `odoo-coder`
  coordinator self-provisions the INTEGRATED module test the same way (never a bare `allocator.py` call -
  `skills/_shared/concurrency-guard.md` § Odoo instance allocation). The `odoo-frontend-coder` is
  INSTANCE-FREE: it never self-provisions; its live check is the coordinator's integrated module test.
  Contract: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`.
- To run `odoo-bin` (scaffold, or tests via `--test-enable`), resolve the interpreter per
  `snippets/venv-resolution.md` - never assume system `python3`.
- Frontend WI only: ground styling tokens against `skills/_shared/odoo-frontend-fidelity.md`
  (no hardcoded hex for themeable colors, no self-referential `--bs-*` shim) - the full method lives
  in the agent's system prompt.

The `odoo-coder` coordinator (not this skill) launches the `odoo-test-writer` agent per WI FIRST -
its authoring brief (MODE, MODULE SCOPE, TARGET BEHAVIOR, TEST TYPE(S), plus the coverage pre-flight
fields above) is the coordinator's to assemble; this skill never pre-dispatches a test author and
the coders never author tests. `odoo-test-writer` follows `snippets/test-first-contract.md`
(red-before-green) and `snippets/test-behavior-contract.md` (drive the real workflow -
action_confirm/action_validate/button_validate, Form() for onchange, with_user() not sudo(); never
seed the terminal state with create({state:...})): assert observable behavior not internals; ONE
intent per test; confirm each goes RED.

Each hard-leaf coder locates files via Read/Grep, writes its output, and reports the files written
plus `__manifest__.py` changes - it does NOT run git. The module's `odoo-coder` coordinator
aggregates ALL its WIs' workers' file lists and, once the integrated module test is green, **COMMITS
the module itself by invoking the `git-toolkit:git-ops` skill** inside the worktree (it requests the
commit; git-ops owns the message convention + DCO + mechanics) and captures the commit SHA on the
module branch. **THIS skill then COLLECTS the coordinator's returned SHA(s) and passes them up so
`run-harness`'s between-wave integration can cherry-pick them (or so any caller can integrate) - it does NOT
re-commit; a DONE with no returned file list, no integrated-test verdict, or no SHA from the
coordinator is a failed contract.** The old depth-saver clause (commit-stays-at-this-skill) is
REMOVED: the coordinator now commits in its dependency-correct worktree (forked from the integrated
state per Block 2W), so git-ops fires from the coordinator, not this skill. `odoo-coding` NEVER
completes with uncommitted output: if it was dispatched WITHOUT a `WORKTREE_PATH`, it self-provisions
a worktree/branch via `git-toolkit:git-ops` (never the principal checkout, S9) and hands it to the
coordinator to commit in - a FALLBACK only, NOT
membership in `git-delegation.md` § Self-provisioning specialists; an orchestrator dispatching
`odoo-coding` SHOULD still provision the worktree first per `run-harness` Hard rule 6.

## Artifacts - persist the coding plan

Write the orchestration plan to `.odoo-ai/coding/<slug>-<YYYY-MM-DD>/plan.md` (`.odoo-ai/` is
gitignored): the module/stack/wave/**model** table, the computed dependency order, and the design
doc referenced. The agents write source directly; `plan.md` records what was built so a later
review / fix / resume step can pick up without recomputing the graph. `<slug>` derives from the
change (branch, feature name, or the module set).

plan.md MUST record, per module: stack, wave, the model tier chosen
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

This skill is part of an agent+skill bundle. The codegen detail lives on the agents -
see `agents/odoo-coder.md` (the per-module coordinator - owns the internal WI split + launches THREE
teammates), `agents/odoo-test-writer.md` (the hard-leaf test author launched FIRST per WI - authors
the RED test by invoking the `odoo-test-writing` skill inline), `agents/odoo-backend-coder.md`
(the backend hard-leaf writer + its lint gate), and `agents/odoo-frontend-coder.md` (the frontend
hard-leaf writer + its static gate) for the execution detail; agents inherit the full tool surface.

## The code -> review+test -> code loop (bounded)

Coding is not one-shot. After this skill writes code (each non-trivial module implemented to a
separately-authored failing test), the **code -> review+test -> code** round-trip runs:
`odoo-code-review` reviews AND checks the tests cover the behavior, looping back on a CRITICAL/HIGH
issue or a red/missing test.

**Drive it yourself in the default case (mandatory).** The Skill tool is available here. After
writing, **IMMEDIATELY invoke `odoo-code-review` via the Skill tool yourself** and fix within the
bounded loop below before returning. A passive `next: odoo-code-review` is only ever advanced by
`run-harness` itself, and only when `run-harness` scheduled THIS `odoo-coding` invocation as its
own RUN-DAG node - in every other path nothing advances a per-module `next`, so verification would
silently never happen. The two branches, precisely:

- **Direct run-harness RUN-DAG node (the only emit-next case).** `odoo-coding` is dispatched
  DIRECTLY by `run-harness` and named as its own `run-<id>` node - `run-harness` owns the DAG and
  WILL schedule the review node. Emit `next: odoo-code-review` and let it advance; do not
  double-dispatch.
- **Every other invocation (default - drive inline).** This is the default, and it explicitly
  INCLUDES a `run-harness` between-wave integration invocation (during between-wave integration
  `run-harness` invokes this skill via the Skill tool per MODULE, passing `WORKTREE_PATH` +
  `WORKLOG: <runSlug>` but no `run-<id>` RUN-DAG node for that module - it never schedules a
  per-module `next`), plus direct invocation, intake fast-path, and autonomous fix. A
  transitively-active run, or a bare `runSlug` / `WORKLOG` value, is NOT a run-harness RUN-DAG node
  and must NOT be read as one - it does not trigger the emit-next branch. DRIVE
  `odoo-code-review` inline yourself and fix in the bounded loop below before returning.

Emit the Continuation Contract either way.

Bound the loop to **3 iterations** per `${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`; still
not green-and-clean after 3 -> STOP and escalate (bad work is worse than no work). Each iteration's
outcome goes in the worklog.

## Continuation Contract

When the bundle finishes, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Set
`produced` to the source + test files written, plus `.odoo-ai/coding/<slug>-<date>/plan.md` and the
`.odoo-ai/worklog/<slug>/` entries, and emit `next: odoo-code-review` with `inputs: {odoo_version:
<the run's resolved version>}` (a reserved key - `continuation-contract.md` Rules) so the review
runs against the same pinned version without re-deriving it (that skill now scales to the same
multi-module set). Additionally, when any module in the
run is new (`NEW MODULE: yes`) OR the change introduces user-facing translatable strings
(`_("...")` / `string=` field attr), also add `SUGGESTED_NEXT: odoo-i18n` so the module's
`.pot` / `.po` files are generated and translated via the dedicated i18n skill. Additive output for the
run-harness - it does not change anything produced above.
