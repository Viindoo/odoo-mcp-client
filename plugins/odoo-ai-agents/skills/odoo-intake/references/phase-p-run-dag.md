# Intake - Phase P: serialize the approved plan into a run file

Load this when the approved plan is a `writes-files` Approach. Phase P writes
`<ISOLATE_DIR>/run-<id>.json` once; the main agent then runs it per
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Running the plan.
Schema: that file's § Run file.

**Autonomy dial** - parse from the user prompt (default `--auto`):
- `--auto` (default): run to done; stop only at the human gates of § Running the plan step 7 and
  on `BLOCKED` / `NEEDS_CONTEXT`.
- `--step`: ask before every node that writes a file.
- `--plan`: write the run file and STOP; do not run it.

**When Phase P engages** (after plan approval), if ANY holds: (1) `node_count >= 2`; (2) a single
`output_mode == writes-files` node; (3) a single workflow node whose YAML declares `on_complete`
(its `next[]` only advances inside a run). Otherwise SKIP: a single chat-only node fires the
specialist on the next turn with no run file, and does not materialize its `next[]`.

**Procedure:**
1. Resolve `<ISOLATE_DIR>` / `<SHARE_DIR>` once (`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`).
   Read the approved plan BY POINTER from `<SHARE_DIR>/plans/<slug>-<date>.md` - the planner's
   file is canonical, never re-derived from chat text; a one-node change takes the same path
   (the main agent fills the default tail into a plan file first). The `<id>` is
   `<short-intent-slug>-<YYYYMMDD>-<4 random chars>`.
2. Emit ONE `nodes[]` entry per plan node, one-to-one, with every Block 1 field copied verbatim
   (`id`, `repo`, `approach`, `approach_kind`, `agent`, `mode`, `model`, `build_tier_hint`,
   `business_function`, `audience`, `when`, `modules`, `files_in_scope`, `depends_on`) and
   `inputs` holding `objective`, `acceptance` (with their SRS or design pointers), `survey`
   (`none` when none), `recon_findings` (the captured absolute path when Phase R persisted one)
   and `needs_worktree: true` on every source-writing node that is not a self-provisioning
   specialist (`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § Self-provisioning specialists).
   On an `odoo-instance` node `modules` IS the suite scope - copied, never recomputed. A workflow
   is ONE node (`approach_kind: workflow`); its phases stay in the `.workflow.yaml`.
3. Emit `repos[]`: one Repo Capability Card per repository the plan's `[repo: ...]` tags name
   (`id` origin-derived from the remote URL, never from a directory, worktree or series; two tags
   resolving to one id are one card), `base`, `verify`, `commit`, `confidential`, and
   `worktree_root` from `project_dir` axis `worktree`. Exactly ONE `integrate` node per card: N
   repos = N PRs. `repo: null` only on a node that writes into no repository and gates no
   delivery; every source-writing, verification, `integrate` and tail node names a card.
4. Set `autonomy`, `budget` (`max_nodes` about 2x the node count), `status: NEEDS_NEXT`,
   `cursor` = the first ready node. Write the file.
5. `--plan`: stop here. Otherwise continue in the same context per § Running the plan.

Intake writes the file and runs the plan itself; it never launches a driver and never spawns the
specialists outside the loop. `odoo-planning` routes its approved plan here (`next: odoo-intake`)
because serialization lives in one place.
