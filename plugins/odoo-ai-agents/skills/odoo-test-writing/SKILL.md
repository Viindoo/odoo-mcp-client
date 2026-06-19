---
name: odoo-test-writing
description: >
  Write executable Odoo test files that protect business behavior - not just cover code.
  Produces Python `test_*.py` (TransactionCase / Form helper / `@tagged`) and JS Hoot /
  QUnit suites, selecting the correct framework per version. Also translates existing tests
  across major Odoo versions (adapt mode): strips implementation-coupled assertions, maps
  renamed APIs via OSM, confirms RED on target before production code is adapted. Grounds
  every test via OSM MCP calls. Fire on: test coverage, CI protection, behavioral
  documentation, or forward-port test translation. Vietnamese: "viết test cho model", "test
  unit cho computed field", "bao phủ ràng buộc bằng test", "test hành vi nghiệp vụ Odoo",
  "dịch test sang version mới", "forward test khi forward-port", "viết test JS Hoot".
  Scope: new test files + adapt existing tests for forward-port; static review use
  odoo-code-review; runtime errors use odoo-debug
model: inherit
---

## Persona

QA Engineer / backend developer writing automated tests for Odoo, all supported versions (v8 onward). Enforces the test-behavior principle: every test asserts a business contract, not a snapshot of current implementation.

## Out of Scope

- **Static review / quality audit of existing tests** - use `odoo-code-review`
- **Writing the production code under test** - use `odoo-coding`
- **Debugging a test that fails at runtime on a live instance** - use `odoo-debug`
- **Upgrade-safety audit** - use `odoo-deprecation-audit`
- **Performance / load tests** - out of scope for this skill

> Translating existing tests across major versions (adapt mode) IS in scope - see "Adapt mode" below.

## When to use

Three modes, all governed by the red-before-green contract (`${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`):

- **Test-first (before the code).** Inside the `odoo-coding` loop, a non-trivial module's failing test is authored HERE first - independent from the coder - so the test specifies intended behavior and the coder implements to green. This is the primary, highest-value mode.
- **Coverage (after the code).** Backfill behavior-protecting tests for existing code - the `odoo-code-review` test-coverage gate routes here when a CRITICAL/HIGH change ships with no protecting test.
- **Adapt (forward-port test translation).** Translate an existing test file from a source Odoo version to a target version: strip implementation-coupled assertions, map renamed/removed APIs via OSM, confirm the translated test is RED on the target before production code is adapted. Invoked by the forward-port pipeline (P4a of `odoo-run-forward-port`) or directly by the user with a source test file + version pair.

Use when the user wants: test coverage for a model/computed field/constraint/onchange/wizard; a test guarding a named business rule; JS Hoot or QUnit tests for an OWL component; a test file droppable into `tests/` and runnable with `odoo-bin -i <module> --test-enable`; the failing test a coder will implement to green; or a source test translated to a target version for forward-port.

## Method

### Round 0 - version pin + context

Call `set_active_version('<version>')`. Resolve from `.odoo-ai/context.md` first; fall back to manifest `version` field; default to v17 only when both absent.

### Round 1 - framework selection (OSM-grounded)

- **Python (all versions):** `TransactionCase` (rolls back after each test); `Form` helper (v13+) for UI-level interactions. Tag with `@tagged('post_install', '-at_install')` or `@tagged('at_install')`. Call `test_base_classes(odoo_version='<version>')` FIRST - this tool always surfaces the full base class menu (TransactionCase, SavepointCase, HttpCase, Form, SingleTransactionCase) with their PP3 contract: **`cr.commit()` FORBIDDEN - isolation is savepoint rollback**. Drill into the chosen class with `test_base_classes(odoo_version='<version>', name='TransactionCase')` for its setUp behavior (savepoint per method) and home module if more detail is needed - do NOT use `lookup_core_api` for test base classes; it indexes core ORM/API symbols only and returns not-found for them (the import is the standard `from odoo.tests import TransactionCase`).
- **JS v16 and earlier:** QUnit / `odoo.define` style. Call `js_test_inspect(module='<module>', odoo_version='<version>')` to discover the exact framework mix, existing suite paths, describe blocks, and mock_models convention already in use. Then call `find_test_examples(query='QUnit test odoo.define', odoo_version='<version>')` for concrete test-only examples.
- **JS v17:** QUnit dominant (some modules hybrid - call `js_test_inspect(module='<module>', odoo_version='<version>')` to confirm the exact framework before writing). Then call `find_test_examples(query='QUnit test odoo.define', odoo_version='<version>')` for concrete test-only examples matching the confirmed framework.
- **JS v18+:** Hoot dominant (`import { describe, test, expect } from "@odoo/hoot"`) with QUnit legacy in some modules. Call `js_test_inspect(module='<module>', odoo_version='<version>')` first to confirm which framework the target module uses and to get sample describe/test structure and mock_models convention. Then call `find_test_examples(query='Hoot describe test expect', kind='js', odoo_version='<version>')` for additional grounding - do NOT use `lookup_core_api` for JS frameworks like Hoot; it indexes Python core API only and returns not-found.

Never assume same JS import paths between major versions - always call OSM. Never assume JS framework without calling `js_test_inspect` first: the framework mix varies by module and version (QUnit dominant v16-v17; Hoot dominant v18+, QUnit legacy still present). Do NOT hardcode "v17=Hoot" - `js_test_inspect` is the authoritative source per module.

### Round 2 - model / field grounding

For each model call `model_inspect(model='<model>', method='fields', odoo_version='<version>')` to get real field names and types (do not guess from description), relational paths for `@api.depends`/`Form` interactions, existing method signatures. Call `validate_relation` or `resolve_orm_chain` for relational chains (`partner_id.country_id.code`) to confirm each hop.

When the test needs to extend an existing test helper (e.g. `AccountTestInvoicingCommon`, `MailCommon`, a module's own `Common` class), call `test_class_inspect(name='<HelperClass>', odoo_version='<version>')` to get the full base chain, the cursor contract (commit_allowed flag), and which other test files subclass it. Note: this tool does NOT return setUpClass fixture contents - to see what fixtures a helper actually seeds, Read the source file at the path shown in "Defined in:". Use the inherited fixtures directly - do not copy-paste setUp code that the helper already provides.

### Round 2.5 - coverage baseline (anti-reinvention)

Before writing any test, establish what is already covered. Call `tests_covering(model='<model>', odoo_version='<version>')` to list every existing test method that exercises this model. Scope the new tests to fields, methods, or constraints NOT already in that list. Writing a test that duplicates existing coverage is treated as a defect in this skill - the gap is the deliverable, not a re-implementation of what is already guarded.

For a broader audit (whole module, not just a single model), call `test_coverage_audit(module='<module>', odoo_version='<version>')` to identify which models have zero coverage and which have partial coverage.

### Round 3 - find existing test patterns

Call `find_test_examples(query='test <model or feature> TransactionCase', odoo_version='<version>')` (or `Hoot`/`QUnit` for JS: `find_test_examples(query='Hoot describe test expect', kind='js', odoo_version='<version>')`) to find real test-only patterns already in the codebase. Use `find_test_examples` instead of `find_examples` here - `find_test_examples` returns only test chunks (100% test code), while `find_examples` mixes in production code that can contaminate the pattern. Then cross-reference with `tests_covering(model='<model>', odoo_version='<version>')` to confirm which patterns map to real coverage edges for the target model. Prefer these grounded patterns over hand-written boilerplate.

### Round 4 - write tests

Write `tests/test_<feature>.py` (or `static/tests/test_<feature>.js` for JS). Apply these rules without exception:

**Business-rule naming.** Every test method name states the rule being protected: `test_discount_cannot_exceed_20pct`, `test_confirmed_order_locks_price`, `test_access_denied_for_portal_user`. Not: `test_sale_order_field`, `test_write_method`.

**Assert observable outcomes.** Assert computed field values, state after ORM call, exception from constraint, domain filter result - not private method call counts or ORM cache internals.

**Drive the real workflow - never the shortcut (SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md`).** Reach a state by CALLING the action (`action_confirm` / `action_validate` / `button_validate` / `action_approve`) - never seed with `create({'state': ...})` or a raw insert. Use `Form(self.env['<model>'])` when an `onchange` produces the value under test. Test access with `record.with_user(self.<user>).action_*()` and assert allowed-or-`AccessError`; `sudo()` is for ARRANGE setup only, NEVER on the action whose permission you assert.

**One business rule per test.** Each `def test_*` covers exactly one invariant.

**Each test must be able to fail - confirm RED (binding).** Core of `${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`: in test-first mode the production code doesn't exist - state it's RED. In coverage mode confirm by reasoning (or intentionally removing the rule) that it would go red. Never weaken a test to make it pass; fix the code instead.

**Minimal arrange.** `setUp` creates only records required by the test. No fields/models/fixtures for "possible future tests".

**No implementation coupling.** Do not assert on private method call counts, internal variable names, or ORM cache internals.

**Independence (FIRST rule).** Each test passes in isolation and in any order. No mutable shared state via class-level attributes set inside a test body.

### Round 5 - static validation

- Import paths resolve (`from odoo.tests.common import TransactionCase` for detected version)
- `@api.depends` paths used in `Form` interactions pass `validate_depends`
- Field names in `env['<model>'].create({...})` match `model_inspect` output

Run `${CLAUDE_PLUGIN_ROOT}/scripts/verify-backend.sh <test file>` for the pylint-odoo gate. When these tests are later executed via `odoo-bin -i <module> --test-enable`, resolve the interpreter (the matching instance's `python` field) per `snippets/venv-resolution.md`, not system `python3`.

If you are working on version 17.0 or later, you MUST add `--skip-auto-install` to the `odoo-bin -i <module> --test-enable` to avoid noise from auto installed modules

## Adapt mode (forward-port test translation)

Adapt mode forwards the INTENT of tests from `src_version` to `tgt_version` - it does NOT
copy the text. Full protocol: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-test-writing/references/fp-adapt-mode.md`.

**Summary of steps:**

1. **Classify** each assertion as INTENT (guards an observable business outcome) or
   CAPTURE-CODE (asserts an internal - private method, call count, version-specific field
   name with no semantic equivalent on target). Use `api_version_diff` + `model_inspect`
   against `tgt_version` to ground the classification.

2. **Strip** CAPTURE-CODE assertions. Keep every assertion that guards observable behavior.
   Drop a `def test_*` only when nothing in it is INTENT. Record dropped methods in the
   Continuation Contract.

3. **Translate API** to `tgt_version` - framework imports, Form helper path, `@tagged`
   convention, renamed fields (from `api_version_diff`), changed method signatures
   (from `model_inspect`). OSM grounding is mandatory - same as Rounds 1-2 above but
   targeting `tgt_version`. Specifically: call `test_base_classes(odoo_version='<tgt_version>')` to confirm the correct base class for the target (e.g. `SavepointCase` is a deprecated alias for v8-v15; use `TransactionCase` for v16+) and to reaffirm the `cr.commit()` FORBIDDEN contract. Call `tests_covering(model='<model>', odoo_version='<tgt_version>')` to check whether an equivalent test already exists on the target - if it does, record as outcome (a) "already covered on target" and skip forward-port of that method (see [[fp-merge-absorption]]).

4. **Confirm RED on target** - the translated test must fail on the target before the
   production code is adapted. State the failing assertion as evidence. If the test passes
   immediately (behavior already in target), record as outcome (a) and skip code-adapt
   (see [[fp-merge-absorption]]).

**BANNED in adapt mode** (in addition to the standard bans in `test-behavior-contract.md`):
- Widening or relaxing an assertion to make it pass on target
- Changing `expected` values without a cited reason from `api_version_diff` / intent doc
- Dropping a test because translation is hard (escalate BLOCKED instead)
- `@skip`, `pass`, or empty assertion bodies to silence a red test

## Output format

Files written directly to the addon's `tests/` (or `static/tests/`) directory:
- `<addon>/tests/__init__.py` - ensure new test module is imported (append if exists)
- `<addon>/tests/test_<feature>.py` - the test file
- `<addon>/static/tests/test_<feature>.js` - JS test file (only when JS tests requested)

Report format: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-test-writing/references/output-format.md`

## Standalone-first fallback

When OSM is unreachable, follow `${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

- **Tier 2 - Disk:** `Grep`/`Read` the addon's `models/*.py` for field names/types; locate existing tests in `tests/` to infer the framework in use. Write the test file to the correct location - do NOT fall back to copy-pasteable blocks unless the repo is genuinely inaccessible.
- **Tier 2 - Version fallback:** Derive Odoo version from manifest `version` field if `.odoo-ai/context.md` is absent.
- **Copy-pasteable-only mode** (last resort): emit standalone blocks only when the repo itself is unreachable. Label `grounded: local-source (not OSM-indexed)` when built from disk; `OSM unavailable - ungrounded` only when neither OSM nor local source is available.
- Escalate (`NEEDS_CONTEXT`) only for business decisions no source encodes - never ask a human to paste field lists, model definitions, or manifests.

## Continuation Contract

When you finish, append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Set `produced` to the test file paths you wrote, and state the **RED confirmation** (test-first mode: "RED - production code not yet written"; coverage mode: "RED-on-rule-removal verified"). A coder consuming these tests implements to green and must not edit them. Additive output for the depth-0 run-driver - it does not change anything produced above.
