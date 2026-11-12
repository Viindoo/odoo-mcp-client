# Backend design guide (web client)

## View type by job

| View | When the user's job is | Wrong use |
|---|---|---|
| list | scan and compare many records, edit a column fast | a kanban of hundreds of records |
| kanban | triage by stage or status, a card read at a glance | a card with a form's worth of fields |
| form | read or edit one record in depth | a dashboard crammed into a form |
| pivot, graph | aggregate, find a trend, slice by a dimension | a hand-built chart |
| calendar, gantt | time is the main axis | a date column in a list for scheduling |
| activity | "what do I owe on these records" | a custom to-do widget |

An action over many records opens on a list or a kanban; the form is for depth.

## Form slots, by rank

- **Statusbar**: the lifecycle and the forward action. Few buttons, ordered by likelihood; a rare
  action goes to the action menu.
- **Smart buttons**: navigation to related records, each with an icon and a live count. They are
  signposts, not actions.
- **Title**: the one or two fields that identify the record.
- **Group columns**: related fields in two balanced columns, grouped by meaning (billing and
  delivery, dates and amounts), in the order they are entered.
- **Notebook**: secondary and bulky detail (lines, notes, technical settings), pages ordered by
  frequency of use. A primary field is never moved behind a tab to make the top look clean.
- **Chatter**: where core puts it.

## Density, state and empty screens

- Keep core's row height, padding and font scale. Air comes from grouping and alignment, never
  from a margin of the module's own.
- State is shown with `decoration-*` and the badge widgets, by meaning (success, warning, danger,
  info, muted), and is also readable as text: colour is never the only signal.
- An empty screen says in one line what belongs here and offers the create action.
- Motion only where it explains a change of state; none on an action repeated all day.
- Icons come from the icon set the series bundles.

## What to avoid

- A form that dumps a table's fields ungrouped, with no rank.
- A kanban card too dense to scan.
- A core QWeb template replaced wholesale instead of extended by xpath.
- A custom widget where a standard one expresses the need.
- A left or right that is not the logical start or end: Odoo runs right-to-left too.
- A control, menu, search or permission shape of the module's own where core has one.
