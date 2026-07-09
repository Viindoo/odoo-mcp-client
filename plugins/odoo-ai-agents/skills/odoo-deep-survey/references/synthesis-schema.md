<!-- SSOT for the deep-survey synthesis.md output contract. The orchestrator (opus, main
     context) reads every phase*/*.md + the worklog and writes synthesis.md to this schema.
     Consumer = the next execute agent (architect / coder / reviewer), never a human - every
     field is actionable without re-derivation. Edit the schema here, not in SKILL.md. -->

# Deep-Survey Synthesis Schema (synthesis.md output contract)

Each section is few-token and agent-readable - this is a hand-off to an execute agent, not a
human architecture document. Every finding carries a `file:line` or an OSM citation and is marked
`RESOLVED` / `UNRESOLVED`.

## Grounding vocabulary (carried on every section / finding)

- `grounded: osm` - confirmed via the OSM index only.
- `grounded: hybrid` - OSM + a local-source read (custom code OSM cannot fully resolve).
- `grounded: local-source` - disk read only (OSM unreachable, or the fact is not OSM-indexed -
  e.g. the framework-validation test classes).

(Maps to the upg P1d labels `osm` / `osm + local-source (hybrid)` / `local-source (not OSM-indexed)`.)

## Sections (in order)

1. **scope_covered** - areas surveyed, tier per area, `grounded:` per area.
2. **key_findings** - each with `file:line` + OSM citation, `RESOLVED` / `UNRESOLVED`.
3. **hot_spots_ranked** - by relevance to the intent.
4. **entry_points** - the Odoo entry-point map (lens L2): action / controller / cron / button /
   `execute_kw`, each `file:line` -> the model / route it dispatches to.
5. **dependency_closure** - the nearest -> base map per hot-spot (drill):
   `module | layer-distance | why it matters | grounded`.
6. **data_flow** - per hot-spot `A -> B -> C -> stored field X` with `[LAYER: ...]` labels
   (lenses L3 + L4).
7. **prior_art** - existing overrides / patterns / tests that already solve this (lens L7), each
   with `file:line` + which one to ADAPT. Header line: "Read this BEFORE coding - do not reinvent."
8. **tests_protecting** - the three-tier test-protection map (own-module / dependency / framework
   gates), each test with its path or "framework gate, verify live". This SUBSUMES the old "test
   coverage gaps" bullet: a zero-coverage hot-spot is the gap, surfaced as a flagged row here.
9. **side_effects** - per hot-spot Odoo side-effects (lens L5).
10. **tech_debt** - flagged pre-existing smells (lens L8). FLAG-ONLY, not a fix list.
11. **cross_cutting** - `groups=` / `sudo()` / `@api.constrains` seams flagged (lens L6),
    existence-only (full verdict is `odoo-security-audit`).
12. **web_findings** (OPTIONAL - present only when Phase W ran; see `references/web-research.md`) -
    external evidence gathered by the bounded web reconnaissance pass. One row per claim:
    `claim | source-tier | URL | corroborating-source | VERIFIED/UNVERIFIED`. `source-tier` is
    one of authoritative / reputable / low-trust (the ladder in `references/web-research.md`).
    HARD rule: a web claim about Odoo behavior is SUBORDINATE to OSM/source - if they disagree,
    OSM/source wins and the web claim is dropped or kept only as a flagged discrepancy. Absent
    entirely for a pure in-codebase/OSM survey (Phase W skipped).
13. **essential_reading** - the 5-10 files MAX a downstream agent must read to UNDERSTAND the scope
    (distinct from "files to change"), each + one line "why" + `file:line`. Example:
    `models/sale_order.py:245 - override of action_confirm, the main entry point`.
14. **open_questions** - anything still `UNRESOLVED` (so intake flags it honestly).
15. **recommended_approach_delta** - how the first Proposed Plan should change given what was found.
16. **upgrade_symbol_gaps** (OPTIONAL - upgrade-adjacent intent only) - non-SURVIVED symbols from the
    dependency-closure drill grounded at the TARGET version (RENAMED / REMOVED / TYPE_CHANGED), in
    the `${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md` § 4 output shape.

## Build notes

- Sections 4-11 + 13 are populated from the Phase-1/2/3 lens subsections
  (`references/survey-lenses.md`); the synthesiser aggregates and de-duplicates, it does not
  re-survey.
- **web_findings** (section 12) is present ONLY when Phase W ran (an external-dimension
  sub-question triggered it); it is aggregated from the `phaseW/*.md` worker files
  (`references/web-research.md`) and OMITTED for a pure in-codebase/OSM survey.
- For **tests_protecting** tier (iii), call `test_coverage_audit` once per surveyed module before
  writing, AND list the framework gates from the runbot-parity-checklist cross-ref - the latter are
  `grounded: local-source` because OSM does not index them.
- Hand back to intake: the path to `synthesis.md` + 3-5 bullets naming what changed versus the first
  plan; intake fills its `Survey:` field and re-proposes. Downstream skills read `synthesis.md` (and
  the worklog) to inherit this survey instead of re-deriving it.
