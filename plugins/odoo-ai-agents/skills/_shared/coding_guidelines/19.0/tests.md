> Source: Odoo Semantic MCP `test_base_classes`, `js_test_inspect`, `find_test_examples` and `cli_help`, each queried with `odoo_version='19.0'`; era boundaries in `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md`. What a tool did not return is written here as a lookup, never as a guess.

# Odoo 19.0 - Writing tests

Series-dependent facts only. What a test protects and how it proves it are in
`${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md` and
`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md`; which records a test may touch is
in `${CLAUDE_PLUGIN_ROOT}/snippets/modularity-contract.md`.

## Python test classes (`odoo.tests`)

`TransactionCase` (one savepoint per test, rolled back; `setUpClass` calls `super()` first), `SingleTransactionCase`, `HttpCase`, `Form` and `O2MForm`.

Removed or deprecated in this series: `SavepointCase` and `HttpSavepointCase` are REMOVED: `SavepointCase` -> `TransactionCase`, `HttpSavepointCase` -> `HttpCase`. Confirm a class before importing it:
`test_base_classes(odoo_version='19.0')`.

Install phase and selection: `@tagged('post_install', '-at_install')` on the class, module tags
`/<module>` on the command line. `cr.commit()` and `cr.rollback()` never appear in a test.

## Form tests

`Form(record_or_model)` drives onchanges server-side the way the web client does, then `.save()`.
Use it to prove behaviour that lives in an onchange or in a form-only modifier; a `Form` save
persists fields the real client never sends, so a rule that must hold on the real client is
covered by a tour or an `HttpCase` as well.

## HTTP and tours

`HttpCase` starts a real server. A tour runs with `self.start_tour("/odoo", "<tour_name>", login="admin")`
from an `HttpCase`. The tour file lives under `static/tests/tours/`; copy the registration form of
one tour returned by `find_test_examples(query='tour', odoo_version='19.0')` from a module of this
series, never from another series.

## JavaScript unit tests

Hoot is the runner for new tests; the QUnit runner is deprecated. Hoot test files live under `static/tests/` and end in `.test.js`; the Python side runs them with `browser_js('/web/tests?headless&preset=desktop...', success_signal='[HOOT] Test suite succeeded')`. Confirm the asset bundle name with `find_test_examples(query='hoot unit test bundle', odoo_version='19.0')` before writing the manifest entry. A QUnit test ported from an older series is rewritten as a Hoot test, never copied as is.

## Demo data

In this series demo data does NOT load by default (`--without-demo` is the default; `--test-enable` implies `--stop-after-init`): a test builds every record it needs and never relies on demo data.

## Data rules

A test creates or reads records only from its module and that module's upstream closure, through
the same calls a user path makes (create, confirm, post, pay): no direct writes to state or
computed fields, no `raise` to simulate a failure. Full rule set: the two test contracts named
at the top of this file.
