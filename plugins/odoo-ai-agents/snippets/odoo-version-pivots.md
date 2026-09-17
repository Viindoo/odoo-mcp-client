<!-- SSOT snippet. Ground-truth version-pivot table v8-v19, verified against on-disk codebase (D9).
     Every file that states a version-specific API fact MUST cross-ref here, NOT restate.
     Edit this file to correct a pivot; do not patch consumers.
     Consumers are DERIVED, never listed here - re-derive with `grep -rl "odoo-version-pivots.md" plugins/odoo-ai-agents/`. -->

# Odoo Version Pivots - v8-v19 SSOT

Compact canonical table. Row format: **change** | **new API / mechanism** | **from vMIN** | **old: removed or alias**.
"alias" = old name still works but emits DeprecationWarning. "REMOVED vN" = raises AttributeError / ImportError / ValidationError at that version.

> **OSM caveat (active until server bug fix):** OSM currently does NOT resolve underscore-renamed
> methods (`_has_cycle`, `_filtered_access`) or `res.users.has_group`/`has_groups` (server bugs
> #2/#3). This table is the authoritative fallback for those symbols. For all others, verify via
> OSM `api_version_diff(symbol, from_version, to_version)` at TARGET - do not read this table as
> a substitute for a live OSM check when OSM is available and the symbol is indexed.

---

## Python ORM - ACL / access

| Change | New API | From | Old |
|---|---|---|---|
| Unified access check | `check_access(operation)` / `has_access(operation)` | v18 | `check_access_rights(operation)` + `check_access_rule(operation)` = alias (DeprecationWarning v18+) |
| Filtered access | `_filtered_access(mode)` | v18 | `_filter_access_rules()` / `_filter_access_rules_python()` = alias |
| User group test - single xmlid | `user.has_group('mod.xmlid')` | v8 | -- (present since v8) |
| User group test - plural / env shorthand | `user.has_groups('a.x,b.y')` | v18 | `user_has_groups(xmlid)` **REMOVED v18** |

## Python ORM - model API

| Change | New API | From | Old |
|---|---|---|---|
| Cycle check | `_has_cycle(field)` | v18 | `_check_recursion(field)` = alias |
| Display name | `_compute_display_name` override | v12 | `name_get()` deprecated v17, **REMOVED v18** |
| Record-style API | `@api.model`, `@api.model_create_multi`, plain multi-record methods | v13 | `@api.one`, `@api.multi`, `_columns` dict, `fields.function`, `osv.osv` **REMOVED v13** |

## Python ORM - cache / flush / metadata

| Change | New API | From | Old |
|---|---|---|---|
| Targeted flush | `Model.flush_model()` / `records.flush_recordset()` | v16 | `self.flush()` **REMOVED v17** |
| Targeted invalidate | `Model.invalidate_model()` / `records.invalidate_recordset()` | v16 | `self.invalidate_cache()` **REMOVED v17** |
| External id lookup | `record.get_external_id()` | v16 | `record.get_xml_id()` **REMOVED v17** |
| View loading | `env['ir.ui.view'].get_views(...)` | v16 | `fields_view_get()` deprecated v16, **REMOVED v17**; `fields_get_keys()` gone v17 |
| Registry cache clear | `registry.clear_cache()` | v17 | `registry.clear_caches()` = alias |
| Field to SQL | `_field_to_sql(alias, fname, query)` | v17 | `_inherits_join_calc(...)` = alias |
| Order to SQL | `_order_to_sql(order, query, alias, reverse)` | v17 | `_generate_order_by(...)` = alias |

## XML views

| Change | New | From | Old |
|---|---|---|---|
| Inline Python modifiers | `readonly="record.state == 'done'"` | v17 | `attrs=`/`states=` → `ValidationError` **from v17** (not just a warning) |
| List view arch tag | `<list>` | v18 | `<tree>` still accepted but `<list>` is canonical; `<tree>` was canonical up to v17 |
| Always-invisible field | field + XML comment AFTER: `<!-- invisible: <reason> -->` | v18 | No comment → fails `base.TestInvisibleField` from v18+ |
| Chatter element | `<chatter/>` | v18 | `<div class="oe_chatter">` deprecated; `<chatter/>` preferred from v18 |

## Manifest

| Change | Detail | From | Notes |
|---|---|---|---|
| Asset bundles | `assets` key in manifest | v15 | Pre-v15: `qweb` key + bundle XML in views |
| Version string | Strict `adapt_version` regex enforcement | v17 | Pre-v17: lenient; malformed version strings are rejected at install from v17 |
| Manifest version - code upgrade | Keep short form `x.y.z`; series-prefixed value CONVERTED, never bumped | CORE | `upg-conventions.md` Convention 1 |
| Forward-port version conflict | Keep TARGET's value, never bump | CORE | `[[fp-merge-absorption]]` C1 |

> `adapt_version` above refers to the install-gate version-string validation (v17+ regex enforcement). The same function also series-prefixes the manifest for migration-runner comparison (its second role) - see C2 in `[[fp-merge-absorption]]`.

## CLI - demo flag

| Scenario | Flag / behavior | Version range |
|---|---|---|
| Disable demo data | `--without-demo` | v8-v19 (present in ALL versions) |
| `--without-demo` takes a REQUIRED value - bare `--without-demo` is a parse error (`option requires 1 argument`) | `--without-demo=all` | v8-v18 |
| `--without-demo` takes an OPTIONAL, BOOL-typed value - bare `--without-demo` is valid | `--without-demo` | v19+ |
| Demo ON is the default; no extra flag needed to get demo | *(default)* | v8-v18 |
| Enable demo data | `--with-demo` | **v19+ only** - this flag does NOT exist in v8-v18 |
| Demo default | **ON** when `-i`/`-u` given | v8-v18 |
| Demo default | **OFF** | v19+ |

> **The flag's ARITY moved - carrying one spelling across that boundary is a real defect.** In the
> earlier era it is an ordinary string option (optparse `action="store"`, `nargs=1`), so a value is
> mandatory and the documented `all` form is the one to use. In the later one it is re-declared onto
> `dest="with_demo"` with `nargs='?'`, `const=True` and a BOOL type inverted on read: a bare
> `--without-demo` is the intended spelling, and a module-list value no longer parses (it fails the
> bool check, logs `invalid boolean value: 'all'`, and only reaches "demo off" via that fallback).
> Rows above own the boundary; read at `odoo/tools/config.py` across the indexed span (2026-09-02).

> `--without-demo=False` is **INVALID** in all versions. Never use it. In the string era the value is
> only truthiness-tested at the consumption site (`if not tools.config['without_demo']`,
> `odoo/modules/loading.py`), so `"False"` is TRUE and DISABLES demo - the opposite of how it reads;
> in the bool era it parses, but the command line still reads as its own opposite. Say what you mean:
> omit the flag where demo is already on, or pass `--with-demo` where it is not. That same
> truthiness-only consumption also breaks the help text's per-module promise ("comma-separated, use
> \"all\" for all modules"): ANY non-empty value disables demo for EVERY module in the build.

### Demo data by build PURPOSE

Because the default flips at v19, the build's PURPOSE decides the flag there. Resolve the purpose
from the dispatch brief's own signals, never from the operation name alone.

| Build purpose - the signal that decides it | `demo` field (what the build REQUIRES, not what the DB ends up with) | v19+ flag | v8-v18 flag |
|---|---|---|---|
| Automation test run that gates code - ANY `--test-enable` build, at BOTH `GATE_ROLE: node-verify` and `GATE_ROLE: pre-pr-lint-gate` | `off` | none - already off | none - demo stays ON by default here, and that is correct; do NOT reach for a disable flag |
| Translation export / `.pot` / `.po` work | `on` | `--with-demo` | none - already on |
| Documentation capture (`CONTEXT: doc`), demo recording, UI review | `on` | `--with-demo` | none - already on |
| Acceptance live-UI sweep | `on` | `--with-demo` | none - already on |
| Demo-load verification - proving a module's own `demo/` data still loads. INSTALL ONLY: this build NEVER carries `--test-enable` | `on` | `--with-demo` | none - already on |
| Anything whose OUTPUT does not depend on demo records - a debug reproduction, an ensure-up, a language activation, a bare create, a no-code-change smoke run | `off` | none | none |

The last row is the ONLY way a demo-carrying build and a code-gating suite coexist: they are two
SEPARATE builds, never one build with both flags. Loading demo proves the `demo/` XML still parses
and installs; running the suite proves the code works - and the moment demo rows enter a DB the
suite asserts on, a correct test that counts records starts failing, which makes weakening the test
look like the fix.

`demo: off` states that the build does not REQUIRE demo; it is never an instruction to remove demo
that the series loads by default. Disabling it changes what the build reproduces, so every row above
asks for a flag only where one is needed to ADD demo.

> **A v19+ automation-test build carries NO demo data, and the test suite must not want any.** Demo
> records are absent there, so a test that reads one fails. Every durable test authored for a v19+
> target - Python `TransactionCase` / `HttpCase`, Python tour, JS tour - MUST create its own records
> in `setUpClass` / `setUp` and MUST NOT reference a demo record by xmlid or by name. This holds even
> when the test was authored while driving a demo-carrying acceptance instance: the file it leaves
> behind runs demo-less in the gate.

## Framework-validation test classes (named in `--test-tags` beside module tags)

**Only two classes are listed here, and the list stays that size on purpose.** A class earns a row
ONLY if all three hold: it is a FRAMEWORK class (lives in `base`/`hr`, not in the module under
test), it enforces a convention THIS plugin teaches, and a module-scoped `--test-tags /<module>` run
SKIPS it so nothing else would catch the violation. Odoo and Viindoo ship hundreds of thousands of
tests; this is not a mirror of them, and a class that fails any of the three does not belong.

| Convention it enforces | Class, per series | Tag spec to pass |
|---|---|---|
| Always-invisible view field needs an explanatory XML comment | `TestInvisibleField` (in `base`), v18+ only - absent below | `/base:TestInvisibleField` |
| Custom `hr.employee` field needs `groups="hr.group_hr_user"` | in `hr`: `TestSelfAccessProfile` v13-v18, RENAMED to `TestSelfAccessPreferences` at v19 | `/hr:TestSelfAccessProfile` or `/hr:TestSelfAccessPreferences` per series |

> **The `hr` class was RENAMED, not removed.** Its file and its `test_employee_fields_groups` method
> both still exist at v19 under the new class name, so the enforcement is live there - dropping the
> tag because the old name no longer resolves silently stops the check. (That method itself only
> exists from v18; below that the class is present but enforces the convention through other tests.)

> **The class separator in a tag spec is a COLON.** The grammar is `[-][tag][/module][:class][.method]`
> (`odoo/tests/tag_selector.py`, `filter_spec_re`), so `base.TestInvisibleField` does NOT name a
> class - it parses as tag `base` plus METHOD `TestInvisibleField`, matches no test method that
> exists, and selects NOTHING. Copy the tag-spec column; never re-derive it from a dotted name.

> **A tag that matches nothing is a SILENT no-op, not an error** - whether the spec is misspelled or
> the series ships a different name. The run exits 0 having tested nothing. So CONFIRM the class name
> against the target build's own `addons/<module>/tests/` before tagging it: this table has been
> wrong twice, once on a bound and once by reading "the old name is absent" as "the thing is gone".
> An UNTAGGED run needs none of this - it already includes every framework class - so prefer it
> wherever the cost of running the full closure is acceptable.

## CLI - server-wide modules (`--load` / `server_wide_modules`)

| Series | Core default | Viindoo set to union | Resulting `--load` on a Viindoo profile |
|---|---|---|---|
| v8-v10 | `web,web_kanban` | `to_base` | `web,web_kanban,to_base` |
| v11 | `web` | `to_base` | `web,to_base` |
| v12-v17 | `base,web` | `to_base` | `base,web,to_base` |
| v18 | `base,web` | `to_erponline_utility,viin_brand` | `base,web,to_erponline_utility,viin_brand` |
| v19+ | `base,rpc,web` | `to_erponline_utility,viin_brand` | `base,rpc,web,to_erponline_utility,viin_brand` |

> Core-default column read from `--load`'s `my_default=` in `odoo/tools/config.py` (`openerp/` in the
> earliest series) across every indexed checkout, 2026-09-17. The core default is NOT monotonic - it
> loses a module at v11 and gains one at v12 and again at v19 - so it is read per row, never
> interpolated between rows. The Viindoo column is a Viindoo DEPLOYMENT fact, not a source fact:
> `grounded: operator-report 2026-09-17`; module presence in a profile cannot confirm it, because
> every module named here also resolves on series where it is not server-wide.

> **`to_base` leaves the SERVER-WIDE set at v18.** It stays an ordinary installable module there;
> only its server-wide role ends. A v18+ `--load` that still lists it is wrong even though the
> module itself resolves.

> **`rpc` is a v19 core addon, absent at v18, and Odoo re-adds only `base` and `web` when a `--load`
> omits them.** A v19+ `--load` spelled `base,web,...` therefore drops `rpc` with no error and no log
> line. Spell the whole set for the series; never append to a remembered shorter one.

> `cli_help(command='server', flag='--load', odoo_version='<version>')` returns NO `Default:` line on v19 - silent, not stale.
> Take the core default from this table and flag `grounded: local-source`; do not read the silence as
> "no modules load by default".

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
- ACL requirement from v16+. Enforced by `hr.TestSelfAccessProfile.test_employee_fields_groups`
  (exact test name present from v18; sibling test `TestSelfAccessRights.testReadOtherEmployee`
  covers v16/v17). Those are METHOD bounds inside the class, narrower than the CLASS bound in
  § Framework-validation test classes - read that section for what to TAG, and this line only for
  which assertion actually fires. The class itself is gone at v19, so the convention stands on its
  own there with no test left to catch a violation.

---

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

---

## Viindoo-distribution conventions (profile-gated - see `upg-conventions.md`)

Apply ONLY under `upg-conventions.md`'s gating. NOT Odoo core or other distributions.

| Convention | Rule | Cross-ref |
|---|---|---|
| No-data module rename | `old_technical_name` key only - no migration script | `upg-conventions.md` Convention 2 |

### Backend lint-class gate - which modules exist per series

| Module | Source | Present at |
|---|---|---|
| `test_lint` | Odoo core (`odoo/addons/test_lint`) | v10+ ONLY - absent below that, where a `/test_lint` tag silently matches nothing |
| `test_pylint` | Viindoo `tvtmaaddons` | v16 ONLY - the gate does not exist below v16 |
| `test_viin_pylint` | Viindoo `tvtmaaddons` | v17+ ONLY - same gate as `test_pylint`, under the new name |

> `test_pylint` and `test_viin_pylint` are ONE gate under two names, split at v17 - never install or
> tag both in the same build. Selection procedure, and the false-green trap that makes this matter:
> `${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md`.
