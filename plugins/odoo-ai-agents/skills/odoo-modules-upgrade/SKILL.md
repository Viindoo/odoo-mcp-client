---
name: odoo-modules-upgrade
argument-hint: "[module-cluster] [target-series]"
description: >-
  Upgrades custom module code to a higher Odoo major; no database migration
model: sonnet
---

## Role

Module-upgrade conductor. Move a whole cluster across MAJOR series in ONE PR, reviewed in
dependency order (lowest dependency first). Delegate every diff read and custom-vs-core
comparison to subagents. Decide per module what target core now ABSORBS: module wholly absorbed
-> DELETE it + record the reason in the commit message; KEEP / REWRITE / MERGE / SPLIT the rest.
The upgrade is a CODE upgrade (`${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md` § Convention 0):
make each module install and work on a fresh database of the new series, modernised as if newly
developed there; write NO migration script, DELETE the `migrations/` directory of every upgraded
module, touch no existing database, and do NOT bump the manifest `version` (§ P4). What the upgrade
renames, removes or deletes goes into `migration-notes.md` (§ P7).
No cluster-squash; per-module consolidation to ONE
clean commit per module IS allowed (`references/upg-phase-detail.md` § Commit consolidation).
Human sign-off before the PR merges.

Parse nothing you can delegate, read no diff, and compare no behavior inline: dispatch subagents,
read their structured output, enforce gates, run Plan Mode, drive the dep-order adapt loop, open the
PR, and stop for human confirm.

## Out of Scope

| Situation | Route to | Discriminator |
|---|---|---|
| Transport ONE commit across majors/cross-series | `odoo-forward-port` | different series = forward-port, never asks "still needed?"; same-series single-commit replay = `odoo-git-rebase` |
| Rebase a branch onto another branch, SAME series | `odoo-git-rebase` | same series, no version bump, no core-absorption question |
| Risk + deprecation + diff PLAN only (no code) | `/odoo-plan-upgrade` | plan-upgrade writes NO code; upgrade EXECUTES (may take its plan as optional `--plan` input) |
| Scan deprecated symbols only | `odoo-deprecation-audit` | detection only; upgrade INVOKES it in recon then fixes |
| Diff two versions' APIs only | `odoo-version-diff` | detection only; upgrade calls it in recon |
| Write fresh upgrade-safe code, no module to carry | `odoo-coding` | nothing to upgrade |
| Migration scripts for a database migration project | `odoo-data-migration` | the user's separate request; never a step of this upgrade |

> An Odoo module/cluster major-version upgrade routes HERE, not to bare git-ops: drive this
> pipeline and invoke `git-ops` (via the Skill tool) for each git step.

## Invocation - free natural language

`/odoo-modules-upgrade <free text>` passes the whole prompt through. There are NO required
positional parameters and NO inferring inline. Optional structured hints (an explicit module
scope, an explicit target version, a prior `/odoo-plan-upgrade` output path) are passed straight to
the P0 intake subagent. Dispatch P0 first and ask the user only the `open_questions` it returns.

## The pipeline

`<cluster>` = the scope slug (the `cluster_slug` field resolved in P0 intake). Artifacts under
`<ISOLATE_DIR>/modules-upgrade/<src>-<tgt>-<cluster>/` (resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once
per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute
path). `<path>` = the upgrade-worktree base, a `.upg-worktrees/` directory SIBLING to the principal
checkout (never inside it). Saga/rollback + checkpoint contract:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md` (record the pre-loop SHA, checkpoint each
integrated dependency level, clean-abort or resume on failure). `<work-base>` = the base ref the integration branch forks from: HEAD
of the target-series branch when one exists, else the merge-base of the cluster against the
target series. ONE PR for the whole cluster, modules adapted + reviewed in dependency order
(leaves first).

Full per-phase commands, dispatch briefs, and artifact formats:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-phase-detail.md`.

When composing the dispatch prompt for any specialist agent you dispatch, fill the caller-side
skeleton in `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton (read it by path) plus the target
agent's family delta; never inline that file verbatim into a hard-leaf brief.

**Sequence invariant.** `recon/classify -> (conditional) solution-design -> Plan Mode gate ->
odoo-coding execution`. NO `odoo-coding` / `odoo-coder` / `odoo-frontend-coder` dispatch before the
Plan Mode gate. When a design trigger fires for a module, its design doc is produced BEFORE the
gate. A change that skips design STILL passes through the gate.

---

**Orphan sweep (every run, BEFORE P0 below).**

`find <ISOLATE_DIR>/modules-upgrade/ -mindepth 1 -maxdepth 1 -type d -mmin +43200 -exec rm -rf {} +`

Rule: `${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3.

**P0 - Intake / resolve [STOP if open_questions non-empty].** Dispatch ONE intake subagent (haiku): it resolves the source series from the branch name cross-checked against the manifests, the OSM profile, the source and target versions, the candidate modules (descriptor `version` below the target, modules depending on one, profile membership for short-form manifests; `installable: False` is a weak hint), the dependency hints, and - when the scope is not explicit - a proposed cluster seeded from the dependency closure, returned as `open_questions`, never guessed. Output `intake.md`; classify every module of the scope per Hard rule 5 (`upgraded` | `already-installable`). Gate: non-empty `open_questions` -> present the candidates and the proposed cluster, ask, then resume at P1. Brief: `references/upg-phase-detail.md` § P0 - Intake / resolve.

**P1 - Recon [four parallel dispatches].** (a) `Explore` (haiku) builds the dependency DAG from the descriptors and the leaves-first order; (b) `odoo-deprecation-audit` (Skill tool, haiku) for source + target; (c) `odoo-version-diff` (Skill tool, sonnet) for the delta; (d) the Transitive Symbol Survey (`Explore`, haiku) grounding every external symbol at the target into `blockers[]` that gate P3/P4. Outputs `graph.md`, `deprecation.md`, `version-delta.md`, `transitive-symbol-survey.md`. A DAG cycle is a `concerns:` entry the user breaks before P2; every dependency must exist at the target. Briefs: `references/upg-phase-detail.md` § P1 - Recon.

**P2 - Core-absorption comparison [per module, dep order, parallel within a dependency level].** Per module, after its in-cluster dependencies: ONE `odoo-diff-comparator` (sonnet) plus `odoo-gap-analysis` (Skill tool, sonnet) in parallel under Mode B of `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`. The comparator classifies each feature per `references/upg-classification-table.md` against the target core and owns the whole-module verdict (DELETE-absorbed / KEEP / REWRITE(api) / REWRITE(model) / MERGE / SPLIT / OBSOLETE), and in the same read reconciles version-anchored deferred work (`TODO`/`FIXME`/`XXX`/`HACK`): DUE (anchored at or below the target: real work in P4), DEFERRED (a higher version: untouched), UNANCHORED (flagged to the human). Output `absorption/<module>.md`. Rule: `${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md` § Convention 0. Briefs: `references/upg-phase-detail.md` § P2.

**P2b - Hard-call design [mandatory route-out on the comparator's `verdict:`].** `MERGE`, `SPLIT`, `RECONCILE`, `MIXED`, `REWRITE(model)` with a field type change, `DELETE-absorbed (with risk)`, a `REWRITE(api)` that changes the public model surface or touches more than 5 call sites or 2+ modules, and a `KEEP (with adaptation)` meeting the non-trivial criterion of `odoo-solution-design` route to `odoo-solution-design` (opus) before P3; a localized fix (<= 5 call sites, one module, no public-surface change), `DELETE-absorbed (no risk)` and `OBSOLETE` never route. Emit the Continuation Contract and YIELD; on re-entry record `design_doc` and proceed to P3. Full table: `references/upg-phase-detail.md` § P2b.

**P3 - Plan gate [Plan Mode].**
The human approves the per-module DELETE/KEEP/REWRITE/MERGE/SPLIT table + install
order BEFORE any code is written or module deleted. This is the request's one Plan-Mode gate
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request): call
`EnterPlanMode`, then present the plan CONTENT (authored here, not routed through
`odoo-planning`): per-module
classification table (one `Class` column: `upgraded` | `already-installable`, Hard rule 5, with
the bump and migration policy of that class; DELETE -> list the core feature that replaces each AND inline the
behavioral-equivalence summary from `absorption/<module>.md` - the proof that every
override is equivalent or no-op; REWRITE/MERGE/SPLIT -> adapt tier + design link);
topo-sorted adapt order (leaves first); design-doc links for any P2b module. For every surviving module (KEEP/REWRITE/MERGE/SPLIT), inline its DUE
version-anchored deferred-work count and list every UNANCHORED marker from
`absorption/<module>.md` `deferred_work` for human awareness (never silently absorbed or
dropped). One `Docs: <module | site | both | none> - <facts>` line: the documentation target the
closing step writes, taken from `odoo-intake`'s Documentation routing facts in the brief, or decided
here by that rule when none came (ask only on a miss); `refine: no docs` drops it.
For EVERY module with a DELETE verdict, the plan table MUST inline:
(a) the absorbing_core_feature or OBSOLETE reason,
(b) the behavioral-equivalence proof summary (from signal #5 in `absorption/<module>.md`),
(c) a per-DELETE confirmation, a text question: "Delete <module>? (approve / skip / cancel)" -
    `skip` keeps the module (separate from the overall plan approval).
`ExitPlanMode` on approve: the user approves the plan AND answers every per-DELETE confirmation.
After approval: write `plan.md` (the approved plan; SSOT for P4+). `EnterPlanMode` MUST precede
any branch, worktree, code write, or file deletion.

**P4 - Adapt [per module, dep order, child worktrees].** Create the integration worktree through `git-toolkit:git-ops` (§ Git / PR conventions). Per module in dep order invoke `odoo-coding` (Skill tool, never a raw coder) at the ADAPT tier of `references/upg-triage-table.md`, in a child worktree off integration. DELETE-absorbed / OBSOLETE: `odoo-coding` runs the dangling-reference sweep, then git-ops removes the directory and commits (confirmed at P3) and every depender's `depends` drops it. KEEP / REWRITE / MERGE / SPLIT: the brief carries the P1d `blockers[]` as a preemptive fix list, the catalog path of `references/upg-classification-table.md` (never pre-applied), the P1 deprecation list, the module's DUE deferred work, `installable: False -> True`, the `migrations/` deletion (Convention 0), no version bump (a series prefix is converted, never bumped), `auto_install`/`application` only on a breadcrumb, and the adapt fields (`MODE: adapt`, `INTENT`, `SOURCE TESTS`, `BROKEN TEST-SYMBOLS`, `RUN_ID`). `odoo-coding` commits in the child worktree; converge serially into integration and remove the child. Brief template: `references/upg-phase-detail.md` § odoo-coding dispatch brief; field detail: § P4 - Adapt.

**P4b - Code-review loop [cap 3 per module].** Dispatch `odoo-code-review` (Skill tool) per adapted module in dep order, scoped to its adapt diff on `worktree:<path>/upg-integration`; a CRITICAL/HIGH finding goes to `odoo-coding` at the ADAPT tier for a root-cause fix and a re-review; MED/LOW wait for P7; a third round still CRITICAL/HIGH is `BLOCKED`. Never review or fix inline. Write `<module>: reviewed` in `checkpoint.json`. A `next: odoo-acceptance` a review emits is not acted on per module - P5.8 covers the cluster once. Loop protocol: `references/upg-phase-detail.md` § P4b.

**P5 - Install + test gate [ephemeral instance, one dependency level at a time].** Dispatch `odoo-instance` (Skill tool) once, then per dependency level (leaves first) init that level's modules and run its tests with `GATE_ROLE: node-verify` - an automation-test build whose demo shape is the row of `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Demo data by build PURPOSE, and whose framework-validation classes `odoo-instance-ops` unions in. A red level goes to `odoo-backend-debugger` or `odoo-ui-debugger` for the root cause, back to P4 for that module, and P5 resumes from the failing level per `checkpoint.json`. Output `install-test.md`. Cross-ref `references/runbot-parity-checklist.md`.

**P5 instance release [MANDATORY].** Once every level is green, release the P5 lease (`lease_release` with the cached token and `run_id`; `lease_park` only for a named later step) before P5.7 - never between levels (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1).

**P5.7 - i18n reconcile [MANDATORY for every surviving module, narrow escape only].** Invoke `odoo-i18n` against a fresh instance with the existing `.po` loaded (re-export, git-ops diff-review of every loss, translate the empty `msgstr` per `${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md`, reload); an escape is one of `${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`, recorded in `install-test.md`.

**P5.8 - Acceptance [MANDATORY, cluster-wide, narrow escape only].** Compute the verify scope with `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md` (`changed_set` = every surviving module; the reverse closure from `graph.md`) and invoke `odoo-acceptance` ONCE for the cluster: `INPUTS` = the changed set, `scope_hint` = `graph.md` + `absorption/*.md`, `odoo_version` = target, `INSTANCE_HANDLE: none provisioned`, `ACCEPTANCE` by pointer to each module's `absorption/<module>.md` behaviour and any P2b design §9 - never the implementation. Skip only when `graph.md` proves a true leaf with no dependents and no behavioural surface, recorded in `install-test.md`. The upgrade is not DONE without ACCEPTED or that recorded escape; the verdict is presented with the P6 sign-off. Output `<ISOLATE_DIR>/qa/<slug>-acceptance-report.md`. Detail: `references/upg-phase-detail.md` § P5, P5.7 and P5.8.

**P6 - Gate [STOP, human sign-off].**
Present `plan.md` + `absorption/*` summaries + `install-test.md` (including the list of
DELETED-absorbed modules + their reasons) + the P5.8 acceptance verdict (or its recorded
narrow-escape) and ask, as a text question, `approve / skip / cancel`. Wait for
`approve` before the PR; `skip` ends the run with the branch unpushed.

**P7 - Final review + PR [human merge].** In the order of `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Default tail: the Runbot parity gates (`references/runbot-parity-checklist.md`); the convention pass (manifest version form, always-invisible XML comment, `${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md`); the two-class gate - the PR is not opened while (a) an `upgraded` module still carries a `migrations/` directory, (b) an `already-installable` module's diff touches data, fields or models with its manifest `version` unchanged or no migration file although existing data moves, or (c) any file under a `migrations/<older series>.*/` directory is modified; `migration-notes.md` compiled by one haiku subagent from the P1 survey, `absorption/*.md`, `version-delta.md` and the deleted `migrations/` paths, linked from the PR body; a perf-lens pass; the i18n pass (P5.7 ran or each skip is a recorded escape); then the final dep-order review of the integration worktree through the review capability, its CRITICAL/HIGH fixed; ONLY then push and open the PR through `git-toolkit:git-ops` (§ Git / PR conventions). Checklist detail: `references/upg-phase-detail.md` § P7 - Final review + PR.

After the PR exists, only PR-OBSERVING work (CI-failure triage, the human merge) and the closing docs below remain. Wait for human merge.

With the PR presented, document the upgraded user-visible features for the target the P3 plan
approved, per `${CLAUDE_PLUGIN_ROOT}/snippets/docs-after-change.md` (a module still
`installable: False` at the target keeps the docs it had).

## Hard rules

1. **Principal-checkout-lock.** NEVER check out or switch the principal (main)
   checkout off its branch. Materialize any needed branch through `git-toolkit:git-ops` (add a worktree).
2. **Plan Mode before any delete or code write.** No directory removal, no code changes, no
   worktree branch until P4 post-gate (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md`).
3. **No cluster-squash; per-module consolidation allowed** (`references/upg-phase-detail.md`
   § Commit consolidation, via `git-toolkit:git-ops`). Commit message formats: § Git / PR conventions.
4. **ONE PR per cluster.** All modules in one PR, reviewed in dep order.
5. **Code upgrade only (Convention 0), two module classes.** This skill NEVER writes a migration
   script for an upgrade, never touches an existing database and never stops to ask about
   existing data. Every module the PR touches is classified at P0 and shown at P3:
   - **upgraded** - `installable` False at `<work-base>`, True after the PR: no version bump; its
     `migrations/` directory is deleted and recorded in `migration-notes.md` (§ P7), together
     with what the upgrade changes for existing data;
   - **already installable** - `installable` True at `<work-base>` (an absent key counts as
     True) and changed in the same PR: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-platform-design-principles.md`
     § Migrations are decided last applies - after P5 is green, when its change alters data
     existing databases hold, ONE version bump and at most one migration file per stage, written
     through `odoo-data-migration`; its older `migrations/` directories are never edited.
   A human answer about existing data is recorded against the class it names and never widened
   to the other (`${CLAUDE_PLUGIN_ROOT}/snippets/read-before-act.md` § 2).
6. **DELETE-absorbed = delegated directory removal + dep cleanup + commit message, with two mandatory gates.**
   A module wholly absorbed by core is removed entirely, not set to `installable: False`.
   The commit message carries the reason (which core feature replaces it). No directory removal is
   permitted without: (a) signal #5 behavioral-equivalence proof recorded in
   `absorption/<module>.md` (all overrides enumerated + each proved equivalent or no-op);
   AND (b) an explicit per-DELETE human acknowledgment at P3, SEPARATE from the overall plan approval:
   each DELETE row requires its own confirm.
   For OBSOLETE verdict (module is moot at target, not absorbed by a named feature): the
   commit request's business outcome states the module is obsolete at `<tgt>` (`<reason>`) -
   do NOT invent a fake `absorbing_core_feature`.
7. **Acceptance is mandatory (narrow escape only):** P5.8. The upgrade is not DONE without an
   ACCEPTED verdict or a recorded narrow-escape.
8. **i18n reconcile is mandatory (narrow escape only):** P5.7, for EVERY surviving module. The
   upgrade is not DONE without a per-module i18n result or a recorded escape.

## Checkpoint / resume

`<ISOLATE_DIR>/modules-upgrade/<src>-<tgt>-<cluster>/checkpoint.json` maps each module to `pending | absorbed | designed | adapted | reviewed | installed | done`, written after each phase; on restart each phase skips the modules at or past its threshold (P2 past `absorbed`, P4 past `adapted`, P4b past `reviewed`, P5 past `installed` per dependency level). Schema and skip table: `references/upg-phase-detail.md` § Checkpoint / resume.

## Cluster / dependency handling

- DAG built ONCE in P1 by a subagent; you only topo-sort it.
- P2->P4 run per module in dep order (leaves first).
- P5 installs bottom-up ONE DEPENDENCY LEVEL AT A TIME (leaves first), recording per-level green.

## Git / PR conventions

Git delegation contract: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.

- Branch: `upg/<src>-<tgt>-<cluster>` (e.g. `upg/<src>-<tgt>-l10n_vn`).
- Integration worktree: invoke `git-toolkit:git-ops` to add a worktree (branch
  `upg/<src>-<tgt>-<cluster>`, worktree `<path>/upg-integration`, base `<work-base>`).
- Commit messages: request the commit via `git-toolkit:git-ops` - the files touched, the business
  outcome (which module moved from which series to which, and what action was taken: KEEP,
  REWRITE, MERGE, SPLIT, or delete-absorbed/delete-obsolete with the reason), and `WORKTREE_PATH`.
  Do not compose or prescribe the message; the proposed tag is the series-upgrade tag
  (`upg-conventions.md` § Convention 0).
- Push to fork: invoke `git-toolkit:git-ops` to push branch `upg/<src>-<tgt>-<cluster>` to the fork
  remote (resolve the fork remote from the `remotes` of a `repo_facts` call, or a dedicated fork remote).
- PR: invoke `git-toolkit:git-ops` to create the PR (resolve upstream org/repo from the `origin_url` of a
  `repo_facts` call).

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`, `describe_module`, `check_module_exists`, `resolve_orm_chain`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `find_deprecated_usage` - Scan the indexed codebase for usages of deprecated API patterns.
- `entity_lookup` ★ - Single-entity drill-down by kind discriminator: model, field, method, view, module, pattern, or report - with full inheritance chain and source module.
- `lookup_core_api` - Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `validate_depends` ⊕ - Validate compute method's `@api.depends('a.b', ...)` paths; flag `id` and suggest typos.
- `cli_help` - Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags.
- `list_available_profiles` ☆ - Enumerate which tenant profiles exist in the server index.
- `profile_inspect` - Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
<!-- END GENERATED TOOLS -->

## Standalone-first fallback

When OSM is unreachable, P0 intake derives
series from the branch name + reads manifest files directly (no OSM needed). P1 recon
reads each descriptor's `depends` from disk (BOTH names) for the DAG; `odoo-deprecation-audit` and
`odoo-version-diff` each have their own standalone fallback (disk-fallback-protocol).
P2 comparator falls back to disk reads of the source module + the target checkout per
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`. Label all artifacts
`grounded: local-source - not OSM-indexed`. The install+test gate (P5) is unaffected.

## Continuation Contract

When the run finishes (or pauses at a gate), append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next).
`produced` lists `intake.md`, `graph.md`, `deprecation.md`, `version-delta.md`,
`transitive-symbol-survey.md`, `absorption/*.md`, `plan.md`, `install-test.md`, `migration-notes.md`,
`<ISOLATE_DIR>/qa/<slug>-acceptance-report.md`, `checkpoint.json`, and the PR URL.
When P2b routes a module out to design, `next: odoo-solution-design` with the Continuation
Contract payload and the run YIELDS. Fold P4b findings into the module rows of `install-test.md`.
Both review points (P4b per module, P7 final dep-order review) are required.
