# odoo-debug - Worked Examples

## Example 1 - backend, contained

Prompt: "Why does the computed field `amount_total` on sale.order not update when a line changes?"

- Step 1 (inline): layer = backend; reproduction = edit a line, the total stays; the module is in
  the worktree under edit, so its field definitions are read from disk.
- Step 2 (`odoo-backend-debugger`, sonnet): `@api.depends` omits `order_line.price_subtotal`;
  confirm-by-toggle described: add the dependency, the total updates. Root cause proven.
- Step 4: `odoo-coding` writes the regression test first, then the fix.

## Example 2 - UI, browser-serial, escalated once

Prompt: "My custom OWL field widget does not show up in the form."

- Step 1 (inline): layer = ui; the console shows `Missing template`.
- Step 2 (`odoo-ui-debugger`, sonnet): three hypotheses excluded (registry key, asset bundle,
  template id spelling); `Confirm-by-toggle: NOT YET CONFIRMED`.
- Step 3 (`odoo-ui-debugger`, opus, `PRIOR_FINDINGS` = the sonnet report): the template is
  registered under the module's old technical name after a rename; toggle executed with
  `evaluate_script`. Root cause proven.
- Step 4: `odoo-coding`.
