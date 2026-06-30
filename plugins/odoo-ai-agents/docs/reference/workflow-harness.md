# Workflow Harness - Reference

> **SSOT for the workflow harness architecture.**
> Skills, workflow files, and the BRL engine reference this document for schema
> definitions, gate conventions, and composition contracts.
> Design reference: internal architecture notes.

---

## Table of Contents

1. [Overview - three-layer architecture](#1-overview-three-layer-architecture)
2. [`.odoo-ai/` artifact convention](#2-odoo-ai-artifact-convention)
3. [BRL job schema](#3-brl-job-schema)
4. [Soft-plan-gate convention](#4-soft-plan-gate-convention)
   - [4.1 Plan mode and skills - what is and isn't possible](41-plan-mode-and-skills--what-is-and-isnt-possible)
   - [4.2 Gate template](42-gate-template)
   - [4.3 Enforcement stack](43-enforcement-stack)
   - [4.4 BRL-specific gates](44-brl-specific-gates)
   - [4.5 Phase R - Recon (read-only current-state survey)](45-phase-r--recon-read-only-current-state-survey)
   - [4.6 Plan Mode Content Schema](46-plan-mode-content-schema)
   - [4.7 Inventory discovery - hybrid SSOT rules](47-inventory-discovery--hybrid-ssot-rules)
5. [Composition contract](#5-composition-contract)
6. [Skill delegation rule](#6-skill-delegation-rule)
7. [Git-wave orchestration (orchestrating context)](#7-git-wave-orchestration-orchestrating-context)
8. [Drive-to-done orchestration (Continuation Contract + run-harness)](8-drive-to-done-orchestration-continuation-contract--run-harness)
   - [8.1 North Star diagram](81-north-star-diagram)
   - [8.2 Continuation Contract](82-continuation-contract)
   - [8.3 run-<id>.json blackboard](83-run-idjson-blackboard)
   - [8.4 Gate-tier policy](84-gate-tier-policy)
   - [8.5 Command / Skill / Agent - the three axes](85-command--skill--agent--the-three-axes)
   - [8.6 Main Agent Operating Contract](86-main-agent-operating-contract)

---

## 1. Overview - three-layer architecture

The workflow harness is organized in three layers. Every workflow lives in exactly
one layer; cross-layer calls travel top-down only and never skip a layer.

```
┌────────────────────────────────────────────────────────────────┐
│  ENTRY / INTAKE LAYER  (orchestrating context)                  │
│  odoo-intake skill - Odoo front door                             │
│  · Phase 0: 4-tier routing + intent gate (mandatory)           │
│  · Phase R: read-only Recon (≤1-2 agents, no writes)           │
│  · Proposed Plan + soft-plan-gate                               │
│  · Plan Mode (EnterPlanMode/ExitPlanMode) for writes-files      │
│  · gate is BEHAVIORAL (in-skill) + Plan Mode - not a write-block │
└───────────────────────────────────┬────────────────────────────┘
                                    │ Skill tool (orchestrating context canonical; NL-dispatch fallback)
                                    ▼
┌────────────────────────────────────────────────────────────────┐
│  WORKFLOW LAYER  (dispatched-specialist)                        │
│  Declarative *.workflow.yaml + workflow-chaining skill            │
│  · maps one of 6 team-patterns to a gated phase sequence        │
│  · phase gates: approve / refine / cancel between phases        │
│  · writes .odoo-ai/<output_dir>/ artifacts                      │
│  Monolithic skills (odoo-brl) also live here                    │
└───────────────────────────────────┬────────────────────────────┘
                                    │ NL-dispatch or context: fork (≤3)
                                    ▼
┌────────────────────────────────────────────────────────────────┐
│  EXECUTION LAYER  (leaf-worker)                                 │
│  Specialist skills (odoo-coding, odoo-code-review, …)          │
│  MCP tool calls (odoo-semantic-mcp server)                      │
│  context: fork subagents - carry hard-rules line, no spawner-  │
│    skill dispatch (depth-cap-5; non-fork interior agents CAN    │
│    spawn their own subagents - see §6 Skill delegation rule)    │
└────────────────────────────────────────────────────────────────┘
```

**Two invariants enforced across every workflow:**

- **1-orchestration-SSOT**: orchestration logic lives in one place - either a
  `*.workflow.yaml` file or a monolithic skill body. It is never duplicated between
  a command shim and a skill body.
- **Fan-out worker constraint**: `context: fork` fan-out workers carry the hard-rules
  line and do NOT dispatch spawner skills or spawn further subagents. Non-fork interior
  agents (e.g. `odoo-coder`, `odoo-code-reviewer`) MAY spawn their own subagents;
  the platform enforces a depth cap of 5. Resources are platform-managed.
- **No Claude Code Workflow (JS) tool**: this plugin orchestrates entirely through the
  Skill tool, the Agent tool, and the `run-harness` loop - it deliberately does NOT emit
  Claude Code Workflow (JS) scripts (the `Workflow` tool with `args` + `agent()`) for
  codegen or orchestration. Dispatch fan-out (e.g. `odoo-coding`, `odoo-wave`) is real
  Agent-tool calls in model-weighted batches (SSOT `skills/_shared/concurrency-guard.md`
  Mode B). Never hand-roll a JS Workflow script to parallelize plugin work: passing the
  plan through the tool's `args` channel is the args-undefined footgun this design avoids.

---

## 2. `.odoo-ai/` artifact convention

`.odoo-ai/` is gitignored by the onboarding skill (`/odoo-onboarding`). All runtime
artifacts are written here; nothing under `.odoo-ai/` is committed to the repo.

### File-ownership table

| Component | Sub-path | Written by |
|-----------|----------|------------|
| Context snapshot | `.odoo-ai/context.md` | `odoo-onboarding` skill |
| Brainstorm state | `.odoo-ai/brainstorm/state.json` | `odoo-intake` skill |
| Brainstorm design doc | `.odoo-ai/brainstorm/<slug>-<date>.md` | `odoo-intake` (approval turn) |
| BRL job artifacts | `.odoo-ai/brl/<job-id>/` | `odoo-brl` skill |
| Workflow phase state | `<output_dir>/<slug>-state.json` (output_dir is the full `.odoo-ai/...` path) | `workflow-chaining` |
| QA artifacts | `.odoo-ai/qa/` | `qa-suite` workflow (static test-plan / checklist / triage); `odoo-acceptance` skill (scope manifest + immutable oracle + live acceptance report) |
| Wave execution log | `.odoo-ai/wave/<slug>/` | `odoo-wave` skill (orchestrating context) |
| Execution plan (3-block) | `.odoo-ai/plans/<slug>-<date>.md` | `odoo-planner` (via `odoo-planning`) - the wave-batched module-DAG + integration cadence + lifecycle plan |
| Design doc (single mode) | `.odoo-ai/designs/<slug>-<date>.md` | `odoo-solution-architect` (one module or simple scope) |
| Design artifacts (master-child) | `.odoo-ai/designs/<master-slug>/` - `index.yaml` (routing SSOT) + `_master-<date>.md` + `<module>-<date>.md` per module; full schema: `snippets/master-child-design-contract.md` | `odoo-solution-architect` (multi-module or large scope) |

Every new workflow declares its `output_dir` in its `*.workflow.yaml` file
(see §5). `output_dir` is the full path (e.g. `.odoo-ai/qa`) and is the single
registration point for that workflow's artifacts.

---

## 3. BRL job schema

The BRL (Business Requirement List) engine writes all artifacts under
`.odoo-ai/brl/<job-id>/`. The job ID format is
`<CUSTOMER_LABEL>-<YYYYMMDD>-<4hex>` (e.g. `Customer-A-20260531-9f3a`).

### 3.1 Directory layout

```
.odoo-ai/brl/<job-id>/
  manifest.json          # immutable job metadata
  input.jsonl            # 1 line per requirement: {req_id, req_text, req_category?, priority?}
  chunkplan.json         # {chunk_size, chunks: [{idx, req_ids:[...]}]}
  checkpoint.json        # machine-resume state
  chunks/
    chunk-000.A.jsonl    # classify output for chunk 0
    chunk-000.B.jsonl    # cost output
    chunk-000.C.jsonl    # evidence output
    chunk-001.A.jsonl
    ...
  cache.json             # module-verdict cache (key → MCP response) - avoids duplicate calls
  results.jsonl          # merged final RTM (1 obj/line, machine-readable SSOT)
  rtm.csv                # consultant export (Excel-ready)
  dag.json               # {nodes, edges, topological_order, phases, critical_path}
  dag.mermaid            # flowchart TD by implementation phase
  cost.json              # project-level cost roll-up
  report.md              # executive human-readable summary
  errors.jsonl           # per-item failures (license-restricted, MCP error, unmapped)
                         # informational only - does not block the batch
```

### 3.2 manifest.json

Written once at job creation (Phase 0 - ingest). Never mutated after Gate 0 approval.

```json
{
  "job_id": "Customer-A-20260531-9f3a",
  "created_at": "2026-05-31T10:00:00Z",
  "customer_label": "Customer-A",
  "odoo_version": "17.0",
  "profiles": {"odoo": "odoo_17", "viindoo": "standard_viindoo_17"},
  "total_reqs": 1000,
  "chunk_size": 50,
  "cost_config_ref": "cost-config.json@v1",
  "rate_region": "vn",
  "risk_profile": "medium",
  "schema_version": "brl/1.0"
}
```

### 3.3 checkpoint.json - resume contract

Updated after every completed chunk. Resume reads `last_completed_chunk` and enters
the outer loop at `last_completed_chunk + 1`. Re-running a chunk overwrites its
`chunk-NNN.*.jsonl` files - the operation is idempotent.

```json
{
  "job_id": "Customer-A-20260531-9f3a",
  "phase": "classify",
  "processed": 350,
  "total": 1000,
  "last_completed_chunk": 6,
  "chunks_done": [0, 1, 2, 3, 4, 5, 6],
  "session_pinned_at": "2026-05-31T10:00:00Z",
  "per_req": {
    "REQ-0001": "done",
    "REQ-0351": "pending"
  }
}
```

`phase` values: `ingest | classify | dag | deliver | done`.  
`session_pinned_at` is used to detect the 24 h session TTL: if
`now - session_pinned_at > 23 h` or the MCP server returns "no active version",
the engine re-runs bootstrap (`set_active_version` + `set_active_profile`) and
updates the timestamp before the next chunk.  
`per_req` is sparse - only in-flight items appear; completed items are omitted.

### 3.4 results.jsonl - one object per requirement (RTM SSOT)

```json
{
  "req_id": "REQ-0042",
  "req_text": "Three-level invoice approval",
  "req_category": "Functional",
  "priority": "Must-have",
  "classification": "Available-in-Odoo-CE",
  "module": "account",
  "edition": "CE",
  "effort_tier": "Extension-M",
  "effort_days_min": 1,
  "effort_days_max": 3,
  "effort_phase": "Config & Development",
  "cost_usd_min": 350,
  "cost_usd_max": 1050,
  "risk_flag": null,
  "evidence_module": "account",
  "evidence_field": "account.move:state",
  "evidence_snippet_ref": "chunks/chunk-000.C.jsonl#L12",
  "dependencies": ["REQ-0010", "REQ-0015"],
  "impl_phase": 2,
  "status": "Not started",
  "notes": ""
}
```

`classification` is one of:
`Available-in-Odoo-CE | Available-in-Odoo-EE | Available-in-Viindoo | Custom`.

`effort_tier` is one of:
`Standard | Config | Extension-M | Extension-L | Custom-XL`.

### 3.5 rtm.csv - header

```
req_id,req_text,req_category,priority,classification,module,edition,effort_tier,
effort_days_min,effort_days_max,cost_usd_min,cost_usd_max,dependencies,impl_phase,
evidence_module,evidence_field,risk_flag,status,notes
```

`dependencies` is pipe-joined (`REQ-0010|REQ-0015`) to remain CSV-safe.

### 3.6 cost.json - project-level roll-up

```json
{
  "base_effort_days": {"min": 210.5, "max": 612.0},
  "customization_coefficient": 1.3,
  "cross_module_factor": 0.96,
  "project_effort_days": {"min": 290, "max": 820},
  "blended_rate_usd": 300,
  "contingency_pct": 0.15,
  "budget_usd": {"min": 100050, "max": 282900},
  "phase_breakdown_usd": {
    "discovery_blueprint": "...",
    "config_development": "...",
    "data_migration": "...",
    "testing_uat": "...",
    "training": "...",
    "golive_hypercare": "...",
    "contingency_reserve": "..."
  },
  "annual_maintenance_usd": "...",
  "classification_mix": {
    "CE": 0.55,
    "EE": 0.08,
    "Viindoo": 0.10,
    "Custom": 0.27
  }
}
```

Every number traces back to `cost-config.json` (shipped with the skill, override-able
at `.odoo-ai/`) via `effort_tier → effort_lookup → rate_card → multiplier`. No cost
figures are hard-coded in the skill body.

### 3.7 dag.json - dependency graph

```json
{
  "nodes": [
    {"id": "REQ-0001", "module": "account", "effort_days": 3, "impl_phase": 1}
  ],
  "edges": [
    {
      "from": "REQ-0010",
      "to": "REQ-0042",
      "type": "business-logic",
      "reason": "approval flow requires chart-of-accounts setup first"
    }
  ],
  "topological_order": ["REQ-0010", "REQ-0042", "..."],
  "phases": {"1": ["REQ-0010"], "2": ["REQ-0042"]},
  "critical_path": ["REQ-0010", "REQ-0042"],
  "critical_path_days": 18
}
```

Edge `type` values: `technical | business-logic | data-flow`.  
Technical edges come from `module_inspect(name=<module>, method='dependencies', odoo_version='<version>')` (deterministic).  
Business-logic and data-flow edges come from Opus cluster reasoning.

---

## 4. Soft-plan-gate convention

### 4.1 Plan mode and skills - what is and isn't possible

Skills, commands, and hooks **cannot declaratively set** `permission_mode=plan` in
their frontmatter or configuration. User-initiated plan mode (Shift+Tab, `/plan`, CLI
flag, `defaultMode` in settings) is separate from anything a skill can declare.

However, this does **not** mean plan mode is unreachable from within a skill-driven
flow:

- **The orchestrating context CAN call `EnterPlanMode` / `ExitPlanMode`** - these are
  platform tools available to the main context. A skill running in the orchestrating
  context (e.g., `odoo-intake`) may instruct the main agent to invoke `EnterPlanMode`
  before any file-touching execution, producing genuine UI-approved Plan Mode - a
  stronger enforcement than a text gate.
- **Subagents cannot call `EnterPlanMode`** - the tool is only reachable from the
  main context. `ExitPlanMode` is only available to a subagent whose `permissionMode`
  is already `plan`.

#### Plan Mode decision tree

Run this before any execute-skill dispatch. Intake reads the chosen Approach's
`output_mode` (resolved via Phase R inventory discovery - §4.7):

- `output_mode = writes-files` → **Plan Mode is REQUIRED**. Proceed through the full
  EnterPlanMode → content schema → ExitPlanMode procedure (see §4.6).
- `output_mode = chat-only` → **SKIP Plan Mode**. Intake ends its turn; the specialist
  fires via the **Skill tool** on the next turn. Chat-only skills include:
  `odoo-feature-check`, `odoo-version-diff`, `odoo-risk-overview`,
  `odoo-deprecation-audit`, `odoo-gap-analysis`, `odoo-discovery-summary`,
  `odoo-capability-proof`, `odoo-objection-handling`, `odoo-content-draft`,
  `odoo-competitive-brief`, and any skill whose output column is "chat only".
  > **SSOT note:** the authoritative `output_mode` now lives per-skill in
  > `generator/skill_tool_deps.json` → `orchestration.<skill>.output_mode` (see §8.4).
  > The inline list above is a convenience snapshot; once intake reads the registry field
  > directly (P3), this list is removed in favour of the field. Until then both agree -
  > the field is a superset that preserves every skill listed here.
- **Skill owns a stronger gate** → **SKIP soft-plan-gate AND Phase P**. When the routed
  skill opens with a STOP plan gate richer than intake's soft-plan-gate (e.g.
  `odoo-forward-port` P0 emits a per-commit plan.md + STOP before any branch or merge),
  do NOT also emit the soft-plan-gate - two consecutive approval gates for one action is
  friction, and the skill's gate is the authoritative one. Launch the skill directly with
  a one-liner noting it will present its own plan and stop for approval. Phase P does NOT
  engage for these skills: a self-gating + self-resuming skill (P0 STOP gate +
  checkpoint.json resume) owns its own run-DAG; intake dispatches it once and the skill
  drives itself.

#### Intake-initiated Plan Mode pattern

When `odoo-intake` (running in the orchestrating context) reaches the execute phase
after the user approves a Proposed Plan and the Approach `output_mode = writes-files`,
the main agent calls `EnterPlanMode` → writes the implementation plan (see §4.6
Content Schema) for UI review → receives user approval via `ExitPlanMode` → then
dispatches the file-touching specialist. This is a first-class enforcement option, not
a workaround.

There is **no platform write-block** behind the gate: `odoo-intake` does not declare
`disallowed-tools: Write Edit`, and the coders (`odoo-coding`) DO write/apply code - that is
their job. The gate is enforced by two behavioral mechanisms, Plan Mode being the strongest
layer when the orchestrating context is available:

1. **Anti-rationalize gate** in the skill body - behavioral: "no execution fires until the user
   has approved a Proposed Plan". Paired with a Red Flags table listing rationalizations
   the agent must refuse (e.g., "This is simple, I'll just start coding" → STOP).
2. **Coder preview-then-write** - before mutating a file a coder previews the proposed
   patch in its turn; the write follows the same turn once the approach is settled.
   A discipline, not a tool restriction.

For skills that **cannot** rely on the orchestrating context (e.g. invoked from inside a
subagent), the behavioral anti-rationalize gate (mechanism 1) is the fallback when
`EnterPlanMode` is unavailable.

### 4.2 Gate template

Every multi-phase workflow emits this block before any execution:

```
## Proposed Plan
Domain:       <one of 9 persona buckets>
Approach:     <skill name | workflow name>
Chain:        <skill A> → <skill B> → ...   (for multi-phase workflows)
Output:       .odoo-ai/<subdir>/<slug>-<date>.<ext>   (or "chat only")
Est. effort:  <S / M / L / XL | "single turn">
Model tier:   <per phase, for workflows>

Gate: approve / refine: [feedback] / cancel
```

### 4.3 Enforcement stack

| Layer | Mechanism | Scope |
|-------|-----------|-------|
| Behavioral | Anti-rationalize gate + Red Flags in skill body | Blocks writes-files dispatch until plan approved |
| Coder discipline | Preview patch, then write in-turn | Coders apply code; no platform write-block |
| Recon boundary | Phase R agents: read-only, no spawn, no writes | Allows current-state survey without breaching gate |
| Plan Mode | `EnterPlanMode` / `ExitPlanMode` | Harness-level enforcement before writes-files execution |
| Approval | `odoo-intake` ends turn; next user prompt enables writes | Write unlock |
| Refine loop | Gate loops inside brainstorm; no writes until `approve` | Iteration |

On `approve` (text gate) + Plan Mode approved (harness level): the specialist fires
via the **Skill tool** (writes-files path). For chat-only Approaches, Plan Mode is skipped
and the specialist fires immediately on the next turn (also via the Skill tool).  
On `refine: [feedback]`: the brainstorm loop continues within the current turn.  
On `cancel`: the skill stops and reports.

**What intake CAN do before the gate closes**: Phase R read-only Recon - dispatching
≤1-2 read-only agents (Explore or read-only specialists) and calling read-only OSM
tools (`model_inspect`, `check_module_exists`, `find_override_point`, `impact_analysis`).
Recon agents are leaf-workers, no file writes, no sub-agent spawning. This is NOT a breach
of the gate; it feeds into the Proposed Plan's Findings (Recon) field.

### 4.4 BRL-specific gates

The BRL engine has two gates (not one per chunk - that would break UX at 20 chunks):

- **Gate 0** (after ingest): shows `{N items, M chunks, version/profile, estimated
  MCP call budget, estimated cost band}`. Options: `approve / refine(chunk_size,
  version, rate_region, risk_profile) / cancel`.
- **Gate E** (before writing deliverables): shows `{classification mix %, total cost
  range, critical-path days, cycles resolved}`. Options:
  `approve → write deliverables / refine → re-run Phase D or E`.

Internal state files (`manifest.json`, `input.jsonl`, `checkpoint.json`) are written
before Gate 0 (they are not deliverables). Final deliverables (`results.jsonl`,
`rtm.csv`, `cost.json`, `dag.*`, `report.md`) are written only after Gate E approval.

---

### 4.5 Phase R - Recon (read-only current-state survey)

Phase R is a **formal stage** in the intake 5-phase flow that runs **after** Phase 0
closes the intent gate and **before** the Proposed Plan is written. Its purpose is to
turn a generic plan into a context-aware one - surveying what already exists rather
than guessing.

#### Position in the 5-phase flow

```
Phase 0 (Context, Detect & Clarify - closes intent/purpose/outcomes gate)
    ↓
Phase R (Recon - read-only current-state survey)   ← NEW formal stage
    ↓
Proposed Plan  (context-rich, informed by Recon findings)
    ↓
Plan Mode  (EnterPlanMode → Content Schema → ExitPlanMode)
    ↓
Execute  (writes-files specialist dispatched via the Skill tool; the skill fans out its own agent)
```

#### What Phase R does

- **Launches ≤1-2 READ-ONLY recon subagents**: `Explore`, or an anonymous recon agent.
  A read-only leaf skill (e.g. `odoo-feature-check`, `odoo-override-finding`) is instead
  invoked via the Skill tool. These map the code or modules relevant to the stated intent.
- **Calls read-only OSM tools** as needed: `model_inspect`, `check_module_exists`,
  `find_override_point`, `impact_analysis`.
- **Never mutates** the filesystem. No `Write`, no `Edit`, no writes-files specialist.

#### Hard limits for Phase R agents

| Constraint | Rule |
|------------|------|
| Role | dispatched-specialist (leaf - launched by the orchestrating context) |
| Nesting | Recon agents MUST NOT spawn further sub-agents |
| File writes | PROHIBITED - Read/Grep/Glob/Bash (read-only) only |
| OSM | Read-only calls allowed; if unreachable, fall back to disk (Read/Grep the local repo, WebFetch upstream source) per `disk-fallback-protocol.md` |
| Count | ≤1-2 agents per Recon; not a fan-out pipeline |

The worker brief is described in full at
`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`. Every Recon agent brief MUST
include the mandatory hard-rules line from §6 (adapted to read-only: no Write/Edit,
no Skill tool, no sub-agent spawn).

#### Rationale

Without Phase R, intake writes a Proposed Plan from user descriptions alone - it cannot
confirm which modules exist, the current hook points, or a change's blast radius. Phase R
answers these cheaply (read-only leaf-workers) so the Proposed Plan's `Findings (Recon)` field
is concrete, not speculative - the same principle as `odoo-override-finding` confirming a hook
before `odoo-coding` writes the override.

---

### 4.6 Plan Mode Content Schema

> **SSOT: `skills/odoo-intake/references/plan-mode-schema.md`** (the human-readable 3-block plan).
> Restated here only as a labeled pointer (the §8 "restated to avoid drift" pattern) - the full
> block schemas, worked examples, and rejection flow live in that one file. For a NON-TRIVIAL
> multi-module change the 3-block plan is AUTHORED by the `odoo-planning` skill (via its
> `odoo-planner` agent); for a trivial single-WI change `odoo-intake` writes the inline
> micro-plan. Either way the plan CONFORMS to the SSOT above - never a second format.

When `output_mode = writes-files` (decision tree §4.1) the plan written inside Plan Mode (step 3
of the EnterPlanMode procedure) MUST contain three blocks, none optional:

- **Block 1 - Workitem list** - one entry per WI: `id`, a one-line description, and disjoint
  `files-in-scope` (no two WIs claim the same file; disjointness is per-file, never
  per-node-within-a-file). Multi-WI deliveries also note worktree + branch + verify command per
  WI. A workflow-command is ONE WI (its `output_dir/`), never expanded into its internal phases.
- **Block 2 - Dependency graph** - a typed-edge DAG (`type: technical | business-logic |
  data-flow` + `reason`, plus `topological_order`, `critical_path`, `cycles: []`); for a few WIs
  pick one of the four `odoo-wave/reference/wave-templates.md` topologies
  (`independent | linear | mixed | diamond`). A mermaid diagram is encouraged.
- **Block 3 - Assignment** - one line per WI: `WI -> skill | command | agent`, plus per-WI
  acceptance criteria + a verify command. Estimates ONLY: `effort` (S/M/L/XL) and, for a spawner
  node, `est_agents`. Both are ADVISORY / du kien - the dispatched specialist skill owns the
  actual per-agent model + fan-out count at runtime (Decision X). The plan binds WHICH skill; it
  never binds a model or a count.

---

### 4.7 Inventory discovery - hybrid SSOT rules

When Phase R or plan-writing needs to know which skills, agents, or commands exist
and their runtime attributes, pull each fact from its **single source of truth**.
Do NOT copy fields between sources - duplication creates drift.

| Attribute | SSOT | How to fetch |
|-----------|------|--------------|
| skill/agent/command **exists** + its description | Runtime context (harness-injected by the platform) | Already available - do NOT read files for this |
| `model_tier` (Haiku / Sonnet / Opus / inherit) | `model:` field in the candidate's `SKILL.md` or `agents/*.md` frontmatter | Read the frontmatter of the **chosen candidate only** at plan time |
| `output_mode` (`chat-only` ↔ `writes-files`) | the explicit `output_mode` field in `skill_tool_deps.json` → `orchestration.<skill>` | Read that field directly. Its value was set per-skill from the skill's declared Output semantics - NOT crudely derived from `stack` (a backend/frontend-stack skill can be read-only/chat-only) |
| `effort` (S / M / L / XL) | NOT registered - it is a skill × task property | Reason per the `odoo-gap-analysis` legend: S <1d · M 1-3d · L 3-10d · XL >10d |

**Key invariants:**

- `model_tier` lives in frontmatter and MUST NOT be copied into any registry or plan
  as a constant. Read it fresh at plan time from the candidate's own SKILL.md.
  Skills that dispatch per-work-item at varying tiers (`odoo-coding`, `odoo-debug`,
  `odoo-solution-design`) resolve and record the dispatch tier in their OWN runtime
  dispatch/gate-table at execution time - never in the planning artifact (Decision X:
  the plan binds WHICH skill, it never binds a model or a count).
- `effort` is per-task, not per-skill. Two invocations of the same skill can have
  different effort tiers depending on scope.
- `output_mode` is the only attribute whose SSOT is the registry - the explicit
  `orchestration.<skill>.output_mode` field in `skill_tool_deps.json` (NOT a `spawn_class`/`stack`
  derivation; see §8.4). This is what drives the Plan Mode decision tree (§4.1).

**Why hybrid?** Each attribute lives where it is cheapest to keep accurate:
description in runtime context (maintained by the platform), model in the skill's own
frontmatter (maintained by skill authors), output_mode in the generator registry
(maintained by the generator pipeline), and effort left to per-task reasoning
(no registry can capture task-specific scope).

---

## 5. Composition contract

### 5.1 Why declarative workflows

Hard-coded command files each contain bespoke phase logic in prose. Adding new
workflows (QA, support, video) the same way produces N bespoke files that violate
SSOT (one schema in each). The declarative approach: one schema + one generic runner
skill (`workflow-chaining`). Adding a workflow = dropping a `.workflow.yaml` file;
no orchestration code is written.

### 5.2 `workflows/*.workflow.yaml` schema

```yaml
# Example: workflows/example-pipeline.workflow.yaml
name: example-pipeline
domain: qa                       # one of 9 persona buckets
team_pattern: Pipeline           # see §5.3 for all 6 patterns
description: |
  Generate and review an Odoo test suite from a feature spec.
  Trigger: "write tests for", "generate test suite", "QA for this feature".
output_dir: .odoo-ai/qa          # all artifacts land here
inputs: [feature_spec]           # named args collected at Phase 0

phases:
  - id: scaffold
    skill: odoo-coding
    nl_trigger: "write Odoo unit tests for the feature described"
    model_tier: sonnet
    gate: "yes / edit / cancel"

  - id: review
    skill: odoo-code-review
    nl_trigger: "review the generated test suite for correctness and Odoo conventions"
    model_tier: sonnet
    gate: "yes / iterate / cancel"

  - id: synthesize
    inline: true                 # runner handles this phase directly (no separate skill)
    model_tier: sonnet
    gate: "save / discard / cancel"

resume: true                     # writes .odoo-ai/qa/<slug>-state.json after each phase
fallback: standalone             # each phase documents OSM-down degradation inline
```

### 5.3 Field reference

| Field | Type | Purpose |
|-------|------|---------|
| `name` | string | Command name and state-file slug |
| `domain` | enum (9) | Persona bucket - drives `odoo-intake` tier-3 routing row |
| `team_pattern` | enum (6) | Execution shape - tells the runner how to orchestrate phases |
| `description` | string | NL text for tier-3 / NL-dispatch matching (no separate registration needed) |
| `output_dir` | string | `.odoo-ai/<subdir>/` path for all artifacts |
| `inputs[]` | string[] | Named args collected by the runner at Phase 0 |
| `phases[].id` | string | Phase identifier (used in state file and gate messages) |
| `phases[].skill` | string | Specialist skill fired by NL dispatch |
| `phases[].inline` | bool | Runner handles this phase itself (no separate skill) |
| `phases[].agent` | string | Agent-tool bundle (e.g. `odoo-code-reviewer`) for read-only passes |
| `phases[].nl_trigger` | string | NL prompt passed to NL-dispatch to fire the skill |
| `phases[].model_tier` | enum | `haiku / sonnet / opus` - Sonnet is the floor for write phases. (Agent-tool dispatches outside YAML workflows additionally know the `fable` tier - see `skills/_shared/concurrency-guard.md` Mode B.) |
| `phases[].gate` | string | Gate options shown to user between phases |
| `resume` | bool | Write `<slug>-state.json` after each phase for resume support |
| `fallback` | string | Degradation policy when the odoo-semantic-mcp server is unreachable |

### 5.4 Six team-patterns and runner behavior

| Pattern | Runner behavior | Layer/role |
|---------|-----------------|------------|
| **Pipeline** | Phases run sequentially; gate between each. Equivalent to existing command shape. | orchestrating → dispatched-specialist |
| **Fan-out / Fan-in** | A phase marked `fanout: true` with `chunk_by` splits input, fires N parallel `context: fork` workers (≤3 concurrent), then aggregates. Used by the BRL engine for chunk processing. | orchestrating → dispatched-specialist → leaf-worker |
| **Expert-Pool** | `phases[].when:` predicate selects which specialist fires per item (e.g. `check_module_exists` for Standard, `model_inspect` for Custom). | orchestrating → dispatched-specialist |
| **Producer-Reviewer** | Two phases: `produce` + `review`. The review phase uses `agent: odoo-code-reviewer` in read-only mode ("report, never fix"). | orchestrating → dispatched-specialist |
| **Supervisor** | An `inline` supervisor phase distributes sub-tasks via NL-dispatch and collects results. | orchestrating → dispatched-specialist |
| **Hierarchical** | A top phase decomposes into a generated `phases[]` list bounded to one decomposition level. | orchestrating → dispatched-specialist → leaf-worker (max) |

**Fan-out ceiling**: `context: fork` workers carry the hard-rules line
(`Do NOT invoke spawner skills via the Skill tool. Do NOT spawn sub-agents. You MAY use the Skill tool for read-only leaf skills (e.g. odoo-feature-check, odoo-override-finding). Only Read/Grep/Glob/Write/Bash.`)
and are capped at 3 concurrent workers (Mode A - see
`skills/_shared/concurrency-guard.md`, the SSOT for the OOM fan-out rule).

### 5.5 Registration and validation

The runner skill (`workflow-chaining`, `user-invocable: false`) auto-discovers
`*.workflow.yaml` from the `workflows/` directory. No `plugin.json` edit is needed
for the skill list.

Validation: `generator/check_workflows.py` validates each file against the schema
(required fields, enum values, skill names exist, `output_dir` under `.odoo-ai/`).
Wired into `make validate`.

---

## 6. Skill delegation rule

```
orchestrating context (main agent / run-harness / odoo-intake)
  └── dispatched-specialist (workflow skill / spawner-agent skill)
        └── leaf-worker (context: fork worker)                ← hard-rules line; no spawner-skill dispatch
        └── named interior agent (odoo-coder, odoo-code-reviewer, …)
              └── may spawn its own subagents (depth cap 5)
```

### Leaf vs spawn

A **leaf skill** (`spawn_class: leaf`) executes work directly using MCP tool calls and
Read/Write/Bash operations. It does NOT use the Agent tool and does NOT spawn workers.
Examples: `odoo-feature-check`, `odoo-gap-analysis`, `odoo-version-diff`, and the other
leaf specialists.

A **spawner-agent skill** (`spawn_class: spawner-agent`) runs in the orchestrating
context and dispatches a named agent via the **Agent tool**. Because it requires the
orchestrating context, it is itself launched via the **Skill tool** (by the main agent
or by an orchestrator like `run-harness`), never by Agent-tool'ing its name and never
by reading-and-imitating its SKILL.md. Examples: `odoo-code-review` (→ `odoo-code-reviewer`),
`odoo-coding` (→ `odoo-coder` / `odoo-frontend-coder`), `odoo-debug`, `odoo-solution-design`,
`odoo-ui-review`, `odoo-acceptance` (→ `odoo-qa-planner` / `odoo-qa-tester`).

A **spawn/orchestrator skill** orchestrates other skills or forks workers via `context: fork`.
Examples: `odoo-brl` (forks DAG cluster workers), `odoo-wave` (worktree fan-out + invokes
`odoo-coding` per WI), `odoo-intake` / `run-harness` / `workflow-chaining` (orchestrators that
dispatch specialists).

### Mandatory hard-rules line

Every `context: fork` subagent prompt MUST contain:

```
Do NOT invoke spawner skills via the Skill tool. Do NOT spawn sub-agents.
You MAY use the Skill tool for read-only leaf skills (e.g. odoo-feature-check, odoo-override-finding).
Only Read/Grep/Glob/Write/Bash.
```

Omitting this line risks an uncontrolled fan-out: a well-meaning worker that invokes a
*spawner* skill launches a fresh agent pipeline that wastes a depth level. Invoking a
genuine leaf skill (no agent dispatch) is fine and adds no depth.

### Dispatch method

The **orchestrating context** (main agent and orchestrators like `odoo-intake`,
`run-harness`) dispatches a target skill via the **Skill tool** - the canonical, deterministic
mechanism, and what lets a spawner skill (`odoo-code-review`, `odoo-coding`, …) actually RUN
its own orchestration in the main context. **NL description-match** (a prompt matching the
target skill's `description`) is the soft fallback.

The "no spawner-skill dispatch" restriction binds **`context: fork` fan-out workers** only:
a fork worker dispatching a spawner skill kicks off a fresh agent pipeline that wastes a depth
level and breaks fan-out isolation - hence the mandatory hard-rules line. Named interior agents
(e.g. `odoo-coder`, `odoo-code-reviewer`) ARE allowed to dispatch further agents or use the Skill
tool; the platform depth cap (5) is the hard guard. Commands dispatch via the Skill tool
(canonical) or NL description-match (fallback) - either is correct at the command level.

### Context-Handoff Protocol (CHP)

When an orchestrator skill dispatches worker agents in a loop (e.g. per-module coders,
per-commit extractors), it should apply the CHP to cut cold-start cost. The 3 tiers:

| Tier | Mechanism | When |
|------|-----------|------|
| A | `SendMessage`-resume - spawn once, resume the same worker per iteration | Capability probe positive: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` + `SendMessage` present + addressable worker + team lead |
| B | `subagent_type: "fork"` - inherits parent context + prompt cache | Read-heavy fan-outs where workers do not mutate shared state |
| C | Fresh spawn + worklog | Always correct; automatic fallback when Tier A/B is unavailable |

Tier C is the SSOT baseline. Tier A/B are optimizations; any path degrades silently to Tier C
without error. SSOT for all probe conditions, fallback rules, and async semantics:
`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md`.

The `handoff` field in `generator/skill_tool_deps.json` records the preferred tier per skill
(`send-message | fork | fresh`) and is surfaced as a column in `docs/reference/ORCHESTRATION-MAP.md`.

**Agent Team mode (send-message tier).** When the capability probe is positive (Tier A available),
the `send-message` tier now carries two extra obligations on top of resume-to-cut-cold-start: a
teammate-side completion-report obligation (each teammate PUSHES its result/Continuation Contract
to the lead via `SendMessage` to `main`, rather than the lead scraping it from the `.output`
transcript) and a lead-side task board (the lead TaskCreates one task per dispatched work-item,
injects `TASK_ID` + `REPLY_TO: main` + `NOTIFY: <dependent names>` into each teammate brief, and
polls `TaskList`/`TaskGet` for live status). The board carries low-context status; the push carries
result content. SSOT for both halves: `${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md`.

### Model-tier assignment

| Tier | When to use |
|------|-------------|
| `haiku` | Read-only lookup, classification, simple Q&A with no writes. NEVER for write phases or for multi-tool OSM synthesis (capability tables, feature verdicts) - use `sonnet` |
| `sonnet` | Write tasks, edits, single-file refactor, review - **floor for write phases** |
| `opus` | Cross-file reasoning, orchestration parent, DAG cluster reasoning - max 3 concurrent |

The BRL skill declares `model: opus` for the orchestrating skill body. Inner MCP
calls and leaf worker turns use the tier assigned in the chunk/phase declaration.

---

*This document is the SSOT for the workflow harness. When the artifact schema, gate
convention, or composition contract changes, update this file first and propagate to
referencing skills via the marker-block or direct reference.*

---

## 7. Git-wave orchestration (orchestrating context)

### 7.1 What it is

The `odoo-wave` skill is the **git-executor**: an INTERNAL, consume-only
(`user-invocable: false`) skill that `run-harness` dispatches per coding wave-layer of an APPROVED
plan. It lands multiple related work-item (WI) changes as one reviewed, squashed PR without ever
touching the principal branch directly. It does NOT choose agent/model and does NOT self-derive a
plan - it INVOKES `odoo-coding` per WI (which owns count+model) and consumes the plan's WI list +
wave-batched module-DAG + topology.

```
principal branch (untouched throughout)
  |
  +-- integration branch  (wave/integration-<slug>)
        |
        +-- WI-A worktree  (wave/wi-<slug>-a)  <- INVOKE odoo-coding (owns its own coder count+model)
        +-- WI-B worktree  (wave/wi-<slug>-b)  <- INVOKE odoo-coding
        +-- WI-C worktree  (wave/wi-<slug>-c)  <- INVOKE odoo-coding
              |
              (per WI, sequentially: cherry-pick A -> B -> C onto integration, verify + checkpoint)
              |
        end-of-wave cross-cutting review  (inline, orchestrating context)
              |
        odoo-code-review invoked inline from main context
              |
        1 PR  (integration -> principal)
              |
        squash + tree-identity verify  (backup ref + git diff --quiet)
              |
        STOP at the L2-squash-gate  (odoo-wave never merges)
              |
        merge + post-merge cleanup owned by odoo-pr-monitoring (L2-merge-gate)
```

### 7.2 Why odoo-wave is NOT a workflow-chaining team-pattern

This is the **authoritative decision record** for why the git-executor is an orchestrating-context
skill, not a `team_pattern` inside the declarative workflow system.

| Axis | workflow-chaining (dispatched-specialist) | odoo-wave skill (orchestrating context) |
|------|------------------------------------------|-------------------------------------|
| Git authority | None - runner does NL-dispatch only; no git ops | Delegates all git/github via the git-toolkit:git-ops skill (git-ops resolves to git-operator/git-surveyor/github-operator/git-pipeline-lead - worktree/cherry-pick/squash/force-with-lease, PR, review diff) |
| odoo-code-review legality | Cannot call odoo-code-review (self-spawn only legal from the orchestrating context) | Calls odoo-code-review inline from main context - the only legal call site |
| Per-WI work | n/a | INVOKES `odoo-coding` per WI via the Skill tool from the orchestrating context (legal - the spawner ban is leaf-only); odoo-coding owns count+model |
| State machine | Declarative phases in `.workflow.yaml`; runner executes them | Imperative phases encoded in the skill body; git refs/worktrees ARE the state |
| Coupling | Coupled to workflow schema; adding GitWave would require new `team_pattern: GitWave` + new runner branch + new yaml keys | Self-contained; no schema changes to existing runner or yaml format |
| Nesting risk | Injecting git orchestration into the workflow runner would push workers one depth level deeper (depth cap 5 platform-wide), leaving less headroom for interior spawns | odoo-wave sits at the orchestrating layer (depth 1-2); main -> odoo-wave -> odoo-coding -> coder stays within the depth cap |

**Decision**: the git-executor (`odoo-wave`) is an orchestrating-context actor dispatched by
`run-harness` per coding wave-layer, not a `team_pattern` below `workflow-chaining`. This is final
and must not be revisited without updating this section.

### 7.3 Phase sequence (summary)

| Phase | Action | Actor |
|-------|--------|-------|
| 0 - Safety verify (consume) | Consume the plan's WI list + module-DAG + topology; run the disjoint file-ownership safety audit; plan-staleness check. No plan-gate (approval is upstream at the driver L2 gate) | odoo-wave (orchestrating context) |
| 1 - Integration branch + worktrees | `git worktree add -b wave/wi-<slug>-X` from integration (dependents lazily) | git-toolkit:git-ops skill via odoo-wave |
| 2 - Per-WI: INVOKE odoo-coding | Per WI, sequentially INVOKE `odoo-coding` via the Skill tool (owns count+model); odoo-coding authors+commits in the provided worktree and returns SHA(s) | odoo-wave (Skill tool) -> odoo-coding |
| 3 - Cherry-pick + resolver (saga) | Cherry-pick A -> B -> C onto integration (serialized, verify + checkpoint after each); Sonnet resolver on conflict; saga rollback on unrecoverable failure | git-toolkit:git-ops skill via odoo-wave |
| 4 - End-of-wave review | Inline cross-cutting review (4.1) over the INTEGRATED tree, then `odoo-code-review` inline from main context (4.2) | odoo-wave (orchestrating context) |
| 5 - PR + squash + tree-identity -> STOP | Create 1 PR (integration -> principal); backup ref, squash to 1 commit, `git diff --quiet` vs backup; STOP at the L2-squash-gate | git-toolkit:git-ops skill via odoo-wave (PR + squash/verify) |
| (merge) | Merge + post-merge cleanup at the L2-merge-gate | `odoo-pr-monitoring` (NOT odoo-wave) |

### 7.4 The spawner ban is leaf-only - odoo-wave legally invokes odoo-coding

The spawner/orchestrator ban (a worker must not invoke a spawner skill or spawn a sub-agent) applies
to **LEAF workers only** - a leaf runs at the bottom of the depth budget and must not fan a fresh
pipeline out from under itself. `odoo-wave` is NOT a leaf: it runs in the orchestrating context that
holds git authority, so it **legally INVOKES `odoo-coding` per WI via the Skill tool** (and invokes
`odoo-code-review` inline in Phase 4). The leaves are `odoo-coding`'s own coders (`odoo-coder` /
`odoo-frontend-coder`), and THEY carry the ban - their system prompts forbid invoking a spawner skill
and forbid integration git ops; they author + commit inside their assigned worktree only
(`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`). A Phase-3 conflict resolver subagent is likewise a
leaf that edits files in the worktree and runs no git op.

This leaf-only boundary is what keeps the nesting chain (main -> odoo-wave -> odoo-coding -> coder)
within the platform depth cap. Removing it from the coder agents' system prompts is a hard-rules
violation.

### 7.5 Scaling + concurrency

odoo-wave is consume-only: the WI count and wave-batching are decided UPSTREAM by `odoo-planning`
(the canonical producer) and consumed here - odoo-wave makes no scaling decision and writes only a
run-local execution log to `.odoo-ai/wave/<slug>/`. Concurrency (the coder fan-out + the Mode-B OOM
budget) is owned INSIDE each `odoo-coding` invocation
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`, Mode B); odoo-wave invokes odoo-coding
per WI sequentially from its single orchestrating context and never sets a coder count or model.

### 7.6 Artifact location

Wave plan and state files land under `.odoo-ai/wave/<slug>/` (gitignored by
`odoo-onboarding`). The `<slug>` is a short kebab-case descriptor chosen at Phase 0.
The directory is cleaned up after a successful human-confirm merge.

---

## 8. Drive-to-done orchestration (Continuation Contract + run-harness)

The harness turns a one-shot `/odoo-intake "<NL>"` into a self-advancing run: intake plans a DAG,
`run-harness` (an orchestrating skill) walks it, each step emits a machine-readable **Continuation
Contract**, and the driver advances until DONE/BLOCKED/NEEDS_CONTEXT. This section is the SSOT
for that mechanism. **It is additive** - every existing skill/agent/workflow keeps its current
semantics; the only required change is appending a Continuation Contract block to each step's
output (back-compat: a legacy `SUGGESTED_NEXT:` line is read as a low-confidence contract).

**Load-bearing principle - NEVER hard-block the main agent.** No hook may `deny` a main-agent
tool call or `block` a main-agent turn-end. The main agent is the top decision-maker alongside
the human; coercing it is dangerous (it can trap the agent / deadlock the session). Main stays
an orchestrator through *structure + instruction + soft nudges*, never force. (`block` is only
ever applied to a **subagent/executor** as a quality gate, e.g. `enforce-grounding.sh`.)

### 8.1 North Star diagram

```
                       HUMAN
                         │  /odoo-intake "<NL>"  [--auto(default) | --step | --plan]
                         ▼
┌──────────────── ORCHESTRATING CONTEXT (MAIN = orchestrator + decision-maker ONLY) ────┐
│  odoo-intake-planner: Tier1 regex → Tier2 resume → Tier3 keyword(40) → Tier4 LLM      │
│     ├─ non-Odoo intent ─► route vault / other plugin / flag out-of-plugin (multi-plugin)│
│     └─ Odoo intent ─► Phase R recon (≤2 read-only) ─► Phase P emit RUN-DAG             │
│  present DAG ONCE ─► [Plan Mode gate if any writes-files node] ─► write run-<id>.json  │
│        │                                                                               │
│        ▼  run-harness (orchestrating skill) - DRIVER LOOP                               │
│   while RUN.status == NEEDS_NEXT and within budget:                                    │
│     node = pick_ready(DAG ∪ dynamic_nodes)         # topo-order; tie → confidence desc │
│     tier = resolve_gate(node)                      # --step raises floor, --auto lowers L1│
│       L2 → ALWAYS human gate ; L1 → auto-pass(--auto)/gate(--step) ; L0 → auto-pass    │
│     dispatch(node):  (3a) leaf skill INLINE (orchestrating context)                    │
│                      (3b) spawner skill → Skill tool → skill launches subagent          │
│                      (3c) workflow-chaining → fanout context:fork (leaf-workers)        │
│     read Continuation Contract ; update run-<id>.json ; materialize next[] → dynamic   │
│   stop ⇒ DONE | BLOCKED | NEEDS_CONTEXT  → report + evidence (Completion #8)           │
└────────────────────────────────────────────────────────────────────────────────────────┘
  HOOKS (self-gate to pass when no active run; NONE hard-blocks MAIN):
   • PreToolUse  remind-delegate  → main Write/Edit/Bash during active run ⇒ additionalContext
                 nudge "consider delegating" (permissionDecision=allow, never deny)
   • SubagentStop parse-continuation → subagent Contract NEEDS_NEXT ⇒ systemMessage nudge advance
                 (block applies ONLY to subagents as a quality gate, never to main)
   • Stop        drive-continuation → main ends turn while RUN==NEEDS_NEXT ⇒ systemMessage
                 advisory (continue=true, never block) - main keeps the right to stop
  blackboard .odoo-ai/run-<id>.json = SINGLE SOURCE (only run-harness writes); state on disk ⇒
  main context does not grow with run length.
```

**Node lifecycle:**

```
PENDING ─(all depends_on DONE)─► READY ─(driver picks + gate passes)─► RUNNING
   │                                                                     │
   │                                       Contract.status ──────────────┼─► DONE (produced[] = evidence)
   │                                                                     ├─► FAILED ─(retry<3)─► READY; (≥3)─► BLOCKED
   └─(when: predicate false)─► SKIPPED                                   └─► BLOCKED | NEEDS_CONTEXT ⇒ stop, ask human
```

### 8.2 Continuation Contract

Every skill/agent appends this fenced block at the **end** of its output (after its normal
artifact). It is the machine-readable handoff the driver reads to advance.

```continuation
status: DONE | NEEDS_NEXT | BLOCKED | NEEDS_CONTEXT
produced: [<real artifact path>, ...]      # evidence for Completion-status #8
next:                                       # [] unless status == NEEDS_NEXT
  - skill: <skill-or-workflow-name>
    reason: <why this is the next step>
    inputs: {<key>: <value>}
    confidence: 0.0..1.0                     # driver arbitration; <0.5 ⇒ not auto-materialized
    risk_level: L0 | L1 | L2
blocked_reason: <non-null iff status in {BLOCKED, NEEDS_CONTEXT}>
```

- **Parsing** reuses the transcript jq pipeline already in `hooks/enforce-grounding.sh`.
- **Back-compat:** a legacy `SUGGESTED_NEXT: <skill> (reason=…, target=…)` line maps to
  `next: [{skill, reason, confidence: 0.5, risk_level: L0}]` with `status: NEEDS_NEXT`. This
  lets the rollout be gradual - an un-migrated skill still drives at low confidence.
- **Nesting safety:** a subagent only *emits* a contract; it never dispatches. Advancing is the
  run-harness's job. fanout/WI leaf-workers emit contracts that bubble up to their
  dispatching orchestrator, never self-fire.

### 8.3 run-`<id>`.json blackboard

Single source of truth for one run, under `.odoo-ai/` (gitignored). **Only `run-harness`
writes it** (hooks never write - avoids a write race). Resume mirrors the BRL checkpoint
contract (§3.3): re-entry reads the file, skips `DONE` nodes, resumes at the first `READY`
node in topo-order.

**When Phase P engages (SSOT in `odoo-intake` § Phase P - restated here to avoid drift):** engage
(write this file + run the driver) if ANY of - (1) `node_count >= 2`; (2) a single
`output_mode == writes-files` node; (3) a single workflow node whose YAML declares
`on_complete`. Otherwise (single chat-only node, not a workflow-with-on_complete) dispatch
directly with no run file. The autonomy dial is NOT a trigger - it is only recorded here once
engaged. A workflow-command is ONE node (its phases are SSOT in the `.workflow.yaml`, never
expanded into WIs - see §4.6).

**Invariant - `on_complete` workflows are driver-required.** A workflow that declares
`on_complete` only *emits* `next[]`; only a `run-harness` dispatches it. Therefore such a
workflow MUST be entered through a driver: intake Phase P engages one automatically (trigger 3
above). A slash command whose workflow declares `on_complete` must likewise engage the driver
(write a 1-node `run-<id>.json` + invoke `run-harness`) instead of dispatching `workflow-chaining`
directly - otherwise the chain degrades to a human suggestion (workflow-chaining states this
when it detects no driver above it). `generator/check_workflows.py` WARNs if a command
references a driver-required workflow directly.

```json
{
  "run_id": "feature-x-20260607-a3f1",
  "schema_version": "run/1.0",
  "intent": "<verbatim user NL>",
  "autonomy": "auto | step | plan",
  "status": "NEEDS_NEXT | DONE | BLOCKED | NEEDS_CONTEXT",
  "cursor": "<next READY node id the driver will pick>",
  "budget": {"max_nodes": 12, "nodes_run": 3, "max_gate_l1_autopass": 20},
  "nodes": [
    {"id": "WI-A", "approach": "odoo-coding", "approach_kind": "skill|agent|workflow|inline",
     "inputs": {}, "depends_on": [], "gate_tier": "L1",
     "status": "PENDING|READY|RUNNING|DONE|FAILED|SKIPPED|BLOCKED",
     "produced": [], "contract": { /* last emitted continuation block */ }}
  ],
  "dynamic_nodes": [],          // nodes added at runtime from a Contract's next[]
  "gate_log": [{"node": "WI-A", "tier": "L1", "decision": "auto-pass"}],
  "completion": {"status": null, "evidence": [], "summary": null}
}
```

**Three coordination surfaces (no overlap).** A run coordinates over three distinct surfaces,
each answering a different question. (1) The **blackboard** above is the driver-only *DAG state
machine* (only `run-harness` writes it). (2) The **worklog** is an append-only *decision journal*
every participant (architect, test-author, coder, reviewer, debugger, odoo-wave WI worker) reads
before starting and writes when finishing, SSOT
`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`. It answers "*why* did the prior phase do
this" so a later phase builds on intent instead of re-deriving it. It is **one file per writer**
under `.odoo-ai/worklog/<run-or-slug>/<NNN>-<agent>.md` (per-writer files make parallel appends
race-free; the single blackboard only the driver touches). When a run is active the driver records
the worklog dir so all nodes resolve the same path; standalone, a skill derives it from its own
slug. (3) The **native task board** (`TaskCreate`/`TaskUpdate`/`TaskList`/`TaskGet`) is the
*live teammate-status* surface, present only in Agent Team mode (CHP Tier A): the lead opens one
task per dispatched work-item and polls it for low-context progress instead of reading each
teammate's `.output` transcript, SSOT `${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md`.
The three never duplicate: **task board = live status, worklog = why, blackboard = DAG.**

**Context-Handoff Protocol (CHP) - 3-tier agent dispatch.** Orchestrator skills that dispatch
worker agents (odoo-coding, odoo-code-review, odoo-wave, odoo-forward-port, odoo-deep-survey,
odoo-brl) use the CHP (§6) to cut cold-start cost. Tier C (fresh spawn + worklog) is the SSOT
baseline; Tier A/B are optimizations that degrade silently to C. CHP is an optimization layer,
never a dependency. SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md`.

**The `code -> review+test -> code` loop.** `odoo-coding` (which now orchestrates red-test authorship before the
code for non-trivial modules, SSOT `${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`) emits
`next: odoo-code-review`; that skill reviews AND checks test coverage, emitting `next: odoo-coding`
on a CRITICAL/HIGH fix or `next: odoo-test-writing` on an uncovered behavior. The driver advances
this loop via the Continuation Contract (a subagent never re-dispatches itself) and bounds it to 3
iterations before escalating - same bounded-iteration safety as every other chain here. When the
reviewed change touches a UI/behavior surface whose blast-radius reaches DEPENDENT modules (the
`render_check_set` widened per `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md` extends beyond the
changed modules) - or the rendered-UI dimension is left `DONE_WITH_CONCERNS` because no instance was
reachable - `odoo-code-review` (and `odoo-wave` Phase 4.3) additionally emit `next: odoo-acceptance` at
**L2 (opt-in, human-gated)**. It never auto-runs and never auto-blocks the review; the driver surfaces
it as the terminal acceptance gate, and `odoo-acceptance` then drives the independent oracle
(`odoo-qa-planner`) + live execution (`odoo-qa-tester`) over the affected cluster.

### 8.4 Gate-tier policy

`output_mode` and `default_gate_tier` are SSOT per-skill in
`generator/skill_tool_deps.json → orchestration.<skill>` (validated by `check_orchestration.py`,
which also enforces the derivation below). They replace the hardcoded chat-only lists (§4.1).

- **`output_mode`** - the authoritative runtime source is the explicit
  `orchestration.<skill>.output_mode` field in the registry (read that field; §4.7 row agrees).
  That field's **value was set per-skill from the skill's declared Output semantics - NOT
  derived from `stack`** (a backend/frontend-stack skill can be read-only: `odoo-version-diff`,
  `odoo-deprecation-audit`, `odoo-code-review`, `odoo-ui-review` are all `chat-only`).
  - `writes-files` → persists a file artifact (`.odoo-ai/…` or source) → **Plan Mode required**.
  - `chat-only` → emits to chat only → skip Plan Mode.
- **`default_gate_tier`** is derived deterministically from `(spawn_class, instance_touching,
  output_mode)`:
  - **L2** if `instance_touching` OR `spawn_class == spawner-wave` - irreversible / outward
    (touches an instance, git push/merge, sends to a third party). **ALWAYS human gate; the
    autonomy dial can never lower L2.**
  - **L1** else if `output_mode == writes-files` - writes internal files. Auto-pass under
    `--auto` within budget; gated under `--step`.
  - **L0** else - read-only / chat. Auto-pass.
- **Per-node override** lives in `run-<id>.json` (a node may raise its tier, e.g. a coder told
  to write outside `.odoo-ai/`), never in the registry.

### 8.5 Command / Skill / Agent - the three axes

These are three **different axes** with a one-way reference chain `Command → Skill → Agent`
(a DAG, no cycle - consistent with the rule that an agent never calls back into a skill).
There is no chicken-and-egg: the recipe (skill) is authored at design-time; the agent is
instantiated at run-time by the recipe.

| Concept | Axis | Nature | When |
|---|---|---|---|
| **Command** | Trigger | human-typed entry point; maps to a skill/workflow; holds no logic | runtime (human) |
| **Skill** | Expertise | knowledge + recipe/SOP (WHAT + method + how-it-must-run) | design-time |
| **Agent** | Executor | own context window + specific expertise + tools + model | run-time (per recipe) |

**Multi-phase, multi-model expertise** (e.g. research: broad haiku survey → deep sonnet dives
→ opus synthesis) is an *orchestrating skill + a workflow YAML*. The infra already supports it
(§5.4, `workflows/_schema.md`): `fanout: true` + `chunk_by` + per-phase `model_tier` +
`context: fork` (≤3 concurrent). The phase count is flexible - fewer or more than three.

**named-agent vs fanout-worker (decision rule):**
- Rich expertise + fixed tool-set + reused in many places → **named agent** (`agents/*.md`,
  model in frontmatter). E.g. `odoo-coder`.
- Homogeneous workers inside one fan-out phase → **anonymous fanout worker**, model controlled
  by the phase's `model_tier` (no named agent per model needed).

### 8.6 Main Agent Operating Contract

When a run is active (`.odoo-ai/run-<id>.json` exists with `status != DONE`), the main agent
keeps its context clean by acting as orchestrator + decision-maker only - three principles, in
priority order:

1. **Structure (primary):** the Contract + `run-<id>.json` are *summary* interfaces between
   steps; all heavy work (reading many files, coding, surveying) lives in subagent contexts.
   Main holds pointers + summaries → context does not grow with session length.
2. **Instruction:** during an active run, main should use only {AskUserQuestion, dispatch
   Agent/Skill, Read(run.json/Contract/plan/pointer), gate decisions}; Write/Edit/wide-Grep/
   build-Bash should be delegated.
3. **Soft nudge (advisory only):** the `remind-delegate` PreToolUse hook nudges (never denies);
   the `drive-continuation` Stop hook nudges (never blocks). **No hook hard-blocks main.** The
   accepted trade-off: occasionally the main agent needs a human "continue" rather than ever
   being trapped by a hook.
