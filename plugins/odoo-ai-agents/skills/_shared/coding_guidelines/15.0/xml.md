> Source: official Odoo 15.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/15.0/content/contributing/development/coding_guidelines.rst

# XML files

## Format

To declare a record in XML, the **record** notation (using *<record>*) is recommended:

- Place `id` attribute before `model`
- For field declaration, `name` attribute is first. Then place the *value* either in the `field` tag, either in the `eval` attribute, and finally other attributes (widget, options, ...) ordered by importance.
- Try to group the record by model. In case of dependencies between action/menu/views, this convention may not be applicable.
- Use naming convention defined at the next point
- The tag *<data>* is only used to set not-updatable data with `noupdate=1`. If there is only not-updatable data in the file, the `noupdate=1` can be set on the `<odoo>` tag and do not set a `<data>` tag.

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

Odoo supports custom tags acting as syntactic sugar:

- menuitem: use it as a shortcut to declare a `ir.ui.menu`
- template: use it to declare a QWeb View requiring only the `arch` section of the view.

These tags are preferred over the *record* notation.

## XML IDs and naming

### Security, View and Action

Use the following pattern :

- For a menu: `<model_name>_menu`, or `<model_name>_menu_<do_stuff>` for submenus.
- For a view: `<model_name>_view_<view_type>`, where *view_type* is `kanban`, `form`, `tree`, `search`, ...
- For an action: the main action respects `<model_name>_action`. Others are suffixed with `_<detail>`, where *detail* is a lowercase string briefly explaining the action. This is used only if multiple actions are declared for the model.
- For window actions: suffix the action name by the specific view information like `<model_name>_action_view_<view_type>`.
- For a group: `<module_name>_group_<group_name>` where *group_name* is the name of the group, generally 'user', 'manager', ...
- For a rule: `<model_name>_rule_<concerned_group>` where *concerned_group* is the short name of the concerned group ('user' for the 'model_name_group_user', 'public' for public user, 'company' for multi-company rules, ...).

Name should be identical to xml id with dots replacing underscores. Actions should have a real naming as it is used as display name.

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

### Inheriting XML

Xml Ids of inheriting views should use the same ID as the original record. It helps finding all inheritance at a glance. As final Xml Ids are prefixed by the module that creates them there is no overlap.

Naming should contain an `.inherit.{details}` suffix to ease understanding the override purpose when looking at its name.

```xml
<record id="model_view_form" model="ir.ui.view">
    <field name="name">model.view.form.inherit.module2</field>
    <field name="inherit_id" ref="module1.model_view_form"/>
    ...
</record>
```

New primary views do not require the inherit suffix as those are new records based upon the first one.

```xml
<record id="module2.model_view_form" model="ir.ui.view">
    <field name="name">model.view.form.module2</field>
    <field name="inherit_id" ref="module1.model_view_form"/>
    <field name="mode">primary</field>
    ...
</record>
```
