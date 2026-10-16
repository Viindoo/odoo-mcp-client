# Scenario 5 - forward-port with the orchestrator at sonnet

**Setup.** One or two modules with a short commit range to port between two series.

**Run.** `/odoo-forward-port <range> <target>`.

**Measure:** the orchestrator runs at `sonnet`; every adapt is done by one `odoo-coder` per
module, resumed, never relaunched; the batch passes acceptance and i18n before the PR; the
result is compared with the previous release's run of the same range (time, review findings,
test outcome).

**Pass when** the port lands with the same or better outcome at the lower tier.
