# Odoo module dependency graph - the unit of work is the module (SSOT)

An Odoo change is partitioned by **module**, not by arbitrary file sets. Modules form a DAG via
each `__manifest__.py` `depends`; that DAG dictates what can run in parallel and what must run in
order. `odoo-coding` (deciding which wave each module's coder runs in) and `run-harness`'s
between-wave integration (ordering modules for cherry-pick) use the **same algorithm** - the OSM
`module_inspect` dependency lookup plus a topological sort - over the **same kind of node set**: the
MODULES in scope (`odoo-coding` over its target module set, `run-harness` over the wave's modules).
The shared algorithm lives here once so every consumer references it
instead of restating it.

## Two-tier decomposition axis (the SSOT statement)

The decomposition has exactly TWO tiers, and the work-item (WI) lives on ONLY the inner one:

- **OUTER tier = the MODULE.** The unit of planning, of a wave, and of a RUN is the module.
  `odoo-planning` batches the module-DAG into waves; `run-harness` groups a wave's modules into one
  `wave` RUN-DAG node and iterates the wave's MODULES via its between-wave integration; `odoo-coding`
  dispatches ONE `odoo-coder` per module. NO layer at or above `odoo-coding` (planning, `odoo-planner`,
  plan-mode-schema, Phase P, `run-harness`) knows the term "work-item" - the outer unit
  is always the module.
- **INNER tier = the WORK-ITEM (WI), owned by `odoo-coder`, INTERNAL to one module.** For its ONE
  module, `odoo-coder` splits the changes into 1..N WIs by DISJOINT file sets, schedules INDEPENDENT
  WIs in PARALLEL and DEPENDENT WIs SEQUENTIALLY (a frontend WI that binds a backend WI runs after
  it - the backend-before-frontend intra-module order), and assigns each WI to the right worker
  (backend files -> `odoo-backend-coder`, frontend files -> `odoo-frontend-coder`). One module ->
  1..N WIs.

This two-tier split is what keeps the outer DAG conflict-free: because the outer unit is the module
and `odoo-coder` owns its single module end-to-end (one worktree, one integrated test, one
coordination-ledger entry), a WI can never slice two coders across the same module, span two modules
in different waves, or split a module's ledger entry between owners. The WI is `odoo-coder`'s PRIVATE
unit and MUST NOT surface to planning / `run-harness`. **Invariant (the one this re-architecture changes):** the PLAN is now the
shared computed result - `odoo-planning` is the canonical PRODUCER of the wave-batched module-DAG;
`odoo-coding` (and `run-harness`'s between-wave integration) CONSUME that plan and call the algorithm here DIRECTLY only
when running STANDALONE (no plan provided). The shared-algorithm-lives-here-once framing still
governs that standalone path: standalone consumers each compute independently (no shared result or
cache); a plan-fed consumer instead reuses planning's single computed result. Skipping it is the
root of point-10
conflicts: work-items that ignore module boundaries get dispatched before the module they build on
exists.

## Compute the graph (OSM is ground truth)

For a target set of modules `M`:

1. For each module `m` in `M`, call
   `module_inspect(name=<m>, method='dependencies', odoo_version='<concrete>')`. Pass the CONCRETE
   resolved version, never `'auto'` (the pin is per-API-key and racy - see
   `concurrency-guard.md` "OSM version-pin race").
2. Build the sub-graph **restricted to `M`** (edges to modules outside `M` are recorded as
   *upstream context*, not as in-set ordering edges).
3. Topologically order it: modules that do not depend on each other within `M` are **independent**
   (run in the same wave, parallel); a module that depends on another in `M` runs in a **later
   wave** (after its in-set dependency).
4. **Fallback (OSM unreachable or too thin):** this graph is computed by the
   orchestrator (`odoo-planning` as the producer, or `odoo-coding` on the self-derive path below) - so the orchestrator dispatches a
   read-only **haiku** subagent to read each `__manifest__.py` `depends` and scan
   for `static/src`, and labels the result `graph from disk (OSM unavailable)`. A leaf WI worker
   must NEVER hit this fallback by spawning - it is computed before any worker exists; if
   a leaf ever needs the graph it reads the manifests itself, it does not spawn.
5. **New module (resolves to NEITHER OSM NOR disk) - the third case.** A target module `m` in `M`
   whose `__manifest__.py` exists in neither the OSM index (step 1) nor on disk (step 4) is a **NEW
   module**: it has not been written yet, so both grounding sources come up empty. Its `depends`
   MUST be sourced from the design's `dag_layers` / the approved plan (a human/architect declared the
   dependency before any code existed) and MUST NOT be left unresolved - never silently drop a new
   module's edges, invent one, or treat it as a dependency-free leaf. This is the third grounding
   case alongside "OSM available" (step 1) and "disk fallback" (step 4), and it is
   version-independent. A NEW in-scope module is CLAIMED in the coordination ledger before it is
   built (forward-ref: `${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md`).

**When the self-derive path is reachable.** Running this algorithm DIRECTLY (self-deriving instead
of consuming a plan's already-computed module-DAG) is a NORMAL path: `odoo-coding` runs it whenever
it is invoked STANDALONE (no plan handed down). It is NOT an admission point - the mandatory-planning
gate lives upstream at the front door (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` §
Mandatory-planning rule), so this algorithm never self-blocks for "no plan". A plan-fed consumer
instead reuses planning's single computed result (the plan IS the SSOT; the algorithm is not re-run).
This keeps the new-module third case above safe: when a design/plan IS in scope it supplies a NEW
module's `depends` from its `dag_layers`; when NO design provides the edge AND the module resolves to
neither OSM nor disk, that does not silently pass - it surfaces via the coder's dependency pre-flight
as a graceful BLOCKED (a CORRECTNESS safeguard on unresolved prerequisites, NOT a planning-admission
gate).

## How `odoo-coding` uses it

Each module's coder runs in its dependency wave: independent modules dispatch together (bounded by
the rolling-window budget); a dependent module's coder starts only after the module it depends on
has been written. The `wave` column in the plan shows depends-on for the reader; execution enforces
it per-module.

## How `run-harness`'s between-wave integration uses it (module-batched cherry-pick order)

`run-harness`'s between-wave integration is consume-only: it does NOT auto-infer the dependency
graph. The auto-inference below is done ONCE by the PRODUCER (`odoo-planning`); `run-harness`
CONSUMES the result as its cherry-pick order. The same algorithm runs standalone only inside
`odoo-coding` (no plan provided).

1. The nodes ARE the modules - there is no WI-to-module mapping step, because the outer unit is
   already the module (two-tier axis above).
2. **Auto-infer `depends_on` (producer side):** if module B `depends` (directly or transitively) on
   module A, then B `depends_on` A - even if the user did not declare it. These edges fix the module
   topology so cherry-pick order = module-DAG topological order. `run-harness` reads these edges
   verbatim from the plan; it never recomputes them.
3. **Disjoint-module safety audit (`run-harness` between-wave step 0):** trust-but-verify that no
   source file is claimed by two module scopes; block on an overlap even though the plan supplied the
   map. (The intra-module split into disjoint-file-set WIs is `odoo-coder`'s PRIVATE concern -
   two-tier axis above - and never surfaces here.)

Record the computed graph + any auto-inferred `depends_on` in the worklog (`worklog-contract.md`) so
later phases can see why the ordering is what it is.
