# Viindoo Upgrade Conventions

> **CONVENTIONS 1-2 ARE VIINDOO-DISTRIBUTION-SPECIFIC - GATING REQUIRED**
>
> Conventions 1 and 2 below are Viindoo-distribution-specific. Apply Conventions 1-2 ONLY when
> BOTH conditions hold:
>
> 1. OSM (`odoo-semantic`) is reachable (probe with `list_available_profiles` or `set_active_version`).
> 2. The active profile resolves to a Viindoo Standard or Viindoo Internal distribution -
>    semantically, profiles of the form `standard_viindoo_<series>` or
>    `viindoo_internal_<series>`. Determine the active profile via `<SHARE_DIR>/context.md`
>    (field `viindoo_profile`; resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per
>    `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute
>    path - never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit), or via OSM
>    `profile_inspect` / `list_available_profiles` /
>    the currently active profile.
>
> If OSM is unavailable, OR the active profile is not a Viindoo Standard/Internal
> distribution (e.g. Odoo CE/EE upstream or any other non-Viindoo distribution) -
> DO NOT apply Conventions 1-2.

> Conv-0, Conv-3 and Conv-4 are CORE Odoo rules (not Viindoo-specific); the gate above does NOT
> apply to them - apply all three on EVERY profile/distribution, OSM-reachable or not. Conv-3's
> and Conv-4's rule text lives in dedicated CORE files reachable via
> `${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/INDEX.md` § Snippets catalog
> (`xml-view-conventions.md`, `odoo-version-pivots.md` - both tagged CORE, all distributions).
> Conv-0 has no such standalone file - it is reached directly, at the point of obedience, not
> through this file's own gate: every `odoo-modules-upgrade` P4 adapt dispatch brief
> (`upg-phase-detail.md` § odoo-coding dispatch brief) cites this file by path unconditionally
> (no profile check on the citation itself), which fires `odoo-backend-coder.md` /
> `odoo-frontend-coder.md`'s "Modules-upgrade adapt" disposition (also unconditional on profile)
> and sends the coder to § Convention 0 below - on ANY profile, Viindoo or not.

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

---

## Convention 0 - A major-series module upgrade is a CODE upgrade

CORE rule - applies to all distributions. Governs every P4 adapt of `odoo-modules-upgrade`.

**(a) No old-series compatibility, no migration script, no version bump.** Treat the module at the
target series as NEW feature development. Do NOT preserve backward compatibility with the previous
Odoo series or with the module's own prior shape, and do NOT write a migration script (Convention 1
owns the no-bump rule; `[[fp-merge-absorption]]` owns the forward-port variant). A genuine
data-at-risk case routes OUT to `odoo-data-migration` and is never handled inline - see (d).

**(b) Write the target series' newest mechanism, not a shim.** The P2 NEW-FEATURE SWEEP already ran
`suggest_pattern` / `find_examples` for every KEEP / REWRITE feature and recorded any replacement in
`reuse_candidates[]` - see
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-phase-detail.md` § P2 step 3b. Do
NOT re-run that sweep here. The only P4-time addition: a feature WITH a `reuse_candidates[]` entry ->
implement the target-core mechanism it names and delete the custom implementation; a feature WITHOUT
one -> nothing to do. Never wrap the new mechanism in a compatibility shim over the old one.

**(c) Bias to the newest external API, decidably.** Trigger the vendor-currency pass when EITHER holds:
1. the module's `__manifest__.py` declares `external_dependencies` with at least one non-empty list
   under `python` or `bin`; OR
2. the module imports a top-level package that is neither `odoo`, nor the module's own name, nor a
   relative import, nor in the running interpreter's stdlib set
   (`python3 -c 'import sys; print("\n".join(sorted(sys.stdlib_module_names)))'`).

Cannot decide whether a name is stdlib -> treat as TRIGGERED. When triggered: for each distinct
third-party package, ONE bounded `WebFetch` or `WebSearch` per
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md` § Tier 2 (official upstream) - no follow-up
chain - capped at THREE packages per module, ONE network call each.

**Then ACT on the finding, do not merely record it.** When the pass shows the module uses an API the
upstream package has superseded: write the NEWEST upstream API in the adapted code and record
`vendor_api_checked: <pkg>@<found> -> adapted-to <newest>`. When the newest API would require a
behavior change beyond this upgrade's scope, keep the current call, record
`vendor_api_checked: <pkg>@<found> (newer <newest> deferred - <one-line reason>)`, and surface that
line at the P6 gate. Never silently keep a superseded call. Other outcomes, one of exactly these:
`vendor_api_checked: <pkg>@<version-found>` (already current);
`vendor_api_checked: over-cap (<n> packages)`; `vendor_api_checked: not-triggered`;
`vendor_api_checked: unreachable`. This pass is ADVISORY and never blocks the adapt.

**(d) Data at risk routes out.** A module the P2 comparator flagged `data_at_risk: true` that receives
REWRITE(model) or DELETE is already an escalation (`odoo-modules-upgrade/SKILL.md` § Hard rules). Do
not write a migration script to "handle" it here; report and route to `odoo-data-migration`.
