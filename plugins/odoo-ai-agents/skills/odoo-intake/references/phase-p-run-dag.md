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
   (harness §8.3). The plan's OUTER unit is the **node**, never the module (SSOT:
   `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md` § Two-tier decomposition axis). Emit
   ONE `nodes[]` entry per PLAN node, ONE-TO-ONE - never grouped, batched, or merged - with
   `depends_on` from the dependency graph, `approach`/`approach_kind` from the assignment, and
   `modules` carried straight from the plan node (the module technical names that node touches, in
   dependency order; omit for a node that touches no Odoo module). On a node whose `approach` is
   `odoo-instance`, `modules` IS that node's suite scope - copy it verbatim, never recompute it.
   **Serialize `repos[]` and every node's `repo`:**
   one `repos[]` entry per repository the plan's Block-2 `[repo: <repo>]` annotations name, each
   carrying that repo's Repo Capability Card (`id` + `base`/`verify`/`commit`/`confidential`/
   `worktree_root`, template in `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/run-integration.md`
   § Repo Capability Card Template - `id` is ORIGIN-DERIVED there, never invented from a directory
   name, a worktree path, or a series, and two entries that resolve to the SAME id are ONE repo:
   collapse them into one card, or STOP if their cards disagree). Stamp each node's `repo` from its
   own `[repo: ...]` annotation. **`repo: null` is legal ONLY for a node that writes into no
   repository tree and gates no repo's delivery** - the chat-only synthesis / routing / report node;
   every SOURCE-writing, `odoo-instance`, `integrate`, and terminal lifecycle node (review, i18n,
   acceptance, doc, lint, monitor, merge) MUST name a declared repo, and a `null` on any of them is a
   serialization bug that opens the PR without that stage having run. Rule owner (do not restate a
   competing version): `${CLAUDE_PLUGIN_ROOT}/docs/reference/workflow-harness.md` §8.3 §
   `repo: null` legality - `run-harness` re-derives the SAME predicate at dispatch and fails the run
   BLOCKED on an illegal `null`, so a mis-stamped node is caught whether or not it reaches the
   auditor.
   Emit exactly ONE `integrate` node per `repos[]` entry: N repos = N integrate nodes = N PRs; a
   single-repo run is a one-entry list and one `integrate`. Every terminal lifecycle stage (doc /
   i18n / acceptance / review / lint / monitor / merge) is its own node, tagged with its repo. The
   work-item never appears at this layer - it is `odoo-coder`'s INTERNAL intra-node unit. The
   `<id>` is `<short-intent-slug>-<YYYYMMDD>-<4 random chars>` (e.g. `add-priority-20260607-a3f1`) so
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
     using the identical "ingest by pointer" procedure as the **Non-trivial path** bullet directly
     above - never hand-author the plan inline.
   - **Decision X (node inputs):** each node carries `inputs: {effort, est_agents}` (ADVISORY /
     du kien) and **no binding `model`, and NO `gate_tier`** - the dispatched specialist skill owns
     the actual model + agent count at runtime, and the tier is a total function resolved at dispatch
     (`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` § Gate-tier resolution); the run-node never
     pins any of the three.
   - **Recon pointer (additive, optional).** When Phase R persisted a findings file, add
     `inputs.recon_findings: <captured ABSOLUTE literal>` to every node that consumes recon. It MUST
     be the captured absolute path - never a `<ISOLATE_DIR>` placeholder and never a relative path: a
     leaf in another worktree cannot re-resolve it. Absent key -> the node scouts for itself, as
     today. This adds a key; it does not change who first writes `run-<id>.json`.
   - **Survey pointer (opt-in, ALWAYS an explicit key - never omitted, unlike Recon above).**
     When the Proposed Plan's `Survey:` field (`SKILL.md` § Deep survey) resolved to a synthesis
     path this session, add `inputs.survey: <captured ABSOLUTE literal>` to every coding node
     and the review node. When no deep survey was opted into, set `inputs.survey: "none"`
     explicitly on those same nodes instead of omitting the key: `inputs.recon_findings` is safe to
     omit because the mandatory recon step always scouts for itself when absent, but a downstream
     per-node brief (`odoo-coding`'s `SURVEY:` field) treats an OMITTED artifact-path key as a
     load-bearing gap (`dispatch-brief.md`'s self-check) rather than "nobody asked" - so this key is
     always present, one explicit value or the other. Threaded onward exactly like `design_index`
     above: the receiving skill (`odoo-planner`'s `SURVEY:` field, `odoo-coding`'s per-node
     `SURVEY:` field) reads it by pointer, never re-derives a survey.
2. For each SOURCE-writing node (writes outside the `$ODOO_AI_HOME` state root) that is NOT a
   self-provisioning specialist (SSOT set: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` §
   Self-provisioning specialists), set `inputs.needs_worktree: true`. `run-harness` provisions the
   actual worktree/branch at dispatch (its Hard rule 6); Phase P only RECORDS the requirement - it
   does not run git. **Phase P computes NO gate tier, here or anywhere** - the field is deleted from
   the schema; the tier is a total function resolved at dispatch
   (`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` § Gate-tier resolution). Do not tag a
   `gate_tier` on any node.
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
