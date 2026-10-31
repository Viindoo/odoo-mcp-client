# Odoo module dependency graph (SSOT)

An Odoo change is grounded by **module**, not arbitrary file sets. A module is the directory
holding its DESCRIPTOR - `__manifest__.py`, or `__openerp__.py` on the series that has it (SSOT:
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 6). Every glob, existence check and
descriptor read below covers BOTH names. Modules form a DAG via each descriptor's `depends`,
dictating what can run in parallel vs in order. `odoo-coding` (ordering nodes when running
standalone) and the plan runner (ordering cherry-picks) use the SAME algorithm - OSM
`module_inspect` dependency lookup plus a topological sort - over the MODULES in scope. The
algorithm lives here once; every consumer references it.

## The node is the unit of work (the SSOT statement)

- **The NODE** is the unit of planning, of dispatch, of commit and of integration
  (`run-<id>.json` `nodes[]`), never the module and never a file type. `odoo-planner` authors
  nodes with `depends_on` edges; `odoo-coding` launches ONE `odoo-coder` per node, whatever
  module(s) it touches, and that coder writes every file the node needs in every module the node
  names.
- **A node is divided only for two reasons**, both the coder's call: a part whose output exceeds
  one agent's budget (a second `odoo-coder` on a disjoint file set), or a frontend part with new
  JS or OWL files that shares no file with the backend part (`odoo-frontend-coder`, launched after
  the backend symbols it binds exist). Never by module or by file type.

**What keeps the outer DAG conflict-free is the DISJOINT FILE SCOPE, not the module boundary.**
Two nodes dispatched together never write the same file: their `files_in_scope` sets are disjoint
by schema (the main agent verifies it before any worktree is created); two RUNS never build the
same module concurrently because the coordination ledger's claim key is the module technical
name. **Invariant:** `odoo-planning` is the canonical PRODUCER of the node DAG; `odoo-coding`
(and the main agent, ordering cherry-picks) CONSUME it and call the algorithm here directly only
when running STANDALONE (no plan provided). A node dispatched before the module it builds on
exists is the ordering conflict this prevents.

## Compute the graph (OSM is ground truth)

For a target set of modules `M`:

1. For each module `m` in `M`, call
   `module_inspect(name=<m>, method='dependencies', odoo_version='<concrete>')` with the CONCRETE
   resolved version, never `'auto'` (`concurrency-guard.md` § OSM session-pin race).
2. Build the sub-graph **restricted to `M`** (edges to modules outside `M` are recorded as
   *upstream context*, not as in-set ordering edges).
3. Topologically order it: modules that do not depend on each other within `M` are **independent**
   (any order, in parallel); a module that depends on another in `M` **runs after** it.
4. **Fallback (OSM unreachable or too thin):** the graph's owning orchestrator (`odoo-planning`
   as producer, or `odoo-coding` self-deriving) dispatches a read-only **haiku** subagent to read
   each descriptor's `depends` (glob BOTH names) and scan for `static/src`, labeling the result
   `graph from disk (OSM unavailable)`. A leaf worker never hits this fallback by spawning - the
   graph is computed before any worker exists; a leaf needing it reads the descriptors itself.
5. **New module (resolves to NEITHER OSM NOR disk).** A target module whose descriptor (BOTH names
   checked) exists in neither the index (step 1) nor on disk (step 4) is a NEW module (a miss
   under only ONE descriptor name is NOT this case). Its `depends` MUST come from the design's
   `dag_layers` / the approved plan - never dropped, invented, or treated as a dependency-free
   leaf. A NEW in-scope module is CLAIMED in the coordination ledger before it is built
   (`${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md`).

Running this algorithm directly (self-deriving instead of consuming a plan) is a NORMAL path for
`odoo-coding` invoked STANDALONE; it is not an admission point - the mandatory-planning gate lives
at the front door (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Mandatory-planning
rule), so this algorithm never self-blocks for "no plan". A new module with no design edge
surfaces via the coder's dependency pre-flight as a graceful BLOCKED.

## Reverse closure

The reverse closure of a module is every module whose `depends` names it, directly or through
other modules, computed to its fixed point (a grep of every manifest, `impact_analysis` as a
lower bound). It is the unit that moves with a module between repositories, the set a retired
module must no longer be used by, and the set whose tests run once more after the module changes
(`${CLAUDE_PLUGIN_ROOT}/snippets/modularity-contract.md` § Tests).

## How `odoo-coding` uses it

A node's `depends_on` edges derive from this graph: if a node's modules depend, directly or
transitively, on another node's modules, that is an edge FROM the dependent node ONTO the
depended-on node. Independent nodes dispatch together (bounded by the rolling-window budget,
`concurrency-guard.md`); a dependent node's coder starts only after every node it `depends_on` is
DONE. How `odoo-coder` orders the files inside its node is its own concern.

## How the main agent orders cherry-picks

The main agent running a plan is consume-only: the auto-inference below is done ONCE by the
PRODUCER (`odoo-planning`); the main agent consumes the result as its cherry-pick order.

1. Nodes are keyed by the MODULES each touches; the node is the unit (above).
2. **Auto-infer `depends_on` (producer side):** if node Y touches a module that `depends` (directly
   or transitively) on a module X touches, and X's module is in the plan's set, then Y
   `depends_on` X - even undeclared. Cherry-pick order = node-DAG topological order; the main
   agent reads the edges verbatim from the plan, never recomputing them.
3. **Disjoint file-scope safety audit (the main agent, before any worktree is created):**
   trust-but-verify no source file is claimed by two nodes dispatched together; STOP BLOCKED on
   an overlap even though the plan supplied the map.

Record the computed graph + any auto-inferred `depends_on` in the worklog (`worklog-contract.md`) so
later phases can see why the ordering is what it is.
