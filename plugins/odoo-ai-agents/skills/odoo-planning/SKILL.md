---
name: odoo-planning
argument-hint: "[approved design / scope]"
description: >-
  Execution plan for an approved Odoo design: build order, parallel work, landing
user-invocable: true
---

# Odoo Planning - the execution plan between design and code

Planning step only. Output: `<SHARE_DIR>/plans/<slug>-<date>.md` (resolve `<SHARE_DIR>`/`<ISOLATE_DIR>`
via the resolve-capture-substitute protocol in `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`
before the first Read/Write/Edit of a state-root path in this skill) - never production source. You do
NOT compute the plan and do NOT write code: launch `odoo-planner`, then own the plan gate and the
hand-off.

```
gap/brl  ->  odoo-solution-design (TDD + index.yaml)  ->  HUMAN approves SRS and design (text)
   ->  odoo-planning -> odoo-planner (the plan: build nodes + the lifecycle tail)
   ->  EnterPlanMode -> the ONE plan gate -> ExitPlanMode
   ->  intake Phase P serializes run-<id>.json  ->  the main agent runs the plan
   ->  the doc nodes (docs-module, then docs-site) run after code/review/QA when their `when:` holds, ungated
```

## Role

Turn an approved technical design into ONE lifecycle plan (the build nodes and the lifecycle tail,
documentation included) by launching ONE leaf planner, `odoo-planner`. The plan is run by the main
agent per `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Running the plan.
The documentation of the change is the tail nodes `docs-module` then `docs-site`
(`plan-mode-schema.md` § Default tail). The documentation target (`module`, `site`, `both`, `none`)
comes from `odoo-intake` in the brief.

## Input port - read the upstream artifacts BY POINTER (before dispatch)

Locate the upstream artifacts and pass their paths to the planner (never paste their contents,
never re-derive their facts):

- **Design DAG (OPTIONAL - `none` when no design was authored)** -
  `<SHARE_DIR>/designs/<master-slug>/index.yaml` (`dag_layers` + dependency direction) for a
  master-child design, or the single-mode `<SHARE_DIR>/designs/<slug>-<date>.md`. When one exists the
  planner CONSUMES it and never recomputes it. When none exists the plan is derived from the
  development work itself and the field is carried as an explicit `none`.
- **Gap matrix** - `<SHARE_DIR>/gap-analysis/<slug>-<date>/gap-matrix.jsonl` (or a BRL RTM under
  `<SHARE_DIR>/brl/<job-id>/`) for per-requirement effort tier - drives the `effort` estimate.
- **QA oracle (OPTIONAL - usually ABSENT at planning time)** - `<ISOLATE_DIR>/qa/<slug>-scenarios.md`.
  The `acceptance` node is ALWAYS authored statically, never omitted for lack of an oracle. When the
  oracle is absent, the plan sources the node's criteria from the design's §9 Acceptance Criteria;
  when present, the plan wires its review/acceptance stages to it.
- **Survey (OPTIONAL - ALWAYS an explicit value)** - `<SHARE_DIR>/survey/<slug>-<date>/synthesis.md`,
  forwarded in this skill's brief `INPUTS` when intake's hand-off carried a deep-survey synthesis.
  State `none` explicitly to `odoo-planner` when absent, and thread it onward the same way (§ P1).

## Design precedes planning

Planning is MANDATORY for ALL work and is NEVER refused for a missing design
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Mandatory-planning rule). Whatever the
Input port resolved, proceed to § Agent invocation; an unresolved design pointer is carried as `none`
in the P1 brief and the development work itself is what gets planned. Evaluate no design predicate.

A design is only ever an INPUT to a plan, NEVER a node of one: no node's `approach` is
`odoo-solution-design` / `odoo-solution-architect`, and you wire none
(`plan-mode-schema.md` § Design is an INPUT to this plan).

## No scope-preview gate - go straight to the planner

Do NOT ask the human to approve a scope preview before dispatching; the front door (`odoo-intake`)
or the `return_to` caller already settled scope. Ask only the genuine open questions the Input port
could not resolve (an ambiguous module set, an unresolved target series) in ONE short message, then
launch the planner. A missing design is never such a question: carry `DESIGN_INDEX: none`. The single
approval this skill owns is § Plan-approval gate, after the planner returns.

The planner writes ONLY the plan under the `$ODOO_AI_HOME` state root (SHARE tier); no source file is
touched before the plan is approved.

## Agent invocation - prompt template

When composing the dispatch prompt for any specialist agent you dispatch, fill the caller-side
skeleton in `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton (read it by path) plus the target
agent's family delta; never inline that file verbatim into a hard-leaf brief. The brief carries no
reply address: the planner hands its report back once, and you collect it as R0
assigns to the agent-launch tool you hold
(`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R0, R3).

### P1 - The plan (odoo-planner)

Launch `odoo-planner` as a subagent (default: ONE planner). For a very large scope (many
independent module clusters) you MAY fan out one planner per cluster following **Mode B**
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`) and reconcile their plans. Choose the
subagent `model` per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier
selection and pass it explicitly.

```
DISPATCH MODEL: <the tier chosen above>
You are the odoo-planner agent. Produce the 3-block EXECUTION PLAN (NOT code, NOT a design) for:

REQUEST: [the change to ship, target Odoo version, any constraints]
DESIGN_INDEX: [none | <SHARE_DIR>/designs/<master-slug>/index.yaml | the single-mode design doc
path - explicit `none` when no design was authored]
GAP_MATRIX: [omit when absent; else the gap-matrix.jsonl / BRL RTM path]
QA_ORACLE: [omit when absent; else the scenarios.md path]
SURVEY: [none | <SHARE_DIR>/survey/<slug>-<date>/synthesis.md - never omit this field]
DOC TARGET: [module | site | both | none - with the facts that decided it; omit when the caller decided nothing]
RETURN_TO: [omit when absent; set to the caller skill name when return routing is requested]
```

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
> STATIC (no live records). The planner uses OSM lightly: pin the version and verify that the
> modules the design DAG names exist and their dependency edges hold before assigning them to nodes;
> it does NOT re-derive the DAG.

## Agent-managed tools

### Plan Mode guard (enter HERE, after the planner returns, before the approval gate)

This skill owns the request's one Plan-Mode gate
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request). Call
`EnterPlanMode` HERE, after the planner returns and before presenting the plan. When `return_to` is
set, the caller owns the gate: do not enter Plan Mode, present nothing, and hand the plan back
(§ Continuation Contract).

## Plan-approval gate (who approves: the human)

Present the plan, gate on human approval, then `ExitPlanMode`. Do NOT auto-chain to execution. Quote
the plan path the planner RETURNED. Write the gate in the USER'S LANGUAGE (translate labels and
prose; keep file paths, module names, model identifiers, and skill names verbatim):

```
Plan ready:
  Plan:       <SHARE_DIR>/plans/<slug>-<YYYY-MM-DD>.md
Build order: <node-1> -> <node-2> -> ...   (topological order; landing: <one line>)
Lifecycle:   <the tail nodes in order with their when: conditions, as the plan writes them>
             (the doc nodes run AFTER code/review/QA when their `when:` holds, with no gate of their own)
Docs:        <module | site | both | none> - <the facts that decided it>   (reply `refine:` to change it)
Estimates:   effort <S/M/L/XL total> · est_agents <n> (ADVISORY)
Approve plan? (approve / refine: [feedback] / cancel)
```

- `Lifecycle:` renders the plan's own tail nodes - the default tail of `plan-mode-schema.md`
  § Default tail as the planner adapted it, with the reason for any change.
- `Docs:` is the single line that shows the documentation target. `refine: no docs` drops
  `docs-module` and `docs-site`, with the reason written in the plan; `refine: docs module | site |
  both` re-sends the planner the new target.
- **Before approving, confirm the rendered Block 2 ASCII graph honors the no-grouping rule**:
  `nodes` and `edges` are the ONLY ordering statement; no header, tier, or annotation batches nodes
  together. If any does, `refine: [feedback]` rather than approving.
- **Also confirm every node states a business `objective` and business-observable acceptance**
  (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Block 1 and § Block 3).
  A node whose objective or acceptance names a technical end-state (a field, model, file or method
  to exist): `refine: [feedback]`.
- **Also confirm every repo with a coding node carries at least one `odoo-instance` node on
  `integrate`'s `depends_on` path whose `modules` cover every module DECLARED in the `modules` field
  of a coding node in that repo.** Compare the two declared `modules` fields of the plan in front of
  you; never read module source and never infer what a node will "really" touch. A coding node whose
  declared `modules` look wrong, or a missing verification node: `refine: [feedback]` back to the
  planner, never a field to correct at this gate.
- `refine: [feedback]` -> re-dispatch the planner with the feedback; rewrite the same plan file.
- `approve` -> call `ExitPlanMode`, then hand the approved 3-block plan to intake **Phase P**, which
  serializes `<ISOLATE_DIR>/run-<id>.json`; the main agent then runs it per `plan-mode-schema.md`
  § Running the plan. This skill never serializes the run file itself.
- `cancel` -> stop; the plan file remains on disk.

## What the plan binds

Per node: WHO runs it (the agent with its `MODE` and `model`, or the skill or workflow), WHEN
(`depends_on` and `when:`) and WHAT business result it delivers (`objective` and business-observable
acceptance - `plan-mode-schema.md` § Block 1 / § Block 3). HOW the result is built stays with the
design doc and the coder. A build node's `model` is the design's `build_tier_hint` with its
checklist; a tail node's is the default tail's. `effort` and `est_agents` are ADVISORY.

The landing sequence the plan reserves follows `${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`;
each `odoo-instance` node's `modules` field IS its regression scope
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/regression-scope.md`). Planning references both and runs
neither.

## Out of Scope

- **Designing the technical solution** (approach / data model / override strategy / module
  structure) -> `odoo-solution-design`
- **Writing production code** -> `odoo-coding`; multi-node landing is the main agent's run of the approved plan
- **Classifying / costing a requirement list** -> `odoo-gap-analysis` (short) / `odoo-brl` (large)
- **Serializing or running the plan** -> intake Phase P serializes `run-<id>.json`; the main
  agent runs it (`plan-mode-schema.md` § Running the plan).
- **A self-planning orchestrator** (`odoo-forward-port` / `odoo-modules-upgrade` /
  `odoo-git-rebase`) -> route such intent to them; they own their own plan gate
  (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request); do
  not embed them as plan nodes

## Standalone-first fallback

OSM is optional. When it is unreachable, the planner plans on the design artifact + user-provided
context alone and labels the plan `OSM: standalone` (grounding tiers:
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`). The plan never invents a module or
dependency the design did not establish - escalate (`NEEDS_CONTEXT`) only for a sequencing decision
no artifact encodes.

## Continuation Contract

When the bundle finishes, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). The `next`
is gated on the human plan-approval above (or, with `return_to` set, emitted once the plan is
written). Both branches carry a plan pointer:

- **`return_to` SET:** emit `next: <return_to>` with `inputs: {plan: <path>}`; hand control back.
- **`return_to` UNSET (default):** emit `next: odoo-intake` with `inputs: {plan: <path>}` -
  intake's **Phase P** ingests the approved 3-block plan by pointer and serializes it into
  `run-<id>.json`. This skill never runs a node itself.

Never name `odoo-solution-design` as `next`.
