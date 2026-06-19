<!-- SSOT reference for adapt mode. Loaded by odoo-test-writing (adapt mode) and by
     odoo-run-forward-port P4a. Edit here only; SKILL.md carries the summary + pointer.
     Dau gach ASCII `-`. -->

# odoo-test-writing - Adapt Mode (Forward-Port Test Forwarding)

Adapt mode translates existing test files from a source Odoo version to a target version
during continuous forward-port. It forwards the INTENT of tests, not their text.

## When adapt mode applies

Invoke adapt mode (not new-test mode) when:
- The input is an existing test file path or diff from a source version
- The context is a forward-port pipeline (P4a of odoo-run-forward-port)
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

- **Framework imports:** call `lookup_core_api(name='TransactionCase', odoo_version='<tgt>')` -
  import paths change between major versions. Call `find_examples(query='TransactionCase setUp',
  odoo_version='<tgt>')` for real setUp signature.
- **Form helper:** available v13+; `from odoo.tests.common import Form` - verify path via OSM.
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

- If the forward-port is in the absorption window (`git merge --no-commit`): run the
  test suite for the target module with the current working tree (where the source code
  was merged but NOT yet platform-adapted). The test must fail because the target platform
  does not yet have the adapted behavior. State the failing assertion as RED evidence.
- If running in isolation: reason from the intent doc + OSM that the behavior is absent on
  the raw target version and state "RED - target does not yet have <behavior>, test will
  fail at <assertion>".
- If the test passes immediately without any adapted code: the behavior is already in the
  target platform - record this as outcome (a) in [[fp-intent-4outcome]], forward the test
  (it passes as a regression guard), skip the code-adapt step.

RED evidence is required in the Continuation Contract. A test without RED evidence may be
a green-by-accident test (change-detector, not a guard).

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

- Symbol-survival check (P3.5) runs BEFORE adapt mode. If a field or method in the
  source test was flagged by symbol-survival as absent on target, treat it as
  CAPTURE-CODE for that symbol and translate accordingly (do not leave a reference to a
  removed symbol).
- RED-then-GREEN and confirm-by-toggle for FP-delta tests is part of Phase 5 verify
  (per-batch), NOT per-test during adapt. Adapt mode confirms RED conceptually (step 4
  above); the actual toggle runs in Phase 5.

## Continuation Contract for adapt mode

End with a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`. For adapt mode, `produced`
lists the translated test file path. The `status` block MUST include:

```
RED confirmation: <assertion> fails on target because <reason>
Dropped (capture-code): <list of test_* methods dropped and why, or "none">
Expected changed: <list of changed expected values with cited reason, or "none">
```

The coder (P4b) reads this block to understand what tests must go green before the merge
commit is created.
