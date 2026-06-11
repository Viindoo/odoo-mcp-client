> Source: official Odoo 17.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/17.0/content/contributing/development/coding_guidelines.rst

# Model Attribute Ordering

In a Model class, attribute order should be:

1. Private attributes (`_name`, `_description`, `_inherit`, `_sql_constraints`, ...)
2. Default method and `default_get`
3. Field declarations
4. Compute, inverse and search methods in the same order as field declaration
5. Selection method (methods used to return computed values for selection fields)
6. Constraints methods (`@api.constrains`) and onchange methods (`@api.onchange`)
7. CRUD methods (ORM overrides)
8. Action methods
9. Other business methods

---

## Annotated example

```python
class Event(models.Model):
    # Private attributes
    _name = 'event.event'
    _description = 'Event'

    # Default methods
    def _default_name(self):
        ...

    # Fields declaration
    name = fields.Char(string='Name', default=_default_name)
    seats_reserved = fields.Integer(string='Reserved Seats', store=True,
        readonly=True, compute='_compute_seats')
    seats_available = fields.Integer(string='Available Seats', store=True,
        readonly=True, compute='_compute_seats')
    price = fields.Integer(string='Price')
    event_type = fields.Selection(string="Type", selection='_selection_type')

    # compute and search fields, in the same order of fields declaration
    @api.depends('seats_max', 'registration_ids.state', 'registration_ids.nb_register')
    def _compute_seats(self):
        ...

    @api.model
    def _selection_type(self):
        return []

    # Constraints and onchanges
    @api.constrains('seats_max', 'seats_available')
    def _check_seats_limit(self):
        ...

    @api.onchange('date_begin')
    def _onchange_date_begin(self):
        ...

    # CRUD methods (and name_search, _search, ...) overrides
    def create(self, values):
        ...

    # Action methods
    def action_validate(self):
        self.ensure_one()
        ...

    # Business methods
    def mail_user_confirm(self):
        ...
```
