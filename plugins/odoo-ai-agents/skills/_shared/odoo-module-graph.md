# Odoo module dependency graph (SSOT)

An Odoo change is grounded by **module**, not arbitrary file sets. A module is the directory
holding its DESCRIPTOR - `__manifest__.py`, or `__openerp__.py` on v8-v9 (SSOT:
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 6). Every glob, existence check, and
descriptor read below covers BOTH names: matching one alone makes a whole era invisible. Modules
form a DAG via each descriptor's `depends`, dictating what can run in parallel vs in order.
`odoo-coding` (ordering nodes when running standalone) and `run-harness` (ordering cherry-picks -
see below) use the SAME algorithm - OSM `module_inspect` dependency lookup plus a topological
sort - over the SAME kind of node set: the MODULES in scope. The shared algorithm lives here
once, referenced by every consumer instead of restated.

## Two-tier decomposition axis (the SSOT statement)

The decomposition has exactly TWO tiers; the work-item (WI) lives on ONLY the inner one:

- **OUTER tier = the NODE.** The unit of planning and of a RUN is the plan node
  (`run-<id>.json` `nodes[]`), never the module. `odoo-planner` authors nodes with `depends_on`
  edges; `odoo-coding` dispatches ONE `odoo-coder` per node, whatever module(s) it touches - one,
  part of one, or several. NO layer at or above `odoo-coding` (planning, `odoo-planner`,
  plan-mode-schema, Phase P, `run-harness`) knows the term "work-item" - the outer unit
  is always the node.
- **INNER tier = the WORK-ITEM (WI), owned by `odoo-coder`, INTERNAL to one node.** For its ONE
  node, `odoo-coder` splits the changes into 1..N WIs by DISJOINT file sets, schedules INDEPENDENT
  WIs in PARALLEL and DEPENDENT WIs SEQUENTIALLY (a frontend WI binding a backend WI runs after
  it), and assigns each to the right worker (backend files -> `odoo-backend-coder`, frontend
  files -> `odoo-frontend-coder`). A WI MAY span modules within the node; WI file sets across the
  node MUST still be disjoint. When two WIs touch modules with a dependency edge between them,
  the WI on the DEPENDED-ON module runs FIRST. One node -> 1..N WIs.

**What keeps the outer DAG conflict-free is the DISJOINT FILE SCOPE, not the module boundary.**
Two nodes never write the same file because `files-in-scope` sets are disjoint by schema and
`run-harness` re-verifies it before any worktree is created; two RUNS never build the same module
concurrently because the coordination ledger's claim key is the module technical name. Within one
node, work-items are disjoint by file set, so two coders never write the same file even when the
node spans modules. The module is not a tier of decomposition: it is a PROPERTY of a node (which
modules it touches) and an Odoo fact (install unit, test-selection unit, dependency node). The WI
is `odoo-coder`'s PRIVATE unit and MUST NOT surface to planning / `run-harness`. **Invariant:** the
PLAN is the shared computed result - `odoo-planning` is the canonical PRODUCER of the node DAG;
`odoo-coding` (and `run-harness`, ordering cherry-picks) CONSUME it and call the algorithm here
DIRECTLY only when running STANDALONE (no plan provided), each computing independently. Skipping
module-dependency ordering is the root of ordering conflicts: work-items that ignore module
boundaries get dispatched before the module they build on exists.

## Compute the graph (OSM is ground truth)

For a target set of modules `M`:

1. For each module `m` in `M`, call
   `module_inspect(name=<m>, method='dependencies', odoo_version='<concrete>')` with the CONCRETE
   resolved version, never `'auto'` (per-session pin race - `concurrency-guard.md` "OSM
   session-pin race").
2. Build the sub-graph **restricted to `M`** (edges to modules outside `M` are recorded as
   *upstream context*, not as in-set ordering edges).
3. Topologically order it: modules that do not depend on each other within `M` are **independent**
   (may run in any order, in parallel); a module that depends on another in `M` **must run after**
   its in-set dependency.
4. **Fallback (OSM unreachable or too thin):** the graph's owning orchestrator (`odoo-planning`
   as producer, or `odoo-coding` self-deriving) dispatches a read-only **haiku** subagent to read
   each descriptor's `depends` (glob BOTH names) and scan for `static/src`, labeling the result
   `graph from disk (OSM unavailable)`. A leaf WI worker
   must NEVER hit this fallback by spawning - the graph is computed before any worker exists; a
   leaf needing it reads the descriptors itself, never spawning.
5. **New module (resolves to NEITHER OSM NOR disk) - the third case.** A target module `m` in `M`
   whose descriptor (BOTH names checked) exists in neither the OSM index (step 1) nor on disk
   (step 4) is a **NEW module**: not yet written, so both grounding sources come up empty (a miss
   under only ONE descriptor name is NOT this case). Its `depends` MUST be sourced from the
   design's `dag_layers` / the approved plan - never silently dropped, invented, or treated as a
   dependency-free leaf. A NEW in-scope module
   is CLAIMED in the coordination ledger before it is built (forward-ref:
   `${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md`).

**When the self-derive path is reachable.** Running this algorithm directly (self-deriving
instead of consuming a plan's computed module-DAG) is a NORMAL path: `odoo-coding` runs it
whenever invoked STANDALONE (no plan handed down). It is NOT an admission point - the
mandatory-planning gate lives upstream at the front door
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Mandatory-planning rule), so this
algorithm never self-blocks for "no plan". This keeps the new-module third case safe: a
design/plan in scope supplies a NEW module's `depends` from `dag_layers`; when no design provides
the edge and the module resolves to neither OSM nor disk, it surfaces via the coder's dependency
pre-flight as a graceful BLOCKED (a correctness safeguard, NOT a planning-admission gate).

## How `odoo-coding` uses it

A node's `depends_on` edges derive from this graph: if a node's modules depend, directly or
transitively, on another node's modules, that is an edge FROM the dependent node ONTO the
depended-on node. Independent nodes dispatch together (bounded by the rolling-window budget,
`concurrency-guard.md`); a dependent node's coder starts only after every node it `depends_on` is
DONE. Which work-item inside a node runs first is `odoo-coder`'s private concern (INNER tier
above), never this algorithm's.

## How `run-harness` orders cherry-picks

`run-harness` is consume-only: it does NOT auto-infer the dependency graph. The auto-inference
below is done ONCE by the PRODUCER (`odoo-planning`); `run-harness` consumes the result as its
cherry-pick order. The same algorithm runs standalone only inside `odoo-coding` (no plan provided).

1. Nodes here are keyed by the MODULES each touches - no WI-to-module mapping step, since the
   outer unit is already the node (two-tier axis above).
2. **Auto-infer `depends_on` (producer side):** if node Y touches a module that `depends` (directly
   or transitively) on a module X touches, and X's module is in the plan's set, then Y
   `depends_on` X - even undeclared. These edges fix the node topology so cherry-pick order =
   node-DAG topological order; `run-harness` reads them verbatim from the plan, never
   recomputing them.
3. **Disjoint file-scope safety audit (`run-harness`, before any worktree is created):**
   trust-but-verify no source file is claimed by two nodes' `files-in-scope`; STOP BLOCKED on
   an overlap even though the plan supplied the map. (The intra-node split into disjoint-file-set
   WIs is `odoo-coder`'s PRIVATE concern - two-tier axis above - never surfacing here.)

Record the computed graph + any auto-inferred `depends_on` in the worklog (`worklog-contract.md`) so
later phases can see why the ordering is what it is.
