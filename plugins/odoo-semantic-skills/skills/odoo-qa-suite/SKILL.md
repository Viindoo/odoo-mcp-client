---
name: odoo-qa-suite
description: >
  Orchestrate a full QA cycle for an Odoo feature or module: generate structured test
  cases from a feature description, produce a pre-deploy QA checklist, and triage any
  open bugs with severity classification, reproduction steps, and suspected module.
  Delegates each phase via NL-dispatch to leaf skills (odoo-deploy-checklist for
  checklist; odoo-ui-debug for runtime triage) and handles test-case generation and
  bug-triage inline. Trigger on: "write test cases for this feature", "QA checklist
  before release", "triage this bug", "what tests should I write for this module",
  "QA pipeline for this change", "generate test cases and checklist", "full QA suite",
  "bug triage with severity and repro steps", "acceptance tests for this Odoo module",
  "test plan for this release". Do NOT trigger for: pure code review (route to
  odoo-code-reviewer); UI rendering defects that need live browser inspection without
  a triage output (route to odoo-ui-debug directly); pre-deploy mechanical safety gate
  alone (route to odoo-deploy-checklist directly)
disallowed-tools: Write Edit
---

## Persona

QA engineer / Odoo developer — producing test plans, checklist gates, and structured
bug reports for a module or feature change. Audience is the engineering team preparing
a release. Output is operational and actionable; not executive-level. Three jobs in one
pass: (1) generate test cases, (2) gate on a pre-deploy checklist, (3) triage bugs with
severity and root-cause hints.

This skill is a **composition orchestrator** — it does not call MCP tools directly.
It delegates phases via NL-dispatch to leaf skills, or handles work inline when no
leaf skill covers it. The workflow-runner reads `workflows/qa-suite.workflow.yaml` and
fires this skill for the qa-suite domain; this skill body describes the inline phases
that the runner cannot resolve to a standalone leaf skill.

---

## Out of Scope

| Topic | Route instead |
|---|---|
| Pure code review / patch review | `odoo-code-reviewer` |
| Live UI rendering / layout defect investigation (no triage output needed) | `odoo-ui-debug` (direct) |
| Pre-deploy gate only (no test-case gen, no bug triage) | `odoo-deploy-checklist` (direct) |
| Full upgrade orchestration plan | `/odoo-upgrade-plan-full` |
| Deprecated API audit | `odoo-deprecation-audit` |
| Executive risk dashboard | `odoo-risk-overview` |
| Continuous performance profiling or memory leak analysis | `odoo-ui-debug` + browser tools |

---

## Phase 0 — Scope confirmation

Ask for all missing inputs in a single message (do not multi-turn):

1. **Feature / module name** — e.g. `sale`, `custom_loyalty_program`, or a description
   of the change being tested.
2. **Odoo version** — e.g. `17.0`.
3. **Open bugs to triage** (optional) — paste a list of bug titles/descriptions, or
   `none` to skip the triage phase.
4. **Scope** — `unit` / `integration` / `both` (default: `both`).

If `.odoo-ai/context.md` is present, pre-fill `odoo_version` and `modules` from it and
skip those questions.

Present a **soft-plan-gate** before running any phase:

```
## Proposed QA Plan
Feature/module: <name>
Version:        <X.Y>
Phases:         generate-tests → qa-checklist → bug-triage
Output:         .odoo-ai/qa/
Gate: approve / refine: [feedback] / cancel
```

---

## Phase 1 — Test-case generation (inline)

Generate a structured test suite table for the stated feature or module. For each test
case, produce one row in the output table:

| # | Test name (business rule) | Type | Precondition | Steps | Expected result | Pass/Fail |
|---|---|---|---|---|---|---|

Rules (ETHOS#11):
- Each test name must state a **business rule**, not an implementation detail.
  Good: "Sale order total updates when line quantity changes"
  Bad: "test_compute_amount_total"
- Every test must have one scenario that would make it **fail** — if no wrong answer
  exists, the test is useless and must not be included.
- Cover at minimum: happy path, edge case (empty/zero/boundary), error path (invalid
  input), permission check (user without access gets rejected).
- Separate unit tests (no DB, no UI) from integration tests (multi-model or multi-user).
- Output file: `.odoo-ai/qa/<slug>-test-cases.md`

---

## Phase 2 — QA checklist (NL-dispatch to odoo-deploy-checklist)

Dispatch via NL: "Generate a pre-deployment QA checklist for <module> targeting Odoo
<version> in staging environment, covering all 8 domains: pre-flight, backup, data
migration, downtime, deploy mechanics, smoke tests, monitoring, and rollback."

The `odoo-deploy-checklist` leaf skill fills the 8-domain checklist and returns a
verdict (READY / NEEDS WORK / NOT READY). Write the returned checklist to
`.odoo-ai/qa/<slug>-deploy-checklist.md`.

Gate before dispatching: "approve / skip / cancel".

---

## Phase 3 — Bug triage (inline, or NL-dispatch to odoo-ui-debug for runtime issues)

If no open bugs were provided in Phase 0, skip this phase and note "No bugs to triage"
in the summary.

For each bug, produce a structured triage entry:

```
### Bug: <title>

**Severity:** Critical | High | Medium | Low
Severity rationale: <one sentence — business impact>

**Reproduction steps:**
1. <step>
2. <step>
...

**Expected:** <what should happen>
**Actual:** <what happens>

**Suspected module:** <odoo module name or "unknown">
**Suspected layer:** UI | Business logic | Data / ORM | Integration | Infrastructure
**Suggested next step:** <odoo-ui-debug for runtime inspection | odoo-coder for fix | escalate>
```

Severity rules (non-negotiable — never soften):
- **Critical**: data loss, financial integrity failure, security breach, system down.
- **High**: core business flow broken (sale, invoice, purchase) with no workaround.
- **Medium**: non-critical flow broken or degraded; workaround exists.
- **Low**: cosmetic, minor UX, or edge-case inconvenience.

If a bug requires live browser inspection to classify, NL-dispatch to `odoo-ui-debug`:
"Investigate the following runtime issue in Odoo <version> and return a root-cause
analysis with reproduction steps: <bug description>." Incorporate the returned
root-cause into the triage entry.

Output file: `.odoo-ai/qa/<slug>-bug-triage.md`

---

## Phase 4 — Summary (inline)

Write `.odoo-ai/qa/<slug>-qa-summary.md`:

```
# QA Summary — <feature/module> @ Odoo <version>

## Test suite
- Total cases: <N>  Unit: <N>  Integration: <N>
- Coverage areas: <list of business rules covered>

## Checklist verdict
<READY / NEEDS WORK / NOT READY> — <one-sentence reason>

## Bug triage
- Bugs triaged: <N>  Critical: <N>  High: <N>  Medium: <N>  Low: <N>
- Blockers (Critical + High): <list or "none">

## Suggested next skills
- `odoo-ui-debug` — for any Critical/High bugs requiring live runtime investigation
- `odoo-deploy-checklist` — run standalone for the full 8-domain gate if not done
- `odoo-coder` — for implementing fixes uncovered during triage
```

---

## Standalone-first fallback

When OSM is unreachable or no API key is configured:

1. **Phase 1 (test-case gen)**: fully inline — no MCP tools needed. Runs normally.
2. **Phase 2 (deploy checklist)**: dispatch `odoo-deploy-checklist` in standalone mode.
   The leaf skill marks OSM-dependent Domain 1 rows as `⚠ Manual check` automatically.
3. **Phase 3 (bug triage)**: inline triage runs normally; skip the `odoo-ui-debug`
   NL-dispatch for runtime inspection and note:
   `(OSM offline — runtime inspection via odoo-ui-debug requires reconnection)`

Add a notice at the top of the summary:
`> Note: QA suite ran in standalone mode. OSM-dependent checks marked ⚠ Manual check.`

The test-case generation and bug-triage phases are fully usable without OSM.
