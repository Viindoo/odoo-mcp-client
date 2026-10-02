# odoo-test-writing - Output Format

After writing or adjusting test files, report:

```
Written: <addon>/tests/test_<feature>.py  (<N> test methods)
Registered: <addon>/tests/__init__.py (the module's own __init__.py untouched)
Grounded: osm | local-source (not OSM-indexed) | OSM unavailable - ungrounded
Framework: <Python base class, e.g. TransactionCase> | <the JS mix `js_test_inspect(<module>, <series>)` actually reports for this module> - NEVER a series-only guess: Hoot and QUnit both ship and both run on the same series (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 2)
Form view grounded: <model + view per form-entered rule, or "none - no form-entered rule">
Business rules covered: [one line per test_* method]
Baseline: <the targeted methods, TESTS_RUN, all passed on the unbroken code>
Per target behavior, the record(s) in the exact shapes ${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md § Break-check record fixes, one per line:
  BREAK_CHECK | COVERED | ADJUSTED (then its BREAK_CHECK) | ABSORBED (adapt, bucket (a)) | NO NEW TEST
  MANIFEST TEST ASSETS - only when a test asset was registered in __manifest__.py
  PENDING BREAK_CHECK - only with no INSTANCE_HANDLE
```
