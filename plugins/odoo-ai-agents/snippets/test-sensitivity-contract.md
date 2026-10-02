<!-- SSOT snippet: the code-then-test principles - who writes what, when a test is needed, and the
     real break-check that proves a test guards its rule. HOW one test is written:
     test-behavior-contract.md. Consumers cite
     ${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md § <heading>. -->

# Test-Sensitivity Contract (code first, then a test proven by breaking the rule)

These are principles, not a script. Real changes vary more than any list can foresee: apply each
one with judgment and say what you decided.

## Code first, then the test leg

`odoo-backend-coder` / `odoo-frontend-coder` write production code only - they never author or edit
a test - and return their file lists, a one-line behavior summary, and `OBSOLETE TESTS` (existing
tests the REQUEST makes obsolete, or `none`). Then ONE `odoo-test-writer` per node writes the new
tests or adjusts the existing ones, taking every expected value from the REQUEST / design AC, never
from the code. Nothing is committed between the coders and the test leg.

While the test-writer works it breaks production code on purpose, so nobody else builds, edits or
commits in that node until it returns. It edits test files only, plus `__manifest__.py` solely to
register test assets (a JS test or tour bundle), and says so in its report.

## No test leg

Judge from the actual change (its diff), not from the brief, whether a new test is needed. Comments,
docstrings, formatting, docs, `.po`/`.pot` translations and manifest-only edits normally need none;
a refactor relies on the existing suite staying green. These are examples, not a closed list - a
reordered field or a changed default is behavior, not formatting. When you decide no new test is
needed, say why in one line (report and worklog).

An empty diff never means "no test needed" when the brief carries adapt work (`SOURCE TESTS`, a
bucket-(a) commit, a deferred test leg): those tests are still owed.

## The break-check

A test earns its place only if it FAILS when the business rule it guards is deliberately broken.
Prove it for real, e.g. for "a line discount above 20% is refused":

1. Run the test on the unbroken code: it passes. A test red on correct code is wrong - fix it first.
2. Keep a copy of each production file before you edit it (under your `ISOLATE_DIR`).
3. Break exactly that rule while the code still loads (§ How to break each change kind) - here,
   skip the cap check in the constraint.
4. Run only the affected tests, at method granularity (`test_tags` `/<module>:<Class>.<method>`),
   and watch them fail - on an assertion, or on the business exception the broken rule produces.
5. Restore every file exactly as it was from your copy and confirm it is back (e.g. its
   `sha256sum` matches the copy).

A test that stays green guards nothing: strengthen or replace it, then break-check it again.

**Restore is your own duty.** Never leave production code broken - not on success, not on failure,
not when you stop early. If you cannot restore a file, return `BLOCKED` naming it.

**Instance.** Run through `Skill(odoo-instance)` inline on the forwarded `INSTANCE_HANDLE`
(`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Test build on a forwarded handle);
never provision a new database. With no handle, write the tests, run nothing, and return
`NEEDS_NEXT: odoo-instance` naming the break-checks still owed as method-level tags (e.g.
`PENDING BREAK_CHECK: /sale_cap:TestDiscountCap.test_above_cap_refused`).

**Database state.** A verdict must come from a database that reflects the restored code: re-run with
`-u` (`reuse`); rebuild fresh when a break touched a data file (XML/CSV) or the schema, because
records and columns outlive the file restore. Use judgment.

## Broken measurement is not a red

A failure that never reached the rule proves only that the code is broken. Deleting a field, model,
external id or import to "break" a rule produces exactly that. Typical shapes: `KeyError` on a
model, `Invalid field`, a missing external id, `ImportError` or a test file missing from
`tests/__init__.py`, a ParseError or failed upgrade, a fixture error, 0 tests selected; in JS an
unregistered component or an asset build error. Fix the break and run again.

## How to break each change kind

Break the rule so the test's expected outcome becomes wrong. Examples, not a closed list: a new rule
-> neutralise it; a changed rule -> put the old one back; a bug fix -> undo the fix (the regression
test must fail); a removed behavior -> reintroduce it; an access rule -> restore the old rule or
domain (the test acts `with_user()`); a forwarded / adapted test -> break the business rule it
guards in the target code, never "disable the adapt code". An accept-path test ("a 20% discount is
allowed") is proven by breaking the rule the other way: tighten it so 20% is refused.

## Break-check record

Report briefly, one free-form line per behavior test: the test, what you broke, how it failed, that
you restored it. For example:

    test_above_cap_refused - broke models/sale_order_line.py:42 (cap check skipped) - failed: ValidationError not raised - restored, hash matches

Also say which existing tests already cover a behavior (you broke its rule and they failed), and
which existing tests you adjusted and why. Put the same lines in your worklog entry.

## Adjusting an existing test

Search the existing tests first: a behavior they already cover needs nothing new (break-check them
and report them as covering); a partly covered one gets a new test method in the existing class.
Adjust an existing test only where the REQUEST changed that behavior or renamed a symbol it uses.
Never adjust a test to fit an unintended result, and never relax or delete an assertion to get green
(removing a translated-text or name-freezing assertion is cleanup - say so).

## The loop, bounded

Integrated run red: compare each failing test with the REQUEST. Its expectation was changed by the
REQUEST, or it names a symbol the REQUEST renamed or removed -> re-launch the test-writer. It tests
behavior the REQUEST did not change -> the code regressed: re-launch the coder. Unsure -> treat the
code as wrong. Re-launch a worker fresh and tell it what happened before (`PRIOR ATTEMPT`) and what
is wrong now (the failure evidence). At most 3 rounds, then `BLOCKED` with the evidence. Log each
round (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`).

## Absorption probe

Forward-port only, for a bucket-(a) commit: the node's single test-writer launch runs the probe
AFTER the node's (b)/(c) code is adapted. The merge can leave the (a) commit's own code in the tree
(`${CLAUDE_PLUGIN_ROOT}/snippets/fp-merge-absorption.md` § Skip-code-but-still-absorb rule), so
probe with that code out of play: run the forwarded source test, then restore. Green = absorbed by
core: keep the test and report it absorbed. Red = the commit is really (b)/(c): it is re-bucketed,
the coder adapts it, and the normal break-check follows. A load/import error in the test is a
broken translation, never a classification - fix the test.
