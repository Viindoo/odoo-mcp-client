---
name: odoo-deep-survey
description: >-
  Multi-phase opt-in deep survey of an Odoo codebase or scope for the EXECUTE-AGENT
  consumer: a broad haiku sweep, then narrow sonnet dives, then an optional opus pass,
  writing reusable findings to .odoo-ai/survey/ that later phases cite. Invoked ONLY by
  odoo-intake AFTER the user explicitly approves a deep survey via the `deep-survey`
  gate keyword - it is NOT a front door and NEVER auto-triggers on a bare prompt. DO NOT
  trigger when: the user has not opted into a deep survey; the intent is a single-file or
  single-symbol lookup that Phase R recon already covers; you run at depth>=1 (a subagent
  must never invoke this depth-0 spawner). It is read-only - discovering scope, ranking
  hot-spots against the stated intent, mapping bidirectional impact, and handing a
  synthesis back to odoo-intake to re-propose a sharper plan
model: opus
---

# Odoo Deep Survey - broad→narrow→deep, then synthesize

Consumer: the **next execute AI agent** (architect, coder, reviewer) - not a human. Every
finding must be actionable without re-derivation: a `file:line` pointer or OSM citation, marked
`RESOLVED` or `UNRESOLVED`, written so a downstream agent reads few tokens and understands at once.

## Persona

Read-only reconnaissance orchestrator. Runs at depth-0 (loaded by the **Skill tool** from the
main context) and fans out anonymous worker agents to map "can the codebase actually meet this
intent, and where does the work land?" - at three escalating tiers of cost and depth. Writes
analysis artifacts under `.odoo-ai/survey/`; never writes Odoo source.

## When this runs (opt-in only)

`odoo-intake` emits a Proposed Plan from a light Phase R recon, then offers a deep survey. The
**user** types `deep-survey`. ONLY THEN does intake invoke this skill via the Skill tool. This is
the human gate - this skill produces no routed deliverable, only analysis that re-informs the
plan. It is heavy (many subagents, real tokens), which is why it is opt-in and never automatic.

## Inputs (passed by intake in the invocation)

- **Intent / purpose / expected outcomes** - the closed Phase 0 gate (what / why / done-looks-like).
- **Odoo version + profile** - from `.odoo-ai/context.md` or the intake version gate. Pin this
  concrete version on every OSM call (see § OSM grounding).
- **The first Proposed Plan** - so synthesis can express its findings as a *delta* against it.
- **Slug** - reuse the feature slug intake already uses for brainstorm artifacts; the survey dir
  is `.odoo-ai/survey/<slug>-<date>/`.

## Hard rules

1. **Depth-0 only.** This skill spawns workers (depth 0→1); it MUST run in the main context. If
   you detect depth>=1, decline - a subagent dispatching this spawner would breach the depth-2
   ceiling.
2. **Read-only.** Workers read Odoo source and call read-only OSM tools. The ONLY writes are this
   skill's own analysis artifacts under `.odoo-ai/survey/` and worklog entries under
   `.odoo-ai/worklog/`. No edits to Odoo source, no routed deliverable.
3. **Every claim is grounded.** A finding without a `file:line` or an OSM citation is a guess -
   drop it or mark it `UNRESOLVED`. The worklog `EVIDENCE` field is mandatory
   (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`).
4. **Escalate by evidence, not by vibe.** Phase 3 (opus) runs only when a measurable trigger fires
   (see § Phase 3). Default is to stop after Phase 2 and synthesize - opus is the expensive tier.

## Fan-out budget

Workers are dispatched via the **Agent tool**, one per scope unit, `general-purpose` type, model
set per phase (haiku / sonnet / opus). No custom agentType; model alone varies by phase
(`docs/reference/workflow-harness.md` §8.5).

Concurrency follows **Mode B (model-weighted budget)** in
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` - SSOT for the weight table and
in-flight cap. Do **not** restate the weights here. When scope exceeds the budget, use a rolling
window (dispatch up to the budget, drain, dispatch the next) exactly as `wave` does.

## Bootstrap - decompose the intent (before Phase 1)

Before any fan-out, break the stated intent into explicit **sub-questions** the survey must
answer (e.g. "where is the discount applied?", "does any report read this field?"). Seed each as
an `UNRESOLVED` worklog entry (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md` format).
Workers flip sub-questions to `RESOLVED`; anything still `UNRESOLVED` after Phase 2 IS the
Phase-3 coverage-gap trigger - without seeding, that trigger never fires.

## Phase 1 - broad / shallow sweep (haiku)

**Goal:** a fast, wide map of every candidate area. Cheap and parallel.

- **Scope unit** = one top-level custom module (enumerate via `find . -name __manifest__.py`, or
  the module list in `.odoo-ai/context.md`). For a non-code intent, the unit is one persona-domain
  area implied by the intent.
- **Fan-out:** one haiku worker per unit, filling the Mode B budget (rolling-window beyond it).
- **Each worker** (haiku = read-only lookup/classify only, never multi-tool OSM synthesis):
  reads the module's manifest + skims its models/views, and confirms existence with read-only OSM
  - `check_module_exists`, `module_inspect` (`method='summary'`), and
  `module_inspect` (`method='tests'`) to enumerate the test classes defined in the module. The test
  class list from Phase 1 seeds the Phase 2 test blast-radius picture: workers record which
  `TestCase` subclasses exist so the synthesiser knows where to look for coverage edges.
  Each worker returns a short bullet map: what the area contains, which 1-3 spots look most
  relevant to the stated intent (the hot-spots) each with a `file:line`, and the module's test
  class list (or "no tests" if the module has none).
- **Persist:** `.odoo-ai/survey/<slug>-<date>/phase1/<NN>-<area>.md` + one worklog entry per worker.

## Phase 2 - narrow / deep dives (sonnet)

**Goal:** understand the hot-spots that actually bear on the intent - fewer targets, real depth.

- **Scope** = the Phase-1 hot-spots ranked most-relevant to the intent (narrow the field; ignore
  areas Phase 1 marked irrelevant).
- **Fan-out:** one sonnet worker per hot-spot, within the Mode B budget.
- **Each worker** (sonnet = multi-tool OSM synthesis allowed): traces the hot-spot with
  `model_inspect` (fields/methods), `find_override_point`, `resolve_orm_chain`, and maps
  **bidirectional impact** per `${CLAUDE_PLUGIN_ROOT}/snippets/bidirectional-impact.md` (upstream
  `depends` closure + downstream `impact_analysis`, direct AND transitive). It answers the
  intent's sub-questions and marks each `RESOLVED` / `UNRESOLVED`.

  After `impact_analysis` resolves the blast radius, each worker also calls `tests_covering` for
  the hot-spot's primary model and method to determine the **test blast radius**: which existing
  tests already guard this behavior, and therefore which tests would be at risk if the hot-spot
  changes. Example (concrete version required):

  ```python
  tests_covering(model='account.move', method='_post', odoo_version='17.0')
  ```

  Record the result in the worker's phase2 file as a "Test blast radius" subsection: number of
  test edges, test file paths, and whether the hot-spot has zero test coverage (a coverage gap).
  Zero-coverage hot-spots are escalation candidates for Phase 3 (trigger: § Phase 3 item 3) and
  are always surfaced in the synthesis "Test coverage gaps" section.

- **Persist:** `.odoo-ai/survey/<slug>-<date>/phase2/<NN>-<hotspot>.md` + worklog entries.

## Phase 3 - opus escalation (conditional)

Run a Phase 3 opus pass **only if** at least one measurable trigger holds (else SKIP straight to
synthesis - opus is the costly tier, 2 in-flight max under Mode B):

1. **Conflict** - two or more Phase-2 reports disagree on one load-bearing fact (e.g. which module
   owns the hook).
2. **Cross-cutting unresolved** - a hot-spot's `impact_analysis` shows >=3 modules depending on it
   transitively that no worker fully traced.
3. **Coverage gap** - an intent sub-question is still marked `UNRESOLVED` in the worklog after
   Phase 2.

Each opus worker takes one such unresolved knot and resolves it with cross-file reasoning over the
Phase-1/2 artifacts + OSM. **Persist:** `.odoo-ai/survey/<slug>-<date>/phase3/<NN>-<knot>.md` +
worklog.

## Worker brief - what every dispatched worker must carry

A worker is a depth-1 subagent that **cannot resolve `${CLAUDE_PLUGIN_ROOT}` itself** - the
orchestrator must **read referenced snippets and paste their content into the brief**.

1. **Nesting guard** - inline full text of `${CLAUDE_PLUGIN_ROOT}/snippets/nesting-guard.md`
   (leaf: no Skill tool, no sub-agent spawn; read-only on Odoo source; only Write is own findings
   file; OSM calls are always allowed).
2. **Scope, hard** - the one module / hot-spot / knot, with explicit files in scope.
3. **Consumer lens** - "survey FOR a later execute agent: cite `file:line` + OSM call, never
   guess, mark every answer `RESOLVED` / `UNRESOLVED`".
4. **OSM version pin** - concrete `odoo_version` on every call (never `'auto'`; see § OSM
   grounding).
5. **Output contract** - write findings to the exact phase path (orchestrator fills the `<NN>`
   prefix so files sort in dispatch sequence); append one worklog entry per decision in the
   inlined `worklog-contract.md` format.
6. **Tier + why** - haiku (wide/shallow), sonnet (deep), or opus (cross-file knot).

## Synthesis + hand back to intake

After the last phase, read every `phase*/*.md` + the worklog (oldest-first) and write
`.odoo-ai/survey/<slug>-<date>/synthesis.md`:

- **Scope covered** - areas surveyed, tier per area.
- **Key findings** - each with `file:line` + OSM citation.
- **Hot-spots ranked** by relevance to the intent.
- **Impact map** - bidirectional blast radius of the likely change.
- **Test coverage gaps** - hot-spots with zero test coverage from `tests_covering` (Phase 2
  blast-radius calls) and fields/methods flagged by `test_coverage_audit`. To build this section,
  call `test_coverage_audit` once per surveyed module before writing synthesis:

  ```python
  test_coverage_audit(module='sale_management', odoo_version='17.0')
  ```

  List uncovered fields and methods that overlap with the Phase-2 hot-spots, marked with urgency:
  a hot-spot with zero coverage is a risk multiplier for any change in that area.
- **Open questions** - anything still `UNRESOLVED` (so intake can flag it honestly).
- **Recommended approach delta** - how the first Proposed Plan should change given what was found.

Return to intake: the path to `synthesis.md` plus 3-5 bullets naming what changed versus the first
plan. Intake fills the `Survey:` field with that path and **re-proposes** the plan; downstream
skills read `synthesis.md` (and the worklog) to inherit this survey instead of re-deriving it.

## OSM grounding

Always pass a **concrete** Odoo version on every OSM call; `'auto'` is unsafe under fan-out
(version pin is server-state shared across concurrent workers -
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § OSM version-pin race). Call
`set_active_version` once as the reachability probe, then pass the explicit version per call.

## Artifacts & resume

```
.odoo-ai/survey/<slug>-<date>/
  state.json        # {slug, intent, phase_done: [...], next: <phase|synthesis>}
  phase1/<NN>-<area>.md
  phase2/<NN>-<hotspot>.md
  phase3/<NN>-<knot>.md      # only if escalated
  synthesis.md
```

If the run is interrupted, a re-invocation with the same slug reads `state.json` + the existing
`phase*/` files, skips completed phases, and resumes at `next` (file-existence is the source of
truth; `state.json` is the fast index).

## Out of Scope

- **NEVER write Odoo source or the routed deliverable.** Analysis artifacts under `.odoo-ai/` only.
- **NEVER auto-trigger.** This skill exists to be invoked by `odoo-intake` after the `deep-survey`
  opt-in. It is not a front door and does not classify intent - that is `odoo-intake`'s job.
- **NEVER spawn deeper than depth-1.** Workers are leaves; they do not invoke the Skill tool or
  spawn sub-agents (nesting guard).
- **NEVER escalate to opus without a measurable trigger** (§ Phase 3). Default is stop-and-synthesize.

## Standalone-first fallback

The survey prefers OSM but does not require it. If OSM is unreachable (a `set_active_version` probe
fails), workers fall back to **read-only disk** - reading each `__manifest__.py` `depends` and
skimming `models/` and `static/src` for the dependency and asset picture - and the synthesis
records `OSM: standalone` so intake states plainly that the impact map is disk-derived, not
graph-resolved. No OSM is forced on any later specialist in this path.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). `produced`
includes `synthesis.md`; `next` hands control back to `odoo-intake` to re-propose the plan.
