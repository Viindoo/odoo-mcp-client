<!-- SSOT snippet. The single home for the EXECUTOR'S OWN live, in-session progress checklist -
     distinct from teammate-status tracking (agent-team-protocol.md Ask 2, CHP-gated) and from the
     durable run-<id>.json blackboard / worklog (worklog-contract.md, the state SSOT). Referenced
     (not copy-pasted) by run-harness, workflow-chaining, odoo-planning, and agent-team-protocol.md.
     Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/execution-tasklist-contract.md. -->

# Execution Task-List Contract (live, in-session progress checklist)

When you begin executing a multi-step plan - waves, modules, phases, or work-items - create a
live task list and keep it updated as execution progresses: one item per unit of work; mark an
item in-progress when you start it, done when you finish it, and add newly-discovered work as a
new item rather than folding it silently into an existing one.

This applies whenever a task-list tool is available in your active toolset, INDEPENDENT of the
experimental Agent Team mode / CHP capability probe (`context-handoff-protocol.md`) and
independent of whether `SendMessage` is present. Do NOT gate this on any experimental flag - use
whatever task-list primitive your runtime actually exposes; this contract deliberately does not
hardcode a tool name, since the concrete tool differs by harness and some harnesses only expose
`TaskCreate`/`TaskUpdate`/`TaskList`/`TaskGet` under the experimental flag.

## Not the same surface as ...

- **The blackboard** (`run-<id>.json`) - the durable DAG state machine, written only by
  `run-harness`. The live task list MIRRORS this state for human visibility; it never replaces or
  redefines it. Update both together when a unit of work changes status - they must not drift.
- **The worklog** (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`) - the durable, append-only
  *why* journal. The live task list carries only status, never rationale.
- **Teammate-status tracking** (`${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md`, Ask 2) -
  that mechanism tracks OTHER named, SendMessage-addressable subagents and stays gated on the full
  CHP capability probe (env flag + `SendMessage` present + addressable worker + team lead). THIS
  contract is different: it is the executor tracking ITS OWN sequential work, and it fires
  whenever a task-list tool exists, regardless of whether any teammate is being tracked at all.

## Scope

Ephemeral, in-session progress UI only - it does not persist across sessions and is not a
substitute for writing `produced` / `contract` / worklog entries. Maintain the live list AND the
durable state together; neither replaces the other. When no task-list tool is available, degrade
silently: proceed without one, exactly as before this contract existed.

## Terminal-state vocabulary - this file does NOT own it

This file names only the generic UI states a live checklist item passes through (`in-progress` when
started, `done` when finished) - it does NOT define, and has never defined, a status enum for a
SPAWNER deciding when its launched children have all finished. That release vocabulary is a SEPARATE
concept, owned once by `${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R1: a
spawner's batch barrier clears when every launched child has returned one of the four Continuation
Contract terminal statuses (`DONE`/`BLOCKED`/`NEEDS_NEXT`/`NEEDS_CONTEXT`,
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`) - never a tool-native label. Do not gate a
barrier on this file naming `completed`/`blocked`/`pending`/`in_progress` as if it were that enum;
it never has been. When you mark a task-list item `done` in the sense this file uses, that MUST mean
"its owner reached ANY of the four terminal statuses", not merely "succeeded" - a `BLOCKED` or
`NEEDS_CONTEXT` child is just as terminal for THIS checklist's purposes as a `DONE` one, even though
your task-list tool may have no dedicated label for the distinction (see `spawner-completion-contract.md`
R1 for how to track the distinction elsewhere when the tool cannot).
