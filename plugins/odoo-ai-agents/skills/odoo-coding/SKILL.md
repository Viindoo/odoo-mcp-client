---
name: odoo-coding
argument-hint: "[what to build or change]"
description: >
  Use when someone wants to build or change Odoo behavior and needs the code written - the
  single front door for ALL Odoo coding and the sole dispatcher of the odoo-coder work-node
  coordinator, scoping and ordering nodes by dependency. Fire on ANY request to add or change
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

Developer - full-stack Odoo coder (all versions, v8 onward). Orchestrates by WORK NODE: for each
node in the plan (or self-derived when standalone) it resolves the node's module set and
dependency order, assigns a model tier, and dispatches **ONE `odoo-coder` COORDINATOR per node**
(every node - backend-only, frontend-only, or full-stack; a node may name one module, part of one,
or several). The `odoo-coder` coordinator owns the node's INTERNAL work-item (WI) breakdown: for
its ONE node it splits the changes into 1..N WIs by DISJOINT file sets, schedules INDEPENDENT WIs
in PARALLEL and DEPENDENT WIs SEQUENTIALLY (a frontend WI that binds a backend WI runs after it -
the backend-before-frontend order), assigns each WI to the right worker (backend files ->
`odoo-backend-coder`, frontend files -> `odoo-frontend-coder`), and owns the integrated whole-node
test on ONE instance. This skill does NOT split a node into WIs and does NOT sequence
backend/frontend - that is `odoo-coder`'s job (SSOT for the two-tier axis:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md` § Two-tier decomposition axis - the
OUTER unit here is the NODE, the WI is `odoo-coder`'s INTERNAL unit; the MODULE is a property of a
node, never the unit of dispatch).

Pair-works with `odoo-code-review` for review.

**Sole dispatcher (single source of truth for coding fan-out).** This skill is the ONLY component
that computes the node dependency order + the model tier and launches the `odoo-coder`
coordinator (one per node). Any other skill that needs Odoo code written routes its coding work
HERE via the Skill tool (passing its context in the brief) instead of launching the coder agents
itself. The intra-node WI split + the backend-before-frontend order are owned by the `odoo-coder`
coordinator, not here.

## Out of Scope

- **Reviewing / auditing existing code (not writing)** → `odoo-code-review`
- **Locating where to hook into core logic (one method)** → `odoo-override-finding`
- **Deprecation analysis / upgrade planning** → `odoo-deprecation-audit` / `odoo-version-diff`
- **Designing the approach before any code (non-trivial)** → `odoo-solution-design`
- **Verifying the rendered UI / a runtime render error / image regression** → `odoo-ui-review` / `odoo-debug` / `odoo-visual-regression`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`, `describe_module`, `check_module_exists`, `resolve_orm_chain`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `find_override_point` - Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior.
- `impact_analysis` - Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields.
- `tests_covering` - List test methods that have COVERS_MODEL/COVERS_FIELD/COVERS_METHOD edges to the target model or field (static reference coverage, not runtime executed coverage).
- `test_coverage_audit` - Audit an entire module for test coverage gaps: lists fields/methods with zero COVERS_* edges (never referenced by any test).
- `test_base_classes` - Menu of official Odoo test framework base classes (TransactionCase, HttpCase, SavepointCase, Form, etc.) for the given version, with test_type and cursor contract.
<!-- END GENERATED TOOLS -->

## Phase 0 - Scope + module graph (1-turn gate, mandatory)

**Orphan sweep (do this every run, at the very start of this Phase 0, before anything else
below).** `coding/<slug>-<date>/plan.md` is never deleted by anything today, so it leaks one
directory per run forever (resolve `<ISOLATE_DIR>` per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` first if not already captured this turn):

`find <ISOLATE_DIR>/coding/ -mindepth 1 -maxdepth 1 -type d -mmin +43200 -exec rm -rf {} +`

(any sibling `<slug>-<date>/` dir untouched for over 30 days is presumed consumed). Full rule + bound rationale:
`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3. Enforcer: whoever
executes `odoo-coding` next, unconditionally, every run.

This is the single confirmation checkpoint. It applies even when the request arrived directly
(e.g. intake bypass) - **unless your brief carries the AUTONOMOUS FIX sentinel (see the exception
immediately below), in which case you skip this gate entirely.**

**Autonomous-fix exception - SKIP this gate entirely** when your brief contains
**"AUTONOMOUS FIX (review-driven)"** or **"AUTONOMOUS FIX (debug-driven)"**: the human already
opted into the autonomous review/debug fix loop, so do NOT stop for a confirmation. Read the worklog
+ the review report / proven root cause passed in, then proceed straight into the dispatch+fix loop:
dispatch the `odoo-coder` coordinator(s) (per ## Execution below) to fix to those findings - this
skill never edits files inline itself - and the moment they return **IMMEDIATELY invoke
`odoo-code-review` via the Skill tool yourself** to verify (§ The code -> review+test -> code loop).
Bound to 3 iterations, then STOP and escalate.

Otherwise (normal invocation), First READ any existing worklog for this run. Worklog is Tier-2
ISOLATE. **When your own brief carries `SHARE_DIR:`/`ISOLATE_DIR:` fields, those literals ARE the
run's dirs for this whole invocation - substitute them and do NOT re-run the resolver, here or at
any later `<SHARE_DIR>`/`<ISOLATE_DIR>` below; re-resolving would fork the run's state root the
moment a per-node worktree enters the picture.** Only when both are absent, resolve them yourself
via the resolve-capture-substitute protocol in
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` (captured path shown as `<ISOLATE_DIR>`
below), BEFORE any `cd` into a worktree - either way ONE captured literal is what you forward to
every `odoo-coder` you dispatch. Read `<ISOLATE_DIR>/worklog/<run-or-slug>/*.md`, oldest-first - per
`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md` so you build on the decisions an upstream
phase (e.g. `odoo-solution-design`) already recorded instead of re-deriving them. Then do six
things, then stop for the user's reply.

**Plan-provided fast-path - CONSUME the plan, do NOT re-derive (inter-node layer).** When the
caller hands you a PLAN's already-computed inter-node results - via the Continuation-Contract
`inputs` on a `run-harness` or `odoo-planning` handoff (`run-harness` dispatches this skill ONCE
PER CODING NODE from its driver loop, passing that node's slice + that node's worktree path - see
WORKTREE_PATH below): the **target node** (its `modules`, in dependency order), the **node DAG**
(`depends_on` edges between nodes), the **design pointers** (`design_index` / `design_doc` /
`design_docs`, carrying the per-node stack split + effort), and, when present, the **survey
pointer** (`inputs.survey` / the brief's `SURVEY:` field - a deep-survey synthesis path for
additional hotspot/impact grounding, per
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/phase-p-run-dag.md` § Survey pointer; the
literal `none` means no deep survey ran this session, never a missing/gap condition) - CONSUME
them verbatim and SKIP the self-derivation steps that would recompute them: the design-doc
resolution (step 1), the node-set step (2), and the dependency-order derivation (step 4). **Stack
tag (step 3) - consume, else infer (never silently skip):** take the node's stack from the node
brief's `STACK` field (or the design pointers' per-node stack split) when provided; when the plan
carries `DESIGN_DOC: none` and no `STACK` (e.g. a dynamic node with no design doc), the stack is
not yet known - retain step 3's file-based inference (`models/` / `views/` / `security/` / `*.csv`
=> backend; `static/src` JS/SCSS/QWeb => frontend; both => fullstack) rather than skipping it. The
plan is the SSOT for the inter-node layer (`odoo-planner` is the canonical author of the node DAG -
see `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md`; `odoo-coding` runs the
module-graph algorithm itself, then partitions into nodes, ONLY when standalone OR when the plan
carries no dependency diagram to consume). You STILL run the intra-skill steps this skill owns at
runtime - **step 5** (model tier per node) and **step 6** (test-first per node) - plus the
inter-node dependency dispatch ordering (the intra-node WI split + the backend-before-frontend
order is the `odoo-coder` coordinator's, not this skill's); the plan binds WHICH nodes build in
WHAT order, never how many agents or which model (the plan's `est_agents` / `effort` is ADVISORY -
this skill decides the actual count + tier at runtime). Trust-but-verify: if a fed node cannot be
resolved on disk, STOP and report BLOCKED - never silently self-derive a different graph. When
dispatched under an active run-harness (a named `run-<id>`) OR with a `WORKTREE_PATH` (the
pre-approved node dispatch path - see WORKTREE_PATH below) the upstream approval (`odoo-planning`
ExitPlanMode / the driver L2 gate) already stands, so do not re-emit the Phase-0 confirmation gate
- a per-node gate here would stall `run-harness`'s sequential node loop; otherwise (a plan fed to a
standalone invocation with no worktree) proceed to the gate below.

**Worktree + commit (caller-agnostic; triggered by the WORKTREE_PATH field, not caller identity).**
Work ALWAYS lands COMMITTED inside an isolated worktree - never an uncommitted diff, never a write
to the principal checkout (S9). A `WORKTREE_PATH` reaches this skill from `run-harness`'s node
dispatch loop (one node per iteration, forked from that repo's run-integration branch) or the
`odoo-intake -> Phase P -> run-harness` chain (run-harness Hard rule 6). The `odoo-coder`
COORDINATOR `cd`s there, its hard-leaf coders author + RETURN their file list (no git, per
`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`), then - once the integrated node test is green -
the COORDINATOR itself COMMITS the node by invoking `git-toolkit:git-ops` and returns the SHA.
THIS skill no longer re-commits: it COLLECTS the coordinator's returned SHA and passes it up (for
`run-harness` to cherry-pick into the run-integration branch, or reports it). If invoked standalone
with NO `WORKTREE_PATH`, this skill FIRST invokes `git-toolkit:git-ops` to provision a
worktree/branch (never the principal checkout, resolving the fork point per
`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § Base-branch resolution rather than the
caller's ambient checkout) and hands its path to the coordinator to author + commit in - a
FALLBACK only, deliberately NOT a member of `git-delegation.md` § Self-provisioning specialists, so
an orchestrator dispatching `odoo-coding` SHOULD still provision the worktree first per
`run-harness` Hard rule 6. S9: every git op is delegated to `git-toolkit:git-ops` and runs ONLY
inside the worktree. See `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.

**No plan provided (bare standalone invocation) - self-derive and proceed.** `odoo-coding` is a
pipeline stage, not an admission point: the mandatory-planning gate is enforced UPSTREAM at the
front door (`odoo-intake` / `odoo-brl` / the `odoo-implement-feature` workflow) per
`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Mandatory-planning rule, so this stage
never self-blocks for "no plan" - when given plan inputs / `run-<id>` / `WORKTREE_PATH` it consumes
them (fast-path above), and invoked standalone it self-derives the approach in the steps below.

**1. Resolve any existing design doc (index-first, backward-compat).**
When a `design_doc` is already provided by the caller (via Continuation Contract `inputs.design_doc` / `inputs.design_docs`, e.g. a `return_to` or run-harness handoff), use it directly as `DESIGN_DOC` and build to it - skip the resolution below. Otherwise:
1. **Master-child (priority):** designs live under the Tier-2 SHARE dir; resolve it via the
   resolve-capture-substitute protocol in `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`
   (captured path shown as `<SHARE_DIR>` below), then glob `<SHARE_DIR>/designs/*/index.yaml`. If found, read the matching
   `index.yaml` per `${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md` - routing SSOT.
   When glob returns >1 file, apply the tie-break in `§Index selection` of that snippet (largest
   module-intersection → newest `created:` → alphabetical slug → emit `design_doc_ambiguity: true`
   when still tied). Resolve `master` and each `child_path` to ABSOLUTE paths (join the index
   directory + the relative value) before use. Per node: `DESIGN_DOC` = resolved absolute child
   path (matched against the node's module set); `MASTER_DESIGN_DOC` = resolved absolute master
   path. Never let the flat glob below match inside a master-child subdir.
2. **Single (fallback):** no `index.yaml` found - glob `<SHARE_DIR>/designs/<slug>-*.md`. If found:
   `DESIGN_DOC` = that path; `MASTER_DESIGN_DOC` = `none`. Behavior identical to pre-master-child.
3. **None:** neither found - no approved design in scope; self-derive the approach in the steps below (this is a normal standalone path - admission is the front door's job, not re-checked here).

When `DESIGN_DOC` is resolved, read it and **build to it** - do not re-derive the approach. When
`MASTER_DESIGN_DOC` is not `none`, it is the HARD constraint layer: ownership, dep-direction, and
§10 cross-module contracts in the master TDD are non-negotiable; a child that violates them is a
CRITICAL defect.

**2. Determine the target NODE set.** First derive the modules the change will touch from the
design doc / the request (coding *creates* the change, so there is no git diff to read - unlike
`odoo-code-review`). A "module" is the directory holding its DESCRIPTOR - `__manifest__.py`, or
`__openerp__.py` on v8-v9. Any discovery glob or existence check covers BOTH names; matching one
alone makes every module of a whole era read as non-existent (SSOT:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md`). Then partition that module set into
NODES by the plan schema's two rules
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` Block 1 -
same-landing-moment closure): modules that must reach the integration branch as ONE commit - a
later change depends on one but not the other, or they are not independently revertable - form ONE
node; modules that can land separately form separate nodes with DISJOINT `files-in-scope`.
Default, when nothing forces a split: one node per module. The MODULE stays a property of the
node - never the unit of dispatch - so a node may name one module, part of one, or several.

**3. Tag each node's stack-need** - `backend`, `frontend`, or `fullstack`, computed over the WHOLE
node (the union across every module it touches). Take it from the design doc when it already
splits the work; otherwise infer per module then union: touching `models/` `views/` `security/`
`*.csv` ⇒ backend; touching `static/src` JS/SCSS/QWeb ⇒ frontend; a node touching both, or
spanning a backend module and a frontend module, ⇒ fullstack.

**4. Compute the dependency order (OSM is ground truth).** Follow
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md` - the SSOT for the module DAG, shared
with `run-harness` so both order work the same way.

**Resolve the Odoo series ONCE here, before the first OSM call that needs it** (steps 4 and 6 below
both pass it, and both run BEFORE the gate): work the rungs of
`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` in order and stop at the first that
answers - NEVER a silent default. When a plan/design fed `odoo_version` in the Continuation-Contract
`inputs`, consume it verbatim. Carry that one concrete value as `[resolved version]` / `<version>`
through the rest of Phase 0 and into every dispatch brief (§ Dispatch loop).

In short: call
`module_inspect(name=<m>, method='dependencies', odoo_version='[resolved version]')` per target
module (concrete version - the pin is per-session and racy under a shared session, see
`skills/_shared/concurrency-guard.md` "OSM session-pin race"), build the sub-graph restricted to the
target set, and topologically order it at the MODULE level. Then fold that order UP to the NODE
level: node Y `depends_on` node X when any module in Y depends (directly or transitively) on any
module in X. Two nodes with no such edge may dispatch in ANY order - there is no grouping label,
only `depends_on`. The disk fallback (haiku reader of each module descriptor's `depends` - BOTH
names - plus a `static/src` scan, labelled "graph from disk (OSM unavailable)") lives in that SSOT.

**5. Assign a model tier per node (deterministic - no judgment call mid-flow).**
Every dispatch in this skill passes an explicit `model`. Resolve the tier for each
node by walking this table TOP-DOWN and stopping at the FIRST match.
When a design doc is present, its effort tier takes precedence over the heuristics. The bar for
opus is DOMAIN complexity, not size: sonnet handles a large single-domain node; opus is reserved
for a change reasoning across MULTIPLE hard business domains AND entangled with many interacting
modules.

| # | Condition (first match wins) | Tier |
|---|---|---|
| 1 | Design doc grades it Custom-XL AND the change alters an inheritance axis across multiple modules - the apex of domain + structural complexity | **fable** |
| 2 | The node reasons across MULTIPLE hard business domains AND is coupled to many interacting modules (both together - not size alone). Qualifying signals: design doc Extension-L / Custom-XL with high cross-module coupling; a core `create`/`write`/`unlink` override whose correctness spans many dependents (`find_override_point` >=3-entry chain, OR `impact_analysis` shows a wide downstream ripple); a cross-model computed chain plus multi-company logic spanning modules; a migration with >1 viable strategy touching many modules | **opus** |
| 3 | Design doc grades it Standard or Config; OR (single-stack AND <=2 intended files AND ~<=50 LOC AND no method override): one field/attr, boilerplate XML view shell, label/string change, security CSV row | **haiku** |
| 4 | Everything else - and the RIGHT default for large-but-tractable work: a big single-domain node, high LOC or many files, a normal computed/onchange/constraint, a single-method override, a standard OWL widget, a full-stack node, even a large / high-blast-radius node that stays within one business domain - plus ANY genuinely ambiguous case you cannot classify confidently. Size, file count, and blast radius alone never escalate past sonnet; only Row-2 multi-domain + heavy-dependency complexity does | **sonnet** (default) |

Constraints on the table:
- **sonnet is the ambiguous-case default and the home of LARGE work.** If two rows
  seem to apply, the higher row (smaller #) wins; if NO row clearly applies, use
  sonnet. Do NOT escalate to opus for size, file count, or blast radius alone -
  Row 2 requires multi-domain difficulty AND cross-module entanglement together.
- **fable is never a default and ALWAYS needs explicit human confirmation.** It is
  the rare top band, about 2x the price of the tier below it. When any row resolves
  to fable, the gate message must call out the TRADEOFF on its own line, in plain
  words and never by tier name - which node, why it needs the deepest reasoning,
  and the cost (e.g. `<n2> changes an inheritance axis across several modules: run
  it on the deepest-reasoning setting? Costs about 2x. (approve / skip / cancel)`).
  On `approve` it fires; on `skip`, downgrade that row to **opus** before dispatch and record the downgrade
  in plan.md (`<n2>: opus (fable declined)`). If the work is fable-grade but NO
  approved design doc exists, recommend `SUGGESTED_NEXT: odoo-solution-design`
  first (Custom-XL work is design-first).
- **Suppressed-gate auto-downgrade (no human is available to confirm).** When the Phase-0 gate is
  suppressed (an active `run-<id>` node, or the `WORKTREE_PATH` node-dispatch path - see Phase 0
  above), no inline human confirmation is possible: if step 5 resolves a node to **fable**,
  AUTO-DOWNGRADE it to **opus** and record `<n>: opus (fable auto-downgraded - gate suppressed)`
  in plan.md, in the same format as the human-declined downgrade above.
- A fullstack node gets ONE tier applied to both legs by default; you MAY set a
  lower `frontendModel` when the design doc splits effort (e.g. opus backend +
  sonnet frontend). Never set the frontend leg HIGHER than the node tier.
- **The human-facing gate shows DEPTH, never the tier name** - same rule as the fable
  trade-off line above, applied to the whole table instead of one row. The user is
  choosing how much reasoning (and cost) each node gets; a vendor tier name does not
  tell them that, a depth word does. Render the tier into the gate's `depth` column
  with this fixed mapping - it is a rendering step, not a second judgment call:

  | Tier (internal) | `depth` shown at the gate |
  |---|---|
  | haiku | `quick` |
  | sonnet | `standard` |
  | opus | `deep` |
  | fable | `deepest` |

- Record the RAW tier in plan.md and the DEPTH word in the gate table - the tier is part
  of the approved plan, not a runtime improvisation, and plan.md is what a later
  review / fix / resume step re-dispatches from.

**6. Coverage pre-flight per node (red before green - authoring is universal).** The test protects
the business behavior and is written BEFORE the code
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`). Test authoring is UNIVERSAL and
context-isolated: the `odoo-coder` coordinator launches the `odoo-test-writer` agent FIRST per WI to
author the RED test, then the coder makes it green - so the test author is never the code author
(independence keeps the test honest). This skill does NOT launch `odoo-test-writer` and does NOT
choose a per-node test mode - it grounds the coverage scope here and forwards it to the
coordinator, which forwards it to `odoo-test-writer`.

**Coverage pre-flight (run before assigning test mode).** For each non-trivial node, query OSM per
module it touches to ground the test scope - only write what is NOT already covered:
- `tests_covering(model='<primary_model>', odoo_version='<version>')` - lists every TestMethod
  already exercising that model; carry this list forward into the `odoo-test-writer` brief so the
  author writes additive tests only, never re-invents existing ones.
- `test_coverage_audit(module='<module>', odoo_version='<version>')` - surfaces fields with zero/partial static-reference coverage (field-level only; does NOT report method gaps and is NOT executed coverage); use this to bound the scope (test only the field gaps).
- `test_base_classes(odoo_version='<version>')` - retrieves the authoritative base class menu
  (TransactionCase, SavepointCase, HttpCase, ...) with the hard rule that **`cr.commit()` is
  FORBIDDEN inside TransactionCase / SavepointCase - isolation is savepoint rollback**. Include
  the matching base class in the `odoo-test-writer` brief so the author never has to guess.

**A node spanning modules - name the cross-module assertions.** When a node's module set has more
than one entry, state in the brief, in one line, which assertions (if any) exercise behaviour
contributed by a LATER module in the node's dependency order (or by a module with no dependency
edge to the asserting one): `odoo-coder` stages those into the post-install phase
(`agents/odoo-coder.md` § Cross-module test staging) instead of the default at-install phase,
where they would run before that module exists.

Skip the coverage pre-flight only when OSM is unreachable (standalone/disk fallback, same flag
as step 4); in that case `odoo-test-writer` works from disk context alone.

**A node whose change cannot go red at all.** Some in-scope work has no RED test by nature - a
comment-only edit, a rename confined to prose, pure formatting, a docs file, a translation-text
change. That node still gets a coder; what it does not get is a test it cannot have. DECLARE the
exemption in its brief (`TEST_EXEMPTION`, below) naming the category and what specifically is
untestable, and skip the coverage pre-flight for it. Silence is not a declaration: a brief that
simply omits the field means test-first, and the coder will refuse a behavior change with no test
exactly as before. Contract: `${CLAUDE_PLUGIN_ROOT}/snippets/test-exemption-contract.md`.

Carry the coverage pre-flight results (`EXISTING COVERAGE` / `COVERAGE GAPS` / `BASE CLASS`) into
the coder brief so the coordinator seeds the `odoo-test-writer` brief with them (additive tests
only, never a duplicate). There is no per-node `test-author` vs `self` choice anymore - every
node's RED test is authored by the `odoo-test-writer` agent the coordinator launches first.

Then emit the gate and wait. Write the gate message in the USER'S language (translate
labels and prose; keep module names, paths, and the reply keywords verbatim - SSOT:
`${CLAUDE_PLUGIN_ROOT}/snippets/language-mirroring.md`), and when the user is not
working in English pass `userLanguage` in the coder brief so the coder agents
return their summaries pre-mirrored:

```
Proposed: <one-line summary of the change>.
Plan:
  | node | modules              | stack     | depth    | test        | files (intended) |
  | n1   | <m1>                 | backend   | quick    | test-writer | <m1>/models/*.py, <m1>/<descriptor> |
  | n2   | <m2>                 | fullstack | deep     | test-writer | <m2>/models/*.py, <m2>/static/src/*.js, <m2>/<descriptor> |
  | n3   | <m3> (after n1)      | frontend  | standard | test-writer | <m3>/static/src/*.js |
depth = how much reasoning each node gets, and what it costs: quick (cheapest, mechanical
     edits) < standard (the default) < deep (costlier - multi-domain, many dependents) <
     deepest (rare, ~2x deep, and always asked separately). Reply `refine:` to change one.
Design: <DESIGN_DOC child path | none> [Master: <MASTER_DESIGN_DOC path | none>]
OSM: backed | standalone   (OSM = Odoo Semantic, the indexed Odoo source. backed = every Odoo
     fact was checked against it; standalone = it is unreachable, so this runs on the local files
     plus model knowledge)
Dispatch: nodes run in model-weighted batches, in `depends_on` order
Proceed? (approve / refine: [feedback] / cancel)
```

`depth` applies to the WHOLE node - a node whose modules would earn different depths pays the
highest one for all of them. If those modules CAN land separately, they should have been separate
nodes (same-landing-moment rule, step 2 above); say so with `refine:` rather than accepting the
inflation silently. The `(after <node-id>)` annotation in the `node` cell is the ONLY ordering
statement - there is no grouping column: dependency order is enforced per-node during execution.

On `approve`, execute; on `refine: …`, update and re-emit; on `cancel`, stop.

## Execution - dispatch ONE odoo-coder per work node (model-weighted batches)

The coder agents run as autonomous agents - never inline codegen in main, never via the Skill tool.

> Launch **ONE `odoo-coder` COORDINATOR PER NODE** - whatever the node's stack tag, whether it
> touches one module, part of one module, or several modules. Never split a node into per-module
> dispatches, and never merge two nodes into one dispatch. The node is the unit the plan approved,
> the unit the coordinator commits, and the unit `run-harness` cherry-picks; changing it here
> would desynchronise all three.

| Situation | Nodes | Dispatches |
|---|---|---|
| Driven by `run-harness` | the plan's coding nodes | `odoo-coding` is invoked once per node and dispatches exactly ONE `odoo-coder` |
| Standalone (no plan) | `odoo-coding` derives its own node set in Phase 0 by the schema's two rules (disjoint file scopes; same-landing-moment closure) | one per derived node, packed into model-weighted batches |

Launch the agent by TYPE; if a short type fails to resolve, retry with the plugin-qualified form
`odoo-ai-agents:odoo-coder`. It coordinates the node end to end: it splits the node into 1..N
INTERNAL WIs by disjoint file sets, schedules independent WIs in parallel and dependent ones
sequentially (backend before a frontend that binds it), launches `odoo-backend-coder` for each
backend WI and `odoo-frontend-coder` for each frontend WI, owns the integrated whole-node test on
ONE instance + the bounded fix loop, and RETURNS the aggregated file list to this skill. You do NOT
launch the worker agents yourself and you do NOT decide the WI split - the coordinator does. The
stack tag is passed to the coordinator as a hint; a single-stack node simply yields one-or-more
same-stack WIs.

Do NOT build a Claude Code Workflow (JS) script for this - all fan-out is real agent launches;
narrating a dispatch in prose instead of launching the agent is not allowed.

Concurrency/OOM rule (SSOT: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`, Mode B):
model-weighted budget - WEIGHT haiku=1, sonnet=2, opus=4, fable=8; at most 8 weight-units in flight
at once (keeps opus <=2 and fable exclusive while haiku/sonnet flow freely). The batching loop
below keeps its shape and this weight budget; only the packed unit changes from module to node.

Instance-allocation rule (SSOT: same `concurrency-guard.md` § Odoo instance allocation): a coder
that runs `odoo-bin` against a database (tests via `--test-enable`, `-i`/`-u`, or scaffolding into a
DB) and was handed NO `INSTANCE_HANDLE` self-provisions an ISOLATED instance by invoking
`Skill(odoo-instance)` (a unique ephemeral DB acquired UNDER the HARD RULES), never a bare
`scripts/lib/allocator.py` call that would bypass them - so the brief never passes a shared
db/port. `odoo-test-writer` NEVER self-provisions: when confirming RED needs a live run, it relays
`NEEDS_NEXT: odoo-instance` up to its launcher (`odoo-coder`), which provisions the instance and
re-launches it (`agents/odoo-coder.md` § NEEDS_NEXT: odoo-instance). A provided handle always wins
(consume, never re-provision) - unless the brief carries `SELF_PROVISION: worktree-addons`
(`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons carve-out).

**Dispatcher-level invariant.** A node's coding run is not DONE until every instance its
`odoo-coder` coordinator self-provisioned this run is released by that coordinator - whether it
self-provisioned because no handle was forwarded OR because you authorized
`SELF_PROVISION: worktree-addons`. A returned node SHA with a still-leased self-provisioned
instance is not a clean handoff. Under the worktree-addons carve-out this is ONE lease per node, so
the release is per-node and non-negotiable. Full rule:
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T0/T1/T3.

### Dispatch loop - model-weighted batches

The Phase 0 plan carries, per node: id, its module set (name + path on disk, in dependency order),
stack, model (and `frontendModel` when split), the `depends_on` edges (the "(after ...)" in the
gate table), which of its modules are new, the coverage pre-flight (universal test-first via
`odoo-test-writer`), and the node's request (+ a frontendRequest for the UI leg). The run's ONE
concrete Odoo series is the value Phase 0 step 4 already resolved (via
`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`) - forward it verbatim; never
re-resolve it here and never substitute a default. Carry the design-doc path, the runSlug
(scopes the shared worklog dir) and - when the user is not working in English - the userLanguage.

0. Resume registry (once per run). You may RESUME a coordinator you launched earlier in THIS run
   instead of cold-spawning it again: capture the id your own launch call returns and record it per
   node in plan.md. That id is the only address you will ever hold for it, and it holds none for
   you. No id recorded (first dispatch, fresh run) -> cold-spawn; always correct. Semantics:
   `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` Tier A.

**Caller-supplied cross-invocation resume id (`WORKER_AGENT_ID`).** When a node's brief carries
`WORKER_AGENT_ID: <id>`, that id was captured by the CALLER from ITS OWN earlier launch of this
node's coordinator in a PRIOR `odoo-coding` invocation (e.g. a forward-port run re-invoking this
skill for a LATER commit touching the same node) - never a string anyone invented. Resume that id
in step 3 below when it still resolves; cold-spawn otherwise. Record it (and the id your own launch
returns) in THIS run's plan.md. Absent `WORKER_AGENT_ID` (today's default) -> cold-spawn.

**Distinguishing predicate (this resume vs step 4's resume - never conflate the two).**
Apply step 4's resume ONLY to a BLOCKED node THIS SAME `odoo-coding` invocation itself
dispatched and recorded in ITS OWN plan.md earlier in this same run; apply this `WORKER_AGENT_ID`
resume whenever the coordinator to reach was launched by a DIFFERENT, already-ended `odoo-coding`
invocation that this run holds no record of - the caller's brief, not this run's own plan.md, is
what carries that id across the invocation boundary.

1. Order nodes so every node appears after its `depends_on` set (the annotation in the gate
   table's `node` cell already encodes this).
2. Greedily pack the next batch: take nodes in order whose dependencies are all done (done = the
   dependency node's `odoo-coder` coordinator reported all its WIs green + the integrated
   whole-node test passed) and whose summed WEIGHT stays <= 8. A
   fable item always forms a batch of ONE.
3. Fire the whole batch as parallel agent launches in a SINGLE message, ONE `odoo-coder` coordinator
   per node (the coordinator internally splits the node into WIs, sequences backend-before-frontend,
   and runs the integrated test - you do not fire the worker agents or decide the WI split yourself).
   Record the id each launch returns in plan.md as you go. A node whose brief carries
   `WORKER_AGENT_ID` resumes that id when it still resolves and cold-spawns otherwise - it still
   counts as this batch's ONE coordinator for that node either way.
4. Wait for the batch (a batch barrier each round): after firing the parallel `odoo-coder` launches
   in step 3, hold until every coordinator in the batch has returned one of the four terminal
   Continuation Contract statuses - `DONE`, `BLOCKED`, `NEEDS_NEXT`, or `NEEDS_CONTEXT` - before
   packing the next batch; mark each coordinator's task-list item terminal the instant it returns
   any of the four. The barrier is mechanical per
   `${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R1 (the release-vocabulary SSOT -
   do not gate this on a task-list tool's own native label, which is runtime-dependent and may not
   even expose a dedicated `blocked` state), not an assumption. A batch is done only when every
   coordinator returned a terminal status, rolling up `NEEDS_NEXT`/`NEEDS_CONTEXT` exactly as a
   `BLOCKED` per R2. A later step re-dispatches a `BLOCKED`/`NEEDS_CONTEXT` node at the SAME
   recorded tier: resume the recorded id when it still resolves; otherwise (Tier C fallback) make a
   fresh launch. The worklog stays the
   always-correct context layer the re-dispatched worker reads.
   **A coordinator dispatch that resolves WITHOUT a parseable Continuation Contract - a
   harness-level dispatch error, an empty/content-less return, or output that does not parse to any
   of the four terminal `status` values - is NEVER a silent success and is NEVER left pending on the
   batch barrier as if it were still running.** Treat it as a distinct, immediate signal from a real
   `BLOCKED`: flip that node's module ledger entries (if any exist - a NEW in-scope module per
   § Dependency-BLOCKED handling below) straight from `building` to `failed`
   (`${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md` § building -> failed
   (dead-dispatch)) rather than let a stale-but-recent `heartbeat_at` keep advertising the module as
   alive to other runs, and treat the node itself as `BLOCKED: dead coordinator dispatch (no
   completion report)` in THIS run's own accounting - roll it into the batch's normal BLOCKED
   handling, but record the distinguishing reason in the worklog so a human does not mistake it for
   a graceful business BLOCKED the coordinator itself chose. Fail CLOSED on any doubt whether a
   return is a real report; never mark a node `failed` on a mere suspicion when a valid
   Continuation Contract WAS returned.
5. Each subagent launch sets BOTH the `model` parameter AND the first prompt line
   `DISPATCH MODEL: <haiku|sonnet|opus|fable>` (belt and braces, mirroring `odoo-debug`).
6. fable -> opus downgrade: if a fable dispatch fails (insufficient usage credit, model unavailable,
   subagent error), retry that node ONCE at `model: opus` and record the downgrade in plan.md
   (`opus (fable unavailable)`).
7. Test-first (red before green): pass each node's coverage pre-flight results (including which
   assertions cross a module boundary, step 6) to its `odoo-coder` coordinator. The coordinator
   owns the per-WI test-first for EVERY node: it launches the `odoo-test-writer` agent FIRST per WI
   (the dedicated context-isolated test author - never the code author, independence keeps the test
   honest) and hands the returned RED test paths to that WI's coder, which implements to green.
   THIS skill does NOT launch `odoo-test-writer`; the coordinator does, and it is the ONLY test
   author. The sole exception is a node you DECLARED `TEST_EXEMPTION` for (step 6) - there the
   coordinator skips the test-writer for the exempt WI and the coder works under the declaration,
   refusing the moment the work turns behavioral.

### Dependency-BLOCKED handling + the module-coordination ledger

THIS skill (not the leaf coder) owns cross-module coordination for NEW modules - it alone holds the
batch map, the DONE barrier, and (now) the coordination ledger. Full contract:
`${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md` (do NOT restate it here).

**Write the ledger (only this skill writes it).** Resolve `LEDGER_ROOT` once per run per
`${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md` (`LEDGER_ROOT` = `<SHARE_DIR>/coordination/modules`,
`SHARE_DIR` via `resolve_project_dir.sh share` - shared across every linked worktree and concurrent
run; do NOT restate the resolution recipe here).

**The claim key stays the module technical name; the claimant is the node.** A node id is
run-local, so a node-keyed ledger could never fire cross-run. For each NEW in-scope module (a
module resolving to neither OSM nor disk per
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md`) named in a node's module set, before
dispatching that node's coder, claim EVERY new module the node touches, in ASCENDING
TECHNICAL-NAME order (never dependency order - locking needs a TOTAL order independent of the
plan; dependency order leaves independent modules unordered and would let two runs deadlock):

- CLAIM it with the atomic `mkdir "$LEDGER_ROOT/$MODULE"` (winner writes `entry.json` status
  `claimed`; a loser reads the existing entry and classifies via the decision table below);
- flip `claimed` -> `building` when the node's coder is dispatched, -> `done` on the module's DONE, ->
  `failed` on a terminal BLOCK;
- refresh `heartbeat_at` on EVERY dispatch-loop tick for each module this run is currently building.

**On EEXIST, do NOT release - keep every claim this node already won and re-queue the WHOLE NODE**
behind the existing bounded barrier (below); a multi-module node multiplies the number of ledger
entries that must go stale on a crash, so the staleness window is wider than a single-module
claim's - say so in the worklog rather than treating it as instant.

The hard-leaf `odoo-backend-coder`/`odoo-frontend-coder` workers stay ledger-unaware; only the
`odoo-backend-coder` runs the dependency pre-flight and returns the RAW status below (the node's
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
barriers, for the concurrent build to land, and on exhaustion returns a normal clean case-6 BLOCKED
for the whole node - its caller (`run-harness`) never re-implements a barrier wait. Honesty
invariant: a run that never wrote the ledger, or a dead/stale run, lands in case 6 as a clean
BLOCKED, never a false "in progress"; absence is always the honest fallback.

### Per-node briefs

Each agent launch carries the brief below as its `prompt`. The brief is **run-specific inputs
only**: every procedure (OSM grounding, coding guidelines, worklog read/append, ORM + static gates,
demo data, output format, test-first) already lives in the launched agent's system prompt, so do NOT
re-teach it here - a re-taught copy duplicates the SSOT and drifts. Keep identifiers verbatim. The
brief goes to the `odoo-coder` COORDINATOR for EVERY node; the coordinator forwards the
module-scoped fields to whichever worker(s) each of its INTERNAL WIs needs (`odoo-backend-coder` for a
backend WI, `odoo-frontend-coder` for a frontend WI - it adds `frontendRequest` for a frontend WI).

**Dispatch-brief skeleton.** Fill the prompt below from the caller-side skeleton in
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` (read it by path) plus the Coder family delta;
never inline that file verbatim into a hard-leaf brief.

Coder brief (target = the `odoo-coder` coordinator for the node):

```
DISPATCH MODEL: <tier>
NODE: <node-id> - the plan node this dispatch fulfills (or a self-derived node id when standalone).
WORKER_AGENT_ID: <id> - OPTIONAL. An id the CALLER captured from ITS OWN earlier launch of this node's coordinator in a PRIOR `odoo-coding` invocation (e.g. a forward-port run walking later commits that touch the same node) - never a string anyone invented. Present -> resume that id in step 0/3 below instead of cold-spawning. Absent (today's default) -> cold-spawn.
REQUEST: <the change for this node: target model(s) + constraints (+ frontendRequest for a frontend WI)>
STACK: <backend | frontend | fullstack - hint for the coordinator's WI split; it decides the actual 1..N WIs>
MODULES: <m1>, <m2>, ... @ <path per module>, IN DEPENDENCY ORDER - write ONLY within this module set (+ each module's descriptor / static assets). Resolve each descriptor filename ONCE from disk (`__manifest__.py`, or `__openerp__.py` on v8-v9) and Edit the one the module has; creating the other name beside it makes Odoo load the new file and drop everything the real descriptor declared.
WORKTREE_PATH: <absolute worktree path> - ALWAYS set (odoo-coding self-provisions one before dispatch when the caller handed in none - S9, never the principal checkout): `cd` here and write ALL your work in this ONE worktree for the WHOLE node; your hard-leaf coders RETURN their file lists (no git), then YOU (the coordinator) COMMIT the node via `git-toolkit:git-ops` once the integrated test is green and RETURN the SHA - `odoo-coding` collects it and `run-harness` cherry-picks it into the run-integration branch. A missing value here is a load-bearing gap, never `current checkout` - surface it (Brief self-check) rather than defaulting to it.
SHARE_DIR: <absolute path> - the run's SHARE dir. Forward the literal your own caller handed you; only when it handed none, capture it ONCE per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` § The resolve-capture-substitute protocol, BEFORE any `cd` into a worktree. Never let a leaf re-resolve.
ISOLATE_DIR: <absolute path> - same rule, and load-bearing: `<ISOLATE_DIR>` keys on the enclosing repository root, so a coordinator or leaf that resolves it after `cd`-ing into WORKTREE_PATH writes the run's worklog into that worktree's OWN tree, orphaned from every sibling (`state-root-resolution.md` § Cross-worktree dispatch). ONE literal, resolved once, forwarded to every node.
NEW MODULE: <per module: yes - ALWAYS scaffold with `odoo-bin scaffold` first; edit only needed keys and KEEP scaffold's commented placeholders; keep its short version default, do NOT rewrite to `<series>.x.y.z` | no>
ODOO VERSION: <version>
INSTANCE_HANDLE: <the run's provisioned instance handle from a prior odoo-instance step, when present - db_name/http_port/db_port/addons_path/venv_python/lease_token/run_id (full field list: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`); omit when the run provisioned none>
SELF_PROVISION: worktree-addons | none - set `worktree-addons` for EVERY per-node dispatch that names a WORKTREE_PATH (then OMIT INSTANCE_HANDLE above; never send both); `none` only when the forwarded handle's ADDONS_PATH already covers this node's worktree
ADDONS_PATH: <comma-joined dirs the forwarded instance loads - REQUIRED whenever INSTANCE_HANDLE is set; omit when SELF_PROVISION: worktree-addons>
DESIGN_DOC: <child TDD path | none> - per-node spec; if present, build to it; do not re-derive.
MASTER_DESIGN_DOC: <master TDD path | none> - hard constraints (ownership, dep-direction, §10 contracts); `none` in single mode.
SURVEY: <deep-survey synthesis.md path | none> - additional hotspot/impact grounding from an
  opted-in deep survey (`inputs.survey` on the run-dag node, `phase-p-run-dag.md` § Survey
  pointer); read it once for grounding before authoring if present. ALWAYS state a value - `none`
  when no deep survey ran this session, never omit the field.
TEST: test-first (universal) - launch `odoo-test-writer` FIRST per WI to author the RED test, then the coder implements to green; the coders do NOT author tests. Forward the coverage pre-flight below to `odoo-test-writer`, INCLUDING which assertions (if any) cross a module boundary within this node (§ Cross-module test staging in `agents/odoo-coder.md`).
TEST_EXEMPTION: none | <category> - <specifics> - `none` unless THIS node's change cannot go red at all (comment-only, prose-rename, formatting, docs, translation-text); a declared exemption names the category AND what specifically is untestable. Never declare one to move a stuck node along: a behavior change with no test stays refused. Contract: `${CLAUDE_PLUGIN_ROOT}/snippets/test-exemption-contract.md`.
EXISTING COVERAGE: <tests_covering(model='<primary_model>', odoo_version='<version>') output - TestMethods already covering this model; author ADDITIVE tests only>
COVERAGE GAPS: <test_coverage_audit(module='<module>', odoo_version='<version>') output per module in this node - fields with zero/partial static-reference coverage (field-level only); prioritise these gaps>
BASE CLASS: <base class from test_base_classes(odoo_version='<version>'), e.g. TransactionCase - cr.commit() FORBIDDEN, isolation is savepoint rollback>
WORKLOG: <runSlug> - read it, then append your significant decisions.
USER LANGUAGE: <lang | omit when the user works in English> - write the summary in this language; keep identifiers verbatim.
Follow the Rounds in your system prompt - it owns every procedure; do not re-derive what it already specifies.
GUIDELINES: Round 1 owns this - open `${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/<version>/INDEX.md` first, consult the "By task" table, read ONLY the mapped files (not the whole directory).
```

- **Addons provenance is the DISPATCHER's job.** Each node gets ONE worktree and ONE `addons_path`
  covering its whole module set, so one lease is exactly right for one node. For every per-node
  dispatch that names a `WORKTREE_PATH`, set `SELF_PROVISION: worktree-addons` and omit
  `INSTANCE_HANDLE`; the coordinator then provisions its own ephemeral instance via
  `Skill(odoo-instance)` (inline) with the worktree re-rooted onto the node's addons list (every
  module the node touches, in dependency order), and releases it before reporting. When you DO
  forward a handle, also state its `ADDONS_PATH` so the receiver can run the coverage assertion. A
  receiver that holds a handle MUST use it and MUST NOT invent a `db_name` or port; it MUST NOT
  re-derive `addons_path` from the catalog; and it self-provisions ONLY under the authorizing
  token. Neither hard-leaf worker self-provisions an instance: both `odoo-backend-coder` and
  `odoo-frontend-coder` are INSTANCE-FREE (the lint-class gate runs at `run-harness`'s pre-PR tail
  instead - `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/run-integration.md` § Pre-PR
  tail) - the coordinator's OWN integrated-node-test self-provision (below) is the only per-node
  instance acquire left. Contract: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`
  (§ Worktree-addons carve-out, § Addons coverage assertion).
- To run `odoo-bin` (scaffold, or tests via `--test-enable`), resolve the interpreter per
  `snippets/venv-resolution.md` - never assume system `python3`.
- Frontend WI only: ground styling tokens against `skills/_shared/odoo-frontend-fidelity.md`
  (no hardcoded hex for themeable colors, no self-referential `--bs-*` shim) - the full method lives
  in the agent's system prompt.

The `odoo-coder` coordinator (not this skill) launches the `odoo-test-writer` agent per WI FIRST -
its authoring brief (MODE, MODULE SCOPE, TARGET BEHAVIOR, TEST TYPE(S), plus the coverage pre-flight
fields above) is the coordinator's to assemble; this skill never pre-dispatches a test author and
the coders never author tests. That FIRST launch is skipped only for a WI covered by a declared
`TEST_EXEMPTION` - never because a test looked hard to write. `odoo-test-writer` follows `snippets/test-first-contract.md`
(red-before-green) and `snippets/test-behavior-contract.md` (drive the real workflow -
action_confirm/action_validate/button_validate, Form() for onchange, with_user() not sudo(); never
seed the terminal state with create({state:...})): assert observable behavior not internals; ONE
intent per test; confirm each goes RED.

Each hard-leaf coder locates files via Read/Grep, writes its output, and reports the files written
plus `__manifest__.py` changes - it does NOT run git. The node's `odoo-coder` coordinator
aggregates ALL its WIs' workers' file lists and, once the integrated node test is green, **COMMITS
the node itself by invoking the `git-toolkit:git-ops` skill** inside the worktree (it requests the
commit; git-ops owns the message convention + DCO + mechanics) and captures the ONE commit SHA on
the node's branch. **THIS skill then COLLECTS the coordinator's returned SHA and passes it up so
`run-harness` can cherry-pick it into the run-integration branch (or so any caller can integrate) -
it does NOT re-commit; a DONE with no returned file list, no integrated-test verdict, no SHA from
the coordinator, no stated WI count + terminal-status accounting for that node (D2 - the private WI
list is the coordinator's, but the ACCOUNTING statement is not), or no explicit mapping of every
item in that node's `REQUEST`/`frontendRequest` to the WI(s) that implemented it (D7 - a node that
silently covers only PART of what was asked is not a green node even when every file it DID touch
is real and tested) is a failed contract.** The coordinator commits in its dependency-correct
worktree (forked from the run's ONE run-integration branch), so git-ops fires from the coordinator,
not this skill. `odoo-coding` NEVER completes with uncommitted output: if it was dispatched WITHOUT
a `WORKTREE_PATH`, it self-provisions a worktree/branch via `git-toolkit:git-ops` (never the
principal checkout, S9) and hands it to the coordinator to commit in - a FALLBACK only, NOT
membership in `git-delegation.md` § Self-provisioning specialists; an orchestrator dispatching
`odoo-coding` SHOULD still provision the worktree first per `run-harness` Hard rule 6.

## Artifacts - persist the coding plan

Write the orchestration plan to `<ISOLATE_DIR>/coding/<slug>-<YYYY-MM-DD>/plan.md` (the whole
`$ODOO_AI_HOME` state root lives outside any git working tree, so this needs no gitignore entry -
it is live run state, not source): the node/modules/stack table carrying the **raw model tier**
(plan.md is agent state, so it records the tier itself, not the gate's depth word), the
`depends_on` edges between nodes, and the design doc referenced. The agents write source directly;
`plan.md` records what was built so a later review / fix / resume step can pick up without
recomputing the graph. `<slug>` derives from the change (branch, feature name, or the module set).

plan.md MUST record, per node: its module set, stack, `depends_on`, the model tier chosen
(and frontendModel when split), the dispatch path (subagent launch), the node's
result status, and the `agentId` that node's launch returned - plan.md IS the agentId registry
(`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` Tier A).
A later review / fix / resume step re-dispatches BLOCKED nodes at the SAME recorded tier
(unless the human changes it) via the Tier-A/Tier-C rule in § Dispatch loop step 4.

## Standalone-first fallback

When OSM (the odoo-semantic-mcp server) is unreachable, the dependency graph and stack tags come
from disk - read each module descriptor's `depends` (`__manifest__.py`, or `__openerp__.py` on
v8-v9 - glob BOTH) and scan `static/src` (or the haiku reader
above) - and each agent falls back to its own disk-grounded mode per
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`, still writing files to their correct
locations. Label the plan "graph from disk (OSM unavailable)"; the node partition is unchanged,
only the grounding degrades. Never ask a human to paste code, field lists, or manifests.

## Agent-managed tools

This skill is part of an agent+skill bundle. The codegen detail lives on the agents -
see `agents/odoo-coder.md` (the per-node coordinator - owns the internal WI split + launches THREE
teammates), `agents/odoo-test-writer.md` (the hard-leaf test author launched FIRST per WI - authors
the RED test by invoking the `odoo-test-writing` skill inline), `agents/odoo-backend-coder.md`
(the backend hard-leaf writer + its ORM-validation gate - the lint-class gate moved to
`run-harness`'s pre-PR tail, see `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/run-integration.md`
§ Pre-PR tail), and `agents/odoo-frontend-coder.md` (the frontend hard-leaf writer + its
zero-toolchain static gate) for the execution detail; agents inherit the full tool surface.

## The code -> review+test -> code loop (bounded)

Coding is not one-shot. After this skill writes code (each non-trivial node implemented to a
separately-authored failing test), the **code -> review+test -> code** round-trip runs:
`odoo-code-review` reviews AND checks the tests cover the behavior, looping back on a CRITICAL/HIGH
issue or a red/missing test.

**Drive it yourself in the default case (mandatory).** The Skill tool is available here. After
writing, **IMMEDIATELY invoke `odoo-code-review` via the Skill tool yourself** and fix within the
bounded loop below before returning - UNLESS the plan already places a separate review node on
this node's dependency path, in which case `run-harness` will dispatch that node itself and
driving review here would double-dispatch. The two branches, precisely:

- **Dispatched by `run-harness` as a plan node whose downstream carries its own review node.**
  `run-harness` drives every node through its ONE dispatch loop; when the approved plan already
  wires a review node (`odoo-code-review`) after this coding node, emit `next: odoo-code-review`
  and let `run-harness` schedule it; do not double-dispatch.
- **Every other invocation (default - drive inline).** This is the default, and it explicitly
  INCLUDES direct invocation, intake fast-path, autonomous fix, and a plan-fed standalone
  invocation whose plan carries no separate review node on this node's path. DRIVE
  `odoo-code-review` inline yourself and fix in the bounded loop below before returning.

Emit the Continuation Contract either way.

Bound the loop to **3 iterations** per `${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`; still
not green-and-clean after 3 -> STOP and escalate (bad work is worse than no work). Each iteration's
outcome goes in the worklog.

## Continuation Contract

When the bundle finishes, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Set
`produced` to the source + test files written, plus `<ISOLATE_DIR>/coding/<slug>-<date>/plan.md` and the
`<ISOLATE_DIR>/worklog/<slug>/` entries, and emit `next: odoo-code-review` with `inputs: {odoo_version:
<the run's resolved version>}` (a reserved key - `continuation-contract.md` Rules) so the review
runs against the same pinned version without re-deriving it (that skill now scales to the same
multi-module node). Do NOT also emit a per-node `next: odoo-i18n` suggestion here. i18n reconcile
is a MANDATORY, ONCE-per-run step now owned by `run-harness`'s pre-PR tail
(`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/run-integration.md` § Pre-PR tail), dispatched
over the run-integration branch's AGGREGATE diff after the last verification node closes GREEN -
not a per-node advisory here, which would fire once per node for the same run-level obligation and
add nothing the mandatory tail step does not already cover. `run-harness` always drives an
`odoo-coding` dispatch (Phase P engages the driver on any `writes-files` node -
`docs/reference/workflow-harness.md` §8.3), so this hand-off is complete without a per-node echo
here.
