<!-- SSOT snippet. Referenced by forward-port agents for new modules and ANY module with
     installable:False at the target. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/fp-installable-false.md. -->

# Forward-Port: installable=False Rule

## Scope - applies to ALL installable:False modules at target

Three categories of module during forward-port:

1. **New module landing** - the module does not yet exist on the target repo.
2. **Pre-existing / dormant installable:False modules** - the module exists on the target with
   `'installable': False` (dormant before the forward-port began, or made dormant during it).
3. **First-enabled at source, not yet upgraded to target** - the module became
   `installable: True` for the first time at the source series but has NOT been upgraded for the
   target series. Forward-ported, it lands `installable: False` - the same treatment as a
   brand-new module.

## Discriminator - read TARGET CLEAN-TIP state (before merge)

**Before dispatching any review/adapt agent for a module**, determine its `installable` status
at the **target clean-tip** - the target branch BEFORE the forward-port merge. Never read the
manifest post-merge: the source-side `installable: True` is already present and masks the gap.

- Read `<module>/<tgt-descriptor>` at the target ref via the `git-toolkit:git-ops` skill
  (read-only) - `<tgt-descriptor>` is the descriptor filename of the TARGET series
  (`odoo-era-boundaries.md` § 6; resolution owned by `odoo-forward-port` Hard rule 11) - an absent
  `installable` key means installable, an absent FILE means the module is not on the clean tip.

Decision:
- Target clean-tip: module ABSENT or `installable: False` -> forward as `installable: False` ->
  the **LINT-ONLY LANE** (below). Never the extract/adapt/business-logic tiers.
- Target clean-tip: module EXISTS with `installable: True` -> forward content normally.

### Category 2/3 - manifest reset after merge (upgraded-then-forwarded)

When a category 2 or 3 module has `installable:False` at the TARGET CLEAN-TIP but the merge
carries in `installable:True` (a source-series upgrade commit), reset the SAME `<tgt-descriptor>`
file immediately after the merge - before any lint or content work:

1. Re-set `'installable': False` in `<tgt-descriptor>`.
2. Re-comment `'auto_install': True` if present - add
   `# TODO: Uncomment when upgrading module to production-ready status`.
3. Re-comment `'application': True` if present - same TODO note.

**NEVER create the other descriptor filename to perform this reset.** Edit the descriptor the
target clean-tip already carries, in place: a second descriptor beside it becomes the one Odoo
loads and silently drops every model, view and dependency the real one declared. A failed write
to `<tgt-descriptor>` means the wrong filename was targeted: re-resolve it.

The result is the same as a new-module landing: `installable:False` with breadcrumb comments
`odoo-modules-upgrade` reads at the next upgrade. Decide from the clean-tip state captured
before the merge (git-ops read, or P0/scope), never by diffing git history.

### Delegated source-history confirmation (category 3 ambiguity)

When it is unclear whether a module falls under category 3 (recently flipped `installable: False
-> True` at source), the orchestrator dispatches the read-only leaf agent
**`odoo-installable-prober`** (haiku) to read the SOURCE repo git history and return a one-line
verdict for the merge-log (e.g. `<module>: first enabled at <series> commit abc1234 - category-3
confirmed`). The read is heavy: always delegated, never inline.

---

## LINT-ONLY LANE

When a module is `installable:False` at target, apply ONLY the following:

- Run `flake8` / `pylint` / `eslint` / `prettier` / `ruff` to detect syntax and style violations
  that block CI; fix the MINIMUM needed to reach green CI. No other code touch: never refactor
  or upgrade module content.
- Do NOT review or adapt business logic, computed fields, onchange handlers, overrides or
  constraints; do NOT deep-OSM-ground symbol usage (`find_override_point`, `impact_analysis`,
  `suggest_pattern`); do NOT rate or report business-logic findings (HIGH/MED/LOW).
- The manifest `version` follows C1 of `[[fp-merge-absorption]]` (the dormant branch: the source
  version when the range changed it), not this lane.

A dormant module is not in production and has not been upgraded for the target; adapting its
logic conflates forward-port with upgrade.

---

## Manifest flags - immediate action on landing (new modules)

For a **new module** (does not yet exist on the target repo):

1. Set `'installable': False` - the module stays dormant until explicitly enabled after
   integration validation.
2. Comment out `'auto_install': True` (if present), with
   `# TODO: Uncomment when upgrading module to production-ready status` - so re-enabling
   `installable` later does not auto-install it before intended; both flags open together at
   the upgrade.
3. Comment out `'application': True` (if present), same TODO note - an incomplete module does not
   appear as a standalone app.

---

## A2 - Manifest version (forward-port)

The manifest `version` follows `[[fp-merge-absorption]]` C1 alone, gate included: a module dormant
at the target takes the source version when the range changed it; a new module lands with the
version the merge carries. Migration dirs follow C2 of the same file. There is no "bump when the
diff touches `.js/.scss/.xml/migrations/`" rule.

---

## B2 - Deferral mode for new modules

When a new module cannot be carried forward in the current PR, choose explicitly and record the
decision in the merge-log (`<module> CARRY installable:False` or `<module> DISCARD - reason`):

| Mode | Meaning | When to use |
|---|---|---|
| **CARRY installable:False** (DEFAULT) | Land the module with `installable:False`; advances the merge-base; lint-only lane. | The code is syntactically valid (or fixable with lint-only effort). |
| **DISCARD** | Drop the merge entirely; the source re-presents the module in the next cycle. | Carrying it would introduce build-breaking errors beyond lint-only scope. |

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
- [ ] Manifest version set per C1 (dormant at target: the source version when the range changed
      it); migration dirs handled per C2 (P9.6) - [[fp-merge-absorption]]
- [ ] For pre-existing dormant / category-3: if merge carried `installable:True`, re-set to False
      + re-comment `auto_install`/`application` with TODO breadcrumb (same as new-module landing)
- [ ] Breadcrumb note: `# TODO: Uncomment when upgrading module to production-ready status` is the
      signal `odoo-modules-upgrade` reads at the next upgrade to restore the flags
- [ ] B2: deferral mode (CARRY/DISCARD) recorded in merge-log if module deferred

## When new-module flags re-open

All three commented flags re-open together in a separate, later commit or PR, once the product
owner confirms the module is integration-tested and stable on the target: `installable: True`
and the two conditional flags uncommented. The `# TODO: Uncomment when upgrading module to
production-ready status` comment is the breadcrumb `odoo-modules-upgrade` reads.

---

## Related

- [[fp-triage-table]]: short-circuit gate at the top of the EXTRACT and ADAPT tables.
- [[fp-merge-absorption]]: merge-commit contract for all forward-port absorption work.
