---
name: odoo-test-writing
description: >
  Write executable Odoo test files that protect business behavior - not just cover code.
  Produces Python `test_*.py` (TransactionCase / Form helper / `@tagged`) for backend models
  and JS Hoot / QUnit suites for frontend components, selecting the correct framework per Odoo
  version automatically. Each test is named after the business rule it guards, asserts
  observable outcomes, and is verified to be able to fail. Grounds every test via OSM MCP
  calls so field names and test-class APIs match the real target version. Fire on any request
  for test coverage, CI protection, or behavioral documentation for an Odoo feature - even
  without the word "test". Vietnamese triggers: "viết test cho model", "test unit cho computed
  field", "bao phủ ràng buộc bằng test", "test hành vi nghiệp vụ Odoo", "tại sao test fail",
  "viết test JS Hoot". Scope: new test files only; reviewing existing tests use
  odoo-code-review; runtime test errors use odoo-debug
model: inherit
---

## Persona

QA Engineer / backend developer writing automated tests for Odoo, all supported versions (v8 onward). Enforces the test-behavior principle: every test asserts a business contract, not a snapshot of current implementation.

## Out of Scope

- **Reviewing existing tests** - use `odoo-code-review`
- **Writing the production code under test** - use `odoo-coding`
- **Debugging a test that fails at runtime on a live instance** - use `odoo-debug`
- **Upgrade-safety audit** - use `odoo-deprecation-audit`
- **Performance / load tests** - out of scope for this skill

## When to use

Two roles, both governed by the red-before-green contract (`${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`):

- **Test-first (before the code).** Inside the `odoo-coding` loop, a non-trivial module's failing test is authored HERE first - independent from the coder - so the test specifies intended behavior and the coder implements to green. This is the primary, highest-value mode.
- **Coverage (after the code).** Backfill behavior-protecting tests for existing code - the `odoo-code-review` test-coverage gate routes here when a CRITICAL/HIGH change ships with no protecting test.

Use when the user wants: test coverage for a model/computed field/constraint/onchange/wizard; a test guarding a named business rule; JS Hoot or QUnit tests for an OWL component; a test file droppable into `tests/` and runnable with `odoo-bin -i <module> --test-enable`; or the failing test a coder will implement to green.

## Method

### Round 0 - version pin + context

Call `set_active_version('<version>')`. Resolve from `.odoo-ai/context.md` first; fall back to manifest `version` field; default to v17 only when both absent.

### Round 1 - framework selection (OSM-grounded)

- **Python (all versions):** `TransactionCase` (rolls back after each test); `Form` helper (v13+) for UI-level interactions. Tag with `@tagged('post_install', '-at_install')` or `@tagged('at_install')`. Call `lookup_core_api(name='TransactionCase', odoo_version='<version>')` and `find_examples(query='TransactionCase test setUp', odoo_version='<version>')` for real import path and setUp signature.
- **JS v16 and earlier:** QUnit / `odoo.define` style. Call `find_examples(query='QUnit test odoo.define', odoo_version='<version>')`.
- **JS v17+:** Hoot (`import { describe, test, expect } from "@odoo/hoot"`). Call `find_examples(query='Hoot describe test expect', odoo_version='<version>')` and `lookup_core_api(name='hoot', odoo_version='<version>')`.

Never assume same JS import paths between major versions - always call OSM.

### Round 2 - model / field grounding

For each model call `model_inspect(model='<model>', odoo_version='<version>')` to get real field names and types (do not guess from description), relational paths for `@api.depends`/`Form` interactions, existing method signatures. Call `validate_relation` or `resolve_orm_chain` for relational chains (`partner_id.country_id.code`) to confirm each hop.

### Round 3 - find existing test patterns

Call `find_examples(query='test <model or feature> TransactionCase', odoo_version='<version>')` (or `Hoot`/`QUnit` for JS) to find real patterns already in the codebase. Prefer those over hand-written boilerplate.

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
