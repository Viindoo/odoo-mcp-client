# New Module - `__manifest__.py` Authoring Guide

SSOT for authoring the manifest of a **greenfield (new) Odoo module**.
For bumping an EXISTING module across a new series, see
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/`.

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
(e.g. `name`, `summary`, `depends`, `data`). **Do NOT delete or uncomment the commented
placeholder keys** that `odoo-bin scaffold` emits in `__manifest__.py`. For example,
scaffold (v17) emits lines such as:

```python
# 'category': 'Uncategorized',
# 'depends': [],
# 'data': [],
# 'demo': [],
```

Keep those comment lines exactly as generated. Uncomment and fill a key only when the task
explicitly needs it. Deleting scaffold comment lines loses the placeholder intent and makes
future extension harder.

The same principle applies to the full skeleton (`models/`, `views/`, `__init__.py`, etc.):
fill only what is needed, preserve what is not yet needed.

---

## 3. Version field - data-driven, short form

The `version` key in `__manifest__.py` has two distinct forms. Choose by reading
observable data - never infer from training memory.

### Greenfield default (this snippet)

Keep the **short form** that `odoo-bin scaffold` emits. The short form is 2-3 numeric
parts (e.g. `0.1`, `1.0.0`, `0.2.0`). It is NOT required to be exactly 3 parts - the
defining characteristic is that it is short and does NOT carry the Odoo series prefix.

**How to ground (execute in order):**

1. `odoo-bin scaffold` available - keep whatever version string the generator wrote;
   do not edit it.
2. Hand-creating without scaffold - run:
   `grep -r '"version"' <addons-dir>/*/__manifest__.py | head -5`
   Adopt the first sibling match.
3. No sibling found - default to `0.1` (scaffold default).

### Series-prefixed form (upgrade / OCA per-series only)

The form `<series>.x.y.z` (e.g. `17.0.1.0.0`, `16.0.2.3.0`) is reserved for **bumping
an EXISTING module across a new Odoo series** - used by the upgrade workflow and by OCA
per-series publishing. See `${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/` for when
and how to apply it.

**Only apply the series-prefixed form when ALL of the following hold:**

- The module already existed in a prior series AND
- The task explicitly upgrades or ports it to a new series AND
- Sibling manifests in the target addons directory already use the series-prefixed form.

---

## Decision table

| Situation | Form to use | Example |
|---|---|---|
| New module via `odoo-bin scaffold` | Scaffold default (short) | `0.1` |
| New module hand-created | Match sibling manifest (short) | `1.0.0` |
| Existing module - upgrade to new series | Series-prefixed | `17.0.1.0.0` |
| Existing module - patch/feature in same series | Keep current value | unchanged |

---

## Anti-patterns (never do)

- Do NOT rewrite a greenfield `0.1` to `17.0.1.0.0` - that misapplies the upgrade convention.
- Do NOT assume the series-prefixed form is "more correct" - it is context-specific.
- Do NOT derive the version from the Odoo series alone; always read a sibling or the scaffold output.
- Do NOT delete the commented placeholder keys that `odoo-bin scaffold` emits (`# 'category':`,
  `# 'depends':`, `# 'data':`, `# 'demo':`, etc.) - keep them until explicitly needed.
- Do NOT uncomment + fill a placeholder key unless the task requires it.
