# odoo-test-writing - Output Format

After writing test files, report:

```
Written: <addon>/tests/test_<feature>.py  (<N> test methods)
Grounded: osm | local-source (not OSM-indexed) | OSM unavailable - ungrounded
Framework: TransactionCase (v<X>) | Hoot (v18+) | QUnit (v<=17) - confirm the exact per-module mix via `js_test_inspect` (preferred over a version-only guess; some modules are hybrid)
Business rules covered: [one line per test_* method]
```
