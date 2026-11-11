# Odoo Version Pivots - v8-v19 SSOT

Compact canonical table. Row format: **change** | **new API / mechanism** | **from vMIN** | **old: removed or alias**.
"alias" = old name still works but emits DeprecationWarning. "REMOVED vN" = raises AttributeError / ImportError / ValidationError at that version.

> For a symbol the index resolves, its own answer at the target series outranks this table; the
> table is the fallback for the symbols it does not resolve.

---

## Python ORM - ACL / access

| Change | New API | From | Old |
|---|---|---|---|
| Unified access check | `check_access(operation)` / `has_access(operation)` | v18 | `check_access_rights(operation)` + `check_access_rule(operation)` = alias (DeprecationWarning v18+) |
| Record rules on new (onchange) records | call `records._origin.check_access(op)`; on new ids `check_access` / `has_access` check access rows only | v18-v19 (v20 checks the origin itself) | earlier series evaluate the rule on the new record |
| Filtered access | `_filtered_access(mode)` | v18 | `_filter_access_rules()` / `_filter_access_rules_python()` = alias |
| User group test - single xmlid | `user.has_group('mod.xmlid')` | v8 | -- (present since v8) |
| User group test - plural / env shorthand | `user.has_groups('a.x,b.y')` | v18 | `user_has_groups(xmlid)` **REMOVED v18** |

## Access groups

Which model a group hangs on, and how to declare it: `access-groups-conventions.md`.

| Change | New API | From | Old |
|---|---|---|---|
| Group placement | `res.groups.privilege_id` -> `res.groups.privilege` (which carries `category_id`) | v19 | `res.groups.category_id` **REMOVED v19** |
| Users of a group | `res.groups.user_ids` | v19 | `res.groups.users` **REMOVED v19** |
| Transitive implied groups | `res.groups.all_implied_ids` | v19 | `res.groups.trans_implied_ids` **REMOVED v19** |
| Group link of a user, view, menu or action | `group_ids` on `res.users`, `ir.ui.view`, `ir.ui.menu`, `ir.actions.act_window`, `ir.actions.server`, `ir.actions.report` | v19 | `groups_id` **REMOVED v19** |
| Category of independent rights | a `res.groups` with no `privilege_id` | v19 | `base.module_category_usability` **REMOVED v19** |

## Python ORM - model API

| Change | New API | From | Old |
|---|---|---|---|
| Cycle check | `_has_cycle(field)` | v18 | `_check_recursion(field)` = alias |
| `translate=True` on a stored field | the column is `jsonb`: every raw SQL that reads it as text breaks, so grep core and the repository for its raw readers before making a core column translatable | v16 | a text column, translations in `ir.translation` |
| Default taxes on plain journal-entry lines | not applied unless the context carries `account_default_taxes` | v19 | v16-v18 apply the account's default taxes on create |
| Display name | `_compute_display_name` override | v12 | `name_get()` deprecated v17, **REMOVED v18** |
| Record-style API | `@api.model`, `@api.model_create_multi`, plain multi-record methods | v13 | `@api.one`, `@api.multi`, `_columns` dict, `fields.function`, `osv.osv` **REMOVED v13** |
| Progress and commit inside a scheduled job | `ir.cron._notify_progress(done=, remaining=)`; `ir.cron._commit_progress(...)` | v18; v19 | a hand-written `cr.commit()` in the job's loop |

## Python ORM - cache / flush / metadata

| Change | New API | From | Old |
|---|---|---|---|
| Targeted flush | `Model.flush_model()` / `records.flush_recordset()` | v16 | `self.flush()` **REMOVED v17** |
| Targeted invalidate | `Model.invalidate_model()` / `records.invalidate_recordset()` | v16 | `self.invalidate_cache()` **REMOVED v17** |
| External id lookup | `record.get_external_id()` | v16 | `record.get_xml_id()` **REMOVED v17** |
| View loading | `Model.get_views(...)` / `Model.get_view(...)` (on the model itself) | v16 | `fields_view_get()` deprecated v16, **REMOVED v17**; `fields_get_keys()` gone v17 |
| Registry cache clear | `registry.clear_cache()` | v17 | `registry.clear_caches()` = alias |
| Field to SQL | `_field_to_sql(alias, fname, query)` | v17 | `_inherits_join_calc(...)` = alias |
| Order to SQL | `_order_to_sql(order, query, alias, reverse)` | v17 | `_generate_order_by(...)` = alias |

## XML views

| Change | New | From | Old |
|---|---|---|---|
| Inline Python modifiers | `readonly="record.state == 'done'"` | v17 | `attrs=`/`states=` → `ValidationError` **from v17** (not just a warning) |
| List view arch tag | `<list>` | v18 | `<tree>` still accepted but `<list>` is canonical; `<tree>` was canonical up to v17 |
| Always-invisible field | XML comment stating why, right after the opening tag | v18 | Rule + enforcing test: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/<series>/xml.md` § Always-invisible field carries a comment |
| Optional list column | `optional="hide"` / `optional="show"` on a list/tree `<field>` | v13 | Attribute not honoured before v13 - the column is always rendered |
| Chatter element | `<chatter/>` | v18 | `<div class="oe_chatter">` deprecated; `<chatter/>` preferred from v18 |

## Manifest

| Change | Detail | From | Notes |
|---|---|---|---|
| Asset bundles | `assets` key in manifest | v15 | Pre-v15: `qweb` key + bundle XML in views |
| Version string | Strict `adapt_version` regex enforcement | v17 | Pre-v17: lenient; malformed version strings are rejected at install from v17 |
| Manifest version - code upgrade | Keep short form `x.y.z`; series-prefixed value CONVERTED, never bumped | CORE | `upg-conventions.md` Convention 1 |
| Forward-port version | C1: `max(M + 1, S)` when installable on both series; the source version when dormant at the target | CORE | `[[fp-merge-absorption]]` C1 |

> `adapt_version` above is the install-gate version-string validation; the same function also series-prefixes the manifest for the migration runner (C2 in `[[fp-merge-absorption]]`).

## JavaScript / OWL / tests

| Change | New API | From | Old |
|---|---|---|---|
| OWL experimental | OWL 1.x alongside `web.Widget` | v14 | pre-v14: `web.Widget` only |
| OWL becomes primary for views | OWL 2.x - `Component`, `useState`, `useService`, `registry.category('fields')` | v16 | from v16 form/list/kanban/fields use `Component`; `AbstractField`/`web.field_registry` → `registry.category('fields')`; legacy `web.Widget` no longer used in core views (class lingers, declining v16→v18) |
| JS module header | `/** @odoo-module **/` | v15 | Mandatory v15-v17; auto-detected (can omit) **from v18**; `/** @odoo-module ignore **/` to opt out |
| Legacy AMD define | `odoo.define(name, fn)` | v9 | Shim-only (compatibility layer) from v17; do NOT write new `odoo.define` code |
| Test framework | `@odoo/hoot` | v18 | QUnit → Hoot from v18 (Hoot primary; QUnit still present at v18, last 100%-QUnit is v17) |

> Detailed per-version JS/OWL authoring rules, pitfall catalogue, and per-version applicability: `skills/_shared/odoo-frontend-fidelity.md`.

## Core test-enforced authoring rules

These are CORE Odoo rules enforced by a core test. Applies to ALL distributions.

### `hr.employee` field absent from `hr.employee.public` - requires `groups=` (v16+)

When adding a field to `hr.employee` that has NO counterpart on `hr.employee.public`, declare
`groups='hr.group_hr_user'` on the field definition:

```python
class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    sensitive_field = fields.Char(groups='hr.group_hr_user')
```

- Place `groups=` on the `hr.employee` override, NOT on a shared mixin - the mixin is used by
  both models and would wrongly gate the field on the public model too.
- ACL requirement from v16+. The core assertion is `test_employee_fields_groups`, in
  `hr.TestSelfAccessProfile` at v18 and in `hr.TestSelfAccessPreferences` from v19 (the class was
  renamed; the method keeps its name). v16 and v17 ship no core test for it, so the convention
  stands on its own there. The method is a bound inside the class, narrower than the CLASS bound
  in § Framework-validation test classes - that section says what to TAG; this line only says
  which assertion fires.

---

### Fields of the employee form's Payroll tab - manager groups (v19+)

From v19 the Payroll tab of the employee form is manager-only and a core test requires every field
placed in it to carry manager or payroll groups, while `groups=` on a field also blocks its ORM
reads for other users. Only real payroll fields go in that tab; an operational field an officer or
a compute reads goes in the Settings tab's application group and keeps its groups.

### Point-of-sale test cashier (v17+)

The PoS user group implies the internal-user group only from v20: on v17-v19 a cashier fixture
lists `base.group_user` and `point_of_sale.group_pos_user`.

## gettext placeholders (named required for multi-arg; E8505 lint failure v18+)

CORE Odoo rule enforced by a core test. Applies to ALL distributions.

In `_()` / `_lt()` translation calls that interpolate MORE THAN ONE variable, use NAMED
placeholders `%(name)s` with keyword arguments - never multiple positional `%s`. A single
positional `%s` is acceptable.

```python
# v14+ correct (named, lint-clean on v18+):
raise UserError(_("Answer to %(field)s is not valid, expected %(kind)s.", field=name, kind="int"))

# v18 E8505 FAILURE (two unnamed placeholders):
raise UserError(_("Answer to %s is not valid, expected %s.", name, "int"))
```

- **Capability:** the multi-arg `_()` signature exists from **v14+** (verified v14, v16, v17, v18).
  `GettextAlias.__call__` is `def __call__(self, source):` (single-arg, no `*args`/`**kwargs`) on
  v12 AND v13 - passing extra positional/keyword args on v13 or earlier raises `TypeError`, it does
  not lint-fail. Multi-var interpolation pre-v14 is done via `%` outside the call.
- **v14-v17:** named placeholders are supported and preferred, but a positional multi-`%s` call
  does NOT lint-fail.
- **v18+:** this is a hard `test_lint` FAILURE, not a style nit - `test_lint`'s gettext AST checker
  (`TestI18nChecks.test_gettext_placeholders`) rejects more than one unnamed placeholder: pylint
  symbol `gettext-placeholders`, message code **E8505**. Escaped `%%s` and a single `%s` are still
  OK. The check is NEW at v18 (absent at v16/v17).
- Treat an E8505 finding as a BUILD FAILURE - fix by switching to named placeholders, never by
  suppressing the lint check.

