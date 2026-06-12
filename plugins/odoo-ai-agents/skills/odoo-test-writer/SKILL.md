---
name: odoo-test-writer
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

QA Engineer / backend developer writing automated tests for Odoo, all supported versions
(v8 onward). Enforces the ETHOS "Test the Behavior, Not the Code" principle: every test
asserts a business contract, not a snapshot of current implementation.

## Out of Scope

- **Reviewing existing tests** - use `odoo-code-review`
- **Writing the production code under test** - use `odoo-coding`
- **Debugging a test that fails at runtime on a live instance** - use `odoo-debug`
- **Upgrade-safety audit** - use `odoo-deprecation-audit`
- **Performance / load tests** - out of scope for this skill

## When to use

This skill plays two roles, both governed by the red-before-green contract
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`):

- **Test-first (before the code).** Inside the `odoo-coding` loop, a non-trivial module's failing
  test is authored HERE first - by an author separate from the coder, so the test specifies the
  intended behavior independently and the coder then implements to green. This is the primary,
  highest-value mode: the test exists and is RED before a line of production code is written.
- **Coverage (after the code).** Add or backfill behavior-protecting tests for code that already
  exists - the `odoo-code-review` test-coverage gate routes here when a CRITICAL/HIGH change ships
  with no protecting test.

Use this skill when the user wants:

- Test coverage for a model, computed field, constraint, onchange, or wizard
- A test that guards a named business rule (invariant, access control, workflow transition)
- JS Hoot or QUnit tests for an OWL component or frontend widget
- A test file they can drop into an addon's `tests/` folder and run with `odoo-bin -i <module> --test-enable`
- The failing test that a coder will implement to green, or evidence that new code meets its contract

## Method

### Round 0 - version pin + context

Call `set_active_version('<version>')` to pin the target Odoo version. Resolve the version
from `.odoo-ai/context.md` first; fall back to the closest manifest `version` field on disk;
default to v17 only when both are absent.

### Round 1 - framework selection (OSM-grounded)

Determine the correct test class and runner for the version:

- **Python (all versions):** `TransactionCase` (rolls back after each test); use `Form`
  helper (v13+) for UI-level field interactions. Tag with `@tagged('post_install', '-at_install')`
  for post-install tests or `@tagged('at_install')` for tests that need the module during
  install. Call `lookup_core_api(name='TransactionCase', odoo_version='17.0')` and `find_examples(query='TransactionCase test setUp', odoo_version='17.0')` to get the real import path and setUp signature for the version.
- **JS v16 and earlier:** QUnit / `odoo.define` style. Call `find_examples(query='QUnit test odoo.define', odoo_version='17.0')`.
- **JS v17+:** Hoot test runner (`import { describe, test, expect } from "@odoo/hoot"`). Call
  `find_examples(query='Hoot describe test expect', odoo_version='17.0')` and `lookup_core_api(name='hoot', odoo_version='17.0')`.

Never assume the same JS test import paths between major versions - always call OSM.

### Round 2 - model / field grounding

For each model under test call `model_inspect(model='<model>', odoo_version='17.0')` to obtain:

- Real field names and types (do not guess field names from the user's description)
- Relational paths for `@api.depends` / `Form` interactions
- Existing method signatures

Call `validate_relation` or `resolve_orm_chain` when a test exercises a relational chain
(`partner_id.country_id.code`, etc.) to confirm each hop exists.

### Round 3 - find existing test patterns

Call `find_examples(query='test <model or feature> TransactionCase', odoo_version='17.0')` (or `Hoot`/`QUnit` for JS)
to discover real test patterns already in the codebase or OSM index. Prefer those patterns
over hand-written boilerplate.

### Round 4 - write tests

Write `tests/test_<feature>.py` (or `static/tests/test_<feature>.js` for JS). Apply these
rules without exception:

**Business-rule naming.** Every test method name states the rule being protected:
`test_discount_cannot_exceed_20pct`, `test_confirmed_order_locks_price`,
`test_access_denied_for_portal_user`. Not: `test_sale_order_field`, `test_write_method`.

**Assert observable outcomes.** Assert the value of a computed field, the state after an ORM
call, an exception raised by a constraint, a domain filter result - not that a private method
was called, not that `write()` was invoked N times.

**One business rule per test.** Each `def test_*` covers exactly one invariant. If testing
three distinct rules, write three methods.

**Each test must be able to fail - confirm RED (binding).** This is the red-before-green core of
`${CLAUDE_PLUGIN_ROOT}/snippets/test-first-contract.md`: before declaring the test complete,
confirm it goes red when the business rule is absent. In **test-first mode** the production code
does not exist yet, so the test is genuinely red now - state that. In **coverage mode** confirm by
reasoning (or by intentionally removing the rule) that it would go red. A test that can only ever
be green is worthless. Never weaken a test later to make it pass (Iron Law #6); fix the code
instead.

**Minimal arrange, no speculative data.** `setUp` creates only the records required by the
test. Do not add fields, related models, or data fixtures for "possible future tests".

**No implementation coupling.** Do not assert on private method call counts, internal
variable names, or ORM cache internals. If the production code is refactored to the same
behavior by a different mechanism, the test must still pass.

**Independence (FIRST rule).** Each test must pass in isolation and in any order. Never
share mutable state across tests via class-level attributes set inside a test body.

### Round 5 - static validation

After writing, verify:

- Import paths resolve (`from odoo.tests.common import TransactionCase` for the detected version)
- `@api.depends` paths used in `Form` interactions pass `validate_depends`
- Field names used in `env['<model>'].create({...})` match `model_inspect` output (no typos)

Run `${CLAUDE_PLUGIN_ROOT}/scripts/verify-backend.sh <test file>` for the pylint-odoo gate.

## Output format

This skill writes files directly to the addon's `tests/` (or `static/tests/`) directory:

- `<addon>/tests/__init__.py` - ensure the new test module is imported (append if exists)
- `<addon>/tests/test_<feature>.py` - the test file
- `<addon>/static/tests/test_<feature>.js` - JS test file (only when JS tests requested)

After writing, report:

```
Written: <addon>/tests/test_<feature>.py  (<N> test methods)
Grounded: osm | local-source (not OSM-indexed) | OSM unavailable - ungrounded
Framework: TransactionCase (v<X>) | Hoot (v17+) | QUnit (v<=16)
Business rules covered: [one line per test_* method]
```

## Standalone-first fallback

When OSM is unreachable, follow the three-tier grounding in
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

- **Tier 2 - Disk:** `Grep`/`Read` the addon's `models/*.py` to obtain field names and types
  yourself. Locate existing tests in `tests/` to infer the framework already in use in this
  addon. Then write the test file to the correct location - do NOT fall back to copy-pasteable
  blocks unless the repo is genuinely inaccessible.
- **Tier 2 - Version fallback:** Derive the Odoo version from any manifest's `version` field
  if `.odoo-ai/context.md` is absent.
- **Copy-pasteable-only mode** (last resort): emit standalone blocks only when the repo itself
  is unreachable. Label output `grounded: local-source (not OSM-indexed)` when built from
  disk; use `OSM unavailable - ungrounded` only when neither OSM nor local source is available.
- Escalate (`NEEDS_CONTEXT`) only for business decisions no source encodes - never ask a human
  to paste field lists, model definitions, or manifests.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Set
`produced` to the test file paths you wrote, and state the **RED confirmation** (in test-first
mode: "RED - production code not yet written"; in coverage mode: "RED-on-rule-removal verified").
A coder consuming these tests implements to green and must not edit them. Additive output for the
depth-0 run-driver - it does not change anything produced above.
