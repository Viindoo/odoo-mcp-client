---
name: odoo-modules-upgrade
argument-hint: "[module-cluster] [target-series]"
description: >-
  Upgrade custom module code to a higher Odoo major: installable, working, modernised; no database migration
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

**P0 - Intake / resolve [STOP if open_questions non-empty].**
Dispatch 1x intake subagent (haiku). Brief: (1) read the CURRENT BRANCH NAME and infer the Odoo series (`<series>-*` -> `<series>`);
cross-check against the MAX manifest `version` series on disk and raise a disagreement as an
`open_question` rather than trusting the branch name alone. EXCEPTION (the manifests carry a SHORT version with NO series prefix - keyed on the VALUE's form):
skip the cross-check and resolve the source series from branch + profile; (2) map to the OSM profile via `set_active_version` +
`list_available_profiles` + `profile_inspect`; report repos + module set; (3) auto-detect
CANDIDATE MODULES by scanning each module descriptor (`__manifest__.py`, or the legacy
`__openerp__.py` on the oldest series - glob BOTH names) for a `version` major series LESS
THAN target AND for modules depending on such a stale module;
`installable: False` is a weak hint only. Short-form manifests (no series prefix) yield nothing from
that version scan on ANY profile - then detect by profile membership + branch series instead; (4) determine
SOURCE version from the matched profile / manifest `version` and TARGET from the NL ask (or next
major if implied); (5) if MODULE SCOPE is not explicit, do NOT guess - return the candidate list +
a proposed cluster (seeded from the dependency closure of the confirmed targets, not naming/path
proximity) as `open_questions`. Emit dependency hints from manifest `depends`.
Output: `intake.md` - {resolved_series, matched_profile, source_version, target_version,
candidate_modules[], proposed_cluster[], dependency_hints, open_questions[]}.
**Gate:** if `open_questions` non-empty, present the candidate list + proposed cluster, ask the
user to confirm/narrow scope, then resume P1.

**P1 - Recon [graph + deprecation + diff + transitive-symbol, parallel].**
Four parallel dispatches:
(a) 1x `Explore` (haiku) reads each descriptor's `depends` (BOTH names, § P0) -> emits {module, depends[]}
for every module in the confirmed cluster -> topo-sort to leaves-first order; (b) `odoo-deprecation-audit` (via Skill tool, haiku) for source +
TARGET version + module list (it runs the TARGET-version survival pass); (c) `odoo-version-diff`
(via Skill tool, sonnet) for source->target delta; (d) **P1d Transitive Symbol Survey**
(`Explore`, haiku, read-only) - scans cluster source for every symbol referencing an external/core
dep and grounds each at target, emitting `blockers[]` that gate P3/P4 (full brief: phase-detail § P1d).
Output: `graph.md` (DAG + topo order), `deprecation.md`, `version-delta.md`, `transitive-symbol-survey.md`.
Assert DAG is acyclic: if a cycle is found, surface the cycle edges as a `concerns:`
entry and ask the user to break the cycle before P2 proceeds (do not hard-fail).
Assert all dependencies exist at the target.

**P2 - Core-absorption comparison [per module, dep order, parallel within dependency levels].**
Rule (code upgrade, no old-series compatibility, no version bump) and the P4-time
dispositions: `${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md` § Convention 0.

For each module in dep order, decide DELETE-absorbed / KEEP / REWRITE(api) /
REWRITE(model) / MERGE / SPLIT by comparing custom behavior vs target-version core.

Per module in dep order (topo order from graph.md): dispatch 1x `odoo-diff-comparator`
(sonnet) + invoke `odoo-gap-analysis` (via Skill tool, sonnet) in
parallel. Modules at the SAME DAG depth (same dependency level) may be dispatched in parallel; a module
is NOT dispatched until its in-cluster dependencies have finished P2. Dispatch concurrency
follows `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` Mode B.
Comparator brief: "compare the module's business intent, expected outcomes and
acceptance criteria against target-version CORE (`<target>`). Classify each feature per
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-classification-table.md`" -
the comparator owns the whole-module DELETE-absorbed derivation.
Output per module: `absorption/<module>.md` - {per-feature classification, evidence
(OSM citation), proposed action, deferred_work items (below)}.

**P2 also reconciles version-anchored deferred work [same per-module read].** The same
`odoo-diff-comparator` dispatch additionally scans every in-scope file
(`.py` incl. `__manifest__.py`, tests, `.xml`, `.js`, `.csv`, `.po`, README/docs) for a
case-insensitive marker set - `TODO`/`todo`/`Todo`/`ToDo`/`@todo`, `FIXME`, `XXX`, `HACK` - and
classifies each hit against the target series X (`<target_version>`): anchored to X or to an
already-passed LOWER version -> **DUE** (execute NOW, in THIS upgrade); anchored to a HIGHER
future version -> **DEFERRED** (leave it untouched); no parseable version anchor ->
**UNANCHORED** - record it and flag it for the human, never silently absorbed into DUE nor
silently dropped. The comparator returns this as a compact `deferred_work` block inside
`absorption/<module>.md` (never raw grep output); never grep module source yourself for this. For a module that survives (KEEP/REWRITE/
MERGE/SPLIT), every DUE item becomes REAL upgrade work: P4 folds it into that module's SAME
implement -> P4b review -> P5 test path (§ P4).

**P2b - Hard-call design [mandatory route-out for specific verdicts].**
Route to `odoo-solution-design` (`odoo-solution-architect` opus) when the comparator's return
block `verdict:` field equals ANY
of the following - match directly on `verdict:`, never infer from the `proposed_classification`
count aggregate:
- `MERGE` (any merge, regardless of apparent clarity)
- `SPLIT` (any split)
- `RECONCILE` (always - data-divergence or new-feature wire-in; the SSOT/wire-in choice is architectural)
- `MIXED` (always - route the whole module to design to resolve the mixed per-feature verdicts)
- `REWRITE(model)` where at least one field type changes
- `DELETE-absorbed (with risk)` (any absorption verdict carrying risk flags)
- `REWRITE(api)` when the adaptation changes the module's PUBLIC MODEL SURFACE (adds/removes/
  retypes a stored field or changes a public method signature on an extended core model), OR
  touches > 5 call sites of the changed API, OR spans >= 2 modules.
- `KEEP (with adaptation)` when the adaptation meets the `odoo-solution-design` § When to invoke
  non-trivial criterion (overrides `create`/`write`/`unlink`, a method with >=3 override-chain
  entries, a cross-model computed chain, or a multi-company/branch change).

A trivial REWRITE(api)/KEEP - a localized deprecation-fix or
call-site swap confined to <= 5 call sites in 1 module with no public-surface change - SKIPS
design and goes straight to P3. DELETE-absorbed (no risk) and OBSOLETE never route (the module
is removed, not adapted). Use the non-trivial criterion `odoo-solution-design` applies. Full table: `references/upg-phase-detail.md` § P2b.
Emit the Continuation Contract and YIELD. On re-entry, read `design_doc` from the returned
contract's `inputs`, record it, and proceed to P3.

**P3 - Plan gate [Plan Mode].**
The human approves the per-module DELETE/KEEP/REWRITE/MERGE/SPLIT table + install
order BEFORE any code is written or module deleted. This is the request's one Plan-Mode gate
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request): call
`EnterPlanMode`, then present the plan CONTENT (authored here, not routed through
`odoo-planning`): per-module
classification table (DELETE -> list the core feature that replaces each AND inline the
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

**P4 - Adapt [per module, dep order, child worktrees].**
Create the JOB-tier integration worktree: invoke the `git-toolkit:git-ops` skill (via the Skill
tool) to add a worktree (branch `upg/<src>-<tgt>-<cluster>`, worktree `<path>/upg-integration`, base `<work-base>`).
Per module in dep order: invoke the `odoo-coding` skill (via the Skill tool) at the ADAPT tier
(per `${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-triage-table.md`)
in a child worktree off integration - NOT optional when
the modules touch disjoint files (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-phase-detail.md`
§ Child worktree per module). Never dispatch raw `odoo-coder` or `odoo-frontend-coder`.
For DELETE-absorbed and OBSOLETE modules: invoke `odoo-coding` to run the dangling-reference
sweep first (grep repo for model names, XML IDs, group xmlids, env.ref targets), then
invoke the `git-toolkit:git-ops` skill (via the Skill tool) for the directory removal, staging, and commit in the child worktree
(op: rm -r module dir + stage deletion + commit -s; confirmed: yes - user confirmed DELETE
at P3 Plan Mode gate; commit message per § Git / PR conventions absorbed/obsolete-delete form);
drop it from every depender's `depends` in their manifests.
For KEEP/REWRITE/MERGE/SPLIT: prepend this module's `blockers[]` from P1d
`transitive-symbol-survey.md` as a PREEMPTIVE FIX LIST, ATTACH the breaking-change catalog's PATH
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-classification-table.md`) to the
`odoo-coding` brief and never pre-select or pre-apply rows -
the per-module deprecation fix list from P1, and this module's DUE version-anchored
deferred-work items from P2's `absorption/<module>.md` `deferred_work` block (executed NOW as
REAL work in the SAME implement -> P4b review -> P5 test path, not a side note; DEFERRED
and UNANCHORED items stay untouched in source); flip `installable: False -> True`; delete the
module's `migrations/` directory (Convention 0); do NOT bump the
manifest `version` (keep the short form; a series-prefixed value is CONVERTED to it, never bumped -
`references/upg-classification-table.md` § Manifest breaks, the Rule A row); set
`auto_install`/`application` only when a manifest-comment breadcrumb directs (NO auto-detect of
"bridge"). The same brief carries the adapt fields - `MODE: adapt`, `INTENT` (the behavior the
module keeps, from `absorption/<module>.md`), `SOURCE TESTS` (its existing tests),
`BROKEN TEST-SYMBOLS` and the run's `RUN_ID` - so the node's test leg adapts the module's own tests
after the code (template: `references/upg-phase-detail.md` § odoo-coding dispatch brief).
`odoo-coding` produces the commit inside each child worktree via `git-toolkit:git-ops`; message per § Git / PR conventions.
Converge each child worktree back to integration (serialized); remove child worktree.
Principal-checkout-lock: Hard rule 1.

**P4b - Code-review loop [odoo-code-review -> odoo-code-reviewer; fix via odoo-coding; cap 3].**
After P4 adapts the cluster into the integration worktree, dispatch `odoo-code-review` (via the
Skill tool) per adapted module IN DEP ORDER (leaves first), scoped to that module's adapt diff
(`TARGET: worktree:<path>/upg-integration`, module-scoped; DELETE-absorbed/OBSOLETE modules have no
adapt diff - skip them). On any CRITICAL/HIGH finding for a module, dispatch `odoo-coding` (same
ADAPT tier) to fix to root cause, then RE-REVIEW that module; MED/LOW are recorded for the P7
pre-PR review, not blocking. Cap at 3 review->fix iterations per module: a 3rd iteration still CRITICAL/HIGH
STOPS and escalates BLOCKED. Proceed to P5 ONLY when every adapted module's review
returns no CRITICAL/HIGH. Dispatch reviewer + fixer, never review or fix inline. Write
`<module>: reviewed` in checkpoint.json. Brief + loop protocol: `references/upg-phase-detail.md` P4b.
The final dep-order review stays at P7; both clear before the PR opens.

**P4b acceptance hand-off (consumption clause).** Each dispatched `odoo-code-review`'s
Continuation Contract MAY carry a `next: odoo-acceptance` entry - its Phase A.5 emits this
whenever a module's `render_check_set` reaches beyond that module (dependents bind a changed
symbol). Do NOT act on it per module here; ONE cluster-wide dispatch at P5.8 below covers it.

**P5 - Install + test gate [ephemeral instance, one dependency level at a time].**
Prove the whole cluster installs + tests green on a fresh target DB, bottom-up, one dependency
level at a time (leaves first). The framework-validation classes run here, whichever of them the
target series ships (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Framework-validation
test classes). This is an AUTOMATION-TEST build - take its demo shape from
the automation-test row of `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Demo data by
build PURPOSE and never override it for this gate. The P4b review MUST cover ACL / `.sudo()` for every create/
write/compute override on a widely-used core model. Cross-ref
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/runbot-parity-checklist.md`.
Dispatch `odoo-instance` (via Skill tool). Create the instance
once; then for each dependency level: dispatch init for that level's modules, then run-tests for
that level with `GATE_ROLE: node-verify` (a per-level verification, never the pre-PR lint gate). Record per-level green in `checkpoint.json` (status `installed`) and `install-test.md`.
On failure in a level, dispatch `odoo-backend-debugger` or `odoo-ui-debugger` to diagnose
to root cause (pass `ISOLATE_DIR:` - the SAME literal resolved at P0 intake - and `SLUG: <cluster>-level<n>`;
`odoo-ui-debugger` places evidence under `<ISOLATE_DIR>/visual/debug/<cluster>-level<n>/`);
feed the diagnosis back to P4 for the affected module. Resume P5 from the
failing level (skip already-green levels per `checkpoint.json`). Loop until all levels green.
Output: `install-test.md` - {per-level + per-module install ok?, test result, root-cause if red}.

**P5 instance release [MANDATORY].** Once every level is green (and its installable-flip gates are
recorded), you are the run-level owner of the P5 test instance (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1): call
`mcp__plugin_odoo-ai-agents_odoo-local__lease_release` with the cached `lease_token` and `run_id`
before P5.7. Call `lease_park` instead only when a named later step of this run still needs the
database. Never release it between levels - every level reuses it.

**P5.7 - i18n reconcile [MANDATORY, narrow escape only].**
MANDATORY for every SURVIVING module (KEEP / REWRITE / MERGE / SPLIT / RECONCILE); a content diff
is NOT the gate. Skip only via an enumerated escape, recorded in `install-test.md`:
`${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`. When it runs, run the `odoo-i18n` skill against a fresh instance with the existing `.po` loaded:
re-export -> git-ops diff-review each `.po` against its committed version + adjudicate every loss
(NEVER blind-regenerate - a fresh-DB export with no load step destroys existing msgstr) ->
translate every entry left with an empty `msgstr` (one whose correct translation equals its `msgid`
stays empty - `${CLAUDE_PLUGIN_ROOT}/snippets/po-entry-semantics.md`) -> reload with `-u`. Detail: phase-detail § P5.7.

**P5.8 - Acceptance (odoo-acceptance) stage [MANDATORY, cluster-wide, narrow escape only].**
Compute the cluster-wide verify scope by invoking `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md`
(do NOT re-derive the reverse-closure): `changed_set` = every surviving (KEEP/REWRITE/
MERGE/SPLIT) module in `plan.md`; the dependent-module reverse-closure comes for free from P1's
`graph.md` DAG.
Invoke the `odoo-acceptance` skill (via the Skill tool) ONCE for the whole cluster (never per
module). Fill the dispatch brief per `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton (read it by
path): `INPUTS` = the `changed_set` above, `scope_hint` = `graph.md` + `absorption/*.md`,
`odoo_version` = target series; `INSTANCE_HANDLE: none provisioned` - NEVER the P5 test handle. `ACCEPTANCE` (by pointer) = each
surviving module's business behavior recorded in `absorption/<module>.md` and any P2b design doc's
§9 - NEVER a pre-built oracle. Do NOT hand it the implementation.
**MANDATORY - narrow escape only.** Skip it ONLY when `graph.md` proves the cluster is a true
dependency leaf with ZERO in-repo dependents AND no behavioral surface (no views, no models any
other module consumes) - record that proof explicitly in `install-test.md`; never skip silently.
**The upgrade is not DONE until this stage returns ACCEPTED (PASS), or the narrow-escape condition
above is explicitly met and recorded.**
Present the acceptance verdict (or the recorded narrow-escape) ALONGSIDE the P6 sign-off below.
Output: `<ISOLATE_DIR>/qa/<slug>-acceptance-report.md` (`odoo-acceptance`'s own artifact), referenced
from `install-test.md`.

**P6 - Gate [STOP, human sign-off].**
Present `plan.md` + `absorption/*` summaries + `install-test.md` (including the list of
DELETED-absorbed modules + their reasons) + the P5.8 acceptance verdict (or its recorded
narrow-escape) and ask, as a text question, `approve / skip / cancel`. Wait for
`approve` before the PR; `skip` ends the run with the branch unpushed.

**P7 - Final review + PR [human merge].**
Order (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Default tail): every code-changing check
clears, THEN the PR opens.
Pre-PR checklist: run the Runbot parity gates
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/runbot-parity-checklist.md`), then
add a convention-compliance pass (manifest version-form - short, no series prefix, not bumped, per
`references/upg-classification-table.md` § Manifest breaks - plus always-invisible XML comment;
no upgraded module still carries a `migrations/` directory; see
`${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md`), the migration notes (below), a perf-lens
pass (no per-record `mapped()` aggregate on a high-volume model - use grouped `_read_group`), and
an i18n pass (P5.7 ran for every surviving module, or each skip is a RECORDED enumerated escape).
Write `<run dir>/migration-notes.md` (`<run dir>` = `<ISOLATE_DIR>/modules-upgrade/<src>-<tgt>-<cluster>/`)
without asking and without blocking: dispatch one haiku subagent to compile it from
`transitive-symbol-survey.md` `blockers[]`, `absorption/*.md`, `version-delta.md` and the
`migrations/` paths the P4 commits deleted - renamed or
removed models, fields, xmlids and selection values; changed field types; modules deleted as absorbed;
changed `noupdate` data; every deleted `migrations/` directory (module, path). Point at it from a
"Migration notes" section of the PR body.
Then delegate the final dep-order code review of the integration worktree - via the plugin's review
capability, passing `worktree:<path>/upg-integration` and asking it to review modules in dependency
order - and fix its CRITICAL/HIGH findings on that worktree, BEFORE the PR opens.
ONLY once that review is clean, push branch and open PR: invoke the `git-toolkit:git-ops` skill (via
the Skill tool) to push the branch, then to create the PR - resolve upstream org/repo and base from
`git remote get-url origin`.
After the PR exists, only PR-OBSERVING work (CI-failure triage, the human merge) and the closing docs below remain. Wait for human merge.

With the PR presented, document the upgraded user-visible features for the target the P3 plan approved (`none`: skip this step). Compose a change file `<ISOLATE_DIR>/docs/change-<slug>.md`: one line per upgraded user-visible feature, with its module and UI label. Module docs: invoke `odoo-doc-illustration` on the target branch's worktree with `CHANGE` = that file and commit the result onto the SAME open PR's branch through `git-toolkit:git-ops` - one PR per repo per run. Site docs: invoke `odoo-doc-site` with `CODE_WORKTREE` = the target worktree, `SERIES` = the target series, `FROM CHANGE` = that file. Both run under the approved plan, with no gate.

## Hard rules

1. **Principal-checkout-lock.** NEVER check out or switch the principal (main)
   checkout off its branch. Materialize any needed branch through `git-toolkit:git-ops` (add a worktree).
2. **Plan Mode before any delete or code write.** No directory removal, no code changes, no
   worktree branch until P4 post-gate (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md`).
3. **No cluster-squash; per-module consolidation allowed** (`references/upg-phase-detail.md`
   § Commit consolidation, via `git-toolkit:git-ops`). Commit message formats: § Git / PR conventions.
4. **ONE PR per cluster.** All modules in one PR, reviewed in dep order.
5. **Code upgrade only (Convention 0).** This skill NEVER writes a migration script, never touches
   an existing database and never stops to ask about existing data. It deletes the `migrations/`
   directory of every upgraded module and records each deleted directory in `migration-notes.md`
   (§ P7), together with what the upgrade changes for existing data; it never blocks the run.
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

The pipeline writes a progress ledger at `<ISOLATE_DIR>/modules-upgrade/<src>-<tgt>-<cluster>/checkpoint.json`
after each module completes a phase. Schema:

```json
{
  "<module_name>": "pending | absorbed | designed | adapted | reviewed | installed | done"
}
```

Status progression:
- `pending` - initial state for all modules at P0.
- `absorbed` - P2 comparison complete, verdict recorded in `absorption/<module>.md`.
- `designed` - P2b design doc received (only for modules routed to design).
- `adapted` - P4 code changes committed and merged to integration worktree.
- `reviewed` - P4b code-review loop returned no CRITICAL/HIGH for the module.
- `installed` - module's dependency level passed P5 install + test green.
- `done` - module fully processed (installed green + verified).

Resume behavior (per-phase skip rules):
- P2 skips modules with status in {absorbed, designed, adapted, reviewed, installed, done}.
- P4 skips modules with status in {adapted, reviewed, installed, done}.
- P4b skips modules with status in {reviewed, installed, done}.
- P5 skips modules at the dependency-level granularity with status in {installed, done}.
On restart, read `checkpoint.json` and resume from the first module that has not yet reached the
target phase's skip-threshold. P5 records green per level in the ledger.

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
  remote (resolve the fork remote from `git remote get-url origin` or a dedicated fork remote).
- PR: invoke `git-toolkit:git-ops` to create the PR (resolve upstream org/repo and base from
  `git remote get-url origin`).

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
