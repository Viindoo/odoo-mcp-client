# Intake - Phase P: RUN-DAG persistence + drive-to-done (optional, additive)

Load this only when the approved plan is multi-step or the user wants hands-off execution. It
turns an approved plan into a self-advancing run, and is **purely additive**: a single-step plan
still dispatches exactly as before. Full schema + loop: `docs/reference/workflow-harness.md` §8.

**Autonomy dial** - parse from the user prompt (default `--auto`):
- `--auto` (default): drive to done; auto-pass L0/L1 nodes; stop only at L2 gates + BLOCKED.
- `--step`: gate every node ≥ L1 (this is today's behaviour - safest).
- `--plan`: emit the RUN-DAG and STOP; do not run the driver.

**When to engage Phase P** (decidable rule - the autonomy dial is NOT a trigger; it is only
recorded in `run.json` once engaged). After the plan is approved, ENGAGE Phase P if ANY holds:
1. `node_count >= 2` (multi-step - needs DAG sequencing / `next[]` materialization), OR
2. a single node whose `output_mode == writes-files` (needs gate-tier tracking + a driver to
   catch any runtime `next[]`), OR
3. a single node that is a workflow (`approach_kind == workflow`) whose YAML declares
   `on_complete` (needs the run-harness present to dispatch the cross-workflow chain - see
   "workflow-as-node" below).

SKIP Phase P (dispatch directly, as today - no run file, no driver) ONLY when the plan is a
single node AND `output_mode == chat-only` AND it is not a workflow-with-`on_complete`. A
single chat-only node fires the specialist on the next turn; `--auto` on it is a harmless no-op
(nothing to drive). Note: a directly-dispatched single node does NOT materialize its
Continuation Contract `next[]` - if a step emits a `next[]` worth chaining, re-run `/odoo-intake` to
open a RUN-DAG.

**Procedure** (when Phase P is engaged):
1. Serialize the approved 3-block plan into `.odoo-ai/run-<id>.json` per the blackboard schema
   (harness §8.3): one `nodes[]` entry per workitem, with `depends_on` from the dependency graph
   and `approach`/`approach_kind` from the assignment. The `<id>` is
   `<short-intent-slug>-<YYYYMMDD>-<4 random chars>` (e.g. `add-priority-20260607-a3f1`) so
   concurrent runs never collide.
   - **Non-trivial path (plan authored by `odoo-planning`):** ingest the planner artifact BY
     POINTER - read the approved 3-block plan from `.odoo-ai/plans/<slug>-<date>.md` and serialize
     its workitems/DAG/assignment directly. Do NOT re-derive the DAG from chat text; the planner
     already produced the canonical 3-block (it does not serialize `run-<id>.json` itself -
     serialization stays here, in one place).
   - **Trivial single-WI path (inline micro-plan):** serialize `odoo-intake`'s own inline 3-block
     micro-plan exactly as before - unchanged.
   - **Decision X (node inputs):** each node carries `inputs: {effort, est_agents}` (ADVISORY /
     du kien) and **no binding `model`** - the dispatched specialist skill owns the actual model +
     agent count at runtime; the run-node never pins them.
2. Tag each node's `gate_tier` from the registry `default_gate_tier`
   (`generator/skill_tool_deps.json`), raising it if the node writes outside `.odoo-ai/`.
3. Set `autonomy`, `budget` (`max_nodes` ≈ 2× node count), `status: NEEDS_NEXT`.
4. If `--plan`: stop here (the DAG file is the deliverable). Otherwise NL-dispatch `run-harness`,
   which walks the DAG to DONE/BLOCKED/NEEDS_CONTEXT.

**Handoff:** intake writes the file and hands off to `run-harness`, which walks the DAG and
dispatches each node to specialists (as subagents or Skill-tool invocations). intake
never spawns the specialists itself here - it persists the plan and yields to the driver.
Phase P is the SINGLE place the approved plan becomes a `run-<id>.json`: `run-harness` is dispatched
ONLY after step 1 has serialized that file (it walks an existing run file and never ingests a plan
`.md` directly). So when `odoo-planning` finishes the non-trivial path, it routes its approved plan
here (`next: odoo-intake`) - NOT straight to `run-harness` - and Phase P serializes it, then drives.

**Workflow-as-node (G-B):** a workflow-command (e.g. `/odoo-respond-bid`) is ONE node at the
DAG level - its internal phases are SSOT inside the `.workflow.yaml` (gated by
`workflow-chaining`), never expanded into separate WIs. Routing:
- single workflow node, NO `on_complete` declared → hand the YAML name straight to
  `workflow-chaining` (it self-gates each phase); no run file needed.
- single workflow node WITH `on_complete` declared → engage Phase P anyway (trigger 3 above):
  the 1-node RUN-DAG is cheap (the run-harness picks the one node, dispatches `workflow-chaining`,
  then reads the emitted `next[]`), and it is the only way the cross-workflow chain auto-advances
  instead of degrading to a human suggestion.
- a workflow node sitting in a `>=2`-node DAG → just one node in that DAG; `run-harness`
  dispatches it via `approach_kind: workflow` and advances on its Continuation Contract.
