# Intake - Plan Mode Content Schema (writes-files Approach)

Load this when the approved Approach has `output_mode = writes-files` and you are writing the
implementation plan inside Plan Mode (step 3 of the Plan Mode procedure in SKILL.md). The plan
MUST contain three blocks. None is optional for a `writes-files` Approach.

**Run header (required on every `writes-files` plan, ABOVE Block 1).**
`odoo_version: <concrete series, e.g. 18.0>`; optional `viindoo_profile: <name|none>`,
`grounding: osm | local-source | standalone`. Resolve `odoo_version` via
`${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md` (`.odoo-ai/context.md` -> manifest
`version` -> ask the user) - NEVER a silent default. `odoo-planner` already emits this as a
prose header (`agents/odoo-planner.md:127`); this run header promotes it INTO the documented
schema so `odoo-wave` / `odoo-coding` read it as a field, not a header line they must guess.
Read-only/chat Approaches never load this schema and carry no such field.

**Block 1 - Workitem list.** Borrow the WI-Brief shape from `skills/odoo-wave/SKILL.md`
(~lines 174-219) and/or the requirement shape in `odoo-brl/reference/schema.md` (~lines
116-197). Each WI carries: `id`, a one-line description, and `files-in-scope` (the file sets
across WIs MUST be **disjoint**). For a multi-WI delivery also note worktree + branch + verify
command per WI (Repo Capability Card).

**Block 2 - Dependency graph.** Borrow the DAG schema from `odoo-brl/reference/schema.md`
(~lines 316-385): `nodes` + `edges` where each edge has a `type` of
`technical | business-logic | data-flow` and a `reason`; a `topological_order` (Kahn's
algorithm), a `critical_path`, and `cycles` (empty `[]` for a valid DAG - a cycle is reported,
never silently dropped). For only a few WIs, instead pick one of the four topologies in
`odoo-wave/reference/wave-templates.md` (~lines 29-92): **independent | linear | mixed | diamond**.
A mermaid diagram is encouraged.

**Block 3 - Assignment.** One line per WI:
`WI → skill | command | agent  (effort + est_agents ESTIMATE; model + count owned by the dispatched skill at runtime - ADVISORY / du kien, non-binding) → which skill that agent uses`.
Add per-WI **acceptance criteria** + a **verify command** (Repo Capability Card). `effort` follows
the gap-analysis legend (S/M/L/XL); `est_agents` is a rough advisory count. The plan binds WHICH
skill, never a per-agent `model` or fan-out `count` - the dispatched specialist skill owns those at
runtime (Decision X). Each **coding-wave** node also carries **`cumulative_modules`** - the union of
every module THIS wave touched AND every module ALL PRIOR waves touched. It is the growing regression
scope the git-executor (`odoo-wave` Phase 4.4) runs GREEN to close the wave; it is STRUCTURAL scope
like `depends_on` (WHICH modules must stay green), NOT a binding `model`/`count` (no Decision X
conflict), and it surfaces the regression scope to the human at plan-approval time. For a NON-TRIVIAL
multi-module change this 3-block plan is AUTHORED by
`odoo-planning` (its `odoo-planner` agent); for a trivial single-WI change `odoo-intake` writes it
inline. Either path CONFORMS to this same schema - never a second format.

**Terminal `integrate` land node (every `writes-files` plan).** The plan does not end at `review`;
it carries a terminal `integrate` node so the change is committed AND landed. A trivial single-WI
inline micro-plan is therefore `[code, review, integrate]`. `integrate` is the SAME land tail the
full lifecycle and `odoo-wave` use: after review is clean, `run-harness` invokes `git-toolkit:git-ops`
to push the WI branch and open a PR against the principal branch, then emits a Continuation-Contract
`next` -> `odoo-pr-monitoring` at `gate_tier: L2` (the single outward merge gate). No squash machinery
is needed for one reviewed commit. This is the ONE land mechanism (git-ops open-PR ->
`odoo-pr-monitoring` merge); there is no local merge to the principal. Block 3 line:
`integrate -> run-harness invokes git-toolkit:git-ops (push + open PR) -> next: odoo-pr-monitoring @ L2`.

**Workflow-as-node in the schema (G-B):** when a WI's approach is a workflow-command, it is
**one WI** - `files-in-scope` = the workflow's `output_dir/` (one box). Do NOT expand the
workflow's internal phases into separate WIs (that would duplicate the phase logic that is SSOT
in the `.workflow.yaml` and break the disjoint-files invariant), and do NOT draw the workflow's
internal phase-sequence in Block 2 (that DAG is the workflow's own; here the workflow is a
single node that may have edges to OTHER WIs). Block 3 line: `WI → /<command> via
workflow-chaining (model per-phase in YAML, effort = total) → verify: artifact in output_dir`.

*Examples (short):*
- Full-stack feature → a single `WI: odoo-coding (sonnet, M)` - it adds the backend field/method
  AND renders the OWL widget, sequencing them internally (backend agent first, then frontend
  agent, so the field exists before the widget binds to it). No cross-WI edge needed.
- Three disjoint fixes (bug + test + docs) → `WI-A odoo-coding`, `WI-B odoo-coding`,
  `WI-C` docs edit; DAG: **independent** (no edges) → the internal `odoo-wave` executor delivers them in parallel (run-harness dispatches it from the approved plan; the user never invokes it).

## Rejection flow

If the user refines or rejects in the Plan Mode UI (step 5), loop back to the
**soft-plan-gate**, not to execution: re-run the relevant part - pick a different skill, adjust
WI parameters (scope / files / assignment / effort), or `cancel`. Re-enter Plan Mode only once
the revised plan is re-approved at the text gate. Never dispatch a writes-files specialist off a
rejected plan.
