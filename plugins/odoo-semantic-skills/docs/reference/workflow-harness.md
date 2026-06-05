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
│  Declarative *.workflow.yaml + workflow-runner skill            │
│  · maps one of 6 team-patterns to a gated phase sequence        │
│  · phase gates: approve / refine / cancel between phases        │
│  · writes .odoo-ai/<output_dir>/ artifacts                      │
│  Monolithic skills (odoo-brl) also live here                    │
└───────────────────────────────────┬────────────────────────────┘
                                    │ NL-dispatch or context: fork (≤3)
                                    ▼
┌────────────────────────────────────────────────────────────────┐
│  EXECUTION LAYER  (depth 1, max depth 2 for fork workers)       │
│  Specialist skills (odoo-coder, odoo-code-reviewer, …)          │
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

`.odoo-ai/` is gitignored by the onboarding skill (`/odoo-onboard`). All runtime
artifacts are written here; nothing under `.odoo-ai/` is committed to the repo.

### File-ownership table

| Component | Sub-path | Written by |
|-----------|----------|------------|
| Context snapshot | `.odoo-ai/context.md` | `odoo-onboard` skill |
| Brainstorm state | `.odoo-ai/brainstorm/state.json` | `intake` skill |
| Brainstorm design doc | `.odoo-ai/brainstorm/<slug>-<date>.md` | `intake` (approval turn) |
| BRL job artifacts | `.odoo-ai/brl/<job-id>/` | `odoo-brl` skill |
| Workflow phase state | `<output_dir>/<slug>-state.json` (output_dir is the full `.odoo-ai/...` path) | `workflow-runner` |
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
  "profiles": {"odoo": "odoo_17", "viindoo": "viindoo-internal"},
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
  `odoo-deprecation-audit`, `odoo-gap-analysis`, `odoo-discovery-summarize`,
  `odoo-capability-proof`, `odoo-objection-handler`, `odoo-content-draft`,
  `odoo-competitive-brief`, and any skill whose output column is "chat only".

#### Intake-initiated Plan Mode pattern

When a depth-0 skill (`intake`) reaches the execute phase after the user approves a
Proposed Plan and the Approach `output_mode = writes-files`, the main agent calls
`EnterPlanMode` → writes the implementation plan (see §4.6 Content Schema) for UI
review → receives user approval via `ExitPlanMode` → then dispatches the
file-touching specialist. This is a first-class enforcement option, not a workaround.

There is **no platform write-block** behind the gate. `intake` does not declare
`disallowed-tools: Write Edit`, and the coders (`odoo-coder`, `odoo-frontend-coding`)
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
  in read-only mode (e.g. `odoo-feature-check`, `odoo-override-finder`). These agents
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
speculative. This is the same principle as `odoo-override-finder` confirming a hook
before `odoo-coder` writes the override.

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
# Full-stack feature (2 WIs, linear)
WI-A → odoo-coder (sonnet, M)        adds backend field + ORM method
WI-B → odoo-frontend-coding (sonnet, M) renders OWL widget
DAG: linear  WI-A --data-flow--> WI-B
  (field must exist before widget binds)
Verify: ./run_tests.sh sale_order

# Three disjoint fixes (independent, candidate for wave)
WI-A → odoo-coder (sonnet, S)        bug fix in account_move
WI-B → odoo-coder (sonnet, S)        unit test for WI-A
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
| `output_mode` (`chat-only` ↔ `writes-files`) | `spawn_class` + `stack` in the generator / `skill_tool_deps.json` registry | Look up the existing registry entry |
| `effort` (S / M / L / XL) | NOT registered — it is a skill × task property | Reason per the `odoo-gap-analysis` legend: S <1d · M 1–3d · L 3–10d · XL >10d |

**Key invariants:**

- `model_tier` lives in frontmatter and MUST NOT be copied into any registry or plan
  as a constant. Read it fresh at plan time from the candidate's own SKILL.md.
- `effort` is per-task, not per-skill. Two invocations of the same skill can have
  different effort tiers depending on scope.
- `output_mode` is the only attribute whose SSOT is the registry (`skill_tool_deps.json`
  via `spawn_class`/`stack`). This is what drives the Plan Mode decision tree (§4.1).

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
skill (`workflow-runner`). Adding a workflow = dropping a `.workflow.yaml` file;
no orchestration code is written.

### 5.2 `workflows/*.workflow.yaml` schema

```yaml
# Example: workflows/qa-test-suite.workflow.yaml
name: qa-test-suite
domain: qa                       # one of 9 persona buckets
team_pattern: pipeline           # see §5.3 for all 6 patterns
description: |
  Generate and review an Odoo test suite from a feature spec.
  Trigger: "write tests for", "generate test suite", "QA for this feature".
output_dir: .odoo-ai/qa          # all artifacts land here
inputs: [feature_spec]           # named args collected at Phase 0

phases:
  - id: scaffold
    skill: odoo-coder
    nl_trigger: "write Odoo unit tests for the feature described"
    model_tier: sonnet
    gate: "yes / edit / cancel"

  - id: review
    skill: odoo-code-reviewer
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

The runner skill (`workflow-runner`, `user-invocable: false`) auto-discovers
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
NOT spawn `context: fork` workers. Examples: `odoo-coder`, `odoo-code-reviewer`,
all 26 specialist skills.

A **spawn skill** orchestrates leaf skills by NL-dispatch or forks workers via
`context: fork`. Examples: `odoo-brl` (forks DAG cluster workers), `intake`
(NL-dispatches to specialists), `workflow-runner` (phases mapped to leaf skills).

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

### 7.2 Why wave is NOT a workflow-runner team-pattern

This is the **authoritative decision record** for why git-wave is a depth-0 skill,
not a `team_pattern` inside the declarative workflow system.

| Axis | workflow-runner (depth-1) | wave skill (depth-0) |
|------|--------------------------|----------------------|
| Depth | Runs at depth 1; fork workers are depth-2 ceiling | Runs at depth 0; WI subagents are depth-2 ceiling |
| Git authority | None — runner does NL-dispatch only; no git ops | Full git authority: worktree add, cherry-pick, PR creation, squash, force-with-lease |
| /code-review legality | Cannot call /code-review (self-spawn only legal at depth-0) | Calls /code-review inline from main context (depth-0) — the only legal call site |
| State machine | Declarative phases in `.workflow.yaml`; runner executes them | Imperative phases (0-6) encoded in the skill body; git refs/worktrees ARE the state |
| Coupling | Coupled to workflow schema; adding GitWave would require new `team_pattern: GitWave` + new runner branch + new yaml keys | Self-contained; no schema changes to existing runner or yaml format |
| Crash risk | Injecting git orchestration into depth-1 runner would push fork workers to depth-3 — exceeds platform ceiling | Depth ceiling respected: 0 (wave) → 2 (WI subagent) |

**Decision**: git-wave is a depth-0 actor that sits alongside `intake` at the top
layer, not below `workflow-runner`. This is final and must not be revisited without
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
You are a leaf worker (depth-2). You MAY NL-dispatch a non-spawning specialist skill
(e.g. odoo-coder, odoo-code-reviewer) if it helps. Do NOT invoke the Skill tool
directly. Do NOT spawn a sub-agent. Do NOT call self-spawning skills (/code-review,
skill-creator, wave). Do NOT git branch/cherry-pick/merge/push; stay in your assigned
worktree. Only Read/Grep/Glob/Edit/Write/Bash.
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
`odoo-onboard`). The `<slug>` is a short kebab-case descriptor chosen at Phase 0.
The directory is cleaned up after a successful human-confirm merge.
