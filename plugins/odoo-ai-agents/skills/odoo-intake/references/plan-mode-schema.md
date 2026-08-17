# Plan Mode Content Schema (writes-files Approach)

**SSOT owned by `odoo-planning`** (authored by its `odoo-planner` agent). Physically hosted here
under `skills/odoo-intake/references/` for backward-compat with intake Plan Mode and the
`docs/reference/workflow-harness.md` labeled-pointer - do NOT relocate it (`agents/odoo-planner.md`
forbids relocation). Edit the schema here; every other site points at this file.

Load this when the approved Approach has `output_mode = writes-files` and the plan is being written
inside Plan Mode (step 3 of the Plan Mode procedure in SKILL.md). The plan MUST contain three
blocks. None is optional for a `writes-files` Approach.

**The plan is the only place a run decision is made.** `run-harness` executes what is written here
and computes nothing this file could have stated. Never author a field for the executor's
convenience; never leave a decision for the executor to improvise. `nodes` and `edges` are the ONLY
ordering statement a plan makes: no field, header, annotation, or grouping construct may batch nodes
together.

**Run header (required on every `writes-files` plan, ABOVE Block 1).**
`odoo_version: <concrete series, e.g. 18.0>`; optional `viindoo_profile: <name|none>`,
`grounding: osm | local-source | standalone`. Resolve `odoo_version` by working the rungs of
`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` in order and stopping at the first that
answers - NEVER a silent default. This run header is a documented schema field so `run-harness` /
`odoo-coding` read it as a field, not a header line they must guess. Read-only/chat Approaches never
load this schema and carry no such field.

**Block 1 - Node list.** The plan's unit is the **node**: one piece of work with one owner skill.
A node is NOT a module. The MODULE is a property of a node, never a unit of planning: one node MAY
span several modules, and one module MAY be covered by several nodes when the changes must land
separately. Each node entry carries:

- `id` - short, stable, kebab-case, unique in the plan. It is the human's handle at the approval
  gate and the driver's tie-break key, so name it for the WORK, not for a module.
- a one-line description of the behaviour the node delivers.
- `modules` - the module technical names this node touches, in dependency order (omit for a node
  that touches no Odoo module, e.g. a chat-only synthesis node). Ordering rule: OSM
  `module_inspect(name=<m>, method='dependencies', odoo_version=<concrete>)` per module, restricted
  to the plan's own module set (SSOT for the algorithm:
  `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md`). On a node whose `approach` is
  `odoo-instance`, this same field IS the suite scope - the modules whose tests must run GREEN.
- `files-in-scope` - the file globs this node may write. **File scopes across nodes MUST be
  DISJOINT.** This used to be free (each module owned a directory); once one module can be covered by
  several nodes it must be authored deliberately. `run-harness` re-checks it and STOPS BLOCKED on an
  overlap rather than guessing an owner. Two changes to the same file are ONE node, or two nodes
  ordered by `depends_on` and rescoped so their globs do not overlap.

For a multi-repo delivery also note worktree + branch + verify command per node, and ONE Repo
Capability Card per REPO (serialized as the run file's `repos[]`; a single-repo delivery has a
one-entry list).

**A node's module set MUST be closed under "same landing moment".** If two modules must reach the
integration branch as separate commits - because a later node depends on one but not the other,
because they must be independently revertable, or because one needs deeper reasoning than the other
and they are separable - they are two nodes. If they always land together, one node is correct and
cheaper: Odoo installs and tests a comma-separated module list in ONE `odoo-bin` run in every series
from 8.0 onward, so a multi-module node costs ONE database and ONE suite pass, not N.

**Block 2 - Dependency graph.** `nodes` + `edges` where each edge has a `type` of
`technical | business-logic | data-flow` and a `reason`; a `topological_order` (Kahn's algorithm), a
`critical_path`, and `cycles` (empty `[]` for a valid DAG - a cycle is reported, never silently
dropped).

**Edges you MUST emit:**
- **Module dependency.** If node Y touches a module that `depends` (directly or transitively) on a
  module node X touches, and X's module is in this plan's set, then `Y depends_on X`. Odoo cannot
  load a module before its declared dependencies in any series v8-v19. Auto-infer this even when the
  human did not state it (the auto-infer rule already lives at
  `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md`; do not restate it here).
- **Verification.** A node whose `approach` is `odoo-instance` `depends_on` every node whose work it
  must prove.
- **Lifecycle.** Each terminal stage `depends_on` the stage before it, in the Terminal stage order
  constant (`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/run-integration.md` § Pre-PR tail).

**REQUIRED - ASCII dependency-graph block.** Render Block 2 with a fenced ```text ASCII graph (NOT
mermaid - mermaid does not render in the plan file or the terminal where the human reviews the plan).
One box per node, annotated `[repo: <repo>]` and tagged `[skill: <execute-skill>]`, each name in
`modules` marked `(NEW)`/`(existing)`; a `depends-on:` line per node AND a flat edge list
(`X --> Y` = Y depends on X, X runs first). List nodes in topological order top-to-bottom: that is a
reading convenience, NOT a grouping - never add a header that batches nodes. ASCII only (ETHOS rule
0): only `-`, `|`, `+`, `>`, `[`, `]` - NO box-drawing Unicode. Exact template (reusable verbatim):

````
## Block 2 - Dependency graph

```text
Node dependency graph
  Legend: [node-id] [repo: <repo>] [skill: <execute-skill>]  modules: <m> (NEW|existing), ...
          "X --> Y" = Y depends on X (X runs first)
  Nodes are listed in topological order for reading only. The edge list below is the ONLY
  ordering statement; nothing groups nodes together.
  [repo: ...] renders a SERIALIZED schema field: intake Phase P writes it onto every node as
  `repo`, and each repo's capability card into the run file's `repos[]` (harness section 8.3).
  ONE integrate node -> ONE PR -> per REPO. This example is SINGLE-REPO.
  Terminal lifecycle ORDER is not chosen per plan - it is the Terminal stage order constant in
  run-harness/references/run-integration.md section Pre-PR tail. Copy the order, never invent one.

  [billing-core] [repo: fleet-addons] [skill: odoo-coding]
      modules: viin_fleet_billing (NEW)
      depends-on: (none)

  [billing-accounting-bridge] [repo: fleet-addons] [skill: odoo-coding]
      modules: viin_fleet_billing_account (NEW), viin_fleet_billing (existing)
      depends-on: billing-core
      One node spanning two modules: the bridge cannot land without the field it reads, so
      both modules land in ONE commit. Its cross-module test is staged - see Block 3.

  [regression-after-bridge] [repo: fleet-addons] [skill: odoo-instance]
      modules: viin_fleet_billing, viin_fleet_billing_account
      depends-on: billing-accounting-bridge
      An ORDINARY node. It runs the suites of the modules it names. Its `modules` list must
      cover, at minimum, every module named by the nodes it transitively depends on -
      run-harness re-computes that floor and STOPS BLOCKED if this list is below it. Widen it
      beyond the floor when regression-scope.md's algorithm says a sibling module is at risk.

  [cluster-i18n] [repo: fleet-addons] [skill: odoo-i18n]
      depends-on: regression-after-bridge

  [cluster-acceptance] [repo: fleet-addons] [skill: odoo-acceptance]
      depends-on: cluster-i18n

  [cluster-docs] [repo: fleet-addons] [skill: odoo-doc-illustration]
      depends-on: cluster-acceptance
      ONE doc node for the WHOLE run, over the aggregate module set - never per module.

  [integrate] [repo: fleet-addons] [skill: git-toolkit:git-ops]
      depends-on: cluster-docs
      opens THE ONE PR for [repo: fleet-addons]. Name here every node in this repo that is
      NOT in the land-tail set {integrate, monitor, merge}. run-harness evaluates its own
      readiness predicate over ALL nodes (including any materialized at runtime) and treats
      this list as a floor: a narrower list is reported as an advisory finding, never a block.

  [monitor] [repo: fleet-addons] [skill: odoo-pr-monitoring]
      depends-on: integrate
      post-PR: CI-failure triage and review polling.

  [merge] [repo: fleet-addons] [skill: odoo-pr-monitoring]
      depends-on: monitor
      the single outward L2 gate. Always a human.

  The pre-PR lint-class gate runs INSIDE run-harness between the doc node and integrate - a driver
  step over the integration branch's aggregate diff, not a plan node, so it gets no box here.

  Second repo (absent from this example): a run touching repo-2 adds a SIBLING terminal chain -
  the same terminal lifecycle nodes, in the same constant's order, every node tagged
  [repo: <repo-2>] - and THAT chain's own [integrate] opens repo-2's ONE PR.
  Two repos = two integrate nodes = two PRs.

  Edges (depends direction; flat list for grep/diff stability):
    billing-core               --> billing-accounting-bridge
    billing-accounting-bridge  --> regression-after-bridge
    regression-after-bridge    --> cluster-i18n
    cluster-i18n               --> cluster-acceptance
    cluster-acceptance         --> cluster-docs
    cluster-docs               --> integrate
    integrate                  --> monitor
    monitor                    --> merge
```
````

**Serialized form (what Phase P writes from those tags).** Each `[repo: <repo>]` becomes a node's
`repo` field, and each repo's Repo Capability Card becomes one `repos[]` entry (harness 8.3):

```json
"repos": [{"id": "fleet-addons", "base": "<principal branch>", "verify": "<command>",
           "commit": "<resolved by git-toolkit:git-ops>", "confidential": "public",
           "worktree_root": "<parent path outside the repo tree>"}],
"nodes": [{"id": "billing-core", "repo": "fleet-addons", "approach": "odoo-coding",
           "approach_kind": "skill", "modules": ["viin_fleet_billing"], "depends_on": []},
          {"id": "regression-after-bridge", "repo": "fleet-addons", "approach": "odoo-instance",
           "approach_kind": "skill",
           "modules": ["viin_fleet_billing", "viin_fleet_billing_account"],
           "depends_on": ["billing-accounting-bridge"]},
          {"id": "integrate", "repo": "fleet-addons", "approach_kind": "integrate"},
          {"id": "run-summary", "repo": null, "approach_kind": "inline"}]
```

`approach_kind` is one of `skill | agent | workflow | inline | integrate` - five values, exhaustive.
A node's serialized field set is exactly: `id`, `repo`, `approach`, `approach_kind`, `modules`,
`inputs`, `depends_on`, `status`, `produced`, `contract`. **That list is EXHAUSTIVE and there is no
field that groups, batches, layers, or orders nodes other than `depends_on`.** A node carries NO
`gate_tier`: the tier is a total function resolved at dispatch
(`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/SKILL.md` section Gate-tier resolution). Writing a tier
here is a schema violation.

A second repo adds a second `repos[]` entry AND its own `integrate` node - N repos = N PRs.
`repo: null` means the node belongs to no repository (chat-only synthesis / routing): it gets no
worktree and sits outside EVERY repo's `integrate` readiness scope. A source-writing node, an
`odoo-instance` node, or an `integrate` node never carries `null`.

**Data source (never hand-drawn).** The node graph is DERIVED from the design's `dag_layers`
(`${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md` `index.yaml`, the LOGICAL truth)
PLUS the Block 3 `node -> SKILL` assignment for each `[skill: ...]` tag. `dag_layers` states which
work must precede which; turn each layer edge into a `depends_on` edge between the nodes carrying
that work - never into a node, a batch, or a grouping. NEW vs existing comes from the module-graph
resolution (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md`: a module resolving to
NEITHER OSM NOR disk is `(NEW)`; otherwise `(existing)`). Every terminal lifecycle stage appears as
its own node wired to its execute-SKILL. Neither WHICH stages exist nor their ORDER is a per-plan
choice: read both from the Terminal stage order constant
(`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/run-integration.md` section Pre-PR tail),
which is its ONE owner. A stage the run does not have is skipped in place; the rest keep their order.

**Master-child reconciliation (extend, not fork).** The dep-graph is a RENDERING of `index.yaml`
`dag_layers`; it adds no field to `index.yaml` and introduces no second DAG schema. Likewise, a
node's Block-2 `[skill: ...]` tag and its Block-3 assignment line are TWO RENDERINGS OF ONE
assignment, never two independent sources - a disagreement between them is one authoring error to
fix, not two facts to reconcile.

**Where the test-running nodes go.** Never open a PR on a red suite. Every repo MUST therefore carry
at least ONE node whose `approach` is `odoo-instance`, on `integrate@R`'s dependency path, whose
`modules` cover every module named by any coding node in that repo. `run-harness` refuses to open the
PR without it (`run-harness/SKILL.md` section integrate readiness), so a plan that omits it BLOCKS
rather than shipping untested code. Place EARLIER `odoo-instance` nodes wherever catching a
regression late would be expensive; each one's `modules` must cover at least the union over its own
transitive dependencies, so scope grows monotonically down the graph.

**Block 3 - Assignment.** One line per node:
`node -> skill | command | agent  (effort + est_agents ESTIMATE; model + count owned by the dispatched skill at runtime - ADVISORY / du kien, non-binding) -> which skill that agent uses`.
Add per-node **acceptance criteria** + a **verify command** (Repo Capability Card). `effort` follows
the gap-analysis legend (S/M/L/XL); `est_agents` is a rough advisory count. The plan binds WHICH
skill, never a per-agent `model`, fan-out `count`, or `gate_tier`. For a node spanning modules, state
in one line which of its assertions cross a module boundary, so `odoo-coder` knows what to stage
(`${CLAUDE_PLUGIN_ROOT}/agents/odoo-coder.md` section Cross-module test staging). This 3-block plan
is ALWAYS authored by `odoo-planning` (its `odoo-planner`); planning is mandatory for all work -
`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` section Mandatory-planning rule.

**Terminal `integrate` land node (ONE per REPO the plan touches).** The plan does not end at
`review`; it carries a terminal `integrate` node so the change is committed AND landed. The minimal
plan for a single-node change is `[code, verify, review, integrate, monitor, merge]`. After every
non-land-tail node in that repo is terminal and its verification is green, `run-harness` invokes
`git-toolkit:git-ops` to squash and push the repo's integration branch and open a PR against the
principal branch, then materializes `next -> odoo-pr-monitoring`. There is no local merge to the
principal. Block 3 line: `integrate -> run-harness invokes git-toolkit:git-ops (squash + push + open
PR) -> next: odoo-pr-monitoring`.

**Workflow-as-node (G-B):** when a node's approach is a workflow-command it is **one node** -
`files-in-scope` = the workflow's `output_dir/` (one box). Do NOT expand the workflow's internal
phases into separate nodes (that logic is SSOT in the `.workflow.yaml`), and do NOT draw its internal
phase-sequence in Block 2. Block 3 line: `node -> /<command> via workflow-chaining (model per-phase
in YAML, effort = total) -> verify: artifact in output_dir`.

*Examples (short):*
- Full-stack feature in one module -> ONE node; `odoo-coding` dispatches one `odoo-coder`, which
  splits it into a backend work-item and a frontend work-item and sequences them (backend first).
  That split is `odoo-coder`'s INTERNAL concern - the plan shows one node.
- A behaviour change spanning three modules that must land atomically -> ONE node whose `modules`
  lists all three in dependency order, ONE `odoo-coder`, ONE instance, ONE commit.
- Three unrelated fixes inside ONE module, each independently revertable -> THREE nodes, each with
  `modules: <that module>` and DISJOINT `files-in-scope`, chained `depends_on` in landing order.
- Three disjoint fixes in three modules -> three nodes, no edges between them; `run-harness` runs
  them one at a time in any order (it dispatches SEQUENTIALLY, never concurrently).

## Rejection flow

If the user refines or rejects in the Plan Mode UI (step 5), loop back to the **soft-plan-gate**, not
to execution: re-run the relevant part - pick a different skill, adjust node parameters (scope /
files / assignment / effort), or `cancel`. Re-enter Plan Mode only once the revised plan is
re-approved at the text gate. Never dispatch a writes-files specialist off a rejected plan.
