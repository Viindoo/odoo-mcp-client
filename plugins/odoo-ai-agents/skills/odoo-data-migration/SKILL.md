---
name: odoo-data-migration
argument-hint: "[source] [target] [model/data]"
description: >-
  Writes in-series module migration scripts: field rename, type change, backfill
model: inherit
---

## Role

Front door for the version bump of a change and, where existing data must change, its module
migration script - both within ONE Odoo series: it resolves the scope, launches `odoo-coder` in
`MODE: migration` to write and prove them, has `odoo-code-reviewer` (`MODE: R1`) review that diff,
and returns. It writes no code itself.

---

## Out of Scope

| Topic | Skill to use instead |
|---|---|
| API deprecation scan before upgrade | `odoo-deprecation-audit` |
| What changed between two Odoo versions | `odoo-version-diff` |
| Deploy readiness gate | `odoo-deploy-checklist` |
| Full upgrade orchestration plan | `/odoo-plan-upgrade` |
| Upgrade a module's code to a higher Odoo series | `odoo-modules-upgrade` |
| Backend model/field creation (no migration needed) | `odoo-coding` |
| Executive risk overview | `odoo-risk-overview` |

**Execution boundary.** The script is proven on a scratch database only. Running it on a real
database is a separate, human-gated deploy step (`docs/reference/INSTANCE-LIFECYCLE.md` § `-i` vs
`-u` semantics); never claim or imply that this skill migrated real data.

---

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
- `set_active_version` ☆ - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- `set_active_profile` ☆ - Pin tenant profile for the session so subsequent calls scope to one customer profile.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `lookup_core_api` - Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `validate_relation` ⊕ - Assert a relational field points at the expected comodel (many2one/one2many/many2many).
- `entity_lookup` ★ - Single-entity drill-down by kind discriminator: model, field, method, view, module, pattern, or report - with full inheritance chain and source module.
<!-- END GENERATED TOOLS -->

## Scope

The version bump of each changed module and the module migration script of a change within ONE
series - the data of the module's own change, nothing else. It never moves a database between
series: that takes a dedicated upgrade tool and repository, not this plugin - never offer it. It
never executes a migration on a real database.

**Under a plan** (an active `run-<id>`, a `WORKTREE_PATH` or plan-provided `inputs`) this skill
runs only as the plan's `migration` node, or from `odoo-modules-upgrade` for the modules that
were already installable on the target series and that its PR changed; invoked from any other
node it launches nothing and returns `BLOCKED(only the migration node bumps or writes
migrations)`.

**Precondition** (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-platform-design-principles.md` § 5): a
module that was `installable` True before the change and stays True, with a change outside its
tests, after the development loops and a proven fresh install. Each such module gets the bump; a
script is written only for a module whose change makes existing data of the series wrong. No
module meets it: launch nothing and say so.

## Method

1. **Resolve.** Series and profile per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`;
   `SHARE_DIR`, `ISOLATE_DIR` once per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`.
   `WORKTREE_PATH` is required (the plan's `run-integration`, else one provisioned through
   `git-toolkit:git-ops`, never the principal checkout). Collect the modules that meet the
   precondition and every data note the run's nodes left for them in the worklog.
2. **Design gate (standalone only).** A model split or merge, a backfill with more than one viable
   mapping, or a pre/post split that is a real decision, with no approved design: the
   Continuation Contract carries `next: odoo-solution-design` (below) and nothing is launched.
3. **Launch** ONE `odoo-coder` (model `sonnet`) with `MODE: migration`, `MODULES` (those modules),
   `WORKTREE_PATH`, `ODOO VERSION`, `PROFILE`, `SHARE_DIR`, `ISOLATE_DIR`, `RUN_ID`, `WORKLOG`,
   `DESIGN_DOC`, and `REQUEST` = per module, the bump and the data its change moves (`none` for
   a bump alone). The coder follows
   `references/writing-the-script.md`: the version read and computed (the new version is the
   smallest step; an existing bump of this PR is reused - extend its existing
   `migrations/<series>.<version>/` folder instead of adding a second one), `migration_gate.py
   check`, and a real upgrade within the series that reads the moved data back.
4. **Review.** Launch `odoo-code-reviewer` `MODE: R1` (model `haiku`) on the coder's commit range;
   a CRITICAL or HIGH finding goes back to the same coder with SendMessage, then to the same
   reviewer, at most twice.
5. **Return** the commit range, `MIGRATION_GATE=` and the upgrade proof per module, and the
   verification checklist of `references/output-templates.md`.

Examples: `references/examples.md`.

## Continuation Contract

Append a Continuation Contract block per `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`
(status / produced / next).

**Design-first entry (standalone only).** When step 2 fired, the block's `next:` carries `skill:
odoo-solution-design`, `reason: <the open design choice>`, `inputs: {odoo_version, module}`,
`confidence: 0.4`. Under a plan (any of the three signals of
`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Approved-plan-artifact detection) a
missing design is plan drift: STOP and route back to `odoo-planning`
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § Execution adherence); the runner
never launches a design node
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Running the plan,
invariants).
