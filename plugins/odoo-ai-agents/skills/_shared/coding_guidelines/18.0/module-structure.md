> Source: official Odoo 18.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/18.0/content/contributing/development/coding_guidelines.rst

# Module structure

> Warning: For modules developed by the community, it is strongly recommended to name your module
> with a prefix like your company name.

## Directories

A module is organized in important directories. Those contain the business logic; having a look at
them should make you understand the purpose of the module.

- *data/* : demo and data xml
- *models/* : models definition
- *controllers/* : contains controllers (HTTP routes)
- *views/* : contains the views and templates
- *static/* : contains the web assets, separated into *css/, js/, img/, lib/, ...*

Other optional directories compose the module.

- *wizard/* : regroups the transient models (`models.TransientModel`) and their views
- *report/* : contains the printable reports and models based on SQL views. Python objects and XML
  views are included in this directory
- *tests/* : contains the Python tests

## File naming

File naming is important to quickly find information through all odoo addons. This section explains
how to name files in a standard odoo module. As an example we use a
[plant nursery](https://github.com/tivisse/odoodays-2018/tree/master/plant_nursery) application.
It holds two main models *plant.nursery* and *plant.order*.

Concerning *models*, split the business logic by sets of models belonging to a same main model.
Each set lies in a given file named based on its main model. If there is only one model, its name
is the same as the module name. Each inherited model should be in its own file to help
understanding of impacted models.

```text
addons/plant_nursery/
|-- models/
|   |-- plant_nursery.py (first main model)
|   |-- plant_order.py (another main model)
|   |-- res_partner.py (inherited Odoo model)
```

Concerning *security*, three main files should be used:

- First one is the definition of access rights done in a `ir.model.access.csv` file.
- User groups are defined in `<module>_groups.xml`.
- Record rules are defined in `<model>_security.xml`.

```text
addons/plant_nursery/
|-- security/
|   |-- ir.model.access.csv
|   |-- plant_nursery_groups.xml
|   |-- plant_nursery_security.xml
|   |-- plant_order_security.xml
```

Concerning *views*, backend views should be split like models and suffixed by `_views.xml`.
Backend views are list, form, kanban, activity, graph, pivot, .. views. To ease split by model in
views main menus not linked to specific actions may be extracted into an optional
`<module>_menus.xml` file. Templates (QWeb pages used notably for portal / website display) are put
in separate files named `<model>_templates.xml`.

```text
addons/plant_nursery/
|-- views/
|   | -- plant_nursery_menus.xml (optional definition of main menus)
|   | -- plant_nursery_views.xml (backend views)
|   | -- plant_nursery_templates.xml (portal templates)
|   | -- plant_order_views.xml
|   | -- plant_order_templates.xml
|   | -- res_partner_views.xml
```

Concerning *data*, split them by purpose (demo or data) and main model. Filenames will be the
main_model name suffixed by `_demo.xml` or `_data.xml`. For instance for an application having demo
and data for its main model as well as subtypes, activities and mail templates all related to mail
module:

```text
addons/plant_nursery/
|-- data/
|   |-- plant_nursery_data.xml
|   |-- plant_nursery_demo.xml
|   |-- mail_data.xml
```

Concerning *controllers*, generally all controllers belong to a single controller contained in a
file named `<module_name>.py`. An old convention in Odoo is to name this file `main.py` but it is
considered as outdated. If you need to inherit an existing controller from another module do it in
`<inherited_module_name>.py`. For example adding portal controller in an application is done in
`portal.py`.

```text
addons/plant_nursery/
|-- controllers/
|   |-- plant_nursery.py
|   |-- portal.py (inheriting portal/controllers/portal.py)
|   |-- main.py (deprecated, replaced by plant_nursery.py)
```

Concerning *static files*, Javascript files follow globally the same logic as python models. Each
component should be in its own file with a meaningful name. For instance, the activity widgets are
located in `activity.js` of mail module. Subdirectories can also be created to structure the
'package' (see web module for more details). The same logic should be applied for the templates of
JS widgets (static XML files) and for their styles (scss files). Don't link data (image, libraries)
outside Odoo: do not use an URL to an image but copy it in the codebase instead.

Concerning *wizards*, naming convention is the same of for python models: `<transient>.py` and
`<transient>_views.xml`. Both are put in the wizard directory. This naming comes from old odoo
applications using the wizard keyword for transient models.

```text
addons/plant_nursery/
|-- wizard/
|   |-- make_plant_order.py
|   |-- make_plant_order_views.xml
```

Concerning *statistics reports* done with python / SQL views and classic views naming is the
following :

```text
addons/plant_nursery/
|-- report/
|   |-- plant_order_report.py
|   |-- plant_order_report_views.xml
```

Concerning *printable reports* which contain mainly data preparation and Qweb templates naming is
the following :

```text
addons/plant_nursery/
|-- report/
|   |-- plant_order_reports.xml (report actions, paperformat, ...)
|   |-- plant_order_templates.xml (xml report templates)
```

The complete tree of our Odoo module therefore looks like

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
|   |-- plant_order_reports.xml (report actions, paperformat, ...)
|   |-- plant_order_templates.xml (xml report templates)
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
|   |--make_plant_order.py
|   |--make_plant_order_views.xml
```

> Note: File names should only contain `[a-z0-9_]` (lowercase alphanumerics and `_`)

> Warning: Use correct file permissions : folder 755 and file 644.
