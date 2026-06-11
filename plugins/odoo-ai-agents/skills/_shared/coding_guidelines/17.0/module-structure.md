> Source: official Odoo 17.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/17.0/content/contributing/development/coding_guidelines.rst

# Module Structure

## Warning: Community modules

For modules developed by the community, it is strongly recommended to name your module with a
prefix like your company name.

---

## Directories

A module is organized in important directories. Those contain the business logic; having a look
at them should make you understand the purpose of the module.

**Core directories:**
- `data/` - demo and data xml
- `models/` - models definition
- `controllers/` - contains controllers (HTTP routes)
- `views/` - contains the views and templates
- `static/` - contains the web assets, separated into `css/`, `js/`, `img/`, `lib/`, ...

**Optional directories:**
- `wizard/` - regroups the transient models (`models.TransientModel`) and their views
- `report/` - contains the printable reports and models based on SQL views. Python objects and XML
  views are included in this directory
- `tests/` - contains the Python tests

---

## File naming

> Note: File names should only contain `[a-z0-9_]` (lowercase alphanumerics and `_`)

> Warning: Use correct file permissions: folder 755 and file 644.

### Models

Split the business logic by sets of models belonging to a same main model. Each set lies in a
given file named based on its main model. If there is only one model, its name is the same as
the module name. Each inherited model should be in its own file to help understanding of impacted
models.

```text
addons/plant_nursery/
|-- models/
|   |-- plant_nursery.py      (first main model)
|   |-- plant_order.py        (another main model)
|   |-- res_partner.py        (inherited Odoo model)
```

### Security

Three main files:
- `ir.model.access.csv` - definition of access rights
- `<module>_groups.xml` - user groups
- `<model>_security.xml` - record rules

```text
addons/plant_nursery/
|-- security/
|   |-- ir.model.access.csv
|   |-- plant_nursery_groups.xml
|   |-- plant_nursery_security.xml
|   |-- plant_order_security.xml
```

### Views

Backend views should be split like models and suffixed by `_views.xml`. Backend views are list,
form, kanban, activity, graph, pivot, ... views. Main menus not linked to specific actions may be
extracted into an optional `<module>_menus.xml` file. Templates (QWeb pages for portal / website)
are put in separate files named `<model>_templates.xml`.

```text
addons/plant_nursery/
|-- views/
|   |-- plant_nursery_menus.xml       (optional definition of main menus)
|   |-- plant_nursery_views.xml       (backend views)
|   |-- plant_nursery_templates.xml   (portal templates)
|   |-- plant_order_views.xml
|   |-- plant_order_templates.xml
|   |-- res_partner_views.xml
```

### Data

Split by purpose (demo or data) and main model. Filenames are the main_model name suffixed by
`_demo.xml` or `_data.xml`.

```text
addons/plant_nursery/
|-- data/
|   |-- plant_nursery_data.xml
|   |-- plant_nursery_demo.xml
|   |-- mail_data.xml
```

### Controllers

Generally all controllers belong to a single file named `<module_name>.py`. The old convention of
naming it `main.py` is considered outdated. If you need to inherit an existing controller from
another module, do it in `<inherited_module_name>.py`.

```text
addons/plant_nursery/
|-- controllers/
|   |-- plant_nursery.py
|   |-- portal.py             (inheriting portal/controllers/portal.py)
|   |-- main.py               (deprecated, replaced by plant_nursery.py)
```

### Static files

Javascript files follow the same logic as Python models - each component should be in its own file
with a meaningful name. The same logic applies to templates of JS widgets (static XML files) and
their styles (scss files). **Do not link data (images, libraries) outside Odoo - do not use an URL
to an image but copy it in the codebase instead.**

### Wizards

Naming convention is the same as for Python models: `<transient>.py` and `<transient>_views.xml`.
Both are put in the `wizard/` directory.

```text
addons/plant_nursery/
|-- wizard/
|   |-- make_plant_order.py
|   |-- make_plant_order_views.xml
```

### Reports

Statistics reports (Python/SQL views + classic views):

```text
addons/plant_nursery/
|-- report/
|   |-- plant_order_report.py
|   |-- plant_order_report_views.xml
```

Printable reports (data preparation + QWeb templates):

```text
addons/plant_nursery/
|-- report/
|   |-- plant_order_reports.xml       (report actions, paperformat, ...)
|   |-- plant_order_templates.xml     (xml report templates)
```

---

## Complete module tree example

```text
addons/plant_nursery/
|-- __init__.py
|-- __manifest__.py
|-- controllers/
|   |-- __init__.py
|   |-- plant_nursery.py
|   |-- portal.py
|-- data/
|   |-- plant_nursery_data.xml
|   |-- plant_nursery_demo.xml
|   |-- mail_data.xml
|-- models/
|   |-- __init__.py
|   |-- plant_nursery.py
|   |-- plant_order.py
|   |-- res_partner.py
|-- report/
|   |-- __init__.py
|   |-- plant_order_report.py
|   |-- plant_order_report_views.xml
|   |-- plant_order_reports.xml
|   |-- plant_order_templates.xml
|-- security/
|   |-- ir.model.access.csv
|   |-- plant_nursery_groups.xml
|   |-- plant_nursery_security.xml
|   |-- plant_order_security.xml
|-- static/
|   |-- img/
|   |   |-- my_little_kitten.png
|   |   |-- troll.jpg
|   |-- lib/
|   |   |-- external_lib/
|   |-- src/
|   |   |-- js/
|   |   |   |-- widget_a.js
|   |   |   |-- widget_b.js
|   |   |-- scss/
|   |   |   |-- widget_a.scss
|   |   |   |-- widget_b.scss
|   |   |-- xml/
|   |   |   |-- widget_a.xml
|   |   |   |-- widget_a.xml
|-- views/
|   |-- plant_nursery_menus.xml
|   |-- plant_nursery_views.xml
|   |-- plant_nursery_templates.xml
|   |-- plant_order_views.xml
|   |-- plant_order_templates.xml
|   |-- res_partner_views.xml
|-- wizard/
|   |-- make_plant_order.py
|   |-- make_plant_order_views.xml
```
