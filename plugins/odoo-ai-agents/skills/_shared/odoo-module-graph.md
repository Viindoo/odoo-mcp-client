# Odoo module dependency graph - the unit of work is the module (SSOT)

An Odoo change is partitioned by **module**, not by arbitrary file sets. A module is the directory
holding its DESCRIPTOR - `__manifest__.py`, or `__openerp__.py` on v8-v9 (SSOT:
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 6). Every glob, existence check, and
descriptor read below covers BOTH names: matching one alone makes a whole era invisible and reports
the module as non-existent. Modules form a DAG via each descriptor's `depends`; that DAG dictates
what can run in parallel and what must run in order. `odoo-coding` (deciding which wave each module's coder runs in) and `run-harness`'s
between-wave integration (ordering modules for cherry-pick) use the **same algorithm** - the OSM
`module_inspect` dependency lookup plus a topological sort - over the **same kind of node set**: the
MODULES in scope (`odoo-coding` over its target module set, `run-harness` over the wave's modules).
The shared algorithm lives here once so every consumer references it
instead of restating it.

## Two-tier decomposition axis (the SSOT statement)

The decomposition has exactly TWO tiers, and the work-item (WI) lives on ONLY the inner one:

- **OUTER tier = the MODULE SCOPE - 1..N modules owned by ONE `odoo-coder`.** The unit of planning
  and of a wave is still the MODULE (`odoo-planning` batches the module-DAG into waves; `run-harness`
  iterates a wave's MODULES). What is NOT capped at one is how many modules a single `odoo-coder`
  dispatch covers: `odoo-coding` dispatches ONE `odoo-coder` per MODULE SCOPE, and a scope is 1..N
  modules - one module being the common case, behaving exactly as a per-module dispatch always did.
  NO layer at or above `odoo-coding` (planning, `odoo-planner`,
  plan-mode-schema, Phase P, `run-harness`) knows the term "work-item" - the outer unit is always
  expressed in MODULES.
- **INNER tier = the WORK-ITEM (WI), owned by `odoo-coder`, INTERNAL to its scope.** For its scope,
  `odoo-coder` splits the changes into 1..N WIs by DISJOINT file sets, schedules INDEPENDENT
  WIs in PARALLEL and DEPENDENT WIs SEQUENTIALLY (a frontend WI that binds a backend WI runs after
  it - the backend-before-frontend order), and assigns each WI to the right worker
  (backend files -> `odoo-backend-coder`, frontend files -> `odoo-frontend-coder`). A WI MAY span
  several modules of the scope when the change is atomic across them - splitting such a change per
  module only manufactures a red intermediate state. One scope -> 1..N WIs.

**Why a scope may span modules.** Some changes CANNOT be completed by editing one module - a symbol
introduced in one and consumed in another, a field moved between them, a §10 cross-module contract:
the behavior exists only once both sides land, so split across dispatches neither module goes green
alone and no coordinator holds an honest verdict. One scope puts change and verification in ONE owner.

**Ownership invariant (the load-bearing rule - not the module count).** A module is WRITTEN by
exactly ONE `odoo-coder` at a time; two coordinators on one module would corrupt the ledger, collide
two worktrees on a file, and make a cherry-pick drop or duplicate work. Enforced at RUNTIME by the
ledger CLAIM over every module in a scope, not only NEW ones
(`${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md`), never by a static
one-module-per-coordinator cap. `odoo-coding` is the ledger's sole writer: a coordinator needing a
module outside its scope REPORTS it and is re-dispatched with an expanded scope, never self-granting.

So `odoo-coder` owns its scope end-to-end (one worktree, one integrated test, one commit) and a WI
can never slice two coders across one module. The WI is `odoo-coder`'s PRIVATE unit and
MUST NOT surface to planning / `run-harness`. **Invariant:** the PLAN is the
shared computed result - `odoo-planning` is the canonical PRODUCER of the wave-batched module-DAG;
`odoo-coding` (and `run-harness`'s between-wave integration) CONSUME that plan and call the algorithm here DIRECTLY only
when running STANDALONE (no plan provided), each computing independently (no shared result or
cache). Skipping the module axis entirely is still the root of ordering conflicts: work that ignores
module boundaries ALTOGETHER gets dispatched before the module it builds on exists. Spanning module
boundaries INSIDE one owned scope is the sanctioned case - it is exactly what keeps the atomic change
in a single owner's hands.

## Compute the graph (OSM is ground truth)

For a target set of modules `M`:

1. For each module `m` in `M`, call
   `module_inspect(name=<m>, method='dependencies', odoo_version='<concrete>')`. Pass the CONCRETE
   resolved version, never `'auto'` (the pin is per-session and racy under a shared session - see
   `concurrency-guard.md` "OSM session-pin race").
2. Build the sub-graph **restricted to `M`** (edges to modules outside `M` are recorded as
   *upstream context*, not as in-set ordering edges).
3. Topologically order it: modules that do not depend on each other within `M` are **independent**
   (run in the same wave, parallel); a module that depends on another in `M` runs in a **later
   wave** (after its in-set dependency).
4. **Fallback (OSM unreachable or too thin):** the orchestrator that owns this graph
   (`odoo-planning` as the producer, or `odoo-coding` on the self-derive path below) dispatches a
   read-only **haiku** subagent to read each descriptor's `depends` (glob BOTH names) and scan
   for `static/src`, and labels the result `graph from disk (OSM unavailable)`. A leaf WI worker
   must NEVER hit this fallback by spawning - it is computed before any worker exists; if
   a leaf ever needs the graph it reads the descriptors itself, it does not spawn.
5. **New module (resolves to NEITHER OSM NOR disk) - the third case.** A target module `m` in `M`
   whose descriptor (BOTH names checked) exists in neither the OSM index (step 1) nor on disk
   (step 4) is a **NEW module**: it has not been written yet, so both grounding sources come up
   empty. A miss under only ONE descriptor name is NOT this case. Its `depends`
   MUST be sourced from the design's `dag_layers` / the approved plan (a human/architect declared the
   dependency before any code existed) and MUST NOT be left unresolved - never silently drop a new
   module's edges, invent one, or treat it as a dependency-free leaf. Version-independent. A NEW
   in-scope module is CLAIMED in the coordination ledger before it is
   built (forward-ref: `${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md`).

**When the self-derive path is reachable.** Running this algorithm DIRECTLY (self-deriving instead
of consuming a plan's already-computed module-DAG) is a NORMAL path: `odoo-coding` runs it whenever
it is invoked STANDALONE (no plan handed down). It is NOT an admission point - the mandatory-planning
gate lives upstream at the front door (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` §
Mandatory-planning rule), so this algorithm never self-blocks for "no plan".
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
