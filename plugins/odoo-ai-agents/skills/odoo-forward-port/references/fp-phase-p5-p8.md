<!-- Reference for `odoo-forward-port` § The pipeline. -->

# Forward-Port Pipeline - P5 to P8 (merge, symbol survival, drift scan, adapt)

**Contents:** P5 - P6 - P7 - P8 (8a, 8b, 8c and 8c-bis, 8e)

All paths are under the integration worktree unless noted. `<slug>` derives from the
source/target series (`<source-series>-to-<target-series>`). Artifacts live under
`<ISOLATE_DIR>/forward-port/<slug>/` (gitignored; resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path). Every Odoo Semantic call passes a concrete
`odoo_version=` (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § OSM session-pin race).


---

## P5 - Merge, left uncommitted (critical section) - ABSORB-ALL, runs ONCE per batch

Invoke the `git-toolkit:git-ops` skill (via the Skill tool) ONCE for the batch's ENTIRE commit
range. Dispatch contract: `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`.
For semantic conflicts use the stateless-resume recipe in that snippet.

`<src-tip-SHA>` = the batch's LAST (newest) source commit after the `--since`/scope filter;
`<src-first-SHA>` = its first. Resolve both from the P0 range map before dispatching.

```
# one merge of the range TIP
op: merge the source range ending at <src-tip-SHA> into the integration worktree as ONE true merge,
    and stop before committing it (never a cherry-pick or a rebase)
worktree: <path>/fp-integration
```

To land only PART of a source branch, pass that sub-range's TIP as `<src-tip-SHA>`. A cherry-pick is
never the answer here (`SKILL.md` Hard rule 2).

**Never iterate this phase per source commit** (`SKILL.md` Hard rule 2). Only one merge in flight.
Do NOT commit - the working tree is the absorption zone for the whole range through P9. Full protocol incl. absorption window order:
`[[fp-merge-absorption]]`.

---

## P6 - Symbol-survival check (MUST, before adapt)

**Dispatched, never run inline** (`[[fp-symbol-survival-check]]` § Who runs this check). Sequence
the dispatches and record what comes back; do NOT run the conflict scan, the file enumeration, or
the OSM grounding in this context.

1. Invoke the `git-toolkit:git-ops` skill (via the Skill tool) for the conflict-marker scan AND the
   list of files the ported range changed (everything after `merge_base` up to the source SHA) in
   ONE dispatch (git-ops writes both to a findings file, filtered to non-empty entries, and returns
   the path). For cross-repo ports include
   `repo: <main-checkout-root>`.
2. Dispatch `Explore` (read-only, `model: haiku` on the launch) over that returned file list to ground every Odoo symbol it
   references (field / method / model / view ref / external-id / manifest depend / ORM chain)
   against the TARGET version, per `[[fp-symbol-survival-check]]` sections 1-2.5. Never issue the OSM
   calls here.
3. Record only what the delegate returns: any absent/changed symbol FORCES bucket b/c/d and bans
   leaving the auto-merged line unchanged; the `SYMBOL-BROKEN | <symbol> | <file>:<line> | bucket |
   evidence` finding list (an empty list `SYMBOL-SURVIVAL: clean` is a valid, desirable result); and
   the PASS/FAIL verdict. A non-empty list BLOCKS P8 on those files. Full contract:
   `[[fp-symbol-survival-check]]`.

**Run on `tests/` files too.** Apply the seven auto-merge-silent symbol classes from
`[[fp-symbol-survival-check]]` section 2.5; feed test files from the enumeration above through the
same grounding, do not filter them out.

---

## P7 - Pre-adapt drift scan (MUST, before the behavioral loop)

P7 is distinct from the P6 TEST-survival sub-check (OSM `tests_covering` / `test_coverage_audit`).
P7 uses the seven static symbol classes from `[[fp-symbol-survival-check]]` section 2.5 over two
lanes: (d) python-import + (e) AST-pyflakes + (g) ORM create/write dict-key run over ALL
merged-touched `.py` (production AND `tests/`); the remaining classes (a)(b)(c)(f) and the
collection ACCEPTANCE GATE apply to the `tests/` lane only. P7 blocks entry to P8 when test
collection itself would fail.

**Enumerate scope - two lanes. Dispatched, never run inline** (`[[fp-symbol-survival-check]]`
§ Who runs this check):

Invoke the `git-toolkit:git-ops` skill (via the Skill tool) to list the files the ported range changed (everything after `merge_base` up to the source SHA;
git-ops writes the file list). Include `repo: <main-checkout-root>` in the dispatch for
cross-repo ports. From the returned list the delegate derives:

- **Lane 1** - ALL merged-touched `.py` (production AND `tests/`): the `*.py` entries.
- **Lane 2** - `tests/` only: the Lane-1 entries whose path contains `tests/`.

Dispatch the gates as read-only delegates and record only their verdict (delegate per class:
`[[fp-symbol-survival-check]]` § Who runs this check): the git-ops dispatch above enumerates the
files, and `Explore` (`model: haiku` on the launch) runs every static lane below. Lane 1
gets classes (d) + (e) (`py_compile` + `pyflakes`) AND (g) (ORM create/write
dict-key scan) over ALL .py - production AND tests; Lane 2 additionally gets (a) (b) (c) (f). Treat
F821 on a production file, and a (g) dead key on a production call site, as blockers.

Record findings as `SYMBOL-BROKEN | <symbol/path> | <file>:<line> | <class> | evidence` and
append to `merge-log.md`. Triage each returned finding into a bucket (b adapt / c re-implement /
d drop); never leave an auto-merged line referencing a dead symbol. These become the
`BROKEN TEST-SYMBOLS` input to the P8 adapt brief.

**ACCEPTANCE GATE (collection clean) - mandatory before P8 starts:**

The gate is a `pytest --collect-only` run over the merged test files (no DB). Dispatch it to `Explore` (read-only, `model: haiku` on the launch), the delegate
`[[fp-symbol-survival-check]]` § Who runs this check assigns to this class. Brief it with: the
integration worktree path, the merged test file list Lane 2 produced, the exact command
`python -m pytest --collect-only <those files>`, and the instruction to return ONLY `PASS`, or
`FAIL` plus one line per collection error (`<file>::<node> | <error class> | <message>`) - never the
raw log. Record that verdict; never run the command, or read its log, in the orchestrating context.

**No ad hoc provisioning, in any phase.** When a `setUpClass` performs DB-dependent work that
`--collect-only` cannot exercise, do NOT acquire an ad hoc DB here - the ONLY provisioning path is
P9's `odoo-instance` dispatch. Record the residual as an open ACCEPTANCE GATE item on that test
file's `merge-log.md` row; P9's own run-tests result for that file is its true confirmation. The
`--collect-only` verdict still blocks P8 for every OTHER file it covers.

A collection failure means the tests NEVER RAN - `0 failed, N error(s)` is NOT a passing result.
Resolve every drift finding (P7 SYMBOL-BROKEN entries) before entering the P8 adapt loop.

**View-topology sub-check (bucket-(b)/(c) same-module inherit stacks).** Runs once a bucket-(b) OR
bucket-(c) commit's own adapt step lands or modifies an `ir.ui.view` record (INCLUDING a clean
auto-merge with no conflict marker), at the 8b adapt point; a finding line is triaged into
`merge-log.md` and confirmed before P10 commits. Buckets (a)/(d) are out of scope. A HIT is a
PROPOSAL only: the merge-and-delete outcome routes out through the P3 design gate to
`odoo-solution-design` and is applied solely when the returned `design_doc` adopts it. Full
predicate, the two non-defect exceptions, and the merge-unsafe escape: `references/fp-triage-table.md`
§ Bucket-(c) same-module inherit-view check.

---

## P8 - Adapt (code first, then tests; serial per-module; ALWAYS directly in the integration worktree)

Adapt the MERGED RESULT module by module, driven by the per-commit intent records; never re-open,
re-merge, or re-stage per source commit. Dispatch the adapt unit DIRECTLY in the integration
worktree (`<path>/fp-integration`) and process modules serially; a module touched by several commits
is adapted ONCE, against the combined merged result. Never create a per-module child worktree.

**Open-merge window.** From P5 (the merge left uncommitted) through P10 (its commit), the merge stays in progress in the
integration worktree: ONE window per batch, opened by P5 and closed only by P10. SSOT:
`[[fp-merge-absorption]]` § Absorption window (inside the ONE uncommitted merge).

**One `odoo-coding` invocation per module.** Code is adapted FIRST, then the node's single test leg
forwards and adapts the module's source tests, proves each FP-delta test by breaking its rule, and
confirms absorption for each bucket-(a) commit
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`). Launch no test author of your own.

**8a - ground the adapt brief.** Resolve the test-leg enrichment lines BEFORE the invocation:

```python
test_base_classes(odoo_version='<target_version>')                           # BASE CLASS (target)
find_test_examples(query='double-post guard on account.move', odoo_version='<target_version>')  # TARGET TEST EXAMPLES
```

ADAPT RULE for the base class: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 3;
`cr.commit()` is FORBIDDEN in tests. `find_test_examples` takes an optional `model=` and `kind`
`'transaction'` | `'http'` | `'form'` (or `'js'` for JS tests), never `'python'`.

`BROKEN TEST-SYMBOLS` is the subset of the P6 symbol-survival findings (plus any P7 drift finding) whose
`<file>` is one of this module's test files - copy those rows in verbatim; omit the line when empty.

**Bucket-(a) hunk map.** P5's merge keeps every cleanly-merged hunk of a bucket-(a) commit in the working
tree (`[[fp-merge-absorption]]` § Skip-code-but-still-absorb rule); the test leg takes those hunks
out of play first. For each bucket-(a) commit touching this module, dispatch `Explore` (read-only, `model: haiku` on the launch) with its commit dump
(`<ISOLATE_DIR>/forward-port/<slug>/commits/<sha>.dump`) and `<path>/fp-integration`; it returns each hunk
as `<file>:<start>-<end>` in the merged tree, `conflicted` when the hunk sits inside conflict markers, or
`absent` when the merge left no trace of it (the target already carried the identical change). Carry the
result and the dump path on that commit's `BUCKET` line.

**8b - adapt the module** per bucket. The forwarded source test IS the oracle: adapt it in place; write
one from scratch only when the source commit shipped none, anchored to the intent record
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`). A frontend leg grounds against
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`. Invoke the `odoo-coding` skill (via the Skill tool) with the
FP-ENRICHED brief (never raw `odoo-coder` or `odoo-frontend-coder`). **R2b at this leg: at most one
coder per module across the WHOLE run.** On the module's FIRST invocation omit the field and record
the coder's agent id `odoo-coding` reports in `plan.md`; on every LATER one carry it as
`WORKER_AGENT_ID: <id>` - never a string anyone invented; `odoo-coding` resumes that id
(`references/fp-phase-briefs.md` § P8 - the coder registry and the resumed coder (R2b)). The brief is identical on a fresh launch or a resume, and the Worktree path
never changes:

```
DISPATCH MODEL: <adapt-tier>
REQUEST: Adapt the forwarded intent to the target platform - code first, then the node's test leg
      forwards the SOURCE TESTS below. On a re-adapt, append the P9 failure output.
MODE: adapt
INTENT: <ISOLATE_DIR>/forward-port/<slug>/<module>/intents/<sha>.md   (one path per source
      commit in this batch touching the module; build to this, not the source diff)
BUCKET: <per sha: a (hunks <file>:<start>-<end>[ conflicted][, ...] | absent; dump <path>) - no
      adapt code: leave the clean hunks as merged, resolve a `conflicted` one to the TARGET side; the
      test leg runs the source test with the clean hunks out of play | b 3-way+adapt | c re-implement
      on target idiom | d skip-code>
SOURCE TESTS (READ/WRITE, in the integration worktree): <path>/fp-integration/<module>/tests/<test_file>[, ...]
      (merged working-tree content; for bucket (b) it may still carry conflict markers - the test leg
       resolves IN PLACE and writes the adapted result back to the SAME path. A bucket-(a) sha's source
       test is its absorption check; a re-bucket it reports goes on that sha's `merge-log.md` row)
BROKEN TEST-SYMBOLS: <the P6 / P7 SYMBOL-BROKEN entries that land in this module's test files -
      repair each, never forward them verbatim>
BASE CLASS (target): <signature from test_base_classes(odoo_version='<target>') for each source
      test's base class - the kwargs the target setUpClass/setUp actually accepts>
TARGET TEST EXAMPLES: <1-2 paths from find_test_examples(query='<feature>', odoo_version='<target>')
      that already test this behavior the target-idiomatic way>
COMMIT: caller   (make NO commit - the batch's merge window stays open; return the file list and
      the test leg's report; P10 commits the batch)
NEW MODULE: <yes | no>
DESIGN_DOC: <path from plan.md's design_doc column for this commit | none>   (P3's route-out result)
MODULE SCOPE: <name>
  READ/WRITE (in the integration worktree, no separate child worktree): <path>/fp-integration/<module>/
    (merged content; for bucket (b) 3-way+adapt start from these files - they hold the
     auto-merged or conflict-marked state - and write ALL output back here, in place)
ODOO VERSION: <target>
WORKTREE_PATH: <path>/fp-integration   (the ONE root this dispatch works in; pass no
  INSTANCE_HANDLE)
RUN_ID: <this run's id>
SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR: <the run's captured absolute ISOLATE path - the SAME literal INTENT above was
  built from; never re-resolve>
WORKLOG: <slug> - read, then append.
CONSTRAINTS: C1 manifest version; C3 carry pre-existing source bugs faithfully, never inline-fix -
  ${CLAUDE_PLUGIN_ROOT}/snippets/fp-merge-absorption.md
  [+ NEW MODULE yes: apply the installable:False checklist - ${CLAUDE_PLUGIN_ROOT}/snippets/fp-installable-false.md]
  [+ LINT-ONLY: the module is installable:False at the target - fix syntax/lint breakage only,
     adapt no business logic (8c-bis) - ${CLAUDE_PLUGIN_ROOT}/snippets/fp-installable-false.md]
WORKER_AGENT_ID: <id recorded for this module on its first invocation this run>   (omit on the
      module's FIRST invocation)
USER LANGUAGE: <lang | omit when English>
```

Return: the file list, the integrated verdict and the test leg's brief per-test report. Store them on the module's own `merge-log.md` row: the file list as `files: <path>, ...` (P10 stages
exactly this union), the test leg's brief per-test report (what it broke, how the test failed - one short
line each, free form), and any re-bucket the node reports as the new bucket + reason on that sha's row.
P9 adjudicates the report.

**8c - installable:False modules (LINT-ONLY lane)** - two sub-cases, same manifest action, both then
lint-fix only. (i) **New module** (absent at target): `installable: False`, comment
`auto_install`/`application`. (ii) **Upgraded-then-forwarded** (target clean-tip =
`installable:False` but merge carries `True`): re-set to False + re-comment `auto_install`/`application`
with `# TODO: Uncomment when upgrading module to production-ready status` breadcrumb BEFORE
dispatching the coder. SSOT: `[[fp-installable-false]]`.

**8c-bis - confirm the target flag, then brief lint-only.** BEFORE dispatching the coder/reviewer
for any module, confirm its target installable flag. Re-read
`<module>/<tgt-descriptor>` at `target_ref` (via git-ops, read-only) only if the manifest was touched
by the merge; otherwise reuse the value P2 already resolved from `manifest_path`. If
`installable: False` at the target, brief
the coder in **lint-only mode**: run flake8 / eslint / prettier / ruff and fix ONLY syntax/lint
breakage to keep CI green - do NOT adapt business logic, do NOT upgrade content. Add the
`LINT-ONLY` clause to the 8b brief's `CONSTRAINTS` field, with the pointer
`[[fp-installable-false]]`. The single exception to "no logic change" is a syntax/lint error that
itself blocks the file from parsing. SSOT: `[[fp-installable-false]]`.

**8e - i18n: COMPUTE and RECORD; the dispatch happens at P9.5.** Do NOT dispatch `odoo-i18n` here.
Evaluate both mandate conditions now and record them on the module's `merge-log.md` row:

1. **Condition 1 - translatable delta.** Run the 8-signal trigger table over this batch's
   `<ISOLATE_DIR>/forward-port/<slug>/commits/<sha>.dump` files. Record
   `i18n_signals: [<fired ids>]` or `i18n_signals: none`.
2. **Condition 2 - already live at the target.** Read `installable_false` from this module's
   `merge-log.md` row. Record `i18n_due: yes|no|escape:<E-id>`.

Both conditions and the escape table: `${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md`.
Carry `i18n_due` forward to P9.5. No convergence or worktree removal step here. Mark `status=adapted`.

---
