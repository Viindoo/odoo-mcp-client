---
name: odoo-planning
description: >
  Turn an APPROVED Odoo technical design into the EXECUTION PLAN that ships it - the step between
  solution-design (the design = HOW to build) and code (odoo-coding / odoo-wave). Dispatches the
  odoo-planner agent to produce a gate-able 3-block plan: a wave-batched module-DAG, the
  integration cadence, each module/stage wired to a SKILL, and the full lifecycle
  (code -> review -> doc -> PR -> monitor -> merge). Estimates only (effort + est_agents,
  ADVISORY); the dispatched skill owns the actual model + count at runtime. Fire on:
  "plan the implementation / execution plan", "what order do we build the modules",
  "sequence this rollout". Vietnamese: "lập kế hoạch thực hiện", "thứ tự build module",
  "lên kế hoạch triển khai". Route the technical DESIGN (data model / override strategy) to
  odoo-solution-design; WRITING code to odoo-coding; costing requirements to odoo-gap-analysis.
  DO NOT trigger for pure design (no execution sequencing) or a trivial one-WI change (intake
  writes the inline micro-plan)
user-invocable: true
---

# Odoo Planning - the execution plan between design and code

## Where this sits in the flow (planning follows design, precedes code)

Planning step only. Output: `.odoo-ai/plans/<slug>-<date>.md` (gitignored, L1) - never production
source. Correct order:

```
gap/brl  ->  odoo-solution-design (TDD + index.yaml)  ->  HUMAN approves design
   ->  odoo-planning -> odoo-planner (the 3-block EXECUTION PLAN)  ->  HUMAN approves plan
   ->  ExitPlanMode -> intake Phase P serializes run-<id>.json  ->  run-harness walks it
```

This skill does NOT compute the plan itself and does NOT write code - it dispatches the
`odoo-planner` agent (which authors the plan) and owns the approve / ExitPlanMode handoff for
planning. `odoo-solution-design` decides HOW to build (inheritance axis, data model, override
strategy); `odoo-planning` decides HOW TO SHIP it (module/wave build order, integration cadence,
each stage wired to a skill, the full lifecycle). Two different concerns - never collapse them.

## Persona

Odoo delivery planner. Turns an approved technical design into a runnable, gate-able execution
plan: a wave-batched module-DAG, the integration cadence, and a `module/stage -> SKILL` wiring
spanning the full lifecycle (code -> review -> doc -> PR -> monitor -> merge). Pairs with
`odoo-solution-design` (consumes its design DAG) and `run-harness` (executes the serialized plan).

## Input port - read the upstream artifacts BY POINTER (before dispatch)

The plan is GROUNDED on three upstream artifacts; locate them and pass their paths to the planner
(do NOT paste their contents, do NOT re-derive their facts):

- **Design DAG** - `.odoo-ai/designs/<master-slug>/index.yaml` (`dag_layers` + dependency
  direction) for a master-child design, or the single-mode `.odoo-ai/designs/<slug>-<date>.md`.
  This is the logical truth the plan batches into waves; the planner CONSUMES it, never recomputes
  it.
- **Gap matrix** - `.odoo-ai/gap-analysis/<slug>-<date>/gap-matrix.jsonl` (or a BRL RTM under
  `.odoo-ai/brl/<job-id>/`) for per-requirement effort tier - drives the `effort` estimate.
- **QA oracle** - `.odoo-ai/qa/<slug>-scenarios.md` (the immutable acceptance oracle authored by
  `odoo-qa-planner`), when present - the plan wires its review/acceptance stages to it.

If a design artifact is absent and the change is non-trivial, recommend running
`odoo-solution-design` first rather than planning an ungrounded build order.

## Phase 0 - Plan intent gate (1-turn gate)

**Exception: when `return_to` is set**, SKIP this Phase 0 gate (the caller already classified
scope). Go straight to the planner dispatch, then the single plan-approval gate after it returns.

**Default:** before dispatching, emit a concise **plan scope preview**, then **stop** for
confirmation:

```
Plan scope:   <one-line of the change to be planned>
Will decide:  wave-batched module-DAG (build/integration order) · integration cadence ·
              module/stage -> skill wiring · full lifecycle (code -> review -> doc -> PR ->
              monitor -> merge) · effort + est_agents ESTIMATES (ADVISORY, non-binding)
Inputs:       design <path> · gap-matrix <path|none> · qa oracle <path|none>
Artifact:     .odoo-ai/plans/<slug>-<date>.md (3-block plan; no run-<id>.json - that is intake Phase P)
OSM:          backed | standalone
Proceed? (yes / refine: [feedback] / cancel)
```

Wait for the reply before proceeding. This is a preview, not a write-block - on confirmation the
planner writes ONLY the plan under `.odoo-ai/`.

## Agent invocation - prompt template (P1)

When intent is confirmed, launch `odoo-planner` as a subagent (default: ONE planner). For a very
large scope (many independent module clusters) you MAY fan out one planner per cluster following
**Mode B** (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`) and reconcile their
plans; the single planner is the default. Set the subagent `model` to **opus** (the planner's
frontmatter default).

```
DISPATCH MODEL: opus
You are the odoo-planner agent. Produce the 3-block EXECUTION PLAN (NOT code, NOT a design) for:

REQUEST: [the change to ship, target Odoo version, any constraints]
DESIGN_INDEX: [.odoo-ai/designs/<master-slug>/index.yaml, or the single-mode design doc path]
GAP_MATRIX: [omit when absent; else the gap-matrix.jsonl / BRL RTM path]
QA_ORACLE: [omit when absent; else the scenarios.md path]
RETURN_TO: [omit when absent; set to the caller skill name when return routing is requested]

Step 0 (ONLY if mcp__odoo-semantic__* tools are available): set_active_version('<version>'). Then
read DESIGN_INDEX / GAP_MATRIX / QA_ORACLE by pointer and emit the plan CONFORMING to
skills/odoo-intake/references/plan-mode-schema.md (3-block). Wire each node to a SKILL (never an
agent, never the skill's internal coordination). Estimates only (effort + est_agents) - do NOT
bind a per-agent model or fan-out count (Decision X). Do NOT serialize run-<id>.json (intake
Phase P owns that). Do NOT write source files. Do NOT spawn subagents or invoke skills.
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
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

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
> before batching them into waves; it does NOT re-derive the DAG (that is the design's job).

## Agent-managed tools

This skill is part of an agent+skill bundle. See `agents/odoo-planner.md` for the agent's
read-only execution detail and output contract.

## Plan-approval gate (who approves: the human)

When the planner returns the plan, **do NOT auto-chain to execution.** Present a tight summary,
then gate. Write the gate in the USER'S LANGUAGE (translate labels and prose; keep file paths,
module names, model identifiers, and skill names verbatim):

```
Plan ready: .odoo-ai/plans/<slug>-<YYYY-MM-DD>.md
Build order: <wave-1 modules> -> <wave-2 modules> -> ...   (integration cadence: <one line>)
Lifecycle:   code -> review -> doc -> PR -> monitor -> merge   (terminal gates: L2)
Estimates:   effort <S/M/L/XL total> · est_agents <n> (ADVISORY / du kien - the runtime skill
             decides the actual count + model; the plan binds only WHICH skill)
Approve plan? (approve / refine: [feedback] / cancel)
```

- `refine: [feedback]` -> re-dispatch the planner with the feedback; rewrite the same plan file.
- `approve` -> two branches:
  - **`return_to` UNSET (default):** the approved plan is the run-DAG. Call `ExitPlanMode`, then
    hand the approved 3-block plan to intake **Phase P**, which serializes `.odoo-ai/run-<id>.json`
    and dispatches `run-harness` to walk it (coding waves via git-executor, then doc/i18n/PR/
    monitor/merge). This skill never serializes the run file itself.
  - **`return_to` SET (caller-return flow):** do NOT enter Plan Mode for code and do NOT dispatch
    any executor. Emit the Continuation Contract with `next: <return_to>` and hand control back.
- `cancel` -> stop; the plan file remains on disk.

## Decision X - the plan estimates, it never binds model or count

The plan binds **WHICH skill** owns each node. It MUST NOT carry a binding per-agent `model` or a
fan-out `count` - the dispatched specialist skill (e.g. `odoo-coding`) owns those at runtime via
its own tier table + `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` Mode-B budget.
Every quantity the plan states carries an `est_` prefix and the explicit note
"ADVISORY / du kien - the runtime skill decides the actual count/model", so no runtime agent ever
reads a number as a directive. Planning is binding at the inter-module layer (wave-batched
module-DAG + integration cadence); intra-skill coordination (per-module dispatch, backend-first
leg, count/model) stays the specialist skill's.

The integration cadence the plan reserves (per-wave cherry-pick + the saga rollback/resume the
git-executor `odoo-wave` will run) follows the SSOT
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`; planning references it so the plan
reserves that behavior - it does NOT run the loop itself.

## Out of Scope

- **Designing the technical solution** (approach / data model / override strategy / module
  structure) -> `odoo-solution-design` (the design = HOW to build; planning = HOW TO SHIP)
- **Writing production code** -> `odoo-coding` (backend + frontend) / `odoo-wave` (git-orchestrated executor, dispatched by run-harness)
- **Classifying / costing a requirement list** -> `odoo-gap-analysis` (short) / `odoo-brl` (large)
- **Serializing or walking the run-DAG** -> intake Phase P serializes `run-<id>.json`;
  `run-harness` walks it. The plan binds WHICH skill; never the model or count.
- **A heavyweight self-driving orchestrator** (`odoo-forward-port` / `odoo-modules-upgrade` /
  `odoo-git-rebase`) -> these are dispatched-once PEER front doors that own their own gate; route
  such intent to them, do not embed them as plan nodes

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
is **gated on the human plan-approval above**. Choose `next` as follows:

- **`return_to` SET:** emit `next: <return_to>` with `inputs: {plan: <path>}`; hand control back.
- **`return_to` UNSET (default):** emit `next: odoo-intake` with `inputs: {plan: <path>}` - intake's
  **Phase P** ingests the approved 3-block plan by pointer, serializes it into `run-<id>.json`, and
  THEN dispatches `run-harness` to drive it to done. Do NOT emit `next: run-harness` here:
  `run-harness` walks an EXISTING `run-<id>.json` and cannot ingest a plan `.md`, so handing the plan
  straight to it would strand every execution node (it reports `NEEDS_CONTEXT` when no run file
  exists). Serialization is Phase P's job; walking is run-harness's. Do NOT self-dispatch the executor.

Additive output for the Phase P -> run-harness handoff - it does not change anything produced above.
