<!-- Reference material for snippets/red-evidence-contract.md. This file is for humans and authors
     doing repo archaeology - it is never cited from any consumer-facing skill/agent/snippet body
     (see docs/authoring-skills-and-agents.md). Explanation and worked examples only; every
     decidable rule stays in the main file. -->

# Red-Evidence Contract - rationale and worked examples

## Why the RED needed its own contract

Red-before-green was stated as a sequence and never as a measurement. Three prescriptions, each
defensible on its own, composed into a gate that could not fire:

1. `odoo-coder` launches `odoo-test-writer` FIRST, before any model, field or external id the test
   will name exists on the tree.
2. `odoo-test-writer` is told not to run the suite inline - correct for context and instance
   economy, but it means the author never observes the failure it reports.
3. The RED confirmation was a fixed sentence to emit ("RED - production code not yet written"), and
   the authoring skill said to "state it's RED".

The coordinator's only check on the returned test was that the FILE EXISTS. So nothing anywhere in
the loop observed a RED. The visible symptom - a test authored against a model that does not exist,
failing with `KeyError`, reported as a confirmed RED - was the contract executing exactly as
written, not an agent being careless. ETHOS 12 names the general shape: a prescribed sentence
standing in for an observation is a claim, and claims are not evidence.

## Why "make it fail first" is a proxy, not the goal

The goal is that a test cannot be a snapshot of the code. Two properties deliver it:

- INDEPENDENCE - the author has not read the implementation. The topology already guarantees this
  (a separate `odoo-test-writer`, launched before the coder), at no extra cost.
- SENSITIVITY - the test can fail when the behavior is absent.

Watching a test fail before the code exists is a proxy for sensitivity. On Odoo the proxy is often
unmeasurable, because a behavior and the vocabulary that names it arrive together: with no field
there is nothing to read, so the observed failure is the field's absence, not the rule's. Forcing
the ritual there buys nothing and costs a run, a loop and tokens - and worse, it reports a gate as
having fired when it did not.

Splitting the two properties is what lets the contract stay strict where snapshot risk is real
(`measured`) and stop manufacturing failures where it is not (`constructed`).

## Worked example - the same rule, three modes

Rule: "a sale order over 100M is locked."

- The `is_locked` field and its compute are both new -> `constructed`. Assert the locked order's
  `amount_total` threshold effect on a value a bare `fields.Boolean()` cannot produce; if the only
  honest assertion is `assertTrue(order.is_locked)`, that value IS producible by absence only in
  the False direction, so assert BOTH directions in one test pair - the True case is unproducible
  by a bare declaration and carries the proof.
- `is_locked` already exists and the threshold is being changed from 50M to 100M -> `measured`. An
  order at 75M must be locked today and unlocked after; run the test, see the assertion fail.
- The field is new and the specification's only observable is "no exception raised" -> `toggle`.
  Nothing distinguishes absent from correct until the rule exists, so the proof is taken after
  green by neutralising the rule.

## Related snippets

- `test-first-contract.md` - the loop this evidence rule serves (WHEN).
- `test-behavior-contract.md` - the arrange rules (HOW). Its "would it still pass with the logic
  deleted?" thought experiment is the same property this file makes decidable.
- `test-exemption-contract.md` - the `exempt` mode.
- `test-scope-contract.md` - the `--test-tags` scoping a single-test RED run relies on.
