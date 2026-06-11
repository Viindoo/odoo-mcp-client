> Source: official Odoo 17.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/17.0/content/contributing/development/coding_guidelines.rst

# Naming Conventions

## Model names (`_name`)

Use dot notation, prefixed by the module name.

- **Regular model**: use singular form.
  - Good: `res.partner`, `sale.order`
  - Bad: `res.partnerS`, `saleS.orderS`
- **Transient model (wizard)**: use `<related_base_model>.<action>` where `related_base_model` is
  the base model (defined in `models/`) related to the transient, and `action` is the short name
  of what the transient does. **Avoid the word "wizard".**
  - Examples: `account.invoice.make`, `project.task.delegate.batch`
- **Report model (SQL views)**: use `<related_base_model>.report.<action>`, based on the transient
  convention.

---

## Python class names

Use **Pascal case** (Object-oriented style).

```python
class AccountInvoice(models.Model):
    ...
```

---

## Variable names

- Use **Pascal case** for model variables.
- Use **underscore lowercase** notation for common variables.
- Suffix variable name with `_id` or `_ids` if it contains a record id or list of ids.
  Do **not** use `partner_id` to contain a record of `res.partner` (it should contain an id).

```python
Partner = self.env['res.partner']
partners = Partner.browse(ids)
partner_id = partners[0].id
```

---

## Field naming

- `One2Many` and `Many2Many` fields should always have `_ids` as suffix.
  - Example: `sale_order_line_ids`
- `Many2One` fields should have `_id` as suffix.
  - Examples: `partner_id`, `user_id`

---

## Method naming (prefixes)

| Method type | Pattern | Notes |
|---|---|---|
| Compute field | `_compute_<field_name>` | |
| Search method | `_search_<field_name>` | |
| Default method | `_default_<field_name>` | |
| Selection method | `_selection_<field_name>` | Returns computed values for selection fields |
| Onchange method | `_onchange_<field_name>` | |
| Constraint method | `_check_<constraint_name>` | |
| Action method | `action_<...>` | Uses only one record; add `self.ensure_one()` at the beginning |
