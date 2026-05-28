---
name: odoo-upgrade-plan-full
description: |
  Generate a comprehensive Odoo upgrade plan from source version to target version. Chains executive risk overview → deprecation audit → API/feature version diff → synthesis with action ordering and effort estimate. Replaces the legacy odoo-upgrade-planner agent
---
# /odoo-upgrade-plan-full

End-to-end upgrade planning command for Odoo version migrations. Chains four skill phases — executive risk overview, deprecation audit, API/feature diff, and synthesis — into a single, gated workflow that produces a developer-readable action checklist and an executive-readable effort estimate in one deliverable.

Type: `/odoo-upgrade-plan-full [v<source>-to-v<target>]`

Optional: supply version range on the command line (e.g., `v16-to-v17` or `16.0-17.0`). If omitted, the command prompts you for source and target versions.

## When to use

Invoke this command when:

- A client asks for a **full upgrade plan** — not just a deprecation audit or version diff alone.
- You need **executive-readable risk overview** and **dev-readable action items** in the same deliverable.
- You are replacing a legacy `agents/odoo-upgrade-planner.md` invocation (deprecated; kept for history).

Do **not** invoke this command when:
- You only need a quick deprecation check: use `odoo-deprecation-audit` skill directly.
- You only need an API diff: use `odoo-version-diff` skill directly.
- You are at agent depth ≥ 1: this command invokes skills and may invoke the `odoo-coder` agent via Agent tool; it must be launched from depth 0 (main context).

## Hard rules

- **Read context first**: Before asking the user anything, read `.odoo-ai/context.md` if it exists. Extract `odoo_version` (source default), `custom_modules` list, and any standing upgrade notes. If the file does not exist, skip silently and rely on user input.
- **Inputs required before proceeding**: Confirm all four inputs before starting Phase 1:
  1. Source version (default from context, else ask)
  2. Target version (ask; no default)
  3. Scope: all custom modules, or a specific list (ask — paste module names or type "all")
  4. Deadline preference: `immediate` (within 1 sprint), `next-quarter`, or `long-term` (>6 months)
- **Each phase is gated**: Do not advance to the next phase until the user explicitly confirms (yes / dig deeper / cancel). On `cancel`, end the command and discard all in-flight output.
- **File write is explicitly gated**: Phase 6 asks the user before writing to disk. Never write the plan file without confirmation.
- **Skill invocations via natural-language**: All four skills (`odoo-risk-overview`, `odoo-deprecation-audit`, `odoo-version-diff`, `odoo-addon-diff`) are invoked by describing the intent in natural language to the AI agent routing layer — not by calling tool names directly. This is depth 0 behavior.
- **`odoo-coder` agent is depth-1 safe**: If sample migration code snippets are needed for specific module fixes, invoke the `odoo-coder` agent via the Agent tool (acceptable at depth 0 → depth 1). Do not spawn further subagents from within it.
- **Confidentiality**: All examples and plan artifacts use abstract customer labels, never real customer names, salary data, or internal pricing.

## Phases

### Phase 0 — Parse arguments and confirm inputs

1. Parse `$ARGUMENTS` for version range if provided. Accepted formats: `v16-to-v17`, `16.0-17.0`, `v16.0-to-v17.0`. Normalize to `<source>/<target>` pair (e.g., `16.0` / `17.0`).
2. Read `.odoo-ai/context.md`. Extract `odoo_version` → use as source default if not in `$ARGUMENTS`. Extract `custom_modules` → pre-fill scope suggestion.
3. Ask the user for any missing inputs (source version, target version, scope, deadline preference). Show the pre-filled values so the user can accept or override.
4. Display a confirmation block before proceeding:

```
Upgrade plan inputs:
  Source version : 16.0
  Target version : 17.0
  Scope          : all custom modules (12 found in context)
  Deadline       : next-quarter

Proceed? (yes / edit / cancel)
```

Do not start Phase 1 until the user confirms.

---

### Phase 1 — Executive risk overview

Invoke the `odoo-risk-overview` skill with the confirmed source and target versions as context.

The skill produces a CEO-level risk dashboard covering:
- Migration complexity rating (LOW / MEDIUM / HIGH / CRITICAL)
- Top 3-5 risk factors (breaking framework changes, OWL migration, removed APIs, ecosystem readiness)
- Go/no-go signal with rationale

Show the risk dashboard output in full. Then gate:

> "Risk picture OK? Reply `yes` to continue, `dig deeper` to explore a specific risk factor, or `cancel` to stop."

- `yes` → Phase 2.
- `dig deeper` → Ask which risk factor. Use `odoo-risk-overview` or lookup tools to expand that factor. Loop back to gate.
- `cancel` → End command.

---

### Phase 2 — Deprecation audit

Invoke the `odoo-deprecation-audit` skill scoped to the user's confirmed module list and source version.

The skill scans for deprecated symbol usage and groups findings by severity:
- **BREAKING** — must fix before upgrade or migration will fail
- **WARN** — should fix; will produce runtime warnings or unexpected behavior
- **STYLE** — optional cleanup; no functional impact

Show a count summary first:

```
Deprecation audit complete:
  BREAKING : 8 findings across 4 files
  WARN     : 14 findings
  STYLE    : 6 findings
```

Then show the full findings table (file | symbol | line | tier | recommended replacement).

Gate:

> "Audit complete? Reply `yes` to continue to version diff, `export` to save raw findings now, or `cancel`."

- `yes` → Phase 3.
- `export` → Write findings to `.odoo-ai/deprecation-<source>-<date>.md`, confirm, then continue to Phase 3.
- `cancel` → End command.

---

### Phase 3 — API and feature version diff

Invoke the `odoo-version-diff` skill for the source → target pair, requesting the **developer track** (API diff, not feature highlights track).

The skill outputs:
- New/changed/removed ORM APIs
- Controller and route changes
- JavaScript / OWL framework changes
- Removed XML `qweb` template namespaces or view keys
- Any relevant `ir.model.data` external ID renames

Show the full diff output. Gate:

> "Diff reviewed? Reply `yes` to proceed to action ordering, or `cancel`."

- `yes` → Phase 4.
- `cancel` → End command.

---

### Phase 4 — Action ordering

Synthesize findings from Phases 1-3 into a prioritized, ordered action checklist. The order is fixed regardless of which items are present:

1. **Pre-flight — CRITICAL fixes** (BREAKING tier from deprecation audit; any CRITICAL risk factors from risk overview that require code changes before upgrade can start)
2. **Per-module migration scripts** (one entry per custom module; ordered by dependency graph — base modules first)
3. **Test plan** (smoke tests → integration tests → critical user flows scoped to affected modules)
4. **Deploy window** (link to `odoo-deploy-checklist` skill at deploy time; include environment checklist: staging → UAT → production)
5. **Post-deploy verification** (key business flows to verify within 48 h of cutover)
6. **Rollback plan** (snapshot/restore procedure, rollback decision criteria, responsible owner)

For each action item, record: description, severity (CRITICAL / HIGH / MEDIUM / LOW), owner role (developer / analyst / DevOps / business), and a placeholder for effort (filled in Phase 5).

Display the ordered checklist. No gate here — proceed directly to Phase 5.

---

### Phase 5 — Effort estimation

For each action item in Phase 4, assign an S / M / L / XL size using the following rules:

| Size | Day range | When to use |
|------|-----------|-------------|
| S    | 0.5 - 1 d | Single-file fix, well-understood API swap, trivial test update |
| M    | 1 - 3 d   | Multi-file change, partial OWL rewrite, moderate test coverage needed |
| L    | 3 - 5 d   | Module-level rewrite, significant controller or view rework |
| XL   | 5+ d      | Full subsystem migration, unknown API, cross-module dependency chain |

For BREAKING-tier items that touch OWL 3 / Python 3.12 runtime changes: bump one size tier up (S→M, M→L, L→XL) as a complexity premium.

Display the effort table:

```
| # | Action item                        | Size | Days    | Owner     |
|---|-----------------------------------|------|---------|-----------|
| 1 | Fix deprecated _compute_ calls     | M    | 1-3 d   | Developer |
| 2 | Migrate custom_module_A views      | L    | 3-5 d   | Developer |
...
| N | Rollback plan documentation        | S    | 0.5-1 d | DevOps    |

Total estimated effort: X.X - Y.Y developer-days
Deadline fit: [next-quarter — FEASIBLE / TIGHT / UNLIKELY]
```

Include a plain-language deadline fit assessment based on user's stated deadline from Phase 0.

No gate — proceed to Phase 6.

---

### Phase 6 — Assemble and output plan

Assemble the final upgrade plan document with the following sections in order:

```markdown
# Odoo Upgrade Plan: <source> → <target>

**Generated:** <date>
**Scope:** <module list>
**Deadline:** <user-stated preference>

## Executive Summary
<3-5 sentences: complexity rating, top risks, total effort range, go/no-go recommendation>

## Risk Overview
<Phase 1 output — CEO-level risk dashboard>

## Deprecation Findings
<Phase 2 output — BREAKING / WARN / STYLE findings table>

## API and Feature Diff
<Phase 3 output — developer-track diff>

## Action Order
<Phase 4 checklist — numbered, with severity and owner>

## Effort Estimate
<Phase 5 table — sizes, day ranges, totals, deadline fit>

## Rollback Plan
<Phase 4 rollback entry expanded: snapshot procedure, decision criteria, owner>
```

Display the assembled plan to the user in full. Then gate:

> "Save plan? Reply:
> - `save` — write to `.odoo-ai/upgrade-plans/<source>-<target>-<YYYY-MM-DD>.md`
> - `terminal` — output to terminal only (no file written)
> - `cancel` — discard"

- `save` → Create `.odoo-ai/upgrade-plans/` directory if it does not exist. Write the plan file. Confirm: `✓ Plan saved to .odoo-ai/upgrade-plans/16.0-17.0-2026-05-28.md`.
- `terminal` → Confirm plan is already displayed; end command.
- `cancel` → Discard; end command.

---

## Standalone fallback (OSM unreachable)

If the `odoo-semantic` MCP server is unreachable during any skill invocation:

1. Note the degraded phase inline: `[DEGRADED — OSM unreachable: Phase 1 risk overview skipped]`.
2. Prompt the user to provide manual input for that phase:
   - Phase 1: "Describe the top 3 risk factors you are aware of for this upgrade."
   - Phase 2: "Paste known deprecated symbol names or file paths, or skip."
   - Phase 3: "Describe any API changes you have already identified, or skip."
3. Insert `<TBD: verify via odoo-risk-overview / odoo-deprecation-audit / odoo-version-diff when OSM back>` placeholders in the corresponding plan sections.
4. Continue to Phase 4 with available data. Mark the final plan header: `⚠ PARTIAL PLAN — OSM was unreachable during generation. Verify TBD sections before use.`

---

## Examples

**Example 1 — Manufacturing SME, 12 custom modules, v15 to v17:**
Customer operates a manufacturing business on Odoo 15.0 with 12 custom modules (MRP extensions, costing overrides, warehouse rules). Goal: upgrade to 17.0 before end of Q3. Phase 1 returns HIGH complexity (two major framework jumps, OWL 3 migration required). Phase 2 finds 11 BREAKING findings across 5 modules. Phase 3 flags removal of `report_action` legacy signature and 3 renamed external IDs. Phase 4 produces 18 action items. Phase 5 estimates 22-34 developer-days total — deadline marked TIGHT for Q3. Plan saved to `.odoo-ai/upgrade-plans/15.0-17.0-2026-05-28.md`.

**Example 2 — Release prep, all custom modules, v17 to v18:**
Internal team preparing v18 release cut for all custom add-ons. Deadline: long-term (no rush). Phase 1 returns MEDIUM complexity (single-hop, mostly stable APIs). Phase 2 finds 4 WARN findings, 0 BREAKING. Phase 3 flags two new ORM helpers available but backward-compatible. Phase 4 produces 9 action items. Phase 5 estimates 6-10 developer-days. Plan output to terminal only for review before committing to file.

---

## What this command does NOT do

- **Does NOT execute migrations**: only produces a plan. No code changes are made to the codebase during this command.
- **Does NOT generate full migration scripts**: for per-module migration code, invoke the `odoo-coder` agent separately after this plan is approved. This command may call `odoo-coder` for illustrative snippets only, not production-ready scripts.
- **Does NOT replace the deployment runbook**: use the `odoo-deploy-checklist` skill at actual deploy time. This plan links to it but does not execute it.
- **Does NOT send or share the plan**: no email, no CRM sync, no external output. The plan is written to `.odoo-ai/upgrade-plans/` only on explicit user confirmation.

---

## See also

- `/odoo-bid-respond` — if this upgrade is part of a prospect proposal (RFQ → bid → plan).
- `odoo-deploy-checklist` skill — use at deploy time to execute the deploy window and post-deploy verification steps from Phase 4.
- `odoo-deprecation-audit` skill — direct invocation for deprecation-only checks without full plan overhead.
- `odoo-version-diff` skill — direct invocation for API diff only.
- `agents/odoo-upgrade-planner.md` — legacy agent (deprecated, kept for history). Use this command instead.
