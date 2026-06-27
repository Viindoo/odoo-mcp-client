# XML View Conventions - CORE (all distributions)

CORE Odoo rules for XML view authoring, version-tagged. Applies to ALL distributions (CE, EE,
Viindoo). Cross-ref F0 `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §XML views`
for the full pivot table - do NOT restate rows here.

---

## Always-invisible field requires XML comment (v18+)

A view field with `invisible="1"` or `column_invisible="1"` (constant value, not a dynamic
expression) MUST carry an explanatory XML comment immediately after the field element:

```xml
<field name="legacy_field_id" invisible="1"/>
<!-- invisible: required by ParentClass._compute_something; unused in this view -->
```

- "Always invisible" = literal `"1"` or `"True"`. Conditional (`invisible="record.state == 'done'"`)
  does NOT require a comment.
- Enforced by `base.TestInvisibleField.test_uncommented_invisible_field` from v18; absent in v17
  and earlier.
- Pivot row: F0 `§XML views` row "Always-invisible field".

---

## Chatter element (v18+)

Use `<chatter/>` instead of the legacy `<div class="oe_chatter">` block:

```xml
<!-- v18+ preferred -->
<chatter/>

<!-- v17 and earlier (still works in v18 but deprecated) -->
<div class="oe_chatter">
    <field name="message_follower_ids"/>
    <field name="activity_ids"/>
    <field name="message_ids"/>
</div>
```

Pivot row: F0 `§XML views` row "Chatter element".

---

## List vs tree view tag

Cross-ref only - see F0 `§XML views` row "List view arch tag". `<list>` is canonical from v18;
`<tree>` was canonical through v17. Do NOT restate details here.
