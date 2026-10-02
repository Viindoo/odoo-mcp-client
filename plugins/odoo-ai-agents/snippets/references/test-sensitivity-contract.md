<!-- Reference material for snippets/test-sensitivity-contract.md. This file is for humans and
     authors doing repo archaeology - it is never cited from any consumer-facing skill/agent/snippet
     body (see docs/authoring-skills-and-agents.md). Explanation and worked examples only; every
     decidable rule stays in the main file. -->

# Test-Sensitivity Contract - rationale and worked examples

## What a test must have, and where each property comes from

A test that cannot be a snapshot of the code needs two properties:

- INDEPENDENCE - its expected values come from the business rule, not from what the code happens to
  do. The topology delivers it: a separate `odoo-test-writer` writes the test, and its brief hands it
  the REQUEST / design AC as the source of every expected value.
- SENSITIVITY - it fails when the rule is wrong. Only an executed run can show this, so the
  break-check alters exactly the rule, runs exactly the guarding tests, and records the assertion
  that fired.

## Why the code comes first

On Odoo a behavior and the vocabulary that names it usually arrive together. A test run before the
model, field or external id exists fails on the missing vocabulary (`KeyError`, `Invalid field`),
not on the rule - a broken measurement that looks like a red. With the code in place, the only way
to make the test fail is to make the rule wrong, which is exactly what the break-check does, and the
failure is guaranteed to be about the rule.

## Why the break-check alters the rule instead of deleting it

Deleting a field, method or model makes every test that names it fail at load time, whether or not
it asserts anything about the rule. Neutralising the rule keeps the code loadable, so the only
remaining failure path is the assertion. That is also why the restore is proved by hash: the
test-writer edits production files temporarily, and a restore that cannot be proved byte-identical
would ship a broken rule.

## Worked example - one rule, three change kinds

Rule: "a sale order over 100M is locked."

- New behavior (the `is_locked` compute is new): neutralise the compute so it always yields
  `False`; a test confirming a 150M order through the real flow must fail on its
  `assertTrue(order.is_locked)`.
- Altered behavior (threshold moved from 50M to 100M): put the 50M threshold back; a test asserting
  a 75M order stays unlocked must fail on that assertion.
- Bug fix (orders exactly at 100M were not locked): revert the fix hunk; the regression test at
  exactly 100M must fail.

## Related snippets

- `test-behavior-contract.md` - how a single test is arranged (HOW); its "would it still pass with
  the logic deleted?" question is the property the break-check makes executable.
- `test-scope-contract.md` - the single-test run carve-out the break-check relies on.
- `fp-merge-absorption.md` / `fp-intent-4outcome.md` - the forward-port buckets the absorption
  probe classifies.
