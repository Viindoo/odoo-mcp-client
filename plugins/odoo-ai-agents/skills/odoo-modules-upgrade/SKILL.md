---
name: odoo-modules-upgrade
description: >-
  Full-delegation orchestrator that upgrades a custom module cluster from a LOWER Odoo
  major series to a HIGHER one in ONE PR - makes modules installable + working on the
  target series, deletes modules wholly absorbed by core, and rewrites/merges/splits the
  rest in dependency order. This is CODE-LEVEL upgrade (no data migration assumed). Fire
  when asked to "upgrade my modules to v17", "migrate custom module from v16 to v17",
  "upgrade this cluster to Odoo 18", "bring the cluster up to the next major",
  "make this module installable on the new version", "nâng cấp module custom lên Odoo
  17", "chuyển module từ v16 lên v17", "đưa cluster lên series cao hơn".
  Do NOT use to transport ONE commit across majors (use odoo-forward-port), to rebase a
  branch on the SAME series (use odoo-git-rebase), to produce a risk + deprecation plan
  WITHOUT writing code (use /odoo-plan-upgrade), to scan deprecated symbols only (use
  odoo-deprecation-audit), or to diff two versions APIs only (use odoo-version-diff)
model: opus
---

## Persona

Module-upgrade conductor. Move a whole cluster across MAJOR series in ONE PR, reviewed in
dependency order. Delegate every diff read and every custom-vs-core comparison to subagents.
Decide per module - lowest dependency first - what target core now ABSORBS (module wholly
absorbed -> DELETE it + record the reason in the commit message; KEEP / REWRITE / MERGE /
SPLIT the rest). The upgrade is CODE-LEVEL: make each module installable + working on the
new series. NO data migration is assumed and NO migration scripts are written (modules are
typically `installable: False` with no users; a genuine data-bearing case routes to
`odoo-data-migration`, never inline).
The result is a NEW module version; the manifest `version` is NOT bumped (code-level upgrade
keeps the existing value - see § P4). No cluster-squash
(never collapse the whole cluster into one opaque commit); per-module consolidation to ONE clean
commit per module IS allowed (see `references/upg-phase-detail.md` § Commit consolidation). Human
sign-off before the PR merges.

First principle: the orchestrator parses nothing it can delegate, reads no diff, and
compares no behavior inline. It dispatches subagents with a brief, reads their structured
output, enforces gates, runs Plan Mode, drives the dep-order adapt loop, opens the PR,
and stops for human confirm.

## Out of Scope

| Situation | Route to | Discriminator |
|---|---|---|
| Transport ONE commit across same-major branches | `odoo-forward-port` | FP = same major, cherry-pick, never asks "still needed?" |
| Rebase a branch onto another branch, SAME series | `odoo-git-rebase` | same series, no version bump, no core-absorption question |
| Risk + deprecation + diff PLAN only (no code) | `/odoo-plan-upgrade` | plan-upgrade writes NO code; upgrade EXECUTES (may take its plan as optional `--plan` input) |
| Scan deprecated symbols only | `odoo-deprecation-audit` | detection only; upgrade INVOKES it in recon then fixes |
| Diff two versions' APIs only | `odoo-version-diff` | detection only; upgrade calls it in recon |
| Write fresh upgrade-safe code, no module to carry | `odoo-coding` | nothing to upgrade |

> **Route in (not bare git-ops):** an Odoo module/cluster major-version upgrade routes HERE - this
> skill wraps git-toolkit's generic `git-ops` front door with the Odoo upgrade pipeline
> (core-absorption, dep-order adapt, install+test gate). Do NOT invoke `git-ops` directly for an
> Odoo module upgrade.

## Invocation - free natural language

The user speaks in free natural language (EN or VI). `/odoo-modules-upgrade <free text>`
passes the whole prompt through. There are NO required positional parameters and NO
inferring inline by the orchestrator. Optional structured hints (an explicit module scope,
an explicit target version, a prior `/odoo-plan-upgrade` output path) MAY be supplied
and are passed straight to the P0 intake subagent. The orchestrator dispatches P0 first
and asks the user only the `open_questions` that subagent returns - it CLARIFIES scope
rather than guessing it.

## The pipeline

`<cluster>` = the scope slug (the `cluster_slug` field resolved in P0 intake). Artifacts under
`.odoo-ai/modules-upgrade/<src>-<tgt>-<cluster>/`. `<path>` = the upgrade-worktree base, a
`.upg-worktrees/` directory SIBLING to the principal checkout (never inside it, so principal
`git status` stays clean). The integration-loop saga/rollback + checkpoint contract this pipeline
runs (record the pre-loop SHA, checkpoint each integrated wave, clean-abort or resume on failure -
never leave a half-built integration branch) is the shared SSOT
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`; `checkpoint.json` (§ below) is this
skill's realization of it. `<work-base>` = the base ref the integration branch forks from: HEAD
of the target-series branch when one exists, else the merge-base of the cluster against the
target series. ONE PR for the whole cluster, modules adapted + reviewed in dependency order
(leaves first).

Full per-phase commands, dispatch briefs, and artifact formats:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-phase-detail.md`.

**Sequence invariant (non-negotiable order).** The pipeline order is
`recon/classify -> (conditional) solution-design -> Plan Mode gate -> odoo-coding execution`.
NO `odoo-coding` / `odoo-coder` / `odoo-frontend-coder` dispatch may happen before the Plan
Mode gate. When the design trigger (see the design-trigger table) fires for a commit/module,
`odoo-solution-design` MUST complete and its design doc MUST be approved BEFORE the Plan Mode
gate for that commit/module. A genuinely tiny/mechanical change (the explicit skip rows of the
design-trigger table) bypasses design but STILL passes through the Plan Mode gate before any
code dispatch. Design is conditional; Plan Mode is not.

---

**P0 - Intake / resolve [STOP if open_questions non-empty].**
Goal: turn the free-text ask into structured inputs - infer series from current branch,
map to the OSM profile, auto-detect candidate modules, propose a cluster, CLARIFY scope.
Dispatch 1x intake subagent (sonnet). Brief: (1) read the CURRENT BRANCH NAME and infer
the Odoo series (branch `17.0-*` or `17.0` -> series `17.0`); cross-check the inferred
series against the MAX manifest `version` series found on disk (read sample
`__manifest__.py` files); if they disagree, raise as `open_question` rather than
silently inferring from the branch name alone. EXCEPTION (Viindoo Standard/Internal
profile - manifests carry a SHORT version with NO series prefix, per
`${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md`): the manifest `version` has no
series to compare, so SKIP this branch-vs-manifest-series cross-check and resolve the
source series from branch + profile - do NOT raise a false `disagree`; (2) map to the matching OSM profile via
`set_active_version` + `list_available_profiles` + `profile_inspect`; report repos +
module set; (3) auto-detect CANDIDATE MODULES by scanning `__manifest__.py` files for
a manifest `version` field whose major series is LESS THAN the target series (e.g.
`16.0.x.y.z` when target is `17.0`) AND by scanning for modules that depend on any
such stale module (depends-on-stale); `installable: False` is logged as a weak hint
only and is NOT the primary detector. For Viindoo short-form manifests (no series
prefix) the version-series scan yields nothing - detect candidates by profile
membership (`profile_inspect` module set) + branch series instead; (4) determine SOURCE version from the matched
profile's Odoo version or manifest `version` fields and TARGET version from the NL ask
(or next major if implied); (5) if the user's MODULE SCOPE is not explicit, do NOT
guess - return the candidate list + a proposed cluster (seeded from the dependency
closure of the confirmed targets, not from naming/path proximity) as `open_questions`.
Emit dependency hints from manifest `depends` fields.
Output: `intake.md` - {resolved_series, matched_profile, source_version, target_version,
candidate_modules[], proposed_cluster[], dependency_hints, open_questions[]}.
**Gate:** if `open_questions` non-empty, orchestrator presents the candidate list +
proposed cluster, asks the user to confirm/narrow scope, then resumes P1.

**P1 - Recon [graph + deprecation + diff + transitive-symbol, parallel].**
Goal: build the dependency DAG; get per-module deprecated-symbol fix list + platform API
delta + a transitive symbol-survival survey grounded at target. Four parallel dispatches:
(a) 1x `Explore` (sonnet) reads each `__manifest__.py` `depends` -> emits {module, depends[]}
for every module in the confirmed cluster -> orchestrator topo-sorts to leaves-first order
(cheap, deterministic); (b) `odoo-deprecation-audit` (via Skill tool, sonnet) for source +
TARGET version + module list (it runs the TARGET-version survival pass); (c) `odoo-version-diff`
(via Skill tool, sonnet) for source->target delta; (d) **P1d Transitive Symbol Survey**
(`Explore`, sonnet, read-only) - scans cluster source for every symbol referencing an external/core
dep and grounds each at target, emitting `blockers[]` that gate P3/P4 (full brief: phase-detail § P1d).
Output: `graph.md` (DAG + topo order), `deprecation.md`, `version-delta.md`, `transitive-symbol-survey.md`.
Assert DAG is acyclic: if a cycle is found, surface the cycle edges as
`DONE_WITH_CONCERNS` and ask the user to break the cycle before P2 proceeds (do not
hard-fail - cycles exist in real custom clusters and require human resolution).
Assert all dependencies exist at the target.

**P2 - Core-absorption comparison [per module, dep order, parallel within waves].**
Goal: for each module in dep order, decide DELETE-absorbed / KEEP / REWRITE(api) /
REWRITE(model) / MERGE / SPLIT by comparing custom behavior vs target-version core.
Per module in dep order (topo order from graph.md): dispatch 1x `odoo-diff-comparator`
(sonnet, opus for cluster-wide) + invoke `odoo-gap-analysis` (via Skill tool, sonnet) in
parallel. Modules at the SAME DAG depth (same wave) may be dispatched in parallel; a module
is NOT dispatched until its in-cluster dependencies have finished P2. Dispatch concurrency
follows `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` Mode B.
Comparator brief: "compare the module's nghiệp vụ / ý đồ / expected outcomes /
acceptance criteria against target-version CORE (`<target>`). Classify each feature per
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-classification-table.md`;
if the WHOLE module is provided by core, return verdict=DELETE-absorbed with the core
module/feature that replaces it."
Output per module: `absorption/<module>.md` - {per-feature classification, evidence
(OSM citation), proposed action}.

**P2b - Hard-call design [mandatory route-out for specific verdicts].**
Route to `odoo-solution-design` (`odoo-solution-architect` opus) when P2 returns ANY of
the following verdicts (tied to the verdict enum, not to a fuzzy "ambiguous" judgment):
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

These verdicts represent architectural or data decisions that must NOT be auto-decided by
the comparator or orchestrator. A trivial REWRITE(api)/KEEP - a localized deprecation-fix or
call-site swap confined to <= 5 call sites in 1 module with no public-surface change - SKIPS
design and goes straight to P3. DELETE-absorbed (no risk) and OBSOLETE never route (the module
is removed, not adapted). Reuse the non-trivial criterion from
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-solution-design/SKILL.md` § When to invoke - do NOT invent a
third definition. Full table: `references/upg-phase-detail.md` § P2b.
Emit the Continuation Contract and YIELD. On re-entry, read `design_doc` from the returned
contract's `inputs`, record it, and proceed to P3.

**P3 - Plan gate [Plan Mode].**
Goal: human approves the per-module DELETE/KEEP/REWRITE/MERGE/SPLIT table + install
order BEFORE any code is written or module deleted.
The main orchestrator calls `EnterPlanMode`; writes inside Plan Mode: per-module
classification table (DELETE -> list the core feature that replaces each AND inline the
behavioral-equivalence summary from `absorption/<module>.md` - the proof that every
override is equivalent or no-op; REWRITE/MERGE/SPLIT -> adapt tier + design link);
topo-sorted adapt order (leaves first); manifest bumps required; design-doc links for
any P2b module.
For EVERY module with a DELETE verdict, the plan table MUST inline:
(a) the absorbing_core_feature or OBSOLETE reason,
(b) the behavioral-equivalence proof summary (from signal #5 in `absorption/<module>.md`),
(c) a per-DELETE explicit confirmation prompt: "Confirm DELETE <module>? [y/N]"
    (separate from the overall plan approval).
Calls `ExitPlanMode`. User approves in the Plan Mode UI AND provides per-DELETE confirms.
After approval: write `plan.md` (RECORD of the approved plan; SSOT for P4+).
**This gate covers the irreversible DELETE decisions.** `EnterPlanMode` MUST precede
any branch, worktree, code write, or file deletion.

**P4 - Adapt [per module, dep order, child worktrees].**
Goal: make each module installable + working at the target series.
Create the JOB-tier integration worktree: delegate to git-operator (op: worktree add,
branch `upg/<src>-<tgt>-<cluster>`, worktree `<path>/upg-integration`, base `<work-base>`).
Per module in dep order: dispatch `odoo-coding`
(via Skill tool) -> `odoo-coder` / `odoo-frontend-coder` (ADAPT tier per
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-triage-table.md`)
in a child worktree off integration. When `odoo-frontend-coder` is dispatched, ported OWL/QWeb/SCSS is grounded against `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`.
For DELETE-absorbed and OBSOLETE modules: dispatch `odoo-coder` to run the dangling-reference
sweep first (grep repo for model names, XML IDs, group xmlids, env.ref targets), then
delegate the directory removal, staging, and commit to git-operator in the child worktree
(op: rm -r module dir + stage deletion + commit -s; confirmed: yes - user confirmed DELETE
at P3 Plan Mode gate; commit message per § Git / PR conventions absorbed/obsolete-delete form);
drop it from every depender's `depends` in their manifests.
For KEEP/REWRITE/MERGE/SPLIT: prepend this module's `blockers[]` from P1d
`transitive-symbol-survey.md` as a PREEMPTIVE FIX LIST, apply the breaking-change catalog from
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-classification-table.md`,
the per-module deprecation fix list from P1, flip `installable: False -> True`; do NOT bump the
manifest `version` (keep the existing short form); set `auto_install`/`application` only when a
manifest-comment breadcrumb directs (NO auto-detect of "bridge").
Converge each child worktree back to integration (serialized); remove child worktree.
**Principal-checkout-lock: NEVER check out or switch the principal checkout yourself.**
Materialize any needed branch by delegating a worktree add to git-operator.

**P4b - Code-review loop [odoo-code-review -> odoo-code-reviewer; fix via odoo-coding; cap 3].**
After P4 adapts the cluster into the integration worktree, dispatch `odoo-code-review` (via the
Skill tool) per adapted module IN DEP ORDER (leaves first), scoped to that module's adapt diff
(`TARGET: worktree:<path>/upg-integration`, module-scoped; DELETE-absorbed/OBSOLETE modules have no
adapt diff - skip them). On any CRITICAL/HIGH finding for a module, dispatch `odoo-coding` (same
ADAPT tier) to fix to root cause, then RE-REVIEW that module; MED/LOW are recorded for the P7 PR
review, not blocking. Cap at 3 review->fix iterations per module: a 3rd iteration still CRITICAL/HIGH
STOPS and escalates BLOCKED per ETHOS #7. Proceed to P5 ONLY when every adapted module's review
returns no CRITICAL/HIGH. Full delegation - the orchestrator dispatches reviewer + fixer, never
reviews or fixes inline. Write `<module>: reviewed` in checkpoint.json. Brief + loop protocol:
`references/upg-phase-detail.md` P4b. This is the in-pipeline review; the final pre-merge dep-order
review stays at P7 (two review points total).

**P5 - Install + test gate [ephemeral instance, wave-by-wave, demo=on].**
Goal: prove the whole cluster installs + tests green on a fresh target DB, bottom-up
wave by wave (one wave = one DAG depth level, leaves first). Installing wave-by-wave
localizes failures and allows resume to skip proven waves.
Run the instance with **demo=on** (no separate framework-validation phase): a module that
flips `installable: False -> True` is scanned by the target's FULL suite for the first time -
from v18 `base.TestInvisibleField` + `hr.TestSelfAccessProfile` run there and need demo data
(demo default is version-keyed - F0 `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md`;
gate stays demo=on regardless). The P4b review MUST cover ACL / `.sudo()` for every create/
write/compute override on a widely-used core model. Cross-ref
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/runbot-parity-checklist.md`.
Dispatch `odoo-instance` (via Skill tool, L2 human gate applies). Create the instance
once; then for each wave: dispatch init for that wave's modules, then run-tests for that
wave. Record per-wave green in `checkpoint.json` (status `installed`) and `install-test.md`.
On failure in a wave, dispatch `odoo-backend-debugger` or `odoo-ui-debugger` to diagnose
to root cause; feed the diagnosis back to P4 for the affected module. Resume P5 from the
failing wave (skip already-green waves per `checkpoint.json`). Loop until all waves green.
Output: `install-test.md` - {per-wave + per-module install ok?, test result, root-cause if red}.

**P5.7 - i18n reconcile [gated-on by default; auto-SKIP].**
Goal: keep translations intact across the upgrade WITHOUT regenerating them. Gated-on by
default; AUTO-SKIP when the cluster changed no translatable surface (no add/remove/rename of
a translatable field, label, view string, or selection). When it runs, wire the existing
`odoo-i18n` skill (no new i18n logic) against the P5 instance: export `.pot` -> polib-MERGE
into each existing `.po` (NEVER regenerate - a fresh export destroys existing msgstr) ->
hand-translate only the residual untranslated entries -> reload with `-u`. Detail: phase-detail § P5.7.

**P6 - Gate [STOP, human sign-off].**
Present `plan.md` + `absorption/*` summaries + `install-test.md` (including the list of
DELETED-absorbed modules + their reasons). Wait for human sign-off before the PR.

**P7 - PR + review [human merge].**
Pre-PR checklist (extends P6 sign-off): run the Runbot parity gates
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/runbot-parity-checklist.md`), then
add a convention-compliance pass (manifest version-form + always-invisible XML comment + rename
via `old_technical_name` - per `${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md`), a perf-lens
pass (no per-record `mapped()` aggregate on a high-volume model - use grouped `_read_group`), and
an i18n pass (P5.7 ran or was correctly auto-SKIPPED).
Push branch and open PR: delegate push to git-operator, then delegate PR creation to
github-operator - resolve upstream org/repo and base from `git remote get-url origin`.
No cluster-squash (per-module consolidation is allowed - see `references/upg-phase-detail.md` § Commit consolidation).
Delegate a dep-order code review of the integration worktree before human merge (via the
plugin's review capability, passing `worktree:<path>/upg-integration` and asking it to
review modules in dependency order). Wait for human merge.

## Hard rules

1. **Principal-checkout-lock.** NEVER check out or switch the principal (main)
   checkout off its branch. Materialize any needed branch by delegating a worktree add to git-operator.
2. **Plan Mode before any delete or code write.** P3 Plan Mode gate covers the irreversible
   DELETE decisions; no directory removal, no code changes, no worktree branch until P4 post-gate.
3. **No cluster-squash; per-module consolidation allowed.** Never collapse the whole cluster
   into one opaque commit - the per-module commit messages are the upgrade record. Consolidating
   a single module's WIP/fixup commits into ONE clean commit per module IS allowed (capability:
   `references/upg-phase-detail.md` § Commit consolidation - delegate to git-operator;
   tree-identity verified via `git diff --quiet`). Commit message formats: § Git / PR conventions.
4. **ONE PR per cluster.** All modules in one PR, reviewed in dep order.
5. **Code-level only; migration scripts NEVER inline; BLOCKED on data-at-risk.** The workflow is
   CODE-LEVEL only. This skill NEVER writes migration scripts - inline, as a P4 step, or otherwise.
   If a module genuinely needs a data migration script, the pipeline reports BLOCKED and routes
   the case to `odoo-data-migration`; the upgrade itself does not emit the script.
   Data-at-risk detection: if a candidate module is currently `installable: True`
   AND it defines stored non-computed fields OR has `noupdate="1"` data records, the P2
   comparator flags `data_at_risk: true` in `absorption/<module>.md`. A `data_at_risk`
   module that receives a REWRITE(model) or DELETE verdict MUST ESCALATE: the pipeline
   reports BLOCKED status and requires explicit human decision before proceeding code-only.
   The fresh P5 ephemeral DB cannot detect data loss - proceeding code-only on a
   data-at-risk module is a production-incident risk.
6. **DELETE-absorbed = delegated directory removal + dep cleanup + commit message, with two mandatory gates.**
   A module wholly absorbed by core is removed entirely, not set to `installable: False`.
   The commit message carries the reason (which core feature replaces it). No directory removal is
   permitted without: (a) signal #5 behavioral-equivalence proof recorded in
   `absorption/<module>.md` (all overrides enumerated + each proved equivalent or no-op);
   AND (b) an explicit per-DELETE human acknowledgment at P3, issued as a SEPARATE
   confirmation step, distinct from the overall plan approval. A single "approve plan"
   does NOT satisfy (b) - each DELETE row requires its own explicit confirm.
   For OBSOLETE verdict (module is moot at target, not absorbed by a named feature): the
   commit message uses `upg: delete <module> - obsolete at <tgt> (<reason>)` - do NOT
   invent a fake `absorbing_core_feature`.

## Checkpoint / resume

The pipeline writes a progress ledger at `.odoo-ai/modules-upgrade/<src>-<tgt>-<cluster>/checkpoint.json`
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
- `installed` - module's wave passed P5 install + test green.
- `done` - module fully processed (installed green + verified).

Resume behavior (per-phase skip rules - prevents overwriting completed work on crash/resume):
- P2 skips modules with status in {absorbed, designed, adapted, reviewed, installed, done}.
- P4 skips modules with status in {adapted, reviewed, installed, done}.
- P4b skips modules with status in {reviewed, installed, done}.
- P5 skips modules at the wave level with status in {installed, done}.
On crash or credit exhaustion, restart the orchestrator: it reads `checkpoint.json`
and resumes from the first module that has not yet reached the target phase's skip-threshold.
P5 per-wave records green in the ledger so re-runs do not re-install proven waves.

## Cluster / dependency handling

- DAG built ONCE in P1 by a subagent; the orchestrator only topo-sorts it (cheap).
- P2->P4 run per module in dep order (leaves first).
- P5 installs bottom-up WAVE BY WAVE (one wave per DAG depth level), recording per-wave
  green so failures localize and resume skips proven waves. ONE PR for the cluster (P7).

## Git / PR conventions

Git delegation contract: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.

- Branch: `upg/<src>-<tgt>-<cluster>` (e.g. `upg/16.0-17.0-l10n_vn`).
- Integration worktree: delegate to git-operator (op: worktree add, branch
  `upg/<src>-<tgt>-<cluster>`, worktree `<path>/upg-integration`, base `<work-base>`).
- Commit messages (adapt): `upg: <module> <src>-><tgt> - <KEEP|REWRITE|MERGE|SPLIT> <summary>`.
- Commit messages (absorbed delete): `upg: delete <module> - absorbed by core <core-module/feature> in <tgt> (no custom delta remains)`.
- Commit messages (obsolete delete): `upg: delete <module> - obsolete at <tgt> (<one-line reason>)`.
- Push to fork: delegate to git-operator (op: push branch `upg/<src>-<tgt>-<cluster>` to the fork
  remote; resolve fork remote URL from `git remote get-url origin` or a dedicated fork remote).
- PR: delegate to github-operator (op: create PR; resolve upstream org/repo and base from
  `git remote get-url origin`; no cluster-squash - per-module consolidation allowed -
  see `references/upg-phase-detail.md` § Commit consolidation).

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `find_deprecated_usage` - Scan the indexed codebase for usages of deprecated API patterns.
- `entity_lookup` ★ - Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `lookup_core_api` - Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `validate_depends` ⊕ - Validate compute method's `@api.depends('a.b', ...)` paths; flag `id` and suggest typos.
- `cli_help` - Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags.
- `list_available_profiles` ☆ - Enumerate which tenant profiles exist in the server index.
- `profile_inspect` - Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
<!-- END GENERATED TOOLS -->

## Standalone-first fallback

When OSM is unreachable, the pipeline degrades but does not stop. P0 intake derives
series from the branch name + reads manifest files directly (no OSM needed). P1 recon
reads `__manifest__.py` `depends` from disk for the DAG; `odoo-deprecation-audit` and
`odoo-version-diff` each have their own standalone fallback (disk-fallback-protocol).
P2 comparator falls back to disk reads of the source module + the target checkout per
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`. Label all artifacts
`grounded: local-source (not OSM-indexed)`. The install+test gate (P5) is unaffected.

## Continuation Contract

When the run finishes (or pauses at a gate), append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next).
`produced` lists `intake.md`, `graph.md`, `deprecation.md`, `version-delta.md`,
`transitive-symbol-survey.md`, `absorption/*.md`, `plan.md`, `install-test.md`,
`checkpoint.json`, and the PR URL.
When P2b routes a module out to design, `next: odoo-solution-design` with the Continuation
Contract payload and the run YIELDS. Additive output for the run-harness - does not change
anything produced above.
Note: this workflow has TWO review points - the P4b in-pipeline code-review loop (per module,
dep order, fix-until-clean, findings folded into the module rows of `install-test.md`) and the
P7 final dep-order PR review (pre-merge). Both are required; neither substitutes for the other.
