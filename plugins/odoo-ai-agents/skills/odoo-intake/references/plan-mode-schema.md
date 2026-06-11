# Intake — Plan Mode Content Schema (writes-files Approach)

Load this when the approved Approach has `output_mode = writes-files` and you are writing the
implementation plan inside Plan Mode (step 3 of the Plan Mode procedure in SKILL.md). The plan
MUST contain three blocks. None is optional for a `writes-files` Approach.

**Block 1 — Workitem list.** Borrow the WI-Brief shape from `skills/wave/SKILL.md`
(~lines 174–219) and/or the requirement shape in `odoo-brl/reference/schema.md` (~lines
116–197). Each WI carries: `id`, a one-line description, and `files-in-scope` (the file sets
across WIs MUST be **disjoint**). For a multi-WI delivery also note worktree + branch + verify
command per WI (Repo Capability Card).

**Block 2 — Dependency graph.** Borrow the DAG schema from `odoo-brl/reference/schema.md`
(~lines 316–385): `nodes` + `edges` where each edge has a `type` of
`technical | business-logic | data-flow` and a `reason`; a `topological_order` (Kahn's
algorithm), a `critical_path`, and `cycles` (empty `[]` for a valid DAG — a cycle is reported,
never silently dropped). For only a few WIs, instead pick one of the four topologies in
`wave/reference/wave-templates.md` (~lines 29–92): **independent | linear | mixed | diamond**.
A mermaid diagram is encouraged.

**Block 3 — Assignment.** One line per WI:
`WI → skill | command | agent  (model from frontmatter, effort by legend) → which skill that agent uses`.
Add per-WI **acceptance criteria** + a **verify command** (Repo Capability Card). `model` is read
from the candidate's `SKILL.md`/`agents/*.md` frontmatter; `effort` follows the gap-analysis
legend (S/M/L/XL).

**Workflow-as-node in the schema (G-B):** when a WI's approach is a workflow-command, it is
**one WI** — `files-in-scope` = the workflow's `output_dir/` (one box). Do NOT expand the
workflow's internal phases into separate WIs (that would duplicate the phase logic that is SSOT
in the `.workflow.yaml` and break the disjoint-files invariant), and do NOT draw the workflow's
internal phase-sequence in Block 2 (that DAG is the workflow's own; here the workflow is a
single node that may have edges to OTHER WIs). Block 3 line: `WI → /<command> via
workflow-chaining (model per-phase in YAML, effort = total) → verify: artifact in output_dir`.

*Examples (short):*
- Full-stack feature → a single `WI: odoo-coding (sonnet, M)` — it adds the backend field/method
  AND renders the OWL widget, sequencing them internally (backend agent first, then frontend
  agent, so the field exists before the widget binds to it). No cross-WI edge needed.
- Three disjoint fixes (bug + test + docs) → `WI-A odoo-coding`, `WI-B odoo-coding`,
  `WI-C` docs edit; DAG: **independent** (no edges) → hand to `wave` for parallel delivery.

## Rejection flow

If the user refines or rejects in the Plan Mode UI (step 5), loop back to the
**soft-plan-gate**, not to execution: re-run the relevant part — pick a different skill, adjust
WI parameters (scope / files / assignment / effort), or `cancel`. Re-enter Plan Mode only once
the revised plan is re-approved at the text gate. Never dispatch a writes-files specialist off a
rejected plan.
