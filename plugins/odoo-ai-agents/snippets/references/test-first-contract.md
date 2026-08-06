<!-- Reference material for snippets/test-first-contract.md. This file is for humans and authors
     doing repo archaeology - it is never cited from any consumer-facing skill/agent/snippet body
     (see docs/authoring-skills-and-agents.md). Explanation and worked examples only; every
     decidable rule stays in the main file. -->

# Test-First Contract - rationale and worked examples

## Why test-first (moved from the file's opening paragraph)

A test written after the code, to match whatever the code happens to do, is a change-detector: it
passes always, catches no bug, and turns every honest refactor into a false alarm. Authoring the
test first, from the business rule, makes it a falsifiable specification of intent instead.

## Worked example - phrasing a test from the business rule

Phrase the test as the rule it protects, e.g. "an order over 100M is locked" - not as a description
of the code path that currently enforces it. The assertion should read as a business statement a
non-engineer could confirm is right or wrong.

## Related snippets

- `snippets/fp-merge-absorption.md` - forward-port merge-absorption outcome classification, which
  the RED-on-target evidence pattern feeds into.
- `snippets/fp-intent-4outcome.md` - the 4-outcome intent classification RED-on-target is one input
  to.
