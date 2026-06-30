---
name: odoo-deep-survey
argument-hint: "[scope/codebase path]"
description: >-
  Multi-phase opt-in deep survey of an Odoo codebase or scope for the EXECUTE-AGENT
  consumer: a broad haiku sweep, then narrow sonnet dives, then an optional opus pass,
  writing reusable findings to .odoo-ai/survey/ that later phases cite. Invoked ONLY by
  odoo-intake AFTER the user explicitly approves a deep survey via the `deep-survey`
  gate keyword - it is NOT a front door and NEVER auto-triggers on a bare prompt. DO NOT
  trigger when: the user has not opted into a deep survey; the intent is a single-file or
  single-symbol lookup that Phase R recon already covers; it must be invoked via the Skill
  tool from the main context (not from inside a subagent). It is read-only - discovering
  scope, ranking hot-spots against the stated intent, mapping bidirectional impact, and
  handing a synthesis back to odoo-intake to re-propose a sharper plan
model: opus
---

# Odoo Deep Survey - broad→narrow→deep, then synthesize

Consumer: the **next execute AI agent** (architect, coder, reviewer) - not a human. Every
finding must be actionable without re-derivation: a `file:line` pointer or OSM citation, marked
`RESOLVED` or `UNRESOLVED`, written so a downstream agent reads few tokens and understands at once.

## Persona

Read-only reconnaissance orchestrator. Loaded by the **Skill tool** from the main context, it
fans out anonymous worker agents to map "can the codebase actually meet this intent, and where
does the work land?" - at three escalating tiers of cost and depth. Writes analysis artifacts
under `.odoo-ai/survey/`; never writes Odoo source.

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

1. **Main-context spawner.** This skill launches subagents; it MUST be invoked via the Skill
   tool from the main context. A subagent MUST NOT invoke this skill - doing so creates
   uncontrolled nesting.
2. **Read-only.** Workers read Odoo source and call read-only OSM tools. The ONLY writes are this
   skill's own analysis artifacts under `.odoo-ai/survey/` and worklog entries under
   `.odoo-ai/worklog/`. No edits to Odoo source, no routed deliverable.
3. **Every claim is grounded.** A finding without a `file:line` or an OSM citation is a guess -
   drop it or mark it `UNRESOLVED`. The worklog `EVIDENCE` field is mandatory
   (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`).
4. **Escalate by evidence, not by vibe.** Phase 3 (opus) runs only when a measurable trigger fires
   (see § Phase 3). Default is to stop after Phase 2 and synthesize - opus is the expensive tier.

## Fan-out budget

Workers are launched as subagents, one per scope unit, using CHP Tier-B `subagent_type: "fork"`
(see `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` - Tier B). A fork worker
inherits the parent's full context (intent decomposition, survey slug, Odoo version pin, the
full lens block text, OSM grounding instructions) and shares the parent's prompt cache - this
eliminates per-worker re-passing of the lens block and OSM bootstrap, which is the dominant
per-worker cost across all three phases. Model varies by phase (haiku / sonnet / opus); no
custom agentType beyond the fork. Each fork still writes its OWN findings file; forks never
share mutable state.
Fallback (Tier C): if `subagent_type: "fork"` is unavailable in the current runtime, dispatch a
fresh `general-purpose` spawn with an explicit brief per the current behavior. Tier C is always
correct; the worklog is always written regardless of tier.

Concurrency follows **Mode B (model-weighted budget)** in
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` - SSOT for the weight table and
in-flight cap. Do **not** restate the weights here. When scope exceeds the budget, use a rolling
concurrency window (dispatch up to the budget, drain, dispatch the next).

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
- **Two Phase-1 lenses** (`references/survey-lenses.md` § Phase 1): **L1 module purpose**
  (`describe_module` - 1-2 lines, downgrades a hot-spot in an off-intent module) and **L2
  entry-point map** (`ir.actions` / controllers / `ir.cron` / view buttons / `execute_kw`-reachable
  `@api.model` methods, each `file:line` -> dispatched model/route) as a first-class artifact.
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

  On top of the trace, each worker applies the **Phase-2 lenses** in
  `references/survey-lenses.md` (the orchestrator inlines the full lens block into the brief),
  recording each as a labelled subsection: **L3 data-flow**, **L4 layer labels** (`[LAYER: ...]`),
  **L5 side-effects**, **L6 cross-cutting** (FLAG existence only, no overlap with
  `odoo-security-audit`), **L7 prior art** (existing override/pattern/test the downstream agent
  ADAPTS instead of reinventing; a MISS is a recorded result), and **L8 tech-debt** (FLAG-only,
  never fix). Full lens definitions + per-lens OSM tools: `references/survey-lenses.md`.

  Each worker also runs the **dependency-closure drill** (`references/survey-lenses.md` §
  Dependency-closure): walk the hot-spot's `depends` graph DOWN from the nearest owner toward
  `base`, PHASED one layer per wave (respect the Mode B budget), and ground each external symbol by
  REUSING `${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md` § 2 + § 2.5 BY PATH (the
  orchestrator inlines those two sections into the brief - never copy them). Output a
  dependency-closure map (`nearest -> ... -> base`, layer + why + `grounded:`). Ground at the
  current version; if the intent is upgrade-adjacent, ground at the target version so the drill
  doubles as a pre-upgrade symbol check.

  After `impact_analysis` resolves the blast radius, each worker also calls `tests_covering` for
  the hot-spot's primary model to determine the **test blast radius**: which existing tests
  already guard this behavior, and therefore which tests would be at risk if the hot-spot
  changes. Prefer model-level or field-level narrow over method-level; COVERS_METHOD edges are
  sparse and frequently return 0 even for well-tested methods - 0 results at method-narrow does
  NOT mean the method is untested. Example (concrete version required):

  ```python
  tests_covering(model='account.move', field='state', odoo_version='17.0')
  ```

  If `tests_covering` returns 0 edges for a method of interest, fall back to
  `find_test_examples(query='<method_name>', odoo_version='17.0')` before concluding zero
  coverage. Record the result in the worker's phase2 file as a "Test blast radius" subsection:
  number of test edges, test file paths, and whether the hot-spot has zero test coverage (a
  coverage gap confirmed by BOTH tools). Zero-coverage hot-spots are escalation candidates for
  Phase 3 (trigger: § Phase 3 item 3). This call populates tiers (i) own-module and (ii)
  dependency tests of the **test-protection map** (`references/survey-lenses.md` § Test-protection
  map); tier (iii) framework-validation + lint gates (`base.TestInvisibleField`,
  `hr.TestSelfAccessProfile`, `test_pylint`, `test_lint`) is assembled at synthesis. All three feed
  the synthesis `tests_protecting` section.

- **Persist:** `.odoo-ai/survey/<slug>-<date>/phase2/<NN>-<hotspot>.md` + worklog entries.

## Phase 3 - opus escalation (conditional)

Run a Phase 3 opus pass **only if** at least one measurable trigger holds (else SKIP straight to
synthesis - opus is the costly tier, 2 in-flight max under Mode B):

1. **Conflict** - two or more Phase-2 reports disagree on one load-bearing fact (e.g. which module
   owns the hook).
2. **Cross-cutting unresolved** - a hot-spot's `impact_analysis` shows >=3 modules depending on it
   transitively that no worker fully traced, OR the Phase-2 dependency-closure drill left a branch
   >=3 layers deep ungrounded to `base` (the closure exceeded one worker's wave budget).
3. **Coverage gap** - an intent sub-question is still marked `UNRESOLVED` in the worklog after
   Phase 2.

Each opus worker takes one such unresolved knot and resolves it with cross-file reasoning over the
Phase-1/2 artifacts + OSM. **Persist:** `.odoo-ai/survey/<slug>-<date>/phase3/<NN>-<knot>.md` +
worklog.

## Worker brief - what every dispatched worker must carry

A worker is a leaf subagent that **cannot resolve `${CLAUDE_PLUGIN_ROOT}` itself** - the
orchestrator must **read referenced snippets and paste their content into the brief**.

1. **Worker brief** - inline full text of `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`
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
7. **Lens block** - inline the phase-relevant lens text from
   `${CLAUDE_PLUGIN_ROOT}/skills/odoo-deep-survey/references/survey-lenses.md` (Phase 1 lenses for
   haiku; Phase 2 lenses + the dependency-closure drill for sonnet). For a worker that runs the
   dependency-closure drill, ALSO inline `${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md`
   § 2 + § 2.5. A leaf cannot resolve these paths - paste, do not cite-by-path-only.

## Synthesis + hand back to intake

After the last phase, read every `phase*/*.md` + the worklog (oldest-first), aggregate the lens
subsections (do NOT re-survey), and write `.odoo-ai/survey/<slug>-<date>/synthesis.md` to the full
contract in `references/synthesis-schema.md`. Each section is few-token, agent-readable, and
carries `grounded: osm | hybrid | local-source`. Sections:

- **scope_covered**, **key_findings** (`file:line` + OSM), **hot_spots_ranked** - as before.
- **entry_points** (L2), **dependency_closure** (`nearest -> base`), **data_flow** (`A -> B -> X`
  + `[LAYER: ...]`), **prior_art** ("read BEFORE coding - do not reinvent"), **side_effects**,
  **tech_debt** (flag-only), **cross_cutting** (flag-only) - aggregated from the Phase-2 lenses.
- **tests_protecting** - the three-tier test-protection map (own-module / dependency / framework
  gates). It SUBSUMES the old "test coverage gaps" bullet: a zero-coverage hot-spot is a flagged
  row. Build tier (i)+(ii) by calling `test_coverage_audit` once per surveyed module:

  ```python
  test_coverage_audit(module='sale_management', odoo_version='17.0')
  ```

  Tier (iii) framework gates are `grounded: local-source` (OSM does not index them) - list them
  from the runbot-parity-checklist cross-ref in `references/survey-lenses.md`, each "verify live".
- **essential_reading** - 5-10 files MAX to UNDERSTAND the scope (distinct from files-to-change),
  each + one-line "why" + `file:line`.
- **open_questions** (`UNRESOLVED`), **recommended_approach_delta**, and **upgrade_symbol_gaps**
  (optional, upgrade-adjacent intent only - non-SURVIVED symbols from the closure drill).

Return to intake: the path to `synthesis.md` plus 3-5 bullets naming what changed versus the first
plan. Intake fills the `Survey:` field with that path and **re-proposes** the plan; downstream
skills read `synthesis.md` (and the worklog) to inherit this survey instead of re-deriving it.

## OSM grounding

Always pass a **concrete** Odoo version on every OSM call; `'auto'` is unsafe under fan-out
(version pin is server-state shared across concurrent workers -
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § OSM version-pin race). Call
`set_active_version` once as the reachability probe, then pass the explicit version per call.

**OSM-first, by principle.** OSM is the PRIMARY source (indexed, cross-version,
inheritance-resolved, checkout-free); read raw Odoo source only when OSM is silent on a fact, and
then label the finding `grounded: local-source`. Reach for the tool whose PURPOSE fits the
question - never hardcode params beyond the mandatory concrete `odoo_version`:

- module shape / purpose / deps: `describe_module`, `module_inspect`, `check_module_exists`,
  `validate_depends`
- model / symbol structure: `model_inspect`, `entity_lookup`, `resolve_orm_chain`
- override + blast radius: `find_override_point`, `impact_analysis`
- prior art + recommended approach: `find_examples`, `suggest_pattern`
- tests guarding the scope: `find_test_examples`, `tests_covering`, `test_coverage_audit`
- version-aware (upgrade-adjacent intent): `api_version_diff`, `find_deprecated_usage`

Every finding carries one grounding label - `grounded: osm | hybrid | local-source` (defined in
`references/synthesis-schema.md`).

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
- **NEVER spawn from workers.** Workers are leaves; they do not invoke the Skill tool or
  spawn sub-agents (see worker-brief).
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
