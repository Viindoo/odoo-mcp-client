<!-- SSOT snippet. Referenced by forward-port agents when handling new modules
     and ANY module with installable:False at the target version.
     Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/fp-installable-false.md. -->

# Forward-Port: installable=False Rule

## Scope - applies to ALL installable:False modules at target

This rule applies to TWO categories of module during forward-port:

1. **New module landing** - module does not yet exist on the target repo.
2. **Pre-existing / dormant installable:False modules** - module already exists
   on the target repo but carries `'installable': False` (was dormant before the
   forward-port began, or becomes dormant during it).

**Before dispatching any review/adapt agent for a module**, determine its
`installable` status at the target version:

- OSM lookup: `module_inspect(name='<module>', method='summary', odoo_version='<target>')`
- OR read the target-side `__manifest__.py` directly.

If `installable` is `False` at target (regardless of source-side status) -> the
module is not upgraded for the target version -> route to the **LINT-ONLY LANE**
(see below). Do NOT proceed to extract/adapt/business-logic tiers.

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

## A2 - Version-bump gate

Bump the manifest `version` field ONLY when the absorbed diff touches at least
one of: a `.js` file, a `.scss` file, a `.xml` file, or a file under
`migrations/`. Check via:

```
git diff --name-only <merge-base> | grep -qE '\.(js|scss|xml)$|/migrations/' \
  && echo BUMP || echo SKIP
```

Pure-Python changes (`*.py` only) do NOT require a version bump.

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

## Checklist for adapter (Phase 4c verification)

- [ ] `installable` status at target confirmed before any agent dispatch
- [ ] `installable:False` at target -> lint-only lane entered; no logic adapt
- [ ] For new modules: `'installable': False` is set
- [ ] For new modules: `'auto_install': True` is commented with TODO note
- [ ] For new modules: `'application': True` is commented with TODO note
- [ ] Lint is green; no refactoring beyond lint fix
- [ ] A2: version-bump applied only when `.js`/`.scss`/`.xml`/`migrations/` diff present
- [ ] B2: deferral mode (CARRY/DISCARD) recorded in merge-log if module deferred

## When new-module flags re-open

All three commented flags re-open together during the actual module upgrade:
- Product owner confirms the module is integration-tested and stable on target.
- A separate, subsequent commit/PR upgrades: `installable: True` and uncomments
  the two conditional flags.
- This separation keeps forward-port commits focused on intent/behavior, upgrade
  commits focused on production-readiness.

---

## Related

- [[fp-triage-table]]: Short-circuit gate at top of EXTRACT and ADAPT tables.
- [[fp-merge-absorption]]: Merge-commit contract for all forward-port absorption work.
