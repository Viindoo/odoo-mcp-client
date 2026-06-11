# Concurrency guard - the OOM envelope for agent fan-out (SSOT)

Root failure log: `unbounded-opus-fanout-oom` - unbounded OPUS fan-out crashed the
host. The guard has two modes; every skill that fans out agents references this
file instead of restating the numbers.

## Mode A - Agent-tool batching (legacy, default for un-migrated skills)

Cap at **3 concurrent** Agent-tool calls (or fork workers / parallel MCP legs);
for more work, batch in waves of <=3 (fire <=3, wait, fire the next <=3). Used
by: odoo-debug, odoo-code-review, workflow-chaining, odoo-brl (inner MCP
parallelism), and the YAML workflow fan-out ceiling (workflows/_schema.md,
docs/reference/workflow-harness.md).

## Mode B - model-weighted budget (rolling-window skills)

| model  | weight |
|--------|--------|
| haiku  | 1 |
| sonnet | 2 |
| opus   | 4 |
| fable  | 8 |

At most **8 weight-units** in flight at once => up to 8 haiku, 4 sonnet, 2 opus,
or exactly 1 fable (always exclusive). Mixing is allowed up to the budget. Worst
case (2 opus) sits within the historical envelope (old cap: 3 sonnet ~ weight 6).
Used by: odoo-coding (Workflow pipeline AND its Agent-tool fallback batches), wave.

If an OOM recurs under Mode B, lower BUDGET to 6 here (one place) - do not patch
individual skills.

## OSM version-pin race

`set_active_version` is server-side state scoped to the API KEY, not to the
calling agent or session. Under ANY concurrency - parallel agents in one run,
or two sessions sharing the key - `'auto'` may resolve to someone else's pin.

Rule for every agent and skill in this plugin: pass the CONCRETE Odoo version
on every OSM call; treat `'auto'` as unsafe and never instruct it. Still call
`set_active_version` once at bootstrap - it is the reachability probe and keeps
the server-side default sane - but never rely on its ambient state. Multi-version
flows (migrations, cross-version diffs) pass the explicit concrete version per
call - never the pin.

## Browser exclusivity (orthogonal)

Browser-driving agents (odoo-ui-debugger / odoo-ui-reviewer) are EXCLUSIVE-serial
regardless of mode - never two at once. That rule lives with those agents; this
file only governs OSM-only fan-out.
