<!-- SSOT snippet. The SURVEY-SPECIFIC elaboration of ODOO-AI-ETHOS.md principle 12
     ("Descriptions are Claims, Source is Truth"): the universal rule binds every agent from
     ETHOS; THIS file adds what only a survey needs - the OSM claim-vs-structure split and the
     RESOLVED/UNRESOLVED finding verdict. Used by odoo-deep-survey (its orchestrator + inlined
     into every dispatched fork-worker brief - workers are leaf subagents that cannot resolve
     ${CLAUDE_PLUGIN_ROOT}, so the orchestrator PASTES this text). Sibling of
     osm-first-contract.md section 1 "Existence is not currency": that rule is about symbol CURRENCY;
     THIS rule is about descriptive TEXT vs resolved SOURCE. Another skill that needs the stance
     but not the survey machinery cites ETHOS 12 - do NOT copy this file's finding-verdict
     apparatus into it, and do NOT restate the universal rule here. Edit here only. -->

# Zero-Trust Code Survey - descriptions are CLAIMS, source is TRUTH

A survey exists to tell a later execute agent what the code ACTUALLY does, not what someone
SAID it does. Every sentence describing behavior is an unverified CLAIM until it is confirmed
against the resolved source definition. Trust the structure; distrust the prose about it.

That stance is universal - `ODOO-AI-ETHOS.md` principle 12 binds every agent to it, whether or not
a survey is running, and owns WHY descriptive text rots. What follows is what a SURVEY additionally
needs: which OSM surfaces count as claim vs structure, and how that decides a finding's
RESOLVED/UNRESOLVED verdict.

## What counts as a CLAIM (confirm, never quote-and-move-on)

Treat all of these as unverified claims to be verified against source, regardless of how
authoritative they look:

- **On-disk prose:** docstrings, inline comments, `# TODO`/`# NOTE`, module `README`/long
  `description` / `summary` in `__manifest__.py`, help strings.
- **History + reports:** commit messages, PR text, and PRIOR survey / audit / design reports
  (including this survey's own earlier phases - a Phase-1 bullet is a lead, not a proof).
- **OSM DESCRIPTIVE fields:** `describe_module` prose, a module/model `summary`, indexed
  docstrings, and natural-language pattern notes (`suggest_pattern` rationale, `find_examples`
  commentary). These are indexed TEXT - still a claim, even though OSM is the primary source.

## What counts as TRUTH (ground findings here)

The RESOLVED structural / behavioral source definition:

- **OSM STRUCTURE (primary, trusted):** `model_inspect` (fields/methods by spec), `entity_lookup`,
  `resolve_orm_chain`, `find_override_point`, `impact_analysis`, and the `validate_*` family.
  These return how the source IS DEFINED, inheritance-resolved - that is truth, not a claim.
- **Raw source (fallback, trusted):** the actual method body / field definition / XPath on disk,
  read only where OSM is silent (label `grounded: local-source`).

## The rule

1. Mark a finding `RESOLVED` only when it is grounded in the STRUCTURAL / BEHAVIORAL source (an
   OSM structural call or a `file:line` read) - never in a sentence that merely describes it. A
   claim you have not confirmed against source is `UNRESOLVED`, not `RESOLVED`.
2. If a description and the source DISAGREE, **source WINS**: record the source-grounded fact and
   FLAG the description as stale (name where the stale text lives so it can be fixed later).
3. This does **NOT** invert OSM-first. OSM's STRUCTURE is still the PRIMARY, trusted ground truth
   (`model_inspect` / `entity_lookup` / `resolve_orm_chain` / `find_override_point` /
   `impact_analysis` / `validate_*`); reading raw source is the FALLBACK. What is demoted to a
   claim is the DESCRIPTIVE TEXT about the code - never the resolved structure OSM returns.
