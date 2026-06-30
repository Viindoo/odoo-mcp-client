# upg-triage-table - ADAPT model-tier table

Used in P4 of `odoo-modules-upgrade` to assign a model tier to each module's adapt
work-item. The orchestrator resolves the tier BEFORE dispatching `odoo-coding` and
records it in `plan.md` (the tier is part of the approved plan, not a runtime improvisation).

This table reuses the shape of `odoo-coding`'s deterministic tier table (Phase 0, step 5).
SSOT for the tier definitions and constraints: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-coding/SKILL.md`.
The rows below are the UPGRADE-specific instantiations of those same four conditions.

---

## ADAPT tier table (upgrade context, first match wins)

| # | Condition | Tier |
|---|-----------|------|
| 1 | Action=MERGE spanning >=3 modules of the cluster AND full-stack AND estimated >800 LOC of net new code; OR action=SPLIT creating a new cross-module inheritance axis; OR the upgrade involves a domain-specific DSL or formula engine that must be redesigned | **fable** |
| 2 | Action=REWRITE(model) where >=1 core model's field type changed AND the module has ORM `create`/`write`/`unlink` overrides; OR override chain has >=3 entries at target (`find_override_point`); OR cross-model computed chain or multi-company logic must be restructured; OR action=MERGE with >5 intended files AND full-stack; OR action=SPLIT and the split boundary is ambiguous | **opus** |
| 3 | Action=DELETE-absorbed (the coder runs the dangling-reference sweep + dep cleanup only - directory removal is delegated to git-toolkit via `git-ops`; no business logic written); OR action=KEEP with only string/label/path fixes (no ORM, no view restructure); OR a single manifest version bump with no logic change | **haiku** |
| 4 | Everything else - action=REWRITE(api) for call-site updates, action=KEEP with field/view additions, normal OWL widget migration (single component), mid-size single-stack adapt, and any case not clearly resolved by rows 1-3 | **sonnet** (default) |

---

## Constraints (same as odoo-coding SSOT)

- **sonnet is the ambiguous-case default.** If two rows seem to apply, the higher row
  (smaller #) wins; if NO row clearly applies, use sonnet.
- **fable is never a default and ALWAYS needs explicit human confirmation.** When a module
  resolves to fable, the P3 plan-gate message must call it out:
  `Fable row: <module> - <reason> (~2x opus cost). Confirm fable?`
  If the human declines, downgrade to opus and record the downgrade in plan.md.
- **DELETE-absorbed modules always use haiku** (the work is dangling-reference sweep + dep list edits;
  directory removal is delegated to git-toolkit via `git-ops`; no business logic is written; haiku is sufficient).
- Record the chosen tier in plan.md per module. Never assign a tier at dispatch time
  without recording it.

---

## Cross-reference

- ADAPT tier definitions and tier constraints (authoritative): `${CLAUDE_PLUGIN_ROOT}/skills/odoo-coding/SKILL.md` Phase 0 step 5
- P4 dispatch briefs and child-worktree commands: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-phase-detail.md`
- Breaking-change catalog (what P4 coders apply): `${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-classification-table.md`
