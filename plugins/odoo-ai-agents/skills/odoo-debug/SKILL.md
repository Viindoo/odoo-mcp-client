---
name: odoo-debug
argument-hint: "[error / symptom / traceback]"
description: >-
  Root-causes a live Odoo failure: traceback, wrong value, blank view, failed install
---

## Role

Front door for root-causing one broken Odoo behaviour. It classifies the symptom, launches ONE
debugger for the incident (`odoo-backend-debugger` or `odoo-ui-debugger`, by layer), escalates
the same incident one tier at a time when a full pass proves no root cause, and hands the proven
cause to the fix. No fix before the cause is proven. Method SSOT:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/debug-method.md`; symptom catalog:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-failure-modes.md`.

## Out of Scope

- **Writing the fix once the cause is proven** -> `odoo-coding` (step 4 hands it there)
- **Proactive scan with no specific symptom** -> `odoo-perf-audit`, `odoo-security-audit`, `odoo-deprecation-audit`
- **Static review of a diff, PR or pasted block** -> `odoo-code-review`
- **Rating a working screen** (aesthetics, a11y, perf verdict) -> `odoo-ui-review`
- **Comparing two builds for visual drift** -> `odoo-visual-regression`

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

**Primary tools:**
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `entity_lookup` ★ - Single-entity drill-down by kind discriminator: model, field, method, view, module, pattern, or report - with full inheritance chain and source module.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `test_base_classes` - Menu of official Odoo test framework base classes (TransactionCase, HttpCase, SavepointCase, Form, etc.) for the given version, with test_type and cursor contract.
- `tests_covering` - List test methods that have COVERS_MODEL/COVERS_FIELD/COVERS_METHOD edges to the target model or field (static reference coverage, not runtime executed coverage).
<!-- END GENERATED TOOLS -->

`set_active_version` once (the reachability probe) and pass the concrete version in the brief;
the debugger makes every other OSM call itself.

## Steps

1. **Triage, inline.** From the report, the traceback or the console text, write three lines
   before any launch: the symptom in one line; the layer per `odoo-failure-modes.md` (`backend`
   for Python, ORM, data state, access rules, module load and migration; `ui` for OWL, JS,
   QWeb, SCSS, console and network; `perf` for "slow now"; `security` only when the report itself
   names a leak, an escalation or an injection); the modules in scope and whether they live in a
   worktree under edit (`W`). A WARNING that matches a deny-path, guard or SQL-constraint
   signature in a test run is expected noise, not a symptom. Capture `SHARE_DIR` and
   `ISOLATE_DIR` once with `project_dir`; mint the session slug per
   `${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 1 and sweep
   abandoned evidence first (Clause 2):

   ```
   find <ISOLATE_DIR>/visual/debug/ -mindepth 1 -maxdepth 1 -type d -mmin +43200 -exec rm -rf {} +
   ```
2. **Launch ONE debugger** (`model: sonnet`) with the brief in
   `${CLAUDE_PLUGIN_ROOT}/skills/odoo-debug/references/debugger-brief.md`: `odoo-backend-debugger`
   for `backend`, `odoo-ui-debugger` for `ui` (browser-exclusive per MCP family,
   `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T2; `BROWSER MODE: headed` only
   when the human asks to watch and a display exists). A `perf` symptom invokes
   `odoo-perf-audit` inline (reactive mode) instead; a named leak, escalation or injection adds
   `odoo-security-audit` inline beside the backend debugger. A symptom with both a backend and a
   UI face gets the backend debugger first; the UI debugger only when the backend report finds
   no cause.
3. **Escalate the same incident, never fan out.** The report's `Root cause` line is proven only
   with an executed or described confirm-by-toggle. `NOT YET CONFIRMED` after a full pass:
   launch the same debugger once more at `model: opus` with `PRIOR_FINDINGS` = the report path,
   so the excluded hypotheses are not re-tested. Still unproven after the opus pass: ask the human
   once, as a trade-off and never by tier name ("The deep pass found no provable cause. Try the
   deepest-reasoning setting? Costs about 2x. (approve / skip / cancel)"); `approve` launches the
   same brief at `model: fable`, `skip` ends with the hypotheses excluded as `concerns`.
4. **Hand off the fix.** With a proven cause: as a plan node, return `NEEDS_NEXT` with the report
   path and `next: odoo-coding`, and stop; standalone, invoke `odoo-coding` inline (Skill tool)
   with the report path and the line "fix to this proven root cause; the regression test the
   report names comes first". A wider sweep instead of a point fix routes to the audit skill of
   that layer.

## Standalone-first fallback

- **OSM unreachable:** the debugger grounds from disk per its own fallback and labels
  `grounded: local-source`; the run continues.
- **Browser or instance unreachable:** the UI debugger uses pre-captured console, network and
  screenshot evidence when the context holds it; otherwise return `NEEDS_NEXT` with
  `next: odoo-instance` (`operation: ensure-up`, the series and the modules under test) and
  launch the UI debugger once the instance is up. Never ask the user to paste console output.

## Agent-managed tools

`odoo-backend-debugger`, `odoo-ui-debugger` (one per incident; a later tier resumes the incident
with `PRIOR_FINDINGS`); the audit skills inline. A debugger launches nothing and never invokes
this skill back.

## Output format

The debugger's Output Contract of `${CLAUDE_PLUGIN_ROOT}/skills/_shared/debug-method.md`, every
field filled, an honest `NOT YET CONFIRMED` where a step is incomplete. Worked examples:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-debug/references/examples.md`.

## Continuation Contract

Append the block of `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`: `produced` = the
report path; `next: odoo-coding` with a proven cause; `status: DONE` with `concerns` listing the
excluded hypotheses when no tier proved one.
