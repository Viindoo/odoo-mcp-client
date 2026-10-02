<!-- Reference material for snippets/test-sensitivity-contract.md. This file is for humans and
     authors doing repo archaeology - it is never cited from any consumer-facing skill/agent/snippet
     body (see docs/authoring-skills-and-agents.md). Explanation and worked examples only; every
     rule stays in the main file. -->

# Test-Sensitivity Contract - rationale and worked examples

## What a test must have

- INDEPENDENCE - its expected values come from the business rule, not from what the code happens to
  do. A separate `odoo-test-writer`, briefed with the REQUEST / design AC, delivers it.
- SENSITIVITY - it fails when the rule is wrong. Only an executed run shows this, so the
  break-check breaks exactly the rule and watches the test fail.

## Why the code comes first

On Odoo a behavior and the vocabulary that names it usually arrive together. A test run before the
model, field or external id exists fails on the missing name (`KeyError`, `Invalid field`), not on
the rule. With the code in place, the only way to make the test fail is to make the rule wrong.

## Why break the rule instead of deleting code

Deleting a field, method or model makes every test that names it fail at load time, whether or not
it asserts anything about the rule. Neutralising the rule keeps the code loadable, so the only
remaining failure path is the assertion.

## Why principles, not a record grammar

A parsed record grammar, a coordinator-side hash manifest and a closed change-kind list add steps an
agent skips under load and prose a reader cannot hold, while real changes keep falling outside any
closed list. So the contract states each principle once with its intent and an example; the
test-writer owns its own restore and reports in free form.

## Why a data-file break needs a fresh build

Python code is reloaded on every run, but records loaded from an XML/CSV file stay in the database
after the file is restored, so a later `-u` run reads the broken record back.

## Worked example - one rule, three change kinds

Rule: "a sale order over 100M is locked."

- New behavior: neutralise the `is_locked` compute so it always yields `False`; a test confirming a
  150M order must fail on `assertTrue(order.is_locked)`.
- Altered behavior (threshold moved from 50M to 100M): put 50M back; a test asserting a 75M order
  stays unlocked must fail.
- Bug fix (orders exactly at 100M were not locked): turn `>=` back into `>`; the regression test at
  exactly 100M must fail.
