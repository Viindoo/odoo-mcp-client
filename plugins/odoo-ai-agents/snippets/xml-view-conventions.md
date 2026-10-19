# XML View Conventions - CORE (all distributions)

CORE Odoo rules for XML view authoring, version-tagged. Applies to ALL distributions.
Cross-ref F0 `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md §XML views` for the full pivot
table - do NOT restate rows here. Series-specific view rules (always-invisible field comment,
inheriting QWeb templates) live in
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/<version>/xml.md`.

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
