---
name: odoo-git-rebase
description: >-
  Orchestrates a same-series Odoo git rebase - replaying a feature or fix branch onto an
  updated base of the SAME Odoo major version - forwarding INTENT, not diff text. Pipeline:
  NL-intake, intent sweep, behavior comparison, per-commit outcome classification, design
  route-out, Plan Mode gate, rebase-onto replay (delegated to git-operator), conflict-resolution loop,
  range-diff + dup-guard verify, human-confirm gate, and PR. Use when asked to
  "rebase my branch onto the updated 17.0" or "rebase PR #N onto the new base";
  "rebase nhánh lên base mới cùng phiên bản" hoặc "cập nhật base cho nhánh feature".
  Do NOT use to port ACROSS major Odoo versions (use odoo-forward-port), to upgrade a
  cluster to a new major (use odoo-modules-upgrade), to write one isolated change
  (use odoo-coding), to diff only (use odoo-version-diff), to review a PR without rebasing
  (use odoo-code-review), or to parallelize N disjoint work-items with cherry-pick + squash
  (use wave - rebase replays one branch range without squashing)
model: opus
---

## Persona

Rebase conductor. Own the git topology and the subagent lifecycle. Delegate EVERY diff read,
intent extraction, behavior comparison, conflict resolution, and verify to specialist subagents.
Core invariant: a rebase that absorbs intent is a SEMANTIC translation onto an updated
SAME-version base, not a text-replay. A clean replay (zero conflict markers) does
NOT prove the feature survived - the new base may already implement the feature (re-add =
duplicate), have renamed or moved the symbols this branch edits (clean merge, runtime
NameError), or refactored the override point away. The orchestrator issues only bounded-read
git calls (`git merge-base`, `git log --oneline`, `git diff --stat`) inline; every mutation
and unbounded read is delegated to git-toolkit agents (git-operator, git-surveyor,
github-operator) per `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`. It NEVER reads a
diff or judges business behavior inline; those always go to subagents.

## Out of Scope

| Situation | Route to | Discriminator |
|---|---|---|
| Port a commit ACROSS Odoo majors (version jump) | `odoo-forward-port` | different series = forward-port; SAME series = rebase |
| Upgrade an entire module/cluster across major series | `odoo-modules-upgrade` | "is this still needed at the new version?" = upgrade |
| One isolated change with no source branch to replay | `odoo-coding` | nothing to rebase |
| A version-to-version API delta only | `odoo-version-diff` | pure diff, no git op |
| Review an existing PR/diff without rebasing | `odoo-code-review` | static review, no replay |
| STANDALONE design, no commits to rebase | `odoo-solution-design` | a bucket-(c) re-implement INSIDE a rebase run uses the P5 route-out (in scope) |
| Parallelize N disjoint changes + squash | `wave` | wave cherry-picks + squashes disjoint WIs; rebase replays one branch range, never squashes |

## Invocation - free natural language (NOT rigid parameters)

The user speaks in free natural language (EN or VI), e.g. "rebase my `17.0-feat-x` branch onto
the latest `17.0`", "đưa nhánh feature của tôi lên base mới cùng phiên bản", or "rebase PR #482
onto the updated 17.0 base". `/odoo-git-rebase <free text>` passes the whole prompt through.
There are NO required positional parameters and NO inferring inline by the orchestrator. The
orchestrator dispatches the P0 intake subagent first (below) and asks the user ONLY the
`open_questions` that subagent returns in one brief message.

## Artifact layout

`<slug> = <feature-ref>-onto-<new-base>`, sanitized: lowercase; replace each space, slash, or
any character outside `[a-z0-9._-]` with `-`; collapse repeated `-`; truncate to 64 chars. The
orchestrator computes `<slug>` ONCE and passes the ABSOLUTE artifact path
(`.odoo-ai/git-rebase/<slug>/...`) into every subagent brief - subagents never recompute the slug
(prevents artifact-path drift). Artifacts under `.odoo-ai/git-rebase/<slug>/` (gitignored).
`<old-base> = git merge-base <new-base> <feature-ref>` (the orchestrator runs this ONE mechanical
command; everything that reads diff CONTENT is delegated). Full git commands, dispatch briefs, and
format templates: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-git-rebase/references/rb-phase-detail.md`.

## Checkpoint / resume

`.odoo-ai/git-rebase/<slug>/checkpoint.json` maps per-commit status and run state:

```json
{
  "phase": "P8",
  "<sha>": "extracted|designed|resolved|reviewed|done",
  "rebase_in_progress": true,
  "integration_worktree": "<absolute path to rb-integration worktree>"
}
```

**P0 reads checkpoint.json first (before intake dispatch):**
- If `rebase_in_progress: true` and the integration worktree still has a live rebase
  (`test -d $(git -C <integration_worktree> rev-parse --git-path rebase-merge)`):
  RESUME the P8 conflict loop from the stopped commit. Do NOT restart, do NOT abort the
  rebase. Skip commits with `status=resolved` or `status=done`; resume
  a `status=designed` commit at P6 design_doc ingestion.
- If `rebase_in_progress: false` (clean checkpoint): skip `status=done` phases and
  resume from the last incomplete phase.
- A dangling integration worktree from a crash is detected from `integration_worktree`
  path and resumed, not blindly recreated.

P2 writes `<sha>: extracted` after each intent file is written. P5 writes `<sha>: designed`.
P8 writes `<sha>: resolved` after the --continue step succeeds for that commit.
P8b writes `phase: P8b_done` after the collection gate passes.
P9b writes `<sha>: reviewed` after the code-review loop returns no CRITICAL/HIGH for that commit.

## The pipeline

Run phases in order. ALL analysis (P1-P4) precedes the Plan Mode gate (P6), which precedes ANY
branch or worktree creation (P7). Concurrency for the P2 parallel fan-out follows
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` (Mode B, model-weighted budget 8).
Full per-phase dispatch briefs, verbatim git commands, and artifact formats:
`references/rb-phase-detail.md`.

**Small-scale fast-path:** when recon shows <=5 commits, the patch-id pre-filter finds zero
absorbed commits, AND one cheap OSM batch over the three-dot diff finds zero renamed/moved
symbols, collapse P2+P3 into ONE sonnet `odoo-diff-comparator` pass and skip the opus cluster
comparator. P8b (symbol-survival + collection gate) still runs in all cases - it is what
guarantees correctness at small scale and is not optional even on a 1-commit branch.
**Fast-path P8 fallback (commit dump provisioning):** the fast-path skips P2 so no
`intents/<sha>.md` exist. If P8 stops on a conflict, provision the dump first: dispatch
git-surveyor to write the stopped commit's full output to
`.odoo-ai/git-rebase/<slug>/commits/<sha>.dump`; then dispatch `odoo-intent-extractor` (rebase
MODE, brief: `references/rb-phase-detail.md` P2) with `commit_dump_path:` set to that path
before dispatching the `odoo-coding` skill at P8.

**Sequence invariant (non-negotiable order).** The pipeline order is
`recon/classify -> (conditional) solution-design -> Plan Mode gate -> odoo-coding execution`.
NO `odoo-coding` / `odoo-coder` / `odoo-frontend-coder` dispatch may happen before the Plan
Mode gate. When the design trigger (see the design-trigger table) fires for a commit/module,
`odoo-solution-design` MUST complete and its design doc MUST be approved BEFORE the Plan Mode
gate for that commit/module. A genuinely tiny/mechanical change (the explicit skip rows of the
design-trigger table) bypasses design but STILL passes through the Plan Mode gate before any
code dispatch. Design is conditional; Plan Mode is not.

Because the conflict-resolution coder runs DURING the rebase (P8, after the rebase starts at
P7), the design (P5) and Plan Mode (P6) MUST decide the adapt strategy for every triggered
commit BEFORE P7 creates the integration worktree and starts the onto-rebase.

**P0 - Intake / resolve [sonnet subagent - clarify gate if open_questions non-empty].**
Turn the free-text ask into structured inputs without guessing. Dispatch a sonnet intake
subagent with the full NL prompt. The subagent: parses the NL request to identify the feature
ref (local branch name or PR number/URL) and new-base; verifies both refs share the same Odoo
major series; emits `open_questions[]` for ambiguities and `branches_to_materialize[]` for any
ref not present locally. The orchestrator: asks the user only the `open_questions` in one
message then re-dispatches P0 with answers; delegates PR details lookup to github-operator if a
PR URL was given; delegates worktree creation to git-operator for each `branches_to_materialize`
entry (principal-checkout-lock is enforced by git-operator - see
`references/rb-phase-detail.md` Principal-checkout-lock). Emit `intake.md`:
{feature_ref, feature_worktree_path, new_base, same_series_ok, pr_resolved_from,
branches_to_materialize[], open_questions[]}.

**P1 - Recon (range enumerate) [git-surveyor - no gate].**
Enumerate commits in `<old-base>..<feature-ref>`; patch-id pre-filter candidates already on
base (mark outcome-a candidate); for each remaining commit emit {sha, modules[], subject,
EXTRACT tier}. Also run `git merge-base --all` - if >1 line, surface as open_question before
P7 (ambiguous range boundary). Also run a graph topology check to detect merge commits in range;
if present, flag for `--rebase-merges` or user confirmation. The patch-id pre-filter is a
cheap hint only; outcome-(a) is authoritatively decided at P3/P10. Never skip
a commit on patch-id alone without P3 confirmation.
Write `recon.md`. Verbatim commands: `references/rb-phase-detail.md` P1.

**P2 - Intent extract (per non-(a) commit, PARALLEL) [git-surveyor pre-step + N x odoo-intent-extractor rebase MODE].**
Pre-step: dispatch git-surveyor to write the full commit output (message + diff) for
each non-(a) commit to `.odoo-ai/git-rebase/<slug>/commits/<sha>.dump`; collect the resulting
`{ <sha>: <abs-path> }` map. Then dispatch one `odoo-intent-extractor` per non-(a) commit with
rebase MODE brief: ground at `<new-base>` HEAD, do NOT call cross-version `api_version_diff`.
Pass `commit_dump_path: <abs-path>` in every extractor brief. Model per EXTRACT tier
(`references/rb-triage-table.md` Table 1). Each writes `intents/<sha>.md`:
{intent_one_liner, symbols, outcome_hint, grounding}. **Above ~30 non-(a) commits, batch
intent extraction by MODULE (one extractor per module covering its commits) rather than
per-commit, to bound dispatch waves and the P3 context load.** Brief template:
`references/rb-phase-detail.md` P2.

**P3 - Cluster behavior comparison [odoo-diff-comparator opus - no gate].**
One `odoo-diff-comparator` reads the three-dot diff (range `<new-base>...<feature-ref>`,
pre-computed by a git-surveyor pre-step per `references/rb-phase-detail.md` P3) + all
`intents/*.md`. Compare nghiệp vụ / ý đồ / expected outcomes / acceptance criteria of the
feature range against `<new-base>` HEAD. Per commit: decide absorption failure mode
(already-present / renamed / moved / override-refactored / depends-drift / test-symbol-removed)
per `[[rb-intent-4outcome]]` (`${CLAUDE_PLUGIN_ROOT}/snippets/rb-intent-4outcome.md`). **When
intent files exceed ~40, chunk the comparator by module cluster and merge per-cluster verdicts;
never load >40 intent files into one opus context.** Emit `comparison.md`:
{per-commit: outcome a/b/c/d, failure_mode, evidence, proposed adapt} + duplicate-behavior risk
list.

**P4 - Classify (record only) [orchestrator - no gate].**
Read verdicts from P2+P3 structured output. Assign exactly one outcome a/b/c/d per commit.
Flag bucket-(c) commits that are upgrade-scale (>~200 LOC of new code OR a full
component/framework rewrite) with the defer-or-do gate from
`references/rb-triage-table.md` § Bucket-(c) upgrade-scale defer-or-do gate. Record all in
`rebase-log.md`. The orchestrator records verdicts from subagent output ONLY - no inline
analysis.

**P5 - Design (conditional route-out) [odoo-solution-design -> odoo-solution-architect opus].**
Route a commit to `odoo-solution-design` when ANY design-trigger row matches (evaluated at P4,
recorded here): bucket-(c) "do now" ALWAYS; bucket-(b) adapt when it touches a model
field add/remove/type-change, changes a method signature, overrides or relocates an override
point (`create`/`write`/`unlink` or a method whose `find_override_point` chain has >=3
entries), spans > 3 files or >= 2 modules, or is full-stack / crosses the legacy<->OWL-2
boundary. A single-file, single-symbol, signature-preserving bucket-(b) rename - and every
bucket-(a)/(d) commit - skips design. Reuse the non-trivial criterion from
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-solution-design/SKILL.md` § When to invoke - do NOT invent a
third definition. Full table: `references/rb-triage-table.md` § Design-trigger table. Emit Continuation Contract and YIELD. Canonical payload (match
exactly): `next: odoo-solution-design`, `inputs: { return_to: odoo-git-rebase,
design_slug_hint: <slug>-rb-<sha>, target_version: <series>, modules: [<names>],
intent_records: [<paths>], classification: <outcome bucket + one-line reason> }`. On re-entry, read
`design_doc` from the returned contract, record it against the commit, set
`status=designed`, and proceed to P6 - do not re-run design.

**P6 - Plan gate (Plan Mode - own gate; EnterPlanMode MUST precede any branch or worktree).**
The orchestrator calls `EnterPlanMode` and writes the plan: commit topology; per-commit outcome
+ EXTRACT tier + ADAPT tier; design-doc links; the rebase invocation (worktree add at feature
tip then two-arg rebase-onto on the integration worktree HEAD - delegated to git-operator at
P7); conflict-resolution policy; B3 instance-verify decision.
Calls `ExitPlanMode`. User approves in the Plan Mode UI. Write `plan.md` AFTER approval as the
resume record. No branch or worktree is created before this point. `plan.md` template:
`references/rb-phase-detail.md` P6.

**P7 - Create integration worktree + start rebase [delegated to git-operator].**
After Plan Mode approval: dispatch git-operator to create the integration worktree AT THE
FEATURE TIP (branch rb/<slug>; NOT at new-base), enable rerere (rr-cache is repo-global,
shared across worktrees), and run the two-arg onto form (new-base as target, old-base as
upstream) on the worktree HEAD. The two-arg form never names a branch checked out in another
worktree, avoiding the `fatal: already used by worktree` abort. git-operator returns
`DONE` (-> P8b) or `BLOCKED-CONFLICT` with `conflicted_files: [<paths>]` and
`stopped_commit: <sha>` (-> P8). Full dispatch brief: `references/rb-phase-detail.md` P7.

**P8 - Conflict-resolution loop [per stopped commit: Explore + the `odoo-coding` skill, ADAPT tier].**
For each commit the rebase stops on: dispatch Explore to read conflicted files + the commit's
`intents/<sha>.md` + P4 outcome; then dispatch the `odoo-coding` skill (via the Skill tool,
mirroring §P9b) at the ADAPT tier to resolve hunks to INTENT on the new-base idiom. `odoo-coding`
owns the backend/frontend split and the coder fan-out/synthesis - including `odoo-frontend-coder`
for OWL/QWeb/SCSS legs, grounded against
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` - so do NOT dispatch raw
`odoo-coder` / `odoo-frontend-coder` agents for conflict resolution. If outcome=(a) or (d),
instruct git-operator to skip that commit. Never leave an auto-merged line referencing a
renamed/moved symbol. After `odoo-coding` returns RESOLVED: re-dispatch git-operator per the
stateless-resume recipe in `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` (mechanical batch ->
semantic bounce -> on-disk --continue). On 3 consecutive BLOCKED returns from git-operator:
request git-operator to abort the rebase, restore from checkpoint, escalate per ETHOS #7. Loop
until the rebase finishes. Conflict-class policy (`.po`/binary/generated), rerere hygiene, and
abort path: `references/rb-phase-detail.md` P8.

**P8b - Symbol-survival + collection gate [MUST - before any test-forward; all heavy checks DELEGATED].**
After the rebase finishes, ground every Odoo symbol the replayed range touches (conflicted
AND merge-clean-but-feature-touched files) against the shared-series base HEAD per
`[[fp-symbol-survival-check]]` Sections 1-2.5. A symbol absent/renamed/retyped at base is a
BLOCKER: it auto-merged with no conflict marker and will crash at runtime. Resolve each into
its 4-outcome bucket and re-stage before P9. Then run the import-resolvability gate (`pyflakes`
over every feature-touched `.py`; any F821 = a broken import to resolve before P9) and the
collection ACCEPTANCE GATE: the replayed test files MUST import and collect cleanly;
`0 failed, N error(s)` is NOT a pass - a setUpClass crash means the tests never ran. Reuse the
same gate as forward-port P7. The orchestrator does NOT run these checks in its own context: it
dispatches the read-only delegates (Explore to enumerate feature-touched files, git-surveyor to
run the gates) and records only the PASS/FAIL verdict. Full brief incl. delegation contract +
import gate: `references/rb-phase-detail.md` P8b.

**P9 - Test forward (per touched module, conditional) [odoo-test-writing adapt + odoo-coder - no gate].**
For modules whose behavior changed (driven by P8b symbol-survival findings + recon.md
modules[], not a vague "behavior changed" heuristic), adapt the branch's own tests to the
new-base idiom: RED first, then GREEN. P8b collection gate is a precondition. Brief template:
`references/rb-phase-detail.md` P9.

**P9b - Code-review loop [odoo-code-review -> odoo-code-reviewer; fix via odoo-coding; cap 3].**
After P9 leaves the adapt diff test-GREEN, dispatch `odoo-code-review` (via the Skill tool) scoped
to the replayed/adapted diff in the integration worktree (`TARGET: worktree:<WT_ROOT>/rb-integration`,
attribute findings only to replayed lines - not pre-existing base debt). On any CRITICAL/HIGH
finding, dispatch `odoo-coding` (same ADAPT tier) to fix to root cause, then RE-REVIEW; MED/LOW are
recorded for the P12 PR review, not blocking. Cap at 3 review->fix iterations: a 3rd iteration still
CRITICAL/HIGH STOPS and escalates BLOCKED per ETHOS #7. Proceed to P10 ONLY when the review returns
no CRITICAL/HIGH. Full delegation - the orchestrator dispatches reviewer + fixer, never reviews or
fixes inline. Write `<sha>: reviewed` in checkpoint.json. Brief + loop protocol:
`references/rb-phase-detail.md` P9b. This is the in-pipeline review; the final pre-merge review
stays at P12 (two review points total).

**P10 - Verify (range-diff + dup-guard + conditional instance) [git-surveyor pre-step + odoo-diff-comparator sonnet + conditional odoo-instance-ops].**
Two-step: (1) dispatch git-surveyor to run `git range-diff <old-base>..<feature-tip>
<new-base>..rb/<slug>` and write the output to `.odoo-ai/git-rebase/<slug>/range-diff.txt`
(full brief: `references/rb-phase-detail.md` P10 pre-step); (2) dispatch `odoo-diff-comparator`
(sonnet) with `diff_path:` pointing to the surveyor-written file to confirm every P4 intent is
present and unchanged in meaning;
dup-guard: OSM `entity_lookup` definition-count across the full inheritance chain is the
PRIMARY (hard) dup signal (fail if count >1); grep is a secondary locator only. Emit
`verify.md`. CONDITIONAL `odoo-instance-ops`: run ONLY when the rebased range touches
DB-stateful behavior (model field add/remove/type-change, stored-compute, ORM
create/write/unlink override, migration dir, or TransactionCase/HttpCase test). Skip for
pure-frontend or docstring-only ranges. Decision from `commits[].modules[]` + P3 metadata -
no inline diff read. Full condition list: `references/rb-phase-detail.md` P10 § B3.
When `odoo-instance-ops` runs: resolve odoo-bin flags via `cli_help` (pass
`odoo_version=<series>`); instance lifecycle protocol:
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE.md`; test invocation conventions:
`${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`.

**P11 - Gate (STOP, human-confirm).**
Present `rebase-log.md` + `verify.md`. STOP. Wait for human approval before any push or PR.

**P12 - PR + review [delegated review capability - human merge].**
Resolve fork remote name and upstream org/repo from `git remote get-url origin` (bounded read,
inline). Dispatch git-operator to push rb/<slug> to the fork remote. Dispatch github-operator
to open the PR against new-base on the upstream repo (head: fork-remote:rb/<slug>); pass the
fork remote name and upstream org/repo as brief fields - never hardcode them. Delegate a code
review of the integration worktree before merge. Wait for human merge. NEVER squash. Full
dispatch briefs: `references/rb-phase-detail.md` P12.

## Model triage

Full both-table detail with per-row conditions:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-git-rebase/references/rb-triage-table.md`.

The two tiers are decided INDEPENDENTLY:
- **EXTRACT tier** (P1 intent extraction): haiku/sonnet/opus per commit complexity.
- **ADAPT tier** (P8 conflict resolution): haiku/sonnet/opus/fable per adapt complexity
  (fable ALWAYS needs explicit human confirmation at P6 plan gate).

Never reuse one tier as the other.

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
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `entity_lookup` ★ - Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `find_override_point` - Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior.
- `find_test_examples` - Semantic search for Odoo test code examples (test_method, test_class, js_test chunks only - never returns production code).
- `test_base_classes` - Menu of official Odoo test framework base classes (TransactionCase, HttpCase, SavepointCase, Form, etc.) for the given version, with test_type and cursor contract.
- `tests_covering` - List test methods that have COVERS_MODEL/COVERS_FIELD/COVERS_METHOD edges to the target model or field (static reference coverage, not runtime executed coverage).
<!-- END GENERATED TOOLS -->

## Standalone fallback

When Odoo Semantic (odoo-semantic-mcp) is unreachable: P2 intent extractors fall back to
local-source reads (`${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md`), labelling each
record `grounded: local-source (not OSM-indexed)`; P3 diff-comparator falls back to disk
reads of the target checkout per `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`.
The range-diff + dup-guard + verify-by-behavior contracts are unchanged.

## Continuation Contract

When the run finishes or pauses at a gate, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next).
`produced` lists `intake.md`, `recon.md`, `intents/<sha>.md`, `comparison.md`,
`rebase-log.md`, `plan.md`, `verify.md`, and the PR URL. `next` is the human-confirm gate
(P11) or human merge (P12). When P5 routes a commit out to design, `next: odoo-solution-design`
with canonical payload and the run YIELDS; the run-driver advances the hop and re-enters
odoo-git-rebase with the returned `design_doc`. In-pipeline review findings (P9b) are folded
into `rebase-log.md`; a resume after a crash mid-loop re-reads them from there. This workflow
has TWO review points: P9b (in-pipeline, fix-until-clean, before verify) and P12 (final PR
review, pre-merge) - both are active.

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
  brief). Series-agnostic; forward-port and rebase both use it.
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` - Mode B concurrency budget for
  the P2 parallel intent fan-out.
