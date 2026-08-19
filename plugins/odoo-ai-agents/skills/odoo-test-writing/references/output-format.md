# odoo-test-writing - Output Format

After writing test files, report:

```
Written: <addon>/tests/test_<feature>.py  (<N> test methods)
Grounded: osm | local-source (not OSM-indexed) | OSM unavailable - ungrounded
Framework: <Python base class, e.g. TransactionCase> | <the JS mix `js_test_inspect(<module>, <series>)` actually reports for this module> - NEVER a series-only guess: Hoot and QUnit both ship and both run on the same series (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 2)
Business rules covered: [one line per test_* method]
```
