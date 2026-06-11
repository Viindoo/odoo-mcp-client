> Source: official Odoo 17.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/17.0/content/contributing/development/coding_guidelines.rst

# XML Guidelines

## Format

To declare a record in XML, the **record** notation (using `<record>`) is recommended:

- Place `id` attribute before `model`
- For field declaration, `name` attribute is first. Then place the value either in the `field`
  tag or in the `eval` attribute, and finally other attributes (widget, options, ...) ordered by
  importance.
- Try to group records by model. In case of dependencies between action/menu/views, this
  convention may not be applicable.
- Use the naming convention defined below.
- The tag `<data>` is only used to set not-updatable data with `noupdate=1`. If there is only
  not-updatable data in the file, the `noupdate=1` can be set on the `<odoo>` tag and do not
  set a `<data>` tag.

```xml
<record id="view_id" model="ir.ui.view">
    <field name="name">view.name</field>
    <field name="model">object_name</field>
    <field name="priority" eval="16"/>
    <field name="arch" type="xml">
        <tree>
            <field name="my_field_1"/>
            <field name="my_field_2" string="My Label" widget="statusbar" statusbar_visible="draft,sent,progress,done" />
        </tree>
    </field>
</record>
```

> Note (17.0): The view type is `tree` (not `list`). List views are declared with the `<tree>`
> element in 17.0.

Odoo supports custom tags acting as syntactic sugar - these are preferred over the record notation:

- `menuitem` - shortcut to declare a `ir.ui.menu`
- `template` - shortcut to declare a QWeb View requiring only the `arch` section

---

## XML IDs and naming

### Security, View and Action patterns

| Element | Pattern |
|---|---|
| Menu | `<model_name>_menu` or `<model_name>_menu_<do_stuff>` for submenus |
| View | `<model_name>_view_<view_type>` where view_type is `kanban`, `form`, `tree`, `search`, ... |
| Main action | `<model_name>_action` |
| Other actions | `<model_name>_action_<detail>` where detail briefly explains the action |
| Window action with specific view | `<model_name>_action_view_<view_type>` |
| Group | `<module_name>_group_<group_name>` where group_name is 'user', 'manager', etc. |
| Rule | `<model_name>_rule_<concerned_group>` where concerned_group is 'user', 'public', 'company', etc. |

Name should be identical to xml id with dots replacing underscores. Actions should have a real
naming as it is used as display name.

```xml
<!-- views  -->
<record id="model_name_view_form" model="ir.ui.view">
    <field name="name">model.name.view.form</field>
    ...
</record>

<record id="model_name_view_kanban" model="ir.ui.view">
    <field name="name">model.name.view.kanban</field>
    ...
</record>

<!-- actions -->
<record id="model_name_action" model="ir.act.window">
    <field name="name">Model Main Action</field>
    ...
</record>

<record id="model_name_action_child_list" model="ir.actions.act_window">
    <field name="name">Model Access Children</field>
</record>

<!-- menus and sub-menus -->
<menuitem
    id="model_name_menu_root"
    name="Main Menu"
    sequence="5"
/>
<menuitem
    id="model_name_menu_action"
    name="Sub Menu 1"
    parent="module_name.module_name_menu_root"
    action="model_name_action"
    sequence="10"
/>

<!-- security -->
<record id="module_name_group_user" model="res.groups">
    ...
</record>

<record id="model_name_rule_public" model="ir.rule">
    ...
</record>

<record id="model_name_rule_company" model="ir.rule">
    ...
</record>
```

---

## Inheriting XML

XML IDs of inheriting views should use the **same ID** as the original record. It helps finding
all inheritance at a glance. As final XML IDs are prefixed by the module that creates them there
is no overlap.

Naming should contain an `.inherit.{details}` suffix to ease understanding the override purpose
when looking at its name.

```xml
<record id="model_view_form" model="ir.ui.view">
    <field name="name">model.view.form.inherit.module2</field>
    <field name="inherit_id" ref="module1.model_view_form"/>
    ...
</record>
```

New **primary views** do not require the inherit suffix as those are new records based upon the
first one:

```xml
<record id="module2.model_view_form" model="ir.ui.view">
    <field name="name">model.view.form.module2</field>
    <field name="inherit_id" ref="module1.model_view_form"/>
    <field name="mode">primary</field>
    ...
</record>
```

---

## `<data noupdate>`

The `<data>` tag is only used to set not-updatable data with `noupdate=1`.

- If the entire file contains only not-updatable data, set `noupdate=1` directly on the `<odoo>`
  tag and do **not** add a `<data>` tag.
- Only use `<data noupdate="1">` when a file contains a mix of updatable and not-updatable
  records.
