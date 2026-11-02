<!-- Reference for `odoo-git-rebase` P8-P12: conflict loop, symbol-survival and collection gate, adapt, review loop, verify, gate, final review and PR, artifact formats. P0-P7: `rb-phase-detail.md`. -->

# Git-Rebase Pipeline - P8 to P12 execution detail

**Contents:** P8 - Conflict-resolution loop - P8b - Symbol-survival + collection gate - P9 - Adapt + test forward - P9b - Code-review loop - P10 - Verify - P11 - Gate - P12 - Final review + PR - rebase-log.md format - P8-resolved modules - Test-leg reports - intake.md format

All paths are under the integration worktree unless noted. Artifacts live under `<ISOLATE_DIR>/git-rebase/<slug>/` (resolve per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path). Every Odoo Semantic call passes a concrete `odoo_version=`.

## P8 - Conflict-resolution loop

### Conflict-class handling (policy passed upfront in P7 dispatch brief)

The P7 `conflict_resolution_policy` makes git-ops resolve all mechanical conflict classes
before stopping on text-hunk conflicts. Rules:

| File type | Policy |
|---|---|
| `.po` / `.pot` | Take the feature side per `po_policy`; then re-run `odoo-i18n` after the full rebase completes; do NOT hand-merge gettext diffs |
| Binary (PNG, ODS, PDF, etc.) | Prefer feature per `binary_policy`; flag the choice in `rebase-log.md` |
| Generated assets (compiled JS, minified CSS, etc.) | Regenerate from source after the rebase completes per `generated_policy`; do NOT hand-merge generated content |
| Text hunk (Python/XML/JS/SCSS/CSV) | Route to the `odoo-coding` skill per ADAPT tier as described below |

### Conflict-TYPE taxonomy (rename-commit scenarios, Odoo rebases)

CONFLICT-TYPE cases born of module/file renames on the new base, resolved per type:

- **static/binary add/add from a renamed module** (e.g. `static/description/*.png`, generated
  assets duplicated under both the old and renamed module path) -> take the NON-EMPTY side; never
  leave a zero-byte file.
- **modify/delete of a renamed-away module** (the new base deleted/relocated a file the feature
  still edits) -> honor the base's removal of the path (the git-toolkit S10 continue-driver runs
  the deletion), then re-home the intent into the renamed module via the `odoo-coding` skill.
- **rename/rename** (both sides renamed the same file differently) -> keep the new-base name; the
  `odoo-coding` skill ports the feature hunk onto it.

Generic per-path mechanics (deleted-by-one-side, text markers, reuse-resolved, continue-vs-skip):
git-ops owns them (git-toolkit `snippets/git-safety-contract.md` § "S10 - Conflict continue-driver
(canonical)"). Never ask git-ops to skip a commit because no files remain unmerged; a commit is
skipped only when continuing reports that it became empty.

### Resolution-reuse hygiene

Run a single rebase per repo at a time. After the reuse step auto-resolves a conflict, the adapt subagent
MUST still verify the auto-resolved hunk against the commit's intent file. Never let git-ops
continue past a file the reuse step resolved without a symbol check against `intents/<sha>.md`.

### Abort path

If 3 consecutive attempts to continue the rebase fail (coder cannot resolve, or the resolution
reintroduces a conflict), do NOT keep retrying. Invoke git-ops to abort the rebase
(restores <WT_ROOT>/rb-integration to its pre-rebase state = feature tip). Restore state from
`checkpoint.json` (the `rb/<slug>` branch is at the feature tip again; all
`designed`/`extracted` intents are still on disk). Escalate, naming which commit SHA blocked the loop and why.

### Per-conflict dispatch

Loop until the rebase finishes. For each `BLOCKED-CONFLICT` return from git-ops, consume the canonical output fields:
- `conflicted_files: [<paths>]` - the text-hunk files that need semantic resolution.
- `stopped_commit: <sha>` - the SHA the rebase stopped on; use for intent file lookup.

Need to confirm the state? Ask git-ops for the files that still carry conflict markers (and the
tree status) in its reply; do not read it with git yourself.

**Fast-path fallback (missing intent file):** if no `intents/<sha>.md` exists for
`stopped_commit`: invoke
git-ops to write the commit dump to `<ISOLATE_DIR>/git-rebase/<slug>/commits/<sha>.dump`,
then dispatch `odoo-intent-extractor` (rebase MODE, P2 brief with `commit_dump_path:` set)
to create the intent file before proceeding to the coder.

Read the stopped commit's P4 outcome first. Outcome (a) or (d): invoke git-ops to skip the commit
and dispatch nothing else - a bucket-(a)/(d) commit is never sent to `odoo-coding`.
Outcome (b)/(c): dispatch Explore first if context is needed, then the `odoo-coding` skill via the
Skill tool (never raw `odoo-coder` or `odoo-frontend-coder` agents):

```
SKILL: odoo-coding
DISPATCH MODEL: <adapt_tier from plan.md>
TASK: Resolve a rebase conflict for one commit in a same-series Odoo rebase.
SHA: <sha>
INTENT: <ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md
BUCKET: <b | c - the P4 outcome; an (a)/(d) commit is skipped, never sent>
COMMIT: caller   (make NO commit - the rebase is stopped on this commit; return the resolved file
      list, and the caller stages it and continues)
TEST LEG: deferred - P9   (write no test and run no integrated test here; P9 runs this module's
      test leg once the rebase is done)
RUN_ID: <this run's id>
FAILURE_MODE: <from comparison.md>
CONFLICTED_FILES: <the conflicted files git-ops reported - text hunks only; .po/binary/generated handled above>
WORKTREE_PATH: <WT_ROOT>/rb-integration
SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve>
RULE: Resolve to the INTENT recorded at INTENT, using the idiom of the new base.
      Never leave a line referencing a symbol that was renamed/moved at the new base.
      On a module-descriptor `version` conflict (the descriptor filename
      ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md row 6 names for the series),
      keep the new-base ref's `version` field unchanged - a same-series replay never bumps it.
      If the reuse step auto-resolved any file: verify each auto-resolved hunk against INTENT
      before staging - a reused resolution replays text, not intent.
      After resolving: emit a "RESOLVED" status listing the resolved files.
      Caller will invoke git-ops to stage and continue per the stateless-resume recipe.
```

After `odoo-coding` returns RESOLVED: record each module its returned file list touches in
`rebase-log.md` § P8-resolved modules (one `<sha>: <module>, ...` line); P9 runs each module's test leg. Then invoke git-ops to stage the returned file list and continue the
stopped rebase, per the canonical continue-driver (git-toolkit S10, cited in the Conflict-TYPE taxonomy
above) and the stateless-resume recipe in `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.

Loop until git-ops returns `DONE` (rebase complete - proceed to P8b). `BLOCKED-CONFLICT`
continues the loop with the next stopped commit from `stopped_commit`; on 3 consecutive
`BLOCKED-CONFLICT` returns for the same `stopped_commit` without resolution progress, invoke
the abort path above. A plain `BLOCKED` return (non-conflict human-confirm gate) escalates
immediately per the stateless-resume recipe in git-delegation.md.

---

## P8b - Symbol-survival + collection gate

**MUST run before P9.** After the rebase loop finishes (git-ops returns `DONE`), run
symbol-survival analysis over every file touched by the replayed range - conflicted AND
merge-clean-but-feature-touched files.

### Identifying feature-touched files (delegated to git-ops)

Ask git-ops for the sorted list of files the replayed range touches (every file changed after
`<old-base>` up to `<feature-ref>`), written to `<ISOLATE_DIR>/git-rebase/<slug>/touched-files.txt`.
Never read the diff inline.

This list is the file set for the gates below.

### Symbol-survival check (delegated)

Dispatch Explore + OSM `entity_lookup` over the feature-touched files per
`[[fp-symbol-survival-check]]` (`${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md`)
Sections 1-2.5 - adapted for rebase context (record the verdict only):

- Ground: the SHARED-SERIES base HEAD (`<new-base>`) - NOT a cross-version diff.
- For each symbol the replayed range imports, calls, or references: confirm it exists
  at `<new-base>` HEAD with the expected name, type, and module. Seven autosilent break
  classes from `[[fp-symbol-survival-check]]` apply unchanged (renamed, moved, retyped,
  split, merged, removed, now-internal).
- A symbol absent/renamed/retyped at base HEAD is a **BLOCKER**. Resolve each blocking symbol back into
  its 4-outcome bucket (outcome b/c/d typically) and re-stage the file before P9.
- Record all findings in `verify.md` § symbol_survival.

### Import-resolvability gate (pyflakes F821)

Run `pyflakes` over every feature-touched `.py` from `touched-files.txt`. Any `F821` (undefined name)
is a broken import that survived the clean merge and MUST be resolved (4-outcome bucket) before P9.
Check: `[[fp-symbol-survival-check]]` (`${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md`)
Sections 2.5(d) and 2.5(e). Dispatch to `Explore` (read-only) per § Who runs this check; record the
PASS/FAIL verdict only.

```bash
pyflakes <every-feature-touched-.py-from-the-Explore-list>   # any F821 = blocker
```

### Collection acceptance gate (two lanes, both delegated)

Two lanes; record each verdict and never read a diff or log inline.

**Lane 1 - static collection (always; no DB, no server).** After all symbol-survival +
import-resolvability blockers are resolved, dispatch `Explore` (read-only) - the delegate
`[[fp-symbol-survival-check]]` § Who runs this check assigns to this lane - with the
`rb-integration` worktree path, the feature-touched test files, and this command. It returns ONLY
`PASS`, or `FAIL` plus one line per collection error (`<file>::<node> | <error class> | <message>`):

```bash
python -m pytest --collect-only <feature-touched test files>   # zero collection errors
```

**Lane 2 - Odoo collection (only when a feature-touched test subclasses an Odoo database-backed
test class - `TransactionCase`, `HttpCase`, or another the series ships, per Odoo Semantic
`test_base_classes`).** Never run `odoo-bin` for this yourself and never have `Explore` run it: invoke the `odoo-instance` skill (via the Skill tool) with:

```
OPERATION: run-tests
GATE_ROLE: node-verify
SERIES: <series>
RUN_ID: <this run's id>
WORKTREE_PATH: <WT_ROOT>/rb-integration
SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve>
MODULES: <the modules owning those test files, dependency order>
TEST_TAGS: </<m> per module in MODULES, comma-joined - never untagged>
MODE: fresh
```

`odoo-instance` returns the `instance-ops` block. Lane 2 PASSES only on `status: tests-passed` or `tests-passed-with-warnings`
with `failed` and `errors` both 0 and every module in `modules_installed`; `tests-failed`,
`tests-inconclusive` (no proof a suite ran) or any `errors > 0` is a FAIL. Warnings are findings for P9, not a collection failure. Capture the returned
`INSTANCE_HANDLE` as this run's ONE instance: forward it to the P9 briefs and reuse it at P10 B3
(`mode: reuse`) instead of provisioning a second one.

**ACCEPTANCE GATE (HARD):** both lanes that apply must PASS. `0 failed, N error(s)` is **NOT a
pass** (a `setUpClass` crash means the tests never ran). Resolve every error before proceeding to P9 (same gate as forward-port P7).

---

## P9 - Adapt + test forward (per touched module)

For each module whose behavior changed - and for every module listed in `rebase-log.md`
§ P8-resolved modules, whose test leg P8 deferred here - invoke the `odoo-coding` skill (via the Skill
tool) ONCE with the adapt fields below (never raw `odoo-coder` or `odoo-frontend-coder`). Record the node's per-test report
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`) in `rebase-log.md` § Test-leg reports,
one `<module>: <report>` per module. Adapt brief:

```
DISPATCH MODEL: <adapt_tier>
REQUEST: Adapt module <module> and the branch's own tests to the new-base (<new-base branch>) idiom.
MODE: adapt
MODULE SCOPE: <module> @ <WT_ROOT>/rb-integration/<module>
INTENT: <ISOLATE_DIR>/git-rebase/<slug>/intents/<sha>.md - the behavioral oracle (one path per
      replayed sha touching the module)
BUCKET: <per replayed sha touching the module: b | c | d - [[rb-intent-4outcome]]; never a
      bucket-(a) sha: (a) commits are skipped or already on the base, with no code and no test
      to forward (rb-triage-table.md Table 2 short-circuit)>
SOURCE TESTS: <the branch's own test files for this module, in the integration worktree>
BROKEN TEST-SYMBOLS: <the P8b symbol-survival entries that land in those test files | omit when none>
ODOO VERSION: <series>
WORKTREE_PATH: <WT_ROOT>/rb-integration
RUN_ID: <this run's id>
INSTANCE_HANDLE: <the P8b Lane 2 instance-ops block, verbatim - or 'none' when P8b provisioned none>
ADDONS_PATH: <that handle's addons_path, comma-joined - the coder's addons coverage assertion
      reads it; omit with INSTANCE_HANDLE: none>
SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve>
RULE: The node's test leg forwards each source test as the behavioral oracle and adapts its API to
      the new-base idiom (base class, imports, helper signatures). Do NOT write a brand-new test if
      the source commit shipped one - adapt it.
```

Pass the same `INSTANCE_HANDLE` to every `odoo-coding` invocation of this phase and of P9b, and
reuse it at P10 B3 (`mode: reuse`); a consumer runs on it and never releases or parks it
(`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`).

---

## P9b - Code-review loop (in-pipeline; fix-until-clean before verify)

Fix in a loop until no CRITICAL/HIGH remains in the just-adapted diff, BEFORE P10. The final P12
review still runs.

Dispatch (Skill tool):

```
SKILL: odoo-code-review
TARGET: worktree:<WT_ROOT>/rb-integration
SCOPE: the replayed/adapted commits only (the rebase has produced rb/<slug>); attribute every
       finding to a replayed/adapted line - a finding on a pre-existing base line is OUT of scope.
SERIES: <series>
ASK: severity-graded findings (CRITICAL/HIGH/MED/LOW) + corrected version. Odoo-specific failure
     modes (ORM-hook order, singleton, super() safety, N+1, view/XPath) are in scope.
```

Loop + escalate:
1. Read findings. No CRITICAL/HIGH -> gate PASS, write `<sha>: reviewed`, proceed to P10.
2. CRITICAL/HIGH present -> dispatch `odoo-coding` with the findings as the fix brief:
   ```
   ODOO VERSION: <series>
   WORKTREE_PATH: <WT_ROOT>/rb-integration
   RUN_ID: <this run's id>
   SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
   ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve>
   ADAPT TIER: <same tier as the P8 adapt for these files>
   INSTANCE_HANDLE: <the P8b Lane 2 instance-ops block, verbatim - or 'none'>
   ADDONS_PATH: <that handle's addons_path, comma-joined - omit with INSTANCE_HANDLE: none>
   FIX BRIEF: <the CRITICAL/HIGH findings + reviewer's corrected version>
   RULE: fix to the finding's root cause only; do not expand scope; keep tests GREEN.
   ```
   Add the fix's test-leg report to `rebase-log.md` § Test-leg reports, then RE-REVIEW
   (step 1). Record MED/LOW in `rebase-log.md` for P12, do not block on them.
3. Cap = 3 review->fix iterations. 3rd iteration still CRITICAL/HIGH -> STOP, escalate BLOCKED
   with the failing finding + diff. Never relax the severity bar to pass the gate.

---

## P10 - Verify

### range-diff + dup-guard (always)

#### P10 pre-step: git-ops range-diff

Invoke git-ops to produce the range-diff before odoo-diff-comparator:

```
TASK: produce range-diff for rebase outcome verification
result: a commit-by-commit comparison of the original series (the commits after <old-base> up to
  <feature-ref-tip>) with the rebased series (the commits after <new-base> up to <rb-tip>)
output: <ISOLATE_DIR>/git-rebase/<slug>/range-diff.txt
worktree: <WT_ROOT>/rb-integration (rb/<slug> and feature-ref-tip accessible from here)
```

git-ops writes the range-diff output to the file and returns the path.

#### P10 dispatch: odoo-diff-comparator

Dispatch `odoo-diff-comparator` (sonnet):

```
DISPATCH MODEL: sonnet
mode: rebase
verify_mode: true
TASK: Verify the rebase outcome via range-diff and duplicate-behavior guard.
diff_scope: original series (after <old-base> up to <feature-ref-tip>) vs rebased series (after <new-base> up to <rb-tip>)
diff_path: <ISOLATE_DIR>/git-rebase/<slug>/range-diff.txt
intents_dir: <ISOLATE_DIR>/git-rebase/<slug>/intents/
PLAN: <ISOLATE_DIR>/git-rebase/<slug>/plan.md
```

Range-diff read, duplicate-behavior guard and `verify.md` format: the agent's own § Step 3b. Its
Step 4 `duplicate_blockers` field gates whether you may proceed.

### B3 - conditional instance verify

If P8b Lane 2 already provisioned the run's instance, reuse its `INSTANCE_HANDLE` here (`mode: reuse`)
and provision nothing; when a break the test leg ran on this database touched data files or schema,
release that lease and take the verdict from ONE fresh build via the `odoo-instance` skill (`mode: fresh`, same `WORKTREE_PATH`,
modules and test tags). Otherwise provision ONE instance via the `odoo-instance` skill ONLY when the
rebased range touches ANY of:
- A model field add, remove, rename, or type-change
- A stored compute or constraint
- An ORM `create` / `write` / `unlink` override
- A `migrations/` directory
- A test that subclasses `TransactionCase` or `HttpCase`

Skip for pure-frontend (JS/OWL/SCSS), docstring/label/comment-only, or non-DB-stateful ranges.
Decide from `recon.md` commits[].modules[] + P3 comparison metadata.

Capture the `odoo-instance` output block ONCE as the run's `INSTANCE_HANDLE` and forward it as an
`INSTANCE_HANDLE:` field in EVERY downstream verify / coder / test brief. Whenever a brief names a
`WORKTREE_PATH`, have the lease acquired
with `addons_path` naming THAT worktree so the instance loads it, or authorize
`SELF_PROVISION: worktree-addons`. One live instance per run at a time, and you are its run-level owner
(`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1): once every brief that carried the
handle has returned and the P10 verdict is final - BEFORE the P11 human gate, never while a leaf still
holds it - call `mcp__plugin_odoo-ai-agents_odoo-local__lease_release` on its `lease_token` and this
run's run_id. Call `lease_park` instead when the database is still wanted for a likely P11 re-entry
into P9/P10; a re-entry after a release provisions again.
If the odoo-local tools are unavailable, use the allocator CLI documented in ${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-API.md.
Contract: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`. Lifecycle:
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md`. Test conventions:
`${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`. Resolve odoo-bin flags via `cli_help` with
`odoo_version=<series>`.

---

## P11 - Gate (human-confirm)

Present `rebase-log.md` + `verify.md` to the human and ask, as a text question,
`approve / skip / cancel`. STOP. Do NOT push, do NOT open a PR until the human
replies `approve`; `skip` ends the run with the branch unpushed.

---

## P12 - Final review + PR

Order (`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Default tail): review -> push -> open PR.

**Step 1 (FIRST) - final code review of the integration worktree, BEFORE any push or PR.**
Delegate a code review passing `TARGET: worktree:<WT_ROOT>/rb-integration`. Fix CRITICAL/HIGH findings on that worktree (dispatch
`odoo-coding` at the P8 ADAPT tier, the SAME loop shape as § P9b) and review again until none
remains; MED/LOW are recorded in `rebase-log.md`. Only when the review returns no CRITICAL/HIGH do
steps 2-3 run.

**Step 2 - push.** Resolve the upstream org/repo from the `origin_url`, and the fork remote name from
the `remotes`, of a `repo_facts` call on `<WT_ROOT>/rb-integration` (the remote other than origin that
branches are pushed to; none or several -> ask the user once). Never hardcode the fork remote or upstream repo.

Invoke the `git-toolkit:git-ops` skill (via the Skill tool) to push rb/<slug> to the fork remote:

```
op: push rebase branch to fork (never to the upstream directly)
scope: rb/<slug>
worktree: <WT_ROOT>/rb-integration
remote: <fork-remote-name>  # resolved from the repo_facts remotes
confirmed: yes - human approved at P11
```

**Step 3 - open the PR.** Invoke git-ops to open the PR:

```
op: create PR for rebase result
upstream_repo: <org>/<repo>  # resolved from origin URL
base: <new-base>
head: <fork-remote-name>:rb/<slug>
title: rb(<slug>): <one-line summary of the feature intent>
body:
  ## Summary
  Rebase of <feature-ref> onto updated <new-base> (same-series semantic translation).

  ## Outcome summary
  | sha | subject | outcome |
  |-----|---------|---------|
  <rows from rebase-log.md>

  ## Verify result
  range_diff_verdict: <pass|warn|fail>
  duplicate_findings: <none | list>

  ## Design docs
  <links if P5 fired, else "none">
```

**After the PR opens, only PR-OBSERVING work remains** (CI-failure triage, the human merge). Do NOT
delegate another worktree code review. Wait for human merge. NEVER squash commits; never rewrite
commit messages (an outcome-(a) skip records the reason in `rebase-log.md`).

---

## rebase-log.md format

```markdown
# Rebase log - <slug>

| sha | subject | outcome | failure_mode | evidence | adapt_tier | status |
|-----|---------|---------|-------------|---------|-----------|--------|
| abc1234 | add double-post guard | (b) | renamed | `_post`->`action_post` at `account/models/account_move.py:123` | sonnet | resolved |
| def5678 | fix typo in docstring | (a) | already-present | patch-id match on new-base | haiku | skipped |
| ghi9012 | OWL widget refactor | (c) | override-refactored | `ListRenderer` replaced by `ListController` | fable | designed |

## P8-resolved modules

<sha>: <module>, ...   (the modules a P8 conflict resolution touched; each gets a P9 test leg)

## Test-leg reports

<module>: <the P9 / P9b test leg's brief per-test report: what it broke, how the test failed>
```

---

## intake.md format

```yaml
feature_ref: <series>-feat-double-post-guard
feature_worktree_path: <WT_ROOT>/rb-feature-<slug>
new_base: <series>
same_series_ok: true
pr_resolved_from: https://github.com/<org>/<repo>/pull/482
branches_to_materialize: []
open_questions: []
```

---
