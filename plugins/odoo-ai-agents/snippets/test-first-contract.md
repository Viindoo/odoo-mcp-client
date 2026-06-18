<!-- SSOT snippet. Referenced (not copy-pasted) by odoo-coding (orchestrates the loop),
     odoo-coder / odoo-frontend-coder (implement to green), odoo-test-writing (authors the red
     test), and odoo-code-review (gates coverage + loops back). Edit here only; consumers point
     at ${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md. -->

# Test-First Contract (red before green, behavior not snapshot)

The test comes BEFORE the code and protects the **business behavior**, not the current
implementation. A test written after the code, to match whatever the code happens to
do, is a change-detector: it passes always, catches no bug, and turns every honest refactor into a
false alarm. This contract makes the test a falsifiable specification of intent.

## The red-before-green sequence

1. **Author the test from the business rule** - phrase it as the rule it protects ("an order over
   100M is locked"), assert only **observable outcomes** (return value, state change, contract-level
   side effect), never internals (private method, call counts, variable names). One intent + one
   expected outcome per test. For the version-correct framework and class (`TransactionCase` /
   `Form` / Hoot / QUnit) and OSM grounding, follow `skills/odoo-test-writing/SKILL.md` and
   `docs/reference/ODOO-TESTING.md` - this contract governs the discipline, that governs the shape.
2. **Confirm it goes RED** - the test MUST fail before the production code exists (or with the rule
   removed). A test that can only ever be green is worthless. State the RED confirmation as evidence
   (the failing assertion / the absent behavior).
3. **Write the minimum code to go GREEN** - implement until the test passes, nothing speculative.
4. **Never edit the test to fit the code.** If a test fails after coding, apply the root-cause rule:
   understand intent first. Fix the code if the code is wrong; change the test only if the test's
   *intent* was wrong - and say so explicitly. Banned: relaxing/deleting assertions, changing
   expected values to match actual output, `@skip`/comment-out to get a green pipeline.

## Hybrid authorship (who writes the red test)

- **Non-trivial module** (per the design gate): a **separate** test-author writes the red test
  first, so the author of the test is not the author of the code - independence keeps the test
  honest. The code-author then implements to green and must not touch the test.
- **Trivial module** (single field, boilerplate, one-approach fix): the coder writes the red test
  itself, then the code - the round-trip of a separate author is not worth it at that size.

## The loop, bounded

`code -> review + test -> code`: after code goes green, review runs and the tests run. If review
finds CRITICAL/HIGH issues OR a test is red, loop back to code. Bound the loop to **3 iterations**;
if still not green-and-clean, STOP and escalate - bad work is worse than no work. Record
each iteration's outcome in the worklog (`worklog-contract.md`).
