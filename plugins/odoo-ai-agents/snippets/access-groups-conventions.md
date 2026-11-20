# Access Groups Conventions - CORE (all distributions)

Core Odoo rules for declaring `res.groups` records and the record rules of a group. Which model a
group hangs on depends on the series; the `ir.module.category` id derivation, the `implied_ids`
mechanism and the record-rule flags do not. A new group's xml id is `group_<mod>_<name>`, the
form core's own groups take; a group that exists keeps its id.

## Which group model the target series uses

Resolve it, never assume it: `model_inspect(model='res.groups', method='fields', name_filter='_id',
odoo_version='<target>')`. A `category_id` field means the **category model**, a `privilege_id`
field (and no `category_id`) the **privilege model**; the series each starts at and the fields it
renames are in `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Access groups. In the
privilege model a `category_id` on a `res.groups` record fails the module install, and
`base.module_category_usability` does not exist; `base.module_category_hidden` exists but no group
points at it.

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

Never invent an id. In the category model an application's groups always carry `category_id`.

- Only `&` and space are transformed - other characters (`.`, `-`, digits) pass through unchanged,
  and repeated underscores are NOT collapsed.
- To add a sequence/description to the category, re-declare the record under its derived id (as
  core `hr` does):
  ```xml
  <record id="base.module_category_<slug>" model="ir.module.category">
      <field name="sequence">N</field>
  </record>
  ```

---

## Category model - group hierarchy (implied_ids ladder)

To expose a role LADDER as a single-select dropdown in Settings > Users > Permissions (rather than
independent checkboxes), give every group in the ladder the SAME `category_id` AND chain them with
`implied_ids` from least to most privileged, with the base rung implying `base.group_user`:

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

A user granted `group_<mod>_manager` holds every group its `implied_ids` transitively reach
(`trans_implied_ids` in this model); that closure is what renders the single select.

- Groups that are INDEPENDENT feature toggles (not a privilege ladder) must NOT be chained with
  `implied_ids` - they render as checkboxes, not a dropdown; they take
  `base.module_category_usability`, and a technical group takes `base.module_category_hidden`.
- Never wire an `implied_ids` cycle. The group's users field is `users`; the group link on
  `res.users`, `ir.ui.view`, `ir.ui.menu` and the actions (`ir.actions.act_window`,
  `ir.actions.server`, `ir.actions.report`) is `groups_id`.

---

## Privilege model

A `res.groups` record has NO `category_id`; `privilege_id` points at a `res.groups.privilege`,
which carries the `category_id` (optional: without one the privilege lands under "Other"). The
users field is `user_ids`, the transitive implied set `all_implied_ids`, and the group link on
`res.users`, `ir.ui.view`, `ir.ui.menu` and the actions (`ir.actions.act_window`,
`ir.actions.server`, `ir.actions.report`) is `group_ids` (not `groups_id`).

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

## Record rules of a group

A rule with `groups` applies to an operation only where its `perm_*` flag is set, an omitted flag
is set, and for one operation the rules of all the user's groups are OR-ed. So such a rule grants
as well as restricts: on a read-only group, a rule that leaves `perm_write` set lets a user who
also holds a writing group write every record that rule matches.

- Set a flag only for an operation that an access row of the rule's group, or of a group it
  implies, grants on that model; write every other flag as `False`.
- Narrow an operation on the rule of the group whose access row grants it, never by a rule on
  another group.

```xml
<record id="x_document_rule_reader" model="ir.rule">
    <field name="model_id" ref="model_x_document"/>
    <field name="groups" eval="[(4, ref('group_x_reader'))]"/>
    <field name="domain_force">[('team_id.member_ids', 'in', user.id)]</field>
    <field name="perm_write" eval="False"/>
    <field name="perm_create" eval="False"/>
    <field name="perm_unlink" eval="False"/>
</record>
```

## Two sensitive domains

A group that opens one sensitive domain (payroll data, accounting entries) never implies, and is
never implied by, the group of another, and no access row, record rule or `sudo` shows one
domain's data to the other's users. A menu or button that needs both requires both groups, and
the tests cover a user with only one, only the other, and both.
