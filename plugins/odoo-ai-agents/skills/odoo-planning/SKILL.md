---
name: odoo-planning
argument-hint: "[approved design / scope]"
description: >-
  Execution plan for an approved Odoo design: build order, parallel work, landing, estimates
user-invocable: true
---

# Odoo Planning - the execution plan between design and code

## Where this sits in the flow (planning follows design, precedes code)

Planning step only. Output: `<SHARE_DIR>/plans/<slug>-<date>.md` (resolve `<SHARE_DIR>`/`<ISOLATE_DIR>`
via the resolve-capture-substitute protocol in `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`
before the first Read/Write/Edit of a state-root path in this skill; gitignored, L1) - never production
source. Correct order:

```
gap/brl  ->  odoo-solution-design (TDD + index.yaml)  ->  HUMAN approves design
   ->  odoo-planning -> odoo-planner (the plan: build nodes + the lifecycle tail)
   ->  ONE lifecycle plan gate  ->  ExitPlanMode
   ->  intake Phase P serializes run-<id>.json  ->  the main agent runs the plan
   ->  the doc node (odoo-doc-writer) runs after code/review/QA when its `when:` holds
```

This skill does NOT compute the plan itself and does NOT write code - it launches `odoo-planner`
and owns the approve / ExitPlanMode handoff. `odoo-solution-design` decides HOW to build;
`odoo-planning` decides HOW TO SHIP (node build order, landing sequence, full lifecycle).

## Role

Odoo delivery planner. Turns an approved technical design into ONE lifecycle plan covering the
full product journey - the build nodes and the lifecycle tail, documentation included. Launches
ONE leaf planner, `odoo-planner`: a dependency-ordered node graph, each node naming the agent,
mode and model it launches, run end to end by the main agent per
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Running the plan. The
documentation of the change is a node
of that tail (`odoo-doc-writer`, one per module, after acceptance - screenshots need the built
module on a live instance); when it covers several modules, the main agent computes their
instance plan inline at that node per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/doc-cluster-plan.md`.
Pairs with `odoo-solution-design` (consumes its design DAG) and intake Phase P (serializes it).

## Input port - read the upstream artifacts BY POINTER (before dispatch)

The plan is GROUNDED on three upstream artifacts; locate them and pass their paths to the planner
(do NOT paste their contents, do NOT re-derive their facts):

- **Design DAG (OPTIONAL at every complexity level - `none` when no design was authored)** -
  `<SHARE_DIR>/designs/<master-slug>/index.yaml` (`dag_layers` + dependency direction) for a
  master-child design, or the single-mode `<SHARE_DIR>/designs/<slug>-<date>.md`. When one EXISTS it
  is the logical truth the plan turns into dependency-ordered nodes; the planner CONSUMES it, never
  recomputes it. When none exists the plan is derived from the development work itself and the field
  is carried as an explicit `none` (§ Design precedes planning below) - it is never a gate.
- **Gap matrix** - `<SHARE_DIR>/gap-analysis/<slug>-<date>/gap-matrix.jsonl` (or a BRL RTM under
  `<SHARE_DIR>/brl/<job-id>/`) for per-requirement effort tier - drives the `effort` estimate.
- **QA oracle (OPTIONAL - usually ABSENT at planning time)** - `<ISOLATE_DIR>/qa/<slug>-scenarios.md`
  (the immutable acceptance oracle authored by `odoo-qa-planner`). The oracle is normally authored
  LATER, at `odoo-acceptance` Phase 1, after coding - do NOT treat it as a standard planning input.
  The `acceptance` node is authored STATICALLY regardless, like every other terminal stage - it is
  NEVER omitted for lack of an oracle. When the oracle is absent (the common case), the plan sources
  the `acceptance` node's criteria from the design's §9 Acceptance Criteria (already authored at
  design time) instead; when present, the plan wires its review/acceptance stages to it directly.
- **Survey (OPTIONAL - ALWAYS an explicit value, never a silently-missing field)** -
  `<SHARE_DIR>/survey/<slug>-<date>/synthesis.md`, forwarded in this skill's own dispatch brief
  `INPUTS` when intake's Proposed Plan `Survey:` field resolved a deep-survey synthesis this
  session. Additional
  hotspot/impact grounding for node authoring and effort estimates - never a required gate. State
  `none` explicitly to `odoo-planner` when absent rather than omitting the field, and thread it
  onward the same way (§ P1 below); the mandatory-recon analog is `odoo-intake`'s Phase P
  `inputs.recon_findings`, which this deliberately does NOT copy verbatim (it is safe to OMIT when
  absent since recon is cheap/mandatory-tier - Survey is opt-in/expensive, so its absence must be
  stated, not dropped).

## Design precedes planning (a DECLARATION of ORDER - never a refusal; ENFORCED elsewhere)

**Planning is MANDATORY for ALL work, and is NEVER refused for a missing design**
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Mandatory-planning rule). A design is
OPTIONAL at EVERY complexity level - non-trivial included - and is never a precondition to planning.
Whatever the Input port resolved, proceed to § Agent invocation: an unresolved DESIGN DAG pointer is
carried as `none` in the P1 brief and the development work itself is what gets planned. This skill
evaluates NO design predicate and owns NO refusal branch.

**The ONE surviving rule is directional: a design may never be produced AFTER this plan.** The plan
is DERIVED from the design, so a design authored afterwards either invalidates the ordering the human
just approved or gets reverse-engineered to justify it. The load-bearing form of that rule: a design
is only ever an INPUT to a plan, NEVER a node of one.

**This is directional, NOT "design always runs" - and that is now the WHOLE rule, not a caveat to
it.** No design at all is the common case: a one-approach change plans straight through, and so does
a non-trivial change whose design was never authored. Only the ORDER is fixed - a design, IF one
exists, precedes the plan.

This skill DECLARES that order; it ENFORCES nothing. Enforcement lives at the three surfaces where a
design could actually be authored into a plan or dispatched from one - go there to change the rule,
not here:

- **schema** - no node's `approach` may be `odoo-solution-design` / `odoo-solution-architect`,
  authored or materialized at runtime
  (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Design is an INPUT to
  this plan).
- **runner** - the main agent's invariant check returns such a node to this skill as a plan
  error and never launches it (`plan-mode-schema.md` § Running the plan).
- **actor** - the plan author, `odoo-planner`, wires no node it writes to that skill or agent.

## No scope-preview gate - go straight to the planner

Do NOT ask the human to approve a scope preview before dispatching. Whoever sent the work here
already gated that same decision: the front door (`odoo-intake`) approved scope, approach and
expected output with the human before dispatching this skill, and a `return_to` caller classified
scope itself. Asking again is friction, not safety.

Ask only the genuine open questions the Input port could not resolve (an ambiguous module set, an
unresolved target series) - in ONE short message - then launch the planner. **A MISSING design
artifact is NOT one of those questions:** a design is not a precondition to planning at any
complexity level (§ Design precedes planning above), so an absent one is carried as `DESIGN_INDEX:
none` and the plan is authored from the development work itself - never turned into a question, a
block, or a wait. The single
approval checkpoint this skill owns is the § Plan-approval gate below, after the planner returns.
Same shape as the sibling self-driving front doors (`odoo-forward-port` P4, `odoo-git-rebase` P6,
`odoo-modules-upgrade` P3): one plan, one gate.

The planner writes ONLY the plan under the `$ODOO_AI_HOME` state root (SHARE tier - see
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`); no source file is touched before the
plan is approved.

## Agent invocation - prompt template

When composing the dispatch prompt for any specialist agent you dispatch, fill the caller-side
skeleton in `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton (read it by path) plus the target
agent's family delta; never inline that file verbatim into a hard-leaf brief. The brief carries no
reply address: the planner hands its report back once, and you collect it as R0
assigns to the agent-launch tool you hold
(`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R0, R3).

When intent is confirmed, launch the planner. Its output is the one lifecycle plan presented at a
single gate.

### P1 - The plan (odoo-planner)

Launch `odoo-planner` as a subagent (default: ONE planner). For a very large scope (many
independent module clusters) you MAY fan out one planner per cluster following **Mode B**
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`) and reconcile their plans;
the single planner is the default. Choose the subagent `model` per
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection and pass it
explicitly: its opus row ("a long, complex plan" - many interdependent nodes, modules or business
domains) or its sonnet row ("a small plan with a narrow blast radius"). The planner's frontmatter
default is opus.

```
DISPATCH MODEL: <opus | sonnet - the tier chosen above>
You are the odoo-planner agent. Produce the 3-block EXECUTION PLAN (NOT code, NOT a design) for:

REQUEST: [the change to ship, target Odoo version, any constraints]
DESIGN_INDEX: [none | <SHARE_DIR>/designs/<master-slug>/index.yaml | the single-mode design doc
path - explicit `none` when no design was authored, which is legal at any complexity level]
GAP_MATRIX: [omit when absent; else the gap-matrix.jsonl / BRL RTM path]
QA_ORACLE: [omit when absent - the common case at planning time, since the oracle is authored
later at odoo-acceptance Phase 1; else the scenarios.md path]
SURVEY: [none | <SHARE_DIR>/survey/<slug>-<date>/synthesis.md - the deep-survey synthesis from
intake's Proposed Plan `Survey:` field, when one was run this session; explicit `none` when no
deep survey was opted into - never omit this field, unlike GAP_MATRIX/QA_ORACLE above]
RETURN_TO: [omit when absent; set to the caller skill name when return routing is requested]
```

(Method - reading inputs, OSM grounding, schema conformance, node/skill wiring, the estimate-only
constraint, and its own leaf/no-write boundaries - is `odoo-planner`'s own Rounds 0-3;
not restated here.)

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
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
<!-- END GENERATED TOOLS -->

> **OSM-first precedence.** Odoo Semantic MCP (OSM) is the PRIMARY source for Odoo
> source/structure (indexed, cross-version, inheritance-resolved, checkout-free); reading the
> codebase with Read/Grep is the FALLBACK, only when OSM is incomplete or unreachable. OSM is
> STATIC (no live records). Here the planner uses OSM lightly - to pin the version and
> trust-but-verify that the modules the design DAG names exist and their dependency edges hold
> before assigning them to nodes; it does NOT re-derive the DAG (that is the design's job).

## Agent-managed tools

This skill is part of an agent+skill bundle; `odoo-planner` itself owns the read-only execution
detail and output contract.

### Plan Mode guard (enter HERE, after the planner returns, before the approval gate)

Enter Plan Mode HERE, AFTER the planner has returned and BEFORE presenting the "Plan ready"
gate - the planner writes ONLY under the `$ODOO_AI_HOME` state root (SHARE tier), and Plan Mode
gates git-TRACKED writes, not state-root writes (SSOT:
`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Plan-Mode enter/exit, the amended
WHEN clause). This skill runs in the MAIN context, so it CAN call `EnterPlanMode`.

Enter IFF ALL THREE hold: `plan_mode_active` is absent/false AND `return_to` is unset AND the
session is not already in native Plan Mode (Shift+Tab / `/plan`). Skip iff `plan_mode_active:
true` (a caller already holds Plan Mode open across this dispatch for its own reason - never a
pre-open on THIS skill's behalf). When `return_to` is SET (caller-return flow) the caller owns the
gate: do NOT enter here;
hand control back via the Continuation Contract (`next: <return_to>`) without ever opening or
closing Plan Mode.

The enter/skip mechanics + the `plan_mode_active` definition are SSOT at
`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Plan-Mode enter/exit +
plan_mode_active. This guard decides only the ENTER side; the "Plan ready" gate and the
`ExitPlanMode` call on `approve` (§ Plan-approval gate below - including the `return_to`-SET
no-enter branch, unchanged) follow immediately after.

## Plan-approval gate (who approves: the human)

The ENTER already happened above (§ Plan Mode guard, after the planner returned). This section
covers what happens next: present the plan, gate on human approval, then `ExitPlanMode`.

When the planner returns, **do NOT auto-chain to execution.** Present a tight summary, then gate.
Quote the plan path the planner RETURNED. Write the gate in the USER'S LANGUAGE (translate labels
and prose; keep file paths, module names, model identifiers, and skill names verbatim):

```
Plan ready:
  Plan:       <SHARE_DIR>/plans/<slug>-<YYYY-MM-DD>.md
Build order: <node-1> -> <node-2> -> ...   (topological order; landing: <one line>)
Lifecycle:   <the tail nodes in order with their when: conditions, as the plan writes them>
             (the doc node runs AFTER code/review/QA when its `when:` holds)
Estimates:   effort <S/M/L/XL total> · est_agents <n> (ADVISORY - the agent count is an estimate;
             each node's agent, mode and model are what the plan states)
Approve plan? (approve / refine: [feedback] / cancel)
```

- `Lifecycle:` renders the plan's own tail nodes - the default tail of `plan-mode-schema.md`
  § Default tail as the planner adapted it, with the reason for any change.
- **Before approving, confirm the rendered Block 2 ASCII graph honors the schema's no-grouping
  rule**: "`nodes` and `edges` are the ONLY ordering statement a plan makes: no field, header,
  annotation, or grouping construct may batch nodes together." This gate is the one human check that
  no automated guard can reach - if any header, tier, or annotation batches nodes together, reject
  and `refine: [feedback]` rather than approving.
- **Also before approving, confirm every node states a business `objective` and business-observable
  acceptance** (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Block 1
  and § Block 3 own the rule). A node whose objective or acceptance names a technical end-state - a
  field, model, file or method to exist - hands the coder a method instead of a result: reject and
  `refine: [feedback]` rather than approving.
- **Also before approving, confirm every repo the plan touches carries at least one `odoo-instance`
  node on `integrate`'s `depends_on` path whose `modules` cover every module DECLARED in the
  `modules` field of a coding node in that repo.** This is a set comparison between two declared
  `modules` fields of the plan in front of you - never a dependency read of module source, and never
  an inference about what a node will "really" touch. A coding node whose declared `modules` field
  looks wrong is a `refine: [feedback]` back to the planner, never a field to correct at this gate.
  Catching this HERE - not at the runner's invariant check, after every coding node in the
  repo has already run - is the whole point of checking it at this gate: reject and
  `refine: [feedback]` rather than approving a plan missing its verification node.
- `refine: [feedback]` -> re-dispatch the planner with the feedback; rewrite the same plan file.
- `approve` -> two branches:
  - **`return_to` UNSET (default):** the approved plan is the run-DAG. Call `ExitPlanMode`, then
    hand the approved 3-block plan to intake **Phase P**, which serializes `<ISOLATE_DIR>/run-<id>.json`;
    the main agent then runs it per `plan-mode-schema.md` § Running the plan. This skill never
    serializes the run file itself.
  - **`return_to` SET (caller-return flow):** do NOT enter Plan Mode for code and do NOT dispatch
    any executor. Emit the Continuation Contract with `next: <return_to>` and hand control back.
- `cancel` -> stop; the plan file remains on disk.

## What the plan binds

The plan binds, per node, **WHO** runs it (the agent with its `MODE` and `model`, or the skill or
workflow), **WHEN** (`depends_on` and `when:`) and **WHAT business result** it delivers (its
`objective` and business-observable acceptance - schema SSOT
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Block 1 / § Block 3);
HOW the result is built stays with the design doc and the coder. A build node's `model` is the
design's `build_tier_hint` with its checklist; a tail node's is the default tail's. `effort` and
`est_agents` carry the `est_` prefix and the note "ADVISORY", so no runtime agent reads them as a
directive; the in-flight budget stays `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
Mode B at run time.

The landing sequence the plan reserves (per-node cherry-pick onto the ONE run-integration branch per
repo, the saga rollback/resume, then the SINGLE PR opened once every non-land-tail node in that repo
is terminal - NO per-node PR - which the main agent runs) follows the SSOT
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`; planning references it so the plan
reserves that behavior - it does NOT run the loop itself. **The plan carries the verification
nodes**: each `odoo-instance` node's `modules` field IS its regression scope, following the SSOT
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/regression-scope.md`; planning REFERENCES it, it does NOT run
the suite.

## Out of Scope

- **Designing the technical solution** (approach / data model / override strategy / module
  structure) -> `odoo-solution-design` (the design = HOW to build; planning = HOW TO SHIP)
- **Writing production code** -> `odoo-coding` (backend + frontend); multi-node landing is the main agent's run of the approved plan, not a separate skill
- **Classifying / costing a requirement list** -> `odoo-gap-analysis` (short) / `odoo-brl` (large)
- **Serializing or running the plan** -> intake Phase P serializes `run-<id>.json`; the main
  agent runs it (`plan-mode-schema.md` § Running the plan).
- **A heavyweight self-driving orchestrator** (`odoo-forward-port` / `odoo-modules-upgrade` /
  `odoo-git-rebase`) -> these are dispatched-once PEER front doors that own their own gate via the
  shared `${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` Plan-Mode mechanics (their
  specialized plan content stays authored in-skill); route such intent to them, do not embed them
  as plan nodes

## Standalone-first fallback

OSM is optional. When OSM is reachable, the planner pins the version and lightly verifies the
modules named in the design DAG; when unreachable, it plans on the design artifact + user-provided
context alone and labels the plan `OSM: standalone`. Three-tier grounding SSOT:
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`. The plan must never invent a module or
dependency the design did not establish - escalate (`NEEDS_CONTEXT`) only for a sequencing decision
no artifact encodes.

## Continuation Contract

When the bundle finishes, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). The `next`
is **gated on the human plan-approval above**. Both branches carry a plan pointer, because this
skill always authors a plan - there is no design branch and no no-plan branch to check first:

- **`return_to` SET:** emit `next: <return_to>` with `inputs: {plan: <path>}`; hand control back.
- **`return_to` UNSET (default):** emit `next: odoo-intake` with `inputs: {plan: <path>}` -
  intake's **Phase P** ingests the approved 3-block plan by pointer, serializes it into
  `run-<id>.json`, and the main agent then runs it. Serialization is Phase P's job, in one place;
  this skill never runs a node itself.

A design hand-off has no branch here: a plan always exists by the time this contract is emitted, so
naming the design skill as `next` would schedule a design AFTER the plan derived from it - the
inverted order (§ Design precedes planning above). A design gap is a design INPUT that was never
authored, not a follow-up step.

Note: the on-the-fly execution task list is the runner's, NOT this skill's - the main agent
creates and keeps it current per `${CLAUDE_PLUGIN_ROOT}/snippets/execution-tasklist-contract.md`
whenever a task-list tool is available.

Additive output for the Phase P handoff - it does not change anything produced above.
