"""Mechanical guard for the P12 defect CLASS (Phase 3 runtime review, round 4.20.0): a cross-file
reference that names a tier/step/phase/clause/round/wave COUNT must agree with the actual count in
the section it cites.

Confirmed pre-fix defect (this round): `skills/odoo-onboarding/SKILL.md` pointed at a
non-existent "i18n.json/tier-6" - stale residue of the C-2 fix that renumbered
`skills/odoo-doc-illustration/SKILL.md`'s language resolver from 6 tiers (with a hardcoded-default
6th tier) down to 5 (with an explicit "No tier 6" rule). The SAME renumbering left FIVE more sites
still calling that resolver "6-tier" / "D6": `agents/odoo-doc-scoper.md` (4 sites: the agent's own
role-intro parenthetical, the `LANGUAGES:` input-table row, and the Step 4 SSOT cross-reference
appearing twice), `workflows/module-packaging.workflow.yaml` (the inline scope-phase comment), and
`skills/odoo-doc-illustration/references/app-store-template.md` (its own SSOT cross-reference) -
the last one found ONLY by this test's own registry-vs-citation sweep, not by the manual review
that found the other five.

Why this needed a NEW mechanism, not just a bigger manual sweep: the round's `${CLAUDE_PLUGIN_ROOT}`
path-pointer sweep found 1550+98 references and 0 dangling paths, and the lane that reviewed the
locale/i18n subsystem passed it - both missed all six sites, because the reference is SEMANTIC (a
tier COUNT), not a filesystem path, and every one of these citations points at a real, resolvable
file - only the NUMBER embedded in the prose is wrong. A path-existence check can never catch that;
only a count-agreement check can.

Design (SCOPED to COUNTED cross-references, not every numbered cross-reference - see rationale
below), no filename allowlist:

1. **Registry pass.** Scan every heading line (`^#{1,4} ...`) in every `.md` file under both
   plugin trees for an embedded `<N>-<unit>` token (tier/step/phase/clause/round/wave, case-
   insensitive) - e.g. `## Language resolution (5-tier + disk-UNION, no default)`,
   `## 4-tier routing`, `## Brainstorm (6-step)`. Each hit becomes a registry row: the OWNING
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
_COUNT_UNIT_RE = re.compile(r"\b(\d+)-(tier|step|phase|clause|round|wave)\b", re.IGNORECASE)
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
                        "unit": cu.group(2).lower(),
                        "count": int(cu.group(1)),
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
            cited_count = int(m.group(1))
            unit = m.group(2).lower()

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


def test_counted_cross_file_references_agree_with_the_target_heading():
    registry = _build_registry()
    assert registry, "no counted (<N>-tier/step/phase/clause/round/wave) headings found at all - regex or tree drifted"

    hits = _mismatched_citation_hits(registry)
    assert not hits, (
        "A cross-file reference names a tier/step/phase/clause/round/wave COUNT that disagrees "
        "with the target section's actual count - stale renumbering residue (the exact P12 "
        "defect class): an agent following the reference goes looking for a step/tier that does "
        "not exist, or misses the real final one:\n" + "\n".join(hits)
    )
