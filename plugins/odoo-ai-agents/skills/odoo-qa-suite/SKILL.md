---
name: odoo-qa-suite
argument-hint: "[module/cluster to test]"
description: >
  Produce a static release QA package for an Odoo feature or module in one pass: generate a structured
  release TEST-PLAN (test-case table, non-executing), gate on a pre-deploy safety checklist, and triage
  user-reported bugs with severity, repro steps, and suspected module. Delegates phases via the Skill tool
  (odoo-deploy-checklist for checklist; odoo-debug for runtime triage), handles test-gen and bug-triage
  inline. Trigger on: "write test cases for this feature", "QA checklist before release", "triage this bug",
  "test plan for this release". Also fires on Vietnamese: "viết test case", "checklist QA
  trước release", "triage bug / phân loại lỗi", "kế hoạch test cho bản phát hành". Do NOT trigger for:
  executing or adjudicating acceptance on a live instance or cluster (route to odoo-acceptance); pure code
  review (route to odoo-code-review); pre-deploy gate alone (route to odoo-deploy-checklist directly);
  writing executable test files (test_*.py/Hoot/tours) route to odoo-test-writing
---

## Role

QA engineer / Odoo developer producing test plans, checklist gates, and structured bug reports for a
module or feature change. Audience: the engineering team preparing a release; output is operational
and actionable, not executive-level. Three jobs in one pass: (1) generate test cases, (2) gate on a
pre-deploy checklist, (3) triage bugs with severity and root-cause hints.

**Composition orchestrator:** delegate phases via the Skill tool to leaf skills; handle work inline
only when no leaf skill covers it.

---

## Out of Scope

| Topic | Route instead |
|---|---|
| Executing or adjudicating acceptance / running tests on a live instance or cluster / behavioral blast-radius cluster verification | `odoo-acceptance` |
| Pure code review / patch review | `odoo-code-review` |
| Live UI rendering / layout defect investigation (no triage output needed) | `odoo-debug` (direct) |
| Pre-deploy gate only (no test-case gen, no bug triage) | `odoo-deploy-checklist` (direct) |
| Full upgrade orchestration plan | `/odoo-plan-upgrade` |
| Deprecated API audit | `odoo-deprecation-audit` |
| Executive risk dashboard | `odoo-risk-overview` |
| Continuous performance profiling or memory leak analysis | `odoo-debug` + browser tools |

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

**Primary tools:**
- `cli_help` - Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags.
- `tests_covering` - List test methods that have COVERS_MODEL/COVERS_FIELD/COVERS_METHOD edges to the target model or field (static reference coverage, not runtime executed coverage).
- `test_coverage_audit` - Audit an entire module for test coverage gaps: lists fields/methods with zero COVERS_* edges (never referenced by any test).
- `test_base_classes` - Menu of official Odoo test framework base classes (TransactionCase, HttpCase, SavepointCase, Form, etc.) for the given version, with test_type and cursor contract.
- `js_test_inspect` - List JsTestSuite nodes in a module: framework mix (hoot/qunit/tour), file paths, suite sizes, describe/test sample, mounts, tags.
<!-- END GENERATED TOOLS -->

---

## Phase 0 - Scope confirmation

Resolve series, profile, and module scope per
`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` before asking for any project fact -
the ladder derives from the declared instance catalog and then from the checkout itself, so asking
comes last, not second. Whatever it resolves is pre-filled; skip asking for it.

Ask for all remaining missing inputs in a **single message**:
1. **Feature / module name** (skip when the resolved module scope or the request already names it)
2. **Odoo series** e.g. `17.0` (skip when the ladder resolved it; never substitute a default)
3. **Open bugs to triage** (optional) - as a list, or a file path to `Read`; pass `none` to skip triage
4. **Scope** - `unit` / `integration` / `both` (default: `both`)

Present a **soft-plan-gate** before running any phase:

```
## Proposed QA Plan
Feature/module: <name>
Version:        <X.Y>
Phases:         generate-tests → qa-checklist → bug-triage
Output:         <ISOLATE_DIR>/qa/
Gate: approve / refine: [feedback] / cancel
```

`qa/` is Tier-2 ISOLATE; resolve it via the same resolve-capture-substitute protocol in
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` (captured path shown as `<ISOLATE_DIR>`
below).

After gate approval, run the **test inventory** before Phase 1: call `tests_covering` for the
module's primary model(s) to find which test methods already exercise them, then `test_coverage_audit`
for the module to identify untested methods and coverage gaps. Example:

```
tests_covering(model='sale.order', odoo_version='17.0')
test_coverage_audit(module='sale_management', odoo_version='17.0')
```

Carry both into Phase 1 so test-case generation focuses on **uncovered business rules** - do not
generate cases for behaviors already protected by existing tests unless `test_coverage_audit` flags a
known gap.

---

## Phase 1 - Release TEST-PLAN (static, non-executing, inline)

Generate a structured release test-plan table for planning and review. STATIC document: the Pass/Fail
column is left blank; no tests execute here. Derived from code structure and coverage gaps, NOT from a
requirement oracle.

For a behavioral acceptance oracle + live execution across the blast-radius cluster, dispatch
`odoo-acceptance` instead (it delegates oracle authoring to `odoo-qa-planner`). The two artifacts are
complementary: this Phase 1 = release planning table; qa-planner = immutable execution oracle. Do NOT
duplicate the oracle's scenario steps into this table.

Generate a structured test suite table:

| # | Test name (business rule) | Type | Precondition | Steps | Expected result | Pass/Fail |
|---|---|---|---|---|---|---|

Rules:
- Test name must state a **business rule**, not an implementation detail. Good: "Sale order total updates when line quantity changes". Bad: "test_compute_amount_total".
- Every test must have one scenario that would make it **fail** - if no wrong answer exists, the test is useless and must not be included.
- **Steps must drive the real workflow, not seed a state.** Name the actual `action_*` / `button_*` method (e.g. "call `action_confirm`"), build via `Form()` where an onchange is involved, run access checks as the real user (`with_user(...)`), never `sudo()` on the action under test - never write a step that injects terminal `state` with `create({'state': ...})` (SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md`).
- Cover at minimum: happy path, edge case (empty/zero/boundary), error path (invalid input), permission check (user without access gets rejected).
- Separate unit tests (no DB, no UI) from integration tests (multi-model or multi-user).
- Ground test mechanics in the TARGET version - test classes, tag syntax, and JS framework (QUnit vs Hoot) differ across versions. Resolve via OSM (`set_active_version` + `cli_help`) and follow `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`; never assume one version's command line applies to another.
- **Python test class grounding:** call `test_base_classes` before specifying any TransactionCase/HttpCase in the table - it returns the `cr.commit() FORBIDDEN - isolation is savepoint rollback` contract plus the authoritative base-class menu (e.g. `test_base_classes(odoo_version='17.0')`). For runnable tests, route to `odoo-test-writing` (see frontmatter `description`) - this phase only records the base-class menu in the table.
- **JS test framework grounding:** for any frontend module, call `js_test_inspect` (e.g. `js_test_inspect(module='web', odoo_version='17.0')`) to discover the framework (hoot/qunit/tour) and existing suites. Never assume Hoot vs QUnit from version alone - some modules pin an older framework during a transitional release.
- Output file: `<ISOLATE_DIR>/qa/<slug>-test-cases.md` (state-root cache, never git-tracked - no
  `WORKTREE_PATH` applies to this phase; the executable `.py`/`.js` test files themselves are
  written by `odoo-test-writing`, which carries its own `WORKTREE_PATH` contract per
  `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` field 5)

---

## Phase 2 - QA checklist (Skill tool: odoo-deploy-checklist)

Invoke `odoo-deploy-checklist` via the Skill tool: "Generate a pre-deployment QA checklist for <module> targeting Odoo <version> in staging environment, covering all 8 domains: pre-flight, backup, data migration, downtime, deploy mechanics, smoke tests, monitoring, and rollback."

Write the returned checklist to `<ISOLATE_DIR>/qa/<slug>-deploy-checklist.md`.

Gate before dispatching: "approve / skip / cancel".

---

## Phase 3 - Bug triage (inline, or Skill tool: odoo-debug for runtime issues)

If no open bugs provided in Phase 0, skip and note "No bugs to triage" in the summary.

For each bug:

```
### Bug: <title>

**Severity:** Critical | High | Medium | Low
Severity rationale: <one sentence - business impact>

**Reproduction steps:**
1. <step>
2. <step>
...

**Expected:** <what should happen>
**Actual:** <what happens>

**Suspected module:** <odoo module name or "unknown">
**Suspected layer:** UI | Business logic | Data / ORM | Integration | Infrastructure
**Suggested next step:** <odoo-debug for runtime inspection | odoo-coding for fix | escalate>
```

Severity rules (non-negotiable - never soften):
- **Critical**: data loss, financial integrity failure, security breach, system down.
- **High**: core business flow broken (sale, invoice, purchase) with no workaround.
- **Medium**: non-critical flow broken or degraded; workaround exists.
- **Low**: cosmetic, minor UX, or edge-case inconvenience.

If a bug requires live browser inspection to classify, invoke `odoo-debug` via the Skill tool: "Investigate the following runtime issue in Odoo <version> and return a root-cause analysis with reproduction steps: <bug description>." Incorporate the returned root-cause into the triage entry.

Output file: `<ISOLATE_DIR>/qa/<slug>-bug-triage.md`

---

## Phase 4 - Summary (inline)

Write `<ISOLATE_DIR>/qa/<slug>-qa-summary.md`:

```
# QA Summary - <feature/module> @ Odoo <version>

## Test suite
- Total cases: <N>  Unit: <N>  Integration: <N>
- Coverage areas: <list of business rules covered>

## Checklist verdict
<READY / NEEDS WORK / NOT READY> - <one-sentence reason>

## Bug triage
- Bugs triaged: <N>  Critical: <N>  High: <N>  Medium: <N>  Low: <N>
- Blockers (Critical + High): <list or "none">

## Suggested next skills
- `odoo-debug` - for any Critical/High bugs requiring live runtime investigation
- `odoo-deploy-checklist` - run standalone for the full 8-domain gate if not done
- `odoo-coding` - for implementing fixes uncovered during triage
```

---

## Standalone-first fallback

When OSM is unreachable:
1. **Phase 1 (test-case gen)**: fully inline - no MCP tools needed. Runs normally.
2. **Phase 2 (deploy checklist)**: dispatch `odoo-deploy-checklist` in standalone mode (leaf skill marks OSM-dependent Domain 1 rows as `⚠ Manual check` automatically).
3. **Phase 3 (bug triage)**: inline triage runs normally; skip the `odoo-debug` Skill-tool invocation for runtime inspection and note: `(OSM offline - runtime inspection via odoo-debug requires reconnection)`

Add notice at top of summary: `> Note: QA suite ran in standalone mode. OSM-dependent checks marked ⚠ Manual check.`

When no live Odoo instance is reachable for Phase 3 runtime bug triage: emit `status: NEEDS_NEXT` with:
```
next:
  - skill: odoo-instance
    reason: provision the Odoo instance needed for runtime bug reproduction
    inputs: {operation: ensure-up, series: "<series from context>", modules: ["<modules under test>"]}
    confidence: 0.9
```
so the run-harness provisions the instance; the caller (or next DAG node) then re-invokes this skill to continue Phase 3. Fall back to `BLOCKED` only if provisioning is itself impossible.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the run-harness - it does not change anything produced above.
