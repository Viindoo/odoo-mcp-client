---
name: odoo-modules-upgrade
argument-hint: "[module-cluster] [target-series]"
description: >-
  Upgrades custom module code to a higher Odoo major; no database migration
model: sonnet
---

## Role

Module-upgrade conductor. Move a whole cluster across MAJOR series in ONE PR, reviewed in dependency order (leaves first). Delegate every diff read and custom-vs-core comparison to subagents; read their structured output, enforce gates, run Plan Mode, open the PR, stop for human confirm. Per module decide what target core now ABSORBS: wholly absorbed -> DELETE + reason in the commit message; else KEEP / REWRITE / MERGE / SPLIT.

The upgrade is a CODE upgrade: Hard rule 4 and ${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md § Convention 0. A database upgrade between series needs a dedicated upgrade tool and repository; not this plugin - never raise, plan or offer it. Human sign-off before the PR merges.

## Hard rules

1. **Principal-checkout-lock.** NEVER check out or switch the principal checkout off its branch; materialize any branch through `git-toolkit:git-ops` (add a worktree).
2. **Plan Mode before any delete or code write** (${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md).
3. **ONE PR per cluster**, reviewed in dep order. No cluster-squash; per-module consolidation to one commit IS allowed (`references/upg-phase-detail-p4-p7.md` § Commit consolidation).
4. **Code upgrade only (Convention 0), two module classes.** This skill NEVER writes a migration script, never touches an existing database and never raises existing data. Every module the PR touches is classified at P0 and shown at P3:
   - **upgraded** - `installable` False at `<work-base>`, True after the PR: its `migrations/` directory is deleted and its `version` is not bumped (Convention 1);
   - **already installable** - `installable` True at `<work-base>` (an absent key counts as True) and changed in the same PR: it is live on databases of the target series, so its change keeps what they rely on (${CLAUDE_PLUGIN_ROOT}/snippets/odoo-platform-design-principles.md § 5, released series), its existing `migrations/` directories are never edited, and at P7 it takes the one version bump of § 5 through `odoo-data-migration`.
   Convention 0 settles every question about existing data, so none is asked (${CLAUDE_PLUGIN_ROOT}/snippets/read-before-act.md § 2).
5. **DELETE-absorbed** = directory removal + dep cleanup, never `installable: False`; the commit message names the replacing core feature. Gates: (a) the signal #5 behavioral-equivalence proof in `absorption/<module>.md`; (b) a per-DELETE human acknowledgment at P3, SEPARATE from the plan approval. OBSOLETE: state that the module is obsolete at `<tgt>`; never invent an `absorbing_core_feature`.
6. **Acceptance (P5.8) and i18n reconcile (P5.7, every surviving module) are mandatory**, narrow escape only; not DONE without the ACCEPTED verdict / per-module i18n result or a recorded escape.

## Out of Scope

| Situation | Route to |
|---|---|
| Transport ONE commit across majors | `odoo-forward-port` (same-series replay: `odoo-git-rebase`) |
| Rebase a branch, SAME series | `odoo-git-rebase` |
| Risk + deprecation + diff PLAN only | `/odoo-plan-upgrade` (writes no code) |
| Scan deprecated symbols / diff two versions' APIs only | `odoo-deprecation-audit` / `odoo-version-diff` |
| Fresh upgrade-safe code, no module to carry | `odoo-coding` |

A module/cluster major upgrade routes HERE, not to bare git-ops: invoke `git-ops` (Skill tool) for each git step. The prompt is free text passed through; optional hints go to the P0 subagent; ask the user only its `open_questions`.

## The pipeline

Artifacts: `<ISOLATE_DIR>/modules-upgrade/<src>-<tgt>-<cluster>/`; the symbols `<cluster>`, `<path>`, `<work-base>` and the artifact paths: `references/upg-phase-detail.md` § Symbols, § Artifact paths. Saga/rollback: ${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md. Phase detail: P0-P3 in `references/upg-phase-detail.md`, P4-P7 in `references/upg-phase-detail-p4-p7.md`, each under its `§ P<n>` section. Compose every dispatch from ${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md § Universal skeleton (read it by path) plus the agent's family delta.

**Sequence invariant.** `recon/classify -> (conditional) solution-design -> Plan Mode gate -> odoo-coding execution`. NO `odoo-coding` / `odoo-coder` / `odoo-frontend-coder` dispatch before the Plan Mode gate; a design doc is produced BEFORE the gate.

**Orphan sweep (every run, BEFORE P0).** `find <ISOLATE_DIR>/modules-upgrade/ -mindepth 1 -maxdepth 1 -type d -mmin +43200 -exec rm -rf {} +` (${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md § Clause 3).

- **P0 Intake [STOP if `open_questions` non-empty]:** one intake subagent (haiku) -> `intake.md`; classify every module per Hard rule 4; present the candidate list and the proposed cluster, ask, resume at P1. `references/upg-phase-detail.md` § P0.
- **P1 Recon [4 parallel]:** DAG, `odoo-deprecation-audit`, `odoo-version-diff`, Transitive Symbol Survey -> `graph.md`, `deprecation.md`, `version-delta.md`, `transitive-symbol-survey.md`; a DAG cycle is a `concerns:` entry the user breaks. § P1.
- **P2 Core-absorption comparison [per module, dep order]:** `odoo-diff-comparator` + `odoo-gap-analysis` -> `absorption/<module>.md` with the verdict and DUE / DEFERRED deferred work. § P2.
- **P2b Hard-call design [route-out on the comparator's `verdict:`]:** `MERGE`, `SPLIT`, `RECONCILE`, `MIXED`, a field-type `REWRITE(model)`, `DELETE-absorbed (with risk)`, a surface-changing or >5-call-site `REWRITE(api)` and a non-trivial `KEEP (with adaptation)` go to `odoo-solution-design` before P3; emit the Continuation Contract and YIELD, record `design_doc` on re-entry. § P2b.
- **P3 Plan gate [Plan Mode]:** the human approves the table + order BEFORE any code or deletion (${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md § One Plan-Mode gate per request); `Class` column, per-DELETE questions "Delete <module>? (approve / skip / cancel)", per surviving module its DUE and DEFERRED deferred-work counts, one `Docs:` line; then write `plan.md`. § P3.
- **P4 Adapt [per module, dep order]:** `odoo-coding` (Skill tool, never a raw coder) at the ADAPT tier of `references/upg-triage-table.md` in a child worktree off the integration worktree (n >= 2 modules; a single module dispatches into the integration worktree); DELETE/OBSOLETE modules are removed through `git-toolkit:git-ops`. § P4.
- **P4b Review loop [cap 3 per module]:** `odoo-code-review` per module; a clean review writes `<module>: reviewed`; CRITICAL/HIGH fixed by `odoo-coding` at the module's ADAPT tier, then re-reviewed; MED/LOW are recorded in the module's row and wait for P7; a third failing round is `BLOCKED`; never review or fix inline. Proceed to P5 ONLY when every adapted module is `reviewed` clean. § P4b.
- **P5 Install + test gate [one dependency level at a time]:** `odoo-instance` once, `GATE_ROLE: node-verify` per level -> `install-test.md`; then release the P5 lease (`lease_release`, `lease_park` only for a named later step) before P5.7, never between levels (${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md T1). § P5.
- **P5.7 i18n reconcile [MANDATORY]:** `odoo-i18n` on a fresh instance with the existing `.po` loaded, with `HAND_ON: odoo-doc-illustration` when the P3 `Docs:` line is not `none`; escapes per ${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md. § P5.7.
- **P5.8 Acceptance [MANDATORY, cluster-wide]:** `odoo-acceptance` ONCE, scope per ${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md; skip only for a true leaf, recorded in `install-test.md`. § P5.
- **P6 Gate [STOP]:** present `plan.md`, `absorption/*` (with each module's `vendor_api_checked:` line and every DUE marker left in place with what it waits for), `install-test.md` and the P5.8 verdict; ask `approve / skip / cancel`; `skip` ends the run unpushed.
- **P7 - Final review + PR [human merge]:** in the order of ${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md § Default tail - the Runbot parity gates, the convention pass (${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md), the two-class gate: the PR is not opened while (a) an `upgraded` module still carries a `migrations/` directory, (b) an `upgraded` module's manifest `version` changed other than by dropping a series prefix, an `already installable` module changed outside its tests lacks its one smallest-step bump, or a migration script was added, or (c) any file under a `migrations/<older series>.*/` directory is modified; then the perf and i18n passes and the final dep-order review with its CRITICAL/HIGH fixed; ONLY then push and open the PR through `git-toolkit:git-ops`. § P7.

After the PR exists, only PR-OBSERVING work and the closing docs remain: document the upgraded user-visible features per ${CLAUDE_PLUGIN_ROOT}/snippets/docs-after-change.md (the P5.7 build serves the module-docs step and is released after it).

## Checkpoint / resume

`checkpoint.json` (in the artifact dir) maps each module to `pending | absorbed | designed | adapted | reviewed | installed | done`, written after each phase; on restart each phase skips modules at or past its threshold (P2 past `absorbed`, P4 past `adapted`, P4b past `reviewed`, P5 past `installed` per dependency level). Schema and skip table: `references/upg-phase-detail-p4-p7.md` § Checkpoint / resume.

## Git / PR conventions

${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md; all through `git-toolkit:git-ops`: branch `upg/<src>-<tgt>-<cluster>`; integration worktree `<path>/upg-integration`, base `<work-base>`; a commit request names the files, the business outcome and `WORKTREE_PATH`, never a composed message (tag: `upg-conventions.md` § Convention 0); push to the fork remote (from `remotes` of a `repo_facts` call); PR against the upstream from its `origin_url`.

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
- `set_active_version` ☆ - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
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

OSM unreachable: P0 and P1 read branch name, manifests and `depends` (BOTH descriptor names) from disk; other skills and the P2 comparator use ${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md. Label artifacts `grounded: local-source - not OSM-indexed`.

## Continuation Contract

At the end or a gate, append a Continuation Contract block per ${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md (status / produced / next); `produced` lists the phase artifacts, `plan.md`, `checkpoint.json` and the PR URL. When P2b routes a module out, `next: odoo-solution-design` and the run YIELDS. Fold P4b findings into `install-test.md`. Both review points (P4b per module, P7 final) are required.
