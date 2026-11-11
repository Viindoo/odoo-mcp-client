# Zero-Trust Code Survey - descriptions are CLAIMS, source is TRUTH

A survey exists to tell a later execute agent what the code ACTUALLY does, not what someone
SAID it does. Every sentence describing behavior is an unverified CLAIM until it is confirmed
against the resolved source definition. Trust the structure; distrust the prose about it.

A change of behaviour that a finding leads to needs three facts: the principle it serves, the
current behaviour verified by a run or by the source on the base and on the working branch, and
its business impact. With one missing, the behaviour stays as it is and the finding records what
is missing.

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
   Not covered here, so the silence is not read as coverage: revision SKEW, where the index
   answers from an older revision of the same file. See `osm-first-contract.md` § Presence in
   the index is not currency.
