# odoo-test-writing - Output Format

After writing or adjusting test files, report:

```
Written: <addon>/tests/test_<feature>.py  (<N> test methods)
Grounded: osm | local-source (not OSM-indexed) | OSM unavailable - ungrounded
Framework: <Python base class, e.g. TransactionCase> | <the JS mix `js_test_inspect(<module>, <series>)` actually reports for this module> - NEVER a series-only guess: Hoot and QUnit both ship and both run on the same series (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 2)
Business rules covered: [one line per test_* method]
Per target behavior, exactly one of:
  BREAK_CHECK: <the shape ${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md § Break-check record fixes>
  COVERED: <existing test ids that already protect it - nothing written>
  ADJUSTED: <test> - intent <old> -> <new> per <REQUEST item/AC>   (then its BREAK_CHECK line)
  NO NEW TEST: <behavior> - <reason>
```
