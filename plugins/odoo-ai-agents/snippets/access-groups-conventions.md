<!-- SSOT snippet. Access-group authoring rules for Odoo: which group model the target series uses
     (category or privilege), ir.module.category XML id derivation, implied_ids hierarchy.
     Edit here only; consumers cross-ref, never restate.
     Consumers are DERIVED, never listed here - re-derive with `grep -rl "access-groups-conventions.md" plugins/odoo-ai-agents/`. -->

# Access Groups Conventions - CORE (all distributions)

CORE Odoo rules for declaring `res.groups` records. Which model a group hangs on depends on the
series; the `ir.module.category` id derivation and the `implied_ids` mechanism do not.

## Which group model the target series uses

Resolve it, never assume it: `model_inspect(model='res.groups', method='fields', name_filter='_id',
odoo_version='<target>')`. A `category_id` field means the **category model**, a `privilege_id`
field (and no `category_id`) the **privilege model**. Evidence: with `odoo_version='18.0'` the call
returns `category_id`, with `odoo_version='19.0'` it returns `privilege_id`. In the privilege model
a `category_id` on a `res.groups` record fails the module install, and `base.module_category_usability`
does not exist; `base.module_category_hidden` exists but no group points at it.

---

## Category id (ir.module.category XML id derivation) - both models

When a module declares `application: True` (or otherwise ships custom `res.groups`), Odoo
auto-creates one `ir.module.category` record per segment of the manifest `category` string at
install time, giving each the external id `base.module_category_<slug>`. Compute `<slug>` EXACTLY
as Odoo does:

1. `segments = manifest['category'].split('/')` (e.g. `'Human Resources/Employees'` ->
   `['Human Resources', 'Employees']`).
2. `slug = '_'.join(seg.lower() for seg in segments)` then `.replace('&', 'and').replace(' ', '_')`.
3. The deepest (full-path) id is `base.module_category_<slug>`.

The record that points at it sets `category_id` to the derived id: the `res.groups` record in the
category model, the `res.groups.privilege` record in the privilege model.

```xml
<field name="category_id" ref="base.module_category_<slug>"/>
```

Do NOT invent an id. In the category model do NOT omit `category_id` for an application's groups.

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

---

## Category model - group hierarchy (implied_ids ladder)

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
transitively reach (`trans_implied_ids` in this model) - that transitive closure is what drives the
single-select dropdown rendering.

- Groups that are INDEPENDENT feature toggles (not a privilege ladder) must NOT be chained with
  `implied_ids` - they render as checkboxes, not a dropdown; they take
  `base.module_category_usability`, and a technical group takes `base.module_category_hidden`.
- Never wire an `implied_ids` cycle. The group's users field is `users`; the group link on
  `res.users`, `ir.ui.view` and `ir.ui.menu` is `groups_id`.
- Canonical reference (core `hr/security/hr_security.xml`, v17): `group_hr_user` implies
  `base.group_user`; `group_hr_manager` implies `group_hr_user`; both share
  `category_id = base.module_category_human_resources_employees`.

---

## Privilege model

A `res.groups` record has NO `category_id`; `privilege_id` points at a `res.groups.privilege`,
which carries the `category_id` (optional: without one the privilege lands under "Other"). The
users field is `user_ids`, the transitive implied set `all_implied_ids`, and the group link on
`res.users`, `ir.ui.view` and `ir.ui.menu` is `group_ids` (not `groups_id`). Source: core `base`
`models/res_groups.py`, `models/res_groups_privilege.py`, and the user-form widget
`web/static/src/webclient/res_user_group_ids_field/res_user_group_ids_field.js`.

| The groups are | Declare | User form shows |
|---|---|---|
| Mutually exclusive LEVELS of one app (user < officer < manager), as core `hr` does | one `res.groups.privilege`; every level sets `privilege_id` to it | one select per privilege (placeholder "No" = none) |
| An INDEPENDENT right, or a technical group (core `product.group_product_variant`) | a `res.groups` with NO `privilege_id` | an independent checkbox under "Extra Rights", in developer mode only |

```xml
<record id="res_groups_privilege_<mod>" model="res.groups.privilege">
    <field name="name">App name</field>
    <field name="category_id" ref="base.module_category_<slug>"/>
</record>
<record id="group_<mod>_user" model="res.groups">
    <field name="name">User</field>
    <field name="sequence">10</field>
    <field name="privilege_id" ref="res_groups_privilege_<mod>"/>
    <field name="implied_ids" eval="[(4, ref('base.group_user'))]"/>
</record>
<record id="group_<mod>_manager" model="res.groups">
    <field name="name">Administrator</field>
    <field name="sequence">20</field>
    <field name="privilege_id" ref="res_groups_privilege_<mod>"/>
    <field name="implied_ids" eval="[(4, ref('group_<mod>_user'))]"/>
</record>
<!-- independent toggle: no privilege_id, no implied_ids chain -->
<record id="group_<mod>_<feature>" model="res.groups">
    <field name="name">Feature name</field>
    <field name="comment">What the user may do with it (the checkbox help text).</field>
</record>
```

- Chain levels with `implied_ids` from least to most privileged; the select orders a privilege's
  groups by how many of its own groups each implies, then `sequence`. Never wire a cycle.
- A group name is unique within its privilege (`UNIQUE (privilege_id, name)`).
- Canonical reference (core `hr/security/hr_security.xml`): `group_hr_user` and `group_hr_manager`
  share `res_groups_privilege_employees` (category `base.module_category_human_resources`), the
  manager implying the officer.
