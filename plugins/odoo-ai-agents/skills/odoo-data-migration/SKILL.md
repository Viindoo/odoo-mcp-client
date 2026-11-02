---
name: odoo-data-migration
argument-hint: "[source] [target] [model/data]"
description: >-
  Writes in-series module migration scripts: field rename, type change, backfill
model: inherit
---

## Role

Front door for the module migration script of a change within ONE Odoo series: it resolves the
scope, launches `odoo-coder` in `MODE: migration` to write the version bump and the script and
prove them, has `odoo-code-reviewer` (`MODE: R1`) review that diff, and returns. It writes no code
itself.

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
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`, `describe_module`, `check_module_exists`, `resolve_orm_chain`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).
- `set_active_profile(profile_name='<profile from the resolved instance entry>')` - Pin tenant profile for the session so subsequent calls scope to one customer profile.

**Primary tools:**
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `lookup_core_api` - Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `validate_relation` ⊕ - Assert a relational field points at the expected comodel (many2one/one2many/many2many).
- `entity_lookup` ★ - Single-entity drill-down by kind discriminator: model, field, method, view, module, pattern, or report - with full inheritance chain and source module.
<!-- END GENERATED TOOLS -->

## When to use

Scope: the module migration script of a change within ONE series - the data of the module's own
change, nothing else. It is never a step of a code upgrade
(`${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md` § Convention 0) and never executes a
migration on a real database. A database upgrade between series needs a dedicated upgrade tool
and repository; not this plugin - never offer it.

**Under a plan** (an active `run-<id>`, a `WORKTREE_PATH` or plan-provided `inputs`) this skill
runs only as the plan's `migration` node; invoked from any other node it launches nothing and
returns `BLOCKED(only the migration node bumps or writes migrations)`.

**Precondition** (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-platform-design-principles.md` § 5): a
module that was `installable` True before the change and stays True, whose change alters data
existing databases hold, after the development loops and a proven fresh install. Otherwise launch
nothing and say which condition failed.

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
   `DESIGN_DOC`, and `REQUEST` = the data each module's change moves. The coder follows
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
