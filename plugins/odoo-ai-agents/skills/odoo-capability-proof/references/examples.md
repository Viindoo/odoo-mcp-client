# Capability Proof — Worked Examples

**Example 1:**
Prompt: "prove Odoo can handle multi-currency invoicing for our prospect"
Output: Verdict "Supported natively", evidence table citing `account.move` fields (`currency_id`,
`amount_currency`, `currency_rate`) from `model_inspect(model='account.move', method='fields', odoo_version='<version>')`, a
real code example, and demo steps.

**Example 2:**
Prompt: "prove Odoo 17 supports multi-level approval for purchase orders"
Output: Verdict with `purchase_stock` + `purchase` module evidence,
`entity_lookup(kind='method', model='purchase.order', method_name='button_approve', odoo_version='<version>')` override
chain, and demo steps.
