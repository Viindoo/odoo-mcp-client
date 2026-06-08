---
name: workflow-chaining
user-invocable: false
description: >
  Generic declarative workflow runner — reads one `workflows/<name>.workflow.yaml` file and
  executes its gated phase sequence according to the declared `team_pattern` (Pipeline,
  Fan-out/Fan-in, Expert-Pool, Producer-Reviewer, Supervisor, or Hierarchical). Dispatches
  each phase to a specialist skill via NL description-match, never via the Skill tool. Writes
  phase artifacts to the `output_dir` declared in the YAML and checkpoints state for resume.
  Invoked by the intake skill (or concierge) via NL-dispatch after a workflow is chosen at the
  soft-plan-gate — never called directly by the user
model: inherit
---

# workflow-chaining — Generic Declarative Workflow Runner

## Persona

Orchestration engine for the composition layer. This skill has no domain of its own; it
executes whatever workflow contract it is handed. It acts as a neutral conductor: it reads
the YAML, announces each phase, gates on user approval, dispatches the right specialist via
NL, and writes checkpoints. It does not make domain decisions — those are encoded in the
`.workflow.yaml` file and in the specialist skills it dispatches to.

Target invoker: the `intake` skill or `odoo-concierge`, after a user approves a multi-step
workflow plan at the soft-plan-gate.

## Hard rules

1. **NEVER invoke the Skill tool.** All cross-skill dispatch uses NL description-match
   (write a natural-language prompt that matches the target skill's `description` field).
2. **NEVER spawn a sub-agent directly** (no Agent tool, no `context: fork` from within
   this skill body — fan-out is the only exception and uses ≤3 concurrent workers with the
   mandatory hard-rules line).
3. **Depth-2 ceiling.** This skill runs at depth 1 (called from the main context). Fork
   workers are depth 2 and carry the mandatory line: "Do NOT invoke Skill tool. Do NOT
   spawn sub-agent. Only Read/Grep/Glob/Write/Bash."
4. **No execution before gate.** Emit a gate before each phase and wait for `approve /
   refine: [feedback] / cancel` before dispatching the phase.
5. **Resume from checkpoint.** If `resume: true` and a state file exists at
   `<output_dir>/<slug>-state.json` (where `output_dir` is the full `.odoo-ai/...`
   path declared in the YAML), read it and skip already-completed phases.
6. **SSOT for schema.** The full field reference lives in `workflows/_schema.md`. This
   skill body describes behavior, not schema.
7. **on_complete EMITs, never dispatches.** A matched `on_complete` transition is added to the
   Continuation Contract `next[]` for the depth-0 run-driver to dispatch — this skill never
   fires a spawner itself (see "on_complete — cross-workflow transition" below).

## Phase 0 — Load and validate

1. Read the referenced `workflows/<name>.workflow.yaml` file.
2. Read `.odoo-ai/context.md` if it exists (Odoo version, profile defaults).
3. If `resume: true`, check for `<output_dir>/<slug>-state.json` (the `output_dir`
   already includes the `.odoo-ai/` prefix); if found, load it and determine the last
   completed phase.
4. Collect any missing `inputs[]` from the user (one question per missing input).
5. Emit the **soft-plan-gate** header before any phase runs:

```
## Proposed Plan
Domain:       <domain>
Workflow:     <name>
Pattern:      <team_pattern>
Chain:        <phase-1.id> → <phase-2.id> → ... → <phase-N.id>
Output:       <output_dir>/
Est. effort:  <count> phase(s), gates between each
Model tiers:  <per-phase list>

Gate: approve / refine: [feedback] / cancel
```

Wait for user response before proceeding to Phase 1.

## Phase execution — pattern dispatch

### Pipeline (sequential, gate between each)

Run phases in order. Before each phase:
1. Announce: "## Phase <id> — <description from nl_trigger>"
2. If the phase declares a `when:` predicate, evaluate it against the current state
   (e.g. a prior phase's classification). If it is **false, skip this phase entirely**
   — no gate, no dispatch, no output — and continue to the next phase. This lets a
   Pipeline carry mutually-exclusive conditional branches (e.g. a `bug` path vs a
   `feature-request` path where exactly one fires).
3. If `gate` is set on this phase, emit the gate and wait for approval.
4. Dispatch via NL: write a prompt that naturally matches the target skill's `description`.
   For `inline: true` phases, handle the work in-line without dispatching.
5. After phase completes, write output to `output_dir` and update the state checkpoint.

### Phase output contract

After each phase finishes (whether dispatched or inline), present the specialist's output
to the user wrapped in the following boundary block:

```
## Phase <id> — <description> [DONE | FAILED]
<specialist output>
---
```

Use `DONE` when the phase completed without error; use `FAILED` when the specialist
reported an error or produced no usable output. This wrapper is mandatory for every
phase — including conditional phases that actually fired and fan-out aggregation — so
phase boundaries remain clearly visible throughout a multi-phase run.

### Fan-out / Fan-in (parallel workers, ≤3 concurrent)

For phases marked `fanout: true` with a `chunk_by` field:
1. Split the input into chunks according to `chunk_by`.
2. Cap concurrent workers at 3 (memory ceiling — see failure log `unbounded-opus-fanout-oom`).
3. Each worker prompt MUST begin with the nesting guard
   (${CLAUDE_PLUGIN_ROOT}/snippets/nesting-guard.md): "Do NOT invoke the Skill tool. Do NOT
   spawn a sub-agent. Only Read/Grep/Glob/Write/Bash." For any worker that touches Odoo
   (classifies modules, writes/reviews code, makes capability claims), also include the
   OSM-First Grounding Contract (${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md):
   verify every Odoo model/field/CLI/token claim via OSM before asserting, reuse indexed
   patterns before hand-writing, and flag "OSM unavailable — ungrounded" if OSM is down —
   never classify or code Odoo from memory.
4. Aggregate worker results before proceeding to the next phase.

### Expert-Pool (predicate-based specialist selection)

For phases with `when:` predicates:
1. Evaluate the predicate against the current item.
2. Select the matching specialist skill and dispatch via NL.
3. If no predicate matches, fall through to the `fallback` specialist if declared.

### Producer-Reviewer (produce + review pair)

Execute the `produce` phase first (NL-dispatch to producer skill). Then execute the
`review` phase with explicit instruction: "review the output for correctness — report
findings, do not fix". The reviewer reads the produced artifact and emits a review report.
Gate between produce and review.

### Supervisor (inline distribution)

The supervisor phase is `inline: true`. The runner distributes sub-tasks via NL-dispatch
and collects results. Each sub-task is one NL prompt to a specialist; results are assembled
inline before writing to `output_dir`.

### Hierarchical (one decomposition level, bounded)

The top phase decomposes the work into a sub-`phases[]` list at runtime. The generated
sub-phases are then executed as a Pipeline. Decomposition is bounded to one level — the
sub-phases CANNOT themselves decompose further (no recursion past depth 2).

## Inline phase handling

For `inline: true` phases, the runner performs the work itself:
- Aggregate results from previous phases.
- Write the final artifact to `output_dir/<slug>-<phase-id>.<ext>`.
- Do not dispatch to any external skill.

## Resume logic

After each phase completes successfully:
1. Write or update `<output_dir>/<slug>-state.json` (`output_dir` already starts with
   `.odoo-ai/` — do not prepend it again):
   ```json
   {
     "workflow": "<name>",
     "slug": "<slug>",
     "last_completed_phase": "<phase-id>",
     "phases_done": ["<id1>", "<id2>"],
     "updated_at": "<ISO-8601>"
   }
   ```
2. On next run with the same workflow + slug, read the state file, skip done phases,
   and resume from `last_completed_phase + 1`.

## on_complete — cross-workflow transition (EMIT only)

After the **final** phase completes, if the YAML declares a top-level `on_complete:` list,
evaluate each entry's `when:` predicate using the SAME mechanism as `phases[].when`: read the
accumulated phase outputs and judge the predicate (e.g. `classification == 'bug'`,
`code_bugs_found == true`). The phase an `on_complete` reads MUST have surfaced that key in its
output (there is no separate typed state store). For every entry that matches, **add it to your
Continuation Contract `next[]`** (mapping `next → skill`, carrying `reason`, `inputs`, and
`gate_tier → risk_level`). Example: a `qa-suite` run that found bugs emits
`next: odoo-coding` so the depth-0 run-driver can chain a fix.

**HARD RULE — EMIT, never self-dispatch.** `on_complete` only *emits* `next[]`. workflow-chaining
runs at depth 1 and MUST NOT invoke a depth0-only spawner (`odoo-coding`, `wave`, …)
itself — that would nest a fresh agent below depth-1 and risk a context crash. The depth-0
`run-driver` reads the emitted `next[]` and dispatches it. If no `on_complete` is declared, or
none matches, finish normally (this is fully back-compatible — existing workflows are unaffected).

**Standalone (no driver above) — degrade honestly.** If this workflow is running WITHOUT an
active `.odoo-ai/run-<id>.json` driver above it (e.g. invoked directly via its slash command,
not through intake Phase P), there is no run-driver to read the emitted `next[]`. In that case,
besides emitting the contract, state plainly to the user: "on_complete suggests `<next>` —
auto-chaining needs the run-driver; run `/intake` to drive it, or trigger `<next>` manually."
So the chain degrades to a visible human suggestion, never a silent drop. (To AUTO-chain a
workflow that declares `on_complete`, enter via intake Phase P — intake engages the driver for
such workflows; see `intake` § Phase P "Workflow-as-node".)

## Gate handling

Each phase gate presents the options declared in the YAML `gate` field (e.g.
`"yes / edit / cancel"`). Standard responses:
- `approve` / `yes` / `ok` → proceed to the phase.
- `refine: [feedback]` → incorporate feedback and re-propose the phase plan.
- `cancel` → stop the workflow; report completed phases and artifact locations.

## Out of Scope

- Domain-specific logic (that lives in the specialist skill or the `.workflow.yaml`).
- BRL chunk orchestration (handled by `odoo-brl` which has its own gating).
- Creating or editing `.workflow.yaml` files (those are data files, not runtime artifacts).
- Being invoked directly by the user (use the `intake` skill or `odoo-concierge`).

## Standalone-first fallback

If the OSM server (odoo-semantic-mcp) is unreachable:
- For phases whose specialist skill requires OSM tools: emit the phase's `nl_trigger` with
  an appended note: "OSM is unavailable — proceed in standalone mode using training knowledge
  and any local files available."
- Continue the workflow; each specialist skill declares its own standalone fallback.
- If a phase's `fallback` field is `standalone`, apply this automatically without asking.
- Write a caveat section in the final artifact noting which phases ran without OSM grounding.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
