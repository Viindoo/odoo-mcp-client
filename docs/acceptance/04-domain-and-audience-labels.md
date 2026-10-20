# Scenario 4 - business function and audience labels

**Setup.** A set of requests with a reference label each: a sales change, an accounting change,
a payroll localization, a forward-port, and a request that crosses sales and accounting.

**Run.** `/odoo-intake` on each request up to its hand-off; for the multi-node ones up to
the design.

**Measure:** the `business_function` and `audience` on each unit against the reference label,
and the `A -> B` interaction line on the cross-domain request.

**Pass when** every label matches the reference, no label is derived from a technical word
(module, model, compute, inherit), and the specialist list sends only accounting, tax, payroll,
localization and legal units to R3.
