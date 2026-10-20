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

A LIGHT external-evidence pass, reusing the SAME fork-worker fan-out as Phases 1-3. Full
procedure + source ladder: `references/web-research.md` (orchestrator inlines the relevant parts
into each web worker's brief). Do **NOT** dispatch or depend on the built-in `deep-research`
skill.

- **Trigger (conditional-on-intent):** run Phase W **only if** the Bootstrap decomposition has
  at least one sub-question with an EXTERNAL dimension - a third-party library/API, a
  standard/regulation, an ecosystem/version-landscape question, or "how do others do X". For a
  PURE in-codebase/OSM survey, **SKIP Phase W entirely** and say so.
- **Bound (hard cap - state it):** at most ONE haiku `WebSearch` fork worker per external
  sub-question (**<= 4 web workers per survey**), each doing `WebFetch` on at most the top 3
  reputable sources. One broad -> targeted pass per sub-question, then stop. NO loop-until-dry,
  NO N-vote adversarial harness, NO unbounded fan-out.
- **Source-credibility ladder:** authoritative (`github.com/odoo/odoo`, odoo.com/documentation,
  the OSM index, `github.com/OCA`, Odoo release notes/runbot, a named dependency's official
  docs) > reputable (well-known Odoo blogs / Cybrosys / accepted Odoo-forum answers) > low-trust
  (random forums / unattributed or AI-generated content - corroboration-only, never
  load-bearing). Prefer >= 2 reputable-or-better sources; mark `UNVERIFIED` otherwise.
- **Web is SUBORDINATE to OSM/source:** a web claim about Odoo behavior loses to OSM/source when
  they disagree - drop it or keep it only as a flagged discrepancy. Web is load-bearing ONLY for
  genuinely external facts OSM does not index. Every web finding carries source-tier + URL +
  fetch-date and lands in the synthesis `web_findings` section.
- **Persist:** `<SHARE_DIR>/survey/<slug>-<date>/phaseW/<NN>-<subquestion>.md` + one worklog entry
  per worker. Sequence Phase W with the broad sweep (it feeds Phase-2 deep dives that touch the
  external dimension); if skipped, note "Phase W: skipped (no external sub-question)".

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

**Goal:** understand the hot-spots that actually bear on the intent - fewer targets, real depth.

- **Scope** = the Phase-1 hot-spots ranked most-relevant to the intent (narrow the field; ignore
  areas Phase 1 marked irrelevant).
- **Fan-out:** one sonnet worker per hot-spot, within the Mode B budget.
- **Each worker** traces the hot-spot with
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
  `base`, PHASED one dependency layer at a time (respect the Mode B budget), and ground each external symbol by
  REUSING `${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md` § 2 + § 2.5 BY PATH (the
  orchestrator inlines those two sections into the brief - never copy them). Output a
  dependency-closure map (`nearest -> ... -> base`, layer + why + `grounded:`). Ground at the
  current version; if the intent is upgrade-adjacent, ground at the target version so the drill
  doubles as a pre-upgrade symbol check.

  After `impact_analysis` resolves the blast radius, each worker also calls `tests_covering` for
  the hot-spot's primary model to determine the **test blast radius**: which existing tests
  already guard this behavior. Prefer model-level or field-level narrow over method-level. If
  `tests_covering` returns 0 edges for a method of interest, fall back to
  `find_test_examples(query='<method_name>', odoo_version=<series>)` before concluding zero
  coverage. Record the result in the worker's phase2 file as a "Test blast radius" subsection:
  number of test edges, test file paths, and whether the hot-spot has zero test coverage (a
  coverage gap confirmed by BOTH tools). Zero-coverage hot-spots are escalation candidates for
  Phase 3 (trigger: § Phase 3 item 3). This call populates tiers (i) own-module and (ii)
  dependency tests of the **test-protection map** (`references/survey-lenses.md` § Test-protection
  map); tier (iii) framework-validation + lint gates (the framework-validation classes the target
  series ships - ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md § Framework-validation test
  classes - plus the lint-class modules) is assembled at synthesis. All three feed
  the synthesis `tests_protecting` section.

- **Persist:** `<SHARE_DIR>/survey/<slug>-<date>/phase2/<NN>-<hotspot>.md` + worklog entries.

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

A worker is a leaf subagent that **cannot resolve `${CLAUDE_PLUGIN_ROOT}` itself** - the
orchestrator must **read referenced snippets and paste their content into the brief**.

**Dispatch-brief skeleton.** Before dispatching, fill the caller-side skeleton in
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton (read it by path) plus the Survey/analyst
family delta; never inline that file verbatim into a hard-leaf brief.

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
8. **Zero-trust stance** - inline the full text of
   `${CLAUDE_PLUGIN_ROOT}/snippets/zero-trust-code-survey.md` into EVERY worker brief (same paste
   mechanism as the worker brief + lens block). For a Phase W worker, ALSO inline `references/web-research.md` (the source
   ladder + the web-subordinate-to-OSM rule).

## Synthesis + hand back to intake

After the last phase, read every `phase*/*.md` + the worklog (oldest-first), aggregate the lens
subsections (do NOT re-survey), and write `<SHARE_DIR>/survey/<slug>-<date>/synthesis.md` to the full
contract in `references/synthesis-schema.md`. Synthesis runs at sonnet in this skill's own context; when the surveyed domain is legal, accounting, regulatory or another deep specialist domain, dispatch it to an opus subagent instead (tier SSOT: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection). Each section is few-token, agent-readable, and
carries `grounded: osm | hybrid | local-source`. Sections:

- **scope_covered**, **key_findings** (`file:line` + OSM), **hot_spots_ranked** - as before.
- **entry_points** (L2), **dependency_closure** (`nearest -> base`), **data_flow** (`A -> B -> X`
  + `[LAYER: ...]`), **prior_art** ("read BEFORE coding - do not reinvent"), **side_effects**,
  **tech_debt** (flag-only), **cross_cutting** (flag-only) - aggregated from the Phase-2 lenses.
- **tests_protecting** - the three-tier test-protection map (own-module / dependency / framework
  gates); a zero-coverage hot-spot is a flagged row. Build tier (i)+(ii) by calling
  `test_coverage_audit` once per surveyed module. Tier (iii) framework gates are `grounded: local-source` (OSM does not index them) - list them
  from the runbot-parity-checklist cross-ref in `references/survey-lenses.md`, each "verify live".
- **web_findings** (external evidence, present ONLY when Phase W ran) - rows
  `claim | source-tier | URL | corroborating-source | VERIFIED/UNVERIFIED`; subordinate to
  OSM/source per § Phase W.
- **essential_reading** - 5-10 files MAX to UNDERSTAND the scope (distinct from files-to-change),
  each + one-line "why" + `file:line`.
- **open_questions** (`UNRESOLVED`), **recommended_approach_delta**, and **upgrade_symbol_gaps**
  (optional, upgrade-adjacent intent only - non-SURVIVED symbols from the closure drill).

Return to intake: the path to `synthesis.md` plus 3-5 bullets naming what changed versus the
recommended approach. Downstream skills read `synthesis.md` (and the worklog) to inherit this
survey.

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
