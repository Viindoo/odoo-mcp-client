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
> (e.g. Odoo CE/EE upstream, OCA, or any other non-Viindoo distribution) - DO NOT apply these
> rules. For OCA/upstream: series-prefix version bump (e.g. `17.0.1.0.0`) still applies on upgrade.

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

**Else-branch (non-Viindoo):** OCA and upstream modules use the series-prefixed form
(e.g. `17.0.1.0.0`) when porting to a new series. Apply that form when the gating conditions
above are NOT met.

---

## Convention 2 - No migration script for no-data module rename

When a Viindoo module with `installable: False` (or a module that carries no user data) is
renamed, use `old_technical_name` in `__manifest__.py` only. Do NOT write a pre-migration SQL
script for this case.

See `${CLAUDE_PLUGIN_ROOT}/snippets/module-rename.md` for the full `old_technical_name` protocol
(key syntax, Viindoo tooling read, relationship to OpenUpgrade path). Do not restate it here.

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
