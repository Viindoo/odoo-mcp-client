---
name: odoo-git-rebase
argument-hint: "[branch] [onto base]"
description: >-
  Rebases a branch onto an updated base of the same Odoo series
model: sonnet
---

## Role

Rebase conductor: own the git topology and subagent lifecycle; delegate EVERY diff read, intent extraction, behavior comparison, conflict resolution and verify. A rebase is a SEMANTIC translation onto an updated SAME-version base, not a text-replay: a clean replay does NOT prove the feature survived. Run no git: repo facts come from `repo_facts`, every other git result is a request to `git-toolkit:git-ops` (`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`).

**Principal-checkout-lock.** NEVER check out, switch or reset the principal checkout off its branch; get any needed branch as a git-ops worktree (`rb-phase-detail.md` § Principal-checkout-lock).

## Out of Scope

| Situation | Route to |
|---|---|
| Port ACROSS Odoo majors (SAME series = rebase) | `odoo-forward-port` |
| Upgrade a module/cluster across majors | `odoo-modules-upgrade` |
| One isolated change, no source branch | `odoo-coding` |
| A version-to-version API delta only | `odoo-version-diff` |
| Review a PR/diff without rebasing | `odoo-code-review` |
| STANDALONE design (INSIDE a rebase the P5 route-out applies) | `odoo-solution-design` |
| Parallelize N changes + squash (a rebase never squashes) | `odoo-planning` |

> A same-series rebase routes HERE, not to bare git-ops: drive this pipeline, invoking `git-ops` (Skill tool) per git step.

## Artifact layout

`<slug> = <feature-ref>-onto-<new-base>`, sanitized: lowercase; each space, slash or character outside `[a-z0-9._-]` becomes `-`; repeated `-` collapse; truncate to 64 chars. Compute `<slug>` ONCE and pass the ABSOLUTE path `<ISOLATE_DIR>/git-rebase/<slug>/...` (resolved once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`) into every brief; subagents never recompute or re-resolve (`state-root-resolution.md` § Cross-worktree dispatch). `<old-base>` is the merge base of `<new-base>` and `<feature-ref>`: git-ops reports it at P1, `recon.md` records `old_base:`, later phases read it there.

## Reference map

Every `§` below names a section under `${CLAUDE_PLUGIN_ROOT}/skills/odoo-git-rebase/references/`: `rb-phase-detail.md` (checkpoint writers and shape, Principal-checkout-lock, P0-P7 briefs and formats), `rb-phase-detail-p8-p12.md` (P8-P12, fast-path fallback, `rebase-log.md` / `intake.md` formats), `rb-triage-table.md` (model tiers, design triggers, bucket-(c) gate). `[[fp-symbol-survival-check]]` is `${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md` (Sections 1-2.5; at P8b grounded at the shared-series base HEAD - say so in the brief).

## Checkpoint / resume

Contract: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md` (pre-loop SHA, per-commit checkpoint, clean-abort or resume). `<ISOLATE_DIR>/git-rebase/<slug>/checkpoint.json` holds `phase`, per-commit `<sha>: extracted-pending-consolidation|extracted|designed|resolved|reviewed|done`, `rebase_in_progress`, `integration_worktree`.

**P0 reads it first.** A live rebase in `<integration_worktree>` (`repo_facts` `operation_in_progress` = `rebase`) -> RESUME P8 at the stopped commit, never restart or abort; skip `resolved` / `done`; resume `designed` at P6 ingestion. Clean checkpoint (`rebase_in_progress: false`) -> skip `done` phases, resume at the last incomplete one. `extracted-pending-consolidation` re-runs ONLY its P2 consolidation copy and P3 refuses it until promoted. A dangling integration worktree is resumed, not recreated. JSON shape and writers: `rb-phase-detail.md` § Checkpoint writers and shape.

## The pipeline

Fill every dispatch from `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton plus the agent's family delta; never inline it. ALL analysis (P1-P4) precedes the Plan Mode gate (P6), which precedes ANY branch or worktree creation (P7). P2 fan-out: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` (Mode B, budget 8).

**Sequence invariant.** `recon/classify -> (conditional) solution-design -> Plan Mode gate -> odoo-coding execution`; the gate is the request's one Plan-Mode approval (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request). A triggered design doc exists BEFORE it; NO `odoo-coding` / `odoo-coder` / `odoo-frontend-coder` dispatch before it (a change that skips design STILL passes it).

**Small-scale fast-path.** Up to 5 commits, no patch-equivalent commit, no renamed or moved symbol in one cheap OSM batch: P2+P3 collapse into ONE sonnet `odoo-diff-comparator` pass; P8b still runs. A P8 conflict on the fast-path provisions the stopped commit's dump and one `odoo-intent-extractor` before `odoo-coding` (`rb-phase-detail-p8-p12.md` § P8).

**Orphan sweep (every run, BEFORE P0):** `find <ISOLATE_DIR>/git-rebase/ -mindepth 1 -maxdepth 1 -type d -mmin +43200 -exec rm -rf {} +` (`snippets/visual-evidence-lifecycle-contract.md` Clause 3).

**P0 - Intake / resolve [haiku subagent; clarify gate if `open_questions` non-empty].** `/odoo-git-rebase <free text>` passes the whole prompt through: NO required parameters, NO inferring inline; dispatch this subagent first with the full text. It parses the NL request into feature ref (branch or PR) and new-base, verifies one Odoo major series, emits `open_questions[]` and `branches_to_materialize[]`. Ask only those questions, in one message, then re-dispatch; PR lookup and worktrees go to git-ops. Emit `intake.md`. § P0.

**P1 - Recon [git-ops, no gate].** Enumerate the commits after `<old-base>`; the patch-equivalence pre-filter is a hint (never skip a commit on it alone); emit {sha, modules[], subject, EXTRACT tier}; more than one merge base is an open_question before P7; merge commits in the range need preservation or user confirmation. Write `recon.md` (`old_base:`). § P1.

**P2 - Intent extract [git-ops dump pre-step + one `odoo-intent-extractor` (rebase MODE) per non-(a) commit, parallel].** Each extractor grounds at `<new-base>` HEAD (never a cross-version API diff), gets `commit_dump_path` and `SLUG: <slug>`, runs at the EXTRACT tier (`rb-triage-table.md` Table 1) and writes `intents/<sha>.md`. Above ~30 commits the unit is the MODULE (`SLUG: <slug>/<module>`) plus a checkpointed consolidation. § P2.

**P3 - Cluster comparison [`odoo-diff-comparator` sonnet; completeness gate first].** Every non-(a) commit needs a non-empty canonical `intents/<sha>.md` (a miss is `BLOCKED` until the P2 consolidation re-runs). One comparator decides per commit the outcome a/b/c/d and absorption failure mode of `[[rb-intent-4outcome]]` (`${CLAUDE_PLUGIN_ROOT}/snippets/rb-intent-4outcome.md`) into `comparison.md` with the duplicate-behavior risk list. § P3.

**P4 - Classify [orchestrator, no gate].** From P2+P3 structured output ONLY, assign exactly one outcome a/b/c/d per commit; flag upgrade-scale bucket-(c) commits (thresholds in `rb-triage-table.md` § Bucket-(c) upgrade-scale defer-or-do gate) for that gate; record in `rebase-log.md`.

**P5 - Design (conditional) [`odoo-solution-design`, opus].** Routes per `rb-triage-table.md` § Design-trigger table (bucket-(c) "do now" always; the rest skip unless a trigger row matches). Emit the Continuation Contract (`next: odoo-solution-design`, `inputs: { return_to: odoo-git-rebase, design_slug_hint, target_version, modules, intent_records, classification }`) and YIELD; on re-entry record `design_doc`, set `status=designed`, go to P6. `rb-triage-table.md` § Design-trigger table; § P5.

**P6 - Plan gate [Plan Mode; `EnterPlanMode` MUST precede any branch or worktree].** The request's one Plan-Mode gate: `EnterPlanMode`, present the plan, `ExitPlanMode` on approve. Authored here, not by `odoo-planning`: commit topology; per-commit outcome + EXTRACT/ADAPT tier; design-doc links; the rebase invocation; conflict policy; B3 instance-verify decision. Write `plan.md` AFTER approval. § P6.

**P7 - Integration worktree + rebase [git-ops].** After approval: worktree AT THE FEATURE TIP (branch `rb/<slug>`, NOT new-base), conflict-resolution reuse on, replay the commits after `<old-base>` onto `<new-base>`. Returns `DONE` (-> P8b) or `BLOCKED-CONFLICT` + `conflicted_files`, `stopped_commit` (-> P8). § P7.

**P8 - Conflict loop [per stopped commit].** Outcome (a)/(d): git-ops skips the commit. Outcome (b)/(c): `Explore` reads the conflicted files and `intents/<sha>.md`; then `odoo-coding` (Skill tool, ADAPT tier, `COMMIT: caller`, `TEST LEG: deferred - P9`, `RUN_ID`) resolves the hunks to the INTENT on the new-base idiom; never a raw coder or an auto-merged line referencing a renamed symbol. Continue via the stateless-resume recipe of `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`; three consecutive `BLOCKED` returns abort, restore the checkpoint, escalate. Record touched modules for P9. § P8 (frontend leg: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`).

**P8b - Symbol-survival + collection gate [MUST, delegated].** Ground every touched symbol against the base HEAD per `[[fp-symbol-survival-check]]` (absent, renamed or retyped = BLOCKER, resolved into its bucket before P9), run the import-resolvability gate over feature-touched `.py`, and the collection ACCEPTANCE GATE (`0 failed, N error(s)` is NOT a pass); who runs it: `[[fp-symbol-survival-check]]` § Who runs this check. § P8b.

**P9 - Adapt + test forward [`odoo-coding`, MODE: adapt, per touched module, no gate].** For modules whose behavior changed (P8b findings, `recon.md` modules[]) AND every module a P8 resolution touched: adapt code first, then the branch's own tests, each proven by a break (`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`). Bucket (a) is never forwarded; P8b is a precondition. § P9.

**P9b - Code-review loop [`odoo-code-review`; fixes via `odoo-coding`; cap 3].** Review `TARGET: worktree:<WT_ROOT>/rb-integration`, findings only on replayed lines. CRITICAL/HIGH: fix to root cause (same ADAPT tier), RE-REVIEW; MED/LOW go to the P12 review. A 3rd iteration still CRITICAL/HIGH: BLOCKED. P10 only on none; never review or fix inline; write `<sha>: reviewed`. § P9b.

**P10 - Verify [git-ops range comparison + `odoo-diff-comparator` sonnet + conditional `odoo-instance`].** `range-diff.txt` of original vs rebased; the comparator confirms every P4 intent is present and unchanged; the dup-guard is OSM `entity_lookup`'s definition count across the inheritance chain (more than one fails), grep only locates; output `verify.md`. Instance verify (Skill tool) only when the range touches DB-stateful behaviour (the B3 list, `rb-phase-detail-p8-p12.md` § P10), reusing P8b's `INSTANCE_HANDLE` (`mode: reuse`), fresh after a break touched data or schema; lifecycle: `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md`. § P10.

**P11 - Gate [STOP, human-confirm].** Show `rebase-log.md` + `verify.md`; ask `approve / skip / cancel`; no push or PR before `approve`; `skip` ends the run unpushed.

**P12 - Final review + PR [human merge].** Order of `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Default tail: final review of `worktree:<WT_ROOT>/rb-integration` with CRITICAL/HIGH fixed, THEN git-ops pushes `rb/<slug>` to the fork remote and opens the PR against new-base on the upstream (both from `repo_facts`, as brief fields). NEVER squash. § P12.

## Model triage

Two tiers, decided INDEPENDENTLY, conditions in `rb-triage-table.md`: **EXTRACT** (P2, Table 1: haiku or sonnet per the commit's intent complexity). **ADAPT** (P8, Table 2): `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection; a bucket (a)/(d) test-only forward is haiku.

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
- `set_active_version` ☆ - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `entity_lookup` ★ - Single-entity drill-down by kind discriminator: model, field, method, view, module, pattern, or report - with full inheritance chain and source module.
- `find_override_point` - Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior.
- `find_test_examples` - Semantic search for Odoo test code examples (test_method, test_class, js_test chunks only - never returns production code).
- `test_base_classes` - Menu of official Odoo test framework base classes (TransactionCase, HttpCase, SavepointCase, Form, etc.) for the given version, with test_type and cursor contract.
- `tests_covering` - List test methods that have COVERS_MODEL/COVERS_FIELD/COVERS_METHOD edges to the target model or field (static reference coverage, not runtime executed coverage).
- `cli_help` - Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags.
<!-- END GENERATED TOOLS -->

## Standalone fallback

Odoo Semantic unreachable: P2 extractors read local source (`${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md`), labelling each record `grounded: local-source - not OSM-indexed`; the P3 comparator reads the checkout per `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`. Range-diff, dup-guard and verify-by-behavior are unchanged.

## Continuation Contract

At a finish or a gate, append a Continuation Contract per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). `produced`: the run artifacts (`intake.md` ... `verify.md`) and the PR URL. `next`: the P11 gate or the P12 human merge; when P5 routes out, `next: odoo-solution-design` with the canonical payload and the run YIELDS (the plan runner re-enters with `design_doc`). Fold P9b findings into `rebase-log.md`.
