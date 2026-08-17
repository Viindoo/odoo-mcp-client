<!-- SSOT snippet. Referenced (not copy-pasted) by every spawner skill, every named agent,
     and every spawned worker brief (a node's WI workers, odoo-coding fan-out, conflict resolver).
     Edit here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md. -->

# Worklog Contract (cross-agent decision log)

The **append-only decision journal** every agent reads before it starts and writes when it
finishes - NOT the Continuation Contract (a handoff signal: status/produced/next). Log *why*, so a
later phase can look it up instead of re-deriving it.

## Where it lives

`worklog/` is Tier-2 **ISOLATE** (per-run execution log; parallel runs must not interleave) - full
policy + classification tables: `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`. Resolve
the ISOLATE dir ONCE via that file's mandatory resolve-capture-substitute protocol
(`scripts/lib/resolve_project_dir.sh isolate`, captured as a literal absolute path - never a bare
`.odoo-ai/...` string in a Read/Write/Edit call), then place the worklog under it:

```
<ISOLATE_DIR>/worklog/<run-or-slug>/<NNN>-<agent>.md     # one file per writer - never a shared file
```

- `<run-or-slug>`: the active run id when a `run-<id>.json` blackboard exists (the driver records
  the worklog dir there); otherwise the feature slug the skill already uses for its artifacts.
- `<NNN>`: the zero-padded dispatch order if the orchestrator passed one; else a
  `date -u +%H%M%S` stamp, or a short label when you have no shell. The HARD requirement is a
  UNIQUE filename per writer - parallel writers would race on a shared file; the prefix only
  aids sort order.
- `<agent>`: the writer's short name (`architect`, `coder-<module>`, `reviewer-<module>`,
  `wi-<id>`, ...). Qualify by stack when a module runs PARALLEL same-module WIs on both stacks:
  `coder-<module>-backend` / `coder-<module>-frontend`.

**Master-child design runs**: each child architect writes under a module subpath:
`<ISOLATE_DIR>/worklog/<run-or-slug>/<module>/NNN-architect.md`. The master architect uses the
top-level dir (no `<module>` subpath): `<ISOLATE_DIR>/worklog/<run-or-slug>/NNN-architect.md`.

## When you WRITE (append, before EVERY exit - not only a successful one)

Log only **decisions that change the outcome or that a later phase must not re-litigate** - not
routine narration: an approach chosen AND the alternatives rejected; scope added or dropped; a
model-tier pick or downgrade; a cross-module impact found + its mitigation; a deliberate deviation
from a platform design principle + its justification; a test confirmed RED before code; a
BLOCKED/escalation - what was tried, what was ruled out and WHY, and the reasoning behind the
refusal itself.

**Every terminal status is an exit that owes an entry** - `DONE`, `BLOCKED`, `NEEDS_CONTEXT` and
`NEEDS_NEXT` alike; a step that ends before reaching its normal write point still writes at that
exit. A refusal owes one most: nothing resumes a worker, so its cold replacement inherits the files
it wrote plus this log and nothing else, while `blocked_reason` carries a single line. List the
entry you appended in your `produced` so the caller can find it.

Entry format (one per decision) - `<when>` is a `date -u +%H:%M:%S` stamp if you have a shell, else
the phase/step label (`Phase 0`, `Round 2`); pick exactly ONE verb:

```
- <when> | <agent> | DECIDED|DROPPED|ADDED|FLAGGED|VERIFIED | <what> | WHY: <reason> | EVIDENCE: <path | cmd | OSM citation>
```

`EVIDENCE` is the Completion-status #8 hook - cite a real path, command output, or OSM call, not
"looks right".

## When you READ (before you start)

Glob `<ISOLATE_DIR>/worklog/<run-or-slug>/*.md` (same captured ISOLATE literal as § Where it lives) and
read them oldest-first. They tell you what upstream phases decided so you build on - not against -
those decisions. If the dir is absent, you are the first writer - create it.

**Orphan sweep (the FIRST writer of a run does this, before creating the new dir above).**
`worklog/<run-or-slug>/` is never deleted by anything today, so a run's decision log leaks one
directory per run forever. Sweep stale siblings first:
`find <ISOLATE_DIR>/worklog/ -mindepth 1 -maxdepth 1 -type d -mmin +43200 -exec rm -rf {} +` (any
sibling `<run-or-slug>/` dir untouched for over 30 days is presumed consumed - a directory's own
mtime refreshes every time ANY writer appends a new per-writer file inside it, so a still-active
run is never touched). Full rule + bound rationale:
`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3. Enforcer: the
first agent that would otherwise create a NEW `<run-or-slug>/` dir - not a separate cleanup agent
or cron. A run resuming into an EXISTING dir (the common case - most runs are not the first
writer) does not re-run the sweep; only dir CREATION triggers it, so it fires once per run, not
once per writer.

## Relation to the blackboard

`run-<id>.json` is the driver-only state machine (only `run-harness` writes it). The worklog is the
human- and agent-readable narrative every participant writes. The driver stores the worklog dir path
in the blackboard so all nodes resolve the same dir; standalone, the skill derives it from its own
slug. The two never duplicate: blackboard = machine state, worklog = decision rationale.
