<!-- SSOT reference for adapt mode. Loaded by odoo-test-writing (adapt mode) and by
     odoo-forward-port P4a. Edit here only; SKILL.md carries the summary + pointer.
     Dau gach ASCII `-`. -->

# odoo-test-writing - Adapt Mode (Forward-Port Test Forwarding)

Adapt mode translates existing test files from a source Odoo version to a target version
during continuous forward-port. It forwards the INTENT of tests, not their text.

## When adapt mode applies

Invoke adapt mode (not new-test mode) when:
- The input is an existing test file path or diff from a source version
- The context is a forward-port pipeline (P4a of odoo-forward-port)
- The user explicitly requests "translate tests from vX to vY" or "forward tests for this commit"

## Inputs

| Input | Required | Notes |
|---|---|---|
| Test file path or raw diff | Yes | Source test file to translate |
| `src_version` | Yes | E.g. `16.0` |
| `tgt_version` | Yes | E.g. `17.0` |
| Intent doc | Recommended | `intents/<sha>.md` from P1 of forward-port pipeline; confirms what behavior the test was written to protect |

Call `set_active_version('<tgt_version>')` at the start of adapt mode - the target version
drives all OSM grounding.

## Step 1 - Classify each assertion

Read the source test file end-to-end. For each assertion or setup block, classify it as
one of:

**INTENT (keep, translate)**
- Asserts an observable outcome: field value after action, state after transition, exception
  raised by constraint, records created as side effect
- Named after a business rule (`test_discount_cannot_exceed_20pct`)
- Uses `action_confirm()` / `action_post()` / Form helper to drive the real workflow
- The business rule it guards exists in the target version (verify via OSM or intent doc)

**CAPTURE-CODE (strip)**
- Asserts a private method was called or how many times `write` ran
- Asserts an internal variable name or ORM-cache structure
- Asserts a field name or API that is version-specific and has no semantic equivalent
  on the target (verify via `api_version_diff` + `model_inspect`)
- Asserts call order of ORM hooks / compute order not mandated by the business contract
- Asserts the text of an error message word-for-word (acceptable to strip to
  `assertRaises(ValidationError)` without message check)

When in doubt: ask "if the platform reimplemented this behavior correctly but used a
different internal mechanism, should this assertion still pass?" - YES = INTENT, NO = CAPTURE-CODE.

## Step 2 - Strip capture-code

Remove or rewrite assertions classified as CAPTURE-CODE. Do not replace them with weaker
assertions that still pass vacuously. If stripping an assertion leaves a test body with
nothing to assert, remove the entire `def test_*` method and note it in the Continuation
Contract as "dropped - capture-code only, no intent preserved".

Never drop a test that has at least one INTENT assertion, even if much of its body was
CAPTURE-CODE.

## Step 3 - Translate API to target

OSM-ground every API reference for `tgt_version`:

- **Framework imports / base class:** call `test_base_classes(odoo_version='<tgt>', name='TransactionCase')`
  for the base-class menu, cursor contract and setUp behavior at the target version (do NOT use
  `lookup_core_api` for test base classes - it indexes core ORM/API symbols only and returns
  not-found). The standard import is `from odoo.tests import TransactionCase`; use
  `find_test_examples(query='TransactionCase setUp', odoo_version='<tgt>')` for a real setUp pattern.
- **Form helper:** available v12+ (see `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 3); `from odoo.tests.common import Form` (relocates to `odoo/tests/form.py` at v17, API unchanged) - verify path via OSM.
- **`@tagged` decorator:** call `find_examples(query='@tagged post_install at_install',
  odoo_version='<tgt>')` for current convention.
- **Field names that changed:** call `api_version_diff(symbol='<model>.<field>', from_version='<src>',
  to_version='<tgt>')` to surface renames. Map each renamed field. A field absent in `tgt`
  and with no rename entry is a CAPTURE-CODE candidate unless the intent doc confirms the
  feature still exists under a different model or field.
- **Method signatures:** call `model_inspect(model='<model>', method='summary', odoo_version='<tgt>')` to get
  current method signatures and field types. A method renamed or removed -> verify intent
  doc; if behavior is still expected, find the replacement via `find_override_point` or
  `find_examples`; if not expected, drop the test.
- **JS tests (Hoot/QUnit transition v16->v17+):** translate `odoo.define` / QUnit to Hoot
  (`import { describe, test, expect } from "@odoo/hoot"`). Call
  `find_examples(query='Hoot describe test expect', odoo_version='<tgt>')`.

## Step 4 - Confirm RED on target

The translated test MUST fail on the target version BEFORE the adapted production code
exists. This is the FP-delta proof.

Modes and evidence: `${CLAUDE_PLUGIN_ROOT}/snippets/red-evidence-contract.md`.

- If in the no-commit merge absorption window (see [[fp-merge-absorption]]): this is
  `RED_MODE: measured` - run the target module's test suite against the current working
  tree (source merged but NOT yet platform-adapted). The test must fail ON THE ASSERTION
  because the target platform lacks the adapted behavior. A `KeyError` /
  `AttributeError` / `Invalid field` instead means YOUR TRANSLATION is incomplete - a
  renamed symbol step 3 missed - not that the target lacks the behavior. That is a broken
  measurement: fix the translation and re-measure. Letting it stand as RED-on-target
  misclassifies the outcome in [[fp-intent-4outcome]].
- If running in isolation: this is `RED_MODE: constructed` - no run is available, so the
  proof must be structural. From the intent doc + OSM, name the asserted VALUE and why the
  raw target cannot produce it. An assertion the absent behavior would already satisfy
  (a default, a falsy flag, "no exception raised") proves nothing here and must be
  strengthened before the test is forwarded.
- If the test passes immediately without any adapted code: the behavior is already in the
  target platform - record this as outcome (a) in [[fp-intent-4outcome]], forward the test
  (it passes as a regression guard), skip the code-adapt step.

`RED_MODE` + its evidence is required in the Continuation Contract. A test without it may
be a green-by-accident test (change-detector, not a guard).

## What is BANNED in adapt mode

The bans from `${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md` apply without
exception in adapt mode. Additionally:

- **NEVER widen or relax an assertion to make the test pass** on the target. If the
  assertion was `assertEqual(val, 42)` on source and the target returns `43`, the test is
  FAILING FOR A REASON - root-cause whether the platform changed the behavior or whether
  the adapt code is wrong; do not change `42` to `43` to silence it.
- **Change `expected` ONLY when the target platform legitimately redefines the behavior**
  AND you can cite the reason: an OSM `api_version_diff` entry, a platform changelog
  entry, or an explicit note in the intent doc. Quote the source.
- **Do not drop a test because translating it is difficult.** Difficulty = the test was
  protecting something real. Escalate as BLOCKED with the specific obstacle.
- Do not add `@skip`, `pass`, or empty assertion bodies to silence a red test.

## Linking back to fp-merge-absorption

Adapt mode runs inside the absorption window described in
`${CLAUDE_PLUGIN_ROOT}/snippets/fp-merge-absorption.md`:

- Symbol-survival check (P6) runs BEFORE adapt mode. If a field or method in the
  source test was flagged by symbol-survival as absent on target, treat it as
  CAPTURE-CODE for that symbol and translate accordingly (do not leave a reference to a
  removed symbol).
- RED-then-GREEN and confirm-by-toggle for FP-delta tests is part of P9 verify
  (per-batch), NOT per-test during adapt. Adapt mode confirms RED conceptually (step 4
  above); the actual toggle runs in P9.

## Continuation Contract for adapt mode

End with a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`. For adapt mode, `produced`
lists the translated test file path. The `status` block MUST include:

```
RED_MODE: measured - <assertion> fails on target because <reason>
         | constructed - target cannot produce <value> because <reason>
Dropped (capture-code): <list of test_* methods dropped and why, or "none">
Expected changed: <list of changed expected values with cited reason, or "none">
```

The coder (P4b) reads this block to understand what tests must go green before the merge
commit is created.
