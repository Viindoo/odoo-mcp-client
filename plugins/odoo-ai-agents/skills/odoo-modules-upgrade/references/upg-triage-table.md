# upg-triage-table - ADAPT model-tier table

Used in P4 of `odoo-modules-upgrade` to assign a model tier to each module's adapt
adapt unit. The orchestrator resolves the tier BEFORE dispatching `odoo-coding` and
records it in `plan.md` (the tier is part of the approved plan, not a runtime improvisation).

This table refines `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection (5.1 checklist, 5.2 opus conditions) - the guard owns the tier
definitions and constraints; read it, do not restate them here.
The rows below are UPGRADE action-specific refinements only; the SSOT table settles everything else.

---

## ADAPT tier table (upgrade context, first match wins)

Action-specific rows only. Any case these rows do not settle takes the tier the guard
resolves for the module's adapt unit. Size, file count, LOC and module count alone never raise a tier.

| # | Condition | Tier |
|---|-----------|------|
| 1 | Action=MERGE or SPLIT that creates or changes a cross-module inheritance axis, OR the upgrade involves a domain-specific DSL or formula engine that must be redesigned | **fable** (always needs explicit human confirmation) |
| 2 | Action=REWRITE(model) where >=1 core model's field type changed AND the module has ORM `create`/`write`/`unlink` overrides; OR override chain has >=3 entries at target (`find_override_point`); OR cross-model computed chain or multi-company logic must be restructured; OR action=SPLIT and the split boundary is ambiguous | **opus** |
| 3 | Action=DELETE-absorbed (the coder runs the dangling-reference sweep + dep cleanup only - directory removal is delegated to git-toolkit via `git-ops`; no business logic written); OR action=KEEP with only string/label/path fixes (no ORM, no view restructure) or with additions that are fully specified (the fields, views and values are already stated); OR action=REWRITE(api) where the old-to-new mapping is already known (the deprecation fix list or the breaking-change catalog names the replacement) | **haiku** |
| 4 | Everything else - action=REWRITE(api) where the replacement must be worked out, action=KEEP with additions that need reasoning, normal OWL widget modernisation, MERGE, and any case not clearly resolved by rows 1-3 | **sonnet** (default) |

---

## Constraints (same as odoo-coding SSOT)

- **sonnet is the ambiguous-case default.** If two rows seem to apply, the higher row
  (smaller #) wins; if NO row clearly applies, use sonnet.
- **fable is never a default and ALWAYS needs explicit human confirmation.** When a module
  resolves to fable, the P3 plan-gate message must call out the TRADEOFF in plain words, never
  the tier name: `<module> - <reason>: run it on the deepest-reasoning setting? Costs about 2x.
  (approve / skip / cancel)`
  On `skip`, downgrade to opus and record the downgrade in plan.md.
- **DELETE-absorbed modules always use haiku** (the work is dangling-reference sweep + dep list edits;
  directory removal is delegated to git-toolkit via `git-ops`; no business logic is written).
- Record the chosen tier in plan.md per module. Never assign a tier at dispatch time
  without recording it.

---

## Cross-reference

- ADAPT tier definitions and tier constraints (authoritative): `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection - read it; do not restate here.
- P4 dispatch briefs and child-worktree commands: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-phase-detail.md`
- Breaking-change catalog (what P4 coders apply): `${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-classification-table.md`
