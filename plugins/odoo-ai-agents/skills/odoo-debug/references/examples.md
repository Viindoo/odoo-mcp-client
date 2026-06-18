# odoo-debug - Worked Examples

## Example 1 - backend, contained

Prompt: "Tại sao computed field `amount_total` trên sale.order không cập nhật khi sửa dòng?"

- Phase 0: layer=backend, plan preview.
- Phase 1 (haiku): reproduce = edit a line, total stays; complexity = contained.
- Phase 2 (sonnet): `odoo-backend-debugger` → `@api.depends` omits `order_line.price_subtotal`;
  confirm-by-toggle: add the depends locally, total updates.
- Phase 3 (sonnet): refute pass holds.
- Phase 4: root cause + fix location + regression test → hand off `odoo-coding`.

## Example 2 - UI, browser (serial)

Prompt: "My custom OWL field widget doesn't show up in the Odoo 17 form."

- Phase 1 (haiku): reproduce; console shows `Missing template`.
- Phase 2 (sonnet): `odoo-ui-debugger` ALONE (browser exclusive) → `t-name` mismatch JS↔QWeb;
  snapshot shows node absent. Confidence MEDIUM (JS location inferred - known OSM gap).
- Phase 3 + 4: verify, synthesize, hand off `odoo-coding`.
