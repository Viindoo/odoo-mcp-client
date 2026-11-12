# Instance-optional vs instance-required completion

When a live Odoo instance/browser is unreachable, which terminal status a skill emits depends
on whether the instance is OPTIONAL or REQUIRED for its PRIMARY deliverable - not on a
per-skill judgment call:

- **Instance-OPTIONAL** (the PRIMARY deliverable is complete WITHOUT an instance - static
  source/code review). Finish the static deliverable, `status: DONE` with a `concerns:` entry for
  the instance-gated dimension (per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`),
  and emit an OPT-IN `next: odoo-acceptance` (L2, human-gated)
  recommending a live verification pass rather than blocking. Example: `odoo-code-review` -
  Python/XML/OWL source review completes fully from static analysis; only the rendered-UI
  dimension needs a live render, so that one dimension is flagged while the overall review
  still ships.
- **Instance-REQUIRED** (the deliverable REQUIRES a live render/execution to exist at all).
  Emit `status: NEEDS_NEXT` with `next: odoo-instance` - there is nothing to ship without the
  instance, so the run stops and hands off provisioning instead of shipping a partial
  artifact. Examples: `odoo-ui-review` (a rated screenshot IS the deliverable),
  `odoo-test-writing` (its break-check runs, `${CLAUDE_PLUGIN_ROOT}/skills/odoo-test-writing/references/no-instance.md`), `odoo-doc-illustration` (screen captures),
  `odoo-acceptance` (live oracle execution).

Rule of thumb: if the skill can finish with a caveat, it is instance-optional
(`status: DONE` + `concerns:` + opt-in `next: odoo-acceptance`); if there is nothing to finish
without the instance, it is instance-required (`NEEDS_NEXT: odoo-instance`).
