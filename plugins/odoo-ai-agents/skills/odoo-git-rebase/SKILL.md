---
name: odoo-git-rebase
argument-hint: "[branch] [onto base]"
description: >-
  Rebases a branch onto an updated base of the same Odoo series
model: sonnet
---

## Role

Rebase conductor. Own the git topology and the subagent lifecycle. Delegate EVERY diff read,
intent extraction, behavior comparison, conflict resolution, and verify to specialist subagents.
An intent-absorbing rebase is a SEMANTIC translation onto an updated SAME-version base, not a
text-replay: a clean replay (zero conflict markers) does NOT prove the feature survived.
Run no git: a repo fact comes from the `repo_facts` tool, and every other git result is a request
to `git-toolkit:git-ops` (`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`). NEVER read a diff or
judge business behavior inline.

## Out of Scope

| Situation | Route to | Discriminator |
|---|---|---|
| Port a commit ACROSS Odoo majors (version jump) | `odoo-forward-port` | different series = forward-port; SAME series = rebase |
| Upgrade an entire module/cluster across major series | `odoo-modules-upgrade` | "is this still needed at the new version?" = upgrade |
| One isolated change with no source branch to replay | `odoo-coding` | nothing to rebase |
| A version-to-version API delta only | `odoo-version-diff` | pure diff, no git op |
| Review an existing PR/diff without rebasing | `odoo-code-review` | static review, no replay |
| STANDALONE design, no commits to rebase | `odoo-solution-design` | a bucket-(c) re-implement INSIDE a rebase run uses the P5 route-out (in scope) |
| Parallelize N disjoint changes + squash | `odoo-planning` | rebase replays one branch range and never squashes |

> An Odoo same-series rebase routes HERE, not to bare git-ops: drive this pipeline and invoke
> `git-ops` (via the Skill tool) for each git step.

## Invocation - free natural language (NOT rigid parameters)

`/odoo-git-rebase <free text>` passes the whole prompt through. There are NO required positional
parameters and NO inferring inline. Dispatch the P0 intake subagent first and ask the user ONLY
the `open_questions` it returns, in one brief message.

## Artifact layout

`<slug> = <feature-ref>-onto-<new-base>`, sanitized: lowercase; replace each space, slash, or
any character outside `[a-z0-9._-]` with `-`; collapse repeated `-`; truncate to 64 chars. Compute `<slug>` ONCE and pass
the ABSOLUTE artifact path (`<ISOLATE_DIR>/git-rebase/<slug>/...`; resolve `<SHARE_DIR>`/`<ISOLATE_DIR>`
once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` and substitute the captured
absolute path) into every subagent brief; subagents never recompute the slug or re-resolve the
state dirs (`state-root-resolution.md` § Cross-worktree dispatch). Artifacts live under
`<ISOLATE_DIR>/git-rebase/<slug>/`.
`<old-base>` is the merge base of `<new-base>` and `<feature-ref>`: git-ops reports it at P1 and
`recon.md` records it (`old_base:`); every later phase reads it from there. Everything that reads
diff CONTENT is delegated. Full git-ops requests, dispatch briefs, and format templates: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-git-rebase/references/rb-phase-detail.md`.

## Checkpoint / resume

Saga/rollback + checkpoint contract: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`
(record the pre-loop SHA, checkpoint each applied commit, clean-abort or resume on failure).

`<ISOLATE_DIR>/git-rebase/<slug>/checkpoint.json` maps per-commit status and run state:

```json
{
  "phase": "P8",
  "<sha>": "extracted-pending-consolidation|extracted|designed|resolved|reviewed|done",
  "rebase_in_progress": true,
  "integration_worktree": "<absolute path to rb-integration worktree>"
}
```

`extracted-pending-consolidation` is a module-batched-dispatch-only state (the commit's CANONICAL
`intents/<sha>.md` copy is not yet confirmed - `references/rb-phase-detail.md` § P2 consolidation).
The default per-commit dispatch writes the canonical file directly and is marked `extracted`.

**P0 reads checkpoint.json first (before intake dispatch):**
- If `rebase_in_progress: true` and the integration worktree still has a live rebase
  (`repo_facts` on `<integration_worktree>` reports `operation_in_progress` = `rebase`):
  RESUME the P8 conflict loop from the stopped commit. Do NOT restart, do NOT abort the
  rebase. Skip commits with `status=resolved` or `status=done`; resume
  a `status=designed` commit at P6 design_doc ingestion.
- If `rebase_in_progress: false` (clean checkpoint): skip `status=done` phases and
  resume from the last incomplete phase.
- A `status=extracted-pending-consolidation` commit RESUMES by re-running ONLY the P2
  consolidation copy for that sha (idempotent - safe even if a prior partial copy already
  landed; never re-dispatch the extractor, whose module-scoped source file is untouched), then
  promotes it to `status=extracted`. Never treat `extracted-pending-consolidation` as
  `extracted` (P3's completeness gate refuses it).
- A dangling integration worktree from a crash is detected from `integration_worktree`
  path and resumed, not blindly recreated.

P2 writes `<sha>: extracted-pending-consolidation` after each intent file is written in
module-batched mode (`<sha>: extracted` directly otherwise). The P2 consolidation fan-in promotes a module-batched sha to `<sha>: extracted` only after git-ops confirms the
canonical record exists and is non-empty. P5 writes `<sha>: designed`.
P8 writes `<sha>: resolved` after git-ops continues the stopped rebase past that commit.
P8b writes `phase: P8b_done` after the collection gate passes.
P9b writes `<sha>: reviewed` after the code-review loop returns no CRITICAL/HIGH for that commit.

## The pipeline

**Dispatch-brief skeleton.** For every specialist agent dispatched below, fill the caller-side
skeleton in `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton (read it by path)
plus the target agent's family delta; never inline that file verbatim into a hard-leaf brief.

Run phases in order. ALL analysis (P1-P4) precedes the Plan Mode gate (P6), which precedes ANY
branch or worktree creation (P7). Concurrency for the P2 parallel fan-out follows
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` (Mode B, model-weighted budget 8).
Full per-phase dispatch briefs, git-ops requests, and artifact formats:
`references/rb-phase-detail.md`.

**Small-scale fast-path:** when recon shows <=5 commits, the patch-id pre-filter finds zero
absorbed commits, AND one cheap OSM batch over the feature diff finds zero renamed/moved
symbols, collapse P2+P3 into ONE sonnet `odoo-diff-comparator` pass and skip the separate
P2 extractor fan-out and P3 cluster comparator. P8b (symbol-survival + collection gate) still runs in all cases.
**Fast-path P8 fallback (commit dump provisioning):** the fast-path skips P2 so no
`intents/<sha>.md` exist. If P8 stops on a conflict, provision the dump first: invoke
git-ops to write the stopped commit's full output to
`<ISOLATE_DIR>/git-rebase/<slug>/commits/<sha>.dump`; then dispatch `odoo-intent-extractor` (rebase
MODE, brief: `references/rb-phase-detail.md` P2) with `commit_dump_path:` set to that path
before dispatching the `odoo-coding` skill at P8.

**Sequence invariant.** `recon/classify -> (conditional) solution-design -> Plan Mode gate ->
odoo-coding execution`. The Plan Mode gate is the request's one Plan-Mode approval
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request; see
P6). When a design trigger fires, its design doc is produced BEFORE the gate for that
commit/module. NO `odoo-coding` / `odoo-coder` / `odoo-frontend-coder` dispatch before the gate. A
change that skips design STILL passes through the gate. P5 design + P6 Plan Mode decide the adapt
strategy for every triggered commit BEFORE P7 creates the integration worktree.

**Orphan sweep (every run, BEFORE P0 below).**

`find <ISOLATE_DIR>/git-rebase/ -mindepth 1 -maxdepth 1 -type d -mmin +43200 -exec rm -rf {} +`

Rule: `${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3.

**P0 - Intake / resolve [haiku subagent - clarify gate if open_questions non-empty].**
Dispatch a haiku intake subagent with the full NL prompt. The subagent: parses the NL request to identify the feature
ref (local branch name or PR number/URL) and new-base; verifies both refs share the same Odoo
major series; emits `open_questions[]` for ambiguities and `branches_to_materialize[]` for any
ref not present locally. You: ask the user only the `open_questions` in one message then re-dispatch P0 with answers;
delegate PR details lookup to git-ops if a PR URL was given; delegate worktree creation to
git-ops for each `branches_to_materialize` entry (`references/rb-phase-detail.md`
Principal-checkout-lock). Emit `intake.md`:
{feature_ref, feature_worktree_path, new_base, same_series_ok, pr_resolved_from,
branches_to_materialize[], open_questions[]}.

**P1 - Recon (range enumerate) [git-ops - no gate].**
One git-ops request enumerates the commits after `<old-base>` up to `<feature-ref>`; a
patch-equivalence pre-filter marks candidates already on base (outcome-a candidate); for each
remaining commit emit {sha, modules[], subject, EXTRACT tier}. The same request reports every merge
base of the two refs - more than one is an open_question before P7 (ambiguous range boundary) - and
whether the range holds merge commits; if so, flag that the replay must preserve merges, or get
user confirmation. The pre-filter is a hint only; outcome-(a) is decided at P3/P10. Never skip a
commit on the pre-filter alone. Write `recon.md` (header `old_base:`). Request: `references/rb-phase-detail.md` P1.

**P2 - Intent extract (per non-(a) commit, PARALLEL) [git-ops pre-step + N x odoo-intent-extractor rebase MODE].**
Pre-step: invoke git-ops to write the full commit output (message + diff) for
each non-(a) commit to `<ISOLATE_DIR>/git-rebase/<slug>/commits/<sha>.dump`; collect the resulting
`{ <sha>: <abs-path> }` map. Then dispatch one `odoo-intent-extractor` per non-(a) commit with
rebase MODE brief: ground at `<new-base>` HEAD, do NOT call cross-version `api_version_diff`.
Pass `commit_dump_path: <abs-path>` and `SLUG: <slug>` (the bare run slug) in every extractor brief. Model per EXTRACT tier (`references/rb-triage-table.md`
Table 1). Each writes `intents/<sha>.md`: {intent_one_liner, symbols, outcome_hint, grounding}.
**Above ~30 non-(a) commits, batch intent extraction by MODULE (one extractor per module
covering its commits) rather than per-commit - the parallel unit becomes the module, so the
fan-out stays within the Mode B budget. When batching, a commit touching two modules is dispatched
inside BOTH modules' bundles, so set that dispatch's `SLUG` to `<slug>/<module>` (never the bare
run `<slug>`); a consolidation fan-in step (before P3, module-batched mode only) then copies each
commit's canonical record back to the bare-slug path `intents/<sha>.md`. Consolidation is
separately checkpointed (`extracted-pending-consolidation` -> `extracted`) and idempotent.**
Brief template: `references/rb-phase-detail.md` P2.

**P3 - Cluster behavior comparison [odoo-diff-comparator sonnet - completeness gate MUST pass
before dispatch; no human-confirm gate].**
Before dispatch: confirm every non-(a) commit has a canonical, non-empty `intents/<sha>.md`
record (delegated read-only check, never inline). A missing or empty record returns `BLOCKED` and P3 does NOT proceed: re-run the named remediation
(the P2 consolidation copy for the listed shas), then retry. Full gate:
`references/rb-phase-detail.md` P3.
One `odoo-diff-comparator` reads the feature diff (the branch's own changes since it diverged
from `<new-base>`, pre-computed by a git-ops pre-step per `references/rb-phase-detail.md` P3) + all
`intents/*.md`. Compare business intent, expected outcomes and acceptance criteria of the
feature range against `<new-base>` HEAD. Per commit: decide absorption failure mode
(already-present / renamed / moved / override-refactored / depends-drift / test-symbol-removed)
per `[[rb-intent-4outcome]]` (`${CLAUDE_PLUGIN_ROOT}/snippets/rb-intent-4outcome.md`). Emit `comparison.md`:
{per-commit: outcome a/b/c/d, failure_mode, evidence, proposed adapt} + duplicate-behavior risk
list.

**P4 - Classify (record only) [orchestrator - no gate].**
Read verdicts from P2+P3 structured output; assign exactly one outcome a/b/c/d per commit.
Flag bucket-(c) commits that are upgrade-scale (>~200 LOC of new code OR a full
component/framework rewrite) with the defer-or-do gate from
`references/rb-triage-table.md` § Bucket-(c) upgrade-scale defer-or-do gate. Record all in
`rebase-log.md`. Record verdicts from subagent output ONLY - no inline analysis.

**P5 - Design (conditional route-out) [odoo-solution-design -> odoo-solution-architect opus].**
Route a commit to `odoo-solution-design` when ANY design-trigger row matches (evaluated at P4,
recorded here): bucket-(c) "do now" ALWAYS; bucket-(b) adapt when it touches a model
field add/remove/type-change, changes a method signature, overrides or relocates an override
point (`create`/`write`/`unlink` or a method whose `find_override_point` chain has >=3
entries), is a refactor in the sense `odoo-solution-design` § When to invoke defines one, or is
full-stack / crosses the legacy<->OWL-2 boundary. A single-file, single-symbol, signature-preserving bucket-(b) rename - and every
bucket-(a)/(d) commit - skips design. Use the non-trivial criterion `odoo-solution-design` applies. Full table:
`references/rb-triage-table.md` § Design-trigger table. Emit Continuation Contract and YIELD. Canonical payload (match
exactly): `next: odoo-solution-design`, `inputs: { return_to: odoo-git-rebase,
design_slug_hint: <slug>-rb-<sha>, target_version: <series>, modules: [<names>],
intent_records: [<paths>], classification: <outcome bucket + one-line reason> }`. On re-entry, read
`design_doc` from the returned contract, record it against the commit, set
`status=designed`, and proceed to P6 - do not re-run design.

**P6 - Plan gate (Plan Mode - own gate; EnterPlanMode MUST precede any branch or worktree).**
This is the request's one Plan-Mode gate
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request): call
`EnterPlanMode`, present the plan, `ExitPlanMode` on approve. The plan CONTENT authored here (not routed through `odoo-planning`): commit topology; per-commit outcome + EXTRACT
tier + ADAPT tier; design-doc links; the rebase invocation (an integration worktree at the
feature tip, then the feature range replayed onto `<new-base>` - delegated to git-ops at P7);
conflict-resolution policy; B3 instance-verify decision.
Write `plan.md` AFTER approval as the resume record. No branch or worktree before `ExitPlanMode` + approval. `plan.md` template: `references/rb-phase-detail.md` P6.

**P7 - Create integration worktree + start rebase [delegated to git-ops].**
After Plan Mode approval: invoke git-ops to create the integration worktree AT THE
FEATURE TIP (branch rb/<slug>; NOT at new-base), turn on conflict-resolution reuse, and replay the commits after `<old-base>` onto
`<new-base>` there. git-ops returns
`DONE` (-> P8b) or `BLOCKED-CONFLICT` with `conflicted_files: [<paths>]` and
`stopped_commit: <sha>` (-> P8). Full dispatch brief: `references/rb-phase-detail.md` P7.

**P8 - Conflict-resolution loop [per stopped commit: Explore + the `odoo-coding` skill, ADAPT tier].**
For each commit the rebase stops on, read its P4 outcome first: outcome (a) or (d) -> instruct
git-ops to skip that commit and invoke nothing else - a bucket-(a)/(d) commit is never sent to
`odoo-coding`. Outcome (b)/(c): dispatch Explore to read conflicted files + the commit's
`intents/<sha>.md`; then dispatch the `odoo-coding` skill (via the Skill tool,
mirroring §P9b) at the ADAPT tier with `COMMIT: caller` (the rebase's own continue creates the
replayed commit), `TEST LEG: deferred - P9` (the node's test leg runs once, at P9) and the run's `RUN_ID`
to resolve hunks to INTENT on the new-base idiom. Record every module each resolution touched - P9 covers
them all. `odoo-coding`
owns the node's coder and synthesis (its `odoo-coder`) - including `odoo-frontend-coder`
for OWL/QWeb/SCSS legs, grounded against
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` - so do NOT dispatch raw
`odoo-coder` or `odoo-frontend-coder` agents for conflict resolution. Never leave an auto-merged line referencing a renamed/moved symbol. After `odoo-coding` returns RESOLVED: re-invoke git-ops per the
stateless-resume recipe in `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` (mechanical batch ->
semantic bounce -> continue the stopped rebase). On 3 consecutive BLOCKED returns from git-ops:
request git-ops to abort the rebase, restore from checkpoint, and escalate. Loop
until the rebase finishes. Conflict-class policy (`.po`/binary/generated), resolution-reuse hygiene, and
abort path: `references/rb-phase-detail.md` P8.

**P8b - Symbol-survival + collection gate [MUST - before any test-forward; all heavy checks DELEGATED].**
After the rebase finishes, ground every Odoo symbol the replayed range touches (conflicted
AND merge-clean-but-feature-touched files) against the shared-series base HEAD per
`[[fp-symbol-survival-check]]` Sections 1-2.5. A symbol absent/renamed/retyped at base is a BLOCKER. Resolve each into
its 4-outcome bucket and re-stage before P9. Then run the import-resolvability gate (`pyflakes`
over every feature-touched `.py`; any F821 = a broken import to resolve before P9) and the
collection ACCEPTANCE GATE: the replayed test files MUST import and collect cleanly;
`0 failed, N error(s)` is NOT a pass - a setUpClass crash means the tests never ran. Reuse the
same gate as forward-port P7. Who may run it: `[[fp-symbol-survival-check]]`
§ Who runs this check. Full brief incl. delegation contract +
import gate: `references/rb-phase-detail.md` P8b.

**P9 - Adapt + test forward (per touched module, conditional) [odoo-coding, MODE: adapt - no gate].**
For modules whose behavior changed (driven by P8b symbol-survival findings + recon.md modules[]) AND every module a P8 resolution touched (its
test leg was deferred to here), invoke `odoo-coding` once per module with the
adapt fields: the code is adapted to the new-base idiom first, then the node's test leg adapts the
branch's own tests and proves each by breaking its rule
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`). Bucket (a) is never forwarded here.
P8b collection gate is a precondition. Brief template: `references/rb-phase-detail.md` P9.

**P9b - Code-review loop [odoo-code-review -> odoo-code-reviewer; fix via odoo-coding; cap 3].**
After P9 leaves the adapt diff green with every adapted test proven, dispatch `odoo-code-review` (via the Skill tool) scoped
to the replayed/adapted diff in the integration worktree (`TARGET: worktree:<WT_ROOT>/rb-integration`,
attribute findings only to replayed lines - not pre-existing base debt). On any CRITICAL/HIGH
finding, dispatch `odoo-coding` (same ADAPT tier) to fix to root cause, then RE-REVIEW; MED/LOW are
recorded for the P12 PR review, not blocking. Cap at 3 review->fix iterations: a 3rd iteration still
CRITICAL/HIGH STOPS and escalates BLOCKED. Proceed to P10 ONLY when the review returns
no CRITICAL/HIGH. Dispatch reviewer + fixer, never review or fix inline. Write `<sha>: reviewed` in checkpoint.json. Brief + loop protocol:
`references/rb-phase-detail.md` P9b. The final pre-PR review stays at P12; both clear before the PR opens.

**P10 - Verify (range-diff + dup-guard + conditional instance) [git-ops pre-step + odoo-diff-comparator sonnet + conditionally the `odoo-instance` skill (via the Skill tool)].**
Two-step: (1) invoke git-ops to compare the original commit series (after `<old-base>` up to the
feature tip) with the rebased series (after `<new-base>` up to `rb/<slug>`), commit by commit, and write the comparison to `<ISOLATE_DIR>/git-rebase/<slug>/range-diff.txt`
(full brief: `references/rb-phase-detail.md` P10 pre-step); (2) dispatch `odoo-diff-comparator`
(sonnet) with `diff_path:` pointing to the surveyor-written file to confirm every P4 intent is
present and unchanged in meaning;
dup-guard: OSM `entity_lookup` definition-count across the full inheritance chain is the
PRIMARY (hard) dup signal (fail if count >1); grep is a secondary locator only. Emit
`verify.md`. CONDITIONAL the `odoo-instance` skill (via the Skill tool): run ONLY when the rebased range touches
DB-stateful behavior (model field add/remove/type-change, stored-compute, ORM
create/write/unlink override, migration dir, or TransactionCase/HttpCase test). Skip for
pure-frontend or docstring-only ranges. Decision from `commits[].modules[]` + P3 metadata -
no inline diff read. If P8b's database collection lane already provisioned the run's instance,
reuse that `INSTANCE_HANDLE` (`mode: reuse`); rebuild fresh when a break touched data files or schema. Full condition
list: `references/rb-phase-detail.md` P10 § B3.
When the `odoo-instance` skill (via the Skill tool) runs: resolve odoo-bin flags via `cli_help` (pass
`odoo_version=<series>`); instance lifecycle protocol:
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md`; test invocation conventions:
`${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`.

**P11 - Gate (STOP, human-confirm).**
Present `rebase-log.md` + `verify.md` and ask, as a text question,
`approve / skip / cancel`. STOP. Wait for `approve` before any push or PR; `skip` ends the run with the branch unpushed.

**P12 - Final review + PR [delegated review capability - human merge].**
Order follows the default tail (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Default tail). FIRST delegate the final code review against `worktree:<WT_ROOT>/rb-integration` and clear
its CRITICAL/HIGH findings on that worktree, BEFORE the branch is pushed and the PR opened. THEN resolve fork remote name and upstream org/repo from
`origin_url` and `remotes` of a `repo_facts` call, invoke git-ops to push rb/<slug> to the fork
remote, and invoke git-ops to open the PR against new-base on the upstream repo (head:
fork-remote:rb/<slug>); pass the fork remote name and upstream org/repo as brief fields - never
hardcode them. Only PR-OBSERVING work stays after the PR exists: CI-failure triage and the human
merge. Wait for human merge. NEVER squash. Full dispatch briefs: `references/rb-phase-detail.md` P12.

## Model triage

Per-row conditions: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-git-rebase/references/rb-triage-table.md`.
Decide the two tiers INDEPENDENTLY:
- **EXTRACT tier** (P1 intent extraction): haiku when the commit states its intent by message/PR/tests
  and stays in one module (or is doc/label/rename-only), sonnet when it needs reasoning (logic,
  migration, cross-module).
- **ADAPT tier** (P8 conflict resolution): `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
  § Model-tier selection; a bucket (a)/(d) test-only forward is haiku.

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

When Odoo Semantic (odoo-semantic-mcp) is unreachable: P2 intent extractors fall back to
local-source reads (`${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md`), labelling each
record `grounded: local-source - not OSM-indexed`; P3 diff-comparator falls back to disk
reads of the target checkout per `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`.
The range-diff + dup-guard + verify-by-behavior contracts are unchanged.

## Continuation Contract

When the run finishes or pauses at a gate, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next).
`produced` lists `intake.md`, `recon.md`, `intents/<sha>.md`, `comparison.md`,
`rebase-log.md`, `plan.md`, `verify.md`, and the PR URL. `next` is the human-confirm gate
(P11) or human merge (P12). When P5 routes a commit out to design, `next: odoo-solution-design`
with canonical payload and the run YIELDS; the plan runner re-enters odoo-git-rebase with the returned `design_doc`. Fold P9b review findings into `rebase-log.md`; a resume after a crash re-reads them from there.

## Additional resources

- `${CLAUDE_PLUGIN_ROOT}/skills/odoo-git-rebase/references/rb-phase-detail.md` - verbatim git
  commands, per-phase dispatch briefs, `rebase-log.md` / `plan.md` / `intake.md` formats, and
  the Principal-checkout-lock rule.
- `${CLAUDE_PLUGIN_ROOT}/skills/odoo-git-rebase/references/rb-triage-table.md` - EXTRACT +
  ADAPT model-tier tables + the bucket-(c) upgrade-scale defer-or-do gate.
- `[[rb-intent-4outcome]]` (`${CLAUDE_PLUGIN_ROOT}/snippets/rb-intent-4outcome.md`) - the
  4-outcome contract (a/b/c/d) + absorption-failure-mode catalog + duplicate-behavior guard
  procedure. Used by `odoo-intent-extractor` and `odoo-diff-comparator` in rebase MODE.
- `[[fp-symbol-survival-check]]` (`${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md`) -
  seven autosilent symbol-break classes + survival check protocol (Sections 1-2.5). Used at P8b
  grounded at the shared-series base HEAD (not a cross-version diff; note this in the dispatch
  brief).
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` - Mode B concurrency budget for
  the P2 parallel intent fan-out.
