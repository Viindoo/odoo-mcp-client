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
1. Serialize the approved 3-block plan into `<ISOLATE_DIR>/run-<id>.json` (resolve `<ISOLATE_DIR>`/`<SHARE_DIR>` via the resolve-capture-substitute protocol in `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`) per the blackboard schema
   (harness §8.3). The plan's OUTER unit is the MODULE, never a work-item (SSOT:
   `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md` § Two-tier decomposition axis). Emit
   one `nodes[]` entry per plan node, with `depends_on` from the dependency graph and
   `approach`/`approach_kind` from the assignment. **Serialize `repos[]` and every node's `repo`:**
   one `repos[]` entry per repository the plan's Block-2 `[repo: <repo>]` annotations name, each
   carrying that repo's Repo Capability Card (`id` + `base`/`verify`/`commit`/`confidential`/
   `worktree_root`, template in `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/wave-integration.md`
   § Repo Capability Card Template); stamp each node's `repo` from its own `[repo: ...]` annotation,
   or `null` when the node belongs to no repository (a chat-only synthesis / routing node - it is
   then outside EVERY repo's `integrate` readiness scope and is never provisioned a worktree). A
   `wave` or `integrate` node ALWAYS names a declared repo - `null` there is a serialization bug.
   Emit exactly ONE `integrate` node per `repos[]` entry: N repos = N integrate nodes = N PRs; a
   single-repo run is a one-entry list and one `integrate`. **PRESERVE the Block 2 `Wave N` grouping:** the
   coding modules within one `Wave N` are grouped into a SINGLE wave node (`approach_kind: wave`)
   that carries the wave's MODULES + their module-DAG + `topology` (value set and the `n <= 1`
   collapse rule are owned by `run-harness/references/wave-integration.md` § Topology values - not
   restated here) + `cumulative_modules` (regression scope, NEVER the topology count) + the
   Block-2W lineage slice - this is the wave node `run-harness` drives via its § Between-wave
   integration (it iterates the wave's modules and invokes `odoo-coding` per module; there is no
   separate git-executor skill). A terminal lifecycle stage (doc / i18n /
   acceptance / PR / monitor / merge) is its own node, tagged with its repo. Serialize each terminal
   `integrate@R` node's `depends_on` to AGREE with the driver's `integrate` readiness precondition - declared in
   `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` § Gate-tier resolution, not restated here -
   which `run-harness` RE-DERIVES anyway: under-specifying it cannot open the PR early, but naming a
   land-tail node in it deadlocks the run. The work-item never appears at this layer - it
   is `odoo-coder`'s INTERNAL intra-module unit. The `<id>` is
   `<short-intent-slug>-<YYYYMMDD>-<4 random chars>` (e.g. `add-priority-20260607-a3f1`) so
   concurrent runs never collide.
   - **Non-trivial path (plan authored by `odoo-planning`):** ingest the planner artifact BY
     POINTER - read the approved 3-block plan from `<SHARE_DIR>/plans/<slug>-<date>.md` and serialize
     its modules/DAG/assignment directly. Do NOT re-derive the DAG from chat text; the planner
     already produced the canonical 3-block (it does not serialize `run-<id>.json` itself -
     serialization stays here, in one place).
   - **Trivial single-module path (inline micro-plan):** still delegate 3-block authoring to
     `odoo-planning` via the **Skill tool** - WITHOUT `plan_mode_active` (never pre-open Plan Mode
     on its behalf; `odoo-planning` is the sole enterer per `planning-gate-contract.md` § Plan-Mode
     enter/exit) - there is NO trivial/size/module-count bypass (`planning-gate-contract.md` §
     Mandatory-planning rule); it emits the minimal `[code, review, integrate]` plan. Once
     `odoo-planning` returns its plan pointer
     (`<SHARE_DIR>/plans/<slug>-<date>.md`), ingest it BY POINTER and serialize it into `run-<id>.json`
     using the identical "ingest by pointer" procedure as the non-trivial path directly above
     (`phase-p-run-dag.md:43-47`) - never hand-author the plan inline.
   - **Decision X (node inputs):** each node carries `inputs: {effort, est_agents}` (ADVISORY /
     du kien) and **no binding `model`** - the dispatched specialist skill owns the actual model +
     agent count at runtime; the run-node never pins them.
   - **Recon pointer (additive, optional).** When Phase R persisted a findings file, add
     `inputs.recon_findings: <captured ABSOLUTE literal>` to every node that consumes recon. It MUST
     be the captured absolute path - never a `<ISOLATE_DIR>` placeholder and never a relative path: a
     leaf in another worktree cannot re-resolve it. Absent key -> the node scouts for itself, as
     today. This adds a key; it does not change who first writes `run-<id>.json`.
   - **Survey pointer (opt-in, ALWAYS an explicit key - never omitted, unlike Recon above).**
     When the Proposed Plan's `Survey:` field (`SKILL.md` § Deep survey) resolved to a synthesis
     path this session, add `inputs.survey: <captured ABSOLUTE literal>` to every coding-wave node
     and the review node. When no deep survey was opted into, set `inputs.survey: "none"`
     explicitly on those same nodes instead of omitting the key: `inputs.recon_findings` is safe to
     omit because the mandatory recon step always scouts for itself when absent, but a downstream
     per-module brief (`odoo-coding`'s `SURVEY:` field) treats an OMITTED artifact-path key as a
     load-bearing gap (`dispatch-brief.md`'s self-check) rather than "nobody asked" - so this key is
     always present, one explicit value or the other. Threaded onward exactly like `design_index`
     above: the receiving skill (`odoo-planner`'s `SURVEY:` field, `odoo-coding`'s per-module
     `SURVEY:` field) reads it by pointer, never re-derives a survey.
2. Tag each node's `gate_tier` from the registry `default_gate_tier`
   (`generator/skill_tool_deps.json`), raising it if the node writes outside the `$ODOO_AI_HOME` state root.
   - For each SOURCE-writing node (writes outside the `$ODOO_AI_HOME` state root) that is NOT a self-provisioning
     specialist (SSOT set: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § Self-provisioning
     specialists), set `inputs.needs_worktree: true`. `run-harness` provisions the actual
     worktree/branch at dispatch (its Hard rule 6); Phase P only RECORDS the requirement - it does
     not run git.
3. Set `autonomy`, `budget` (`max_nodes` ≈ 2× node count), `status: NEEDS_NEXT`.
4. If `--plan`: stop here (the DAG file is the deliverable). Otherwise NL-dispatch `run-harness`,
   which walks the DAG to DONE/BLOCKED/NEEDS_CONTEXT.

**Handoff:** intake writes the file and hands off to `run-harness`, which walks the DAG and
dispatches each node to specialists (as subagents or Skill-tool invocations). intake
never spawns the specialists itself here - it persists the plan and yields to the driver.
Phase P is the SINGLE place the approved plan becomes a `run-<id>.json`. Why `odoo-planning` routes
its approved plan here (`next: odoo-intake`) and NOT straight to `run-harness`: rationale SSOT is
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-planning/SKILL.md` § Continuation Contract.

**Workflow-as-node (G-B):** a workflow-command (e.g. `/odoo-respond-bid`) is ONE node at the
DAG level - its internal phases are SSOT inside the `.workflow.yaml` (gated by
`workflow-chaining`), never expanded into separate nodes. Routing:
- single workflow node, NO `on_complete` declared → hand the YAML name straight to
  `workflow-chaining` (it self-gates each phase); no run file needed.
- single workflow node WITH `on_complete` declared → engage Phase P anyway (trigger 3 above):
  the 1-node RUN-DAG is cheap (the run-harness picks the one node, dispatches `workflow-chaining`,
  then reads the emitted `next[]`), and it is the only way the cross-workflow chain auto-advances
  instead of degrading to a human suggestion.
- a workflow node sitting in a `>=2`-node DAG → just one node in that DAG; `run-harness`
  dispatches it via `approach_kind: workflow` and advances on its Continuation Contract.
