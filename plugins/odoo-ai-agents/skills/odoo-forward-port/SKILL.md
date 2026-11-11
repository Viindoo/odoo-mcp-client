---
name: odoo-forward-port
argument-hint: "[from-series] [to-series] [module/range]"
description: >-
  Ports commits, module docs or docs-site pages from a lower Odoo series to a higher one
model: sonnet
---

## Role

Forward-port conductor: own the git topology, the per-commit SEMANTIC pipeline and the subagent lifecycle. The git unit is the RANGE (Hard rule 2). Delegate leaf work and every P6 / P6-TEST / P7 gate to specialist agents
and read-only delegates (`[[fp-symbol-survival-check]]` - Who runs this check); you record verdicts
and finding lines, never produce them. A green merge + lint + install proves nothing (Hard rules 4-5). Code, module docs and docs-site pages
all run HERE; P0 picks the lane (docs-site: `references/fp-docs-site-lane.md`,
replacing only the content phases).

Route out: no commit -> `odoo-coding`; API delta only -> `odoo-version-diff`; review ->
`odoo-code-review`; deprecation sweep -> `odoo-deprecation-audit`; same-series replay ->
`odoo-git-rebase`; whole-cluster upgrade -> `odoo-modules-upgrade`; standalone design ->
`odoo-solution-design`; N disjoint WIs with
cherry-pick + squash -> `odoo-planning`; upgrade plan only -> `/odoo-plan-upgrade`.

`/odoo-forward-port <source-ref> <target-branch> [--scope <mod1,mod2>] [--since <sha>]`, parsed from
`$ARGUMENTS` in P0 (missing `source-ref` / `target-branch` -> ask once before any read
or git-ops request). ONE shape, no mode flag; to land PART of a branch pass that sub-range's TIP SHA.

## Hard rules

1. **Target-branch-lock** - NEVER checkout, switch, commit, merge, rebase, reset or push target
   branch B (reads allowed). Integrate only in the JOB-tier worktree `fp/<slug>` branched
   FROM B (`<path>/fp-integration`); P8 adapts DIRECTLY there, no per-module child worktree.
   Every mutation goes via `git-toolkit:git-ops` (`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`);
   saga: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`.
2. **ONE merge, ONE merge commit** - a single true merge of the range TIP, left uncommitted
   (`[[fp-merge-absorption]]`), closed by one merge commit; every source SHA is preserved; the commit count never sets the merge count. BANNED:
   (i) merging or committing one source commit at a time; (ii) cherry-pick at ANY granularity. A
   batch merges its own tip once; a FROZEN source merges alike.
3. **Intent before code** - forward the behavior, never a source hunk. SSOT
   `[[fp-intent-4outcome]]`.
4. **Verify by behavior** - the forwarded INTENT test passes on the target AND its node's test leg
   broke the rule and restored the code
   (`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`); a bucket-(a) source test passes
   with the commit's code out of play.
5. **Symbol-survival before adapt** - after every merge run P6 on conflicted AND merge-clean-but-
   source-touched files; resolve every broken symbol into a bucket first.
6. **Human gates are P4 (plan) and P12 (PR merge); local merges are self-decided.** P4 is the one
   Plan-Mode gate (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate); P10 concludes each batch on `fp/<slug>` unasked and lands nothing on B; no auto-merge.
7. **Buckets (a)/(d) are still ABSORBED** - never narrow the range to exclude them; record bucket +
   reason on the `merge-log.md` row and in the merge commit body.
8. **Verify subagent claims** - never trust a leaf's GREEN; run the P9 verify yourself per batch.
9. **Acceptance (P11) is mandatory**, narrow escape only: no DONE without ACCEPTED or a recorded escape.
10. **i18n reconcile is mandatory**, narrow escape only: 8e COMPUTES the conditions, P9.5 DISPATCHES
    `odoo-i18n` per batch; skip only via an enumerated escape on the module's `merge-log.md` row
    (`${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`); no DONE without a result or escape
    for each `i18n_due: yes` module.
11. **Descriptor filename resolves ONCE, per side** - from `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md`
    row 6: at P0 record `<tgt-descriptor>` (`target_ref`) and `<src-descriptor>` (`source_ref`; they
    can differ). Reuse those literals for every descriptor read, path and assertion: `installable`,
    `depends`, `version`, `manifest_path`, `history_dump_path`, and the P9 addons-coverage assertion. An absent descriptor may mean the
    WRONG FILENAME was opened; a failed read never justifies dropping the module or guessing
    `installable` / `depends` / `demo`.

## The pipeline

Dispatch briefs: `references/fp-phase-briefs.md` § Dispatch-brief skeleton; fan-out: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
(Mode B). Before P0, sweep:
`find <ISOLATE_DIR>/forward-port/ -mindepth 1 -maxdepth 1 -type d -mmin +43200 -exec rm -rf {} +`
(`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3).

- **P0 Recon** [read-only]: read the Forward-port row of `${CLAUDE_PLUGIN_ROOT}/snippets/read-before-act.md`;
  resolve `REPO KIND` (descriptor in tree -> `addons`; declared docs-site row -> `docs-site`; neither
  -> `NEEDS_CONTEXT` naming `/odoo-ai-agents:odoo-setup docs-site`); enumerate the range via git-ops,
  record `<src-first-SHA>` / `<src-tip-SHA>`; the source-tip merge lands every commit above the merge
  base, colleagues' included: record the merge base and the unnamed commits, and show that real scope at
  P4 before anything merges (empty range -> `DONE`); build `module -> [shas]`; EXTRACT tier inline (`references/fp-phase-p0-p4.md` § P0).
- **P1 Intent** [parallel, read-only]: at most ONE `odoo-intent-extractor` per module for the whole
  run. `references/fp-phase-briefs.md` § P1.
- **P2 Classify** + installable-probe: bucket a/b/c/d per commit, `merge-log.md` row, `installable_false`
  per module (`[[fp-installable-false]]`). `references/fp-phase-p0-p4.md` § P2.
- **P3 Design** [route-out]: bucket-(c) on a non-trivial module -> `odoo-solution-design` and YIELD.
  `references/fp-phase-p0-p4.md` § P3.
- **P4 Plan gate** [Plan Mode]: `EnterPlanMode` before any touch; module-first plan, batches
  (default ONE), `Docs:` line; then git-ops creates `fp/<slug>`, write `plan.md`. `references/fp-phase-p0-p4.md` § P4.
- **P5 Merge uncommitted** [once per batch]: ONE true merge of `<src-tip-SHA>`.
  `references/fp-phase-p5-p8.md` § P5.
- **P6 Symbol-survival** [MUST], **P6 TEST-survival**, **P7 Drift scan** [MUST; merged tests must
  collect cleanly]: dispatched read-only delegates. `references/fp-phase-p5-p8.md` § P6, § P7;
  `references/fp-phase-briefs.md` § P6 TEST-survival.
- **P8 Adapt** [serial per module, inside the open merge window]: one `odoo-coding` per module for the
  run (`WORKER_AGENT_ID` after the first launch); a frontend leg grounds against
  `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`. `references/fp-phase-p5-p8.md` § P8 (8a-8c);
  `references/fp-phase-briefs.md` § P8 - the coder registry and the resumed coder (R2b).
- **P9 Verify** [per batch]: `odoo-instance` provisioned once, `INSTANCE_HANDLE` reused; **P9.5** i18n;
  **P9.6** migration dir (C2): `references/fp-phase-p9-p12.md` § P9, § P9.6;
  `references/fp-phase-briefs.md` § P9.5. Never release the verify lease between batches; after the last batch's P10, before P11, call `lease_release` with the `lease_token` and
  `run_id` cached at P9 (`lease_park` only if a named later step needs the database).
- **P10 Conclude** the merge: ONE commit, full file list. `references/fp-phase-p9-p12.md` § P10.
- **P11 Acceptance** [MANDATORY]: `odoo-acceptance` once per batch. `references/fp-phase-briefs.md` § P11.
- **P12 PR + review**: never squash; wait for the human. Code review is MANDATORY when the batch grafts a
  new engine or mechanism; attribute findings by the FP diff before rating. `references/fp-phase-p9-p12.md` § P12. Then
  document the ported features per `${CLAUDE_PLUGIN_ROOT}/snippets/docs-after-change.md`
  (`HAND_ON: odoo-doc-illustration` at P9.5 unless `Docs: none`).

## Model triage

First match wins, EXTRACT and ADAPT tables independent (`references/fp-triage-table.md`);
record every tier in `plan.md`. An `installable:False` module skips tiers (lint-only lane). Checkpoint: `<ISOLATE_DIR>/forward-port/<slug>/checkpoint.json`; a crash in P6-P9 resumes in
place, never re-run P5 (`references/fp-phase-briefs.md` § Checkpoint, resume).

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
- `set_active_version` ☆ - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items. **Caller:** orchestrator-inline ONLY where a phase explicitly assigns it (P2 classification, and the 8a/8b adapt-brief grounding); at P6 / P6-TEST / P7 the same call belongs to the dispatched read-only delegate, so never issue it in the orchestrating context there (`snippets/fp-symbol-survival-check.md` - Who runs this check).
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call. **Caller:** orchestrator-inline ONLY where a phase explicitly assigns it (P2 classification, and the 8a/8b adapt-brief grounding); at P6 / P6-TEST / P7 the same call belongs to the dispatched read-only delegate, so never issue it in the orchestrating context there (`snippets/fp-symbol-survival-check.md` - Who runs this check).
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call. **Caller:** orchestrator-inline ONLY where a phase explicitly assigns it (P2 classification, and the 8a/8b adapt-brief grounding); at P6 / P6-TEST / P7 the same call belongs to the dispatched read-only delegate, so never issue it in the orchestrating context there (`snippets/fp-symbol-survival-check.md` - Who runs this check).
- `entity_lookup` ★ - Single-entity drill-down by kind discriminator: model, field, method, view, module, pattern, or report - with full inheritance chain and source module. **Caller:** orchestrator-inline ONLY where a phase explicitly assigns it (P2 classification, and the 8a/8b adapt-brief grounding); at P6 / P6-TEST / P7 the same call belongs to the dispatched read-only delegate, so never issue it in the orchestrating context there (`snippets/fp-symbol-survival-check.md` - Who runs this check).
- `find_override_point` - Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior.
- `find_test_examples` - Semantic search for Odoo test code examples (test_method, test_class, js_test chunks only - never returns production code). **Caller:** orchestrator-inline ONLY where a phase explicitly assigns it (P2 classification, and the 8a/8b adapt-brief grounding); at P6 / P6-TEST / P7 the same call belongs to the dispatched read-only delegate, so never issue it in the orchestrating context there (`snippets/fp-symbol-survival-check.md` - Who runs this check).
- `test_base_classes` - Menu of official Odoo test framework base classes (TransactionCase, HttpCase, SavepointCase, Form, etc.) for the given version, with test_type and cursor contract. **Caller:** orchestrator-inline ONLY where a phase explicitly assigns it (P2 classification, and the 8a/8b adapt-brief grounding); at P6 / P6-TEST / P7 the same call belongs to the dispatched read-only delegate, so never issue it in the orchestrating context there (`snippets/fp-symbol-survival-check.md` - Who runs this check).
- `test_coverage_audit` - Audit an entire module for test coverage gaps: lists fields/methods with zero COVERS_* edges (never referenced by any test). **Caller:** delegate only - the P6-TEST test-survival sweep runs inside the dispatched read-only `Explore` delegate; the orchestrating context records its verdict and never issues this call (`snippets/fp-symbol-survival-check.md` - Who runs this check).
- `tests_covering` - List test methods that have COVERS_MODEL/COVERS_FIELD/COVERS_METHOD edges to the target model or field (static reference coverage, not runtime executed coverage). **Caller:** delegate only - the P6-TEST test-survival sweep runs inside the dispatched read-only `Explore` delegate; the orchestrating context records its verdict and never issues this call (`snippets/fp-symbol-survival-check.md` - Who runs this check).
- `cli_help` - Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags.
- `impact_analysis` - Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields.
<!-- END GENERATED TOOLS -->

## Standalone-first fallback

OSM unreachable: read local source (`${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md`),
label `grounded: local-source - not OSM-indexed`. P2 classify and P6 symbol-survival fall back to disk
reads of the target checkout per `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md` (read each
`<tgt-descriptor>` `depends` and the model/field source). `odoo-version-diff` standalone mode supplies
the version delta from release notes when the index is down. Never ask a human to paste code, field
lists or manifests.

## Continuation Contract

Append the block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`. `produced`: `plan.md`,
each `<module>/intents/<sha>.md`, `merge-log.md`, `<ISOLATE_DIR>/qa/<slug>-acceptance-report.md`,
`checkpoint.json`, the PR URL. `next`: the gate the run stopped at (P4 plan, or P12 PR merge with the
P11 verdict); for P3, `next: odoo-solution-design` with the `inputs` of
`references/fp-phase-p0-p4.md` § P3, and YIELD.
