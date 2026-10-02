<!-- SSOT snippet: node order (code, then tests), the no-test-leg set, the break-check. HOW one
     test is written: test-behavior-contract.md. Consumers cite
     ${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md § <heading>. -->

# Test-Sensitivity Contract (code first, then a test proven by a real break-check)

## Code first, then the test leg

Inside one node: (1) `odoo-backend-coder` / `odoo-frontend-coder` write the code, never a test, and
each reports `OBSOLETE TESTS: <existing test ids this REQUEST makes obsolete | none>`; (2) the
coordinator checkpoints the code; (3) it decides the test leg from the actual diff (§ No test leg);
(4) ONE `odoo-test-writer` per node writes or adjusts the tests - expected values from the REQUEST /
design AC, never from the code - and break-checks each; (5) restore proof: every production file
byte-identical to the checkpoint; (6) the integrated run (§ The loop, bounded).

## No test leg

The COORDINATOR decides from the ACTUAL diff (`git diff --name-only` since the checkpoint/base, a
bounded read), never from the brief. Skip the test leg only when every changed file is
`comment-only` (comments/docstrings), `prose-rename` (a name inside comment/doc prose),
`formatting` (whitespace/ordering; parsed tree unchanged), `docs` (files no Odoo runtime loads),
`translation-text` (`.po`/`.pot` msgstr only) or `manifest` (only `__manifest__.py` keys). Any
other runtime-observable edit requires the test leg. Record the category + file list in the worklog.

## The break-check

Per business rule guarded by a new or adjusted test:

1. `sha256sum` each production file you will alter.
2. Alter EXACTLY that rule so the result is wrong and the code still loads.
3. Run only the guarding tests on the forwarded `INSTANCE_HANDLE`
   (`--test-tags /<module>:<Class>.<method>[,...]`, selected > 0) - each must fail ON THE ASSERTION.
4. Restore the file(s); re-run `sha256sum` - every hash must match step 1.

One run per broken rule, with every test guarding it. A test that still passes guards nothing:
strengthen it, re-run. Never provision an instance for it: no handle -> write the tests, return
`NEEDS_NEXT: odoo-instance`, break-checks pending. An unproven restore is `BLOCKED`, naming the file.

## Broken measurement is not a red

A failure that never reached the assertion proves nothing - fix it and re-run: `KeyError` on a
model; `Invalid field`; missing external id; `AttributeError` on an undefined method; `ImportError`
or a file missing from `tests/__init__.py`; ParseError / failed install-upgrade; fixture/env error;
0 tests selected. JS: unregistered component/service, asset build error, a tour selector that never
appears. Breaking a rule by deleting a symbol manufactures these - banned.

## How to break each change kind

| Change kind | Break |
|---|---|
| New behavior | neutralise the rule |
| Altered behavior | put the old rule back |
| Bug fix | revert the fix hunk (the regression test must fail) |
| Behavior removal | reintroduce it (the test asserts it is gone) |
| Access / security | restore the old rule/domain (the test acts `with_user()`) |
| Performance | restore the per-record query / exceed the budget |
| Data migration | skip the migration step |
| View / QWeb / OWL | revert the modifier/binding (assert the rendered/behavioral outcome) |
| Refactor (behavior preserved) | none - no new test; touched suite green before and after |
| § No test leg categories | none |

## Break-check record

Each behavior test returns exactly one line:

`BREAK_CHECK: <test node id> | broke <file:line - rule> | failed at <assertion> | selected <n> | restored <sha256 match>`

## Adjusting an existing test

Only when the REQUEST makes the old expectation obsolete: state
`ADJUSTED: <test> - intent <old> -> <new> per <REQUEST item/AC>`, then break-check it. Never adjust
to fit an unintended result; never relax or delete an assertion to get green (removing a
translated/display text or manifest/name-freezing assertion is cleanup - say so).

## The loop, bounded

Integrated run red: a test for behavior the REQUEST did not change -> code regression, re-dispatch
the coder; an expectation the REQUEST explicitly changes, or whose intent contradicts the
REQUEST/AC -> re-dispatch `odoo-test-writer` (it re-runs its break-check); unsure -> the code is
wrong; restore mismatch -> re-dispatch `odoo-test-writer`, never commit. Max 3 iterations, then
`BLOCKED` with evidence. Log each iteration (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`).

## Absorption probe (forward-port classification, not a test gate)

For a commit bucketed (a) (absorbed by target core), the adapt test leg forwards its source test and
runs it BEFORE any adapt code. GREEN confirms (a): keep the test as a core regression
guard, no break-check owed (no ported code to break). FAIL ON THE ASSERTION re-buckets to (b)/(c):
adapt the code first, then the normal break-check. A load/import error is a broken translation,
never a classification.
