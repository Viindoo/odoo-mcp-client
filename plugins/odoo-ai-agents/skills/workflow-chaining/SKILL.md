---
name: workflow-chaining
argument-hint: "[workflow name/file]"
user-invocable: false
description: >
  Generic declarative workflow runner - reads one `workflows/<name>.workflow.yaml` file and
  executes its gated phase sequence according to the declared `team_pattern` (Pipeline,
  Fan-out/Fan-in, Expert-Pool, Producer-Reviewer, Supervisor, or Hierarchical). Dispatches
  each phase to a specialist skill via the Skill tool (preferred) or NL description-match as a fallback. Writes
  phase artifacts to the `output_dir` declared in the YAML and checkpoints state for resume.
  Invoked by the intake skill (or concierge) via NL-dispatch after a workflow is chosen at the
  soft-plan-gate - never called directly by the user
model: inherit
---

# workflow-chaining - Generic Declarative Workflow Runner

## Role

Neutral orchestration engine: reads the YAML, announces each phase, gates on user approval,
dispatches specialists via the Skill tool (NL description-match as fallback), writes checkpoints. No domain knowledge - that lives in the
`.workflow.yaml` and the specialist skills. Invoked by `odoo-intake` or `odoo-concierge` after
a user approves a multi-step workflow plan at the soft-plan-gate.

## Hard rules

1. **Prefer the Skill tool for phase dispatch.** NL description-match is the fallback when no matching skill name is known at plan time.
2. **NEVER spawn a sub-agent directly** (no Agent tool, no `context: fork` - fan-out is the
   only exception, ≤3 concurrent workers with the mandatory worker-brief preamble).
3. **No recursion.** Fork workers are leaf agents and carry:
   "Do NOT invoke spawner skills via the Skill tool. Do NOT spawn sub-agents. You MAY use the Skill tool for read-only leaf skills (e.g. odoo-feature-check, odoo-override-finding). Only Read/Grep/Glob/Write/Bash."
4. **No execution before gate.** Emit a gate before each phase; wait for approval.
5. **Resume from checkpoint.** If `resume: true` and `<output_dir>/<slug>-state.json` exists
   (`output_dir` is the full `.odoo-ai/...` path from the YAML), load it and skip done phases.
6. **SSOT for schema** → `workflows/_schema.md`. This body describes behavior, not schema.
7. **on_complete EMITs, never dispatches.** Matched transitions go to Continuation Contract
   `next[]` for the run-harness - this skill never fires a spawner itself.

## Phase 0 - Load and validate

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

## Phase execution - pattern dispatch

### Pipeline (sequential, gate between each)

Run phases in order. Before each phase:
1. Announce: "## Phase <id> - <description from nl_trigger>"
2. If `when:` predicate is false, **skip entirely** (no gate, no dispatch, no output).
3. If `gate` is set, emit gate and wait for approval.
4. Dispatch via the Skill tool (NL description-match as fallback); for `inline: true` phases, handle in-line.
5. Write output to `output_dir` and update the state checkpoint.

### Phase output contract

After each phase finishes (whether dispatched or inline), present the specialist's output
to the user wrapped in the following boundary block:

```
## Phase <id> - <description> [DONE | FAILED]
<specialist output>
---
```

Use `DONE` when the phase completed without error; use `FAILED` when the specialist
reported an error or produced no usable output. This wrapper is mandatory for every
phase - including conditional phases that actually fired and fan-out aggregation - so
phase boundaries remain clearly visible throughout a multi-phase run.

### Fan-out / Fan-in (parallel workers, ≤3 concurrent)

For phases marked `fanout: true` with a `chunk_by` field:
1. Split input into chunks per `chunk_by`.
2. Cap at 3 concurrent workers (Mode A - `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`).
3. Each worker prompt MUST begin with the worker brief
   (`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`). For Odoo-touching workers also inline
   the OSM-First Grounding Contract (`${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md`).
4. Aggregate worker results before proceeding.

### Expert-Pool (predicate-based specialist selection)

Evaluate `when:` predicate against the current item; dispatch the matching specialist via the Skill tool (NL description-match as fallback).
If no predicate matches, fall through to the `fallback` specialist if declared.

### Producer-Reviewer (produce + review pair)

Dispatch producer first via the Skill tool (NL description-match as fallback). Then dispatch reviewer with: "review the output for correctness -
report findings, do not fix". Gate between produce and review.

### Supervisor (inline distribution)

Supervisor phase is `inline: true`. Distribute sub-tasks via the Skill tool (or NL description-match as fallback); assemble results
inline before writing to `output_dir`.

### Hierarchical (one decomposition level, bounded)

Top phase decomposes work into a sub-`phases[]` list at runtime, then executes as a Pipeline.
**Bounded to one level** - sub-phases cannot decompose further (no recursion).

## Inline phase handling

For `inline: true` phases, the runner performs the work itself:
- Aggregate results from previous phases.
- Write the final artifact to `output_dir/<slug>-<phase-id>.<ext>`.
- Do not dispatch to any external skill.

## Resume logic

After each phase completes successfully:
1. Write or update `<output_dir>/<slug>-state.json` (`output_dir` already starts with
   `.odoo-ai/` - do not prepend it again):
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

## on_complete - cross-workflow transition (EMIT only)

After the **final** phase completes, if the YAML declares a top-level `on_complete:` list,
evaluate each entry's `when:` predicate (same mechanism as `phases[].when` - read accumulated
phase outputs; the key MUST have surfaced in that phase's output). For every matching entry,
**add it to your Continuation Contract `next[]`** (`next → skill`, `reason`, `inputs`,
`gate_tier → risk_level`). Example: a `qa-suite` run that found bugs emits `next: odoo-coding`.

**HARD RULE - EMIT, never self-dispatch.** `on_complete` only *emits* `next[]`. This skill MUST NOT
invoke a spawner - the run-harness dispatches it.
If no `on_complete` is declared, or none matches, finish normally (back-compatible).

**No driver above - degrade honestly.** If running WITHOUT an active run-harness (e.g. invoked
directly, not through intake Phase P), emit the contract AND state plainly: "on_complete
suggests `<next>` - auto-chaining needs the run-harness; run `/odoo-intake` to drive it, or
trigger `<next>` manually." Never silently drop. (To AUTO-chain, enter via intake Phase P.)

## Gate handling

Present options from the YAML `gate` field. Standard responses:
- `approve` / `yes` / `ok` → proceed.
- `refine: [feedback]` → incorporate feedback and re-propose.
- `cancel` → stop; report completed phases and artifact locations.

## Out of Scope

- Domain-specific logic → lives in the specialist skill or `.workflow.yaml`.
- BRL chunk orchestration → `odoo-brl` has its own gating.
- Creating or editing `.workflow.yaml` files (data files, not runtime artifacts).
- Direct user invocation → use `odoo-intake` or `odoo-concierge`.

## Standalone-first fallback

If the odoo-semantic-mcp server is unreachable:
- For phases whose specialist requires OSM: append to the `nl_trigger`: "OSM is unavailable -
  proceed in standalone mode using training knowledge and any local files available."
- Continue the workflow; each specialist declares its own standalone fallback.
- If a phase's `fallback` field is `standalone`, apply this automatically.
- Write a caveat in the final artifact noting which phases ran without OSM grounding.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the run-harness - it does not change anything produced above.
