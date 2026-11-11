# Backend lint-class gate - module selection

This snippet decides WHICH modules make up the backend code-quality gate and how a run of them is
read. WHETHER the gate runs on a dispatch is owned by `GATE_ROLE` (`odoo-instance-ops` § Lint modules).

## Candidate set

Odoo core `test_lint` (its series presence: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-build-facts.md`
§ Backend lint-class gate), plus every lint-class module the resolved addons path SHIPS: a module
whose technical name starts with `test_` and whose tests run flake8 or pylint. Find them by reading
the resolved addons path, never from memory.

## Selection - run every step, in order

1. List the candidates for the target series and addons path.
2. Confirm each with `check_module_exists(name='<module>', odoo_version='<series>',
   profile_name='<pinned profile>')`; pass `profile_name=` explicitly on every call.
3. Union each confirmed module into BOTH the `-i`/`-u` install list AND `--test-tags`
   (`/<module>`). Never tag a module you did not also install.

## Scope the gate to the PR's modules

Read each candidate's own source (its tests and manifest) for the options its tests read to narrow
what they check - a `tools.config` key or an environment variable - never assume names. Pass them,
set to the PR's modules, as the build's `conf_options`. A candidate whose source names none is
UNSCOPED: it checks the whole addons path. Core `test_lint` is always unscoped (its tests walk every
addon manifest). Name the unscoped candidates in `notes`.

A finding is this PR's only when it points into one of the PR's modules; anywhere else it is repo
state, listed in `notes`, never in the verdict.

- A finding in a PR module -> `tests-failed`.
- An unscoped candidate that failed ONLY on repo-state findings, while at least one SCOPED candidate
  installed, loaded its tests and passed: informational, recorded in `notes`. The scoped candidate's
  verdict covers the PR's modules, so the gate is not held by debt the PR did not add.
- Any other lint test that failed only on repo-state findings (no scoped candidate passed, or none
  exists): `tests-inconclusive`, never green and never this PR's `tests-failed`.

An out-of-scope failing TEST is still governed by `test-scope-contract.md` § Reporting.

## Companion loaded server-wide

When the lint module's source names a companion that must be loaded server-wide, that is a
deployment fact: the catalog row's `server_wide_modules` (set through `/odoo-ai-agents:odoo-setup`
step `46-server-wide`), or the dispatch's `SERVER_WIDE` `include` for one run. A companion that is
not loaded makes the gate `tests-inconclusive`.

## A probe is not proof - the index can be stale (HARD RULE)

`check_module_exists` answers from the revision it indexed, so it can confirm a module the addons
path no longer ships: that name installs nothing, its tag matches nothing, and the run reports a
FALSE GREEN. The addons path decides the module; after the run, § Coverage evidence decides whether
each tagged module really ran.

## Coverage evidence

Read before trusting any pass, for every lint module the build unioned (the same probe result).
The log of THIS run shows, per module: the module installed, and each of its tests has the
runner's start line (`Starting <Class>.<method> ...`; on a series whose runner
logs no per-test line, the module's test-load line) and is not skipped.

A lint test that runs its checker and reports nothing after its start line passed clean: the
checkers log no count, so that silence is the normal result, never a hold. Only a shortfall makes
the gate `tests-inconclusive`, whatever the counters say: a module whose tests never loaded, a
lint test skipped (its tool missing or too old, its scope filtered to nothing), a checker or
plugin the log says failed to load, a count smaller than requested. `notes` names the module and
the shortfall.

## What the SQL-injection check proves

The check judges syntax, not values, and its rules differ by series: read the checker the target
series ships (the pylint plugin of core's `test_lint`) before changing a query to satisfy it. In
its fuller form an integer conversion alone is accepted whatever the value, mixing it with a
string conversion is not, only an `assert` (not a `raise`) clears a guarded parameter, and a
private function is exempt - so the same line can pass in `_helper` and fail in `helper`. Convert
a value that must be interpolated on its own first, join the pieces with string placeholders only,
confirm the generated SQL is byte-identical, and re-run that one checker.
