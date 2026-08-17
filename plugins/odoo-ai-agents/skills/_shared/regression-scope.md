<!-- SSOT snippet. The single home for the CUMULATIVE test-selection algorithm an `odoo-instance`
     plan node uses to pick its suite scope, and any peer that runs a regression suite over a
     module set. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/skills/_shared/regression-scope.md.
     This selects WHICH suites run; the saga/rollback of the run itself is integration-loop.md;
     the OSM session-pin race + ephemeral-DB lease are concurrency-guard.md. -->

# Regression-scope selection (SSOT)

Bounded algorithm `odoo-planner` follows to choose the modules an `odoo-instance` plan node must run
GREEN before `integrate` may open a PR. The scope is the monotonically-growing regression guard
`C_N` plus a capped, in-repo-only downstream widening. Every OSM call passes a CONCRETE
`odoo_version` (parallel fan-out shares one server pin - `'auto'` is last-write-wins; see
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` OSM session-pin race).

## C_N - the mandatory regression core

- `C_N` = the union of `modules` over the `odoo-instance` node's OWN transitive `depends_on`
  closure - every module named by any coding node that node depends on, directly or transitively.
- `odoo-planner` AUTHORS `C_N` into that node's `modules` field at plan-authoring time. It is not
  injected at runtime by anything: `run-harness` only computes the FLOOR (the same union, computed
  from the live `depends_on` graph) and BLOCKS the plan if the authored `modules` list is below it
  (`run-harness/SKILL.md` § `verify_plan_agreement`, check 4).
- `C_N` grows with the node's position in the graph - a node placed later in the dependency order
  covers a larger union, because it depends (transitively) on more coding nodes. This is the
  regression guard: an earlier node's module must stay green after a later node lands.
- `C_N` is ALWAYS run in full. Nothing below narrows below it.

## Run-set = C_N UNION a bounded in-repo widening

Run-set = `C_N` (mandatory) UNION {IN-REPO modules whose own suite statically references a model
this node's coding nodes changed}. Compute the widening:

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
  node genuinely touches more in-repo owners). On overflow, KEEP `C_N` + the in-repo owners that fit
  and RECORD the truncation (which owners were dropped, and K) in the node's worklog entry.
- On series 12.0 and later, `--test-tags /<m>` per module means the run NEVER re-runs unchanged
  Odoo CORE: a core dependent (e.g. `sale.order` pulls 100+ core modules) is pure runtime blowup
  with near-zero regression signal, so it is excluded. The regressions a node can actually cause are
  in (a) the custom cluster and (b) our own modules that depend on the changed models - both
  in-repo. **On series 8.0-11.0, this exclusion is NOT achievable: there is no test-tag filter, so
  `-i <modules> --test-enable` also runs every CORE module pulled in as a transitive dependency.**
  State that on those series instead of asserting the never-core rule - do not claim a guarantee
  those series cannot keep (0.5 caveat).
- `impact_analysis(entity_type="model", entity_name="<changed-model>", odoo_version=<explicit>)` is
  an OPTIONAL blast-radius signal to CONSIDER (a widen hint), NEVER a mandatory run-selection input -
  its `Dependent modules` list is dominated by core.

## Standalone / OSM-down degrade

If OSM is unreachable, still run `C_N` in full - its members and their `depends` come from the
node's authored `modules` field + each module's descriptor on disk (SSOT:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md` disk fallback). RECORD in the node's
worklog entry that the `tests_covering` widening was SKIPPED (OSM unavailable). Never silently
narrow below `C_N`.

## Recording

Record in the run's worklog (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`): the resolved
run-set, any K-truncation, and any degrade, so a resumed session sees why that suite set ran.
