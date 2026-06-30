# Odoo module dependency graph - the unit of work is the module (SSOT)

An Odoo change is partitioned by **module**, not by arbitrary file sets. Modules form a DAG via
each `__manifest__.py` `depends`; that DAG dictates what can run in parallel and what must run in
order. `odoo-coding` (deciding which wave each coder runs in) and the git-executor `odoo-wave`
(ordering WIs for cherry-pick) use the **same algorithm** - the OSM `module_inspect` dependency
lookup plus a topological sort - over **different node sets**: `odoo-coding` over its target module
set, `odoo-wave` over the modules each WI touches. The shared algorithm lives here once so every
consumer references it
instead of restating it. **Invariant (the one this re-architecture changes):** the PLAN is now the
shared computed result - `odoo-planning` is the canonical PRODUCER of the wave-batched module-DAG;
`odoo-coding` (and the git-executor) CONSUME that plan and call the algorithm here DIRECTLY only
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
   orchestrator (`odoo-coding` Phase 0 when standalone, `odoo-planning` as the producer) - so the orchestrator dispatches a
   read-only **haiku** subagent to read each `__manifest__.py` `depends` and scan
   for `static/src`, and labels the result `graph from disk (OSM unavailable)`. A leaf WI worker
   must NEVER hit this fallback by spawning - it is computed before any worker exists; if
   a leaf ever needs the graph it reads the manifests itself, it does not spawn.

## How `odoo-coding` uses it

Each module's coder runs in its dependency wave: independent modules dispatch together (bounded by
the rolling-window budget); a dependent module's coder starts only after the module it depends on
has been written. The `wave` column in the plan shows depends-on for the reader; execution enforces
it per-module.

## How `odoo-wave` uses it (module-aware work-items)

`odoo-wave` is consume-only: it does NOT auto-infer the WI dependency graph. The auto-inference below
is done ONCE by the PRODUCER (`odoo-planning`); `odoo-wave` CONSUMES the result as its cherry-pick
order. The same algorithm runs standalone only inside `odoo-coding` (no plan provided).

1. Map each WI to the module(s) its files belong to (`{WI -> [modules]}`).
2. **Auto-infer `depends_on` (producer side):** if any module owned by WI-B `depends` (directly or
   transitively) on a module owned by WI-A, then WI-B `depends_on` WI-A - even if the user did not
   declare it. These edges fix the WI topology so cherry-pick order = module-DAG topological order.
   `odoo-wave` reads these edges verbatim from the plan; it never recomputes them.
3. **Warn on boundary-crossing WIs:** if a single WI owns files spanning multiple modules at
   different DAG depths (or that other WIs also touch), flag it and propose splitting along module
   boundaries. A WI should be one module (or a tightly-coupled cluster that always ships together),
   not an arbitrary file slice. (`odoo-wave` STILL runs the disjoint file-ownership safety audit at
   its Phase 0 - trust-but-verify - and blocks on an overlap even though the plan supplied the map.)

Record the computed graph + any auto-inferred `depends_on` and split warnings in the worklog
(`worklog-contract.md`) so later phases can see why the ordering is what it is.
