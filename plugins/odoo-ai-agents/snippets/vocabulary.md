<!-- SSOT snippet. The single entry point for this plugin's cross-cutting status/gate/term
     vocabulary. Machine-consumed values (the status enum, the gate-reply sets) are declared in
     `generator/skill_tool_deps.json` -> `vocabulary` and rendered here for a human/agent reader;
     `phase`/`cluster`/`leaf` are declared HERE because nothing parses them. Every consumer POINTS
     at this file instead of restating any of the below - restating is how the plugin's vocabulary
     drifted into three incompatible status enums and three gate-reply sets. -->

# Vocabulary (SSOT index)

## Continuation status

`status` has exactly four values: `DONE`, `NEEDS_NEXT`, `BLOCKED`, `NEEDS_CONTEXT`.
`DONE_WITH_CONCERNS` is NOT one of them - it is RESERVED. To report a caveat on otherwise-complete
work, emit `status: DONE` plus a `concerns:` list (one line per caveat, naming the dimension and an
evidence path). Full schema + rules: `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`.

A `run-<id>.json` node's `status` is a DIFFERENT, wider enum: `PENDING | READY | RUNNING | DONE |
FAILED | SKIPPED | BLOCKED | NEEDS_CONTEXT`. Full schema: `docs/reference/workflow-harness.md` §8.

`DONE_WITH_CONCERNS` also names an UNRELATED field - `ODOO-AI-ETHOS.md` #10 Completion Status is a
human-facing self-report defined for every domain (engineering, sales, marketing, ...), not a
DAG-advance signal, and is out of this plugin's ownership. The two fields share a token; they are
not the same field.

## Gate-reply keywords

Two sets, no others - full statement + WHEN-to-use-which: `${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md`.

- PLAN gate: `approve / refine: [feedback] / cancel`
- STEP gate: `approve / skip / cancel`

`yes` is not a gate keyword.

## Overloaded terms

| Term | Normative meaning | Declared in |
|---|---|---|
| module | An Odoo addon. The install, test-selection and dependency unit - a PROPERTY of a node, never a unit of planning | `skills/_shared/odoo-module-graph.md` |
| work-item (WI) | The INNER unit: one disjoint file-set slice of ONE node's change. INTERNAL to `odoo-coder`, never surfaced to the plan or to any other node | `skills/_shared/odoo-module-graph.md` |
| node | One entry in `run-<id>.json` `nodes[]`; the OUTER unit of planning and execution | `docs/reference/workflow-harness.md` §8 |
| stage | A lifecycle position in the planner's Block-3 assignment | `agents/odoo-planner.md` |
| phase | A numbered step INSIDE one skill's pipeline. ALWAYS qualified by owner (e.g. "odoo-brl Phase A", "run-harness §8.1"). A bare "phase" with no owner is a defect | this file |
| cluster | A grouping INSIDE one skill, always qualified by owner (e.g. "review cluster", "doc-cluster") | this file |
| leaf | ALWAYS qualified: "agent-hierarchy leaf" (spawns nothing) / "module-graph leaf" (no unresolved `depends`) / "fan-out leaf" (a `context: fork` worker). A bare "leaf" with no qualifier is a defect | this file |

Bare-term detection for `phase`/`cluster`/`leaf` is deliberately NOT linted - the false-positive
rate on ordinary English prose would train contributors to ignore the lint. This table is a
review-time reference.
