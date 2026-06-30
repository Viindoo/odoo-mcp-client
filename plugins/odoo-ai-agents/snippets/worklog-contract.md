<!-- SSOT snippet. Referenced (not copy-pasted) by every spawner skill, every named agent,
     and every spawned worker brief (wave WI workers, odoo-coding fan-out, conflict resolver).
     Edit here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md. -->

# Worklog Contract (cross-agent decision log)

A multi-phase Odoo run spans several agents (architect -> test-author -> coder -> reviewer ->
debugger) and several waves of parallel workers. Each makes decisions the *next* one needs:
approach chosen vs rejected, scope added or dropped, model tier picked, cross-module impacts
found and mitigated. The Continuation Contract is a *handoff signal* (status/produced/next) - NOT
this. This is the **append-only decision journal** every agent reads before it starts and writes
when it finishes, so a later phase can look up *why* instead of re-deriving it.

## Where it lives

```
.odoo-ai/worklog/<run-or-slug>/<NNN>-<agent>.md     # one file per writer - never a shared file
```

- `<run-or-slug>`: the active run id when a `run-<id>.json` blackboard exists (the driver records
  the worklog dir there); otherwise the feature slug the skill already uses for its artifacts
  (e.g. the `<slug>-<date>` that `odoo-coding`/`odoo-code-review` write under), so the worklog
  sits beside the work it explains.
- `<NNN>`: an ordering prefix for chronological sort. Use the zero-padded dispatch order if the
  orchestrator passed one; else (the common case - most briefs carry only the worklog dir, not a
  sequence number) fall back to a `date -u +%H%M%S` stamp, or a short label when you have no shell.
  The HARD requirement is a UNIQUE filename per writer; the prefix only makes the sort best-effort,
  it is not a correctness invariant.
- `<agent>`: the writer's short name (`architect`, `coder-<module>`, `reviewer-<module>`,
  `wi-<id>`, ...). Combined with the prefix, two writers never collide on a filename.

**One file per writer is mandatory.** Parallel workers (rolling-window coders, wave WIs) would
race on a single shared file; per-writer files make every append conflict-free.

**Master-child design runs**: each child architect writes under a module subpath to prevent
collision across N parallel children:
`.odoo-ai/worklog/<run-or-slug>/<module>/NNN-architect.md`. The master architect uses the
top-level dir (no `<module>` subpath): `.odoo-ai/worklog/<run-or-slug>/NNN-architect.md`.

## When you WRITE (append, at end of your step)

Log only **decisions that change the outcome or that a later phase must not re-litigate** - not
routine narration. Concretely: an approach chosen AND the alternatives rejected; scope added or
dropped; a model-tier pick or downgrade (e.g. `fable declined -> opus`); a cross-module impact
found + its mitigation; a deliberate deviation from a platform design principle + its
justification; a test confirmed RED before code; a BLOCKED/escalation and what was tried.

Entry format (one per decision) - `<when>` is a `date -u +%H:%M:%S` stamp if you have a shell, else
the phase/step label (`Phase 0`, `Round 2`); pick exactly ONE verb:

```
- <when> | <agent> | DECIDED|DROPPED|ADDED|FLAGGED|VERIFIED | <what> | WHY: <reason> | EVIDENCE: <path | cmd | OSM citation>
```

Worked example:

```
- Round 2 | architect | DECIDED | extend sale.order via _inherit (not a new model) | WHY: the margin field belongs on the existing order | EVIDENCE: model_inspect(model='sale.order', method='summary', odoo_version='<version>')
```

`EVIDENCE` is the Completion-status #8 hook - cite a real path, command output, or OSM call, not
"looks right". The `<when>` prefix plus the per-writer filename already order writers, so a coarse
label is fine when no clock is available.

## When you READ (before you start)

Glob `.odoo-ai/worklog/<run-or-slug>/*.md` and read them oldest-first. They tell you what upstream
phases decided so you build on - not against - those decisions (understand intent
before acting). If the dir is absent, you are the first writer - create it.

## Relation to the blackboard

`run-<id>.json` is the driver-only state machine (only `run-harness` writes it). The worklog is the
**human- and agent-readable narrative** every participant writes. When a run is active, the driver
stores the worklog dir path in the blackboard so all nodes resolve the same dir; standalone, the
skill derives it from its own slug. The two never duplicate: blackboard = machine state, worklog =
decision rationale.
