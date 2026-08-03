# Plan Mode Content Schema (writes-files Approach)

**SSOT owned by `odoo-planning`** (authored by its `odoo-planner` agent). Physically hosted here
under `skills/odoo-intake/references/` for backward-compat with intake Plan Mode and the
`docs/reference/workflow-harness.md` labeled-pointer - do NOT relocate it (`agents/odoo-planner.md`
forbids relocation). Edit the schema here; every other site points at this file.

Load this when the approved Approach has `output_mode = writes-files` and the plan is being written
inside Plan Mode (step 3 of the Plan Mode procedure in SKILL.md). The plan MUST contain three
blocks. None is optional for a `writes-files` Approach.

**Run header (required on every `writes-files` plan, ABOVE Block 1).**
`odoo_version: <concrete series, e.g. 18.0>`; optional `viindoo_profile: <name|none>`,
`grounding: osm | local-source | standalone`. Resolve `odoo_version` via
`${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md` (`<SHARE_DIR>/context.md` -> manifest
`version` -> ask the user; resolve `<SHARE_DIR>` via the resolve-capture-substitute protocol in
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`) - NEVER a silent default. This run header is a documented schema field
so `run-harness` / `odoo-coding` read it as a field, not a header line they must guess. Read-only/chat
Approaches never load this schema and carry no such field.

**Block 1 - Module list.** The plan's unit is the **module**, not a work-item: the OUTER
decomposition axis is module-only (SSOT: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md`
§ Two-tier decomposition axis - the work-item is `odoo-coder`'s INTERNAL intra-module unit and never
appears in the plan). Borrow the requirement shape in `odoo-brl/reference/schema.md` (~lines
116-197). Each module entry carries: `id` (the module name), a one-line description, and
`files-in-scope` (each module owns a directory, so module file-sets are naturally **disjoint**; a
terminal lifecycle node - doc / i18n / acceptance / integrate - is its own entry). For a multi-module
delivery also note worktree + branch + verify command per module (Repo Capability Card).

**Block 2 - Dependency graph.** Borrow the DAG schema from `odoo-brl/reference/schema.md`
(~lines 316-385): `nodes` (= modules) + `edges` where each edge has a `type` of
`technical | business-logic | data-flow` and a `reason`; a `topological_order` (Kahn's
algorithm), a `critical_path`, and `cycles` (empty `[]` for a valid DAG - a cycle is reported,
never silently dropped). For only a few modules, instead set the wave's `topology` to one of the values declared in
`run-harness/references/wave-integration.md` § Topology values (that file is the enum's ONE owner - do
not restate the value list here). **Operative MUST:** when a wave dispatches `n <= 1` modules,
`topology` is `single` - the wave collapses to a direct dispatch into the integration worktree, with no
child worktree and no cherry-pick. `n` is `len(this wave's modules)`; `cumulative_modules` is a
regression-scope union and is NEVER the count. This governs the single-module plan too: the minimal
`[code, review, integrate]` plan is a `single`-topology wave.

**REQUIRED - module-DAG ASCII dependency-graph block.** Every `writes-files` plan MUST render Block
2 with a fenced ```` ```text ```` ASCII dependency-graph of the module-DAG (NOT mermaid - mermaid
does not render in the plan file or the terminal where the human reviews the plan). Nodes = modules;
each node marked `(NEW)`/`(existing)` and tagged `[skill: <execute-skill>]`; nodes grouped under
`Wave N` headers; the `depends` direction shown per node (a `depends-on:` line) AND as a flat edge
list (`X --> Y` = Y depends on X, X builds first). ASCII only (ETHOS rule 0): use only `-`, `|`,
`+`, `>`, `[`, `]` - NO box-drawing Unicode. Exact template (reusable verbatim):

````
## Block 2 - Dependency graph (wave-batched module-DAG)
<typed-edge DAG or topology, as above>

```text
Module dependency graph
  Legend: [module] (NEW|existing) [skill: <execute-skill>] ; "X --> Y" = Y depends on X (X builds first)
  Waves run top-to-bottom; modules within a wave are independent - build ORDER is unconstrained
  (run-harness still dispatches them SEQUENTIALLY, ONE AT A TIME - not concurrently).

  Wave 1
    [viin_fleet_billing] (NEW) [skill: odoo-coding]
        depends-on: (none)

  Wave 2
    [viin_fleet_billing_account] (NEW) [skill: odoo-coding]
        depends-on: viin_fleet_billing
    [viin_fleet_billing docs] (existing) [skill: odoo-doc-illustration]
        depends-on: viin_fleet_billing

  Wave 3 (terminal lifecycle)
    [cluster acceptance] [skill: odoo-acceptance]
        depends-on: viin_fleet_billing_account, viin_fleet_billing docs

  Edges (depends direction; flat list for grep/diff stability):
    viin_fleet_billing         --> viin_fleet_billing_account
    viin_fleet_billing         --> viin_fleet_billing docs
    viin_fleet_billing_account --> cluster acceptance
    viin_fleet_billing docs    --> cluster acceptance
```
````

**Data source (never hand-drawn).** The dep-graph is DERIVED from the design's `dag_layers`
(`${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md` `index.yaml`, the LOGICAL truth)
grouped into integration waves - OR, for the few-module topology path, from the plan's own
`topological_order` - PLUS the Block 3 `module/stage -> SKILL` assignment for each `[skill: ...]`
tag. NEW vs existing comes from the module-graph resolution
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md`: a module resolving to NEITHER OSM NOR
disk is `(NEW)`; otherwise `(existing)`). Terminal lifecycle nodes (doc, i18n, acceptance,
PR/monitor/merge) appear as their own nodes wired to their execute-SKILL.

**Master-child reconciliation (extend, not fork).** The dep-graph is a RENDERING of `index.yaml`
`dag_layers`; it adds no field to `index.yaml` and introduces no second DAG schema - the `[skill:]`
tag and the Block 3 line are two renderings of the ONE assignment, never two sources.

**Block 2W - Worktree dependency graph (a SECOND projection alongside the Block-2 module-DAG).**
Every `writes-files` plan with more than one coding wave MUST also render a **Block 2W** worktree
dependency graph, authored by `odoo-planner` **IN PARALLEL** with the Block-2 module-DAG from the
SAME `dag_layers` / wave grouping. It adds NO new field to `index.yaml` and NO second DAG source -
it is the wave grouping **re-projected onto worktree lineage**, the same "extend, not fork"
reconciliation Block 2 uses. Block 2W is **SYMBOLIC**: it carries worktree **TOPOLOGY + LIFECYCLE**
(node names, fork-from lineage, cherry-pick-into points, the per-wave integration node, and the
loop) but NEVER concrete ref **STATE** - no SHAs, no branch tips, no resolved worktree filesystem
paths, no lease tokens; those are RUNTIME, resolved by the executor. Because the topology is a
**deterministic function of the wave grouping** (same `dag_layers` -> same waves -> same fork
lineage), the plan stays as reproducible as Block 2 itself.

Nodes (all SYMBOLIC - names, never SHAs/paths):
- `base` - the run's base ref: the version-named main branch, resolved per
  `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § Base-branch resolution - **never** "whatever
  the invoking checkout currently has checked out". One root.
- `run-integration` - ONE per run: forked from `base` at run start, it is the cherry-pick target for
  EVERY wave and the branch the terminal `integrate` land-tail squashes + pushes as the run's ONE PR.
  (There is NO per-wave integration branch.)
- `worktree(m)@wave-N` - one per module `m` built in wave N.

Edges (three kinds, all symbolic):
- **fork-from** (`==>`, lineage): `run-integration ==> base` (ONCE at run start); and every module
  worktree `worktree(m)@wave-N ==> run-integration` - EVERY wave's worktrees fork from the ONE
  run-integration branch, which already holds all PRIOR waves' cherry-picked code. This is the
  fork-from-integrated-parent property (now on ONE branch): a dependent wave builds on its
  dependencies' already-integrated SOURCE by construction, but that source reaches the addons-path
  only as a POLICY step - the per-module brief must carry `WORKTREE_PATH` + `SELF_PROVISION:
  worktree-addons`, which `odoo-coding` sets on every such dispatch (never a structural guarantee of
  the fork itself - though `scripts/lib/allocator.py`'s `_addons_path_worktree_mismatch` guard
  provides a belt-and-braces backstop for the override-less case; exact scope, and the one case
  where this policy step remains the SOLE protection: `snippets/instance-handle-contract.md` §
  Worktree-addons carve-out - not restated here). With that step taken, the cross-wave "dependency
  absent" BLOCKED path (the ledger's decision-table case 4) no longer fires intra-run.
- **cherry-pick-into** (`-->`): `worktree(m)@wave-N --> run-integration` (the coder's module commit
  is cherry-picked onto the ONE run-integration branch, in module-DAG topo order).
- **close** (per wave): `run-integration` -> {integrated cross-cutting review, cumulative close-gate}
  -> AUTO-ADVANCE to the next wave (NO per-wave PR); the next wave's worktrees fork from the same
  run-integration branch. After the FINAL wave, the terminal `integrate` land-tail squashes
  run-integration + opens the run's ONE PR.

Render Block 2W as a fenced ```` ```text ```` block (ASCII only, ETHOS rule 0), mirroring Block-2
style (reusable template):

```text
Worktree dependency graph  (symbolic lineage; "==>" fork-from, "-->" cherry-pick-into)
  base
    ==> run-integration                                  # forked ONCE at run start
          <-- worktree(mod_a)@w1        (forks run-integration; commit cherry-picked back)
          <-- worktree(mod_b)@w1
        [close w1: integrated review + cumulative gate {mod_a,mod_b} -> AUTO-ADVANCE, no PR]
          <-- worktree(mod_c)@w2        (mod_c depends mod_a; mod_a already on run-integration)
        [close w2: integrated review + cumulative gate {mod_a,mod_b,mod_c} -> AUTO-ADVANCE, no PR]
  After the FINAL wave: integrate land-tail -> squash run-integration + fresh first-push + open ONE PR
  Loop: build+commit (odoo-coder) -> cherry-pick onto run-integration -> close -> AUTO-ADVANCE to next wave
```

The **planned cadence** the graph encodes, one iteration per coding wave (onto ONE run-integration
branch): run-integration forks `base` ONCE at run start -> per wave, its module worktrees fork from
run-integration -> `odoo-coder` builds + COMMITS each module in its worktree -> cherry-pick each
commit onto run-integration (module-DAG order, verify + checkpoint) -> close the wave (integrated
review + cumulative close-gate) -> AUTO-ADVANCE to the next wave (NO per-wave PR) -> loop. After the
FINAL wave, the terminal `integrate` land-tail squashes run-integration + fresh first-push + opens the
run's ONE PR. The between-wave integration (fork-worktrees-from-run-integration + cherry-pick + saga +
integrated review + cumulative close-gate + auto-advance, then the single terminal PR) is EXECUTED at
runtime - SSOT `${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md` (SOLE consumer:
`run-harness`'s between-wave integration - there is no separate git-executor skill). The
concrete SHAs / branch tips / worktree paths / leases the runtime resolves are exactly the non-
reproducible facts that stay OUT of Block 2W. Block 2W is the code-build analog of the doc-side
instance graph (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/doc-cluster-plan.md`), which likewise plans an
instance topology symbolically with concrete DB/port/lease resolved at runtime.

**Block 3 - Assignment.** One line per module/node:
`module/node → skill | command | agent  (effort + est_agents ESTIMATE; model + count owned by the dispatched skill at runtime - ADVISORY / du kien, non-binding) → which skill that agent uses`.
Add per-node **acceptance criteria** + a **verify command** (Repo Capability Card). `effort` follows
the gap-analysis legend (S/M/L/XL); `est_agents` is a rough advisory count. The plan binds WHICH
skill, never a per-agent `model` or fan-out `count` - the dispatched specialist skill owns those at
runtime (Decision X). Each **coding-wave** node also carries **`cumulative_modules`** - the union of
every module THIS wave touched AND every module ALL PRIOR waves touched. It is the growing regression
scope `run-harness`'s between-wave integration close-gate runs GREEN to close the wave; it is STRUCTURAL scope
like `depends_on` (WHICH modules must stay green), NOT a binding `model`/`count` (no Decision X
conflict), and it surfaces the regression scope to the human at plan-approval time. This 3-block
plan is ALWAYS authored by `odoo-planning` (its `odoo-planner`); planning is mandatory for all work
- `${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Mandatory-planning rule.

**Terminal `integrate` land node (every `writes-files` plan).** The plan does not end at `review`;
it carries a terminal `integrate` node so the change is committed AND landed. The minimal plan
`odoo-planning` emits for a single-module change is therefore `[code, review, integrate]`. `integrate` is the SAME land tail the
full lifecycle and the between-wave integration use: after review is clean, `run-harness` invokes `git-toolkit:git-ops`
to push the change's branch and open a PR against the principal branch, then emits a Continuation-Contract
`next` -> `odoo-pr-monitoring` at `gate_tier: L2` (the single outward merge gate). No squash machinery
is needed for one reviewed commit. This is the ONE land mechanism (git-ops open-PR ->
`odoo-pr-monitoring` merge); there is no local merge to the principal. Block 3 line:
`integrate -> run-harness invokes git-toolkit:git-ops (push + open PR) -> next: odoo-pr-monitoring @ L2`.

**Workflow-as-node in the schema (G-B):** when a node's approach is a workflow-command, it is
**one node** - `files-in-scope` = the workflow's `output_dir/` (one box). Do NOT expand the
workflow's internal phases into separate nodes (that would duplicate the phase logic that is SSOT
in the `.workflow.yaml`), and do NOT draw the workflow's
internal phase-sequence in Block 2 (that DAG is the workflow's own; here the workflow is a
single node that may have edges to OTHER nodes). Block 3 line: `node → /<command> via
workflow-chaining (model per-phase in YAML, effort = total) → verify: artifact in output_dir`.

*Examples (short):*
- Full-stack feature in one module → a single module node `odoo-coding (sonnet, M)` - `odoo-coding`
  dispatches one `odoo-coder` for the module, which internally splits it into a backend WI and a
  frontend WI and sequences them (backend WI first, then the frontend WI, so the field exists before
  the widget binds to it). That WI split is `odoo-coder`'s INTERNAL concern - the plan shows only the
  one module node.
- Three disjoint fixes in three modules (bug + test + docs) → three module nodes: `mod-A odoo-coding`,
  `mod-B odoo-coding`, `mod-C` docs edit; DAG: **independent** (no edges) → `run-harness`'s
  between-wave integration iterates the wave's modules SEQUENTIALLY, in any order (no edge
  constrains which one goes first - NOT concurrently; from the approved plan; the user never
  drives it directly).

## Rejection flow

If the user refines or rejects in the Plan Mode UI (step 5), loop back to the
**soft-plan-gate**, not to execution: re-run the relevant part - pick a different skill, adjust
module/node parameters (scope / files / assignment / effort), or `cancel`. Re-enter Plan Mode only once
the revised plan is re-approved at the text gate. Never dispatch a writes-files specialist off a
rejected plan.
