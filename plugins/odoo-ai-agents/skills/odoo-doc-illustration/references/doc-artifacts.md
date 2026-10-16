# Documentation artifacts - the three shared files (SSOT)

`odoo-doc-writer` writes these three files per module under
`<SHARE_DIR>/documentation/<slug>/<module>/`; the user guide, the landing and every later run read
them from that same path. A caller that already holds them passes their paths; the writer never
rebuilds a file it is given.

## `feature-catalog.jsonl` - one JSON object per user-visible capability

A capability is a menu item with its action, a standalone action or wizard, or a model with its
own views but no menu (embedded in another model's form). Never one entry per field. Rank by menu
depth, then alphabetically; `feature_id` is `<module-slug>-<NN>` and never changes once assigned.

```json
{"feature_id": "sale-01", "name": "Sales Orders", "type": "view",
 "menu_path": "Sales > Orders > Orders", "entry_point": "sale.action_quotations_with_onboarding",
 "models": ["sale.order"], "key_fields": ["name", "partner_id", "amount_total", "state"],
 "roles": ["sales.group_sale_salesman"], "states": ["draft", "sent", "sale", "cancel"],
 "depends_on": [], "value": "Manage sales orders from quotation to confirmation and invoicing",
 "grounded": "osm"}
```

| Field | Value |
|---|---|
| `name` | the label the user sees (menu name or view string), never a technical name |
| `type` | `model`, `view`, `menu`, `action` or `component` |
| `menu_path` | the full breadcrumb from the root; empty for an invisible action |
| `entry_point` | the action xmlid, or `<model>:<view_type>` for an embedded view |
| `models` | the models involved, main model first |
| `key_fields` | the 3-6 most user-visible fields of the main model, technical names |
| `roles` | the group xmlids that reach it; empty = every internal user |
| `states` | the values of the main model's state field in declared order; empty when stateless |
| `depends_on` | `feature_id`s this one needs first |
| `value` | one line of user benefit (the landing's Key Features grid reads it) |
| `grounded` | `osm`, `hybrid`, `local-source` or `unknown` |

`feature-catalog.md` mirrors the JSONL as a table for a human reader, followed by the role table
and a grounding count.

## `role-map.json` - the business roles and the process

```json
{"module": "fleet_booking", "odoo_version": "<series>", "grounded": "hybrid",
 "roles": [
   {"role_id": "R0", "kind": "admin", "groups": ["base.group_system"],
    "ui_name": "Administration / Settings", "implies": [],
    "business_role": "System Administrator", "business_role_source": "inferred",
    "job": "installs the module, sets booking rules and gives each person their access right",
    "can": [{"kind": "setting", "label": "Booking Approval", "feature_id": "booking-03"}]},
   {"role_id": "R1", "kind": "user", "groups": ["fleet_booking.group_booking_user"],
    "ui_name": "Fleet Booking / User", "implies": [],
    "business_role": "Employee", "business_role_source": "inferred",
    "job": "requests a vehicle for a business trip",
    "can": [{"kind": "menu", "label": "Bookings", "feature_id": "booking-01"},
            {"kind": "button", "label": "Submit", "feature_id": "booking-01"}]},
   {"role_id": "R2", "kind": "manager", "groups": ["fleet_booking.group_booking_manager"],
    "ui_name": "Fleet Booking / Manager", "implies": ["R1"],
    "business_role": "Fleet Supervisor", "business_role_source": "inferred",
    "job": "approves requests and assigns vehicles",
    "can": [{"kind": "button", "label": "Approve", "feature_id": "booking-01"}]}],
 "process": [
   {"stage": 1, "name": "Draft", "state": "draft", "role_id": "R1", "action": "Submit",
    "feature_id": "booking-01", "handoff_to": "R2"},
   {"stage": 2, "name": "Submitted", "state": "submitted", "role_id": "R2", "action": "Approve",
    "feature_id": "booking-01", "handoff_to": null}]}
```

- **Roles.** One role per group that gates something the module ships (a catalog `roles` entry, a
  `groups=` on a menu, button, field or setting, or a group the module defines). When no group
  gates its day-to-day surface, add one `kind: user` role for the group whose access rights reach
  its main models (else `base.group_user`). Exactly one role is `kind: admin`: the group that
  reaches configuration and settings. A role that implies another role of the map is `manager`,
  every other one `user`. `ui_name` is the privilege or category plus the group name as the
  access-rights screen shows them.
- **Implied roles.** `implies` lists the `role_id`s inherited through `implied_ids`; `can[]` lists
  only what the role adds on top.
- **Business role.** The job title of the person who holds the access, in English. From the group
  name when it already is a job title (`business_role_source: group-name`), else inferred from
  what the role can do (`inferred`) and never presented as a fact about the reader's company.
- **Process.** Follows the main model's state machine in declared order: per stage the state's
  label and value, the role whose button moves it on, that button, and the role it hands to.
  `[]` when the module has no state machine.

## `walkthrough.jsonl` - one happy-path scenario per role task

```json
{"scenario_id": "WS1", "goal": "<the user's goal in one line>", "role": "R1",
 "features": ["booking-01"], "precondition": "<records that must exist before step 1>",
 "steps": [{"action": "navigate", "target": "Fleet > Bookings", "note": "<caption>"},
           {"action": "fill", "target": "Vehicle", "value": "Company car 1", "note": "<caption>"},
           {"action": "click", "target": "Submit", "note": "<what pressing it does>"},
           {"action": "wait", "target": "Submitted", "note": "<the state badge appears>"}],
 "expected_outcome": "<what the user sees as the end state>", "grounded": "osm"}
```

- Order: the administrator's setup first, then each process stage's task by the role acting
  there, then each role's remaining tasks, roles in role-map order.
- Positive flows only: no negative input, no boundary probing, no permission-violation path.
- `action` is `navigate`, `fill`, `click`, `select` or `wait`; `target` is a menu path, field
  label, button label or state badge that exists in the OSM surface or on disk; `value` is a
  representative sample (omitted for `click` and `wait`).
- Each scenario is independent: a later stage's precondition names the record the earlier stage
  produces.

`walkthrough.md` renders the same scenarios for a human reader, one `### WS<n>` section each.
