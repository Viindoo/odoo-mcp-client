> Source: official Odoo 19.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/19.0/content/contributing/development/coding_guidelines.rst

# Symbols and Conventions

## Model name

Model name (using the dot notation, prefix by the module name) :

- When defining an Odoo Model : use singular form of the name (*res.partner* and *sale.order* instead of *res.partnerS* and *saleS.orderS*)
- When defining an Odoo Transient (wizard) : use `<related_base_model>.<action>` where *related_base_model* is the base model (defined in *models/*) related to the transient, and *action* is the short name of what the transient do. Avoid the *wizard* word. For instance : `account.invoice.make`, `project.task.delegate.batch`, ...
- When defining *report* model (SQL views e.i.) : use `<related_base_model>.report.<action>`, based on the Transient convention.

## Odoo Python Class

Odoo Python Class : use Pascal case (Object-oriented style).

```python
class AccountInvoice(models.Model):
    ...
```

## Variable name

Variable name :

- use Pascal case for model variable
- use underscore lowercase notation for common variable.
- suffix your variable name with *_id* or *_ids* if it contains a record id or list of id. Don't use `partner_id` to contain a record of res.partner

```python
Partner = self.env['res.partner']
partners = Partner.browse(ids)
partner_id = partners[0].id
```

## Field suffixes

- `One2Many` and `Many2Many` fields should always have *_ids* as suffix (example: sale_order_line_ids)
- `Many2One` fields should have *_id* as suffix (example : partner_id, user_id, ...)

## Method conventions

- Compute Field : the compute method pattern is *_compute_<field_name>*
- Search method : the search method pattern is *_search_<field_name>*
- Default method : the default method pattern is *_default_<field_name>*
- Selection method: the selection method pattern is *_selection_<field_name>*
- Onchange method : the onchange method pattern is *_onchange_<field_name>*
- Constraint method : the constraint method pattern is *_check_<constraint_name>*
- Action method : an object action method is prefix with *action_*. Since it uses only one record, add `self.ensure_one()` at the beginning of the method.
