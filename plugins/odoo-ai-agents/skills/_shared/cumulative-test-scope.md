<!-- SSOT snippet. The single home for the per-wave CUMULATIVE test-selection algorithm shared by
     the wave close-gate (odoo-wave Phase 4.4) and any peer that closes a wave on a regression suite.
     Edit here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/skills/_shared/cumulative-test-scope.md.
     This selects WHICH suites run; the saga/rollback of the run itself is integration-loop.md;
     the OSM version-pin race + ephemeral-DB lease are concurrency-guard.md. -->

# Cumulative test-scope selection (SSOT)

Bounded algorithm an execute-agent follows to pick the test suites a wave must run GREEN before it
may open a PR. The scope is the monotonically-growing regression guard `C_N` plus a capped,
in-repo-only downstream widening. It NEVER re-runs unchanged Odoo core. Every OSM call passes a
CONCRETE `odoo_version` (parallel fan-out shares one server pin - `'auto'` is last-write-wins;
see `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` OSM version-pin race).

## C_N - the mandatory regression core

- `C_N` = the union of every module THIS wave touched AND every module ALL PRIOR waves touched.
- It is INJECTED, never self-derived: the planner emits `cumulative_modules` per static coding-wave
  node (run-harness injects it for a dynamic wave). The consumer receives it; it does not compute it.
- `C_N` grows every wave - wave N re-runs the suites of waves 1..N over the custom cluster. This is
  the regression guard: an earlier wave's module must stay green after a later wave lands.
- `C_N` is ALWAYS run in full. Nothing below narrows below it.

## Run-set = C_N UNION a bounded in-repo widening

Run-set = `C_N` (mandatory) UNION {IN-REPO modules whose own suite statically references a model
this wave changed}. Compute the widening:

1. For each changed model `X`: `tests_covering(model=<changed-model>, odoo_version=<explicit>)`.
2. Collect the DISTINCT `[module]` owners from the returned rows.
3. KEEP ONLY owners that live in the repo under test; DROP every core / out-of-repo owner.
4. Fold whole MODULES, never individual methods - `tests_covering` can return 900+ methods but
   only ~a dozen owner modules; the run unit is the owning module's suite.

Own-module suites for every module in the run-set:
- Python: `module_inspect(name=<module>, method="tests", odoo_version=<explicit>)`.
- JS / Hoot / tour: `js_test_inspect(module=<module>, odoo_version=<explicit>)`.

## Ceiling K + never-core

- Cap the widening union at a ceiling `K` (default `K = 25` modules; tunable - raise it only when a
  wave genuinely touches more in-repo owners). On overflow, KEEP `C_N` + the in-repo owners that fit
  and RECORD the truncation (which owners were dropped, and K) in the wave log.
- NEVER re-run unchanged Odoo CORE. Core does not change between our waves, so a core dependent
  (e.g. `sale.order` pulls 100+ core modules) is pure runtime blowup with near-zero regression
  signal. The regressions a wave can actually cause are in (a) the custom cluster and (b) our own
  modules that depend on the changed models - both in-repo.
- `impact_analysis(entity_type="model", entity_name="<changed-model>", odoo_version=<explicit>)` is
  an OPTIONAL blast-radius signal to CONSIDER (a widen hint), NEVER a mandatory run-selection input -
  its `Dependent modules` list is dominated by core.

## Standalone / OSM-down degrade

If OSM is unreachable, still run `C_N` in full - its members and their `depends` come from the
plan's injected `cumulative_modules` + each module's `__manifest__.py` on disk (SSOT:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md` disk fallback). RECORD in the wave log
that the `tests_covering` widening was SKIPPED (OSM unavailable). Never silently narrow below `C_N`.

## Recording

Record in the run's worklog (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`): the resolved
run-set, any K-truncation, and any degrade, so a resumed session sees why that suite set ran.
