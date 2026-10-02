<!-- SSOT snippet: node order (code, then tests), the no-test-leg set, the break-check and its
     records. HOW one test is written: test-behavior-contract.md. Consumers cite
     ${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md § <heading>. -->

# Test-Sensitivity Contract (code first, then a test proven by a real break-check)

## Code first, then the test leg

Inside one node, with NO commit between the coders and the test leg:

1. `odoo-backend-coder` / `odoo-frontend-coder` write the code, never a test; each returns its file
   list, a one-line behavior summary, and `OBSOLETE TESTS: <existing test ids this REQUEST makes
   obsolete | none>`.
2. The coordinator decides the test leg (§ No test leg).
3. Before launching the test-writer, the coordinator records the restore baseline - a hash manifest
   of every production file in the node's module directories (all but `tests/`, `static/tests/`,
   `static/tours/`): `find <module_dir> -type f -not -path '*/tests/*' -not -path '*/static/tours/*'
   -print0 | sort -z | xargs -0 sha256sum > <ISOLATE_DIR>/<node>/prod-hashes.txt`.
4. ONE `odoo-test-writer` per node writes or adjusts the tests - expected values from the REQUEST /
   design AC, never from the code - and break-checks each (§ The break-check). It edits test files
   only, plus `__manifest__.py` solely to register test assets (JS test / tour bundles), reported as
   `MANIFEST TEST ASSETS`. Its `CHANGED CODE` = the node base SHA + the coders' file lists + their
   behavior summaries.
5. Restore proof: the coordinator re-runs the same command and diffs. Any difference outside the
   test paths - other than a reported `MANIFEST TEST ASSETS` manifest - is a restore failure:
   re-dispatch the test-writer, never commit.
6. The integrated run (§ The loop, bounded); then the node is committed ONCE (`COMMIT: self`, a
   plain commit), or nothing is committed and the file list returns (`COMMIT: caller`).

## No test leg

The COORDINATOR decides from the ACTUAL change - the coders' file lists, each file's diff against
the node base read with a bounded read - never from the brief. Skip the test leg only when every
changed file is `comment-only` (comments/docstrings), `prose-rename` (a name inside comment/doc
prose), `formatting` (whitespace/indentation only - reordering fields or elements is observable,
never formatting), `docs` (files no Odoo runtime loads), `translation-text` (`.po`/`.pot` msgstr
only) or `manifest` (only `__manifest__.py` keys: a manifest-only diff needs no test; a file a
manifest key loads is judged by its own diff). Any other runtime-observable edit requires the test
leg. Record the category + file list in the worklog and launch no test-writer.

## The break-check

0. **Baseline.** Run the tests you authored or adjusted, and every existing test you claim as
   COVERED, on the UNBROKEN code: all pass, selected > 0. A test red on correct code is wrong - fix
   it before any break.
1. **Copy + hash.** Before altering a production file:
   `cp <file> <ISOLATE_DIR>/break-check/<relative path>` and record its `sha256sum`.
2. **Break** exactly the rule (§ How to break each change kind) so the result is wrong and the code
   still loads.
3. **Run only the guarding tests, at method granularity:** `instance_build` op `test`, `test_mode`
   `reuse`, `test_tags` `/<module>:<Class>.<method>[,/<module>:<Class>.<method>...]`. Read selected
   and failed from the returned summary (`TESTS_RUN`, the failed count): selected must equal the
   number of tests you targeted.
4. **Restore** by copying each file back; re-hash - every hash must match step 1.

Only the tests you AUTHORED, ADJUSTED or claim as COVERED must go red; an existing test of adjacent
behavior may stay green. A targeted test that stays green guards nothing: strengthen it, re-run.
**Red** = the targeted test FAILS, at an assertion or because its act step raises the business
exception the broken rule produces (an accept-path save that now raises `ValidationError`).
Deleting a field, model, external id or imported symbol to break is banned; neutralising a method
body, or removing a method nothing else references, is allowed. An unproven restore is `BLOCKED`,
naming the file.

**Instance.** Run steps 0 and 3 through `Skill(odoo-instance)` inline on the forwarded
`INSTANCE_HANDLE`, under
`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Test build on a forwarded handle.
`odoo-coder` always forwards one. From any other caller it is optional: without it, write the
tests, run nothing, and return `NEEDS_NEXT: odoo-instance` with
`PENDING BREAK_CHECK: <test ids>`. Never provision an instance for a break-check.

**Database state.** A break that touched an XML/CSV data file leaves broken records in the
database (`data-file: yes` on its record). The next VERDICT on that database comes from a fresh
build when any record says `data-file: yes`; otherwise a `reuse` run is enough.

## Broken measurement is not a red

A failure that never exercised the rule proves nothing - fix it and re-run: `KeyError` on a model;
`Invalid field`; missing external id; `AttributeError` on an undefined method; `ImportError` or a
file missing from `tests/__init__.py`; ParseError / failed install-upgrade; fixture/env error;
0 tests selected, or fewer than you targeted. JS: unregistered component/service, asset build
error, a tour selector that never appears.

## How to break each change kind

`CHANGE KIND` takes exactly one row value per behavior.

| Change kind | Break |
|---|---|
| `new` | neutralise the rule |
| `altered` | put the old rule back |
| `bug fix (fix hunk file:lines)` | neutralise the fix as it stands at those lines (the regression test must fail) |
| `removal` | reintroduce the behavior (the test asserts it is gone) |
| `access` | restore the old rule/domain (the test acts `with_user()`) |
| `performance` | restore the per-record query / exceed the budget |
| `data migration` | skip the migration step |
| `view` (view / QWeb / OWL) | revert the modifier/binding (assert the rendered/behavioral outcome) |
| `refactor` | none - no new test; the touched suite is green before and after |
| `adapt (rule file:lines)` | break the business rule the forwarded test guards, at those lines - never "disable the adapt code" |

## Break-check record

Return exactly these lines; the coordinator rejects a malformed line and re-dispatches:

```
BREAK_CHECK: <module>:<Class>.<method> | broke <file:line> - <rule> | red <assertion file:line | raised <ExceptionType>> | selected <n> | restored sha256 match | data-file <yes|no>
COVERED: <module>:<Class>.<method> - <behavior> | <its own BREAK_CHECK fields>
ADJUSTED: <test> - intent <old> -> <new> per <REQUEST item/AC>
ABSORBED: <test> - probe green on target, no ported code to break
NO NEW TEST: <behavior> - refactor, suite green before and after
MANIFEST TEST ASSETS: <manifest file> - <keys added>
PENDING BREAK_CHECK: <test ids>
```

An `ADJUSTED` line is followed by its test's `BREAK_CHECK`. `ABSORBED` (bucket (a) only,
§ Absorption probe) stands wherever a forwarded test owes a `BREAK_CHECK`. `PENDING BREAK_CHECK`
rides on `NEEDS_NEXT: odoo-instance` when no handle was forwarded (§ The break-check).

## Adjusting an existing test

Extending a partly-protected behavior = ADD a new test method to the existing test class, then
break-check it. ADJUSTED is only for an expectation the REQUEST made obsolete. Never adjust to fit
an unintended result; never relax or delete an assertion to get green (removing a
translated/display text or manifest/name-freezing assertion is cleanup - say so). On a re-dispatch
whose `PRIOR ATTEMPT` names tests you already wrote, do not re-author them: run only their pending
baseline + break-checks (your own earlier tests are never `COVERED`).

## The loop, bounded

Integrated run red: compare each failing test to the REQUEST items first. A test failing on a
symbol the REQUEST or the adapt renamed or removed (`BROKEN TEST-SYMBOLS`), an expectation the
REQUEST explicitly changes, or one whose intent contradicts the REQUEST/AC -> re-dispatch
`odoo-test-writer`. A test for behavior the REQUEST did not change -> code regression, re-dispatch
the coder. Unsure -> the code is wrong. Restore mismatch -> re-dispatch `odoo-test-writer`, never
commit. Max 3 iterations, then `BLOCKED` with evidence. Log each iteration
(`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`).

## Absorption probe (forward-port classification, not a test gate)

For a commit bucketed (a), the node's single test-writer launch runs the probe AFTER the node's
(b)/(c) code is adapted. The merge keeps a cleanly-merged (a) hunk in the tree
(`${CLAUDE_PLUGIN_ROOT}/snippets/fp-merge-absorption.md` § Skip-code-but-still-absorb rule), so
probe with that code out of play: copy + hash (§ The break-check step 1), neutralise the (a)
commit's hunks at the brief's `BUCKET a (hunks file:lines)`, run the forwarded source test, then
restore and re-hash. GREEN -> `ABSORBED`. A load/import error is a broken translation, never a
classification. Fix the test and re-run. The test FAILING, or production code that no longer loads once those hunks
are neutralised, re-buckets to (b)/(c): the coordinator re-dispatches the coder, then the normal
break-check.
