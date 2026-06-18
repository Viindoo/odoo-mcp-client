# odoo-test-writing - Output Format

After writing test files, report:

```
Written: <addon>/tests/test_<feature>.py  (<N> test methods)
Grounded: osm | local-source (not OSM-indexed) | OSM unavailable - ungrounded
Framework: TransactionCase (v<X>) | Hoot (v17+) | QUnit (v<=16)
Business rules covered: [one line per test_* method]
```
