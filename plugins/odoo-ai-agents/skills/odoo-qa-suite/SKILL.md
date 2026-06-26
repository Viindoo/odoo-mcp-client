---
name: odoo-qa-suite
description: >
  Orchestrate a full QA cycle for an Odoo feature or module in one pass: generate
  structured test cases from a feature description, produce a pre-deploy QA checklist,
  and triage open bugs with severity, repro steps, and suspected module. Delegates
  phases via the Skill tool (odoo-deploy-checklist for checklist; odoo-debug for
  runtime triage), handles test-gen and bug-triage inline. Trigger on: "write test
  cases for this feature", "QA checklist before release", "triage this bug", "QA
  pipeline for this change", "full QA suite", "test plan for this release",
  "acceptance tests for this module". Also fires on Vietnamese: "viết test case", "checklist
  QA trước release", "triage bug / phân loại lỗi", "kế hoạch test cho bản phát hành". Do NOT
  trigger for: pure code review (route to
  odoo-code-review); a UI rendering defect needing live browser inspection with no
  triage output (route to odoo-debug directly); pre-deploy mechanical safety gate
  alone (route to odoo-deploy-checklist directly)
---

## Persona

QA engineer / Odoo developer - producing test plans, checklist gates, and structured
bug reports for a module or feature change. Audience is the engineering team preparing
a release. Output is operational and actionable; not executive-level. Three jobs in one
pass: (1) generate test cases, (2) gate on a pre-deploy checklist, (3) triage bugs with
severity and root-cause hints.

This skill is a **composition orchestrator**: do not call MCP tools directly. Delegate phases
via the Skill tool to leaf skills; handle work inline only when no leaf skill covers it.

---

## Out of Scope

| Topic | Route instead |
|---|---|
| Pure code review / patch review | `odoo-code-review` |
| Live UI rendering / layout defect investigation (no triage output needed) | `odoo-debug` (direct) |
| Pre-deploy gate only (no test-case gen, no bug triage) | `odoo-deploy-checklist` (direct) |
| Full upgrade orchestration plan | `/odoo-plan-upgrade` |
| Deprecated API audit | `odoo-deprecation-audit` |
| Executive risk dashboard | `odoo-risk-overview` |
| Continuous performance profiling or memory leak analysis | `odoo-debug` + browser tools |

---

## Phase 0 - Scope confirmation

Read `.odoo-ai/context.md` first (per `${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md`) to extract `odoo_version` and `modules`. Use those as defaults and skip asking for already-resolved fields.

Ask for all missing inputs in a **single message**:
1. **Feature / module name** (skip if clear from context)
2. **Odoo version** e.g. `17.0` (skip if pre-filled)
3. **Open bugs to triage** (optional) - as a list, or a file path to `Read`; pass `none` to skip triage
4. **Scope** - `unit` / `integration` / `both` (default: `both`)

Present a **soft-plan-gate** before running any phase:

```
## Proposed QA Plan
Feature/module: <name>
Version:        <X.Y>
Phases:         generate-tests → qa-checklist → bug-triage
Output:         .odoo-ai/qa/
Gate: approve / refine: [feedback] / cancel
```

After gate approval, run the **test inventory** before entering Phase 1. Call
`tests_covering` for the primary model(s) of the module to find which test
methods already exercise those models, then call `test_coverage_audit` for the
module to identify untested methods and coverage gaps. Example:

```
tests_covering(model='sale.order', odoo_version='17.0')
test_coverage_audit(module='sale_management', odoo_version='17.0')
```

Carry both results into Phase 1 so test-case generation focuses on **uncovered
business rules** - do not generate test cases for behaviors already protected
by existing tests unless the existing test has a known gap flagged by
`test_coverage_audit`.

---

## Phase 1 - Test-case generation (inline)

Generate a structured test suite table:

| # | Test name (business rule) | Type | Precondition | Steps | Expected result | Pass/Fail |
|---|---|---|---|---|---|---|

Rules:
- Test name must state a **business rule**, not an implementation detail. Good: "Sale order total updates when line quantity changes". Bad: "test_compute_amount_total".
- Every test must have one scenario that would make it **fail** - if no wrong answer exists, the test is useless and must not be included.
- **Steps must drive the real workflow, not seed a state.** Name the actual `action_*` / `button_*` method (e.g. "call `action_confirm`"), build via `Form()` where an onchange is involved, run access checks as the real user (`with_user(...)`), never `sudo()` on the action under test - never write a step that injects terminal `state` with `create({'state': ...})` (SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md`).
- Cover at minimum: happy path, edge case (empty/zero/boundary), error path (invalid input), permission check (user without access gets rejected).
- Separate unit tests (no DB, no UI) from integration tests (multi-model or multi-user).
- Ground test mechanics in the TARGET version - test classes, tag syntax, and JS framework (QUnit vs Hoot) differ across Odoo versions. Resolve via OSM (`set_active_version` + `cli_help`) and follow `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`; never assume one version's command line applies to another.
- **Python test class grounding:** call `test_base_classes` before specifying any TransactionCase/HttpCase in the generated test table. This tool always returns the `cr.commit() FORBIDDEN - isolation is savepoint rollback` contract alongside the authoritative base-class menu for the target version. Example: `test_base_classes(odoo_version='17.0')`. When dispatching Phase 1 test writing to `odoo-test-writing`, instruct that leaf skill to run `test_base_classes` first and to apply `${CLAUDE_PLUGIN_ROOT}/snippets/python-naming-conventions.md` for all test local variables (Rule A: no `l`/`O`/`i`; B/C when Viindoo profile).
- **JS test framework grounding:** for any frontend module, call `js_test_inspect` to discover which framework (hoot/qunit/tour) the module already uses and what test suites exist. Example: `js_test_inspect(module='web', odoo_version='17.0')`. Never assume Hoot vs QUnit from version alone - some modules pin an older framework during a transitional release. When dispatching JS test writing to `odoo-test-writing`, forward the `js_test_inspect` result so the leaf skill writes tests in the correct framework.
- Output file: `.odoo-ai/qa/<slug>-test-cases.md`

---

## Phase 2 - QA checklist (Skill tool: odoo-deploy-checklist)

Invoke `odoo-deploy-checklist` via the Skill tool: "Generate a pre-deployment QA checklist for <module> targeting Odoo <version> in staging environment, covering all 8 domains: pre-flight, backup, data migration, downtime, deploy mechanics, smoke tests, monitoring, and rollback."

Write the returned checklist to `.odoo-ai/qa/<slug>-deploy-checklist.md`.

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

Output file: `.odoo-ai/qa/<slug>-bug-triage.md`

---

## Phase 4 - Summary (inline)

Write `.odoo-ai/qa/<slug>-qa-summary.md`:

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
    risk_level: L2
```
so the run-driver provisions the instance; the caller (or next DAG node) then re-invokes this skill to continue Phase 3. Fall back to `BLOCKED` only if provisioning is itself impossible.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the run-driver - it does not change anything produced above.
