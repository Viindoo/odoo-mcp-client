<!-- SSOT snippet. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-platform-design-principles.md. -->

# Odoo Platform Design Principles (binding checklist)

Any design, code, review or diagnosis touching business structure MUST respect the principles
below. Verify each against OSM / live source - never assume (`osm-first-contract.md`). A change
that cannot satisfy a principle is a deliberate deviation: state it and the justification in the
worklog (`worklog-contract.md`), never let it pass silently.

## 1. Multi-company (and multi-branch from v17+)

- If the model carries company-scoped data (it inherits `res.company` semantics, or peer core
  models declare `company_id`), the design MUST scope it: a `company_id` field, `ir.rule`
  company isolation, and company-aware defaults/domains. Verify with
  `model_inspect(model=<model>, method='summary', odoo_version='<concrete>')` whether `company_id`
  exists on the model or its peers.
- **From Odoo 17+**, where the data is meaningfully branch-level (a sub-unit of a company -
  `res.branch`), also evaluate branch scoping (`branch_id` + branch-aware rules). Check the
  resolved version first; pre-17 has no `res.branch`. Do not bolt on a custom branch concept when
  the standard `res.branch` exists for the target version.
- Stored computes, defaults, and domains must respect the active company/branch context - a value
  correct for one company must not leak across the boundary.

## 2. Generic and international before localization

The generic, country-neutral behavior lives in a **shared** module; a localization (`l10n_*`)
module only **seeds** the rules/data/COA/taxes that differ per country.

- When a change touches a localized feature, FIRST evaluate reuse across countries: would >= 2
  countries share this behavior? If yes, the behavior belongs in the **generic/shared** module and
  each `l10n_*` only adds country-specific records (rules, data, sequences, tax/account templates).
  Never build a parallel architecture inside one country's `l10n_*` module for something other
  countries will also need.
- Keep user-facing strings translatable (`_()`, no hardcoded language/currency/locale) so the
  generic layer serves every locale.

## 3. Standard app menu architecture (modules with `application=True`)

Any module marked `application=True` must present the standard Odoo app shape - verify the
manifest flag and the menu tree (`module_inspect` / source) before signing off:

- **One root (top-level) menu** for the app; feature menus organized logically beneath it.
- **A Reports menu is mandatory**: one top/overview report plus the child reports the business
  needs (depth scaled to complexity).
- **A Configuration menu when the app has settings**: `Settings` (the `res.config.settings`
  extension for this app) plus the admin-only configuration models of the app. Operational data
  does not live under Configuration; admin setup does.

A non-application module (a pure extension/bridge) is exempt from #3 but still bound by #1 and #2.

## 4. Extension, access and data hygiene (every module)

- **Extend, never replace.** A change to an existing view is an inherited view (`inherit_id` +
  xpath). A whole-view replacement happens only when the design names it and says why.
- **Every new model ships its access row** in `ir.model.access.csv`. A model with `company_id`
  ships a company record rule: a user sees only records of the companies they are allowed to see
  (the core convention; a module never loosens it for its own records).
- **`@api.depends` lists every field the compute body reads** - checked against the body, not
  the intent. A stored compute whose inputs change meaning over time (a rate, a price, a tax
  position) is designed as a snapshot taken at the business event, not a live recompute that
  silently rewrites history.
- **`sudo()` carries its reason** in a comment on the same statement, and the narrowest scope
  that works. `sudo()` without a reason is a review finding.
- **No hardcoded locale, currency, company, timezone, date format or language** in a shared
  module: read them from the record, the company, the user or the context.
- **A defect in Odoo core is reported, not patched in a downstream module.** The fix goes where
  the defect lives.
- **Reversibility over blocking.** The default for a user action is confirm-and-allow-correction,
  not a constraint. A blocking guard (a constraint, a refused transition, a cascade cancel) is
  added only on evidence - an accounting or legal rule, a data corruption that happened, or a
  block core Odoo itself enforces - never on "it could happen". Every guard that ships comes with
  a cheap way out for the same role (back to draft, cancel this one record, correct and redo) -
  named in the SRS when it is designed, or by the coder in its worklog and return when the need
  appears while coding; a guard whose way out cannot be named is not shipped, the permissive
  path is. A cascade (cancel the whole chain to fix one link) is used only where integrity truly
  requires it, through the mechanism core provides (reversal, credit note, return), never a
  custom one. A module never narrows a lifecycle core allows (draft -> cancel -> draft) without a
  reason written in the SRS.

## 5. Change hygiene: versions, migrations, retirement

Within a series; a cross-series code upgrade follows
`${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md` § Convention 0.

- **Migrations are decided last (SSOT).** Write no migration script and no version bump inside
  the code, test, review, acceptance, debug or i18n loops. After the loops end and the modules
  are proven on a FRESH install, a module that was `installable` True before the PR (an absent
  key counts as True) and whose change alters data existing databases hold gets at most ONE
  `__manifest__.py` version bump per PR, and its migration directory holds at most ONE file per
  stage (`pre-migrate.py`, `post-migrate.py`, `end-migrate.py`), never files named after
  business topics. A module `installable: False` before the PR or within it takes neither.
- **Retire, do not delete.** A module, model or field that customer databases hold data in stays
  in place with a TODO naming the next major that removes it. Only a pre-migration script removes
  data that carries an XML ID.
- **Data files declare only part of a module's XML IDs.** Odoo mints more for `_inherits`
  records and for the records a cron or a user creates; a migration never lists XML IDs from the
  data files - it reads them from the database.
- **Removing a `noupdate` data file deletes its records** at `_process_end` and cascades into
  customer records through `ondelete='cascade'`. A record customers reference is pinned by
  dropping its XML ID, never by removing the file.
