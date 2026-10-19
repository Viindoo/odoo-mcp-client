> Source: Odoo Semantic MCP `test_base_classes`, `js_test_inspect`, `find_test_examples` and `cli_help`, each queried with `odoo_version='17.0'`; era boundaries in `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md`. What a tool did not return is written here as a lookup, never as a guess.

# Odoo 17.0 - Writing tests

Series-dependent facts only. What a test protects and how it proves it are in
`${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md` and
`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`; which records a test may touch is
in `${CLAUDE_PLUGIN_ROOT}/snippets/modularity-contract.md`.

## Python test classes (`odoo.tests`)

`TransactionCase` (one savepoint per test, rolled back; `setUpClass` calls `super()` first), `SingleTransactionCase`, `HttpCase`, `Form` and `O2MForm`.

Removed or deprecated in this series: `SavepointCase` and `HttpSavepointCase` are REMOVED: `SavepointCase` -> `TransactionCase`, `HttpSavepointCase` -> `HttpCase`. Confirm a class before importing it:
`test_base_classes(odoo_version='17.0')`.

Install phase and selection: `@tagged('post_install', '-at_install')` on the class, module tags
`/<module>` on the command line. `cr.commit()` and `cr.rollback()` never appear in a test.

## Form tests

`Form(record_or_model)` drives onchanges server-side the way the web client does, then `.save()`.
Use it to prove behaviour that lives in an onchange or in a form-only modifier; a `Form` save
persists fields the real client never sends, so a rule that must hold on the real client is
covered by a tour or an `HttpCase` as well.

## HTTP and tours

`HttpCase` starts a real server. A tour runs with `self.start_tour("/web", "<tour_name>", login="admin")`
from an `HttpCase`. The tour file lives under `static/tests/tours/`; copy the registration form of
one tour returned by `find_test_examples(query='tour', odoo_version='17.0')` from a module of this
series, never from another series.

## JavaScript unit tests

QUnit. Unit test files live under `static/tests/` and end in `_tests.js`. Confirm the asset bundle name for this series with `find_test_examples(query='qunit suite bundle', odoo_version='17.0')` before writing the manifest entry.

> Plugin rule (not in the upstream text):

- No per-module JS runner exists: a module's JS unit tests run inside `web`'s suite classes, which
  run the JS tests of every installed module; read the module's own failures from the log. When JS
  unit tests are in scope, tag BOTH `/web:WebSuite.test_js` and `/web:MobileWebSuite.test_mobile_js`. Green on one proves
  nothing about the other. The mobile suite runs at `375x667` with touch emulation.
- Touch: `hasTouch()` reads `browser.ontouchstart`, copied from `window` when `browser` is
  imported, or a coarse pointer from `browser.matchMedia`; changing `window` inside a test changes
  nothing. A test that needs a device condition patches `browser` with `patchWithCleanup`
  (`ontouchstart`, and `matchMedia` where the mobile suite reports a coarse pointer), as core
  `tooltip_service_tests.js` does for `ontouchstart`. A test titled for a device condition
  establishes that condition itself.

## Demo data

In this series demo data loads by default (`--without-demo` defaults to off): a test MAY use demo records of a module in its upstream closure.

## Data rules

A test creates or reads records only from its module and that module's upstream closure, through
the same calls a user path makes (create, confirm, post, pay): no direct writes to state or
computed fields, no `raise` to simulate a failure. Full rule set: the two test contracts named
at the top of this file.
