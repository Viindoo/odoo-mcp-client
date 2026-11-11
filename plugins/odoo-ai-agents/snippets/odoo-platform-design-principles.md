# Odoo Platform Design Principles (binding checklist)

Every design, code change, review, test, acceptance and diagnosis that touches business structure
respects the principles below, each checked against OSM or the source, never assumed. A change
that cannot satisfy one is a deliberate deviation: state it with its justification in the worklog.

## 0. The user comes first

- **Easy for a user with low IT skills.** Every screen, message and step is judged as that user
  sees it: fewer things to see, faster to understand, fewer steps to act.
- **Post-audit over blocking.** A business action is allowed and recorded, not refused: a block
  cuts operational efficiency for everyone. A blocking guard (a constraint, a refused transition,
  a cascade cancel) exists only for data integrity, on evidence - an impossible state, a broken
  reference, a duplicate, an access breach, multi-company consistency, a corruption that
  happened, or a block core Odoo itself enforces - never on "it could happen". A legal or policy
  limit (a cap, a ratio, an approval window, a tax method) never blocks: the violation is recorded
  for audit - a stored, searchable flag, a non-blocking warning, tracking and a filter, under the
  rule in force at the business date - and its test asserts that the action succeeds and the flag
  is set.
- **Every block has a way out** for the same role (back to draft, cancel this one record, correct
  and redo), named in the SRS when it is designed or by the coder in its worklog and return when
  the need appears while coding; a guard whose way out cannot be named is not shipped, the
  permissive path is. A cascade (cancel the whole chain to fix one link) is used only where
  integrity truly requires it, through the mechanism core provides (reversal, credit note,
  return), never a custom one. A module never narrows a lifecycle core allows (draft -> cancel ->
  draft) without a reason written in the SRS.
- **Predictable, because consistent with core.** The user can guess what a button, a field or a
  state does before trying it, because it behaves as the same thing does everywhere else: one
  search bar behaviour, one group model per app, views of one design, the same messages, menus
  and lifecycle shapes. A module follows the core convention of its series for every surface it
  touches and invents no shape of its own.

## 1. Multi-company and branches

- A model that carries company-scoped data (peer core models declare `company_id`) is scoped by
  design: a `company_id` field, an `ir.rule` for company isolation, and company-aware defaults
  and domains. Confirm at the target series whether `company_id` exists on the model or its peers.
- A branch is a child company - `res.company` with a parent, on the series whose `res.company`
  has that hierarchy. There is no separate branch model, and none is invented. Where a record of
  a parent company must serve its branches (an account, a tax, a shared setting), the rule and
  the domain follow the company hierarchy with the helpers core's own company-dependent models
  use at that series.
- Stored computes, defaults and domains respect the active company context - a value correct for
  one company must not leak across the boundary.

## 2. Generic and international before localization

The generic, country-neutral behavior lives in a **shared** module; a localization (`l10n_*`)
module only **seeds** the rules, data, chart and taxes that differ per country.

- A module without the `l10n_` prefix carries no content of one country: no law, account, form or
  value of a country, and no hook, field or filter that exists only to serve one. It behaves as
  core of the series does on the generic chart.
- When a change touches a localized feature, first ask whether two or more countries would share
  the behavior. If so it belongs in the generic module and each `l10n_*` only adds its country's
  records; never a parallel architecture inside one country's module.
- User-facing strings stay translatable.
- **A value or rule set by law or regulation is a data record, never code** (§ 6).
- **A generic accounting module runs on the generic chart of `account`** and is tested with it:
  accounts come from configuration, from the account type or from a partner or company property,
  never from a code a localization assigns; the `l10n_*` module fills the hook. Its tests take
  accounts from the generic chart through the chart template's `ref(xmlid)` and pin that chart in
  the test base class, so the suite does not depend on the localization installed. Code that
  builds lines of a plain journal entry sets `tax_ids` explicitly, an empty list when no tax is
  meant.

## 3. Standard app menu architecture (modules with `application=True`)

A module marked `application=True` presents the standard Odoo app shape, checked on its manifest
and menu tree:

- **One root menu** for the app, feature menus beneath it.
- **A Reports menu**: one overview report plus the child reports the business needs.
- **A Configuration menu when the app has settings**: `Settings` (the `res.config.settings`
  extension for this app) plus the admin-only configuration models of the app. Operational data
  does not live under Configuration; admin setup does.

A non-application module (an extension, a bridge) is exempt from this section.

## 4. Extension, access and data hygiene (every module)

- **A field with `groups=` on a model users duplicate breaks the copy** for everyone outside the
  group: restrict editing in the view and in `create`/`write`, or set `copy=False` and say why.
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
  that works.
- **No hardcoded locale, currency, company, timezone, date format or language** in a shared
  module: read them from the record, the company, the user or the context.
- **A defect in Odoo core is reported, not patched in a downstream module.** The fix goes where
  the defect lives.
- **An economic transaction belongs to the commercial partner.** Invoices, receivables and
  payables, payments, reconciliation, credit limits and statements are recorded for and compared
  by `commercial_partner_id`, never a child contact.

- **Point of sale works offline.** Anything at the counter - the selling screen, printing,
  scales, scanners, the customer display, a bridge between them - works through the PoS offline
  mode and syncs later; a sale never depends on the server at the moment of selling.

## 5. Change hygiene: versions, migrations, retirement

Within a series; a cross-series code upgrade follows
`${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md` § Convention 0.

- **Migrations are decided last (SSOT).** Within one PR, the plan's `migration` node is the ONLY
  step that edits a module's `version` or creates a `migrations/` folder; its `odoo-coder`
  (`MODE: migration`) writes them, after every code, test, review, acceptance, debug, i18n and
  docs node and immediately before `integrate`. Several nodes touching one module never bump it
  separately - they record what existing data needs in the worklog for that node.
- **One version bump per changed module.** Every module with a change outside its tests
  (`tests/`, `static/tests/`) gets ONE bump of its short `version` per PR, by the smallest step -
  `x.y.z` -> `x.y.(z+1)`, a two-component `x.y` -> `x.y.1`, never `x.(y+1)`; versions compare
  numerically, a missing component read as 0 (`0.3` < `0.3.1` < `0.4`). The version is what tells
  an existing database, and the platform hosting it, that the module must be reloaded. Not
  bumped: a module new in the PR, a `test_*` module, a module not installable after the PR, and a
  module the PR upgrades to this series (`installable` False before, True after). After a rebase
  onto a base that moved, the bump is taken again from the new base.
- **A migration script only when existing data must change.** A change that makes data the
  databases of this series already hold wrong adds ONE folder
  `migrations/<series>.<new short version>/` holding at most one file per stage
  (`pre-migrate.py`, `post-migrate.py`, `end-migrate.py`), never a file named after a business
  topic and never an edit to a folder that already exists. A folder named in the short form runs
  on every series the module ships on, and is written only when the SRS asks for that.
  `${CLAUDE_PLUGIN_ROOT}/scripts/lib/migration_gate.py check` proves the version and the folder
  (`--help` states every rule).
- **A released series keeps what its databases rely on.** No field, model or XML ID that holds
  data is removed or renamed (retire it, below). A renamed method keeps its old name as a wrapper
  that logs a deprecation warning, calls the new one and carries a TODO, and every caller moves to
  the new name; code retired with no replacement is deleted outright. Views and layouts may
  change. This binds a module that is already installable on the series whenever a PR changes it,
  a PR that upgrades other modules to the series included.
- **A database upgrade between series is never module work**: it takes a dedicated upgrade tool
  and repository, never this plugin. A module migration script only moves the data of the
  module's own change within one series.
- **Retire, do not delete.** A module, model or field that customer databases hold data in stays
  in place with a TODO naming the next major that removes it - in `__manifest__.py` right under
  the `name` key for a module, a short comment on the definition for a model or field. Only a
  pre-migration script removes data that carries an XML ID; no remaining module uses anything of
  a retired one.
- **Data files declare only part of a module's XML IDs.** Odoo mints more for `_inherits`
  records and for the records a cron or a user creates; a migration never lists XML IDs from the
  data files - it reads them from the database.
- **Removing a `noupdate` data file deletes its records** at `_process_end` and cascades into
  customer records through `ondelete='cascade'`. A record customers reference is pinned by
  dropping its XML ID, never by removing the file.

**A module merge is semantic.** Code merged from another module reads as if written once in the
target: one class per model, no same-module `super()` chain where one method does, view
extensions folded into the base view, and every shell or "module not installed" fallback deleted.

## 6. Legal rules as data

**Scope.** Anything a law or regulation sets and can change: values (a rate, a ceiling, a
threshold, a deadline, an effective date, an account or form code) and rules (a time window, an
hour limit, how a tax is treated, a duty to ask consent or to notify). The test: can a new law
change it? A technical constant no law sets is out of scope.

**Shape.**
- An ordinary record, shipped as XML data and editable in the UI: a salary rule, an
  `account.tax`, a report line, an `account.payment.term`.
- A legal model the module defines carries a valid-from and a valid-to date, both optional; code
  reads the record in force on the business date for the company and country, so a change already
  enacted is entered today and applies on its date.
- Which record applies is a company field or a Settings option: a new company gets the default
  from data (e.g. the chart template's `template_data`), a running company keeps its value.
- Python only reads data: no constant, no number inside a formula string, no hardcoded xmlid, no
  `if` for one article.
- The generic module holds the model and the way it is read, for every country; an `l10n_*`
  module only seeds its country's records (§ 2).
- The software records a violation and never enforces the law by blocking (§ 0).

**Removing a legal constant.** Grep the whole repository, `migrations/` and tests included. A
migration script declares the historical values it needs itself and never imports them from
`models/`: a fresh-install test runs no migration, so nothing else catches that import error
before an upgraded database does.

**Per role.**
- Architect: the SRS (without one, the design header) has a section `Legal rules as data` that
  answers per legal element: (1) which record carries it; (2) which role edits it, on which
  screen; (3) its effective dates; (4) where the user updates it when the law changes. An element
  that is not data yet gets the shape it will take.
- Coder: before adding a field or a setting, search for the field, record or data template that
  already holds the value. A legal value or rule in Python, in a module the PR touches, moves to
  data in the same PR; one in another module is listed in the return (file:line, what it is).
- Test writer: `test-behavior-contract.md` § Protect the outcome, never the implementation.
- Reviewer: asks the four questions; a legal value or rule held in Python is a finding.
