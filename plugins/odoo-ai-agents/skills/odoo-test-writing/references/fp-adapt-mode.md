<!-- SSOT reference for adapt mode. Loaded by odoo-test-writing (adapt mode).
     Edit here only; SKILL.md carries the summary + pointer.
     Dau gach ASCII `-`. -->

# odoo-test-writing - Adapt Mode (Forward-Port Test Forwarding)

Adapt mode translates existing test files from a source Odoo version to a target version
during forward-port or rebase. It forwards the INTENT of tests, not their text, and it runs
AFTER the adapt code exists.

## When adapt mode applies

Invoke adapt mode (not `change` mode) when:
- The input is an existing test file path or diff from a source version
- The brief carries `MODE: adapt` with `SOURCE TESTS` (a forward-port or rebase node, reached
  through `odoo-coding` -> `odoo-coder` -> `odoo-test-writer`)
- The user explicitly requests "translate tests from vX to vY" or "forward tests for this commit"

## Inputs

| Input | Required | Notes |
|---|---|---|
| Test file path or raw diff | Yes | Source test file to translate |
| `src_version` | Yes | E.g. `16.0` |
| `tgt_version` | Yes | E.g. `17.0` |
| Intent doc | Recommended | the commit's intent doc from the forward-port intent sweep; confirms what behavior the test was written to protect |
| `BROKEN TEST-SYMBOLS` | When the caller has them | source symbols the symbol-survival check found absent on target - each is CAPTURE-CODE or a step-3 mapping, never a reference left in the test |
| `BUCKET` | When the caller has it | the commit's forward-port bucket; (a) runs the Absorption probe in step 4 instead of a break-check |

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

## Step 4 - Prove it after the code (break-check, or the Absorption probe for bucket (a))

The forwarded test is proven the same way as any behavior test: AFTER the adapt code exists, by
an executed break-check (`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`
§ The break-check, recorded per § Break-check record). The break is disabling the adapt code that
carries the rule; every forwarded behavior test must then fail ON THE ASSERTION.

- A `KeyError` / `AttributeError` / `Invalid field` on the target means YOUR TRANSLATION is
  incomplete - a renamed symbol step 3 missed - not that the target lacks the behavior. It is a
  broken measurement (§ Broken measurement is not a red): fix the translation and re-run. It never
  classifies the commit.
- `BUCKET` (a) - the behavior is already absorbed by target core - leaves no adapt code to break:
  run the forwarded test BEFORE any adapt code, as § Absorption probe (forward-port
  classification, not a test gate) states, and report what the probe decided.

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
- Do not add `@skip`, `pass`, or empty assertion bodies to silence a failing test.

## Linking back to fp-merge-absorption

Adapt mode runs inside the absorption window described in
`${CLAUDE_PLUGIN_ROOT}/snippets/fp-merge-absorption.md`:

- Symbol-survival check runs BEFORE adapt mode. A field or method in the source test that it
  flagged as absent on target (`BROKEN TEST-SYMBOLS`) is CAPTURE-CODE for that symbol or a step-3
  mapping - never leave a reference to a removed symbol.
- The adapt code is written first; the forwarded tests and their break-checks follow it in the
  same node (step 4).

## Continuation Contract for adapt mode

End with a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`. For adapt mode, `produced`
lists the translated test file path. The `status` block MUST include:

```
BREAK_CHECK: <one line per forwarded behavior test, the shape test-sensitivity-contract.md § Break-check record fixes>
Absorption probe: <bucket (a) only - the probe's result and decision, or "n/a">
Dropped (capture-code): <list of test_* methods dropped and why, or "none">
Expected changed: <list of changed expected values with cited reason, or "none">
```
