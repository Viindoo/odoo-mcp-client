# New Module - `__manifest__.py` Authoring Guide

The manifest of a **new Odoo module**.

---

## 1. Scaffold first (mandatory)

When creating a new module, ALWAYS generate the skeleton with:

```bash
odoo-bin scaffold <new_module_name> <addons-dir>
```

Hand-create files only when `odoo-bin` is genuinely unavailable (note it in the output
checklist). Extending an EXISTING module needs no scaffold.

---

## 2. Preserve scaffold output - only fill what is needed

After scaffolding, fill in or change only the keys that the task actually requires
(e.g. `name`, `summary`, `depends`, `data`) and `version` (§ 3). **Do NOT delete or uncomment the commented
placeholder keys** that `odoo-bin scaffold` emits in `__manifest__.py`. For example,
scaffold emits lines such as:

```python
# 'category': 'Uncategorized',
# 'depends': [],
# 'data': [],
# 'demo': [],
```

Keep those comment lines exactly as generated. Uncomment and fill a key only when the task
explicitly needs it.

The same principle applies to the full skeleton (`models/`, `views/`, `__init__.py`, etc.):
fill only what is needed, preserve what is not yet needed.

---

A key that is present with its default value (an empty `data` or `demo` list, `application:
False`, an empty `summary`) fails the manifest lint of a series that has one, for every addon on
the addons path: after scaffolding, delete such a live key. A commented placeholder line is not a
key and stays.

## 3. Version field - data-driven, short form

The `version` key in `__manifest__.py` uses the **short form** everywhere this snippet's scope
reaches. Choose by reading observable data - never infer from training memory.

### A new module

A new module's `version` is `0.1.0`: three numeric parts, no series prefix. `odoo-bin scaffold`
writes a two-part value; replace it with `0.1.0`.

A module that already has a two-part value keeps it until it needs a bump; the bump of
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-platform-design-principles.md` § 5 then gives it three
parts (`0.2` -> `0.2.1`). A change that needs no bump leaves the value as it is.

### Existing module across a new series (out of this file's scope)

Bumping an EXISTING module across a new Odoo series is handled by
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/`, not this file. Its rule - CORE, applying to
every distribution: keep the short form unchanged; a value that currently carries the series
prefix (`<series>.x.y.z`, e.g. `17.0.1.0.0`) is CONVERTED to the short form, never bumped. Full
rule: `${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md` Convention 1.

---

## Decision table

| Situation | Form to use | Example |
|---|---|---|
| New module, scaffolded or hand-created | Three parts, no series prefix | `0.1.0` |
| Existing module - code upgrade to a new series | Short form - keep unchanged, or CONVERTED from long form | `0.1` (unchanged); `17.0.1.0.0` -> `1.0.0` (converted) - see `upg-conventions.md` Convention 1 |
| Existing module - patch/feature in same series | Keep the current value; the plan's `migration` node gives every module changed outside its tests its one bump per PR (`odoo-platform-design-principles.md` § 5) | unchanged, or the smallest step of § 5 (`1.0.3` -> `1.0.4`, `0.1` -> `0.1.1`) |
| Forward-port, source bumped an existing target module's `version` | C1: `max(M + 1, S)` when installable on both series; the source version when dormant at the target | see `[[fp-merge-absorption]]` (C1) |

---

## Anti-patterns (never do)

- Do NOT rewrite a new module's `0.1.0` to a series-prefixed form (e.g. `17.0.1.0.0`) - a code-level
  upgrade keeps the short form, or converts an existing long-form value to it; it never adds a
  series prefix (see `upg-conventions.md` Convention 1).
- Do NOT derive the version from the Odoo series.
- Do NOT delete the commented placeholder keys that `odoo-bin scaffold` emits (`# 'category':`,
  `# 'depends':`, `# 'data':`, `# 'demo':`, etc.) - keep them until explicitly needed.
- Do NOT uncomment + fill a placeholder key unless the task requires it.
