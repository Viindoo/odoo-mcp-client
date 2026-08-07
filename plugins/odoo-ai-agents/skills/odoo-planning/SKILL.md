---
name: odoo-planning
argument-hint: "[approved design / scope]"
description: >
  Single planning front-door for the FULL product lifecycle - turns an APPROVED Odoo technical
  design into one gate-able plan spanning code AND doc. Dispatches TWO planners: odoo-planner
  (wave-batched code-DAG + integration cadence) AND odoo-doc-planner (dependency-cluster doc
  schedule + instance allocation for user-guide + marketing landing). One plan covers the full
  lifecycle from code to merge, in run-harness's Terminal stage order. Code executes first; doc
  executes after code/review/QA lands. Estimates only (ADVISORY). Fire on:
  "plan the implementation", "execution plan", "what order do we build", "sequence this rollout".
  Vietnamese: "lập kế hoạch thực hiện", "thứ tự build module", "lên kế hoạch triển khai".
  Route the technical DESIGN (data model / override strategy) to odoo-solution-design; WRITING
  code to odoo-coding; costing requirements to odoo-gap-analysis. DO NOT trigger for pure design
  (no execution sequencing)
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
   ->  odoo-planning -> {odoo-planner (code plan) + odoo-doc-planner (doc plan)}
   ->  ONE lifecycle plan gate  ->  ExitPlanMode
   ->  intake Phase P serializes run-<id>.json  ->  run-harness walks code waves
   ->  doc stage (user-doc + marketing-doc) executes after code/review/QA
```

This skill does NOT compute either plan itself and does NOT write code - it dispatches TWO
planners (`odoo-planner` for code, `odoo-doc-planner` for doc) and owns the approve /
ExitPlanMode handoff. `odoo-solution-design` decides HOW to build; `odoo-planning` decides HOW TO
SHIP (module/wave build order, integration cadence, doc cluster schedule, full lifecycle).

Note: `odoo-doc-planner` also runs STANDALONE via `odoo-doc-illustration` / `module-packaging`
for doc-only work on existing modules - `odoo-planning` is NOT the only path to it.

## Role

Odoo delivery planner. Turns an approved technical design into ONE lifecycle plan covering the
full product journey - code-build AND doc. Dispatches TWO leaf planners in sequence:

1. `odoo-planner` (code-build plan): wave-batched module-DAG, integration cadence,
   `run-harness`'s between-wave integration cadence, each `module/stage -> SKILL` wiring. Pure
   code-build planner - no doc-logic.
2. `odoo-doc-planner` (doc-package plan): dependency clusters, branch-aware instance allocation,
   per-instance incremental install-doc-verify-commit order, dedup, parallelism schedule; covers
   user-guide (`doc/index.rst`) AND marketing landing (`static/description/index.html`).
   Runs with `plan_source: design-dag` - reuses the approved design DAG; does NOT re-derive it.

Execution order: the code plan executes first - `run-harness` walks it in the Terminal stage order
constant it owns, never an order chosen here; the doc plan's stage sits inside that same constant,
after acceptance (screenshots need the built module on a live instance).
Both plans are authored UPFRONT in one gate and executed sequentially code then doc.
Pairs with `odoo-solution-design` (consumes its design DAG, passed to both planners) and
`run-harness` (walks the code waves; the doc stage follows as a subsequent lifecycle stage).

## Input port - read the upstream artifacts BY POINTER (before dispatch)

The plan is GROUNDED on three upstream artifacts; locate them and pass their paths to the planner
(do NOT paste their contents, do NOT re-derive their facts):

- **Design DAG** - `<SHARE_DIR>/designs/<master-slug>/index.yaml` (`dag_layers` + dependency
  direction) for a master-child design, or the single-mode `<SHARE_DIR>/designs/<slug>-<date>.md`.
  This is the logical truth the plan batches into waves; the planner CONSUMES it, never recomputes
  it.
- **Gap matrix** - `<SHARE_DIR>/gap-analysis/<slug>-<date>/gap-matrix.jsonl` (or a BRL RTM under
  `<SHARE_DIR>/brl/<job-id>/`) for per-requirement effort tier - drives the `effort` estimate.
- **QA oracle (OPTIONAL - usually ABSENT at planning time)** - `<ISOLATE_DIR>/qa/<slug>-scenarios.md`
  (the immutable acceptance oracle authored by `odoo-qa-planner`). The oracle is normally authored
  LATER, at `odoo-acceptance` Phase 1, after coding - do NOT treat it as a standard planning input.
  When absent (the common case), the plan RESERVES the acceptance stage against the design's §9
  Acceptance Criteria (already authored at design time); when present, the plan wires its
  review/acceptance stages to it directly.
- **Survey (OPTIONAL - ALWAYS an explicit value, never a silently-missing field)** -
  `<SHARE_DIR>/survey/<slug>-<date>/synthesis.md`, forwarded in this skill's own dispatch brief
  `INPUTS` when intake's Proposed Plan `Survey:` field resolved a deep-survey synthesis this
  session (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/SKILL.md` § Deep survey). Additional
  hotspot/impact grounding for wave-batching and effort estimates - never a required gate. State
  `none` explicitly to `odoo-planner` when absent rather than omitting the field, and thread it
  onward the same way (§ P1a below); the mandatory-recon analog is `odoo-intake`'s Phase P
  `inputs.recon_findings`, which this deliberately does NOT copy verbatim (it is safe to OMIT when
  absent since recon is cheap/mandatory-tier - Survey is opt-in/expensive, so its absence must be
  stated, not dropped).

If a design artifact is absent and the change is design-required, route to `odoo-solution-design`
FIRST (design precedes planning) - do not plan an ungrounded build order. Planning itself is
mandatory for ALL work (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` §
Mandatory-planning rule); it is the DESIGN gate that may be skipped for a one-approach change,
never the plan.

## No scope-preview gate - go straight to the planners

Do NOT ask the human to approve a scope preview before dispatching. Whoever sent the work here
already gated that same decision: the front door (`odoo-intake`) approved scope, approach and
expected output with the human before dispatching this skill, and a `return_to` caller classified
scope itself. Asking again is friction, not safety.

Ask only the genuine open questions the Input port could not resolve (a missing design artifact,
an ambiguous module set) - in ONE short message - then dispatch both planners. The single
approval checkpoint this skill owns is the § Plan-approval gate below, after both planners return.
Same shape as the sibling self-driving front doors (`odoo-forward-port` P4, `odoo-git-rebase` P6,
`odoo-modules-upgrade` P3): one plan, one gate.

The planners write ONLY the plan under the `$ODOO_AI_HOME` state root (SHARE tier - see
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`); no source file is touched before the
plan is approved.

## Agent invocation - prompt templates (P1: code + doc)

When composing the dispatch prompt for any specialist agent you dispatch, fill the caller-side
skeleton in `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` (read it by path) plus the target
agent's family delta; never inline that file verbatim into a hard-leaf brief. Field 11
(`CALLER_ID`/`REPLY_TO`) applies here too: run the CHP capability probe once (per
`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` - Capability probe) before the P1a
dispatch below; when positive (Agent Team mode on), inject `TASK_ID` + `REPLY_TO: <this skill's
current orchestrating context>` (`main` only when the main context launched this skill directly -
never a hardcoded literal) into each planner's brief and read its result via the `SendMessage` push
per `${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md` - the same CHP-conditional pattern
`skills/odoo-forward-port/SKILL.md` already implements (cited, not restated here). When the probe
is negative, dispatch + collect as today (final message + Continuation Contract).

When intent is confirmed, dispatch BOTH planners sequentially. Their outputs compose into one
lifecycle plan presented at a single gate.

### P1a - Code plan (odoo-planner)

Launch `odoo-planner` as a subagent (default: ONE planner). For a very large scope (many
independent module clusters) you MAY fan out one planner per cluster following **Mode B**
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`) and reconcile their plans;
the single planner is the default. Set the subagent `model` to **opus** (the planner's
frontmatter default).

```
DISPATCH MODEL: opus
You are the odoo-planner agent. Produce the 3-block EXECUTION PLAN (NOT code, NOT a design) for:

REQUEST: [the change to ship, target Odoo version, any constraints]
DESIGN_INDEX: [<SHARE_DIR>/designs/<master-slug>/index.yaml, or the single-mode design doc path]
GAP_MATRIX: [omit when absent; else the gap-matrix.jsonl / BRL RTM path]
QA_ORACLE: [omit when absent - the common case at planning time, since the oracle is authored
later at odoo-acceptance Phase 1; else the scenarios.md path]
SURVEY: [none | <SHARE_DIR>/survey/<slug>-<date>/synthesis.md - the deep-survey synthesis from
intake's Proposed Plan `Survey:` field, when one was run this session; explicit `none` when no
deep survey was opted into - never omit this field, unlike GAP_MATRIX/QA_ORACLE above]
RETURN_TO: [omit when absent; set to the caller skill name when return routing is requested]

Step 0 (ONLY if mcp__odoo-semantic__* tools are available): set_active_version('<version>'). Then
read DESIGN_INDEX / GAP_MATRIX / QA_ORACLE / SURVEY by pointer and emit the plan CONFORMING to
skills/odoo-intake/references/plan-mode-schema.md (3-block). Wire each node to a SKILL (never an
agent, never the skill's internal coordination). Estimates only (effort + est_agents) - do NOT
bind a per-agent model or fan-out count (Decision X). Do NOT serialize run-<id>.json (intake
Phase P owns that). Do NOT write source files. Do NOT spawn subagents or invoke skills.
```

### P1b - Doc plan (odoo-doc-planner)

**Fast-path `doc: none`.** When the change is internal-only with no user-guide or marketing goal
(no Apps-Store listing, no end-user docs), SKIP the P1b dispatch (or dispatch so the doc planner
returns an empty plan) and record "doc plan: none (internal-only)" at the plan gate. Default stays:
dispatch the doc planner whenever there is any store/doc intent - the human still confirms scope at
the plan-approval gate.

After P1a returns, launch `odoo-doc-planner` as a SEPARATE subagent. It reuses the design DAG
from DESIGN_INDEX (`plan_source: design-dag`) and does NOT re-derive the module graph.
Model: **sonnet** (the doc planner's frontmatter default).

```
DISPATCH MODEL: sonnet
You are the odoo-doc-planner agent. Produce the DOC-PACKAGE PLAN for:

REQUEST: [same change as P1a]
DESIGN_INDEX: [same path as P1a - read dag_layers by pointer, do NOT re-derive the graph]
plan_source: design-dag
LANGUAGES: [brief-specified list if any; otherwise resolve from registry - English always included]

Apply the scheduling algorithm from skills/_shared/doc-cluster-plan.md. Emit doc-plan.yaml to
<SHARE_DIR>/plans/<slug>-doc-<date>.yaml covering user-guide (doc/index.rst) AND marketing landing
(static/description/index.html) for every in-scope module. Estimates only. Do NOT provision any
instance. Do NOT spawn subagents or invoke skills.
```

After both return, stitch their summaries into the combined plan-approval gate (see below).
Note: the doc plan's EXECUTION is deferred - it runs after the code plan's waves land.

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
> before batching them into waves; it does NOT re-derive the DAG (that is the design's job).

## Agent-managed tools

This skill is part of an agent+skill bundle. See `agents/odoo-planner.md` for the agent's
read-only execution detail and output contract.

### Plan Mode guard (enter HERE, after both planners return, before the approval gate)

Enter Plan Mode HERE, AFTER both planners have returned and BEFORE presenting the "Plan ready"
gate - the planners write ONLY under the `$ODOO_AI_HOME` state root (SHARE tier), and Plan Mode
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

The ENTER already happened above (§ Plan Mode guard, after both planners returned). This section
covers what happens next: present the plan, gate on human approval, then `ExitPlanMode`.

When BOTH planners return, **do NOT auto-chain to execution.** Present a tight combined summary,
then gate. Write the gate in the USER'S LANGUAGE (translate labels and prose; keep file paths,
module names, model identifiers, and skill names verbatim):

```
Plan ready:
  Code plan:  <SHARE_DIR>/plans/<slug>-<YYYY-MM-DD>.md
  Doc plan:   <SHARE_DIR>/plans/<slug>-doc-<YYYY-MM-DD>.yaml
Build order: <wave-1 modules> -> <wave-2 modules> -> ...   (integration cadence: <one line>)
Doc clusters: <n clusters> · <n instances> · <n modules doc'd>   (allocation: <one line>)
Lifecycle:   <the Terminal stage order constant run-harness owns, rendered in full>
             (doc executes AFTER code/review/QA; both plans gate here in ONE approval)
Estimates:   effort <S/M/L/XL total> · est_agents <n> (ADVISORY / du kien - the runtime skill
             decides the actual count + model; the plan binds only WHICH skill)
Approve plan? (approve / refine: [feedback] / cancel)
```

- `Lifecycle:` renders the Terminal stage order constant IN FULL - resolve it from
  `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md` § Pre-PR tail >
  Terminal stage order, that section being the order's ONE owner. Never restate the order here.
- `refine: [feedback]` -> re-dispatch the planner with the feedback; rewrite the same plan file.
- `approve` -> two branches:
  - **`return_to` UNSET (default):** the approved plan is the run-DAG. Call `ExitPlanMode`, then
    hand the approved 3-block plan to intake **Phase P**, which serializes `<ISOLATE_DIR>/run-<id>.json`
    and dispatches `run-harness` to walk it (coding waves via its own between-wave integration,
    then the terminal tail in the Terminal stage order constant). This skill never serializes the
    run file itself.
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

The integration cadence the plan reserves (per-wave cherry-pick onto the ONE run-integration branch +
the saga rollback/resume + per-wave auto-advance, then the SINGLE run-level PR opened once after the
FINAL wave - NO per-wave PR - which `run-harness`'s between-wave integration will run) follows the SSOT
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`; planning references it so the plan
reserves that behavior - it does NOT run the loop itself. The plan likewise reserves the per-wave
cumulative close-verify (`run-harness`'s between-wave close-gate) the planner surfaces as each coding-wave node's
`cumulative_modules` scope, following the SSOT
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/cumulative-test-scope.md`; planning REFERENCES it, it does NOT
run the suite.

## Out of Scope

- **Designing the technical solution** (approach / data model / override strategy / module
  structure) -> `odoo-solution-design` (the design = HOW to build; planning = HOW TO SHIP)
- **Writing production code** -> `odoo-coding` (backend + frontend); git-orchestrated multi-module landing is `run-harness`'s between-wave integration (driven from the approved plan, not a separate skill)
- **Classifying / costing a requirement list** -> `odoo-gap-analysis` (short) / `odoo-brl` (large)
- **Serializing or walking the run-DAG** -> intake Phase P serializes `run-<id>.json`;
  `run-harness` walks it. The plan binds WHICH skill; never the model or count.
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
is **gated on the human plan-approval above**. Choose `next` as follows:

- **`return_to` SET:** emit `next: <return_to>` with `inputs: {plan: <path>, doc_plan: <path>}`;
  hand control back.
- **`return_to` UNSET (default):** emit `next: odoo-intake` with
  `inputs: {plan: <path>, doc_plan: <path>}` - intake's **Phase P** ingests the approved 3-block
  code plan by pointer, serializes it into `run-<id>.json`, and THEN dispatches `run-harness` to
  drive it to done. The doc plan (`doc-plan.yaml`) is consumed by the doc stage after code lands.
  **This is the SSOT rationale for "why `next: odoo-intake`, not `next: run-harness`"** (other sites
  - `agents/odoo-planner.md`, `skills/odoo-intake/references/phase-p-run-dag.md` - point here, do
  not restate it): Do NOT emit `next: run-harness` here: `run-harness` walks an EXISTING
  `run-<id>.json` and cannot ingest a plan `.md`, so handing the plan straight to it would strand
  every execution node (it reports `NEEDS_CONTEXT` when no run file exists). Serialization is Phase
  P's job; walking is run-harness's. Do NOT self-dispatch the executor.

Note: the on-the-fly execution task list is owned by `run-harness`, NOT by this skill - run-harness
creates and keeps it current per
`${CLAUDE_PLUGIN_ROOT}/snippets/execution-tasklist-contract.md` whenever a task-list tool is
available, INDEPENDENT of the CHP capability probe / Agent Team mode (that gate applies only to
the separate teammate-status layer, `${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md` Ask 2).
See `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md`.

Additive output for the Phase P -> run-harness handoff - it does not change anything produced above.
