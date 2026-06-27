---
name: odoo-forward-port
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

## Persona

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
- Single-WI parallelism with cherry-pick + squash semantics -> use `wave` (forward-port
  keeps SHA by merge; `wave` re-bases by cherry-pick - different git contract)

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

Parse these from `$ARGUMENTS` in P0; if `source-ref` or `target-branch` is missing, ask
once in a single brief message before any read or git op.

### When to use

- **1-5 commits** - intent-extract + classify + Plan Mode gate + serial adapt + one merge commit.
- **6+ commits** - full plan (commit topology, per-commit model tier, buckets) presented in
  Plan Mode and recorded to `plan.md`, with a human-confirm gate per merge batch.
- **Continuous mode (default)** - recurring; source keeps evolving; SHA preserved so the
  merge-base advances and past conflicts are never re-resolved.

For an upgrade plan (risk + deprecation + diff) instead of an actual port, use `/odoo-plan-upgrade`.

### Examples

```
/odoo-forward-port origin/17.0 origin/18.0 --scope l10n_vn,l10n_vn_viin --since abc1234
```
Recon: 3 commits, scope 2 modules, Sonnet tier. Then 3 parallel read-only intent extractions
-> classify + installable-probe -> conditional design route-out -> Plan Mode gate (user
approves) -> merge --no-commit -> symbol-survival check -> serial per-module adapt (worktree
per module) -> verify-by-behavior (red-then-green) -> GATE MERGE -> merge commit -> checkpoint.

```
/odoo-forward-port origin/17.0 origin/18.0 --one-shot
```
One-shot cherry-pick for a single frozen batch; same intent-extract -> classify ->
symbol-survival -> adapt -> verify -> gate flow, cherry-pick instead of merge.

```
/odoo-forward-port
```
Prompts for source-ref and target-branch, then the same flow.

## Hard rules

1. **Target-branch-lock** - NEVER checkout, switch, commit, merge, rebase, reset, or push the
   target branch B directly. Another session may hold B's working tree. All integration happens
   in a dedicated integration worktree branched FROM B (the JOB tier below). Read-only ops on
   B are allowed. Delegate every mutation on the integration worktree to git-operator
   (`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`).

2. **Keep the source SHA (continuous)** - continuous forward-port uses a no-ff no-commit
   merge (delegated to git-operator; see `[[fp-merge-absorption]]`) so the source commit
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

6. **Human-confirm merge** - STOP at the P10 gate. The P4 plan gate runs in harness Plan Mode
   (user approves in the Plan Mode UI). No automated commit of the integration into B, no
   auto-merge of the PR. Present and wait.

7. **Outcome a/d still merge** - buckets (a) already-satisfied and (d) no-longer-relevant
   produce no adapt diff but STILL create the merge commit (keeps SHA, advances merge-base).
   Skipping the merge for them re-encounters the commit tomorrow. SSOT: `[[fp-merge-absorption]]`.

8. **Verify subagent claims** - never trust a leaf's self-report of GREEN. Run the verify
   command yourself per batch (P9) before the P10 gate.

## Git topology - two tiers of worktree

Forward-port never touches B directly and parallelizes through worktree isolation.

**JOB tier (always):** create `fp/<slug>` integration branch via dedicated worktree (delegated
to git-operator) from B's HEAD. All absorption, adapt, and verify happen inside this integration
worktree. The target branch B is read-only for the whole run; the only thing that ever lands on
B is the final PR merge (P11), human-confirmed.

**WORK tier (when a phase fans out):** from the integration worktree, each parallel unit
(one module or work-item in P8 adapt) gets its OWN dedicated child worktree (delegated to
git-operator) + branch off integration. Each adapt subagent works in its child worktree (a
private git index -> safe parallelism, no `index.lock` race). When a child finishes, the
orchestrator brings it back into integration by merge (keeping SHA), then removes the child
worktree. The next phase recreates child worktrees from the updated integration. LOOP until
phases are done.

**Per-commit vs absorb-all.** The child-worktree fan-out above assumes integration HEAD
is COMMITTED between units (per-commit continuous, or one-shot) so a child forks from a clean
tree. For an **absorb-all** run that merges every source commit in ONE no-commit merge,
the conflicts are materialized in the integration worktree's WORKING TREE (uncommitted) - a child
worktree off the uncommitted integration HEAD cannot see them. In that mode do NOT fan out child
worktrees for conflict resolution: resolve serially, per module, DIRECTLY in the integration
worktree; child-worktree isolation resumes only once the absorbed merge is committed.

The only serialized point is converging children into integration + writing the source-merge
commit. Worktrees provide filesystem isolation, not a second agent-dispatch level - no nested
agent dispatch.

## The pipeline

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
at P2; a `status=adapted` commit resumes at P9). Delegate commit enumeration to git-surveyor
(range `<merge-base>..<source-ref>`, --no-merges; read-only, no worktree or branch yet);
apply `--scope` / `--since` filters to the returned list. Map each `--scope` module name to
its directory path before requesting git-surveyor to filter by path (module `l10n_vn` ->
`l10n_vn/`; resolve via manifest location, may be at repo root or under an addons subdir).
TRIAGE each commit to an EXTRACT model tier INLINE (`git show --stat` + one `find_override_point` probe - the orchestrator
triages the tier itself; never dispatch an agent to decide a dispatch). This is recon only:
no approval gate, no worktree, no branch yet - the plan gate is P4, after intent + classify +
design. Triage tier table: `references/fp-triage-table.md`.

**P1 - Intent extract [PARALLEL, READ-ONLY].** Runs BEFORE the plan gate so the plan is built
on extracted intent, not a guess. This is the only true parallel speed-up - and it is honored
fully. Pre-step: dispatch git-surveyor (read-only, no worktree) in a single batch pass to write
per-commit dump files - for each commit in the range, a full-patch commit dump (message + diff)
written to `.odoo-ai/forward-port/<slug>/commits/<sha>.dump`; collect the `{ <sha>: <abs-path> }`
map. Include `repo: <main-checkout-root>` in the git-surveyor dispatch for cross-repo ports. Each
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
grounds categories 1-2, so a probe there is wasted. Pre-step before dispatch: delegate to
git-surveyor (read-only) to write two files - the clean-tip manifest (`<module>/__manifest__.py`
at `target_ref`) to `manifest_path = .odoo-ai/forward-port/<slug>/installable/<module>/manifest.py`,
and the patched manifest history (log-with-patch of manifest modifications against `source_ref`) to
`history_dump_path = .odoo-ai/forward-port/<slug>/installable/<module>/history.diff`. Include
`repo: <main-checkout-root>` in the git-surveyor dispatch for cross-repo ports. Dispatcher inputs
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
emit the Continuation Contract and YIELD - forward-port only EMITS the next hop; the run-driver
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
runs from the MAIN context, so it MAY call `EnterPlanMode` / `ExitPlanMode` (a subagent cannot).
Procedure: the main agent calls `EnterPlanMode`; writes the implementation plan inside Plan Mode
(commit topology; per-commit model tier [the real triaged tier]; bucket [the real classification];
installable routing per module; design-doc link for any commit P3 designed; merge batches); calls
`ExitPlanMode`; the user approves in the Plan Mode UI. Red flags: a text-gate "approve" is NOT
Plan Mode approval - they are two separate steps; `EnterPlanMode` MUST come before any branch,
worktree, or file touch.

After Plan Mode approval, delegate to git-operator: create the JOB-tier integration worktree
branched from B (Hard rule 1; dispatch contract: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`).
Supply the branch name `fp/<slug>`, path `<path>/fp-integration`, and base `<target-branch>` in the
brief. No branch is created before this point - everything up to and including the plan gate is read-only.

THEN write `.odoo-ai/forward-port/<slug>/plan.md` (commit topology + per-commit tier + bucket +
installable routing + design-doc links + merge batches) as the resume RECORD - the SSOT-of-record
that later phases and the checkpoint/continuation read. plan.md is now a RECORD, not the gate;
the gate is Plan Mode above. plan.md template: `references/fp-phase-detail.md` P4.

**P5 - Merge --no-commit [critical section, in integration].** Delegate to git-operator.
Continuous: no-ff no-commit merge of `<src-SHA>`. One-shot: no-commit cherry-pick of
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
After production symbol check, also run test-coverage grounding to detect test code that
references a field or model symbol removed at the target version (git auto-merge produces no
conflict marker, so this break is autosilent at test time, not just at runtime). For each model
or field touched by the commit, call `tests_covering(model='<model>', odoo_version='<target_version>')`
(also accepts optional `field='<field>'` to narrow). If the tool returns test methods that
reference a symbol NOT present in the target `model_inspect` output, those test methods
reference a deleted symbol and MUST be triaged as part of the same bucket assignment - they
cannot be forwarded verbatim. When a broader audit is needed (e.g. the commit touches an
entire module), supplement with `test_coverage_audit(module='<module>', odoo_version='<target_version>')`
to surface fields with zero COVERS edges at target (field-level only; method gaps are NOT
reported by this tool - for per-method coverage use `tests_covering(model='<model>', method='<method>',
odoo_version='<version>')`, which is sparse and may return 0 edges even for tested methods).
After `tests_covering` returns a list of test methods referencing field X at target, CONFIRM X
is absent at target before concluding those tests are broken candidates: call
`model_inspect(model='<model>', method='fields', odoo_version='<target_version>')` - only if X
is absent in that output are the test methods broken; `tests_covering` does not itself compare
cross-version. Record all broken test-symbol references in the per-commit row of
`merge-log.md` alongside the production symbols. The P8a adapt brief MUST include this list.

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
after git-operator ran `--no-commit` and before git-operator runs the P10 `commit` - `MERGE_HEAD`
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

CHP Tier-A (SendMessage-resume) applies to the P8 adapt worker / P9 verify cycle: after the
adapt worker finishes 8a+8b and the merge back to integration, P9 may reveal a failing test.
Instead of spawning a cold fresh worker for the re-adapt, resume the SAME adapt worker via
`SendMessage` (see `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` - Tier A),
sending it the P9 failure output. The worker keeps its full prior context (intent record, bucket,
worktree path, partially adapted code) - far cheaper than rebuilding from a brief. Structure the
exchange as async park-and-be-resumed: send the P9 failure output, end your turn, and wait to be
resumed when the worker's re-adapt reply arrives. On resume the worker MUST immediately `cd` to
its child worktree path before any Bash command (the shell cwd is NOT guaranteed to be restored
across resume - see the CHP snippet "Tier-A workers in a git worktree - cd on resume"). Assign
each adapt worker a stable `name` (e.g. `adapt-<slug>-<module>`) when spawning it and record the
returned `agentId` in `plan.md` keyed by module, so `plan.md` becomes the agentId registry for
re-adapt dispatches.
Fallback (Tier C): if the capability probe is negative (env unset, `SendMessage` absent, or probe
signals the orchestrator is not the team lead), spawn a fresh `odoo-coder` /
`odoo-test-writing` agent with an explicit brief containing the P9 failure output. Tier C is
always correct; the worklog is always written regardless of tier.

- **8a forward the test FIRST** via `odoo-test-writing` mode `adapt`. Adapt the MERGED SOURCE
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
- **8b adapt the code** per bucket via `odoo-coder` (backend) / `odoo-frontend-coder` (frontend),
  dispatched with an FP-ENRICHED brief = the named **Child worktree path: `<absolute path>`** field
  + the same **cd-on-resume (HARD RULE - Tier-A)** item as 8a + intent record + bucket + the failing
  test + the installable:False checklist. Bucket (a)/(d): no adapt code. Bucket (b): 3-way merge + adapt.
  Bucket (c): re-implement on the target idiom. The frontend leg additionally grounds any
  ported OWL/QWeb/SCSS against `skills/_shared/odoo-frontend-fidelity.md` so the forwarded UI
  stays on-theme and design-system-correct for the target version.
- **8c new module** (exists at source, not yet at target): `installable: False` + comment
  `auto_install`/`application`, lint-fix only. SSOT: `[[fp-installable-false]]`.
- **8d migration script**: rename `<src-series>` -> `<tgt-series>` dir ONLY when the gate
  `installed < parse(dir) <= current` holds - never rename blind (an inert dir is silent).
  (`installed` = `ir.module.module.installed_version` for the module; `current` = manifest `version`.)
Converge each child worktree back to integration (serialized) - the converge-back stays
serialized, one in-flight at a time. Do NOT remove the child worktree at converge-back time:
under Tier-A the adapt -> verify -> (re-adapt on failure) cycle for that module may resume the
SAME worker, which `cd`s back into its still-existing child worktree, so the worktree MUST persist
through the whole cycle. Remove a module's child worktree only AFTER that module's cycle is
confirmed done (P9 GREEN for that module's batch); a worktree removed before P9 verify would leave
a Tier-A re-adapt worker `cd`-ing into a deleted path.

**P9 - Verify by behavior [PER-BATCH, in integration].** Resolve odoo-bin flags for the
TARGET series via `cli_help` before invoking (the allocator returns version-agnostic ports;
flags differ per series, e.g. v19 namespace bootstrap). Acquire ONE ephemeral instance per
batch via the allocator (reserves DB name + ports; the `-i` run performs Odoo create-on-init
and builds the DB; the allocator drops it through Odoo on release), install the N affected modules
ONCE, run the target suite: RED-then-GREEN for the whole module + confirm-by-toggle for FP-delta
tests only. Triage each red test as FP-delta vs pre-existing (run it on clean target tip). Never
relax an assertion to hide a pre-existing failure. Full per-batch + allocator + CREATEDB-role
protocol (CREATEDB still required - Odoo create-on-init needs the same privilege): `[[fp-merge-absorption]]`.
Instance lifecycle and test invocation conventions:
`docs/reference/INSTANCE-LIFECYCLE.md` and `docs/reference/ODOO-TESTING.md`.

**P10 - Gate merge [STOP, per batch].** Emit `merge-log.md`, present it, wait for human-confirm.
On confirm: delegate to git-operator to commit the merge (buckets a/d still commit - Hard rule 7), update
`checkpoint.json` `{<sha>: done}`. More commits/batches remain -> LOOP to P5: each subsequent
commit re-runs the full per-commit cycle P5 merge -> P6 symbol-survival -> P7 drift -> P8 adapt
(recreating WORK-tier worktrees from integration), with P9 verifying the adapted batch and P10
gating it. Never loop straight to P8 - that would absorb the next commit without a merge or a
symbol/drift check.

**P11 - PR + review.** Push `fp/<slug>` (delegate to git-operator; resolve origin URL via
`git remote get-url origin`), then open PR (delegate to github-operator). Run `odoo-code-review`
inline (via the Skill tool, from this orchestrating context) passing `TARGET: worktree:<path>/fp-integration` (the
JOB-tier integration worktree created at P4 - `<path>` is the base path passed to git-operator at P4)
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
   it sits on a line this port changed. Delegate to git-surveyor a three-dot diff
   (`origin/<target-branch>...fp/<slug>`) and attribute each finding to either a
   forward-ported line (in scope, fix now) or a pre-existing target line (out of scope, do not
   re-rate the target's own debt as a port regression). Rate findings only after this attribution.

A module that is `installable:False` at the target is in the lint-only lane (`[[fp-installable-false]]`):
the reviewer rates ONLY lint/syntax for it and MUST NOT raise a business-logic finding (its
behavior is intentionally not forward-ported - see `## Model triage`).

NEVER squash (keeps SHA). B stays LOCKED - the PR only adds the merge commits. Wait for human
merge.

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

- **Continuous (default).** Recurring; source keeps evolving. Merge keeps SHA; merge-base
  advances; `checkpoint.json` makes the next run skip done commits and never re-resolve a past
  conflict.
- **One-shot (`--one-shot`).** Port one frozen batch once; repeated-resolution footgun does not
  apply. A no-commit cherry-pick (delegated to git-operator) is the accepted op; everything else (intent -> classify ->
  design -> plan gate -> merge -> symbol-survival -> adapt -> verify -> gate) is identical.

## Checkpoint / resume

`.odoo-ai/forward-port/<slug>/checkpoint.json` maps
`{<sha>: extracted | designed | adapted | verified | done}`, with `designed` carrying the
`design_doc` path for any commit P3 routed to `odoo-solution-design`. P0 reads it and skips
`status=done` commits (and resumes a `status=designed` commit at the P4 plan gate with its
recorded `design_doc`, so a crash between design-approval and re-entry resumes correctly). A
crash mid-batch is recovered by re-reading the checkpoint + the on-disk `intents/`, `plan.md`,
and `merge-log.md` (file existence is the source of truth, the JSON is the fast index). Child
worktrees left dangling by a crash are removed and recreated from integration. Cache any held
allocator lease token in the batch worklog so a crash can release the DB instead of orphaning it.

## Frontend / i18n / data-XML caveats

Forward-port adds platform-drift classes a pure-Python port misses - flag and route each:

- **Frontend (JS/OWL/SCSS).** Asset-bundle keys drift across series (e.g. `web.assets_backend`
  manifest entry shape) and OWL moved from the legacy `web.Widget` / `odoo.define()` era to
  OWL 2.x `patch()` / `useState` / `useService`. Route a frontend adapt commit to
  `odoo-frontend-coder` (it owns both eras) - never hand-translate OWL from memory.
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
  the source ref into reach (delegate to git-operator: add source remote + fetch) BEFORE computing
  the merge-base or merging; a forward-port across repos that skips this silently merges against a
  stale local ref. Detail: `references/fp-phase-detail.md`.
- **Manifest version-bump gate.** Bump a module's manifest `version` only when the absorbed
  diff touches a `.js` / `.scss` / `.xml` file or anything under `migrations/`; a pure-`.py` port
  needs no bump. SSOT: `[[fp-installable-false]]`.
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
`produced` lists `plan.md`, `intents/<sha>.md`, `merge-log.md`, `checkpoint.json`, and the PR
URL; `next` is the human-confirm gate (P10 or P11 merge). When P3 routes a commit out to design,
`next: odoo-solution-design` with canonical payload
`{ return_to: odoo-forward-port, design_slug_hint: <slug>-fp-<sha>, target_version: <series>,
modules: [<names>], intent_records: [<paths>], classification: <bucket-(c) summary> }` and the
run YIELDS - the run-driver advances the hop and re-enters forward-port with the returned
`design_doc`. Additive output for the run-driver - it does not change anything produced above.
