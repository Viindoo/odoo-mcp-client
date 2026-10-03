# odoo-test-writing - Output Format

After writing or adjusting tests, report briefly - free form, no fixed grammar, as plain lines outside any
code fence (its `grounded:` line is your grounding claim, `${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md` §5):

```
Written: <addon>/tests/test_<feature>.py (<N> test methods), registered in tests/__init__.py
grounded: osm | hybrid | local-source | ungrounded
Framework: <Python base class> | <the JS mix js_test_inspect reports for this module - never a series-only guess>
Baseline: <the targeted tests, all passing on the unbroken code>
Per behavior test, one line - for example:
  test_discount_above_cap_is_refused - disabled the cap check in models/sale_order.py:42 -> failed at its assertRaises; restored (hash matches)
Already covered: <existing tests you proved by a break, or none>
Adjusted: <test - why the REQUEST changed that behavior, or none>
No new test: <behavior - one-line reason, or none>
Pending (no instance): <method-level test ids, or none>
```
