---
name: odoo-forward-port
argument-hint: "[from-series] [to-series] [module/range]"
description: >-
  Forward-port commits from a lower Odoo series branch to a higher one
model: sonnet
---

## Role

Forward-port conductor: own the git topology, the per-commit SEMANTIC pipeline, and the subagent
lifecycle. Decide which commit at which model tier, which outcome bucket, when to gate.
The semantic work is per-commit; the git operation is NOT: intent, bucket, and adapt are reasoned
per source commit; the range is absorbed by ONE merge closed by ONE merge commit.
Delegate leaf tasks to specialist agents and read-only delegates: intent extraction, code adapt,
test forwarding, AND every gate P6 / P6-TEST / P7 runs - the conflict-marker scan and range file
list, the OSM symbol grounding, the static lint lanes, and the test-collection gate (WHO takes
which: `[[fp-symbol-survival-check]]` - Who runs this check). You record verdicts and finding
lines; you do not produce them.
A green merge + lint + install does NOT prove the feature works on the target platform; only an
intent test that passes on the target and was proven to fail when its rule is broken (for a bucket-(a)
commit: confirmed absorbed), plus a symbol-survival check, proves it. SHA is sacred: absorb the source
RANGE with a single merge of its tip; never squash, never cherry-pick, and never merge the range
one commit at a time.

## Out of Scope

- One isolated change with no source commit to port -> use `odoo-coding`
- A version-to-version API/feature delta only (no merge, no adapt) -> use `odoo-version-diff`
- Reviewing or auditing an existing PR or diff -> use `odoo-code-review`
- A pre-upgrade deprecation sweep of one codebase -> use `odoo-deprecation-audit`
- Same-series single-commit replay (no version jump) -> use `odoo-git-rebase`
- A docs-site repository (not an addons repo): porting its pages to higher series -> `odoo-doc-site` (PORT)
- Whole-cluster upgrade to a higher series (not one commit) -> use `odoo-modules-upgrade`
- A STANDALONE design request with no commits to port -> use `odoo-solution-design` directly.
  A bucket-(c) commit INSIDE a forward-port run that requires non-trivial design is handled by
  the P3 route-out and stays in scope
- Parallelizing N disjoint WIs with cherry-pick + squash semantics -> use `odoo-planning`

> An Odoo forward-port routes HERE, not to bare git-ops: drive this pipeline and invoke `git-ops`
> (via the Skill tool) for each git step.

## Invocation

Entry points (one pipeline): the `/odoo-forward-port` slash command, a natural-language match, or
a Skill-tool call from an orchestrator (e.g. `odoo-intake`).

### Arguments

```
/odoo-forward-port <source-ref> <target-branch> [--scope <mod1,mod2>] [--since <sha>]
```

| Argument | Required | Description |
|---|---|---|
| `<source-ref>` | yes | Source branch or commit range (e.g. `origin/<source-series>`) |
| `<target-branch>` | yes | Target branch (e.g. `origin/<target-series>`) |
| `--scope <modules>` | no | Comma-separated module list; default = all modified modules in range |
| `--since <sha>` | no | Only commits after this SHA (an incremental or resumed run) |

There is exactly ONE shape and no mode flag: an SHA-preserving merge of the range tip, closed by ONE
merge commit. To land only PART of a source branch, pass that sub-range's TIP SHA as `<source-ref>`.

Parsed from `$ARGUMENTS` in P0 (missing `source-ref`/`target-branch` -> ask once, one message,
before any read or git op).

### When to use

- **1-5 commits** - intent-extract + classify + Plan Mode gate + serial adapt + one merge commit.
- **6+ commits** - full plan (commit topology, per-commit tier, buckets) in Plan Mode, recorded
  to `plan.md`. Still ONE merge and ONE merge commit by default; a human may split the run into
  several batches at the plan gate, and then each BATCH gets one merge of its own range tip
  - the commit count never sets the merge count.

For an upgrade plan (risk + deprecation + diff) instead of an actual port, use `/odoo-plan-upgrade`.

## Hard rules

1. **Target-branch-lock** - NEVER checkout, switch, commit, merge, rebase, reset, or push the
   target branch B directly. Another session may hold B's working tree. All integration happens
   in a dedicated integration worktree branched FROM B (the JOB tier below). Read-only ops on
   B are allowed. Delegate every mutation on the integration worktree to `git-toolkit:git-ops`
   (`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`). Saga (record the pre-loop SHA, checkpoint
   after each integrated commit, clean-abort or resume on failure):
   `${CLAUDE_PLUGIN_ROOT}/skills/_shared/integration-loop.md`.

2. **ONE merge, ONE merge commit - the range is the git unit, never the commit.** A
   forward-port opens a SINGLE no-ff no-commit merge of the range's TIP SHA (delegated to
   git-toolkit via `git-ops`; see `[[fp-merge-absorption]]`) and closes it with a SINGLE merge
   commit - exactly the shape an ordinary branch-level merge produces. Every commit in the range
   becomes an ancestor of that merge commit, so every source SHA is preserved and the merge-base
   advances to the tip in one step. **Two shapes are BANNED, both unconditionally:**
   (i) **merging (or committing) one source commit at a time**;
   (ii) **cherry-pick, at ANY granularity**.
   Batches never reinstate either shape: a batch merges its own range TIP once. There is no
   cherry-pick escape hatch: a FROZEN source merges like any other, and a DELIBERATE SUB-RANGE is
   landed by merging that sub-range's TIP SHA. Full protocol: `[[fp-merge-absorption]]`.

3. **Intent before code** - the unit being forwarded is the behavior/purpose, not the diff.
   P1 extracts intent (read-only); P8 re-implements that intent on the target
   idiom. Never paste a source diff hunk forward and call it done. SSOT: `[[fp-intent-4outcome]]`.

4. **Verify by behavior, not by text** - success = the forwarded INTENT test passes on the target AND was
   proven to guard its rule: the node's test leg broke that rule, watched the test fail, and restored the
   code (`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`); for a bucket-(a) commit, its
   source test passes on the target with the commit's own code out of play (absorbed by core). A clean
   merge is necessary, never sufficient.

5. **Symbol-survival before adapt** - after every merge, run the P6 symbol-survival
   check on BOTH conflicted files and merge-clean-but-source-touched files. Resolve every broken
   symbol into a bucket before adapt starts. SSOT:
   `[[fp-symbol-survival-check]]`.

6. **Human gates are P4 (plan) and P12 (PR merge); local merges are self-decided.** The P4 plan
   gate is the request's one Plan-Mode approval (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md`
   § One Plan-Mode gate per request). P10 concludes each batch's merge on
   the integration branch `fp/<slug>` without asking - it lands nothing on B. No automated commit of
   the integration into B, no auto-merge of the PR: P12 presents and waits.

7. **Outcome a/d are still ABSORBED** - buckets (a) already-satisfied and (d) no-longer-relevant
   produce no adapt diff, but their SHAs stay inside the merged range. NEVER narrow or fragment
   the merge range to exclude an (a)/(d) commit. Record
   the bucket + reason on that commit's `merge-log.md` row and in the single merge commit's message
   body, so reviewers see why those SHAs carry no adapt work. SSOT: `[[fp-merge-absorption]]`.

8. **Verify subagent claims** - never trust a leaf's self-report of GREEN. Run the verify
   command yourself per batch (P9) before P10 concludes the merge.

9. **Acceptance is mandatory (narrow escape only)** - P11. The forward-port is not DONE without an
   ACCEPTED verdict or a recorded narrow-escape.

10. **i18n reconcile is mandatory (narrow escape only)** - 8e COMPUTES the two conditions and P9.5
    DISPATCHES `odoo-i18n` per batch. Skip only via an enumerated escape recorded on the module's
    `merge-log.md` row (`${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`). The forward-port
    is not DONE without an i18n result or a recorded escape for every module whose row says
    `i18n_due: yes`.

11. **Descriptor filename resolves ONCE, per side** - the descriptor filename of a series is named by
    `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 6. At P0, resolve it once from each
    side's series and record it in the run's working state: `<tgt-descriptor>` for `target_ref`,
    `<src-descriptor>` for `source_ref` - they can DIFFER. Reuse those literals
    for every descriptor read, path, and assertion below: `installable`, `depends`, `version`,
    `manifest_path`, `history_dump_path`, and the P9 addons-coverage assertion. An absent
    descriptor means the WRONG FILENAME may have been opened; a failed descriptor
    read is never a reason to drop the module or to report a guessed `installable` / `depends` /
    `demo` value.

## Git topology - two tiers of worktree

**JOB tier (always):** create `fp/<slug>` integration branch via dedicated worktree (delegated
to git-toolkit via `git-ops`) from B's HEAD. All absorption, adapt, and verify happen inside this integration
worktree. The target branch B is read-only for the whole run; only the final, human-confirmed PR merge lands on B.

**WORK tier - NOT used by P8 adapt.** P8 is SERIAL, and P5 opens the run's SINGLE merge of the range tip
(`--no-commit`) that only P10 commits, so `MERGE_HEAD` is live in the integration worktree for the
batch's whole P6-P9 span. P8 8a/8b always adapt DIRECTLY in the integration worktree - never a
per-module child worktree. § P8 gives the brief field: one run-long `Worktree path` naming the
integration worktree. JOB tier is the only worktree tier in this skill.

## The pipeline

**Dispatch-brief skeleton.** For every specialist agent dispatched below (`odoo-intent-extractor`,
`odoo-installable-prober`), fill the caller-side skeleton in
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton (read it by path) plus the
target agent's family delta; never inline that file verbatim into a hard-leaf brief. Resolve
`<SHARE_DIR>`/`<ISOLATE_DIR>` once and pass the captured literals
(`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` § Cross-worktree dispatch).

Run phases in order. Intent + classify + design + the Plan Mode gate ALL precede the merge.
Concurrency for any fan-out follows `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
(Mode B). Full per-phase dispatch briefs, git commands, and worklog templates:
`references/fp-phase-detail.md`.

**Orphan sweep (every run, BEFORE P0 below).**

`find <ISOLATE_DIR>/forward-port/ -mindepth 1 -maxdepth 1 -type d -mmin +43200 -exec rm -rf {} +`

Rule: `${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3.

**P0 - Recon & triage [read-only, NO stop].** Parse `$ARGUMENTS` (`source-ref` / `target-branch` /
`--scope` / `--since`); if `source-ref` or `target-branch` is missing, ask once in a
single brief message before any read or git op.

**"one-shot" / "one-time" in a request means ONE RUN, not a different git shape.** Never read those
words as a licence to cherry-pick; if the caller meant "land only part of the branch", point them
at the sub-range recipe in Hard rule 2. Read any existing worklog
(`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`) and `checkpoint.json` (resume per the
Checkpoint section: skip ONLY `status=done`; do NOT re-run design for a `status=designed` commit -
resume it at the P4 plan gate with its recorded `design_doc`; a `status=extracted` commit resumes
at P2; a `status=adapted` commit resumes at P9). Invoke the `git-toolkit:git-ops` skill (via the
Skill tool) to enumerate commits (range `<merge-base>..<source-ref>`, --no-merges; read-only, no
worktree or branch yet); apply `--scope` / `--since` filters to the returned list. Map each
`--scope` module name to its directory path before requesting git-ops to filter by path (module `l10n_vn` ->
`l10n_vn/`; resolve via manifest location, may be at repo root or under an addons subdir).

**Record the range ENDPOINTS.** From the filtered, chronologically ordered list, record
`<src-first-SHA>` (oldest) and `<src-tip-SHA>` (newest) in the run's working state; P5 absorbs the
range with them and the P10 commit message spans them. An EMPTY filtered list: report `DONE`
(nothing to forward) and stop; never open a merge window on an empty range.

**Group by MODULE first, then by commit within that module (R2a).** Invoke the
`git-toolkit:git-ops` skill (via the Skill tool; read-only, no worktree) to list touched files
per commit (`--name-only`) for every commit in the range, and map each touched path to its owning
module (same resolution rule as `--scope` above). Build
`module -> [ordered sha list]` (chronological order, oldest first); a commit touching 3 modules
appears in each of the 3 modules' lists. This map is what P1 dispatches over and what Table 1 (EXTRACT
tier) resolves against below.

TRIAGE each MODULE's commit bundle to an EXTRACT model tier INLINE (`git show --stat` per commit in
the bundle + one `find_override_point` probe when override depth matters; never dispatch an agent
to decide a dispatch). Recon only: no gate, no worktree, no branch yet. Triage tier table (module-bundle-scoped): `references/fp-triage-table.md`.

**P1 - Intent extract [PARALLEL, READ-ONLY, MODULE-SCOPED].** ONE PARALLEL UNIT PER MODULE (never per
commit). Pre-step: invoke the
`git-toolkit:git-ops` skill (via the Skill tool; read-only, no worktree)
in a single batch pass to write per-commit dump files - for each commit in the range, a full-patch
commit dump (message + diff) written to `<ISOLATE_DIR>/forward-port/<slug>/commits/<sha>.dump`
(resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`;
substitute the captured absolute path); collect the `{ <sha>: <abs-path> }` map. Include `repo: <main-checkout-root>` in the git-ops dispatch for cross-repo ports.

**BAN (R2b): at most ONE `odoo-intent-extractor` instance per module across the ENTIRE run.**
Dispatch by walking the P0 `module -> [ordered sha list]` map, ONE agent launch per module, never
one launch per commit. Each extractor brief MUST include `commit_dump_paths: { <sha>: <path>, ... }`
(the module's full ordered map from the P0 pre-step, oldest first; `commit_dump_path` only for the
narrow re-check/audit uses documented on the agent itself; the extractor never runs git). A second
instance for a module ALREADY dispatched this run, while the first is live or has completed
successfully, is a pipeline defect; retry a failed or incomplete module pass by resuming the SAME
instance by the id its launch returned.
**Tier-C retry (no recorded id, or it no longer resolves -
`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` § Tier A):** confirm the failed
instance's turn has fully ended, then launch exactly ONE replacement `general-purpose` worker
carrying the module's FULL, UNCHANGED `commit_dump_paths` plus `PRIOR ATTEMPT: <what the failed
pass returned or omitted>`. The replacement is authoritative for the whole module bundle.
Dispatch each module's single instance using CHP Tier-B `subagent_type: "fork"`
(`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` - Tier B), with the module's triaged
`model` override (Table 1, resolved per module bundle - § Model triage), up to the Mode B budget
(rolling window beyond it; the budget counts MODULES in flight, not commits). Extraction is
read-only, so no worktree children. Fallback (Tier C): if `subagent_type: "fork"` is unavailable,
dispatch a fresh `general-purpose` spawn with an explicit brief; the worklog is always written.

**Write path is PER-MODULE NAMESPACED.** A commit shared between modules A and B is dispatched to
BOTH modules' single extractor instances. Set the P1 dispatch brief's `SLUG` field to
`<slug>/<module>`, never the bare run `<slug>`, for EVERY module's extractor dispatch (full brief:
`references/fp-phase-detail.md` P1). Each worker writes one record PER COMMIT in its module bundle
under its own module's namespace (the why + behavioral contract + OSM-grounded symbols, never the
diff). Aggregate every returned summary (one per commit, across every module's dispatch) into the
P2 classify queue; read each summary's `intent_file` path as returned.

**P2 - Classify + installable-probe [module-first order, per-commit bucket, OSM].** Walk modules in
the SAME order P0/P1 established (the `module -> [ordered sha list]` map), and within each module
walk its commits in that module's own order (R2a). For each commit, ground its symbols
against the TARGET version (`set_active_version` once, then `api_version_diff` + `model_inspect`)
and assign exactly one bucket a/b/c/d per commit. SSOT: `[[fp-intent-4outcome]]`. Append one row per commit to
`merge-log.md`. `odoo-version-diff` in forward-port mode can supply the per-symbol bucket
suggestion. Every Odoo Semantic call carries `odoo_version=` - never omit it. Once buckets are
known, apply the **bucket-(c) upgrade-scale gate** to each bucket-(c) cluster: estimate its size
and, if it is an upgrade-scale re-implement rather than a mechanical port, RECORD the
`upgrade-scale` flag on that cluster now (`## Model triage`). Do NOT STOP at P2 - the recorded flag becomes a defer-or-do line in the P4 plan. A `(b) do now`
cluster that ALSO meets the P3 non-trivial criterion proceeds to P3 design before P4.

In the same phase, resolve each touched module's `installable` status from the TARGET CLEAN-TIP
`<tgt-descriptor>` (Hard rule 11) - the state of the target branch BEFORE the merge, never
post-merge. Invoke the
`git-toolkit:git-ops` skill (read-only) to write that file, then read it: an absent key means
installable, an absent FILE means the module is not on the clean tip. **Produce
`manifest_path` for EVERY touched module, unconditionally** - it is the prober's required input, and
the prober is a `role: leaf` that cannot fetch it. DISPATCH the read-only haiku leaf
`odoo-installable-prober` only when the SOURCE HISTORY must ALSO be read to disambiguate category 3
(the module's manifest was NOT touched by the forwarded commit range yet its target state is
unclear); for categories 1-2 your own clean-tip read suffices.

Pre-step (for EVERY touched module):
invoke the `git-toolkit:git-ops` skill (via the Skill tool; read-only) to write two files - the
clean-tip manifest (`<module>/<tgt-descriptor>`
at `target_ref`) to `manifest_path = <ISOLATE_DIR>/forward-port/<slug>/installable/<module>/manifest.py`,
and the patched manifest history (log-with-patch of manifest modifications against `source_ref`) to
`history_dump_path = <ISOLATE_DIR>/forward-port/<slug>/installable/<module>/history.diff`. Include
`repo: <main-checkout-root>` in the git-ops dispatch for cross-repo ports. Dispatcher inputs
(canonical contract, pass exactly, when the prober IS dispatched for category-3 disambiguation):
`{ module, repo_root, source_ref, target_ref, target_version, manifest_path, history_dump_path }`.
`repo_root` is the MAIN checkout root where git runs (the integration worktree does not exist at
P2). `manifest_path` / `history_dump_path` are absolute paths to the pre-step files - both mandatory.
Whether resolved directly (categories 1-2) or via the prober (category 3), record
`installable_false=yes|no` as the module's OWN row in `merge-log.md`, keyed by module, distinct
from the per-commit rows - the ONE field any later phase reads for a module's installable state.
Short-circuit and lint-only lane: `## Model triage`; SSOT: `[[fp-installable-false]]`.

**P3 - Design [conditional route-out].** When a bucket-(c) "do now" commit touches a NON-TRIVIAL
module (the non-trivial criterion `odoo-solution-design` applies), route OUT to `odoo-solution-design` instead of
adapting blind. A deferred or `installable:False` module needs no design - skip it. Mechanism:
emit the Continuation Contract and YIELD - forward-port only EMITS the next hop; the plan runner
advances it. The payload is `next: odoo-solution-design` with `return_to: odoo-forward-port` and
the rest of the `inputs` block printed in `references/fp-phase-detail.md` P3 - match it exactly,
including `design_proposals`.
`odoo-solution-design` under `return_to` runs its own design, then emits `next: odoo-forward-port`
with `design_doc`. On re-entry, read `design_doc` from the returned contract's `inputs`, record it
against the commit, set checkpoint `status=designed`, and proceed to the P4 plan gate with the
design linked - do not re-run design. If `design_doc` is ABSENT from the returned inputs, set the
commit back to `status=extracted` and re-enter P3 next run. Full contract:
`references/fp-phase-detail.md` P3.

**P4 - Plan gate [Plan Mode].** The request's one Plan-Mode gate (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One
Plan-Mode gate per request): call `EnterPlanMode`, present the plan, `ExitPlanMode` on approve.
The plan CONTENT is authored here (not routed through `odoo-planning`) and is MODULE-FIRST:
module topology (each module's own ordered commit list, from the P0 map); per-module EXTRACT tier
[the real triaged tier]; per-commit bucket [the
real classification] and ADAPT tier within that module; installable routing per module; design-doc
link for any commit P3 designed; and the ABSORPTION topology - how many batches, each batch's
`<src-first-SHA>..<src-tip-SHA>` range, and therefore how many merge commits the run will produce. State
that number explicitly (the human's ONLY chance to choose a multi-batch split; the default is ONE
batch = ONE merge commit, never derived from the commit count). The plan also carries one `Docs: <module | site | both | none> - <facts>` line: the
documentation target the closing step writes, taken from `odoo-intake`'s Documentation routing
facts in the brief, or decided here by that rule when none came (ask only on a miss); `refine: no
docs` drops it. `EnterPlanMode` MUST come before any branch, worktree, or file touch.

After Plan Mode approval, invoke the `git-toolkit:git-ops` skill (via the Skill tool) to create the
JOB-tier integration worktree branched from B (Hard rule 1; dispatch contract: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`).
Supply the branch name `fp/<slug>`, path `<path>/fp-integration`, and base `<target-branch>` in the
brief. No branch is created before this point - everything up to and including the plan gate is read-only.

THEN write `<ISOLATE_DIR>/forward-port/<slug>/plan.md` (module-first: one block per module carrying
its EXTRACT tier + its ordered commits, each with bucket + ADAPT tier + installable routing +
design-doc link + merge batch) as the resume RECORD that later phases and the checkpoint/continuation read. plan.md template:
`references/fp-phase-detail.md` P4.

**P5 - Merge --no-commit [critical section, in integration; ABSORB-ALL - runs ONCE per batch].**
Invoke the `git-toolkit:git-ops` skill (via the Skill tool) ONCE for the whole batch, absorbing
its ENTIRE commit range in one operation: a no-ff no-commit merge of `<src-tip-SHA>` (the batch's
LAST/newest source commit - absorbing every earlier commit in the range as an ancestor). **Never iterate P5 per source
commit** (Hard rule 2). For semantic
conflicts, use the stateless-resume recipe in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`. Only one merge in flight at a time. Do NOT commit yet (P6 -> P8 -> P9 all happen before the single commit). SSOT: `[[fp-merge-absorption]]`.

**P6 - Symbol-survival check [MUST].** Before any adapt, every source-side symbol in conflicted
AND merge-clean-but-source-touched files is OSM-grounded against the target surface - by a
DISPATCHED read-only delegate, never in this context; you record the verdict and the finding lines
only (WHO runs it: `[[fp-symbol-survival-check]]` § Who runs this check). Any symbol absent/changed
at target FORCES the commit into bucket b/c/d and BANS leaving the auto-merged line unchanged. This
catches the autosilent field-break (no conflict marker, runtime crash).
SSOT: `[[fp-symbol-survival-check]]`.

**P6 TEST-survival sub-check [MUST - after the production symbol check].**
Detect test code referencing a field/model symbol removed at target. **Dispatched to `Explore`
(read-only, `model: haiku` passed on the launch)** per `[[fp-symbol-survival-check]]` § Who runs
this check. Every call named below is CONTENT OF THAT DELEGATE'S BRIEF, never a call you issue in
this context. Brief it to: for each model/field touched, call
`tests_covering(model='<model>', odoo_version='<target_version>')`
(optional `field='<field>'` narrows); for a whole-module commit, supplement with
`test_coverage_audit(module='<module>', odoo_version='<target_version>')` (field-level only; for
per-method coverage use `tests_covering(model='<model>', method='<method>', odoo_version='<version>')`,
which is sparse); and, because `tests_covering` does not compare cross-version, before concluding a
test is broken CONFIRM the symbol is absent at target via
`model_inspect(model='<model>', method='fields', odoo_version='<target_version>')`. Test methods
referencing a symbol absent at target MUST be triaged into the same bucket (not forwarded
verbatim). Record every broken test-symbol reference in the `merge-log.md` per-commit row; the
P8 adapt brief MUST carry this list as `BROKEN TEST-SYMBOLS`.

**P7 - Pre-adapt drift scan [MUST, before the behavioral loop].** P6 catches OSM-indexed
symbol-graph breaks; P7 catches static grep / import / AST breaks via two lanes: classes (d)(e)(g) run over ALL merged-touched `.py`
(production AND `tests/`) - (d)(e) catch runtime NameError and (g) catches an autosilent
ORM Invalid-field key before P9; the remaining classes (a)(b)(c)(f) and the collection
ACCEPTANCE GATE apply over `tests/` only.
DISPATCH the two lanes as read-only delegates (`Explore`, `model: haiku` passed on the launch) and
record only their verdict (`[[fp-symbol-survival-check]]` § Who runs this check). The delegate enumerates every symbol, file
path, import, and test-base-class the merged code touches (Lane 1 production AND tests; Lane 2 tests
only); you triage each returned finding into a bucket (b adapt / c re-implement / d drop) - never
leave an auto-merged line referencing a dead symbol.
**ACCEPTANCE GATE:** merged test files MUST import and collect cleanly on the target
(`python -m pytest --collect-only`; a `setUpClass` that needs a database is confirmed by P9's
`odoo-instance` run-tests, never by a raw `odoo-bin` run) before any
adapt starts (`0 failed, N error(s)` is NOT a passing result). Record findings in
`merge-log.md`; the P8 adapt brief consumes them. SSOT: `[[fp-symbol-survival-check]]`.
Full commands: `references/fp-phase-detail.md` P7.

P7 is also where the VIEW-TOPOLOGY sub-check surfaces: once a bucket-(b) OR bucket-(c) commit's own
adapt step lands or modifies an `ir.ui.view` record (INCLUDING a clean auto-merge with no conflict
marker), confirm it is not an unconditional same-module inherit stack on its own base view - a
re-implementation (or a clean-merged carryover) that carries the SOURCE module-split idiom forward
instead of the target's. Buckets (a)/(d) are out of scope. A HIT is a PROPOSAL: it routes out through
the P3 design gate to `odoo-solution-design`, and is applied only if the returned `design_doc`
adopts it - never merged or deleted on the predicate alone. Predicate, the two non-defect
exceptions, and the merge-unsafe escape: `references/fp-triage-table.md` § Bucket-(c) same-module
inherit-view check.

**P8 - Adapt [code first, then tests; SERIAL per-module; runs INSIDE the batch's single open merge window].**
Adapt the MERGED RESULT module by module, driven by the per-commit intent records - never
re-opening, re-merging or re-staging per source commit; a module touched by several commits is
adapted ONCE against the combined result. Adapt DIRECTLY in the integration worktree
(`<path>/fp-integration`); never a per-module child worktree (§ Git topology). In-window protocol: `[[fp-merge-absorption]]` § Absorption window (inside the ONE no-commit merge).

**Per-module agent-id registry (this run's plan.md).** Record in `plan.md`, keyed by module, the id
each of your launches returns - one id per module for the WHOLE run, never one per commit
(`${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` Tier A).

**R2b at the 8b leg: one coder per module, resumed.** P8's only launch per module is the
`odoo-coder` that `odoo-coding` starts (the node's test leg runs inside it). On the module's
FIRST P8 invocation this run, invoke `odoo-coding` without `WORKER_AGENT_ID` and record the coder's agent id
that launch returns; on every LATER one (a P9 re-adapt, a later batch) carry it as `WORKER_AGENT_ID: <id>`
in the FP-ENRICHED brief and `odoo-coding` resumes it. Send the P9 failure output (or the next batch's brief) and collect the result per CHP § Async
park-and-be-resumed semantics - R0 of `${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md`
decides whether you end your turn or wait inside it; never carry on with the next module before the result
is in hand. On resume the coder MUST `cd` to the integration worktree before any Bash command (CHP
snippet "Tier-A workers in a git worktree - cd on resume").
Fallback (Tier C): when no id is recorded for the module, the recorded id no longer resolves, or no
messaging tool is present, re-invoke `odoo-coding` cold with the full FP-ENRICHED brief - the same
**Worktree path: `<path>/fp-integration`** field and, for a re-adapt, the P9 failure output.

- **8a ground the adapt brief** (inline OSM calls, attached as raw output): `test_base_classes(odoo_version='<target_version>')` for the base
  class (ADAPT RULE: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 3; `cr.commit()` is
  FORBIDDEN in tests); `find_test_examples(query='<feature_or_model>', odoo_version='<target_version>')`
  (optional `model=`; `kind` `'transaction'` | `'http'` | `'form'`, or `'js'` for JS tests - never
  `'python'`) for target-idiom templates; the module's rows of the P6 test-survival list as
  `BROKEN TEST-SYMBOLS` (rewritten or dropped by the test leg, never forwarded verbatim); and, for each
  bucket-(a) commit, the hunk map - where its merged hunks sit in the working tree, from a read-only
  delegate (`references/fp-phase-detail.md` P8, Bucket-(a) hunk map) - carried on that commit's
  `BUCKET` line so the absorption check can take that code out of play.
- **8b adapt the module: ONE `odoo-coding` invocation per module** (via the Skill tool; never raw
  `odoo-coder` or `odoo-frontend-coder`; frontend legs ground against
  `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`). The forwarded source test IS the oracle: adapt it in place;
  write one from scratch only when the source commit shipped none, anchored to the intent record
  (`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`). FP-ENRICHED brief = the named **Worktree path: `<path>/fp-integration`** field
  (the SAME JOB-tier worktree for the WHOLE run) + `MODE: adapt` + `SOURCE TESTS` (the module's merged test files, read/write in place)
  + `BROKEN TEST-SYMBOLS` + `BASE CLASS` + `TARGET TEST EXAMPLES` + `INTENT` (the intent record per
  source commit touching the module) + `BUCKET` per commit + `COMMIT: caller` (no commit: the node
  returns its file list and P10 commits the batch) + `RUN_ID: <this run's id>` +
  `WORKER_AGENT_ID: <id recorded for this module>` (omit on its first invocation) +
  `DESIGN_DOC: <path from plan.md's design_doc column for this commit | none>` (P3's route-out result) +
  `CONSTRAINTS` - the forward-port boundaries in ONE field: C1 (set the target `version` to `max(M + 1, S)` when the source bumped it), C2 (migration dir: retarget when the
  target has the problem the script solves, else forward), C3 (carry pre-existing source bugs faithfully, never
  inline-fix) - `[[fp-merge-absorption]]`; plus the installable:False checklist for a new module and
  `LINT-ONLY` for a module `installable:False` at the target - `[[fp-installable-false]]`. Pass no
  `INSTANCE_HANDLE`: `odoo-coding` resolves the node's instance over that `WORKTREE_PATH`.
  Bucket (b): 3-way merge + adapt. (c): re-implement on the target idiom. (d): no adapt code. (a): no
  adapt code - P5 keeps its cleanly-merged hunks in the tree, so the test leg confirms absorption by
  running the commit's source test on the target with those hunks (the 8a map) out of play: green =
  absorbed by core, keep the test; red re-buckets the commit to (b)/(c) and the normal proof follows -
  record the new bucket + reason on its `merge-log.md` row.
  Return: the file list, the integrated verdict, and the test leg's brief per-test report. Store them on
  the module's own `merge-log.md` row (file list as `files:`); P9 adjudicates the report, P10 stages the
  files.
- **8c installable:False modules** - two sub-cases, same manifest action:
  (i) **New module** (absent at target): set `installable: False` + comment `auto_install`/
      `application`, lint-fix only.
  (ii) **Upgraded-then-forwarded** (pre-existing at target with `installable:False` at clean-tip,
      but merge carries `installable:True`): re-set to False + re-comment `auto_install`/
      `application` with breadcrumb - then lint-fix only.
  Both land in the LINT-ONLY lane. SSOT: `[[fp-installable-false]]`.
- **8d migration script**: decide each forwarded `migrations/<src-series>.a.b.c/` dir per C2 -
  retarget only when every module the script acts on is installable at the target tip, else forward
  it unchanged and record why; a retargeted dir is named FULL `<tgt-series>.V` so it fires on a
  deployed target DB at manifest `M` (bump the manifest only in the `S<=M` case; a legacy source-only
  data fix keeps `<src-series>.a.b.c`). This is a migration-threshold action, NOT a conflict-resolution version bump (C1). Full rule +
  `adapt_version` silent-skip WHY: `[[fp-merge-absorption]]`.
8b writes directly into the integration worktree (§ Git topology), so there is nothing to converge; P10 commits the adapt edits. A Tier-A resume is therefore always safe: the `cd`-on-resume target is the SAME path for the WHOLE run.

**P9 - Verify by behavior [PER-BATCH, in integration].** DELEGATE the run - do NOT allocate a DB +
port and run the full suite inline (`${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`).
Dispatch `odoo-instance` (via the Skill tool): provision the cluster ONCE, PASSING
`WORKTREE_PATH: <path>/fp-integration` in that first dispatch so the lease's addons path covers the
adapted tree (`odoo-instance` § WORKTREE_PATH substitution). Then per batch dispatch init for the N
affected modules followed by run-tests of the target suite (`GATE_ROLE: node-verify`), relaying the
returned `INSTANCE_HANDLE` so later batches reuse the same instance. Every build on that ONE
database follows `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § One build or export
per database. The executor returns a structured result block (per-test pass/fail + the instance log
path). From that block you adjudicate FP intent: the whole-module suite is green AND each forwarded
intent test was proven by its node's test leg (the returned per-test report says what it broke and
how the test failed; `merge-log.md`); a bucket-(a) commit's source test is instead confirmed absorbed
(green on the target with the commit's own code out of play). A test with neither is unverified:
resume the module's coder through `odoo-coding` (8b, `WORKER_AGENT_ID`) to produce it - never run a
break of your own here. 8b passes no `INSTANCE_HANDLE`; never hand the P9 handle to a P8 invocation.
Triage each red test as FP-delta vs pre-existing (re-run it on clean target tip via the same
executor); an FP-delta red goes back to the module's coder with the P9 failure output. Never relax an
assertion to hide a pre-existing failure. Full per-batch protocol + § Ephemeral isolation:
`[[fp-merge-absorption]]`. Conventions: `docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md` and
`docs/reference/ODOO-TESTING.md`.

**P9.5 - i18n reconcile [MANDATORY, per batch, own export build].** For every module in this
batch whose 8e record says `i18n_due: yes`, invoke the `odoo-i18n` skill (via the Skill tool) ONCE.
Pass the five caller obligations from
`${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`: `WORKTREE_PATH` (this batch's integration
worktree), `SELF_PROVISION: worktree-addons` so `odoo-i18n` builds its OWN export instance whose
addons path covers that worktree
(`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Addons coverage assertion: on a
miss, BLOCK), and `TARGET LANGUAGES` (the codes inferred from the source-side `<lang>.po` filenames -
deliverable languages only, never `en_US` - when any exist; otherwise OMIT the field). An
`i18n_due: escape:<E-id>` module is skipped with its recorded reason. Present every result -
reconciled or escaped - at P12 with the PR.

**Do NOT hand over the P9 verify instance** to `odoo-i18n`
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-i18n/references/i18n-recipe.md` KT4); let it provision.

**P10 - Conclude the merge [self-decided, per batch].** Write `merge-log.md`, reconcile the file
list, and commit - no human confirmation (a local merge on `fp/<slug>`; P12 presents it). Invoke the `git-toolkit:git-ops` skill (via the Skill tool) ONCE with the FULL file
list - the union of every module row's `files:` (8b) plus the files P9.5 returned - and the request
"stage these, then conclude the merge with one commit". That closes the batch's single open merge
window: the whole range lands as ONE merge commit, and every SHA in the range is marked `done` in
`checkpoint.json` (buckets a/d included - Hard rule 7). Then confirm the tree is clean (`git -C <path>/fp-integration status
--porcelain` empty, `MERGE_HEAD` gone - bounded reads); a leftover path is a file the list missed:
record it in `merge-log.md` for P12, never amend. Full brief: `references/fp-phase-detail.md` P10.

**There is no P5 loop.** A single-batch run reaches P10 exactly once, then P11. Only when the human
split the run into several batches at the P4 plan gate does the pipeline return to P5 - once PER
BATCH, never per commit - with the NEXT batch's range TIP, then P6 -> P7 -> P8 -> P9 -> P10 for that
batch.

**P9 instance release [MANDATORY].** Once the last batch's P10 merge is concluded, you are the run-level
owner of the P9 verify instance (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1): call
`mcp__plugin_odoo-ai-agents_odoo-local__lease_release` with the cached `lease_token` and `run_id`
before P11. Call `lease_park` instead only when a named later step of this run still needs the
database. Never release it between batches - every batch reuses it.

**P11 - End-to-end acceptance (odoo-acceptance) stage [MANDATORY, cluster-wide, narrow escape
only, BEFORE the P12 PR opens or reviews].** Runs after the P10 loop closes and BEFORE P12 pushes the
branch, opens the PR, or runs its review gate (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md`
§ Default tail). Compute the verify scope by invoking `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md`
over every module touched across the batch (from `merge-log.md`), deriving the reverse-closure via
OSM `impact_analysis` per that snippet's Step 1.
Invoke the `odoo-acceptance` skill (via the Skill tool) ONCE for the whole batch (never per commit
or per module). Fill the dispatch brief per `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton
(read it by path): `INPUTS` = the touched module set from `merge-log.md`, `scope_hint` =
`merge-log.md` + each touched module's own `<module>/intents/<sha>.md` (§ P1 write path), `odoo_version`
= target series; `INSTANCE_HANDLE: none provisioned` - NEVER P9's verify handle. `ACCEPTANCE` (by
pointer) = each ported commit's behavioral contract recorded in the touched module's own
`<module>/intents/<sha>.md` and any P3 design doc's §9 - NEVER a pre-built oracle. Do NOT hand it
the implementation.
**MANDATORY - narrow escape only.** Skip it ONLY when the touched set is a true dependency leaf with
ZERO in-repo dependents AND no behavioral surface (no views, no models any other module consumes) -
record that proof explicitly in `merge-log.md`; never skip silently. **The forward-port is not DONE
until this stage returns ACCEPTED (PASS), or the narrow-escape condition above is explicitly met and
recorded.**
Carry the acceptance verdict (or the recorded narrow-escape) forward and present it ALONGSIDE the
P12 human-merge decision below.
Output: `<ISOLATE_DIR>/qa/<slug>-acceptance-report.md` (`odoo-acceptance`'s own artifact), referenced
from `merge-log.md`.
**P12 - PR + review [runs AFTER P11 acceptance clears].** Push `fp/<slug>` (invoke
`git-toolkit:git-ops`; resolve origin URL via `git remote get-url origin`). Run `odoo-code-review`
inline (via the Skill tool, from this orchestrating context) passing `TARGET: worktree:<path>/fp-integration` (the
JOB-tier integration worktree created at P4 - `<path>` is the base path passed to git-ops at P4)
so the skill reviews the fp integration tree, not the principal tree - this lint-class review gate
runs BEFORE the PR is opened (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Default tail). It is OPTIONAL for a trivial port
(docstring/string/comment-only buckets), but
**MANDATORY whenever the batch grafts a new engine or mechanism** (a shared report engine, a
group-by/total/drill computation, an export/print path, a wizard, any multi-path component) -
a clean merge of one path proves nothing about the others. For a mandatory review:

1. **Enumerate EVERY code path of the grafted mechanism and confirm each was adapted** (for a
   report or compute engine: total, sub-total/group-by, expand/collapse, drill-down, export
   (xlsx/csv), print (PDF/QWeb)). The review is not done until every enumerated path is accounted
   for (adapted, or explicitly N/A with a reason).
2. **Attribution diff before rating any finding.** A finding only belongs to THIS port if
   it sits on a line this port changed. Invoke the `git-toolkit:git-ops` skill (via the Skill tool) for a three-dot diff
   (`origin/<target-branch>...fp/<slug>`) and attribute each finding to either a
   forward-ported line (in scope, fix now) or a pre-existing target line (out of scope). Rate
   findings only after this attribution.

A module that is `installable:False` at the target is in the lint-only lane (`[[fp-installable-false]]`):
the reviewer rates ONLY lint/syntax for it and MUST NOT raise a business-logic finding.

**Acceptance hand-off (consumption clause).** The `odoo-code-review` dispatch above may itself
carry a `next: odoo-acceptance` entry in its own Continuation Contract (Phase A.5 emits this
whenever `render_check_set` reaches beyond the reviewed modules). Do NOT act on it - P11 already ran acceptance for this batch.

NEVER squash (keeps SHA). Only once the review above is addressed does B get anything at all:
open PR now (invoke `git-toolkit:git-ops`). B stays LOCKED - the PR carries the run's merge commit
(one per batch; one in total for a default single-batch run), nothing else.

**Cross-check every static-review bot comment on the PR (post-PR, informational only).** Once the PR
is open and CI has run, read the bot (CI linter / review bot) comments and resolve or consciously
waive each. It runs after PR creation and never gates it.

Present the PR URL, the review findings, and the P11 acceptance verdict together, and wait for the
human to merge.

With the PR presented, document the ported user-visible features for the target the P4 plan approved (`none`: skip this step). Compose a change file `<ISOLATE_DIR>/docs/change-<slug>.md`: one line per ported user-visible feature, with its module and UI label. Module docs: invoke `odoo-doc-illustration` on the target branch's worktree with `CHANGE` = that file and commit the result onto the SAME open PR's branch through `git-toolkit:git-ops` - one PR per repo per run. Site docs: invoke `odoo-doc-site` with `CODE_WORKTREE` = the target worktree, `SERIES` = the target series, `FROM CHANGE` = that file. Both run under the approved plan, with no gate.

## Model triage - two tier tables

**installable:False short-circuit.** Before assigning ANY tier, resolve each touched module's
`installable` flag at the target clean tip by reading `<module>/<tgt-descriptor>` at `target_ref` (the
file P2 wrote to `manifest_path`; an absent key means installable). A module that is
`installable:False` at the target - a brand-new module not yet landed, OR a pre-existing dormant
one - is NOT forward-ported for behavior: route it to the **lint-only lane** (flake8 / pylint /
eslint / prettier / ruff to green CI, minimum fix only) and SKIP the extract/adapt/review logic
tiers entirely. P12 review rates only its lint/syntax. SSOT: `[[fp-installable-false]]`.

**Bucket-(c) upgrade-scale gate.** After P2 classify, estimate each bucket-(c) cluster's adapt size
(source LOC delta + framework-modernisation flag). If it exceeds ~200 LOC of new OWL/JS OR is a full
component/framework rewrite, it is an upgrade-scale RE-IMPLEMENT: RECORD the `upgrade-scale` flag at
P2 and PRESENT the defer-or-do choice at the P4 plan gate - (a) defer (carry `installable:False`,
lint-only lane) or (b) do now (estimate effort, adapt at the ADAPT-table tier). Never silently
absorb unbounded re-implement work; default on no answer is defer. SSOT:
`references/fp-triage-table.md` § Bucket-(c) upgrade-scale gate.

Triage is INLINE and deterministic, run twice with different tables; EXTRACT is resolved PER MODULE
BUNDLE (`references/fp-triage-table.md` Table 1):

- **EXTRACT tier (P0 -> P1 intent extraction, per MODULE bundle):** haiku for a bundle whose every
  commit states its intent by message/PR/tests and stays in this one module, or is
  docstring/comment/string/rename-only; sonnet for a bundle with a commit that needs reasoning -
  logic, a migration, a cross-module change (the default). Resolved as the HIGHEST-priority row ANY
  commit in the module's bundle matches. Neither fable nor opus is in the EXTRACT band, and size
  alone never raises it.
- **ADAPT tier (P8 code adapt, per commit within a module):**
  `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection - except a
  bucket (a)/(d) test-only forward, which is haiku. Table 2 in `references/fp-triage-table.md`.

Resolve a tier by walking each table top-down, first match wins. Record every chosen tier in
`plan.md`. Decide the two tiers INDEPENDENTLY; never reuse one as the other.

## Absorb-all - the ONE git shape, and the only one

**Absorb-all** is this pipeline's ONLY git shape: P5 takes the batch's ENTIRE commit range in ONE
operation as a no-ff no-commit merge of the range TIP, P6-P9 work inside that one open window, and
P10 closes it with ONE commit. Stepping the range one source commit at a time is banned (Hard rule
2), and so is a cherry-pick at any granularity. The SEMANTIC work stays strictly per-commit (P1
intent, P2 bucket, per-commit ADAPT tier and `merge-log.md` rows).

## Checkpoint / resume

`<ISOLATE_DIR>/forward-port/<slug>/checkpoint.json` maps
`{<sha>: extracted | designed | adapted | verified | done}`, with `designed` carrying the
`design_doc` path for any commit P3 routed to `odoo-solution-design`. P0 reads it and skips
`status=done` commits (and resumes a `status=designed` commit at the P4 plan gate with its
recorded `design_doc`, so a crash between design-approval and re-entry resumes correctly). After a
crash mid-batch, re-read the checkpoint + the on-disk `<module>/intents/` per-module
subdirectories, `plan.md`, and `merge-log.md` (file existence is the source of truth).

**Resuming a crash INSIDE the absorption window.** A crash during P6-P9 leaves `MERGE_HEAD`
live and partial adapt on disk; that state IS the resume point: check for it
FIRST (`git -C <path>/fp-integration rev-parse -q --verify MERGE_HEAD`, a bounded read), and when
it is live, RESUME the existing window at the phase `checkpoint.json` last recorded - never re-run
P5 on top of it and never abort it in order to restart the range commit-by-commit. Abort and re-open the WHOLE range only when the window is already gone or
the working tree is unrecoverable, and record that decision in `merge-log.md`. Record the executor's
`INSTANCE_HANDLE` (and its instance log path) in the batch worklog so a resumed run reuses the same
instance or releases it instead of orphaning the DB. A resume in the SAME session reuses the recorded
handle as-is. A resume that spans a session boundary reuses it only through
`lease_find` (state `parked`, this run's `run_id`) -> `lease_adopt` the token that call returns ->
`instance_serve`; `found=false` means the recorded instance is gone - provision a fresh one via
`odoo-instance`, and never release or park the recorded token you did not adopt. You are the run-level owner of the P9 lease
(`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1); release it per § P9 instance release.

## Frontend / i18n / data-XML caveats

- **Frontend (JS/OWL/SCSS).** Route a frontend adapt commit to `odoo-coding` - never hand-translate
  OWL from memory.
- **i18n (.pot / .po).** Do NOT hand-port or re-export translation files in this pipeline. The i18n
  reconcile is MANDATORY, narrow-escape only, per `${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`:
  8e COMPUTES the trigger + already-upgraded conditions per module, P9.5 DISPATCHES `odoo-i18n` once
  the P9 instance exists - it owns the non-destructive `.pot`/`.po` recipe and validates the result.
  Full wiring: `references/fp-phase-detail.md` § 8e, SKILL.md § P9.5.
- **Data XML (`noupdate` records).** A source data record may reference an external-id that does
  not resolve at the target. After merge, verify every external-id in touched data XML resolves
  on the target (P6 covers `ref()` / `xml_id`); a `noupdate="1"` record will not be
  re-written.

Per-batch checks:

- **Multi-repo env bootstrap.** When source and target live in different repos/clones, bring
  the source ref into reach (invoke `git-toolkit:git-ops`: add source remote + fetch) BEFORE computing
  the merge-base or merging. Detail: `references/fp-phase-detail.md`.
- **Manifest version & migration dir.** When the range changes an existing target module's `version` on
  the source, set the target `<tgt-descriptor>` `version` to `max(M + 1, S)` (C1). A forwarded
  `migrations/` dir is RETARGETED to the target series when the target has the problem its script
  solves, else forwarded unchanged (C2) - C1 and C2 are distinct; apply both. SSOT:
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
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`, `describe_module`, `check_module_exists`, `resolve_orm_chain`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**

> **Listing a tool here does NOT license every context to call it.** A bullet carrying a **Caller:** clause is QUALIFIED: that clause names who may issue the call and where, and it overrides this list. Where a phase of this skill assigns the call to a dispatched delegate, the delegate issues it and the orchestrating context records only what comes back.

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

When Odoo Semantic is unreachable: P1 intent extractors fall back to local-source reads
(`${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md`), labelling each record
`grounded: local-source - not OSM-indexed`. P2 classify and P6 symbol-survival
fall back to disk reads of the target checkout per
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md` (read each `<tgt-descriptor>`
`depends` and the model/field source). `odoo-version-diff` standalone mode
supplies the version delta from GitHub release notes when the index is down. Never ask a human
to paste code, field lists, or manifests.

## Continuation Contract

When the run finishes (or pauses at a gate), append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next).
`produced` lists `plan.md`, each touched module's own `<module>/intents/<sha>.md` (§ P1 write path -
never the bare `intents/<sha>.md`), `merge-log.md`,
`<ISOLATE_DIR>/qa/<slug>-acceptance-report.md`, `checkpoint.json`, and the PR
URL; `next` is the human gate the run stopped at (the P4 plan gate, or the P12 PR merge gate that
carries the P11 acceptance verdict). When P3 routes a commit out to design,
`next: odoo-solution-design` with the `inputs` block of `references/fp-phase-detail.md` P3, and the
run YIELDS; the plan runner re-enters forward-port with the returned `design_doc`.
