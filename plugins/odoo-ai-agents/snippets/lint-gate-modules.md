<!-- SSOT snippet. The single home for WHICH modules make up the backend lint-class gate, how to
     select and scope them, and the stale-index false-green trap. Consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md - never restate the module set elsewhere. -->

# Backend lint-class gate - module selection

This snippet decides WHICH modules make up the backend code-quality gate and how a run of them is
read. WHETHER the gate runs on a dispatch is owned by `GATE_ROLE` (`odoo-instance-ops` § Lint modules).

## Candidate set

Odoo core `test_lint` (its series presence: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md`
§ Backend lint-class gate), plus every lint-class module the resolved addons path SHIPS: a module
whose technical name starts with `test_` and whose tests run flake8 or pylint. Find them by reading
the resolved addons path, never from memory.

## Selection - run every step, in order

1. List the candidates above for the target series and addons path.
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

`check_module_exists` answers from the revision it indexed, so it can report Indexed = Yes for a
module the addons path no longer ships. That name installs nothing, its tag matches nothing, and the
run reports a clean pass anyway - a FALSE GREEN on the gate whose job is to catch what review missed.

- The addons path decides the module; the probe only confirms the pinned profile carries it.
- After the run, confirm from the build log that every tagged lint module INSTALLED and its tests
  LOADED. A tagged module whose tests never loaded makes the gate `tests-inconclusive`, never a
  pass - report it as a finding and name the module.
