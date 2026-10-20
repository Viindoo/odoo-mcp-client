---
name: workflow-chaining
argument-hint: "[workflow name/file]"
user-invocable: false
description: >-
  Internal: runs a workflow YAML phase by phase
model: inherit
---

# workflow-chaining - Generic Declarative Workflow Runner

## Role

Read the YAML, decide the workflow plan once, announce each phase, dispatch specialists via the Skill
tool (NL description-match as fallback), write checkpoints. Invoked by `odoo-intake`, a workflow
command, or a plan's workflow node.

## Hard rules

1. **Prefer the Skill tool for phase dispatch.** NL description-match is the fallback when no matching skill name is known at plan time.
2. **NEVER spawn a sub-agent directly** (no direct agent launch, no `context: fork` - fan-out is the
   only exception, ≤3 concurrent workers with the mandatory worker-brief preamble).
3. **No recursion.** Fork workers are leaf agents and carry:
   "Do NOT invoke spawner skills via the Skill tool. Do NOT spawn sub-agents. You MAY use the Skill tool for read-only leaf skills (e.g. odoo-feature-check, odoo-override-finding). Only Read/Grep/Glob/Write/Bash."
4. **One plan decision, then no stops.** No phase runs before the workflow plan is decided
   (Phase 0 step 6). Phases then run without stopping; a phase `gate` is a text confirmation
   before that phase's outward or irreversible action, and the only one.
5. **Resume from checkpoint.** If `resume: true` and `<output_dir>/<slug>-state.json` exists
   (`output_dir` resolves per Phase 0 step 2), load it and skip done phases.
6. **Schema** → `workflows/_schema.md`.
7. **on_complete EMITs, never dispatches.** Matched transitions go to Continuation Contract
   `next[]` for the plan runner (the main agent) - this skill never fires a spawner itself.

## Phase 0 - Load and validate

1. Read the referenced `workflows/<name>.workflow.yaml` file.
2. Resolve the run's state root once, via the resolve-capture-substitute protocol in
   `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`: `output_dir:` from the YAML is a
   relative `.odoo-ai/<name>` literal that this skill resolves against the Tier-2 **ISOLATE**
   dir (call `mcp__plugin_odoo-ai-agents_odoo-local__project_dir` with axis `isolate`, `cwd` = the run's target root) at
   RUNTIME - never write to the bare project-relative `.odoo-ai/<name>` path. Resolve
   series + profile per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`.
3. **Orphan sweep (do this every invocation, before the resume check below).** Run `find <resolved
   ISOLATE output_dir>/ -mindepth 1 -maxdepth 1 -type d -mmin +43200 -exec rm -rf {} +` (it removes
   whatever `output_dir` THIS workflow declares that was untouched for over 30 days). Full rule +
   bound: `${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` § Clause 3. Run it
   unconditionally, every run.
4. If `resume: true`, check for `<output_dir>/<slug>-state.json` under the resolved ISOLATE dir; if
   found, load it and determine the last completed phase.
5. Collect any missing `inputs[]` from the user (one question per missing input).
6. **Decide the workflow plan** (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md`
   § One Plan-Mode gate per request):
   - A phase with `plan: true` computes the plan: run the phases up to and including it first
     (they write only under the state root), and present its output as the plan.
   - The workflow owns the request (invoked by `odoo-intake`, a command, or the user): call
     `EnterPlanMode`, present the block below, `ExitPlanMode` on `approve`; `refine: [feedback]`
     re-plans, `cancel` stops.
   - Every `on_complete` entry of the workflow hands the request to `odoo-solution-design` or
     `odoo-planning` (the workflow only scopes): that skill holds the request's Plan-Mode gate.
     State the chain in one line and run.
   - A node of an approved plan: present nothing and run.

```
## Workflow plan
Domain:       <domain>
Workflow:     <name>
Pattern:      <team_pattern>
Chain:        <phase-1.id> → <phase-2.id> → ... → <phase-N.id>
Plan:         <the plan phase's output, when a phase has plan: true>
Confirms:     <each phase whose gate confirms an outward or irreversible action | none>
Output:       <output_dir>/

Approve plan? (approve / refine: [feedback] / cancel)
```

Write this block in the USER'S language (translate labels and prose; keep phase ids,
workflow/skill names, file paths, and the reply keywords verbatim - SSOT:
`${CLAUDE_PLUGIN_ROOT}/snippets/language-mirroring.md`).

## Live task list

Per `${CLAUDE_PLUGIN_ROOT}/snippets/execution-tasklist-contract.md`, create and keep current a
live task list of this workflow's phases (one item per phase id) as execution proceeds - mark a
phase in-progress when dispatched, done when its output is written, and add any phase inserted via
`on_complete` or a dynamic transition as a new item. This does not replace the
`<slug>-state.json` checkpoint. Applies whenever a task-list tool is available.

## Phase execution - pattern dispatch

### Pipeline (sequential)

Run phases in order. Before each phase:
1. Announce: "## Phase <id> - <description from nl_trigger>"
2. If `when:` predicate is false, **skip entirely** (no dispatch, no output).
3. If `gate` is set, ask it as a text question before the phase's outward action and wait.
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
phase - including conditional phases that actually fired and fan-out aggregation.

### Fan-out / Fan-in (parallel workers, ≤3 concurrent)

For phases marked `fanout: true` with a `chunk_by` field:
1. Split input into chunks per `chunk_by`.
2. Cap at 3 concurrent workers (Mode A - `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`).
3. Each worker prompt MUST begin with the worker brief
   (`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`). For Odoo-touching workers also inline
   the OSM-First Grounding Contract (`${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md`).
4. Aggregate worker results before proceeding.

When composing the dispatch prompt for any specialist agent you dispatch (e.g. a fan-out
worker), fill the caller-side skeleton in `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton
(read it by path) plus the target agent's family delta; never inline that file verbatim into a
hard-leaf brief.

### Expert-Pool (predicate-based specialist selection)

Evaluate `when:` predicate against the current item; dispatch the matching specialist via the Skill tool (NL description-match as fallback).
If no predicate matches, fall through to the `fallback` specialist if declared.

### Producer-Reviewer (produce + review pair)

Dispatch producer first via the Skill tool (NL description-match as fallback). Then dispatch reviewer with: "review the output for correctness -
report findings, do not fix".

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
1. Write or update `<output_dir>/<slug>-state.json` under the resolved ISOLATE dir from Phase 0
   step 2 (substitute the captured ISOLATE literal for the `.odoo-ai/` prefix, never a bare
   `.odoo-ai/...` path in a Read/Write/Edit call):
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
**add it to your Continuation Contract `next[]`** (`next → skill`, `reason`, `inputs`).
Example: a `qa-suite` run that found bugs emits `next: odoo-coding`.

**HARD RULE - EMIT, never self-dispatch.** `on_complete` only *emits* `next[]`. This skill MUST NOT
invoke a spawner - the plan runner dispatches it.
If no `on_complete` is declared, or none matches, finish normally.

**No run above.** If running WITHOUT an active run file (not through intake Phase P), emit the
contract AND state plainly: "on_complete suggests `<next>` - auto-chaining needs a run; run
`/odoo-intake` to open one, or trigger `<next>` manually." Never silently drop.

## Gate handling

A `gate` confirms an outward or irreversible action (send, publish, merge, push, delete) and
nothing else. Present the options from the YAML `gate` field verbatim; it is ONE of the two reply
sets of `${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md`, never a third:

- PLAN set - `approve / refine: [feedback] / cancel`: `approve` proceeds, `refine: [feedback]`
  incorporates the feedback and re-proposes, `cancel` stops.
- STEP set - `approve / skip / cancel`: `approve` runs the phase, `skip` moves to the next phase
  without running it, `cancel` stops.

On `cancel`, report the completed phases and where their artifacts are.

Write the gate message in the USER'S language (translate labels and prose; keep phase ids, file
paths, skill names, and the reply keywords verbatim - SSOT:
`${CLAUDE_PLUGIN_ROOT}/snippets/language-mirroring.md`).

## Out of Scope

- Domain-specific logic → lives in the specialist skill or `.workflow.yaml`.
- BRL chunk orchestration → `odoo-brl`.
- Direct user invocation → use `odoo-intake`.

## Standalone-first fallback

If the odoo-semantic-mcp server is unreachable, the tier order in
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md` governs: Tier 2 is MANDATORY before
Tier 3, and training memory IS Tier 3 - a last resort, never a co-equal option.
- For phases whose specialist requires OSM, append to the `nl_trigger`: "OSM is unavailable -
  ground on Tier 2 per disk-fallback-protocol.md; use training memory only where Tier 2 also
  fails, and flag that part `ungrounded`."
- Continue the workflow; each specialist declares its own standalone fallback.
- If a phase's `fallback` field is `standalone`, apply this automatically.
- Caveat the final artifact PER PHASE: a Tier-2-grounded phase is NOT `ungrounded`; only a
  memory-only phase carries `grounded: ungrounded - OSM unavailable`.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next).
