# Odoo module dependency graph - the unit of work is the module (SSOT)

An Odoo change is partitioned by **module**, not by arbitrary file sets. Modules form a DAG via
each `__manifest__.py` `depends`; that DAG dictates what can run in parallel and what must run in
order. `odoo-coding` (deciding which wave each coder runs in) and `wave` (deciding which WI depends
on which) use the **same algorithm** - the OSM `module_inspect` dependency lookup plus a topological
sort - over **different node sets**: `odoo-coding` over its target module set, `wave` over the
modules each WI touches. The shared algorithm lives here once so both reference it instead of
restating it (they do not share a computed result or cache). Skipping it is the root of point-10
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
   orchestrator (`odoo-coding` Phase 0, `wave` Phase 0) - so the orchestrator dispatches a
   read-only **haiku** subagent to read each `__manifest__.py` `depends` and scan
   for `static/src`, and labels the result `graph from disk (OSM unavailable)`. A leaf WI worker
   must NEVER hit this fallback by spawning - it is computed before any worker exists; if
   a leaf ever needs the graph it reads the manifests itself, it does not spawn.

## How `odoo-coding` uses it

Each module's coder runs in its dependency wave: independent modules dispatch together (bounded by
the rolling-window budget); a dependent module's coder starts only after the module it depends on
has been written. The `wave` column in the plan shows depends-on for the reader; execution enforces
it per-module.

## How `wave` uses it (module-aware work-items)

1. Map each WI to the module(s) its files belong to (`{WI -> [modules]}`).
2. **Auto-infer `depends_on`:** if any module owned by WI-B `depends` (directly or transitively) on
   a module owned by WI-A, then WI-B `depends_on` WI-A - even if the user did not declare it. Add
   these edges to the WI topology so cherry-pick order = module-DAG topological order.
3. **Warn on boundary-crossing WIs:** if a single WI owns files spanning multiple modules that sit
   at different DAG depths (or that other WIs also touch), flag it and propose splitting the WI
   along module boundaries before dispatch. A WI should be one module (or a tightly-coupled cluster
   that always ships together), not an arbitrary file slice.

Record the computed graph + any auto-inferred `depends_on` and split warnings in the worklog
(`worklog-contract.md`) so the plan gate and later phases can see why the ordering is what it is.
