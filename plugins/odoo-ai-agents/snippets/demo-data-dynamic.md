<!-- SSOT snippet. Referenced (not copy-pasted) by odoo-solution-architect (designs it) and
     odoo-coder (implements it). Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/demo-data-dynamic.md. -->

# Dynamic Demo Data (demo-readiness, not test fixtures)

Demo data exists so the feature can be **demonstrated on a fresh database without manual data
entry** - a sales rep, a prospect call, an internal walkthrough. It is NOT a test fixture: test
fixtures live in `tests/` and exist for isolation/assertions; demo data lives in `demo/` and exists
for live demo readiness. Keep the two separate and serve both.

## Rule: every new end-user-visible model or behavior ships demo data

If the design introduces a new model or a new behavior a user can see/operate, it MUST include demo
data that exercises it, so the feature is demo-ready the moment the module installs with
`--demo`/demo enabled.

## Make it dynamic in time (so the demo never looks stale)

Hardcoded dates rot: a demo installed in 2026 showing 2023 orders looks broken. Anchor date/datetime
fields to *now* with `relativedelta` so the data is always fresh relative to install time:

```xml
<!-- demo/<feature>_demo.xml -->
<record id="demo_sale_order_recent" model="sale.order">
    <field name="partner_id" ref="base.res_partner_2"/>
    <field name="date_order"
           eval="(DateTime.today() - relativedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')"/>
</record>
```

- Use `DateTime` / `relativedelta` (available in the data-XML eval context) - spread records across
  a believable recent window (`days=2`, `days=14`, `days=45`, ...) so the demo shows a realistic
  timeline on any install date.
- Wire it in the manifest under `demo=[...]` (not `data=[...]`). Demo files are loaded only with
  demo enabled.
- `noupdate`: demo records default to `noupdate="0"` so a `-u` refresh re-seeds them. Use
  `noupdate="1"` only for demo records a user is meant to edit and keep across upgrades.

## Distinguish from fixtures - one line in the design

The architect states, per new model/behavior: "demo data: <records + which dates are time-relative>"
in the design doc; the coder implements exactly that in `demo/`. Neither puts demo data in `tests/`,
nor relies on demo data for test assertions (tests build their own deterministic data).
