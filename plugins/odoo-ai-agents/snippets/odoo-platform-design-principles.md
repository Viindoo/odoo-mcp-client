<!-- SSOT snippet. Referenced (not copy-pasted) by every agent that touches Odoo architecture,
     code, review, or debug (architect, coder, frontend-coder, code-reviewer, ui-reviewer,
     backend-debugger, ui-debugger). Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-platform-design-principles.md. -->

# Odoo Platform Design Principles (binding checklist)

Odoo is a platform with non-negotiable architectural conventions. Any design, code, review, or
diagnosis that touches business structure MUST respect the three principles below. Verify each
against OSM / live source - never assume (see `osm-first-contract.md`). When a change *cannot*
satisfy a principle, that is a deliberate deviation: state it and the justification in the worklog
(`worklog-contract.md`), do not let it pass silently.

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
  correct for one company must not leak across the boundary (SaaS multi-tenancy safety).

## 2. Generic and international before localization

Odoo's design law is: the generic, country-neutral behavior lives in a **shared** module; a
localization (`l10n_*`) module only **seeds** the rules/data/COA/taxes that differ per country.

- When a change touches a localized feature, FIRST evaluate reuse across countries: would >= 2
  countries share this behavior? If yes, the behavior belongs in the **generic/shared** module and
  each `l10n_*` only adds country-specific records (rules, data, sequences, tax/account templates).
- Do NOT build a parallel architecture inside one country's `l10n` module for something other
  countries will also need - that is duplication waiting to drift. Lift it to the shared layer and
  seed per country.
- Keep user-facing strings translatable (`_()`, no hardcoded language/currency/locale) so the
  generic layer serves every locale.

## 3. Standard app menu architecture (modules with `application=True`)

Any module marked `application=True` must present the standard Odoo app shape - verify the
manifest flag and the menu tree (`module_inspect` / source) before signing off:

- **One root (top-level) menu** for the app; feature menus organized logically beneath it.
- **A Reports menu is mandatory**: the app has its own reporting system - one top/overview report
  plus the child reports the business needs (depth scaled to complexity). Do not ship an app with
  no Reports menu.
- **A Configuration menu when the app has settings**: it contains `Settings` (the
  `res.config.settings` extension for this app) plus the admin-only configuration models of the
  app. Operational data does not live under Configuration; admin setup does.

A non-application module (a pure extension/bridge) is exempt from #3 but still bound by #1 and #2.
