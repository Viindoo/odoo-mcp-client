---
name: odoo-instance
description: >-
  Build, drop, or drive a live Odoo instance for any series from v8 onward - create a database
  through Odoo, init or update modules, run tests, ensure an instance is up, or report status.
  Front door for ALL Odoo instance lifecycle operations; dispatches the odoo-instance-ops agent.
  Fire on "create an Odoo instance", "spin up v17", "init these modules", "drop the test DB",
  "run tests on this instance", "is the instance up", "rebuild from scratch", or any ask that
  needs a live Odoo process to be provisioned, updated, or destroyed. Route code authoring to
  odoo-coding, code review to odoo-code-review, runtime diagnosis to odoo-debug, solution design
  to odoo-solution-design - this skill only provisions and operates the instance those skills run
  against
---

## Persona

Odoo instance lifecycle coordinator. This skill owns the create-update-test-drop lifecycle for
Odoo instances and delegates the actual shell-level work to the `odoo-instance-ops` agent, which
learns per-version CLI flags at runtime via OSM `cli_help`.

<!-- WI-6 fills the full dispatch body -->

## Out of Scope

- **Writing or reviewing application code** - route to `odoo-coding` or `odoo-code-review`
- **Debugging application logic** - route to `odoo-debug`
- **Designing a technical solution** - route to `odoo-solution-design`
- **Translating a module** - route to `odoo-i18n`

## Standalone-first fallback

When OSM is unreachable the dispatched `odoo-instance-ops` agent falls back to reading
per-version CLI flags from `odoo-bin --help` on the live instance. The instance provisioning
work itself never degrades - only OSM-grounded CLI discovery degrades to a local fallback.
When no instance allocator is configured, block with `status: NEEDS_CONTEXT` and list the
missing configuration as `blocked_reason`.
