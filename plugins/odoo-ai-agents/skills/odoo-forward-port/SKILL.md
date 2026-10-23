---
name: odoo-forward-port
argument-hint: "[from-series] [to-series] [module/range]"
description: >-
  Ports commits, module docs or docs-site pages from a lower Odoo series to a higher one
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
Every forward-port - code, the docs a module ships (its user guide and App Store page), or the
pages of a docs-site repository - runs HERE, with this one git shape. The repository kind picks
the content lane at P0: an addons repository runs the phases below; a docs-site repository runs
`references/fp-docs-site-lane.md`, which replaces only the content phases.

## Out of Scope

- One isolated change with no source commit to port -> use `odoo-coding`
- A version-to-version API/feature delta only (no merge, no adapt) -> use `odoo-version-diff`
- Reviewing or auditing an existing PR or diff -> use `odoo-code-review`
- A pre-upgrade deprecation sweep of one codebase -> use `odoo-deprecation-audit`
- Same-series single-commit replay (no version jump) -> use `odoo-git-rebase`
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
before any read or git-ops request).

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
   forward-port opens a SINGLE true merge of the range's TIP SHA, left uncommitted (delegated to
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

**WORK tier - NOT used by P8 adapt.** P8 is SERIAL, and P5 opens the run's SINGLE merge of the range tip,
left uncommitted, that only P10 commits, so the merge stays in progress in the integration worktree for the
batch's whole P6-P9 span. P8 8a/8b always adapt DIRECTLY in the integration worktree - never a
per-module child worktree. § P8 gives the brief field: one run-long `Worktree path` naming the
integration worktree. JOB tier is the only worktree tier in this skill.

## The pipeline

**Dispatch-brief skeleton.** Every specialist dispatch below fills `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton (read by path) plus the agent's family delta, with `<SHARE_DIR>`/`<ISOLATE_DIR>` resolved once and passed as literals (`references/fp-phase-detail.md` § Dispatch-brief skeleton).

Run phases in order. Intent + classify + design + the Plan Mode gate ALL precede the merge.
Concurrency for any fan-out follows `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
(Mode B). Full per-phase dispatch briefs, git-ops requests, and worklog templates:
`references/fp-phase-detail.md`.

**Orphan sweep (every run, BEFORE P0 below).**

`find <ISOLATE_DIR>/forward-port/ -mindepth 1 -maxdepth 1 -type d -mmin +43200 -exec rm -rf {} +`

Rule: `${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3.

**P0 - Recon & triage [read-only, NO stop].** Read the Forward-port row of
`${CLAUDE_PLUGIN_ROOT}/snippets/read-before-act.md` first. Parse `$ARGUMENTS` (`source-ref` /
`target-branch` / `--scope` / `--since`); if `source-ref` or `target-branch` is missing, ask once
in a single brief message before any read or git-ops request. Resolve `REPO KIND` from the
repository: a module descriptor anywhere in the tree -> `addons`; none, and a declared docs-site
row whose `remote` or `clone` is this repository -> `docs-site`, whose content phases are
`references/fp-docs-site-lane.md`; neither -> `NEEDS_CONTEXT` naming
`/odoo-ai-agents:odoo-setup docs-site`.

"one-shot" in a request means ONE RUN, never a cherry-pick (Hard rule 2). Read the worklog and `checkpoint.json` (§ Checkpoint, resume and the per-batch caveats), then invoke `git-toolkit:git-ops` (read-only, no worktree) to enumerate the non-merge commits after the merge base up to the source ref, oldest first, with the merge base, the files and the change statistics of each; apply `--scope` / `--since` on the returned list. Full request and the scope-to-path mapping: `references/fp-phase-detail.md` § P0 - range enumeration.

**Record the range ENDPOINTS.** From the filtered, chronologically ordered list, record
`<src-first-SHA>` (oldest) and `<src-tip-SHA>` (newest) in the run's working state; P5 absorbs the
range with them and the P10 commit message spans them. An EMPTY filtered list: report `DONE`
(nothing to forward) and stop; never open a merge window on an empty range.

**Group by MODULE first, then by commit within that module (R2a).** `range.md` (above) lists the touched files
per commit for every commit in the range; map each touched path to its owning
module (same resolution rule as `--scope` above). Build
`module -> [ordered sha list]` (chronological order, oldest first); a commit touching 3 modules
appears in each of the 3 modules' lists. This map is what P1 dispatches over and what Table 1 (EXTRACT
tier) resolves against below.

TRIAGE each MODULE's commit bundle to an EXTRACT model tier INLINE (the per-commit change statistics in `range.md` for the bundle
+ one `find_override_point` probe when override depth matters; never dispatch an agent
to decide a dispatch). Recon only: no gate, no worktree, no branch yet. Triage tier table (module-bundle-scoped): `references/fp-triage-table.md`.

**P1 - Intent extract [PARALLEL, READ-ONLY, MODULE-SCOPED].** ONE PARALLEL UNIT PER MODULE (never per
commit). Pre-step: invoke the
`git-toolkit:git-ops` skill (via the Skill tool; read-only, no worktree)
in a single batch pass to write per-commit dump files - for each commit in the range, a full-patch
commit dump (message + diff) written to `<ISOLATE_DIR>/forward-port/<slug>/commits/<sha>.dump`
(resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`;
substitute the captured absolute path); collect the `{ <sha>: <abs-path> }` map. Include `repo: <main-checkout-root>` in the git-ops dispatch for cross-repo ports.

**BAN (R2b): at most ONE `odoo-intent-extractor` instance per module across the ENTIRE run**, launched by walking the P0 `module -> [ordered sha list]` map with the module's full `commit_dump_paths`, resumed by its id on a retry, never re-launched; the brief's `SLUG` is `<slug>/<module>`, so every record lands under the module's own namespace. Dispatch tier (CHP Tier B fork, the Mode B budget counting modules) and the Tier-C replacement rule: `references/fp-phase-detail.md` § P1 - one extractor per module. Aggregate every returned summary into the P2 queue.

**P2 - Classify + installable-probe [module-first order, per-commit bucket, OSM].** Walk the modules and their commits in the P0 order; ground each commit's symbols at the TARGET (`set_active_version` once, then `api_version_diff` + `model_inspect`, every call with `odoo_version=`) and assign exactly one bucket a/b/c/d per `[[fp-intent-4outcome]]`, one `merge-log.md` row per commit; record the `upgrade-scale` flag on a bucket-(c) cluster that is a re-implement rather than a mechanical port (`## Model triage`), never stopping here. Resolve each module's `installable` from the target CLEAN-TIP descriptor (Hard rule 11) through a read-only git-ops write; dispatch the haiku `odoo-installable-prober` only for a category-3 ambiguity. Detail: `references/fp-phase-detail.md` § P2 - Classify.

Pre-step for EVERY touched module: `git-toolkit:git-ops` (read-only) writes the clean-tip manifest (`manifest_path`) and the source-side descriptor history (`history_dump_path`); the prober's canonical inputs and both paths are in `references/fp-phase-detail.md` § P2 - installable pre-step. Record `installable_false=yes|no` as the module's OWN row in `merge-log.md` - the one field later phases read. Short-circuit and lint-only lane: `## Model triage`; SSOT: `[[fp-installable-false]]`.

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

**P4 - Plan gate [Plan Mode].** The request's one Plan-Mode gate (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request): `EnterPlanMode` BEFORE any branch, worktree or file touch; the MODULE-FIRST plan authored here (never through `odoo-planning`) shows each module's ordered commits with EXTRACT tier, bucket, ADAPT tier, installable routing and design-doc link, the ABSORPTION topology (how many batches and merge commits - the human's one chance to split, default ONE), and the `Docs: <module | site | both | none>` line decided by `odoo-intake`'s Documentation routing facts or by that rule here (`refine: no docs` drops it); `ExitPlanMode` on approve. Then git-ops creates the JOB-tier integration worktree `fp/<slug>` from B (Hard rule 1) and `plan.md` is written as the resume record. Template: `references/fp-phase-detail.md` § P4.

**P5 - Merge, left uncommitted [critical section, in integration; ABSORB-ALL - runs ONCE per batch].**
Invoke the `git-toolkit:git-ops` skill (via the Skill tool) ONCE for the whole batch, absorbing
its ENTIRE commit range in one operation: ONE true merge of `<src-tip-SHA>`, left uncommitted (the batch's
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

**P6 TEST-survival sub-check [MUST - after the production symbol check].** Test code that references a symbol removed at the target is found by a dispatched read-only `Explore` (`model: haiku`), never by calls from this context; its brief (the `tests_covering` / `test_coverage_audit` / `model_inspect` sequence) is `references/fp-phase-detail.md` § P6 TEST-survival. Every broken test symbol goes on the `merge-log.md` per-commit row and into the P8 brief as `BROKEN TEST-SYMBOLS`; such a test is triaged into the same bucket, never forwarded verbatim.

**P7 - Pre-adapt drift scan [MUST, before the behavioral loop].** Two read-only `Explore` lanes (`model: haiku`) catch the static import / grep / AST breaks P6's symbol graph does not (lane 1 over every merged-touched `.py`, production and tests; lane 2 over `tests/` only); you triage each returned finding into a bucket and never leave an auto-merged line referencing a dead symbol. **ACCEPTANCE GATE:** merged test files import and collect cleanly on the target before any adapt starts (`0 failed, N error(s)` is NOT a pass). The VIEW-TOPOLOGY sub-check of a bucket-(b)/(c) commit that lands an `ir.ui.view` routes a hit out through the P3 design gate as a PROPOSAL. Lanes, classes, commands and the predicate: `references/fp-phase-detail.md` § P7; `references/fp-triage-table.md` § Bucket-(c) same-module inherit-view check; SSOT `[[fp-symbol-survival-check]]`.

**P8 - Adapt [code first, then tests; SERIAL per-module; runs INSIDE the batch's single open merge window].**
Adapt the MERGED RESULT module by module, driven by the per-commit intent records - never
re-opening, re-merging or re-staging per source commit; a module touched by several commits is
adapted ONCE against the combined result. Adapt DIRECTLY in the integration worktree
(`<path>/fp-integration`); never a per-module child worktree (§ Git topology). In-window protocol: `[[fp-merge-absorption]]` § Absorption window (inside the ONE no-commit merge).

**R2b at 8b: one coder per module for the whole run.** The first P8 invocation of a module invokes `odoo-coding` without `WORKER_AGENT_ID` and records in `plan.md` the coder id it returns; every later one (a P9 re-adapt, a later batch) carries `WORKER_AGENT_ID: <id>` so `odoo-coding` resumes it; the result is collected per R0 of `${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md`, never the next module before it is in hand. Resume semantics, the cd-on-resume rule and the Tier-C cold fallback: `references/fp-phase-detail.md` § P8 - the coder registry.

- **8a** ground the adapt brief with inline OSM calls (`test_base_classes`, `find_test_examples` on the target; the module's `BROKEN TEST-SYMBOLS`; a bucket-(a) commit's hunk map from a read-only delegate).
- **8b** ONE `odoo-coding` invocation per module (via the Skill tool, never a raw coder) with the FP-ENRICHED brief: `Worktree path: <path>/fp-integration`, `MODE: adapt`, `SOURCE TESTS`, `BROKEN TEST-SYMBOLS`, `BASE CLASS`, `TARGET TEST EXAMPLES`, `INTENT` and `BUCKET` per commit, `COMMIT: caller`, `RUN_ID`, `WORKER_AGENT_ID` (after the first launch), `DESIGN_DOC`, and `CONSTRAINTS` = C1 and C3 of `[[fp-merge-absorption]]` plus the `[[fp-installable-false]]` checklist or `LINT-ONLY`; no `INSTANCE_HANDLE`; a frontend leg grounds against `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`. The forwarded source test is the oracle. Bucket (b): merge + adapt; (c): re-implement on the target idiom; (d): no code; (a): the test leg proves absorption with the commit's hunks out of play, red re-buckets it. The return (file list, verdict, per-test report) goes on the module's `merge-log.md` row.
- **8c** a module `installable:False` at the target (new, or upgraded-then-forwarded) re-sets the flag, comments `auto_install`/`application` and takes the LINT-ONLY lane (`[[fp-installable-false]]`).
Field-by-field brief, the bucket-(a) hunk map and the 8c sub-cases: `references/fp-phase-detail.md` § P8 - 8a, 8b and 8c. 8b writes into the integration worktree; P10 commits.

**P9 - Verify by behavior [PER-BATCH, in integration].** Dispatch `odoo-instance` (Skill tool): provision ONCE with `WORKTREE_PATH: <path>/fp-integration`, then per batch init the affected modules and run the target suite (`GATE_ROLE: node-verify`), reusing the returned `INSTANCE_HANDLE` across batches (`${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md`). Adjudicate from its result block: the whole-module suite green AND every forwarded intent test proven by its node's test leg (a bucket-(a) test confirmed absorbed); an unproven test resumes the module's coder through 8b, never a break of your own. Triage each red as FP-delta (back to the coder with the output) or pre-existing (re-run on the clean target tip); never relax an assertion. Never hand the P9 handle to 8b.

**P9.5 - i18n reconcile [MANDATORY, per batch, own export build].** For every module whose 8e record says `i18n_due: yes`, invoke `odoo-i18n` ONCE with the caller obligations of `${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md` (`WORKTREE_PATH`, `SELF_PROVISION: worktree-addons`, `TARGET LANGUAGES` from the source `.po` names when any); an `escape:<E-id>` module is skipped with its reason; never hand it the P9 instance. Every result is presented at P12.

**P9.6 - Migration dir (C2) [per batch, after P9 is green].** For each module whose range forwards a `migrations/<src-series>.*/` dir, resume its coder through 8b with `CONSTRAINTS` = C2 and the dir list; store the moved files on the module's `merge-log.md` row.

Per-batch protocol, the executor's result block and the P9 triage detail: `references/fp-phase-detail.md` § P9, P9.5 and P9.6.

**P10 - Conclude the merge [self-decided, per batch].** Write `merge-log.md`, then ONE git-ops request with the FULL file list (every module row's `files:` plus P9.5 and P9.6's) to stage and conclude the merge with one commit - the whole range as ONE merge commit, every SHA marked `done` in `checkpoint.json` (a/d included); no human gate (P12 presents it). Confirm the tree is clean with `repo_facts`; a leftover path is recorded for P12, never amended. Brief: `references/fp-phase-detail.md` § P10.

**There is no P5 loop.** A single-batch run reaches P10 exactly once, then P11. Only when the human
split the run into several batches at the P4 plan gate does the pipeline return to P5 - once PER
BATCH, never per commit - with the NEXT batch's range TIP, then P6 -> P7 -> P8 -> P9 -> P10 for that
batch.

**P9 instance release [MANDATORY].** Once the last batch's P10 merge is concluded, you are the run-level
owner of the P9 verify instance (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1): call
`mcp__plugin_odoo-ai-agents_odoo-local__lease_release` with the cached `lease_token` and `run_id`
before P11. Call `lease_park` instead only when a named later step of this run still needs the
database. Never release it between batches - every batch reuses it.

**P11 - End-to-end acceptance [MANDATORY, cluster-wide, narrow escape only, BEFORE P12].** Compute the verify scope with `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-scope.md` over every touched module of `merge-log.md` and invoke `odoo-acceptance` ONCE for the batch: `INPUTS` = the touched set, `scope_hint` = `merge-log.md` + each module's `<module>/intents/<sha>.md`, `odoo_version` = target, `INSTANCE_HANDLE: none provisioned` (never P9's), `ACCEPTANCE` by pointer to the intent records and any P3 design §9 - never the implementation. Skip only for a true dependency leaf with no in-repo dependents and no behavioural surface, recorded in `merge-log.md`. The forward-port is not DONE without ACCEPTED or that recorded escape; the verdict is presented with the P12 merge decision. Output `<ISOLATE_DIR>/qa/<slug>-acceptance-report.md`. Brief: `references/fp-phase-detail.md` § P11.

**P12 - PR + review [runs AFTER P11 acceptance clears].** Push `fp/<slug>` through `git-toolkit:git-ops`, then run `odoo-code-review` inline with `TARGET: worktree:<path>/fp-integration` BEFORE the PR opens: optional for a trivial port (docstring / string / comment-only buckets), MANDATORY whenever the batch grafts a new engine or mechanism - then every code path of the mechanism is enumerated and accounted for, and every finding is attributed by a git-ops diff of this port's lines before it is rated. A module `installable:False` at the target is rated for lint and syntax only. Ignore a `next: odoo-acceptance` the review emits - P11 already ran. NEVER squash: the PR carries the run's merge commit(s) and nothing else; B stays locked. Once the PR is open and CI ran, resolve or consciously waive every review-bot comment (informational, never a gate). Present the PR URL, the review findings and the P11 verdict together and wait for the human to merge. Enumeration list and the attribution rule: `references/fp-phase-detail.md` § P12 - PR and review.

With the PR presented, document the ported user-visible features for the target the P4 plan
approved, per `${CLAUDE_PLUGIN_ROOT}/snippets/docs-after-change.md`: the change file lists the
features of the modules installable at the target (`merge-log.md` `installable_false: no`); a
module `installable_false: yes` keeps the docs the merge carried, untouched.

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
operation as a true merge of the range TIP, left uncommitted, P6-P9 work inside that one open window, and
P10 closes it with ONE commit. Stepping the range one source commit at a time is banned (Hard rule
2), and so is a cherry-pick at any granularity. The SEMANTIC work stays strictly per-commit (P1
intent, P2 bucket, per-commit ADAPT tier and `merge-log.md` rows).

## Checkpoint, resume and the per-batch caveats

`<ISOLATE_DIR>/forward-port/<slug>/checkpoint.json` maps `{<sha>: extracted | designed | adapted | verified | done}`; P0 skips `done` and resumes a `designed` commit at the P4 gate with its `design_doc`. A crash inside the absorption window (P6-P9) is resumed in place - never re-run P5 on top, never restart commit-by-commit - and the recorded P9 `INSTANCE_HANDLE` is reused or adopted through `lease_find` / `lease_adopt`. Frontend commits go to `odoo-coding`; `.pot`/`.po` are reconciled only by P9.5; data-XML external ids are verified on the target after the merge; multi-repo ports fetch the source into reach before the merge base; C1 (manifest version) and C2 (migration dirs) both apply; a renamed label is grounded with `entity_lookup` on the target. Full rules: `references/fp-phase-detail.md` § Checkpoint, resume and the per-batch caveats.

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
