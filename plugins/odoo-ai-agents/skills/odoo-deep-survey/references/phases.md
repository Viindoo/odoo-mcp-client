# odoo-deep-survey - phase detail

**Contents:** Phase W - web research (conditional + bounded) - Phase 2 - narrow / deep dives (sonnet) - Worker brief - what every dispatched worker must carry - Synthesis + hand back to intake

The full wording of the phases `SKILL.md` summarises; `SKILL.md` names the section it needs.

### Phase W - web research

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

### Phase 2 - narrow / deep dives (sonnet)

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

### Worker brief - what every dispatched worker must carry

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

### Synthesis + hand back to intake

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
