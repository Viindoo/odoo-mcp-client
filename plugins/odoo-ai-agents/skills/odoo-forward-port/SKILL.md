---
name: odoo-forward-port
argument-hint: "[from-series] [to-series] [module/range]"
description: >-
  This skill orchestrates a continuous or one-shot Odoo forward-port - porting fixes
  and features from a lower-series source repo or branch up to a higher-series target -
  as an ordered agentic pipeline that forwards INTENT, not code text. It runs a parallel
  read-only intent sweep, a 4-outcome classification, an installable probe, a conditional
  design route-out, a Plan Mode gate, an SHA-preserving git merge, a symbol-survival check
  that catches autosilent field breaks, test-first adapt, per-batch verify-by-behavior, a
  human-confirm gate, and a PR. Invoked when asked to
  "forward-port", "port commits to a
  newer Odoo version", "merge a fix forward", "continuous forward-port", "one-shot
  back-of-port", or in Vietnamese "forward-port Odoo", "port fix lên phiên bản mới",
  "đẩy commit lên series cao", "forward-port liên tục". Do NOT use to write one isolated
  change (use odoo-coding), to diff two versions only (use odoo-version-diff), or to
  review a PR (use odoo-code-review)
model: opus
---

## Role

Forward-port conductor: own the git topology, per-commit pipeline, and subagent lifecycle.
Decide which commit at which model tier, which outcome bucket, when to merge, when to gate.
Delegate leaf tasks - intent extraction, code adapt, test forwarding - to specialist agents.
Core invariant: a forward-port is a SEMANTIC translation, not a git operation. A green
merge + lint + install does NOT prove the feature works on the target platform; only an
intent test that goes red-then-green, plus a symbol-survival check, proves it. SHA is sacred -
continuous forward-port absorbs the source SHA into the target DAG so the merge-base advances;
never squash or cherry-pick in continuous mode.

## Out of Scope

- One isolated change with no source commit to port -> use `odoo-coding`
- A version-to-version API/feature delta only (no merge, no adapt) -> use `odoo-version-diff`
- Reviewing or auditing an existing PR or diff -> use `odoo-code-review`
- A pre-upgrade deprecation sweep of one codebase -> use `odoo-deprecation-audit`
- A STANDALONE design request with no commits to port -> use `odoo-solution-design` directly.
  A bucket-(c) commit INSIDE a forward-port run that requires non-trivial design is handled by
  the P3 conditional route-out (which delegates to odoo-solution-design and returns) - that is
  IN scope of this skill, not a hand-off boundary
- Parallelizing N disjoint WIs with cherry-pick + squash semantics -> use `odoo-planning` (the
  USER-facing choice; it plans the wave-batched delivery for `run-harness`'s between-wave integration,
  which re-bases by cherry-pick - whereas forward-port keeps SHA by merge: a different git contract)

> **Route in (Odoo forward-port lands HERE, not bare git-ops):** an Odoo forward-port routes to
> this skill - it wraps git-toolkit's generic `git-ops` front door with the Odoo intent-forwarding
> pipeline (intent sweep, symbol-survival, verify-by-behavior). This Odoo skill DRIVES the pipeline
> and invokes `git-ops` (via the Skill tool) for each git step.

## Invocation

Fires three ways - all reach the same pipeline: the `/odoo-forward-port` slash command,
a natural-language description match, or a Skill-tool call from an orchestrator (e.g.
`odoo-intake`).

### Arguments

```
/odoo-forward-port <source-ref> <target-branch> [--scope <mod1,mod2>] [--since <sha>] [--one-shot]
```

| Argument | Required | Description |
|---|---|---|
| `<source-ref>` | yes | Source branch or commit range (e.g. `origin/17.0`, `v17-fixes`) |
| `<target-branch>` | yes | Target branch (e.g. `origin/18.0`, `18.0-fp-batch-01`) |
| `--scope <modules>` | no | Comma-separated module list; default = all modified modules in range |
| `--since <sha>` | no | Only commits after this SHA (continuous or incremental FP) |
| `--one-shot` | no | Cherry-pick mode for a single one-time port (default: merge mode) |

Parsed from `$ARGUMENTS` in P0 (missing `source-ref`/`target-branch` -> ask once, one message,
before any read or git op).

### When to use

- **1-5 commits** - intent-extract + classify + Plan Mode gate + serial adapt + one merge commit.
- **6+ commits** - full plan (commit topology, per-commit tier, buckets) in Plan Mode, recorded
  to `plan.md`, with a human-confirm gate per merge batch.
- **Continuous mode (default)** - recurring; source keeps evolving; SHA preserved so the
  merge-base advances and past conflicts are never re-resolved.

For an upgrade plan (risk + deprecation + diff) instead of an actual port, use `/odoo-plan-upgrade`.

## Hard rules

1. **Target-branch-lock** - NEVER checkout, switch, commit, merge, rebase, reset, or push the
   target branch B directly. Another session may hold B's working tree. All integration happens
   in a dedicated integration worktree branched FROM B (the JOB tier below). Read-only ops on
   B are allowed. Delegate every mutation on the integration worktree to git-toolkit via the
   `git-ops` skill (`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`). The integration-loop saga (record the
   pre-loop SHA, checkpoint after each integrated commit, clean-abort or resume on failure - never
   leave a half-built integration branch) follows the shared SSOT
   `${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`.

2. **Keep the source SHA (continuous)** - continuous forward-port uses a no-ff no-commit
   merge (delegated to git-toolkit via `git-ops`; see `[[fp-merge-absorption]]`) so the source commit
   enters the target DAG with its SHA intact and the merge-base advances. NEVER squash or cherry-pick for
   continuous mode - both mint a fresh SHA, leave the merge-base behind, and force
   re-resolving the same conflict every future run. Cherry-pick is the one-shot-only
   fallback. Full protocol: `[[fp-merge-absorption]]`.

3. **Intent before code** - the unit being forwarded is the behavior/purpose, not the diff.
   P1 extracts intent (read-only); P8 re-implements that intent on the target
   idiom. Never paste a source diff hunk forward and call it done. SSOT: `[[fp-intent-4outcome]]`.

4. **Verify by behavior, not by text** - success = the forwarded INTENT test goes RED then
   GREEN on the target, plus confirm-by-toggle (disable the adapt code -> the FP-delta test
   must go red again). A clean merge is necessary, never sufficient.

5. **Symbol-survival before adapt** - after every merge, run the P6 symbol-survival
   check on BOTH conflicted files and merge-clean-but-source-touched files. A source line
   referencing a symbol removed/renamed at the target produces NO conflict marker but breaks
   at runtime. Resolve every broken symbol into a bucket before adapt starts. SSOT:
   `[[fp-symbol-survival-check]]`.

6. **Human-confirm merge** - STOP at the P10 gate. The P4 plan gate runs the shared Plan-Mode gate
   (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Plan-Mode enter/exit; user approves
   in the Plan Mode UI). No automated commit of the integration into B, no auto-merge of the PR.
   Present and wait.

7. **Outcome a/d still merge** - buckets (a) already-satisfied and (d) no-longer-relevant
   produce no adapt diff but STILL create the merge commit (keeps SHA, advances merge-base).
   Skipping the merge for them re-encounters the commit tomorrow. SSOT: `[[fp-merge-absorption]]`.

8. **Verify subagent claims** - never trust a leaf's self-report of GREEN. Run the verify
   command yourself per batch (P9) before the P10 gate.

9. **Acceptance is mandatory (narrow escape only)** - P12 dispatches `odoo-acceptance` ONCE for
   the whole forward-ported batch before the human merge decision, mirroring the rigor a new
   module build gets. This is NOT opt-in: skip it only when the touched module set is a true
   dependency leaf with zero in-repo dependents and no behavioral surface, and record that proof -
   never skip silently. The forward-port is not DONE without an ACCEPTED verdict or a recorded
   narrow-escape.

## Git topology - two tiers of worktree

Forward-port never touches B directly and parallelizes through worktree isolation.

**JOB tier (always):** create `fp/<slug>` integration branch via dedicated worktree (delegated
to git-toolkit via `git-ops`) from B's HEAD. All absorption, adapt, and verify happen inside this integration
worktree. The target branch B is read-only for the whole run; the only thing that ever lands on
B is the final PR merge (P11 opens it, P12 gates it), human-confirmed.

**WORK tier (when a phase fans out):** from the integration worktree, each parallel unit
(one module or work-item in P8 adapt) gets its OWN dedicated child worktree (delegated to
git-toolkit via `git-ops`) + branch off integration - a private git index for safe parallelism,
no `index.lock` race. When a child finishes, merge it back into integration (keeping SHA), then
remove it. The next phase recreates child worktrees from the updated integration. LOOP until done.

**Per-commit vs absorb-all.** The child-worktree fan-out above assumes integration HEAD
is COMMITTED between units (per-commit continuous, or one-shot) so a child forks from a clean
tree. For an **absorb-all** run that merges every source commit in ONE no-commit merge,
the conflicts are materialized in the integration worktree's WORKING TREE (uncommitted) - a child
worktree off the uncommitted integration HEAD cannot see them. In that mode do NOT fan out child
worktrees for conflict resolution: resolve serially, per module, DIRECTLY in the integration
worktree; child-worktree isolation resumes only once the absorbed merge is committed.

The only serialized point is converging children into integration + writing the source-merge
commit. Worktrees are filesystem isolation, not a second agent-dispatch level.

## The pipeline

**Dispatch-brief skeleton.** When composing the dispatch prompt for any specialist agent
dispatched across the phases below (`odoo-intent-extractor`, `odoo-diff-comparator`,
`odoo-installable-prober`, `odoo-test-writer`, etc.), fill the caller-side skeleton in
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` (read it by path) plus the target agent's family
delta; never inline that file verbatim into a hard-leaf brief.

Run phases in order. Intent + classify + design + the Plan Mode gate ALL precede the merge -
the plan is approved against the REAL triaged tiers and REAL buckets, never bucket-guesses.
Concurrency for any fan-out follows
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` (Mode B, model-weighted budget 8) -
do not restate the weight numbers here. Full per-phase dispatch briefs, git commands, and
worklog templates: `references/fp-phase-detail.md`.

**P0 - Recon & triage [read-only, NO stop].** Parse `$ARGUMENTS` (`source-ref` / `target-branch` /
`--scope` / `--since` / `--one-shot`); if `source-ref` or `target-branch` is missing, ask once in a
single brief message before any read or git op. Read any existing worklog
(`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`) and `checkpoint.json` (resume per the
Checkpoint section: skip ONLY `status=done`; do NOT re-run design for a `status=designed` commit -
resume it at the P4 plan gate with its recorded `design_doc`; a `status=extracted` commit resumes
at P2; a `status=adapted` commit resumes at P9). Invoke the `git-toolkit:git-ops` skill (via the
Skill tool) to enumerate commits (range `<merge-base>..<source-ref>`, --no-merges; read-only, no
worktree or branch yet); apply `--scope` / `--since` filters to the returned list. Map each
`--scope` module name to its directory path before requesting git-ops to filter by path (module `l10n_vn` ->
`l10n_vn/`; resolve via manifest location, may be at repo root or under an addons subdir).
TRIAGE each commit to an EXTRACT model tier INLINE (`git show --stat` + one `find_override_point` probe - the orchestrator
triages the tier itself; never dispatch an agent to decide a dispatch). This is recon only:
no approval gate, no worktree, no branch yet - the plan gate is P4, after intent + classify +
design. Triage tier table: `references/fp-triage-table.md`.

**P1 - Intent extract [PARALLEL, READ-ONLY].** Runs BEFORE the plan gate so the plan is built
on extracted intent, not a guess. This is the only true parallel speed-up - and it is honored
fully. Pre-step: invoke the `git-toolkit:git-ops` skill (via the Skill tool; read-only, no worktree)
in a single batch pass to write per-commit dump files - for each commit in the range, a full-patch
commit dump (message + diff) written to `.odoo-ai/forward-port/<slug>/commits/<sha>.dump`; collect
the `{ <sha>: <abs-path> }` map. Include `repo: <main-checkout-root>` in the git-ops dispatch for cross-repo ports. Each
extractor brief MUST include `commit_dump_path: <that path>` (the extractor mandates this field
and never runs git itself).
Dispatch one `odoo-intent-extractor` agent per commit using CHP Tier-B `subagent_type:
"fork"` (see `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` - Tier B), each
with its triaged `model` override, up to the Mode B budget (rolling window beyond it). A fork
worker inherits the parent's full context (slug, source-ref, target-branch, OSM version pin,
profile) and shares the parent's prompt cache, eliminating per-worker re-grounding cost. No
worktree children needed - extraction is read-only; Tier B applies unconditionally here.
Fallback (Tier C): if `subagent_type: "fork"` is unavailable, dispatch a fresh `general-purpose`
spawn with an explicit brief (current behavior) - the worklog is always written regardless of tier.
Each worker writes `.odoo-ai/forward-port/<slug>/intents/<sha>.md` (the why + behavioral contract +
OSM-grounded symbols, never the diff).
Aggregate the returned summaries into the P2 classify queue.

**P2 - Classify + installable-probe [per-commit, OSM].** For each commit, ground its symbols
against the TARGET version (`set_active_version` once, then `api_version_diff` + `model_inspect`)
and assign exactly one bucket a/b/c/d. SSOT: `[[fp-intent-4outcome]]`. Append one row per commit to
`merge-log.md`. `odoo-version-diff` in forward-port mode can supply the per-symbol bucket
suggestion. Every Odoo Semantic call carries `odoo_version=` - never omit it. Once buckets are
known, apply the **bucket-(c) upgrade-scale gate** to each bucket-(c) cluster: estimate its size
and, if it is an upgrade-scale re-implement rather than a mechanical port, RECORD the
`upgrade-scale` flag on that cluster now (`## Model triage`). Do NOT STOP at P2 - the defer-or-do
choice is PRESENTED to the user at the P4 plan gate, where the recorded flag becomes a
defer-or-do line in the plan. A `(b) do now` cluster that ALSO meets the P3 non-trivial criterion
proceeds to P3 design before P4 (the upgrade-scale gate decides WHETHER to proceed; P3 decides
HOW to design it).

In the same phase, determine each touched module's `installable` status using the TARGET
CLEAN-TIP rule (read the module's `installable` at the target BEFORE the merge, never
post-merge). DISPATCH the read-only sonnet leaf `odoo-installable-prober` ONLY when category-3 is
AMBIGUOUS - OSM returned `installable:True` at the target AND the module manifest was NOT touched
by the cherry-pick range, OR OSM was unreachable. Do NOT blanket-sweep every module: OSM already
grounds categories 1-2, so a probe there is wasted. Pre-step before dispatch: invoke the
`git-toolkit:git-ops` skill (via the Skill tool; read-only) to write two files - the clean-tip manifest (`<module>/__manifest__.py`
at `target_ref`) to `manifest_path = .odoo-ai/forward-port/<slug>/installable/<module>/manifest.py`,
and the patched manifest history (log-with-patch of manifest modifications against `source_ref`) to
`history_dump_path = .odoo-ai/forward-port/<slug>/installable/<module>/history.diff`. Include
`repo: <main-checkout-root>` in the git-ops dispatch for cross-repo ports. Dispatcher inputs
(canonical contract, pass exactly):
`{ module, repo_root, source_ref, target_ref, target_version, manifest_path, history_dump_path }`.
`repo_root` is the MAIN checkout root where git runs - the integration worktree does NOT exist at
P2 (it is created at P4); never reference it here. `source_ref` / `target_ref` are the source /
target git refs. `manifest_path` / `history_dump_path` are absolute paths to the surveyor-written
files (see pre-step above); the prober mandates both and never runs git itself.
The prober returns a `merge_log_line:` (logged VERBATIM to `merge-log.md`) PLUS a structured
verdict block; the verdict is its OWN row in `merge-log.md` keyed by module, distinct from the
per-commit intent/bucket/reason/evidence rows. A `tentative` verdict is carried to the P4 plan
gate as a FLAGGED row requiring human confirmation before that module's merge - NEVER silently
coerced to yes/no. Keep the installable:False short-circuit (`## Model triage`) and its lint-only
lane unchanged. Do not restate the rule here - SSOT: `[[fp-installable-false]]`.

**P3 - Design [conditional route-out].** When a bucket-(c) "do now" commit touches a NON-TRIVIAL
module (reuse the non-trivial criterion from `skills/odoo-solution-design/SKILL.md` § When to
invoke - do NOT invent a third definition), route OUT to `odoo-solution-design` instead of
adapting blind. A deferred or `installable:False` module needs no design - skip it. Mechanism:
emit the Continuation Contract and YIELD - forward-port only EMITS the next hop; the run-harness
advances it. Canonical payload (match exactly):
`next: odoo-solution-design`, `inputs: { return_to: odoo-forward-port,
design_slug_hint: <slug>-fp-<sha>, target_version: <series>, modules: [<names>],
intent_records: [<paths>], classification: <bucket-(c) summary> }`.
`odoo-solution-design` under `return_to` runs its own design + design-approval gate, then emits
`next: odoo-forward-port` with `design_doc`; it does NOT enter a code Plan Mode and does NOT
dispatch a coder. On re-entry, read `design_doc` from the returned contract's `inputs`, record it
against the commit, set checkpoint `status=designed`, and proceed to the P4 plan gate with the
design linked - do not re-run design. If `design_doc` is ABSENT from the returned inputs (design
crashed before producing it), set the commit back to `status=extracted` and re-enter P3 next run
rather than advancing to P4 with no design. SSOT for the full contract:
`references/fp-phase-detail.md` P3.

**P4 - Plan gate [Plan Mode].** This is where the user approves - AFTER intent + classify +
design, so the plan carries the REAL triaged tiers and REAL buckets, not guesses. Forward-port
runs from the MAIN context, so it MAY drive Plan Mode (a subagent cannot). The enter/exit
mechanics are the SHARED SSOT `${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Plan-Mode
enter/exit + plan_mode_active - forward-port REUSES them for its own approval gate rather than
defining its own: `EnterPlanMode` iff `plan_mode_active` is absent/false (skip iff a caller already
opened Plan Mode), present the plan, `ExitPlanMode` on approve so the user approves in the Plan Mode
UI. The plan CONTENT is forward-port-specific and stays authored here - it is NOT routed through
`odoo-planning`: commit topology; per-commit model tier [the real triaged tier]; bucket [the real
classification]; installable routing per module; design-doc link for any commit P3 designed; merge
batches. Red flags: a text-gate "approve" is NOT Plan Mode approval - they are two separate steps;
`EnterPlanMode` MUST come before any branch, worktree, or file touch.

After Plan Mode approval, invoke the `git-toolkit:git-ops` skill (via the Skill tool) to create the
JOB-tier integration worktree branched from B (Hard rule 1; dispatch contract: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`).
Supply the branch name `fp/<slug>`, path `<path>/fp-integration`, and base `<target-branch>` in the
brief. No branch is created before this point - everything up to and including the plan gate is read-only.

THEN write `.odoo-ai/forward-port/<slug>/plan.md` (commit topology + per-commit tier + bucket +
installable routing + design-doc links + merge batches) as the resume RECORD - the SSOT-of-record
that later phases and the checkpoint/continuation read. plan.md is now a RECORD, not the gate;
the gate is Plan Mode above. plan.md template: `references/fp-phase-detail.md` P4.

**P5 - Merge --no-commit [critical section, in integration].** Invoke the `git-toolkit:git-ops`
skill (via the Skill tool). Continuous: no-ff no-commit merge of `<src-SHA>`. One-shot: no-commit cherry-pick of
`<src-SHA>`. For semantic conflicts, use the stateless-resume recipe in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`. Only one merge in flight at a time
(shared git index). Do NOT commit yet - the working tree is now the absorption zone
(P6 -> P8 -> P9 all happen before the commit). SSOT: `[[fp-merge-absorption]]`.

**P6 - Symbol-survival check [MUST].** Before any adapt, OSM-ground every source-side symbol
in conflicted AND merge-clean-but-source-touched files against the target surface. Any symbol
absent/changed at target FORCES the commit into bucket b/c/d and BANS leaving the auto-merged
line unchanged. This catches the autosilent field-break (no conflict marker, runtime crash).
SSOT: `[[fp-symbol-survival-check]]`.

**P6 TEST-survival sub-check [MUST - after the production symbol check].**
Also ground test coverage to detect test code referencing a field/model symbol removed at target
(git auto-merge leaves no conflict marker, so the break is autosilent at test time). For each
model/field touched, call `tests_covering(model='<model>', odoo_version='<target_version>')`
(optional `field='<field>'` narrows). For a whole-module commit, supplement with
`test_coverage_audit(module='<module>', odoo_version='<target_version>')` (field-level only; for
per-method coverage use `tests_covering(model='<model>', method='<method>', odoo_version='<version>')`,
which is sparse). `tests_covering` does not compare cross-version - before concluding a test is
broken, CONFIRM the symbol is absent at target via
`model_inspect(model='<model>', method='fields', odoo_version='<target_version>')`. Test methods
referencing a symbol absent at target MUST be triaged into the same bucket (not forwarded
verbatim). Record every broken test-symbol reference in the `merge-log.md` per-commit row; the
P8a adapt brief MUST include this list.

**P7 - Pre-adapt drift scan [MUST, before the behavioral loop].** Distinct from P6:
P6 catches OSM-indexed symbol-graph breaks (cross-version via index); P7 catches static
grep / import / AST breaks via two lanes: classes (d)(e)(g) run over ALL merged-touched `.py`
(production AND `tests/`) - (d)(e) catch runtime NameError and (g) catches an autosilent
ORM Invalid-field key before P9; the remaining classes (a)(b)(c)(f) and the collection
ACCEPTANCE GATE apply over `tests/` only.
Enumerate every symbol, file path, import, and test-base-class the merged code touches (Lane 1
production AND tests; Lane 2 tests only); triage each finding into a bucket (b adapt /
c re-implement / d drop) - never leave an auto-merged line referencing a dead symbol.
**ACCEPTANCE GATE:** merged test files MUST import and collect cleanly on the target
(`python -m pytest --collect-only` or `odoo-bin ... --test-enable` collection) before any
red-then-green adapt starts. A `setUpClass` crash means tests never ran, so a green count from
P9 is a false pass (`0 failed, N error(s)` is NOT a passing result). Record findings in
`merge-log.md`; P8a brief consumes them. SSOT: `[[fp-symbol-survival-check]]`.
Full commands: `references/fp-phase-detail.md` P7.

**P8 - Adapt [test-first; SERIAL per-module within a commit; SERIAL across commits].** For each touched module/WI,
spawn an adapt unit in its own child worktree off integration (worktree per module for filesystem isolation).

**CRITICAL - open merge window:** During the open P5 merge window of the CURRENT source commit -
after git-ops ran `--no-commit` and before git-ops runs the P10 `commit` - `MERGE_HEAD`
is live in the integration worktree. Git will reject any second merge in that worktree until
the first is committed or aborted. Therefore: adapt all modules SERIALLY DIRECTLY in the
integration worktree during this window - do NOT create child worktrees. Child-worktree fan-out
(the WORK-tier described in `## Git topology`) is ONLY valid when the integration HEAD is already
committed, i.e. when processing a SUBSEQUENT source commit after the previous P10 commit has
closed the prior merge. SSOT for the in-window adapt protocol: `[[fp-merge-absorption]]`
§Absorption-window.

Run the CHP capability probe once (per `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md`
- Capability probe) before the first P8 adapt dispatch, and cache the result for every P8 dispatch
in this run - this tells the orchestrator up front whether Tier-A is available at all.
When the CHP capability probe is positive (Agent Team mode on), TaskCreate one task per dispatched
work-item, inject TASK_ID + REPLY_TO: main + NOTIFY: <dependent names> into each teammate brief,
poll TaskList/TaskGet for status, and read each result from the teammate's SendMessage push (NEVER
from the .output transcript) - per `${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md`. When
off, dispatch + collect as today.

CHP Tier-A (SendMessage-resume) applies to the P8a test-forward worker (`odoo-test-writer`, which
authors by invoking the `odoo-test-writing` skill inline) / P9 verify cycle: after 8a+8b and the
merge back to integration, P9 may reveal a failing test. For the TEST worker, instead of spawning a
cold fresh one for the re-adapt, resume the SAME `odoo-test-writer` worker via `SendMessage` (see
`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` - Tier A), sending it the P9 failure
output. The worker keeps its full prior context (intent record, bucket, worktree path) - far
cheaper than rebuilding from a brief. Structure the exchange as async park-and-be-resumed: send
the P9 failure output, end your turn, and wait to be resumed when the worker's reply arrives. On
resume the worker MUST immediately `cd` to its child worktree path before any Bash command (the
shell cwd is NOT guaranteed to be restored across resume - see the CHP snippet "Tier-A workers in
a git worktree - cd on resume"). Assign each such worker a stable `name` (e.g.
`adapt-<slug>-<module>`) when spawning it and record the returned `agentId` in `plan.md` keyed by
module. The 8b CODE re-adapt is a fresh `odoo-coding` invocation (via the Skill tool) carrying the
P9 failure output; `odoo-coding` owns the coder fan-out and any internal coder resume via its own
context-handoff protocol - the forward-port orchestrator never resumes raw coders itself.
Fallback (Tier C): if the capability probe is negative (env unset, `SendMessage` absent, or probe
signals the orchestrator is not the team lead), re-invoke the `odoo-coding` skill (code re-adapt)
and/or spawn a fresh `odoo-test-writer` agent (test re-adapt) with an explicit brief containing
the P9 failure output. Tier C is always correct; the worklog is always written regardless of tier.

- **8a forward the test FIRST** by launching the `odoo-test-writer` agent (adapt mode; it invokes the `odoo-test-writing` skill inline). Adapt the MERGED SOURCE
  TEST to run on the target - translate API to the target idiom (base class, imports, helper
  signatures per P7), strip implementation-coupled assertions, confirm it goes RED. Do NOT
  author a brand-new test from scratch: the forwarded source test IS the oracle; 8a adapts it
  to run. Only when the source commit shipped NO test does the agent write one - anchored to
  the source intent record, not improvised.
  Build an FP-ENRICHED brief carrying a named **Child worktree path: `<absolute path>`** field
  (the worker's own child worktree off integration - the same path the orchestrator created for
  this module/WI), plus:
  (0) **cd-on-resume (HARD RULE - Tier-A):** On resume via `SendMessage`, immediately `cd` to the
  Child worktree path listed in this brief before running any Bash command. Shell cwd is NOT
  guaranteed to be restored across a SendMessage-resume; the explicit `cd` makes Tier-A re-adapt
  safe regardless of runtime behavior. Apply this on every resume, not only the first;
  (i) **base class grounding** - call `test_base_classes(odoo_version='<target_version>')` to
  confirm the correct base class (`SavepointCase` deprecated alias from v8-v15, should adapt to
  `TransactionCase`; `cr.commit()` FORBIDDEN in all test cases); attach the output so the agent
  uses target-native idiom;
  (ii) **test examples at target** - call `find_test_examples(query='<feature_or_model>', odoo_version='<target_version>')`
  (optional `model='<model>'`; for kind: `'transaction'`|`'http'`|`'form'`; `kind='js'` only
  for JS tests - `kind='python'` is NOT valid) and attach the top examples as concrete templates;
  (iii) **broken test-symbol list** from P6 test-survival - adapt agent must rewrite or drop
  every test assertion referencing a symbol removed at target.
- **8b adapt the code** per bucket by invoking the `odoo-coding` skill (via the Skill tool) -
  `odoo-coding` owns the backend/frontend split, coder fan-out (via its `odoo-coder` per-module
  coordinator), model, and synthesis (do NOT dispatch raw `odoo-coder`, `odoo-backend-coder`, or
  `odoo-frontend-coder`) -
  with an FP-ENRICHED brief = the named **Child worktree path: `<absolute path>`** field
  + the same **cd-on-resume (HARD RULE - Tier-A)** item as 8a + intent record + bucket + the failing
  test + the installable:False checklist + `MANIFEST/MIGRATION/PROVENANCE: apply C1 (keep TARGET
  version on conflict, never bump), C2 (migration-dir retarget), C3 (carry pre-existing source bugs
  faithfully, do not inline-fix) - [[fp-merge-absorption]]`. Bucket (a)/(d): no adapt code.
  Bucket (b): 3-way merge + adapt. Bucket (c): re-implement on the target idiom. The frontend leg
  additionally grounds any ported OWL/QWeb/SCSS against `skills/_shared/odoo-frontend-fidelity.md`
  so the forwarded UI stays on-theme and design-system-correct for the target version.
- **8c installable:False modules** - two sub-cases, same manifest action:
  (i) **New module** (absent at target): set `installable: False` + comment `auto_install`/
      `application`, lint-fix only.
  (ii) **Upgraded-then-forwarded** (pre-existing at target with `installable:False` at clean-tip,
      but merge carries `installable:True`): re-set to False + re-comment `auto_install`/
      `application` with breadcrumb - then lint-fix only.
  Both land in the LINT-ONLY lane. SSOT: `[[fp-installable-false]]`.
- **8d migration script**: retarget a forwarded `migrations/<src-series>.a.b.c/` dir to the target
  series per C2 (default: name it FULL `<tgt-series>.V` so it fires on a deployed target DB at manifest
  `M`; bump the manifest only in the `S<=M` case; legacy source-only data fix keeps `<src-series>.a.b.c`).
  This is a migration-threshold action, NOT a conflict-resolution version bump (C1). Full rule +
  `adapt_version` silent-skip WHY: `[[fp-merge-absorption]]`.
Converge each child worktree back to integration (serialized) - the converge-back stays
serialized, one in-flight at a time. Do NOT remove the child worktree at converge-back time:
under Tier-A the adapt -> verify -> (re-adapt on failure) cycle for that module may resume the
SAME worker, which `cd`s back into its still-existing child worktree, so the worktree MUST persist
through the whole cycle. Remove a module's child worktree only AFTER that module's cycle is
confirmed done (P9 GREEN for that module's batch); a worktree removed before P9 verify would leave
a Tier-A re-adapt worker `cd`-ing into a deleted path.

**P9 - Verify by behavior [PER-BATCH, in integration].** DELEGATE the run - do NOT allocate a DB +
port and run the full suite inline. A full per-batch suite is exactly the case the test-execution
handoff contract reserves for the executor: its output is large (test log, tracebacks) and would flood
this orchestrator's context, and running it here folds the executor role into the conductor. SSOT:
`${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`. Dispatch `odoo-instance` (via the Skill tool;
L2 human gate applies) - the same delegation `odoo-modules-upgrade` P5 and `odoo-git-rebase` P10 use:
provision the cluster ONCE, then per batch dispatch init for the N affected modules followed by
run-tests of the target suite, relaying the returned `INSTANCE_HANDLE` so later batches reuse the same
instance instead of self-provisioning (`odoo-instance-ops` resolves odoo-bin flags per series via
`cli_help`, performs Odoo create-on-init, and drops the DB through Odoo on release). The executor
returns a structured result block (per-test pass/fail + the instance log path), NOT the raw firehose.
From that block THIS skill stays the adjudicator of FP intent: RED-then-GREEN for the whole module +
confirm-by-toggle for FP-delta tests only, triaging each red test as FP-delta vs pre-existing (re-run it
on clean target tip via the same executor). Never relax an assertion to hide a pre-existing failure.
Full per-batch + CREATEDB-role protocol (CREATEDB still required - Odoo create-on-init needs the same
privilege): `[[fp-merge-absorption]]`. Instance lifecycle and test invocation conventions:
`docs/reference/INSTANCE-LIFECYCLE.md` and `docs/reference/ODOO-TESTING.md`.

**P10 - Gate merge [STOP, per batch].** Emit `merge-log.md`, present it, wait for human-confirm.
On confirm: invoke the `git-toolkit:git-ops` skill (via the Skill tool) to commit the merge (buckets a/d still commit - Hard rule 7), update
`checkpoint.json` `{<sha>: done}`. More commits/batches remain -> LOOP to P5: each subsequent
commit re-runs the full per-commit cycle P5 merge -> P6 symbol-survival -> P7 drift -> P8 adapt
(recreating WORK-tier worktrees from integration), with P9 verifying the adapted batch and P10
gating it. Never loop straight to P8 - that would absorb the next commit without a merge or a
symbol/drift check.

**P11 - PR + review.** Push `fp/<slug>` (invoke `git-toolkit:git-ops`; resolve origin URL via
`git remote get-url origin`), then open PR (invoke `git-toolkit:git-ops`). Run `odoo-code-review`
inline (via the Skill tool, from this orchestrating context) passing `TARGET: worktree:<path>/fp-integration` (the
JOB-tier integration worktree created at P4 - `<path>` is the base path passed to git-ops at P4)
so the skill reviews the fp integration tree, not the principal tree. It is OPTIONAL for a trivial port
(docstring/string/comment-only buckets), but
**MANDATORY whenever the batch grafts a new engine or mechanism** (a shared report engine, a
group-by/total/drill computation, an export/print path, a wizard, any multi-path component) -
a clean merge of one path proves nothing about the others. For a mandatory review:

1. **Enumerate EVERY code path of the grafted mechanism and confirm each was adapted.** A report
   or compute engine typically fans out into: total, sub-total/group-by, expand/collapse, drill
   -down, export (xlsx/csv), and print (PDF/QWeb). List each path and verify the forward-port
   adapted it - a path the source touched but the adapt missed is a silent partial port that
   passes the headline test while a sibling path renders wrong. The review is not done until
   every enumerated path is accounted for (adapted, or explicitly N/A with a reason).
2. **Cross-check every static-review bot comment on the PR.** After the PR opens, read the bot
   (CI linter / review bot) comments and resolve or consciously waive each - a bot comment on a
   forward-ported line is signal that an auto-merged construct did not survive the target.
3. **Attribution diff before rating any finding.** A finding only belongs to THIS port if
   it sits on a line this port changed. Invoke the `git-toolkit:git-ops` skill (via the Skill tool) for a three-dot diff
   (`origin/<target-branch>...fp/<slug>`) and attribute each finding to either a
   forward-ported line (in scope, fix now) or a pre-existing target line (out of scope, do not
   re-rate the target's own debt as a port regression). Rate findings only after this attribution.

A module that is `installable:False` at the target is in the lint-only lane (`[[fp-installable-false]]`):
the reviewer rates ONLY lint/syntax for it and MUST NOT raise a business-logic finding (its
behavior is intentionally not forward-ported - see `## Model triage`).

**Acceptance hand-off (consumption clause).** The `odoo-code-review` dispatch above may carry a
`next: odoo-acceptance` entry in its Continuation Contract (Phase A.5 emits this whenever
`render_check_set` reaches beyond the reviewed modules). READ it, but do NOT act on it here - it is
superseded by the single cluster-wide dispatch P12 runs below.

NEVER squash (keeps SHA). B stays LOCKED - the PR only adds the merge commits.

**P12 - End-to-end acceptance (odoo-acceptance) stage [MANDATORY, cluster-wide, narrow escape
only].** Goal: prove the forward-ported batch works end-to-end on a real running instance/UI
across its blast-radius - the SAME acceptance rigor new-module development applies, so a
forward-port is not held to a lighter bar just because it moves existing behavior. P9's per-batch
verify-by-behavior proves RED-then-GREEN + confirm-by-toggle for the ported intent tests; it does
NOT prove the touched cluster behaves correctly for a real user across roles/state/search -
closing that gap is this stage's job. This is a DIFFERENT concept from the P7 pre-adapt drift-scan
**ACCEPTANCE GATE** (the test-collection sanity check that merged test files import and collect
cleanly, `references/fp-phase-detail.md:335`) - deliberately named differently so the two are never
conflated.
Compute the verify scope by invoking `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md` over
every module touched across the batch (from `merge-log.md`) - forward-port has no pre-built
dependency DAG file the way `odoo-modules-upgrade` does, so this pass derives the reverse-closure
directly via OSM `impact_analysis` per that snippet's Step 1.
Invoke the `odoo-acceptance` skill (via the Skill tool) ONCE for the whole batch (never per commit
or per module). Fill the dispatch brief per `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md`
(read it by path): `INPUTS` = the touched module set from `merge-log.md`, `scope_hint` =
`merge-log.md` + `intents/<sha>.md`, `odoo_version` = target series; `INSTANCE_HANDLE` from P9 if
still live (reuse - never re-provision; else pass `none provisioned` and `odoo-acceptance` still
scopes + plans its oracle, then emits `NEEDS_NEXT -> odoo-instance`). `ACCEPTANCE` (by pointer) =
each ported commit's behavioral contract recorded in `intents/<sha>.md` and any P3 design doc's §9
- NEVER a pre-built oracle: `odoo-acceptance` authors its OWN independent oracle at its own
Phase 1 from that intent, the same oracle-independence guarantee the new-module lifecycle
protects. Do NOT hand it the implementation.
**MANDATORY - narrow escape only.** A forward-ported batch's touched modules have in-cluster
dependents by construction whenever they carry shared/depended-on symbols, so the blast-radius
bar this stage exists for is met almost always - this is NOT an opt-in hand-off. Skip it ONLY when
the touched set is a true dependency leaf with ZERO in-repo dependents AND no behavioral surface
(no views, no models any other module consumes) - record that proof explicitly in `merge-log.md`;
never skip silently. **The forward-port is not DONE until this stage returns ACCEPTED (PASS), or
the narrow-escape condition above is explicitly met and recorded.**
Gate tier: L2 (human) - present the acceptance verdict (or the recorded narrow-escape) ALONGSIDE
the human-merge decision below so the human sees ONE combined gate, not a surprise extra step
after merge is already requested.
Output: `.odoo-ai/qa/<slug>-acceptance-report.md` (`odoo-acceptance`'s own artifact), referenced
from `merge-log.md`.

Wait for human merge.

## Model triage - two tier tables

**installable:False short-circuit.** Before assigning ANY tier, check each touched
module's `installable` flag at the target (`module_inspect(name='<module>', method='summary',
odoo_version='<target>')` or read the target `__manifest__.py`). A module that is
`installable:False` at the target - a brand-new module not yet landed, OR a pre-existing dormant
one - is NOT forward-ported for behavior: route it to the **lint-only lane** (flake8 / pylint /
eslint / prettier / ruff to green CI, minimum fix only) and SKIP the extract/adapt/review logic
tiers entirely. Its business logic is not adapted and P11 review rates only its lint/syntax, never
a business finding. SSOT: `[[fp-installable-false]]`.

**Bucket-(c) upgrade-scale gate.** Bucket (c) is "re-implement on the target idiom" - but
that one bucket covers a 3-line call-site fix and a 500-line component rewrite alike, and the
ADAPT tier below only picks the MODEL, not whether the work is even a mechanical port. After P2
classify, estimate each bucket-(c) cluster's adapt size (source LOC delta + framework-migration
flag). If it exceeds ~200 LOC of new OWL/JS OR is a full component/framework rewrite, it is an
upgrade-scale RE-IMPLEMENT, not a mechanical port: RECORD the `upgrade-scale` flag at P2 and
PRESENT the defer-or-do choice at the P4 plan gate - (a) defer (carry `installable:False`,
lint-only lane) or (b) do now (estimate effort, adapt at the ADAPT-table tier). Never silently
absorb unbounded re-implement work; default on no answer is defer. SSOT:
`references/fp-triage-table.md` § Bucket-(c) upgrade-scale gate.

Triage is INLINE and deterministic, run twice with different tables:

- **EXTRACT tier (P0 -> P1 intent extraction):** haiku for docstring/comment/string-only
  commits, sonnet for logic commits, opus for migration/cross-module commits. **fable is NOT
  in the EXTRACT band** - intent extraction is read-only analysis, never worth fable cost.
- **ADAPT tier (P8 code adapt):** follow the `odoo-coding` deterministic tier table
  (haiku/sonnet/opus/fable, sonnet default, fable always needs explicit human confirmation).

Resolve a tier by walking each table top-down, first match wins. Full both-table detail with
per-row conditions: `references/fp-triage-table.md`. Record every chosen tier in `plan.md` - a
tier is part of the approved plan, not a runtime improvisation.

The two tiers are decided INDEPENDENTLY - never reuse one tier as the other. Run the EXTRACT
table at P0->P1 and the ADAPT table at P8 against each table's own conditions; a docstring-only
commit may be haiku to EXTRACT but opus to ADAPT if the target re-implementation is cross-module.

## Two modes

- **Continuous (default).** Recurring; merge keeps SHA; `checkpoint.json` skips done commits and
  never re-resolves a past conflict.
- **One-shot (`--one-shot`).** Port one frozen batch once via a no-commit cherry-pick (delegated
  to git-toolkit via `git-ops`); every other phase is identical.

## Checkpoint / resume

`.odoo-ai/forward-port/<slug>/checkpoint.json` maps
`{<sha>: extracted | designed | adapted | verified | done}`, with `designed` carrying the
`design_doc` path for any commit P3 routed to `odoo-solution-design`. P0 reads it and skips
`status=done` commits (and resumes a `status=designed` commit at the P4 plan gate with its
recorded `design_doc`, so a crash between design-approval and re-entry resumes correctly). A
crash mid-batch is recovered by re-reading the checkpoint + the on-disk `intents/`, `plan.md`,
and `merge-log.md` (file existence is the source of truth, the JSON is the fast index). Child
worktrees left dangling by a crash are removed and recreated from integration. Record the executor's
`INSTANCE_HANDLE` (and its instance log path) in the batch worklog so a resumed run reuses the same
instance or asks `odoo-instance` to release it instead of orphaning the DB - since P9 delegates the run,
the instance lifecycle is owned by `odoo-instance-ops`, not held as an allocator lease in this skill.

## Frontend / i18n / data-XML caveats

Forward-port adds platform-drift classes a pure-Python port misses - flag and route each:

- **Frontend (JS/OWL/SCSS).** Asset-bundle keys drift across series and OWL moved from the legacy
  `web.Widget` / `odoo.define()` era to OWL 2.x `patch()` / `useState` / `useService`. Route a
  frontend adapt commit to `odoo-coding` (its frontend leg owns both eras) - never hand-translate
  OWL from memory.
- **i18n (.pot / .po).** Do NOT hand-port or re-export translation files in this pipeline. When a
  forwarded commit touches `.po`/`.pot` or adds translatable strings, DISPATCH the `odoo-i18n`
  skill after the code adapt - it owns the non-destructive `.pot`/`.po` recipe and validates the
  result. Pass it the source `.po` paths, the target modules, the target `odoo_version`, and the
  source series. Full dispatch wiring: `references/fp-phase-detail.md`.
- **Data XML (`noupdate` records).** A source data record may reference an external-id that does
  not resolve at the target. After merge, verify every external-id in touched data XML resolves
  on the target (P6 covers `ref()` / `xml_id`); a `noupdate="1"` record will not be
  re-written, so a broken ref is permanent until fixed here.

Three more cross-cutting checks apply per batch:

- **Multi-repo env bootstrap.** When source and target live in different repos/clones, bring
  the source ref into reach (invoke `git-toolkit:git-ops`: add source remote + fetch) BEFORE computing
  the merge-base or merging; a forward-port across repos that skips this silently merges against a
  stale local ref. Detail: `references/fp-phase-detail.md`.
- **Manifest version & migration dir.** Forward-port carries the source manifest AS-IS and NEVER
  auto-bumps `version`: on a `__manifest__.py` conflict keep the TARGET file's value (C1). A forwarded
  `migrations/` dir is RETARGETED to the target series (C2) - a dir rename with a threshold-driven
  version, NOT a "diff-touched-a-file" bump. C1 and C2 are distinct; apply both. SSOT:
  `[[fp-merge-absorption]]`.
- **Field-label grounding.** When the port renames or re-labels a field, confirm the
  target's canonical label before adapting -
  `entity_lookup(kind='field', model='<model>', field='<field>', odoo_version='<target>')` - so the
  forwarded string matches the target's own term. Detail: `references/fp-phase-detail.md`.

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
- `entity_lookup` ★ - Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `find_override_point` - Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior.
- `find_test_examples` - Semantic search for Odoo test code examples (test_method, test_class, js_test chunks only - never returns production code).
- `test_base_classes` - Menu of official Odoo test framework base classes (TransactionCase, HttpCase, SavepointCase, Form, etc.) for the given version, with test_type and cursor contract.
- `test_coverage_audit` - Audit an entire module for test coverage gaps: lists fields/methods with zero COVERS_* edges (never referenced by any test).
- `tests_covering` - List test methods that have COVERS_MODEL/COVERS_FIELD/COVERS_METHOD edges to the target model or field (static reference coverage, not runtime executed coverage).
<!-- END GENERATED TOOLS -->

## Standalone-first fallback

When Odoo Semantic (the odoo-semantic-mcp server) is unreachable, the pipeline degrades but
does not stop. P1 intent extractors fall back to local-source reads
(`${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md`), labelling each record
`grounded: local-source (not OSM-indexed)`. P2 classify and P6 symbol-survival
fall back to disk reads of the target checkout per
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md` (read each `__manifest__.py`
`depends` and the model/field source) - the symbol-survival guarantee still holds via grep on
the target source, only the grounding citation changes. `odoo-version-diff` standalone mode
supplies the version delta from GitHub release notes when the index is down. Never ask a human
to paste code, field lists, or manifests; the merge SHA-preservation and verify-by-behavior
contracts are unchanged - only the grounding source degrades.

## Continuation Contract

When the run finishes (or pauses at a gate), append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next).
`produced` lists `plan.md`, `intents/<sha>.md`, `merge-log.md`,
`.odoo-ai/qa/<slug>-acceptance-report.md`, `checkpoint.json`, and the PR
URL; `next` is the human-confirm gate (P10, P11, or P12 merge). When P3 routes a commit out to design,
`next: odoo-solution-design` with canonical payload
`{ return_to: odoo-forward-port, design_slug_hint: <slug>-fp-<sha>, target_version: <series>,
modules: [<names>], intent_records: [<paths>], classification: <bucket-(c) summary> }` and the
run YIELDS - the run-harness advances the hop and re-enters forward-port with the returned
`design_doc`. Additive output for the run-harness - it does not change anything produced above.
