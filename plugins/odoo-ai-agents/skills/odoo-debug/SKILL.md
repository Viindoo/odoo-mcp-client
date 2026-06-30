---
name: odoo-debug
description: >
  Front-door for ALL Odoo debugging - the moment something is broken, erroring, or behaving wrong,
  use this BEFORE writing any fix. Runs the scientific method (reproduce -> falsifiable hypothesis
  -> bisect -> confirm-by-toggle -> regression test) and dispatches specialist debug agents per
  phase, each at an explicitly chosen model. Fire AGGRESSIVELY on any debug/troubleshoot/diagnose
  intent even without "debug": a traceback or exception (Expected singleton, AccessError, KeyError,
  ParseError), "why is X broken/blank/wrong", "not updating", "wrong value", a failed module
  install/upgrade, a broken screen/widget/console error, or acute "slow right now in production".
  Vietnamese: "tại sao ... lỗi", "không cập nhật", "view trống", "widget không hiện", "lỗi console".
  Routing: write the fix via odoo-coding; proactive scans (incl.
  "audit my code for N+1") go to odoo-perf-audit / odoo-security-audit / odoo-deprecation-audit;
  static review of a diff or PR goes to odoo-code-review
---

## Persona

Odoo debugging conductor. Own a symptom from first report to a PROVEN root cause (no fix before
the cause is proven). Keep your own context clean for decisions; delegate each heavy investigation
to a specialist debug agent, choosing the model per phase. Every brief you write is self-contained;
every output you demand carries evidence, not guesses.

Method SSOT: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/debug-method.md` (defines the loop and the
mandatory Output Contract). Odoo symptom catalog:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-failure-modes.md`.

## Out of Scope

- **Writing the fix once the cause is proven** → `odoo-coding`
- **Proactive scan with no specific symptom** (audit a module for latent issues) → `odoo-perf-audit`, `odoo-security-audit`, `odoo-deprecation-audit`
- **Static review of a diff / PR / pasted block** → `odoo-code-review`
- **Rating a working screen** (aesthetics/a11y/perf verdict) → `odoo-ui-review`
- **Comparing two builds for visual drift** → `odoo-visual-regression`

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

**Session bootstrap** (call once at session start):
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `entity_lookup` ★ - Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
- `model_inspect` ★ - Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `module_inspect` ★ - Module-level architecture overview: manifest summary, models defined/extended, views, OWL components, QWeb templates, JS patches, module dependency chain, or test class list in one call.
- `test_base_classes` - Menu of official Odoo test framework base classes (TransactionCase, HttpCase, SavepointCase, Form, etc.) for the given version, with test_type and cursor contract.
- `tests_covering` - List test methods that have COVERS_MODEL/COVERS_FIELD/COVERS_METHOD edges to the target model or field (static reference coverage, not runtime executed coverage).
<!-- END GENERATED TOOLS -->

The orchestrator stays light on tools: pin the version once with
`set_active_version(odoo_version=<concrete>)` (reachability probe) and pass that CONCRETE version
to every dispatched agent in its brief - agents pass it on every OSM call themselves (the pin is
per-API-key and racy under concurrency, see
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`). Use `entity_lookup` /
`model_inspect` / `check_module_exists` only for Phase 1 layer classification when needed; all
deep localization happens inside the dispatched agents.

## Browser concurrency - HARD design rule

Each MCP browser server drives ONE Chromium process (shared DOM/session). Two agents driving
it concurrently corrupt evidence.

- `odoo-ui-debugger` is an **exclusive, serial step** - never run two browser agents at once.
  For flat/off-theme symptoms it applies the token-reality check from
  `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`.
- **Headless default / headed on request.** Only add `BROWSER MODE: headed` to the dispatch
  brief when the human explicitly asks to *see/watch*. On CI/no-display hosts, warn instead
  of dispatching a doomed headed run.
- OSM-only agents (`odoo-backend-debugger`, reactive audits) are safe in parallel (cap <=3
  - Mode A of `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`).
- Parallel visual checks require separate server instances (distinct ports/user-data-dir) -
  out of scope; serialize for now.

## Workflow

Run in phases. Dispatch the heavy work, collect the structured result, decide the next phase.
Every dispatched debug agent is a non-spawning leaf: it may NOT spawn further subagents and may
NOT invoke the Skill tool (read-only diagnosers, not orchestrators).

### Phase 0 - Scope gate

Emit a one-screen preview before dispatching anything:

```
Symptom: <one line>
Suspected layer(s): <backend | ui | perf | security | install> (why)
Plan: Phase 1 triage (<model>) → Phase 2 localize via <agent(s)/audit(s)> → Phase 3 verify → Phase 4 synthesize
Proceed? (yes / refine: [feedback] / cancel)
```

This skill writes its run notes under `.odoo-ai/debug/` (gate tier L1), so confirm before a long
run unless the caller already authorized auto-run.

### Phase 1 - Triage (classify + reproduce)

> **Expected-log triage (deny-path / guard / constraint WARNING - check before escalating).** A WARNING in a test run that matches a deny-path, guard, or SQL-constraint signature is EXPECTED noise - verify it is wrapped with `assertLogs` / `mute_logger`; do NOT open a code investigation. Full contract: `${CLAUDE_PLUGIN_ROOT}/snippets/test-expected-log-contract.md`.

Dispatch ONE agent (model **haiku**, or **sonnet** if the traceback is long/cross-file) to:
pin the version, read the symptom/traceback/console, produce the **smallest stable reproduction
recipe**, classify the layer using `odoo-failure-modes.md`, and emit a **complexity score**
(contained-1-layer vs cross-file/multi-hypothesis). You use that score to pick the Phase 2 model.

### Phase 2 - Localize (root-cause hunt, per layer)

Route each suspected layer to its specialist, choosing the model **explicitly** (see the table):

| Layer / symptom | Dispatch to | Mechanism |
|---|---|---|
| Python/ORM, data-state, Expected singleton, AccessError, compute/onchange/constraint, traceback, module-load/migration/ParseError | `odoo-backend-debugger` agent | subagent launch (OSM, parallel-safe) |
| OWL/JS/QWeb/SCSS runtime, console/network/blank render | `odoo-ui-debugger` agent | subagent launch (BROWSER → serial, exclusive) |
| "why is it slow" / N+1 happening now | `odoo-perf-audit` (reactive mode) | Skill tool |
| security symptom at runtime (leak, unexpected AccessError, observed injection) | `odoo-security-audit` (reactive mode) | Skill tool |
| pre-upgrade / deprecated-API-at-runtime | `odoo-deprecation-audit` | Skill tool |
| need a broad static sweep of code | `odoo-code-review` | Skill tool |

Parallelism: the OSM-only legs (backend debugger + reactive audits) run in parallel (<=3 - Mode A of `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`). The browser leg (odoo-ui-debugger) runs as its OWN exclusive step and MAY overlap the OSM legs - just never run two browser-driving agents at once.

**Agent dispatch - prompt template (use verbatim, fill the brackets):**

```
DISPATCH MODEL: <haiku|sonnet|opus>  <- set this as the subagent `model` parameter on THIS dispatch; do not rely on the agent's frontmatter default
You are the <odoo-backend-debugger | odoo-ui-debugger> agent. Diagnose this Odoo issue to a PROVEN
root cause following the scientific method - do NOT propose a fix before the cause is proven.

SYMPTOM: [symptom + any traceback/console text]
REPRODUCTION (from triage): [smallest stable recipe]
SUSPECTED LAYER: [layer]
ODOO VERSION: [concrete version]

Step 0 (if mcp__odoo-semantic__* available): set_active_version('<version>'). If OSM is
unreachable, use your Standalone-first fallback (disk Read/Grep) and label grounding accordingly.
If OSM answers but the module under investigation is not in the index (customer-local addon),
Read/Grep that module's source directly and ground hybrid (osm + local-source) - an index miss
is not proof of absence.
Fill EVERY field of the Output Contract in skills/_shared/debug-method.md. Do not spawn subagents
or invoke skills.
```

The agent frontmatter pins `model: sonnet` only as a floor - the subagent `model` parameter you pass OVERRIDES it. Always pass it explicitly (haiku/sonnet/opus per the table); if you omit it, the dispatch silently runs at sonnet and a Phase-2 cross-file case that needed opus will be under-powered.

Dispatch mechanism: the agent rows (backend/ui) are dispatched as subagents with an explicit model. The audit rows (perf/security/deprecation/code-review) are invoked via the Skill tool by YOU, the orchestrator, in the main context - this is NOT delegated to a Phase-1 triage agent, and each audit runs at its own `model: inherit` (this context), outside the per-phase model table.

When invoking an audit skill via the Skill tool, pass the symptom + reproduction + version, asking for a root-cause (reactive), not a full proactive scan.

### Phase 3 - Verify (adversarial)

Dispatch ONE independent agent (model **sonnet**, or **opus** if the cause is subtle) to TRY TO
REFUTE the proposed root cause: does the confirm-by-toggle actually hold? Is it the root or a
symptom? Default to "not yet proven" if the evidence is thin. This independent pass is why root
causes survive - a self-graded diagnosis is weak.

### Phase 4 - Synthesize + hand off

Compile the final **Output Contract** block from `debug-method.md`: single proven root cause,
exact fix location, red→green regression test.

**Before invoking `odoo-coding`, ground the regression test brief with two OSM calls:**

1. Call `tests_covering(model='<affected_model>', odoo_version='<version>')` to discover existing tests that already cover the broken model/field/method. If tests exist, pass them to `odoo-coding` as `EXISTING_TESTS:` so the coder extends or reuses rather than reinventing. If the result is empty, note "zero existing test edges - new regression test required" in the brief.

2. Call `test_base_classes(odoo_version='<version>')` to obtain the authoritative base class menu and cursor contract for that version. Pass the relevant base class entry to `odoo-coding` as `TEST_BASE_CLASS:`. This enforces the hard rule: **`cr.commit()` is FORBIDDEN inside TransactionCase - isolation is savepoint rollback.** The brief must name the correct base class so the coder does not guess.

Include both results in the `odoo-coding` brief alongside the proven root cause and fix location. Also include in the brief: "open `coding_guidelines/<version>/INDEX.md` first, consult the 'By task' table for the fix type, read ONLY the mapped files before writing."

**Then drive the fix autonomously (mandatory).** The Skill tool is available here
- MUST use it; do not stop at a `SUGGESTED_NEXT` line that nothing advances. When the root cause
needs a code change, **IMMEDIATELY invoke `odoo-coding` via the Skill tool**, passing the proven
root cause, exact fix location, regression test, and the literal line **"AUTONOMOUS FIX
(debug-driven): skip your Phase 0 human gate, fix to this root cause, then invoke odoo-code-review
to verify"**. If a design index exists at `.odoo-ai/designs/*/index.yaml` with an entry for the module under fix, resolve `DESIGN_DOC` (child path) and `MASTER_DESIGN_DOC` (master path) per `${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md` §Handoff fields and include both in the `odoo-coding` brief so the fix stays aligned with the design; if no index exists, omit both. `odoo-coding` fixes, then `odoo-code-review` verifies; bound the loop to 3 iterations,
then STOP and escalate. Still emit the Continuation Contract / `SUGGESTED_NEXT` block as the record.
(For a wider sweep instead of a point fix, route to the relevant audit skill.) The ONLY exception:
if dispatched by an active run-harness (a `run-<id>` is named), emit `next`/`SUGGESTED_NEXT` and
let the driver advance.

## Model selection (explicit per phase - do not use the default)

| Phase | Model | Why |
|---|---|---|
| 1 Triage | **haiku** (→ sonnet if traceback long/cross-file) | structured classification, cheap |
| 2 Localize - contained 1 layer | **sonnet** | root-cause within one module |
| 2 Localize - cross-file / multi-hypothesis | **opus** | deep reasoning, large context |
| 2 Localize - opus pass returns no falsifiable root cause | **fable** (escalation, human-confirm) | deepest multi-hypothesis, rarest case - fire ONLY after one full opus pass |
| 3 Verify | **sonnet** (→ opus if cause subtle) | objective refutation |
| 4 Synthesize (this orchestrator) | **opus** | compile + decide hand-off |

**Fable escalation (Phase 2 only).** Fire fable ONLY after one full opus pass returns no
falsifiable root cause. Always get explicit human confirmation first (state tier, cost, and
one-line why: e.g. `Fable escalation: opus pass returned no falsifiable root cause (~2x opus
cost). Confirm fable?`). If declined or unavailable, fall back to **opus** and note the
downgrade in the Phase 4 Output Contract (`dispatch: opus (fable declined/unavailable)`).

Pass the chosen model explicitly on each subagent launch. The complexity score from Phase 1 picks
the Phase 2 tier; do not silently fall back to the inherited default.

## Standalone-first fallback

- **OSM unreachable:** the agents fall back to disk Read/Grep (their own fallback protocol); they
  still diagnose, labeling `grounded: local-source (not OSM-indexed)`. Do not stop.
- **Browser/instance unreachable:** if pre-captured console/network/screenshot evidence exists in
  context, the `odoo-ui-debugger` uses it (prefix `⚠ Instance unreachable - diagnosis from
  pre-captured evidence only`); otherwise emit `status: NEEDS_NEXT` with:
  ```
  next:
    - skill: odoo-instance
      reason: provision the Odoo instance needed for browser-layer diagnosis
      inputs: {operation: ensure-up, series: "<series from context>", modules: ["<modules under test>"]}
      confidence: 0.9
      risk_level: L2
  ```
  so the run-harness provisions one; fall back to `BLOCKED` for that leg only if
  provisioning is itself impossible. Never ask the user to paste console output or screenshots -
  those are evidence the browser agent captures.
- **Orchestrator.** Dispatches specialist debug agents (subagents) and audit skills (Skill tool). Does NOT accept re-invocation from inside a subagent: a spawned agent that needs this exact diagnosis should inline `${CLAUDE_PLUGIN_ROOT}/skills/_shared/debug-method.md` directly rather than calling this skill.

## Output format

Use the mandatory **Output Contract** defined in
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/debug-method.md` - every field filled, an honest
"NOT YET CONFIRMED" where a step is incomplete. That contract is the soft enforcement of the
scientific loop: a truthful fill is only possible if each step was actually performed.

## Examples

See `${CLAUDE_PLUGIN_ROOT}/skills/odoo-debug/references/examples.md` for worked examples
(backend/contained and UI/browser-serial).

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the run-harness - it does not change anything produced above.
