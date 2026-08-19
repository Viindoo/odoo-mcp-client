<!-- SSOT snippet. Access-group authoring rules for Odoo: ir.module.category XML id derivation +
     implied_ids hierarchy.
     Edit here only; consumers cross-ref, never restate.
     Consumers are DERIVED, never listed here - re-derive with `grep -rl "access-groups-conventions.md" plugins/odoo-ai-agents/`. -->

# Access Groups Conventions - CORE (all distributions)

CORE Odoo rules for declaring `res.groups` records: how Odoo auto-derives the `ir.module.category`
external id from the manifest `category` string, and how to wire an `implied_ids` privilege ladder
so Settings > Users > Permissions renders it correctly. Both the derivation algorithm and the
`implied_ids` mechanism are algorithmically identical (same output v8-v19).

---

## Category id (ir.module.category XML id derivation)

When a module declares `application: True` (or otherwise ships custom `res.groups`), Odoo
auto-creates one `ir.module.category` record per segment of the manifest `category` string at
install time, giving each the external id `base.module_category_<slug>`. Compute `<slug>` EXACTLY
as Odoo does:

1. `segments = manifest['category'].split('/')` (e.g. `'Human Resources/Employees'` ->
   `['Human Resources', 'Employees']`).
2. `slug = '_'.join(seg.lower() for seg in segments)` then `.replace('&', 'and').replace(' ', '_')`.
3. The deepest (full-path) id is `base.module_category_<slug>`.

A new `res.groups` record MUST set `category_id` to this derived id:

```xml
<field name="category_id" ref="base.module_category_<slug>"/>
```

Do NOT invent an id and do NOT omit `category_id` for an application's groups.

- Only `&` and space are transformed - other characters (`.`, `-`, digits) pass through unchanged,
  and repeated underscores are NOT collapsed.
- To add a sequence/description to the category, re-declare the record under its derived id (as
  core `hr` does):
  ```xml
  <record id="base.module_category_<slug>" model="ir.module.category">
      <field name="sequence">N</field>
  </record>
  ```
- Algorithm is ALGORITHMICALLY IDENTICAL v8-v19 (`odoo/modules/db.py::create_categories`,
  `openerp/modules/db.py` pre-rename - v8-v10 use `'_'.join(map(lambda x: x.lower(), category))`,
  v11+ use an equivalent genexpr; same output, different source literal). Applies v8-v19.

**Worked examples:**

| Manifest `category` | Derived `category_id` | Source |
|---|---|---|
| `Human Resources/Employees` | `base.module_category_human_resources_employees` | core `hr` manifest |
| `Sales/Sales` | `base.module_category_sales_sales` | core `sale` manifest |
| `Accounting & Finance` | `base.module_category_accounting_and_finance` | Viindoo `tvtmaaddons` manifest |

---

## Group hierarchy (implied_ids ladder)

To expose a role LADDER as a single-select dropdown in Settings > Users > Permissions (rather than
independent checkboxes), give every group in the ladder the SAME `category_id` (the derived
`base.module_category_<slug>` from the section above) AND chain them with `implied_ids` from least
to most privileged, with the base rung implying `base.group_user`:

```xml
<record id="group_<mod>_user" model="res.groups">
    <field name="category_id" ref="base.module_category_<slug>"/>
    <field name="implied_ids" eval="[(6, 0, [ref('base.group_user')])]"/>
</record>
<record id="group_<mod>_manager" model="res.groups">
    <field name="category_id" ref="base.module_category_<slug>"/>
    <field name="implied_ids" eval="[(4, ref('group_<mod>_user'))]"/>
</record>
```

Semantics: a user granted `group_<mod>_manager` automatically holds every group its `implied_ids`
transitively reach (Odoo computes `trans_implied_ids`) - that transitive closure is what drives the
single-select dropdown rendering.

- Groups that are INDEPENDENT feature toggles (not a privilege ladder) must NOT be chained with
  `implied_ids` - they render as checkboxes, not a dropdown.
- Never wire an `implied_ids` cycle.
- Canonical reference (core `hr/security/hr_security.xml`, v17): `group_hr_user` implies
  `base.group_user`; `group_hr_manager` implies `group_hr_user`; both share
  `category_id = base.module_category_human_resources_employees`.
- `implied_ids` (and its `trans_implied_ids` compute) on `res.groups` in `base` is stable v8-v19.
