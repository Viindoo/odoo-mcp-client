# Module Rename Conventions

> **DISTRIBUTION-SPECIFIC - GATING REQUIRED**
>
> The rules below are Viindoo-distribution-specific. Apply them ONLY when BOTH conditions hold:
>
> 1. OSM (`odoo-semantic`) is reachable (probe with `list_available_profiles` or `set_active_version`).
> 2. The active profile resolves to a Viindoo Standard or Viindoo Internal distribution -
>    semantically, profiles of the form `standard_viindoo_<series>` or
>    `viindoo_internal_<series>`. Determine the active profile via `.odoo-ai/context.md`
>    (field `viindoo_profile`), or via OSM `profile_inspect` / `list_available_profiles` /
>    the currently active profile.
>
> If OSM is unavailable, OR the active profile is not a Viindoo Standard/Internal distribution
> (e.g. Odoo CE/EE upstream, OCA, or any other non-Viindoo distribution) - DO NOT apply these
> rules. They do not belong to Odoo upstream or OCA conventions.

---

## Rule 1 - `old_technical_name` in `__manifest__.py`

When an existing module is renamed (its technical name - i.e. the directory / module identifier -
changes), add the following key to `__manifest__.py` of the module AFTER the rename:

```python
'old_technical_name': '<previous technical name>',
```

**Key facts:**

- This key is a **Viindoo metadata key only**. The Odoo core module loader ignores it after
  merging the manifest (it is not in `_DEFAULT_MANIFEST`). It is NOT an OCA convention.
- Viindoo internal tooling reads `old_technical_name` to map the old technical name to the new
  one (e.g. for upgrade scaffolding, dependency resolution, and registry cross-referencing).
- This key is **additive** - it does NOT replace the standard rename mechanism. The standard
  Odoo/OCA rename path (OpenUpgrade `apriori.renamed_modules` +
  `openupgrade.update_module_names`) handles the DB-level rename on upgrade and is still
  required independently of this key.

**Example:**

Module `viin_sale_extra` is renamed to `viin_sale_extended`:

```python
# __manifest__.py of the renamed module (now viin_sale_extended/)
{
    'name': 'Viindoo Sale Extended',
    'old_technical_name': 'viin_sale_extra',
    ...
}
```

---

## Future rules

Additional module-rename conventions (e.g. data-file migration notes, ir.module.module record
handling, inter-module alias wiring) will be appended to this file as new numbered rules.
