---
name: odoo-acceptance
argument-hint: "[module/cluster to accept]"
description: >-
  Acceptance test of a change on a live instance and UI: PASS/FAIL
---

## Role

Front door for proving, on a live instance, that a change does what its SRS criteria say. It
resolves the scope, launches `odoo-qa-tester` in its modes at their tiers, and returns the
verdict with evidence. It launches and returns; the fix round belongs to the caller, who resumes
the node's coder and the reviewer with the tester's report. The oracle author, the coder and the
adjudicator stay three contexts
(`${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-oracle-contract.md`). The oracle and the verdicts
obey `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-platform-design-principles.md` § 0: a policy limit is
expected to flag and allow, a block to have a way out, a surface to behave as core's does.

## Out of Scope

- **A static release test plan or a deploy checklist** (no execution) -> `odoo-qa-suite`
- **Rating one rendered screen** -> `odoo-ui-review`
- **Static review of a diff or PR** -> `odoo-code-review`
- **Fixing the code** -> the caller resumes the node's coder; **root cause of one symptom** -> `odoo-debug`
- **A standalone durable test with no acceptance loop** -> `odoo-test-writing`
- **Walkthrough text for documentation** -> `odoo-doc-feature-map`

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
- `set_active_version` ☆ - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- `impact_analysis` - Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `cli_help` - Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags.
<!-- END GENERATED TOOLS -->

## Inputs

| Field | Meaning |
|---|---|
| `MODULES`, `WORKTREE_PATH`, `ODOO VERSION`, `PROFILE`, `RUN_ID` | the node's modules and the tree the instance is built from |
| `SRS` or `ORACLE_PATH` | the acceptance criteria; `scenarios.md` when a planner wrote one |
| `RECON` | for the in-repo dependents of the modules (`none` when absent) |
| `DOMAIN` | the Domain line; its `Audience` drives mode `A4` |
| `SHARE_DIR`, `ISOLATE_DIR` | captured once against `WORKTREE_PATH` |
| `INSTANCE_HANDLE` | optional: a demo-loaded cluster built from the same tree |
| `WHEN` | the plan node's condition, already evaluated true by the caller |

## Steps

1. **State dirs and slug.** Capture `SHARE_DIR` and `ISOLATE_DIR` with `project_dir` against
   `WORKTREE_PATH`; mint the run `SLUG`
   (`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 1); delete
   `<ISOLATE_DIR>/visual/qa/<slug>/` directories untouched for 30 days (Clause 2).
2. **Oracle readiness.** Every criterion of `SRS` has a role, a precondition, steps and a
   comparable expected value. One that does not: launch `odoo-qa-planner` (`model: sonnet`) for
   those criteria only, with `REQUIREMENT` = the SRS and `SCENARIOS_PATH:
   <ISOLATE_DIR>/qa/<slug>-scenarios.md`; the result is the `ORACLE_PATH` for them. Never the
   planner for criteria that are already executable.
3. **Scope.** Build the verify-scope manifest per `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md`
   (reverse closure, risk rank, affected screens) into `<ISOLATE_DIR>/qa/<slug>-scope.md`;
   `DEPENDENTS` = the in-repo dependents of `MODULES` from `RECON` and the manifest grep of the
   repo (`none` when there are none).
4. **Launch `A1A2`** (`odoo-qa-tester`, `MODE: A1A2`, `model` per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection - `haiku` unless a
   Given needs a fixture built): `ORACLE_PATH`, `MODULES`,
   `DEPENDENTS`, `WORKTREE_PATH`, `ODOO VERSION`, `PROFILE`, `RUN_ID`, `SCOPE` (screens and roles
   of the manifest), `BROWSER_MODE` (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md`),
   `SLUG`, `SHARE_DIR`, `ISOLATE_DIR`, `DOMAIN`, `INSTANCE_HANDLE` when one exists, `REPORT_PATH:
   <ISOLATE_DIR>/qa/<slug>-acceptance-report.md`. One tester per browser family; several
   families may run in parallel up to the pool cap of
   `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Browser exclusivity.
5. **Launch `A4`** (`MODE: A4`, `model: sonnet`) in the same message when the node adds a menu,
   a report or a screen for an end user and `Audience` is not `n/a`; it reuses the cluster
   handle the `A1A2` tester reports, or waits for it.
6. **Durable tests** when the plan asks for them: launch `odoo-test-writer` (`MODE: tour/HttpCase`,
   `model: haiku` when every scenario is executable, else `sonnet`) for the High-tier PASS
   scenarios. Provision its fresh test instance without demo through `Skill(odoo-instance)`
   (`${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`), pass it as `INSTANCE_HANDLE`, and
   release that lease after the writer returns. Commit the files it returns through
   `git-toolkit:git-ops`; the writer never commits.
7. **Return.** The report path, the roll-up (PASS, FAIL, UNVERIFIED per database; `ACCEPTED` or
   `REJECTED`), the A4 rows, the bug list, and the Continuation Contract. UNVERIFIED on a
   High-tier scenario: relaunch the tester for that scenario on a fresh session at most twice,
   then report it `BLOCKED (evidence unobtainable)`. Every lease the testers took is released
   by them before they return; a forwarded `INSTANCE_HANDLE` is never released here. For a UI
   change, open the screenshots yourself before you accept - desktop and mobile, every screen
   reported as changed and a sample of those reported identical - and say what you saw: a
   tester's verdict forwarded unseen is not acceptance.

## Standalone-first fallback

OSM unreachable: the scope closure comes from the manifests on disk and the manifest says
`closure approximate from disk`. No live instance reachable: still produce the scope and the
oracle, then return `NEEDS_NEXT: odoo-instance`; never `ACCEPTED` without live evidence.

## Agent-managed tools

`odoo-qa-tester` (two modes), `odoo-qa-planner` (only for criteria that are not executable),
`odoo-test-writer` (durable tests when the plan asks). Each is a leaf; the tester invokes
`odoo-instance` inline for the databases it builds.

## Continuation Contract

Append the block of `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`: `produced` = the
scope, oracle and report paths; `status: DONE` with the roll-up; a FAIL is reported in the
result, never driven into a fix from here.
