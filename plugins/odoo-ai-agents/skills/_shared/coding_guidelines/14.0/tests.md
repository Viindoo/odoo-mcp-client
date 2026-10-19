> Source: Odoo Semantic MCP `test_base_classes`, `js_test_inspect`, `find_test_examples` and `cli_help`, each queried with `odoo_version='14.0'`; era boundaries in `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md`. What a tool did not return is written here as a lookup, never as a guess.

# Odoo 14.0 - Writing tests

Series-dependent facts only. What a test protects and how it proves it are in
`${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md` and
`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`; which records a test may touch is
in `${CLAUDE_PLUGIN_ROOT}/snippets/modularity-contract.md`.

## Python test classes (`odoo.tests`)

`TransactionCase` (one savepoint per test, rolled back), `SavepointCase` (one savepoint per class, shared setup), `SingleTransactionCase` (one transaction for the class, no per-test rollback), `HttpCase` (real HTTP server, per-test savepoint), `HttpSavepointCase` (HTTP plus class-level savepoint), `Form` and `O2MForm` (server-side onchange simulation, not a case class).

Removed or deprecated in this series: none in this series. Confirm a class before importing it:
`test_base_classes(odoo_version='14.0')`.

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
one tour returned by `find_test_examples(query='tour', odoo_version='14.0')` from a module of this
series, never from another series.

## JavaScript unit tests

QUnit. Unit test files live under `static/tests/` and end in `_tests.js`; they are registered in the `web.qunit_suite_tests` bundle (`web.qunit_mobile_suite_tests` for mobile).

> Plugin rule (not in the upstream text):

- No per-module JS runner exists: a module's JS unit tests run inside `web`'s suite classes, which
  run the JS tests of every installed module; read the module's own failures from the log. When JS
  unit tests are in scope, tag BOTH `/web:WebSuite.test_js` and `/web:MobileWebSuite.test_mobile_js`. Green on one proves
  nothing about the other. The mobile suite runs at `375x667` without touch emulation.

## Demo data

In this series demo data loads by default (`--without-demo` defaults to off): a test MAY use demo records of a module in its upstream closure.

## Data rules

A test creates or reads records only from its module and that module's upstream closure, through
the same calls a user path makes (create, confirm, post, pay): no direct writes to state or
computed fields, no `raise` to simulate a failure. Full rule set: the two test contracts named
at the top of this file.
