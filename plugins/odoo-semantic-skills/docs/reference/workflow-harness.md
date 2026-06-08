# Workflow Harness — Reference

> **SSOT for the workflow harness architecture.**
> Skills, workflow files, and the BRL engine reference this document for schema
> definitions, gate conventions, and composition contracts.
> Design reference: internal architecture notes.

---

## Table of Contents

1. [Overview — three-layer architecture](#1-overview--three-layer-architecture)
2. [`.odoo-ai/` artifact convention](#2-odoo-ai-artifact-convention)
3. [BRL job schema](#3-brl-job-schema)
4. [Soft-plan-gate convention](#4-soft-plan-gate-convention)
   - [4.1 Plan mode and skills — what is and isn't possible](#41-plan-mode-and-skills--what-is-and-isnt-possible)
   - [4.2 Gate template](#42-gate-template)
   - [4.3 Enforcement stack](#43-enforcement-stack)
   - [4.4 BRL-specific gates](#44-brl-specific-gates)
   - [4.5 Phase R — Recon (read-only current-state survey)](#45-phase-r--recon-read-only-current-state-survey)
   - [4.6 Plan Mode Content Schema](#46-plan-mode-content-schema)
   - [4.7 Inventory discovery — hybrid SSOT rules](#47-inventory-discovery--hybrid-ssot-rules)
5. [Composition contract](#5-composition-contract)
6. [Skill delegation depth rule](#6-skill-delegation-depth-rule)
7. [Git-wave orchestration (depth-0)](#7-git-wave-orchestration-depth-0)
8. [Drive-to-done orchestration (Continuation Contract + run-driver)](#8-drive-to-done-orchestration-continuation-contract--run-driver)
   - [8.1 North Star diagram](#81-north-star-diagram)
   - [8.2 Continuation Contract](#82-continuation-contract)
   - [8.3 run-<id>.json blackboard](#83-run-idjson-blackboard)
   - [8.4 Gate-tier policy](#84-gate-tier-policy)
   - [8.5 Command / Skill / Agent — the three axes](#85-command--skill--agent--the-three-axes)
   - [8.6 Main Agent Operating Contract](#86-main-agent-operating-contract)

---

## 1. Overview — three-layer architecture

The workflow harness is organized in three layers. Every workflow lives in exactly
one layer; cross-layer calls travel top-down only and never skip a layer.

```
┌────────────────────────────────────────────────────────────────┐
│  ENTRY / INTAKE LAYER  (depth 0)                                │
│  intake skill — domain-agnostic front door                      │
│  · Phase 0: 4-tier routing + intent gate (mandatory)           │
│  · Phase R: read-only Recon (≤1–2 agents, depth-1, no writes)  │
│  · Proposed Plan + soft-plan-gate                               │
│  · Plan Mode (EnterPlanMode/ExitPlanMode) for writes-files      │
│  · gate is BEHAVIORAL (Iron Law) + Plan Mode — not a write-block │
└───────────────────────────────────┬────────────────────────────┘
                                    │ NL-dispatch (never Skill tool)
                                    ▼
┌────────────────────────────────────────────────────────────────┐
│  WORKFLOW LAYER  (depth 0 → 1)                                  │
│  Declarative *.workflow.yaml + workflow-chaining skill            │
│  · maps one of 6 team-patterns to a gated phase sequence        │
│  · phase gates: approve / refine / cancel between phases        │
│  · writes .odoo-ai/<output_dir>/ artifacts                      │
│  Monolithic skills (odoo-brl) also live here                    │
└───────────────────────────────────┬────────────────────────────┘
                                    │ NL-dispatch or context: fork (≤3)
                                    ▼
┌────────────────────────────────────────────────────────────────┐
│  EXECUTION LAYER  (depth 1, max depth 2 for fork workers)       │
│  Specialist skills (odoo-coding, odoo-code-review, …)          │
│  MCP tool calls (odoo-semantic-mcp server)                      │
│  context: fork subagents — carry hard-rules line, no spawn      │
└────────────────────────────────────────────────────────────────┘
```

**Two invariants enforced across every workflow:**

- **1-orchestration-SSOT**: orchestration logic lives in one place — either a
  `*.workflow.yaml` file or a monolithic skill body. It is never duplicated between
  a command shim and a skill body.
- **Depth-2 ceiling**: the call stack is at most
  `main-context → workflow/skill (depth 1) → fork-worker (depth 2)`.
  Fork workers carry the hard-rules line and never spawn further agents or invoke
  the Skill tool.

---

## 2. `.odoo-ai/` artifact convention

`.odoo-ai/` is gitignored by the onboarding skill (`/odoo-onboarding`). All runtime
artifacts are written here; nothing under `.odoo-ai/` is committed to the repo.

### File-ownership table

| Component | Sub-path | Written by |
|-----------|----------|------------|
| Context snapshot | `.odoo-ai/context.md` | `odoo-onboarding` skill |
| Brainstorm state | `.odoo-ai/brainstorm/state.json` | `intake` skill |
| Brainstorm design doc | `.odoo-ai/brainstorm/<slug>-<date>.md` | `intake` (approval turn) |
| BRL job artifacts | `.odoo-ai/brl/<job-id>/` | `odoo-brl` skill |
| Workflow phase state | `<output_dir>/<slug>-state.json` (output_dir is the full `.odoo-ai/...` path) | `workflow-chaining` |
| QA artifacts | `.odoo-ai/qa/` | `qa-suite` workflow |
| Wave plan artifact | `.odoo-ai/wave/<slug>/` | `wave` skill (depth-0) |

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
  cache.json             # module-verdict cache (key → MCP response) — avoids duplicate calls
  results.jsonl          # merged final RTM (1 obj/line, machine-readable SSOT)
  rtm.csv                # consultant export (Excel-ready)
  dag.json               # {nodes, edges, topological_order, phases, critical_path}
  dag.mermaid            # flowchart TD by implementation phase
  cost.json              # project-level cost roll-up
  report.md              # executive human-readable summary
  errors.jsonl           # per-item failures (license-restricted, MCP error, unmapped)
                         # informational only — does not block the batch
```

### 3.2 manifest.json

Written once at job creation (Phase 0 — ingest). Never mutated after Gate 0 approval.

```json
{
  "job_id": "Customer-A-20260531-9f3a",
  "created_at": "2026-05-31T10:00:00Z",
  "customer_label": "Customer-A",
  "odoo_version": "17.0",
  "profiles": {"odoo": "odoo_17", "viindoo": "viindoo_internal_17"},
  "total_reqs": 1000,
  "chunk_size": 50,
  "cost_config_ref": "cost-config.json@v1",
  "rate_region": "vn",
  "risk_profile": "medium",
  "schema_version": "brl/1.0"
}
```

### 3.3 checkpoint.json — resume contract

Updated after every completed chunk. Resume reads `last_completed_chunk` and enters
the outer loop at `last_completed_chunk + 1`. Re-running a chunk overwrites its
`chunk-NNN.*.jsonl` files — the operation is idempotent.

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
`per_req` is sparse — only in-flight items appear; completed items are omitted.

### 3.4 results.jsonl — one object per requirement (RTM SSOT)

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

### 3.5 rtm.csv — header

```
req_id,req_text,req_category,priority,classification,module,edition,effort_tier,
effort_days_min,effort_days_max,cost_usd_min,cost_usd_max,dependencies,impl_phase,
evidence_module,evidence_field,risk_flag,status,notes
```

`dependencies` is pipe-joined (`REQ-0010|REQ-0015`) to remain CSV-safe.

### 3.6 cost.json — project-level roll-up

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

### 3.7 dag.json — dependency graph

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
Technical edges come from `module_inspect(method='dependencies', odoo_version='auto')` (deterministic).  
Business-logic and data-flow edges come from Opus cluster reasoning.

---

## 4. Soft-plan-gate convention

### 4.1 Plan mode and skills — what is and isn't possible

Skills, commands, and hooks **cannot declaratively set** `permission_mode=plan` in
their frontmatter or configuration. User-initiated plan mode (Shift+Tab, `/plan`, CLI
flag, `defaultMode` in settings) is separate from anything a skill can declare.

However, this does **not** mean plan mode is unreachable from within a skill-driven
flow:

- **Main agent (depth-0) CAN call `EnterPlanMode` / `ExitPlanMode`** — these are
  platform tools available to the main context. A skill running at depth-0 (e.g.,
  `intake`) may instruct the main agent to invoke `EnterPlanMode` before any
  file-touching execution, producing genuine UI-approved Plan Mode — a stronger
  enforcement than a text gate.
- **Subagents cannot call `EnterPlanMode`** — the tool is only reachable from the
  main context. `ExitPlanMode` is only available to a subagent whose `permissionMode`
  is already `plan`.

#### Plan Mode decision tree

Run this before any execute-skill dispatch. Intake reads the chosen Approach's
`output_mode` (resolved via Phase R inventory discovery — §4.7):

- `output_mode = writes-files` → **Plan Mode is REQUIRED**. Proceed through the full
  EnterPlanMode → content schema → ExitPlanMode procedure (see §4.6).
- `output_mode = chat-only` → **SKIP Plan Mode**. Intake ends its turn; the specialist
  fires via the Agent tool on the next turn (NL-dispatch). Chat-only skills include:
  `odoo-feature-check`, `odoo-version-diff`, `odoo-risk-overview`,
  `odoo-deprecation-audit`, `odoo-gap-analysis`, `odoo-discovery-summary`,
  `odoo-capability-proof`, `odoo-objection-handling`, `odoo-content-draft`,
  `odoo-competitive-brief`, and any skill whose output column is "chat only".
  > **SSOT note:** the authoritative `output_mode` now lives per-skill in
  > `generator/skill_tool_deps.json` → `orchestration.<skill>.output_mode` (see §8.4).
  > The inline list above is a convenience snapshot; once intake reads the registry field
  > directly (P3), this list is removed in favour of the field. Until then both agree —
  > the field is a superset that preserves every skill listed here.

#### Intake-initiated Plan Mode pattern

When a depth-0 skill (`intake`) reaches the execute phase after the user approves a
Proposed Plan and the Approach `output_mode = writes-files`, the main agent calls
`EnterPlanMode` → writes the implementation plan (see §4.6 Content Schema) for UI
review → receives user approval via `ExitPlanMode` → then dispatches the
file-touching specialist. This is a first-class enforcement option, not a workaround.

There is **no platform write-block** behind the gate. `intake` does not declare
`disallowed-tools: Write Edit`, and the coders (`odoo-coding`)
DO write/apply code — that is their job. The gate is enforced by two behavioral
mechanisms, with Plan Mode as the strongest layer when depth-0 context is available:

1. **Iron Law** in the skill body — behavioral: "no execution fires until the user
   has approved a Proposed Plan". Paired with a Red Flags table listing rationalizations
   the agent must refuse (e.g., "This is simple, I'll just start coding" → STOP).
2. **Coder preview-then-write** — before mutating a file a coder previews the proposed
   patch in its turn; the write follows the same turn once the approach is settled.
   This is a discipline, not a tool restriction.

For skills that **cannot** rely on depth-0 context (e.g., skills invoked from inside
a subagent), the behavioral Iron Law gate (mechanism 1) is the fallback when
`EnterPlanMode` is not available; it is not the only option.

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
| Behavioral | Iron Law + Red Flags in skill body | Blocks writes-files dispatch until plan approved |
| Coder discipline | Preview patch, then write in-turn | Coders apply code; no platform write-block |
| Recon boundary | Phase R agents: read-only, depth-1, no spawn, no writes | Allows current-state survey without breaching gate |
| Plan Mode | `EnterPlanMode` / `ExitPlanMode` | Harness-level enforcement before writes-files execution |
| Approval | `intake` ends turn; next user prompt enables writes | Write unlock |
| Refine loop | Gate loops inside brainstorm; no writes until `approve` | Iteration |

On `approve` (text gate) + Plan Mode approved (harness level): the specialist fires
via the Agent tool (writes-files path). For chat-only Approaches, Plan Mode is skipped
and the specialist fires immediately on the next turn.  
On `refine: [feedback]`: the brainstorm loop continues within the current turn.  
On `cancel`: the skill stops and reports.

**What intake CAN do before the gate closes**: Phase R read-only Recon — dispatching
≤1–2 read-only agents (Explore or read-only specialists) and calling read-only OSM
tools (`model_inspect`, `check_module_exists`, `find_override_point`, `impact_analysis`).
Recon is depth-1, no file writes, no sub-agent spawning. This is NOT a breach of the
gate; it feeds into the Proposed Plan's Findings (Recon) field.

### 4.4 BRL-specific gates

The BRL engine has two gates (not one per chunk — that would break UX at 20 chunks):

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

### 4.5 Phase R — Recon (read-only current-state survey)

Phase R is a **formal stage** in the intake 5-phase flow that runs **after** Phase 0
closes the intent gate and **before** the Proposed Plan is written. Its purpose is to
turn a generic plan into a context-aware one — surveying what already exists rather
than guessing.

#### Position in the 5-phase flow

```
Phase 0 (Context, Detect & Clarify — closes intent/purpose/outcomes gate)
    ↓
Phase R (Recon — read-only current-state survey)   ← NEW formal stage
    ↓
Proposed Plan  (context-rich, informed by Recon findings)
    ↓
Plan Mode  (EnterPlanMode → Content Schema → ExitPlanMode)
    ↓
Execute  (writes-files specialist dispatched via Agent tool)
```

#### What Phase R does

- **Dispatches ≤1–2 READ-ONLY agents** via the Agent tool: `Explore`, or a specialist
  in read-only mode (e.g. `odoo-feature-check`, `odoo-override-finding`). These agents
  map the code or modules relevant to the stated intent.
- **Calls read-only OSM tools** as needed: `model_inspect`, `check_module_exists`,
  `find_override_point`, `impact_analysis`.
- **Never mutates** the filesystem. No `Write`, no `Edit`, no writes-files specialist.

#### Hard limits for Phase R agents

| Constraint | Rule |
|------------|------|
| Depth | depth-1 (one hop from main context; these agents are leaves) |
| Nesting | Recon agents MUST NOT spawn further sub-agents |
| File writes | PROHIBITED — Read/Grep/Glob/Bash (read-only) only |
| OSM | Read-only calls allowed; if unreachable, fall back to disk (Read/Grep the local repo, WebFetch upstream source) per `disk-fallback-protocol.md` |
| Count | ≤1–2 agents per Recon; not a fan-out pipeline |

The nesting guard is described in full at
`${CLAUDE_PLUGIN_ROOT}/snippets/nesting-guard.md`. Every Recon agent brief MUST
include the mandatory hard-rules line from §6 (adapted to read-only: no Write/Edit,
no Skill tool, no sub-agent spawn).

#### Rationale

Without Phase R, intake writes a Proposed Plan based only on user descriptions — it
cannot confirm which modules exist, what the current hook points are, or what the
blast radius of a change would be. Phase R answers these questions cheaply (read-only,
depth-1) so the Proposed Plan's `Findings (Recon)` field is concrete rather than
speculative. This is the same principle as `odoo-override-finding` confirming a hook
before `odoo-coding` writes the override.

---

### 4.6 Plan Mode Content Schema

When `output_mode = writes-files` (see decision tree in §4.1), the implementation
plan written inside Plan Mode (step 3 of the EnterPlanMode procedure) MUST contain
three blocks. None is optional.

#### Block 1 — Workitem list

Borrow the WI-Brief shape from `skills/wave/SKILL.md` (~lines 174–219) and/or the
requirement shape in `odoo-brl/reference/schema.md` (~lines 116–197). Each WI carries:

- `id` — short identifier (WI-A, WI-B, …)
- one-line description of what changes
- `files-in-scope` — the set of files this WI owns

**File-ownership invariant**: the `files-in-scope` sets across all WIs MUST be
**disjoint**. No two WIs may claim the same file. For multi-WI deliveries also note:
worktree name, branch name, and verify command (from the Repo Capability Card).

**Shared-file case (e.g. a form-view XML that a backend WI adds a `<field>` to and a frontend
WI adds a `widget=` attribute to):** do NOT split one file across two WIs — that breaks the
invariant. Resolve one of two ways: (a) collapse the XML edit into the backend WI (it adds both
the field and the `widget=`), leaving the frontend WI to own only the JS/OWL/SCSS files; or
(b) keep it one WI if the change is small. Disjointness is per-file, never per-node-within-a-file.

**Workflow-as-node:** a WI whose approach is a workflow-command is **one WI**, with
`files-in-scope` = the workflow's `output_dir/`. Do NOT expand the workflow's internal phases
into separate WIs (they are SSOT in the `.workflow.yaml` and share the output_dir, which would
break disjointness), and do NOT redraw the workflow's internal phase-sequence in Block 2 — the
workflow is a single node that may carry edges to OTHER WIs.

#### Block 2 — Dependency graph

For deliveries with a small number of WIs, pick **one of the four topologies** from
`wave/reference/wave-templates.md` (~lines 29–92):

| Topology | When to use |
|----------|-------------|
| `independent` | WIs have no ordering constraint; can run in parallel |
| `linear` | Each WI depends on the previous (strict chain) |
| `mixed` | Some WIs parallel, some sequential |
| `diamond` | Two parallel WIs converge into a final WI |

For deliveries with many WIs, use the full **DAG schema** from
`odoo-brl/reference/schema.md` (~lines 316–385): `nodes` + `edges` where each edge
carries:

```json
{
  "from": "WI-A",
  "to": "WI-B",
  "type": "technical | business-logic | data-flow",
  "reason": "one-line rationale"
}
```

Also include: `topological_order` (Kahn's algorithm), `critical_path`, and `cycles`
(must be empty `[]` for a valid DAG — a cycle is reported, never silently dropped).
A mermaid diagram is encouraged.

#### Block 3 — Assignment

One line per WI:

```
WI-X → <skill | command | agent>  (model: <from frontmatter>, effort: <S|M|L|XL>)
```

Also include per-WI:
- **acceptance criteria** — observable signal that the WI is done
- **verify command** — runnable command from the Repo Capability Card

`model` is read from the candidate's `SKILL.md` or `agents/*.md` frontmatter
(`model:` field) — never guessed or hard-coded in the plan. `effort` follows the
gap-analysis legend: **S = <1 day · M = 1–3 days · L = 3–10 days · XL = >10 days**.

#### Short examples

```
# Full-stack feature (1 WI — odoo-coding sequences both stacks internally)
WI-A → odoo-coding (sonnet, M)        adds backend field + ORM method, THEN renders OWL widget
  (odoo-coding runs the backend agent first so the field exists before the widget binds)
Verify: ./run_tests.sh sale_order

# Three disjoint fixes (independent, candidate for wave)
WI-A → odoo-coding (sonnet, S)        bug fix in account_move
WI-B → odoo-coding (sonnet, S)        unit test for WI-A
WI-C → (inline edit) (sonnet, S)     docs update (sonnet: docs update is a write phase)
DAG: independent (no edges) → hand to `wave` for parallel delivery
```

---

### 4.7 Inventory discovery — hybrid SSOT rules

When Phase R or plan-writing needs to know which skills, agents, or commands exist
and their runtime attributes, pull each fact from its **single source of truth**.
Do NOT copy fields between sources — duplication creates drift.

| Attribute | SSOT | How to fetch |
|-----------|------|--------------|
| skill/agent/command **exists** + its description | Runtime context (harness-injected by the platform) | Already available — do NOT read files for this |
| `model_tier` (Haiku / Sonnet / Opus / inherit) | `model:` field in the candidate's `SKILL.md` or `agents/*.md` frontmatter | Read the frontmatter of the **chosen candidate only** at plan time |
| `output_mode` (`chat-only` ↔ `writes-files`) | the explicit `output_mode` field in `skill_tool_deps.json` → `orchestration.<skill>` | Read that field directly. Its value was set per-skill from the skill's declared Output semantics — NOT crudely derived from `stack` (a backend/frontend-stack skill can be read-only/chat-only) |
| `effort` (S / M / L / XL) | NOT registered — it is a skill × task property | Reason per the `odoo-gap-analysis` legend: S <1d · M 1–3d · L 3–10d · XL >10d |

**Key invariants:**

- `model_tier` lives in frontmatter and MUST NOT be copied into any registry or plan
  as a constant. Read it fresh at plan time from the candidate's own SKILL.md.
- `effort` is per-task, not per-skill. Two invocations of the same skill can have
  different effort tiers depending on scope.
- `output_mode` is the only attribute whose SSOT is the registry — the explicit
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
| `domain` | enum (9) | Persona bucket — drives `intake` tier-3 routing row |
| `team_pattern` | enum (6) | Execution shape — tells the runner how to orchestrate phases |
| `description` | string | NL text for tier-3 / NL-dispatch matching (no separate registration needed) |
| `output_dir` | string | `.odoo-ai/<subdir>/` path for all artifacts |
| `inputs[]` | string[] | Named args collected by the runner at Phase 0 |
| `phases[].id` | string | Phase identifier (used in state file and gate messages) |
| `phases[].skill` | string | Specialist skill fired by NL dispatch |
| `phases[].inline` | bool | Runner handles this phase itself (no separate skill) |
| `phases[].agent` | string | Agent-tool bundle (e.g. `odoo-code-reviewer`) for read-only passes |
| `phases[].nl_trigger` | string | NL prompt passed to NL-dispatch to fire the skill |
| `phases[].model_tier` | enum | `haiku / sonnet / opus` — Sonnet is the floor for write phases |
| `phases[].gate` | string | Gate options shown to user between phases |
| `resume` | bool | Write `<slug>-state.json` after each phase for resume support |
| `fallback` | string | Degradation policy when the odoo-semantic-mcp server is unreachable |

### 5.4 Six team-patterns and runner behavior

| Pattern | Runner behavior | Depth |
|---------|-----------------|-------|
| **Pipeline** | Phases run sequentially; gate between each. Equivalent to existing command shape. | 0 → 1 |
| **Fan-out / Fan-in** | A phase marked `fanout: true` with `chunk_by` splits input, fires N parallel `context: fork` workers (≤3 concurrent), then aggregates. Used by the BRL engine for chunk processing. | 0 → 1 → 2 |
| **Expert-Pool** | `phases[].when:` predicate selects which specialist fires per item (e.g. `check_module_exists` for Standard, `model_inspect` for Custom). | 0 → 1 |
| **Producer-Reviewer** | Two phases: `produce` + `review`. The review phase uses `agent: odoo-code-reviewer` in read-only mode ("report, never fix"). | 0 → 1 |
| **Supervisor** | An `inline` supervisor phase distributes sub-tasks via NL-dispatch and collects results. | 0 → 1 |
| **Hierarchical** | A top phase decomposes into a generated `phases[]` list bounded to one decomposition level — no recursion past depth 2. | 0 → 1 → 2 (max) |

**Fan-out ceiling**: `context: fork` workers carry the hard-rules line
(`Do NOT invoke Skill tool. Do NOT spawn sub-agent. Only Read/Grep/Glob/Write.`)
and are capped at 3 concurrent workers to avoid OOM (see failure log
`unbounded-opus-fanout-oom`).

### 5.5 Registration and validation

The runner skill (`workflow-chaining`, `user-invocable: false`) auto-discovers
`*.workflow.yaml` from the `workflows/` directory. No `plugin.json` edit is needed
for the skill list.

Validation: `generator/check_workflows.py` validates each file against the schema
(required fields, enum values, skill names exist, `output_dir` under `.odoo-ai/`).
Wired into `make validate`.

---

## 6. Skill delegation depth rule

```
main context (depth 0)
  └── workflow skill / intake  (depth 1)
        └── context: fork worker        (depth 2, ceiling)
              └── NO further spawn. Hard-rules line mandatory.
```

### Leaf vs spawn

A **leaf skill** executes work directly using MCP tool calls and Read/Write/Bash
operations. It does NOT invoke the Skill tool, does NOT use the Agent tool, and does
NOT spawn `context: fork` workers. Examples: `odoo-coding`, `odoo-code-review`,
all 26 specialist skills.

A **spawn skill** orchestrates leaf skills by NL-dispatch or forks workers via
`context: fork`. Examples: `odoo-brl` (forks DAG cluster workers), `intake`
(NL-dispatches to specialists), `workflow-chaining` (phases mapped to leaf skills).

### Mandatory hard-rules line

Every `context: fork` subagent prompt MUST contain:

```
Do NOT invoke Skill tool. Do NOT spawn sub-agent.
Only Read/Grep/Glob/Write/Bash.
```

Omitting this line is a depth-2 violation risk: a well-meaning worker that invokes
a skill creates depth 3, which exceeds the platform ceiling.

### Dispatch method

All cross-skill dispatch uses **NL description-match** (natural-language prompt that
matches the target skill's `description`). The Skill tool is never used inside a
running skill or workflow. This is the pattern used by all 5 existing command files
and must be preserved in new workflows.

### Model-tier assignment

| Tier | When to use |
|------|-------------|
| `haiku` | Read-only lookup, classification, simple Q&A with no writes. NEVER for write phases or for multi-tool OSM synthesis (capability tables, feature verdicts) - use `sonnet` |
| `sonnet` | Write tasks, edits, single-file refactor, review — **floor for write phases** |
| `opus` | Cross-file reasoning, orchestration parent, DAG cluster reasoning — max 3 concurrent |

The BRL skill declares `model: opus` for the orchestrating skill body. Inner MCP
calls and leaf worker turns use the tier assigned in the chunk/phase declaration.

---

*This document is the SSOT for the workflow harness. When the artifact schema, gate
convention, or composition contract changes, update this file first and propagate to
referencing skills via the marker-block or direct reference.*

---

## 7. Git-wave orchestration (depth-0)

### 7.1 What it is

The `wave` skill is a **depth-0 git orchestrator** that lands multiple related
work-item (WI) changes as one reviewed, squashed PR without ever touching the
principal branch directly.

```
principal branch (untouched throughout)
  |
  └── integration branch  (wave/integration-<slug>)
        |
        ├── WI-A worktree  (wave/wi-<slug>-a)  ← Sonnet subagent, leaf depth-2
        ├── WI-B worktree  (wave/wi-<slug>-b)  ← Sonnet subagent, leaf depth-2
        └── WI-C worktree  (wave/wi-<slug>-c)  ← Sonnet subagent, leaf depth-2
              |
              (cherry-pick A → B → C onto integration)
              |
        end-of-wave Opus review  (inline, depth-0)
              |
        /code-review invoked inline from main context (depth-0)
              |
        1 PR  (integration → principal)
              |
        squash + tree-identity verify  (backup ref + git diff --quiet)
              |
        HUMAN-CONFIRM MERGE  (mandatory stop — never auto-merge)
              |
        cleanup: worktrees + branches + wave dir removed
```

### 7.2 Why wave is NOT a workflow-chaining team-pattern

This is the **authoritative decision record** for why git-wave is a depth-0 skill,
not a `team_pattern` inside the declarative workflow system.

| Axis | workflow-chaining (depth-1) | wave skill (depth-0) |
|------|--------------------------|----------------------|
| Depth | Runs at depth 1; fork workers are depth-2 ceiling | Runs at depth 0; WI subagents are depth-2 ceiling |
| Git authority | None — runner does NL-dispatch only; no git ops | Full git authority: worktree add, cherry-pick, PR creation, squash, force-with-lease |
| /code-review legality | Cannot call /code-review (self-spawn only legal at depth-0) | Calls /code-review inline from main context (depth-0) — the only legal call site |
| State machine | Declarative phases in `.workflow.yaml`; runner executes them | Imperative phases (0-6) encoded in the skill body; git refs/worktrees ARE the state |
| Coupling | Coupled to workflow schema; adding GitWave would require new `team_pattern: GitWave` + new runner branch + new yaml keys | Self-contained; no schema changes to existing runner or yaml format |
| Crash risk | Injecting git orchestration into depth-1 runner would push fork workers to depth-3 — exceeds platform ceiling | Depth ceiling respected: 0 (wave) → 2 (WI subagent) |

**Decision**: git-wave is a depth-0 actor that sits alongside `intake` at the top
layer, not below `workflow-chaining`. This is final and must not be revisited without
updating this section.

### 7.3 Phase sequence (summary)

| Phase | Action | Actor |
|-------|--------|-------|
| 0 — Discovery + plan gate | Read repo capability, draft WI ownership map, emit plan gate | wave (depth-0) |
| 1 — Integration branch + worktrees | `git worktree add -b wave/wi-<slug>-X` from integration | wave (depth-0) |
| 2 — Dispatch WI subagents | Parallel Sonnet subagents; each carries Phase-4 brief + nesting line | WI workers (depth-2) |
| 3 — Cherry-pick + resolver | Cherry-pick A → B → C onto integration; Sonnet resolver if conflict | wave (depth-0) |
| 4 — End-of-wave review | Inline Opus review (4.1) for plan-adherence + correctness, then `/code-review` invoked inline from main context (4.2) | wave (depth-0) |
| 5 — PR + squash + tree-identity | Create 1 PR (integration → principal); backup ref, squash to 1 commit, `git diff --quiet` vs backup | wave (depth-0) |
| 6 — Human-confirm merge + cleanup | STOP and wait for explicit user approval before merge; remove worktrees/branches/wave dir after | human + wave (depth-0) |

### 7.4 Nesting rule for WI subagents (leaf depth-2)

Every WI subagent brief MUST contain the following line verbatim:

```
You are a leaf worker (depth-2). You ARE the specialist — write/review the code yourself,
grounding every Odoo claim with the OSM MCP tools (an MCP tool call is never a spawn, so it is
always allowed); follow the odoo-coding / odoo-code-review conventions
but do NOT invoke those bundles. Do NOT invoke any depth0-only skill (odoo-coding,
odoo-code-review, odoo-ui-review, wave, intake, odoo-brl,
workflow-chaining, /code-review, skill-creator) — they dispatch a fresh agent and are
main-agent-only. You MAY NL-dispatch a genuinely non-spawning (leaf) skill (e.g.
odoo-feature-check, odoo-override-finding) for a read-only lookup. Do NOT invoke the Skill tool
to trigger a spawner. Do NOT spawn a sub-agent. Do NOT git branch/cherry-pick/merge/push; stay
in your assigned worktree. Only Read/Grep/Glob/Edit/Write/Bash.
```

This line is the boundary that prevents depth-3 violations. Omitting it is a
hard-rules violation in the wave skill.

### 7.5 Scaling rule

| WI count | Action |
|----------|--------|
| 1 WI | Minimal — skip integration branch; dispatch single worktree; squash still applies |
| 2-3 WI | Standard — use integration branch + plan gate before dispatch |
| >=4 WI | Full plan artifact required: `.odoo-ai/wave/<slug>/plan.md` (topology + DAG + model-tier per WI) before any worktree is created |

Maximum 3 concurrent WI subagents (OOM ceiling).

### 7.6 Artifact location

Wave plan and state files land under `.odoo-ai/wave/<slug>/` (gitignored by
`odoo-onboarding`). The `<slug>` is a short kebab-case descriptor chosen at Phase 0.
The directory is cleaned up after a successful human-confirm merge.

---

## 8. Drive-to-done orchestration (Continuation Contract + run-driver)

The harness turns a one-shot `/intake "<NL>"` into a self-advancing run: intake plans a DAG,
`run-driver` (a depth-0 skill) walks it, each step emits a machine-readable **Continuation
Contract**, and the driver advances until DONE/BLOCKED/NEEDS_CONTEXT. This section is the SSOT
for that mechanism. **It is additive** — every existing skill/agent/workflow keeps its current
semantics; the only required change is appending a Continuation Contract block to each step's
output (back-compat: a legacy `SUGGESTED_NEXT:` line is read as a low-confidence contract).

**Load-bearing principle — NEVER hard-block the main agent.** No hook may `deny` a main-agent
tool call or `block` a main-agent turn-end. The main agent is the top decision-maker alongside
the human; coercing it is dangerous (it can trap the agent / deadlock the session). Main stays
an orchestrator through *structure + instruction + soft nudges*, never force. (`block` is only
ever applied to a **subagent/executor** as a quality gate, e.g. `enforce-grounding.sh`.)

### 8.1 North Star diagram

```
                       HUMAN
                         │  /intake "<NL>"  [--auto(default) | --step | --plan]
                         ▼
┌──────────────── DEPTH 0 (MAIN = orchestrator + decision-maker ONLY) ─────────────────┐
│  intake-planner: Tier1 regex → Tier2 resume → Tier3 keyword(40) → Tier4 LLM           │
│     ├─ non-Odoo intent ─► route vault / other plugin / flag out-of-plugin (multi-plugin)│
│     └─ Odoo intent ─► Phase R recon (≤2 read-only) ─► Phase P emit RUN-DAG             │
│  present DAG ONCE ─► [Plan Mode gate if any writes-files node] ─► write run-<id>.json  │
│        │                                                                               │
│        ▼  run-driver (NEW skill, orchestrator-nl, depth0-only) — DRIVER LOOP           │
│   while RUN.status == NEEDS_NEXT and within budget:                                    │
│     node = pick_ready(DAG ∪ dynamic_nodes)         # topo-order; tie → confidence desc │
│     tier = resolve_gate(node)                      # --step raises floor, --auto lowers L1│
│       L2 → ALWAYS human gate ; L1 → auto-pass(--auto)/gate(--step) ; L0 → auto-pass    │
│     dispatch(node):  (3a) leaf skill INLINE (depth 0)                                  │
│                      (3b) spawner skill → Agent tool → NAMED AGENT (depth 1)           │
│                      (3c) workflow-chaining (depth 1) → fanout context:fork (depth 2)  │
│     read Continuation Contract ; update run-<id>.json ; materialize next[] → dynamic   │
│   stop ⇒ DONE | BLOCKED | NEEDS_CONTEXT  → report + evidence (Completion #8)           │
└────────────────────────────────────────────────────────────────────────────────────────┘
  HOOKS (self-gate to pass when no active run; NONE hard-blocks MAIN):
   • PreToolUse  remind-delegate  → main Write/Edit/Bash during active run ⇒ additionalContext
                 nudge "consider delegating" (permissionDecision=allow, never deny)
   • SubagentStop parse-continuation → subagent Contract NEEDS_NEXT ⇒ systemMessage nudge advance
                 (block applies ONLY to subagents as a quality gate, never to main)
   • Stop        drive-continuation → main ends turn while RUN==NEEDS_NEXT ⇒ systemMessage
                 advisory (continue=true, never block) — main keeps the right to stop
  blackboard .odoo-ai/run-<id>.json = SINGLE SOURCE (only run-driver writes); state on disk ⇒
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

````
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
````

- **Parsing** reuses the transcript jq pipeline already in `hooks/enforce-grounding.sh`.
- **Back-compat:** a legacy `SUGGESTED_NEXT: <skill> (reason=…, target=…)` line maps to
  `next: [{skill, reason, confidence: 0.5, risk_level: L0}]` with `status: NEEDS_NEXT`. This
  lets the rollout be gradual — an un-migrated skill still drives at low confidence.
- **Depth safety:** a subagent only *emits* a contract; it never dispatches. Advancing is the
  depth-0 driver's job. fanout/WI workers (depth 2) emit contracts that bubble up to their
  depth-1 orchestrator, never self-fire.

### 8.3 run-`<id>`.json blackboard

Single source of truth for one run, under `.odoo-ai/` (gitignored). **Only `run-driver`
writes it** (hooks never write — avoids a write race). Resume mirrors the BRL checkpoint
contract (§3.3): re-entry reads the file, skips `DONE` nodes, resumes at the first `READY`
node in topo-order.

**When Phase P engages (SSOT in `intake` § Phase P — restated here to avoid drift):** engage
(write this file + run the driver) if ANY of — (1) `node_count >= 2`; (2) a single
`output_mode == writes-files` node; (3) a single workflow node whose YAML declares
`on_complete`. Otherwise (single chat-only node, not a workflow-with-on_complete) dispatch
directly with no run file. The autonomy dial is NOT a trigger — it is only recorded here once
engaged. A workflow-command is ONE node (its phases are SSOT in the `.workflow.yaml`, never
expanded into WIs — see §4.6).

**Invariant — `on_complete` workflows are driver-required.** A workflow that declares
`on_complete` only *emits* `next[]`; only a `run-driver` dispatches it. Therefore such a
workflow MUST be entered through a driver: intake Phase P engages one automatically (trigger 3
above). A slash command whose workflow declares `on_complete` must likewise engage the driver
(write a 1-node `run-<id>.json` + invoke `run-driver`) instead of dispatching `workflow-chaining`
directly — otherwise the chain degrades to a human suggestion (workflow-chaining states this
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

### 8.4 Gate-tier policy

`output_mode` and `default_gate_tier` are SSOT per-skill in
`generator/skill_tool_deps.json → orchestration.<skill>` (validated by `check_orchestration.py`,
which also enforces the derivation below). They replace the hardcoded chat-only lists (§4.1).

- **`output_mode`** — the authoritative runtime source is the explicit
  `orchestration.<skill>.output_mode` field in the registry (read that field; §4.7 row agrees).
  That field's **value was set per-skill from the skill's declared Output semantics — NOT
  derived from `stack`** (a backend/frontend-stack skill can be read-only: `odoo-version-diff`,
  `odoo-deprecation-audit`, `odoo-code-review`, `odoo-ui-review` are all `chat-only`).
  - `writes-files` → persists a file artifact (`.odoo-ai/…` or source) → **Plan Mode required**.
  - `chat-only` → emits to chat only → skip Plan Mode.
- **`default_gate_tier`** is derived deterministically from `(spawn_class, instance_touching,
  output_mode)`:
  - **L2** if `instance_touching` OR `spawn_class == spawner-wave` — irreversible / outward
    (touches an instance, git push/merge, sends to a third party). **ALWAYS human gate; the
    autonomy dial can never lower L2.**
  - **L1** else if `output_mode == writes-files` — writes internal files. Auto-pass under
    `--auto` within budget; gated under `--step`.
  - **L0** else — read-only / chat. Auto-pass.
- **Per-node override** lives in `run-<id>.json` (a node may raise its tier, e.g. a coder told
  to write outside `.odoo-ai/`), never in the registry.

### 8.5 Command / Skill / Agent — the three axes

These are three **different axes** with a one-way reference chain `Command → Skill → Agent`
(a DAG, no cycle — consistent with the depth rule that an agent never calls back into a skill).
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
`context: fork` (≤3 concurrent). The phase count is flexible — fewer or more than three.

**named-agent vs fanout-worker (decision rule):**
- Rich expertise + fixed tool-set + reused in many places → **named agent** (`agents/*.md`,
  model in frontmatter). E.g. `odoo-coder`.
- Homogeneous workers inside one fan-out phase → **anonymous fanout worker**, model controlled
  by the phase's `model_tier` (no named agent per model needed).

### 8.6 Main Agent Operating Contract

When a run is active (`.odoo-ai/run-<id>.json` exists with `status != DONE`), the main agent
keeps its context clean by acting as orchestrator + decision-maker only — three layers, in
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
