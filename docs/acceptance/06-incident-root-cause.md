# Scenario 6 - an incident with a traceback

**Setup.** A reproducible failure with a traceback (backend) and one with a blank render (UI).

**Run.** `/odoo-debug "<the symptom>"` for each.

**Measure:** one debugger launched per incident; whether the first pass (sonnet) proved the
root cause by toggle, and if not, whether the opus pass with `PRIOR_FINDINGS` did; time from
request to the proven cause; the fix landing through `odoo-coding` at the tier the report
allowed.

**Pass when** each root cause is proven with an executed or described toggle and no incident
needed more than two tiers.
