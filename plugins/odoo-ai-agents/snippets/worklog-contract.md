# Worklog contract (decisions across agents)

The worklog carries the decisions of a run from one agent to the next, so a later phase builds on
them instead of re-deriving or reopening them. It is not the continuation block (status, produced,
next).

## Where it lives

`<ISOLATE_DIR>/worklog/<run-or-slug>/<NNN>-<agent>.md` - one file per writer, never a shared file.
`ISOLATE_DIR` is the captured literal of
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`.

- `<run-or-slug>`: the run id when a `run-<id>.json` exists, else the feature slug the skill uses
  for its artifacts.
- `<NNN>`: the dispatch order when the caller passed one, else a UTC time stamp or a short label;
  it only has to make the filename unique.
- `<agent>`: the writer's short name (`architect`, `coder-<module>`, `reviewer-<module>`),
  qualified by stack when two workers share a module.
- A master-child design: each child architect writes under `<run-or-slug>/<module>/`, the master
  at the top level.

## What you write, before every exit

One line per decision that changes the outcome or that a later phase must not reopen: the approach
chosen; scope added or dropped; a model tier picked or lowered; a cross-module impact and its
mitigation; a deliberate deviation from a design principle; the test leg's report lines
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md` § Break-check record) or why no
test was needed; a refusal - what was tried, what was ruled out and why.

```
- <when> | <agent> | DECIDED|DROPPED|ADDED|FLAGGED|VERIFIED | <what> | WHY: <reason> | EVIDENCE: <path, command or OSM citation>
```

Write the decision in force and the reason that holds, not the path that led to it. An alternative
you ruled out is written only when a later phase would otherwise propose it again: one line, with
the reason. Every terminal status owes an entry - a `BLOCKED` most of all, because a replacement
worker inherits only your files and this log. List the entry in `produced`.

## What you read, before you start

Every file under `<ISOLATE_DIR>/worklog/<run-or-slug>/`, oldest first. No directory: you are the
first writer - sweep sibling run directories untouched for more than 30 days
(`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3), then create it.
