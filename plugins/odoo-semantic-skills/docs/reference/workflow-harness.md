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
5. [Composition contract](#5-composition-contract)
6. [Skill delegation depth rule](#6-skill-delegation-depth-rule)

---

## 1. Overview — three-layer architecture

The workflow harness is organized in three layers. Every workflow lives in exactly
one layer; cross-layer calls travel top-down only and never skip a layer.

```
┌────────────────────────────────────────────────────────────────┐
│  ENTRY / INTAKE LAYER  (depth 0)                                │
│  intake skill — domain-agnostic front door                      │
│  · 4-tier routing (regex → state → keyword → LLM)              │
│  · brainstorm-when-vague (6-step), pro fast-path                │
│  · always emits a soft-plan-gate before dispatching            │
│  · disallowed-tools: Write Edit (platform-enforced this turn)   │
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
Technical edges come from `module_inspect(method='dependencies')` (deterministic).  
Business-logic and data-flow edges come from Opus cluster reasoning.

---

## 4. Soft-plan-gate convention

### 4.1 Why skills cannot force plan mode (A1 constraint)

Skills, commands, and hooks cannot set `permission_mode=plan`. Plan mode is only
user-activated (Shift+Tab, `/plan`, CLI flag, `defaultMode` in settings).
The harness achieves an equivalent read-only planning turn through two mechanisms:

1. **`disallowed-tools: Write Edit`** in the skill frontmatter — platform-enforced
   for the current turn, clearing automatically when the user sends the next message.
2. **Iron Law** in the skill body — behavioral: "no execution fires until the user
   has approved a Proposed Plan". Paired with a Red Flags table listing rationalizations
   the agent must refuse (e.g., "This is simple, I'll just start coding" → STOP).

This combination is the only A1-legal substitute for plan mode in a plugin skill.

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
| Platform | `disallowed-tools: Write Edit` | Blocks file writes for this turn |
| Behavioral | Iron Law + Red Flags in skill body | Blocks execution dispatch |
| Approval | `intake` ends turn; next user prompt enables writes | Write unlock |
| Refine loop | Gate loops inside brainstorm; no writes until `approve` | Iteration |

On `approve`: the skill ends its turn. The user's next message fires the specialist
or workflow via NL description-match dispatch (writes are now allowed).  
On `refine: [feedback]`: the brainstorm loop continues within the current turn.  
On `cancel`: the skill stops and reports.

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
| `haiku` | Read-only lookup, classification, simple Q&A with no writes |
| `sonnet` | Write tasks, edits, single-file refactor, review — **floor for write phases** |
| `opus` | Cross-file reasoning, orchestration parent, DAG cluster reasoning — max 3 concurrent |

The BRL skill declares `model: opus` for the orchestrating skill body. Inner MCP
calls and leaf worker turns use the tier assigned in the chunk/phase declaration.

---

*This document is the SSOT for the workflow harness. When the artifact schema, gate
convention, or composition contract changes, update this file first and propagate to
referencing skills via the marker-block or direct reference.*
