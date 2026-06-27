# Viindoo Upgrade Conventions

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
> (e.g. Odoo CE/EE upstream or any other non-Viindoo distribution) - DO NOT apply these
> rules.

> Conv-3 and Conv-4 are CORE Odoo rules (not Viindoo-specific); they appear here for upgrade context only and are reachable for ALL profiles via the version INDEX By-task table.

---

## Convention 1 - No version bump on code-level upgrade

When upgrading a Viindoo module to a new Odoo series with ONLY code-level changes (no data
migration, no behavior contract change visible to end users), do **not** bump `version` in
`__manifest__.py` and do **not** add the series prefix.

- Keep the existing short form `x.y.z` (e.g. `0.1`, `1.2.0`) unchanged.
- This is a Viindoo-specific convention. The SSOT for the version form is
  `${CLAUDE_PLUGIN_ROOT}/snippets/new-module-manifest.md §3`. Do not restate the form here.
- Version-specific guidance: see `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md`
  section "Viindoo-distribution conventions".

> **Forward-port note:** In forward-port the no-bump rule is STRONGER - on a `__manifest__.py`
> conflict keep the TARGET's value; never merge-pick or invent. See `[[fp-merge-absorption]]`.
> Convention 1 applies to upgrade commits only.

---

## Convention 2 - Module rename via `old_technical_name` (no migration script)

When a Viindoo module with `installable: False` (or no user data) is renamed, add to the renamed
module's `__manifest__.py`:

    'old_technical_name': '<previous technical name>',

- Viindoo metadata key only - the core loader ignores it (not in `_DEFAULT_MANIFEST`). NOT a core Odoo
  convention.
- Viindoo tooling reads it to map old->new technical name (upgrade scaffolding, dep resolution, registry).
- Additive - the standard Odoo rename path (OpenUpgrade `apriori.renamed_modules` +
  `openupgrade.update_module_names`) still handles the DB-level rename independently.
- Do NOT write a pre-migration SQL script for a no-data rename.

> **C2 note:** This convention is about not writing NEW migration scripts. It does NOT exempt an
> existing forwarded `migrations/` dir from the C2 retarget - see `[[fp-merge-absorption]]`.
<!-- Future rules (data-file migration notes, ir.module.module record handling, alias wiring) append here. -->

---

## Convention 3 - Always-invisible field requires XML comment (from v18)

CORE rule - applies to all distributions. Full rule, definition, code example, and test name:
`${CLAUDE_PLUGIN_ROOT}/snippets/xml-view-conventions.md`

Upgrade context: a missing comment causes `base.TestInvisibleField` to fail in the full CI suite
triggered when a module flips `installable: False -> True` (P5 gate).

---

## Convention 4 - `hr.employee` fields absent from `hr.employee.public` need `groups=` (from v16)

CORE rule - applies to all distributions. Full rule and code example:
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` section "Core test-enforced authoring rules".

Upgrade context: omitting `groups='hr.group_hr_user'` causes
`hr.TestSelfAccessProfile.test_employee_fields_groups` to fail in the full CI suite triggered on
installable-flip (P5 demo=on gate).
