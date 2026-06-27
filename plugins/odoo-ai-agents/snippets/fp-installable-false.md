<!-- SSOT snippet. Referenced by forward-port agents when handling new modules
     and ANY module with installable:False at the target version.
     Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/fp-installable-false.md. -->

# Forward-Port: installable=False Rule

## Scope - applies to ALL installable:False modules at target

This rule applies to THREE categories of module during forward-port:

1. **New module landing** - module does not yet exist on the target repo.
2. **Pre-existing / dormant installable:False modules** - module already exists
   on the target repo but carries `'installable': False` (was dormant before the
   forward-port began, or becomes dormant during it).
3. **First-enabled at source, not yet upgraded to target** - the module became
   `installable: True` for the first time at source series X (previously dormant
   or absent) but has NOT yet been verified/upgraded for target series Y. When
   forward-ported X->Y it must land `installable: False` - same treatment as a
   brand-new module - because it is not ready for the target stack.

## Discriminator - read TARGET CLEAN-TIP state (before merge)

**Before dispatching any review/adapt agent for a module**, determine its
`installable` status at the **target clean-tip** - the state of the target
branch BEFORE the forward-port merge is applied. Do NOT read the manifest
post-merge; after merge the source-side `installable: True` is already present
and masks the gap.

- OSM lookup (static index of target series): `module_inspect(name='<module>', method='summary', odoo_version='<target>')`
- OR checkout the target branch and read `<module>/__manifest__.py` BEFORE merging.

Decision:
- Target clean-tip: module ABSENT or `installable: False` -> forward as
  `installable: False` -> route to the **LINT-ONLY LANE** (see below). Do NOT
  proceed to extract/adapt/business-logic tiers.
- Target clean-tip: module EXISTS with `installable: True` -> forward content
  normally (standard forward-port adapt flow applies).

This covers all three categories: a new module is absent at target; a dormant
module is `installable: False` at target; a category-3 first-enabled module is
absent or `installable: False` at target because it was never upgraded there.

### Category 2/3 - manifest reset after merge (upgraded-then-forwarded)

When a pre-existing dormant module (category 2) or first-enabled-at-source module (category 3)
has `installable:False` at the TARGET CLEAN-TIP but the merge carries in `installable:True`
(from a source-series upgrade commit), the agent MUST reset the manifest immediately after the
merge - before any lint or content work:

1. Re-set `'installable': False` in `__manifest__.py`.
2. Re-comment `'auto_install': True` if present - add
   `# TODO: Uncomment when upgrading module to production-ready status`.
3. Re-comment `'application': True` if present - same TODO note.

These are the same actions as for a new-module landing (see "Manifest flags" below). The
trigger is different: for a new module the manifest arrives absent; for category 2/3 the
manifest already exists at target with `installable:False` but the merge overwrites it to True.
The result must be the same: `installable:False` with breadcrumb comments so
`odoo-modules-upgrade` reads them at Y+1 upgrade time.

Recognition: determine the target module's `installable` at the target clean-tip before merging
(delegate the read to `git-surveyor`, or capture it during P0/scope); if clean-tip =
`installable:False` and the merged manifest shows `installable:True`, the reset is required.
Do NOT diff git history to decide - the clean-tip state is the unambiguous signal.

### Delegated source-history confirmation (category 3 ambiguity)

When it is unclear whether a module falls under category 3 (recently flipped
`installable: False -> True` at source), the orchestrator dispatches the
dedicated read-only leaf agent **`odoo-installable-prober`** (sonnet) to read
the SOURCE repo git history and confirm whether a recent `installable: False ->
True` transition exists for the module. The agent returns a one-line verdict
for the merge-log (e.g. `<module>: first enabled at 17.0 commit abc1234 -
category-3 confirmed`). This git-history read is heavy and MUST be delegated
to keep it out of the main/specialist context - do not inline it.

---

## LINT-ONLY LANE

When a module is `installable:False` at target, apply ONLY the following:

- Run `flake8` / `pylint` / `eslint` / `prettier` / `ruff` to detect syntax
  and style violations that block CI.
- Fix the MINIMUM needed to reach green CI. No other changes.
- Do NOT review or adapt business logic.
- Do NOT adapt computed fields, onchange handlers, overrides, or constraints.
- Do NOT deep-OSM-ground symbol usage (e.g. no `find_override_point`,
  `impact_analysis`, `suggest_pattern`).
- Do NOT rate or report business-logic findings (HIGH/MED/LOW).
- SOLE exception: fix a syntax or lint error that flake8/eslint/prettier/ruff
  flags and that blocks CI outright - that is the only code touch permitted.

Rationale: forward-port carries the intent and behavior of ACTIVE modules.
A dormant (installable:False) module is not in production and has not been
upgraded for the target version. Adapting its business logic conflates two
separate decisions: forward-port vs. upgrade.

---

## Manifest flags - Immediate action on landing (new modules)

For a **new module** (does not yet exist on the target repo):

### 1. Set `'installable': False`

Prevents accidental installation before the module is properly integrated into
the target stack. The module will remain dormant until explicitly enabled after
integration validation.

### 2. Comment out `'auto_install': True` (if present)

Add note: `# TODO: Uncomment when upgrading module to production-ready status`

Reason: When `installable` is set back to `True` later, `auto_install: True`
must not auto-install the module before you intend it. Comment it out now; both
flags (`installable` and `auto_install`) open together during the actual upgrade.

### 3. Comment out `'application': True` (if present)

Add note: `# TODO: Uncomment when upgrading module to production-ready status`

Reason: An incomplete module should not appear as a standalone app in the app
store or top menu. Comment it out now; both flags open together during upgrade.

---

## Code quality - Minimal fix only

If any module with `installable:False` at target has code that violates lint /
ESLint / Prettier / ruff rules:
- Fix ONLY to unblock the repo (reach green CI).
- Do NOT refactor or upgrade module content.
- Reason: forward-port carries intent and behavior, not a code upgrade
  opportunity. Nesting an upgrade inside forward-port conflates two separate
  decisions and masks which commit caused which change.

---

## A2 - No manifest version bump (forward-port)

Forward-port NEVER auto-bumps the manifest. The forward-port merge (`--no-ff`) carries the source manifest as-is; on a
`__manifest__.py` `version` conflict keep the **TARGET** file's value. The single exception is the C2
migration-threshold bump (when `S <= M`). Both rules: `[[fp-merge-absorption]]` (C1 + C2). There is no
"bump when the diff touches `.js/.scss/.xml/migrations/`" rule - that gate is removed.

---

## B2 - Deferral mode for new modules

When a new module cannot be carried forward in the current PR, choose
explicitly between two modes and record the decision in the merge-log:

| Mode | Meaning | When to use |
|---|---|---|
| **CARRY installable:False** (DEFAULT) | Land the module with `installable:False` set. Advances the merge-base (Hard Rule 7). Module falls into lint-only lane. | When the code is syntactically valid (or fixable with lint-only effort) and carrying it dormant is safe. |
| **DISCARD** | Drop the merge entirely; source re-presents the module in the next forward-port cycle. | When carrying the module would introduce build-breaking errors that exceed lint-only scope. |

Record the mode in the merge-log entry for this module:
`<module> CARRY installable:False` or `<module> DISCARD - reason`.

The CARRY mode is the default because it advances the merge-base and prevents
the module from re-appearing in every subsequent port cycle.

---

## Checklist for adapter (P8c verification)

- [ ] `installable` status read from TARGET CLEAN-TIP (before merge) - not post-merge
- [ ] Category determined: new landing / dormant / category-3 first-enabled
- [ ] If ambiguous category-3: `odoo-installable-prober` dispatched; verdict in merge-log
- [ ] `installable:False` at target clean-tip -> lint-only lane entered; no logic adapt
- [ ] For new modules: `'installable': False` is set
- [ ] For new modules: `'auto_install': True` is commented with TODO note
- [ ] For new modules: `'application': True` is commented with TODO note
- [ ] Lint is green; no refactoring beyond lint fix
- [ ] Manifest version NOT bumped on conflict (kept TARGET); migration dirs handled per C2 - [[fp-merge-absorption]]
- [ ] For pre-existing dormant / category-3: if merge carried `installable:True`, re-set to False
      + re-comment `auto_install`/`application` with TODO breadcrumb (same as new-module landing)
- [ ] Breadcrumb note: `# TODO: Uncomment when upgrading module to production-ready status` is the
      signal `odoo-modules-upgrade` reads at Y+1 upgrade time to restore the flags
- [ ] B2: deferral mode (CARRY/DISCARD) recorded in merge-log if module deferred

## When new-module flags re-open

All three commented flags re-open together during the actual module upgrade:
- Product owner confirms the module is integration-tested and stable on target.
- A separate, subsequent commit/PR upgrades: `installable: True` and uncomments
  the two conditional flags.
- This separation keeps forward-port commits focused on intent/behavior, upgrade
  commits focused on production-readiness.
- The `# TODO: Uncomment when upgrading module to production-ready status` comment IS the breadcrumb
  `odoo-modules-upgrade` reads to restore these flags.

---

## Related

- [[fp-triage-table]]: Short-circuit gate at top of EXTRACT and ADAPT tables.
- [[fp-merge-absorption]]: Merge-commit contract for all forward-port absorption work.
