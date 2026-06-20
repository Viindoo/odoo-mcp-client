---
name: odoo-data-migration
description: >
  Write Odoo migration scripts (`migrations/<version>/pre-migrate.py` and/or `post-migrate.py`)
  for schema or data changes - field rename, type change, model split/merge, data backfill, or
  module data transform - using parameterized SQL and/or ORM, following openupgradelib helpers
  where available, plus a VERIFICATION checklist (row counts, spot-checks, rollback note). The
  deliverable is the written script file; executing it is a separate human-gated deploy step.
  Trigger on: "write a migration script", "rename this field in the database", "backfill data
  after a column change", "split a model", "merge two models", "generate pre/post migrate".
  Vietnamese triggers: "viết migration script", "đổi tên cột trong CSDL", "backfill dữ liệu
  sau khi đổi field", "tách model", "gộp model", "sinh file pre_migrate / post_migrate". DO NOT
  trigger for: WHAT changed between versions (odoo-version-diff); deploy readiness gate
  (odoo-deploy-checklist); full upgrade plan (odoo-plan-upgrade)
model: inherit
---

## Persona

Developer / Data Engineer - writes safe, idempotent Odoo migration scripts. Prioritizes
data integrity above all else: parameterized SQL only, explicit transaction boundaries,
verifiable row counts, and a rollback note in every output.

---

## Out of Scope

| Topic | Skill to use instead |
|---|---|
| API deprecation scan before upgrade | `odoo-deprecation-audit` |
| What changed between two Odoo versions | `odoo-version-diff` |
| Deploy readiness gate | `odoo-deploy-checklist` |
| Full upgrade orchestration plan | `/odoo-plan-upgrade` |
| Backend model/field creation (no migration needed) | `odoo-coding` |
| Executive risk overview | `odoo-risk-overview` |

**IMPORTANT - execution boundary.** This skill WRITES the migration script. It does NOT
execute the migration against any live database. Running the migration is a separate,
human-gated step that belongs in the deploy pipeline (see `odoo-deploy-checklist` Domain 3
and the project `INSTANCE-LIFECYCLE.md`); when it is run via `odoo-bin -u <module>`, the
interpreter is resolved per `snippets/venv-resolution.md` (the matching instance's `python`
field), not system `python3`. Never claim or imply that invoking this skill migrates any real
data.

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
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Primary tools:**
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `api_version_diff` - Structured diff of an API symbol or scope across two Odoo versions: new, changed, removed, deprecated items.
- `lookup_core_api` - Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `validate_relation` ⊕ - Assert a relational field points at the expected comodel (many2one/one2many/many2many).
- `entity_lookup` ★ - Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
<!-- END GENERATED TOOLS -->

## When to use

Migration is needed when a module version bump introduces any of: field rename, field type change, model split/merge, data backfill (new stored/required field), module data transform (XML records, ir.config_parameter, many2many tags), or column drop with preservation.

---

## Method

### Round 0 - Load context

Read `.odoo-ai/context.md` if present. Extract `odoo_version`, `modules`, and any migration history. If absent, ask for target version and module name in a single message.

Call `set_active_version` and `set_active_profile` (parallel if both available).

### Round 1 - Confirm migration type and inspect models (parallel)

> **Design-gate (non-trivial migrations).** A model split/merge, a backfill/transform with more
> than one viable mapping, or a migration where the pre/post split is itself a real decision is a
> DESIGN choice. When no approved design doc exists (`.odoo-ai/designs/<slug>-*.md` or a
> `design_doc` input), recommend `odoo-solution-design` first (`SUGGESTED_NEXT: odoo-solution-design`).
> A straight field rename / type change goes directly to script-writing below.

Confirm: (1) migration type, (2) source/target field/model names, (3) module name and version bump, (4) timing (pre-migrate / post-migrate / both).

Simultaneously call (parallel):

```
model_inspect(model=<source_model>, method='fields', odoo_version='<version>')
model_inspect(model=<target_model>, method='fields', odoo_version='<version>')   # if model changes
entity_lookup(kind='field', model=<source_model>, field=<source_field>, odoo_version='<version>')
api_version_diff(symbol=<model_or_field>, from_version=<source_v>, to_version=<target_v>)
```

Use results to confirm actual column name (stored fields only), real field types, and whether Odoo core already handles this change in the target version.

### Round 2 - Validate relations and helpers (parallel)

For relational fields, call `validate_relation` for each. For openupgradelib helpers, call `lookup_core_api` to confirm the helper signature. Fire all calls in parallel.

### Round 3 - Write the script(s)

Path: `<module>/migrations/<module_version>/pre-migrate.py` (before ORM load) and/or `post-migrate.py` (after ORM load). `<module_version>` matches the NEW version string in `__manifest__.py`.

Script rules and code templates: `${CLAUDE_PLUGIN_ROOT}/skills/odoo-data-migration/references/script-rules.md`

Output template (script file + verification checklist): `${CLAUDE_PLUGIN_ROOT}/skills/odoo-data-migration/references/output-templates.md`

### Round 4 - Produce the verification checklist

Append verification checklist to the chat response after writing the file(s). See template in `${CLAUDE_PLUGIN_ROOT}/skills/odoo-data-migration/references/output-templates.md`.

---

## Standalone-first fallback

When OSM is unreachable, follow the three-tier grounding in
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

- **Tier 2 - Disk:** Run `find . -maxdepth 4 -name "__manifest__.py"` to locate the
  module. Read `models/*.py` with `grep -n "class \|_name\|_inherit\|= fields\." models/*.py`
  to discover real field names and types. Read any existing `migrations/` directory for
  prior patterns. Derive the Odoo version from the manifest `version` field if
  `.odoo-ai/context.md` is absent.
- **Tier 2 - Column check fallback:** When OSM cannot confirm a column name, add a comment
  in the script: `# VERIFY: confirm column name against live schema with \`\d <table>\` before running`.
- **Caveat:** Label output `grounded: local-source (not OSM-indexed)`. Confirm openupgradelib
  helper availability once OSM is back online.
- Escalate to the caller (`NEEDS_CONTEXT`) only for business decisions (e.g. what the
  default backfill value should be) that no source file encodes.

---

## Examples

See `${CLAUDE_PLUGIN_ROOT}/skills/odoo-data-migration/references/examples.md` for three worked examples: field rename, data backfill for a new stored computed field, and Selection-to-Many2one type change.

---

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the run-driver - it does not change anything produced above.
