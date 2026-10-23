---
name: odoo-coding
argument-hint: "[what to build or change]"
description: >-
  Write or change Odoo module code for any behavior request, even non-technical: fields, rules, overrides, views
---

## Role

Developer front door: turn an approved node (or a small change with no plan) into committed,
tested code by launching ONE `odoo-coder` per node, at the tier the design hints, inside the
node's worktree. Compute nothing the plan already computed, write no source yourself, and own the
cross-run module-coordination ledger.

## Out of Scope

- **Designing the approach** -> `odoo-solution-design` (a node with no design and `SRS_REQUIRED`
  criteria met goes there first; a small change without them is coded directly)
- **Ordering several nodes** -> `odoo-planning`
- **Reviewing the result** -> `odoo-code-review` (a plan node, or the caller's next step)
- **Data-only migration scripts** -> `odoo-data-migration`
- **Finding one hook location** -> `odoo-override-finding`

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
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `find_override_point` - Show override chain, super() safety guidance, and anti-patterns for a method to find the safest place to inject custom behavior.
- `impact_analysis` - Risk assessment of changing or removing a field, method, or model: blast radius, dependent modules, and downstream fields.
- `tests_covering` - List test methods that have COVERS_MODEL/COVERS_FIELD/COVERS_METHOD edges to the target model or field (static reference coverage, not runtime executed coverage).
- `test_coverage_audit` - Audit an entire module for test coverage gaps: lists fields/methods with zero COVERS_* edges (never referenced by any test).
- `test_base_classes` - Menu of official Odoo test framework base classes (TransactionCase, HttpCase, SavepointCase, Form, etc.) for the given version, with test_type and cursor contract.
<!-- END GENERATED TOOLS -->

## Inputs

| Field | Meaning |
|---|---|
| plan node (`NODE`, `MODULES`, `REQUEST` with its criteria, `depends_on`, `build_tier_hint`, `DESIGN_DOC`, `MASTER_DESIGN_DOC`, `SRS`, `RECON`, `DOMAIN`) | consumed verbatim; nothing re-derived |
| `WORKTREE_PATH` | the node's worktree; absent -> provision one through `git-toolkit:git-ops` at the path `project_dir` (axis `worktree`) returns, forked per `${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md` § Base-branch resolution |
| `SHARE_DIR`, `ISOLATE_DIR`, `RUN_ID` | captured once, forwarded unchanged; standalone, `RUN_ID` is the worklog `<run-or-slug>` |
| `ODOO VERSION`, `PROFILE` | concrete; absent version -> the ladder of `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`, never a default |
| `INSTANCE_HANDLE` + `ADDONS_PATH` or `SELF_PROVISION: worktree-addons` | one of them; a per-node dispatch with a `WORKTREE_PATH` gets `SELF_PROVISION` |
| `COMMIT: caller`, `CONSTRAINTS`, `SERVER_WIDE`, `MODE: adapt` fields, `TEST LEG: deferred - <phase>` | forwarded verbatim from a porting or upgrade caller; never set here |
| `AUTONOMOUS FIX (review-driven | debug-driven)` + the findings or root cause | resume the node's coder with them (§ Fix rounds) |

## Steps

1. **Orient.** Read the code row of `${CLAUDE_PLUGIN_ROOT}/snippets/read-before-act.md` (its
   § 2 governs every question you raise). Use the captured state dirs; read the worklog
   (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`). Delete `coding/<slug>-<date>/`
   directories under `<ISOLATE_DIR>` untouched for 30 days
   (`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3).
2. **One node, one coder.** A plan gives the node; standalone, the change is one node with the
   modules it touches in dependency order (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md`)
   and `SRS_REQUIRED` decided with the list in `odoo-solution-design` (met -> that skill first).
   Standalone work that needs more than one node: stop and invoke `odoo-planning`
   (`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` § One Plan-Mode gate per request, rule 6).
   Two nodes that touch the same module never run at once.
3. **Tier.** `model` = `build_tier_hint` from the design; absent, the table of
   `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection (5.1 for
   haiku, 5.2 for opus, else sonnet). Record it in `plan.md`. Fable is never set here.
4. **Ledger.** For every NEW module the node creates (in neither OSM nor the addons path), claim
   it in `<SHARE_DIR>/coordination/modules` per
   `${CLAUDE_PLUGIN_ROOT}/snippets/module-coordination-ledger.md` before launching; a lost claim
   re-queues the node behind the bounded barrier of that contract.
5. **Launch** `odoo-coder` with the brief below (fill the universal skeleton of
   `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton read by path, plus the
   Coder delta). Several independent nodes launch in one message within the Mode B budget of the
   guard.
6. **Collect.** A `DONE` carries a commit range (or a file list under `COMMIT: caller`), both test
   verdicts, the web-client boot evidence when the node touched `static/src/**`, the impact-map
   path and the mapping of every `REQUEST` item to its files; a return missing one of them is not
   `DONE`. `BLOCKED: manifest dependency <dep> unresolved` is
   classified with the ledger's decision table, never by the coder. `NEEDS_NEXT` naming a module
   outside the node: under a plan, a module outside the approved scope re-plans (same contract,
   rule 7); standalone, widen `MODULES` and
   resume the same coder with `SendMessage`. `NEEDS_JUDGEMENT` or a failed own gate: relaunch once,
   one tier up, with `PRIOR ATTEMPT`.
7. **Record** per node in `<ISOLATE_DIR>/coding/<slug>-<date>/plan.md`: modules, tier, the agent id
   of the launch, status, commit range.

## Brief to `odoo-coder`

```
DISPATCH MODEL: <tier>
NODE: <id>
REQUEST: <the change in business terms; "Done when:" + the acceptance criteria or their pointer>
MODULES: <m1 @ path>, <m2 @ path> (dependency order)
DOMAIN: <Domain line | omit>
WORKTREE_PATH: <abs>   SHARE_DIR: <abs>   ISOLATE_DIR: <abs>   RUN_ID: <id>   WORKLOG: <run-or-slug>
ODOO VERSION: <v>   PROFILE: <p | none>
DESIGN_DOC: <path | none>   MASTER_DESIGN_DOC: <path | none>   SRS: <path | none>   RECON: <path | none>
SELF_PROVISION: worktree-addons | INSTANCE_HANDLE: <handle> + ADDONS_PATH: <dirs>
COMMIT: caller            (only when the caller sent it)
CONSTRAINTS / SERVER_WIDE / MODE: adapt + INTENT, BUCKET, SOURCE TESTS, BROKEN TEST-SYMBOLS, TARGET TEST EXAMPLES / CHANGE KIND / TEST LEG   (verbatim from the caller, when sent)
PRIOR ATTEMPT: <relaunch only>
USER LANGUAGE: <lang | omit>
```

The brief carries inputs only. Paths handed down (design, recon, worklog, state dirs, worktree)
never appear in shipped code.

## Fix rounds

Findings from review or acceptance, or a proven root cause from debug, go back to the coder that
built the node with `SendMessage`, never to a new launch. Three rounds per
node; a fourth finding of the same kind stops the loop and returns the evidence to the caller.
Review itself is a plan node or the caller's next step, never driven from here.

## Standalone-first fallback

OSM unreachable: the module graph comes from the descriptors on disk (`__manifest__.py`, or
`__openerp__.py` where a module has it); the coder grounds per
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`; `plan.md` says
`graph from disk (OSM unavailable)`.

## Agent-managed tools

This skill launches `odoo-coder` only. The coder launches `odoo-impact-recon` when it has no
recon, a second `odoo-coder` only for a part that exceeds one agent's output budget, and
`odoo-frontend-coder` only for a frontend part with new JS or OWL files disjoint from the backend
files; it invokes `odoo-test-writing` inline and `odoo-instance` for every instance run.

## Continuation Contract

Append the block of `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`: `produced` = the
node's commit range (or file list), `plan.md`, the impact map and the worklog entries; `next:
odoo-code-review` with `inputs: {odoo_version: <v>, impact_map: <path>}` except under
`COMMIT: caller` or when the plan already wires a review node.
