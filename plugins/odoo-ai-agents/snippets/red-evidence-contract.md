<!-- SSOT snippet. The single declaring file for `RED_MODE` - what counts as EVIDENCE that a test
     can fail when the behavior is absent. test-first-contract.md owns WHEN (test before code),
     test-behavior-contract.md owns HOW a test is arranged; THIS file owns which proof a change
     owes and what a RED is not. Referenced (not copy-pasted) by odoo-test-writing, odoo-test-writer,
     odoo-coder, odoo-backend-coder / odoo-frontend-coder, odoo-code-reviewer. Edit here only;
     consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/red-evidence-contract.md. -->

# Red-Evidence Contract (a RED is measured or constructed, never asserted)

Red-before-green buys two things: the test is authored from the business rule by an actor that has
not read the implementation, so it cannot snapshot the code; and the test is SENSITIVE - it can
fail when the behavior is absent. Independence is free from the topology. Sensitivity needs
evidence, and this file says which evidence each change owes. A ceremonial failure proving neither
is waste: it spends a run, a loop and tokens, and leaves the gate un-run.

## A failure that never reached the assertion is NOT a RED

It is a BROKEN MEASUREMENT: report `RED: not measured - <class>`, fix it, re-measure. Never count
it, never proceed on it. The classes:

`KeyError: '<model>'` - `ValueError: Invalid field '<f>' on model` - external id not found -
`AttributeError` on an undefined method - `ImportError`, or the file missing from
`tests/__init__.py` (which silently collects NOTHING) - ParseError or a failed module
install/upgrade - a fixture/environment error - **0 tests selected** (a suite that ran nothing is
neither red nor green). On the JS side: an unregistered component/service, an asset-bundle build
error, a tour step whose selector never appears.

Naming a model, field or external id you KNOW is absent, just to watch it fail, manufactures one of
these. Banned, not clever.

## Prefer the free proof - sensitivity by construction

Absence produces a narrow, knowable set: the field's declared default (`False`, `0`, `0.0`, `[]`,
`None`, the first `selection` value), the input unchanged, and NO exception. **Assert a value
outside that set** and the test is provably sensitive with no run at all.

- `assertEqual(order.margin, 37.5)` - a bare declaration cannot produce `37.5`. Proven, free.
- `assertFalse(order.is_locked)` - that IS what absence produces; it would pass with the rule
  deleted. Strengthen the assertion, or measure it.

## `RED_MODE` - the proof this change owes

Declared per authored test by the test author, verified by the coordinator:

- **`constructed`** - the rule above applies. No run. Evidence: the asserted value + why absence
  cannot produce it.
- **`measured`** - the behavior is observable on the tree AS IT STANDS. Run that ONE test before
  the code (`--test-tags /<module>:<Class>.<method>` - a RED PROBE, the one run `test-scope-contract.md` exempts from its two-sided scope rule). Evidence: the assertion failure, the test
  node id, selected-count > 0. Snapshot risk is real here - the author can read the implementation
  - so this measurement is not optional.
- **`toggle`** - vocabulary is new AND the asserted value is one absence produces. After green:
  neutralise the rule, re-run that one test, see the assertion fail, restore, re-run green.
- **`exempt`** - `${CLAUDE_PLUGIN_ROOT}/snippets/test-exemption-contract.md`.

**Never provision an instance to measure a RED.** Measurement rides an instance that already
exists; with none, `measured` degrades to `constructed` and `toggle` rides the integrated run.

## The RED each change owes

| Change | The RED that means something |
|---|---|
| New model / field / method | `constructed`, on a value absence cannot produce |
| Bug fix | `measured` - reproduces the REPORTED symptom; a test written from the intended FIX passes on any implementation |
| Behavior removal | `measured`, inverted - asserts the behavior is GONE, fails while it is still present |
| Refactor (behavior preserved) | none exists - the proof is the existing suite green BEFORE and after; add a characterisation test only where it leaves a contract uncovered |
| Access / security tightening | `measured` - the forbidden action currently SUCCEEDS under `with_user()`; never assert the ACL row |
| Performance | `measured` - the stated budget is exceeded now |
| Data migration | `measured` - the post-migration invariant fails on a pre-migration fixture |
| View / QWeb / OWL | `constructed`, on the rendered or behavioral outcome, never the arch string |
| Declarative only | none - declare `TEST_EXEMPTION` |

## Banned

Counting a load/import/collection error as RED - a `measured`/`toggle` RED claimed with no test
node id or 0 selected - `assertRaises(Exception)`, which swallows the broken measurement too -
re-implementing the rule inside the test - editing the test to reach green.
