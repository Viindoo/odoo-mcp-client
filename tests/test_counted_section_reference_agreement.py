"""Mechanical guard for the P12 defect CLASS (Phase 3 runtime review, round 4.20.0): a cross-file
reference that names a tier/step/phase/clause/round/wave/operation COUNT must agree with the actual
count in the section it cites.

WHAT THIS GUARD STILL CANNOT SEE (stated here so nobody mistakes a green run for full coverage -
each of these is a live false NEGATIVE, not a design nicety):

- **A count written in any spelling this file does not enumerate.** `_WORD_NUMERALS` stops at
  twelve, and nothing recognises `a dozen`, `half a dozen`, an ordinal-as-count (`the 7th and
  final operation`), or a digit-with-separator (`1,024 steps`). A heading using one of those
  declares nothing to this guard, so every citation of it is unchecked.
- **A hyphenated word numeral, on purpose.** `two-tier` is an ordinary English compound adjective
  (see `_COUNT_UNIT_RE`), so it is deliberately not matched - which means a GENUINE `two-step`
  citation that drifted out of date is missed. Precision was chosen over recall there because the
  measured false positives were real and the missed true positives are hypothetical.
- **Any unit outside `_UNITS`.** A section counting `lenses`, `rungs`, `arms`, `gates` or `exits`
  is invisible. The set is closed on purpose (an open unit list collides with prose), which makes
  every uncounted vocabulary a blind spot by construction.
- **A citation further than `_CITATION_WINDOW` from the path it cites**, and any citation that
  names its target some other way than by path suffix (by skill name, by heading title, by "the
  agent above").
- **The MEMBERS behind a count.** This guard proves the NUMBER agrees; it cannot prove the two
  lists hold the same items. `tests/test_instance_ops_hardening.py::
  test_operation_set_matches_the_dispatch_table` is the companion that checks membership for the
  one place both halves exist - a count guard alone would pass a rename that kept the total.

Confirmed pre-fix defect (this round): `agents/odoo-doc-scoper.md` pointed at a
non-existent "i18n.json/tier-6" in 4 sites (the agent's own role-intro parenthetical, the
`LANGUAGES:` input-table row, and the Step 4 SSOT cross-reference appearing twice) - stale residue
of the C-2 fix that renumbered `skills/odoo-doc-illustration/SKILL.md`'s language resolver from 6
tiers (with a hardcoded-default 6th tier) down to 5 (with an explicit "No tier 6" rule). The SAME
renumbering left ONE more site the manual review also found still calling that resolver "6-tier" /
"D6": `workflows/module-packaging.workflow.yaml` (the inline scope-phase comment).
`skills/odoo-doc-illustration/references/app-store-template.md` (its own SSOT cross-reference) was
found ONLY by this test's own registry-vs-citation sweep, not by the manual review that found the
other five.

Why this needed a NEW mechanism, not just a bigger manual sweep: the round's `${CLAUDE_PLUGIN_ROOT}`
path-pointer sweep found 1550+98 references and 0 dangling paths, and the lane that reviewed the
locale/i18n subsystem passed it - both missed all six sites, because the reference is SEMANTIC (a
tier COUNT), not a filesystem path, and every one of these citations points at a real, resolvable
file - only the NUMBER embedded in the prose is wrong. A path-existence check can never catch that;
only a count-agreement check can.

Design (SCOPED to COUNTED cross-references, not every numbered cross-reference - see rationale
below), no filename allowlist:

1. **Registry pass.** Scan every heading line (`^#{1,4} ...`) in every `.md` file under both
   plugin trees for an embedded count token (tier/step/phase/clause/round/wave/operation, case-
   insensitive), in EITHER spelling - `## Language resolution (4-tier + disk-UNION, no default)`,
   `## 4-tier routing`, `## Brainstorm (6-step)`, `## Seven operations`, `## The three tiers`.
   A count written in words is the majority spelling of a heading in this tree, so a
   digits-only rule was blind to most of the sections it exists to protect - see `_COUNT_UNIT_RE`
   for the one asymmetry between the two spellings and the measurement behind it. Each hit
   becomes a registry row: the OWNING
   file's plugin-relative path (`skills/odoo-doc-illustration/SKILL.md`), the unit, and the
   TRUE count - always re-derived from the heading text itself, never hardcoded, so a future
   legitimate renumbering (5 -> 7, say) updates the guard's expectation automatically with zero
   code change.
2. **Citation pass.** Scan every `<N>-<unit>` occurrence anywhere else in either plugin tree
   (`.md`/`.yaml`/`.yml`, generated-tools blocks blanked). For each, look at a same-paragraph
   character window (+/-300 chars, enough to span a wrapped 3-5 line citation like the ones this
   defect actually took) for the registry row's OWNING-file path suffix appearing VERBATIM
   (`skills/odoo-doc-illustration/SKILL.md`, with or without a `${CLAUDE_PLUGIN_ROOT}/` prefix -
   the same path-citation convention `test_no_hardcoded_locale_or_filename.py` already relies on
   for its own path-existence check). If the path is present and the cited count differs from the
   registry's true count for the SAME unit -> offender.
3. A citation inside the registry file's OWN heading-defining span is excluded (that is the
   DEFINITION, not a citation of it).

Why the path-suffix anchor and not a looser "topic keyword" or bare-directory-name match: a bare
directory-name proximity check was prototyped first and produced 12 false positives (e.g. a "3-tier"
mention elsewhere in `README.md` landing within 400 chars of an unrelated "odoo-intake" mention that
has nothing to do with that 3-tier concept). The exact path-suffix string is the one signal that is
BOTH precise (a false match requires the literal path substring, not just a shared word) and
GENERAL (every genuine cross-file SSOT citation in this codebase already names the target file this
way - verified across the whole tree during the manual side of this round's sweep) - not a per-file
allowlist, since ANY current or future file using this same path-citation convention is
automatically covered, in both directions (a citation that adopts the convention is checked; one
that already matches and drifts out of count is caught).

Why SCOPED to counted references, not every numbered cross-reference (an explicit design choice,
not an oversight): a bare ordinal reference ("tier 1", "Phase 0", "Step 4", "Clause 2") names a
POSITION, not a COUNT, and checking THOSE mechanically requires knowing each target file's own
step/phase/clause vocabulary and matching prose topic - a much larger, more heterogeneous problem
(this round's manual sweep checked ~19 such cross-file ordinal references by hand and found all of
them correct; automating that class risks either false positives on legitimate prose or a
false sense of coverage from an over-fitted matcher). A COUNT is a single scalar fact that is
mechanically checkable against a single heading with no semantic judgment required, so it is
automated here; the ordinal class stays a manual-review item (recorded in the round's fix report),
mirroring this repo's existing precedent of automating what is cleanly decidable and leaving a
genuinely judgment-requiring check manual (`test_no_hardcoded_locale_or_filename.py`'s currency-
default check makes the identical trade-off, for the identical reason).

`evals/` and `generator/` are exempted by the same repo-documented, directory-wide convention as
`test_no_self_referential_tracker_citation.py` (fixture data / build tooling, never agent-facing
prose an execute-agent loads as its operating contract) - not a per-file allowlist.
"""
from __future__ import annotations

from pathlib import Path

import re

ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = ROOT / "plugins"
PLUGIN_NAMES = ("odoo-ai-agents", "git-toolkit")

_GENERATED_BLOCK = re.compile(
    r"<!-- BEGIN GENERATED TOOLS -->.*?<!-- END GENERATED TOOLS -->", re.S
)
_HEADING_RE = re.compile(r"^#{1,4}\s+.*$", re.M)
# Spelled-out numerals, so `## Seven operations` is registered as a count and not
# skipped for being written in words. English headings in this tree count in words
# far more often than in digits, so a digits-only rule was not "narrow but sound" -
# it was blind to the majority spelling of the very thing it checks.
_WORD_NUMERALS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_UNITS = ("tier", "step", "phase", "clause", "round", "wave", "operation")
_UNIT_ALT = "|".join(_UNITS)
# ONE pattern, two spellings, and the asymmetry between them is MEASURED, not
# stylistic:
#   - a DIGIT may be joined by a hyphen or a space (`5-tier`, `5 tiers`);
#   - a WORD numeral is accepted ONLY space-separated (`Seven operations`,
#     `the three tiers`), never hyphenated.
# Because a hyphenated word numeral is an ordinary English compound adjective
# that usually names something else entirely. Measured on this tree the moment
# the hyphenated form was allowed: `two-tier decomposition axis`
# (skills/odoo-intake/references/phase-p-run-dag.md) and `no two-tier dance`
# (skills/odoo-doc-illustration/references/capture-mechanics.md) both landed
# within the citation window of an unrelated `state-root-resolution.md`
# reference and were reported as disagreeing with its `## The three tiers`
# heading - two false positives, zero true ones. The space-separated plural has
# no such collision: it reads as a count of things, which is what this guard is
# about.
_COUNT_UNIT_RE = re.compile(
    r"\b(?:(\d+)[-\s]|(" + "|".join(_WORD_NUMERALS) + r")\s)("
    + _UNIT_ALT + r")s?\b",
    re.IGNORECASE,
)


def _count_of(token: str) -> int:
    """The numeral a match captured, digits or word."""
    token = token.strip().lower()
    return int(token) if token.isdigit() else _WORD_NUMERALS[token]
_EXEMPT_DIR_SEGMENTS = ("/evals/", "/generator/")
# A citation this close to the heading it matches is treated as that heading's own definition,
# not a separate reference to it (covers a heading's own body paragraph restating its count).
_SELF_DEF_PROXIMITY = 200
# Wide enough to span a wrapped citation paragraph (the real defect's longest span was ~180 chars
# across 3 physical lines); narrow enough that an unrelated file mention 400+ chars away does not
# false-positive (measured: a 400-char window produced 12 false positives; 300 produces 0 while
# still catching every confirmed real site).
_CITATION_WINDOW = 300


def _plugin_roots():
    for name in PLUGIN_NAMES:
        p = PLUGINS_DIR / name
        if p.is_dir():
            yield name, p


def _is_exempt(rel: str) -> bool:
    rel_slashed = f"/{rel}/"
    return any(seg in rel_slashed for seg in _EXEMPT_DIR_SEGMENTS)


def _blanked(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return _GENERATED_BLOCK.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _build_registry() -> list[dict]:
    """Every heading, in either plugin tree, that embeds an <N>-<unit> count."""
    registry = []
    for _name, plugin_dir in _plugin_roots():
        for path in sorted(plugin_dir.rglob("*.md")):
            rel_full = _rel(path)
            if _is_exempt(rel_full):
                continue
            rel_in_plugin = str(path.relative_to(plugin_dir))
            text = _blanked(path)
            for m in _HEADING_RE.finditer(text):
                heading = m.group(0)
                cu = _COUNT_UNIT_RE.search(heading)
                if not cu:
                    continue
                registry.append(
                    {
                        "file": rel_full,
                        "path_suffix": rel_in_plugin,
                        "unit": cu.group(3).lower(),
                        "count": _count_of(cu.group(1) or cu.group(2)),
                        "heading": heading.strip(),
                        "heading_start": m.start(),
                    }
                )
    return registry


def _iter_scanned_files():
    for _name, plugin_dir in _plugin_roots():
        for pattern in ("*.md", "*.yaml", "*.yml"):
            for path in sorted(plugin_dir.rglob(pattern)):
                if _is_exempt(_rel(path)):
                    continue
                yield path


def _mismatched_citation_hits(registry: list[dict]) -> list[str]:
    hits = []
    for path in _iter_scanned_files():
        rel = _rel(path)
        text = _blanked(path)
        for m in _COUNT_UNIT_RE.finditer(text):
            cited_count = _count_of(m.group(1) or m.group(2))
            unit = m.group(3).lower()

            is_self_definition = any(
                r["file"] == rel
                and r["unit"] == unit
                and abs(r["heading_start"] - m.start()) < _SELF_DEF_PROXIMITY
                for r in registry
            )
            if is_self_definition:
                continue

            window_start = max(0, m.start() - _CITATION_WINDOW)
            window_end = min(len(text), m.end() + _CITATION_WINDOW)
            window = text[window_start:window_end]

            for r in registry:
                if r["unit"] != unit or r["file"] == rel:
                    continue
                if r["path_suffix"] not in window:
                    continue
                if cited_count != r["count"]:
                    hits.append(
                        f"{rel}: cites {cited_count}-{unit} but {r['file']} "
                        f'("{r["heading"]}") is actually {r["count"]}-{unit}'
                    )
    return hits


def test_the_matcher_reads_both_spellings_and_refuses_the_ambiguous_one():
    """Red-before-green for the widening itself: without this, the word-numeral
    branch could silently stop matching (or start over-matching) and the sweep
    below would go on printing "clean" for a registry it no longer builds."""
    def _one(text):
        m = _COUNT_UNIT_RE.search(text)
        return None if not m else (_count_of(m.group(1) or m.group(2)), m.group(3).lower())

    assert _one("## Seven operations") == (7, "operation")
    assert _one("## The three tiers") == (3, "tier")
    assert _one("## 4-tier routing") == (4, "tier")
    assert _one("a 5 phase pipeline") == (5, "phase")
    # Deliberately NOT matched - a hyphenated word numeral is a compound
    # adjective, and matching it produced two measured false positives.
    assert _one("no two-tier dance") is None
    assert _one("Two-tier decomposition axis") is None
    # Not a count at all: an ordinal names a POSITION, which this guard is
    # explicitly scoped away from.
    assert _one("see phase 4 below") is None


def test_counted_cross_file_references_agree_with_the_target_heading():
    registry = _build_registry()
    assert registry, (
        "no counted (tier/step/phase/clause/round/wave/operation) headings found at all - "
        "regex or tree drifted"
    )
    assert any(r["unit"] == "operation" for r in registry), (
        "the `operation` unit must be discoverable, or the agent's operation count is "
        "unguarded again - the exact gap this unit was added to close"
    )

    hits = _mismatched_citation_hits(registry)
    assert not hits, (
        "A cross-file reference names a tier/step/phase/clause/round/wave COUNT that disagrees "
        "with the target section's actual count - stale renumbering residue (the exact P12 "
        "defect class): an agent following the reference goes looking for a step/tier that does "
        "not exist, or misses the real final one:\n" + "\n".join(hits)
    )
