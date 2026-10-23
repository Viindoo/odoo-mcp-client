---
name: odoo-deep-survey
argument-hint: "[scope/codebase path]"
description: >-
  Deep codebase survey; only odoo-intake runs it, on user opt-in
model: sonnet
---

# Odoo Deep Survey - broad→narrow→deep, then synthesize

Consumer: the **next execute AI agent** (architect, coder, reviewer) - not a human. Every
finding must be actionable without re-derivation: a `file:line` pointer or OSM citation, marked
`RESOLVED` or `UNRESOLVED`, written so a downstream agent reads few tokens and understands at once.

## Role

Read-only reconnaissance orchestrator. Loaded by the **Skill tool** from the main context, it
fans out anonymous worker agents at three escalating tiers to map whether the codebase can meet
the intent and where the work lands. Writes analysis artifacts
under `<SHARE_DIR>/survey/` (resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path -
never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit); never writes Odoo source.

## When this runs (opt-in only)

`odoo-intake` asks its approach question from a light Phase R recon and offers a deep survey. The
**user** replies `refine: deep-survey` - the PLAN reply set
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md`); `deep-survey` is the feedback, not a
reply word of its own. ONLY THEN does intake invoke this skill via the Skill tool. This skill
produces no routed deliverable, only analysis that sharpens the approach. Never run it
automatically.

## Inputs (passed by intake in the invocation)

- **Intent / purpose / expected outcomes** - the closed Phase 0 gate (what / why / done-looks-like).
- **Odoo series + profile** - from the intake version gate, else resolved per
  `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`. Pin this
  concrete series on every OSM call (see § OSM grounding).
- **The recommended approach** - so synthesis can express its findings as a *delta* against it.
- **Slug** - reuse the feature slug intake already uses for brainstorm artifacts; the survey dir
  is `<SHARE_DIR>/survey/<slug>-<date>/`.

## Hard rules

1. **Main-context spawner.** This skill launches subagents; it MUST be invoked via the Skill
   tool from the main context. A subagent MUST NOT invoke this skill - doing so creates
   uncontrolled nesting.
2. **Read-only.** Workers read Odoo source and call read-only OSM tools. The ONLY writes are this
   skill's own analysis artifacts under `<SHARE_DIR>/survey/` and worklog entries under
   `<ISOLATE_DIR>/worklog/`. No edits to Odoo source, no routed deliverable.
3. **Every claim is grounded.** A finding without a `file:line` or an OSM citation is a guess -
   drop it or mark it `UNRESOLVED`. The worklog `EVIDENCE` field is mandatory
   (`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md`).
4. **Escalate by evidence, not by vibe.** Phase 3 (opus) runs only when a measurable trigger fires
   (see § Phase 3). Default is to stop after Phase 2 and synthesize.
5. **Zero-trust: descriptions are CLAIMS, source is TRUTH.** Confirm every description (docstring,
   comment, manifest prose, prior report, OSM descriptive field) against the resolved source before
   marking a finding `RESOLVED`; when they disagree, source WINS and the description is flagged
   stale. OSM STRUCTURE stays the trusted primary. Full rule (inlined into every worker brief):
   `${CLAUDE_PLUGIN_ROOT}/snippets/zero-trust-code-survey.md`.

## Fan-out budget

Workers are launched as subagents, one per scope unit, using CHP Tier-B `subagent_type: "fork"`
(see `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` - Tier B). Set the model
explicitly on each fork's launch per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
§ Model-tier selection (Phase 1 haiku, Phase 2 sonnet; Phase 3's opus is the evidence-gated
escalation below, never a default); no custom agentType beyond the fork. Each fork writes its OWN
findings file; forks never share mutable state.
Fallback (Tier C): if `subagent_type: "fork"` is unavailable, dispatch a fresh `general-purpose`
spawn with an explicit brief. Write the worklog regardless of tier.

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

While decomposing, TAG each sub-question as in-codebase or **external** - an external dimension
is the trigger for Phase W (see below).

## Phase W - web research (conditional + bounded)

Runs ONLY when the Bootstrap decomposition holds a sub-question with an EXTERNAL dimension (a third-party library or API, a standard, an ecosystem or version-landscape question); a pure in-codebase survey skips it and says so. Hard cap: one haiku `WebSearch` fork worker per external sub-question, at most 4 per survey, each fetching at most the top 3 reputable sources, one broad-then-targeted pass. Web is subordinate to OSM and source: a web claim about Odoo behaviour loses to them; every finding carries source tier, URL and fetch date and lands in `web_findings`. Never the built-in `deep-research` skill. Source ladder and persistence: `references/web-research.md`, `references/phases.md` § Phase W.

## Phase 1 - broad / shallow sweep (haiku)

**Goal:** a fast, wide map of every candidate area. Cheap and parallel.

- **Scope unit** = one top-level custom module (the module scope resolved per
  `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`, which globs BOTH descriptor
  filenames). For a non-code intent, the unit is one persona-domain area implied by the intent.
- **Fan-out:** one haiku worker per unit, filling the Mode B budget (rolling-window beyond it).
- **Each worker**: reads the module's manifest + skims its models/views, and confirms existence
  with read-only OSM - `check_module_exists`, `module_inspect` (`method='summary'`), and
  `module_inspect` (`method='tests'`) to enumerate the test classes defined in the module.
  Each worker returns a short bullet map: what the area contains, which 1-3 spots look most
  relevant to the stated intent (the hot-spots) each with a `file:line`, and the module's test
  class list (or "no tests" if the module has none).
- **Two Phase-1 lenses** (`references/survey-lenses.md` § Phase 1): **L1 module purpose**
  (`describe_module` - 1-2 lines, downgrades a hot-spot in an off-intent module) and **L2
  entry-point map** (`ir.actions` / controllers / `ir.cron` / view buttons / `execute_kw`-reachable
  `@api.model` methods, each `file:line` -> dispatched model/route) as a first-class artifact.
- **Persist:** `<SHARE_DIR>/survey/<slug>-<date>/phase1/<NN>-<area>.md` + one worklog entry per worker.

## Phase 2 - narrow / deep dives (sonnet)

**Goal:** real depth on the Phase-1 hot-spots that bear on the intent. One sonnet worker per hot-spot within the Mode B budget: it traces the hot-spot (`model_inspect`, `find_override_point`, `resolve_orm_chain`), maps bidirectional impact (`${CLAUDE_PLUGIN_ROOT}/snippets/bidirectional-impact.md`), answers the sub-questions as `RESOLVED` / `UNRESOLVED`, applies the Phase-2 lenses L3-L8 of `references/survey-lenses.md` (inlined into the brief), runs the dependency-closure drill (`fp-symbol-survival-check.md` § 2 + § 2.5 pasted by the orchestrator, grounded at the target version when the intent is upgrade-adjacent) and the test blast radius (`tests_covering`, then `find_test_examples` before concluding zero coverage) that feeds the three-tier test-protection map. Persist `<SHARE_DIR>/survey/<slug>-<date>/phase2/<NN>-<hotspot>.md` + worklog. Full worker procedure: `references/phases.md` § Phase 2.

## Phase 3 - opus escalation (conditional)

Run a Phase 3 opus pass **only if** at least one measurable trigger holds (else SKIP straight to
synthesis; 2 in-flight max under Mode B):

1. **Conflict** - two or more Phase-2 reports disagree on one load-bearing fact (e.g. which module
   owns the hook).
2. **Cross-cutting unresolved** - a hot-spot's `impact_analysis` shows >=3 modules depending on it
   transitively that no worker fully traced, OR the Phase-2 dependency-closure drill left a branch
   >=3 layers deep ungrounded to `base`.
3. **Coverage gap** - an intent sub-question is still marked `UNRESOLVED` in the worklog after
   Phase 2.

Each opus worker takes one such unresolved knot and resolves it with cross-file reasoning over the
Phase-1/2 artifacts + OSM. **Persist:** `<SHARE_DIR>/survey/<slug>-<date>/phase3/<NN>-<knot>.md` +
worklog.

## Worker brief - what every dispatched worker must carry

A worker is a leaf that cannot resolve `${CLAUDE_PLUGIN_ROOT}`: the orchestrator fills `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton plus the Survey/analyst delta and PASTES into every brief the full text of `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`, `${CLAUDE_PLUGIN_ROOT}/snippets/zero-trust-code-survey.md`, the phase's lens block (and the two symbol-survival sections for a closure drill; `references/web-research.md` for a Phase W worker), plus the hard scope, the consumer lens (`file:line` + OSM call, `RESOLVED` / `UNRESOLVED`), the concrete `odoo_version`, the exact output path and worklog format, and the tier with its reason. The eight fields: `references/phases.md` § Worker brief.

## Synthesis + hand back to intake

After the last phase, read every `phase*/*.md` and the worklog oldest-first, aggregate (never re-survey) and write `<SHARE_DIR>/survey/<slug>-<date>/synthesis.md` to the contract of `references/synthesis-schema.md` - scope, key findings, ranked hot-spots, the lens sections (entry points, dependency closure, data flow, prior art, side effects, tech debt, cross-cutting), `tests_protecting` (three tiers; `test_coverage_audit` once per module; framework gates `grounded: local-source`, "verify live"), `web_findings` when Phase W ran, 5-10 `essential_reading` files, `open_questions`, `recommended_approach_delta`, `upgrade_symbol_gaps`. Synthesis runs at sonnet in this context (opus for a legal, accounting or regulatory domain); every claim carries `grounded:`. Return to intake the `synthesis.md` path and 3-5 bullets on what changed versus the recommended approach. Section detail: `references/phases.md` § Synthesis.

## OSM grounding

Always pass a **concrete** Odoo version on every OSM call; `'auto'` is unsafe under fan-out
(version pin is server-state shared across concurrent workers in one session -
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § OSM session-pin race). Call
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
<SHARE_DIR>/survey/<slug>-<date>/
  state.json        # {slug, intent, phase_done: [...], next: <phase|synthesis>}
  phaseW/<NN>-<subquestion>.md   # only if an external-dimension sub-question triggered Phase W
  phase1/<NN>-<area>.md
  phase2/<NN>-<hotspot>.md
  phase3/<NN>-<knot>.md      # only if escalated
  synthesis.md
```

If the run is interrupted, a re-invocation with the same slug reads `state.json` + the existing
`phase*/` files, skips completed phases, and resumes at `next` (file-existence is the source of
truth; `state.json` is the fast index).

## Standalone-first fallback

The survey prefers OSM but does not require it. If OSM is unreachable (a `set_active_version` probe
fails), workers fall back to **read-only disk** - reading each module's descriptor `depends`
(the descriptor filename per `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md`) and
skimming `models/` and `static/src` for the dependency and asset picture - and the synthesis
records `OSM: standalone` so intake states that the impact map is disk-derived, not
graph-resolved.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). `produced`
includes `synthesis.md`; `next` hands control back to `odoo-intake` to re-ask its approach question.
