"""Guard [ref-scope] half (a) (rule 14a in generator/check_orchestration.py, M9 in
12-design-final.md) against silent threshold crossings by a widely-cited SSOT file.

## The defect this test exists to prevent

`check_ref_scope_citation_anchor` flags a SKILL.md/agents/*.md citation of another real file
over `LARGE_FILE_THRESHOLD` (20480B) that carries no `'§ <anchor>'` within `REF_SCOPE_WINDOW`
(150) chars - a whole-file citation for one clause. That half is shipped WARN-ONLY in the CLI
(`check_orchestration.py --strict` never gates on it for one release, per its own docstring), by
deliberate design: there is a real, already-documented backlog of pre-existing oversize files
(dominated by `skills/_shared/odoo-frontend-fidelity.md` and
`snippets/visual-evidence-lifecycle-contract.md` - named in `check_ref_scope_citation_anchor`'s
own docstring as "neither named by the design as requiring an immediate sweep").

Because the CLI check never gates, NOTHING enforced "a widely-cited snippet must not silently
cross the threshold." `snippets/state-root-resolution.md` sat at 20403B on master - deliberately
tuned just under the 20480B threshold, because it is cited (whole-file, no anchor) by dozens of
skills/agents. A single 132B addition (a required Tier-1 `conf/` allowlist row) pushed it to
20535B - 55 bytes over - with nobody noticing, because the only mechanism that would have caught
it (`[ref-scope]` half (a)) is warn-only. The consequence, measured: the finding count went from
89 to 153 - +64, and 66 of those 153 findings cited this ONE file. The size crossing alone
manufactured dozens of orphan findings against files nobody in that session even touched.

## Chosen formulation

For each file cited (via `LARGE_FILE_CITE_RE`, `check_orchestration.py`'s own citation-detection
regex - not re-derived here) by MORE than a dominance ceiling of DISTINCT citer files without a
`'§ <anchor>'` nearby, assert the cited file is at or under `LARGE_FILE_THRESHOLD` (the SAME
constant `check_orchestration.py` uses - imported, never re-typed as a second `20480` literal).
Because `check_ref_scope_citation_anchor` only ever reports a finding for a file that ALREADY
exceeds the threshold, "assert it is under the threshold" collapses to "assert it is not in the
findings with a citer-count over the ceiling" - which is exactly what `_ref_scope_violations`
below computes. This is deliberately a RELATIONSHIP check (fan-in x size), not a per-filename
byte assertion: `assert size('state-root-resolution.md') < 20480` would pass forever the moment a
DIFFERENT widely-cited file crossed the same threshold. `test_synthetic_different_widely_cited_file_is_flagged`
below proves this test does not have that blindness.

A small number of ALREADY-documented backlog files get a wider ceiling instead of an unconditional
exemption - each one still fails if its fan-in balloons far past its measured-today count. This
mirrors `tests/fixtures/card_budget_grandfather.json`'s own grandfather convention: known debt is
named and bounded, not ignored, and a NEW file entering the same failure shape (any name, not just
the two known ones, and not just `state-root-resolution.md`) is caught immediately at the default
(tighter) ceiling.

## Red-before-green proof (run manually; the assertions below are executable, not the manual step)

    1. Append ~200 bytes of filler to `snippets/state-root-resolution.md` (crossing back over
       20480B).
    2. `pytest tests/test_ref_scope_citation_anchor.py::test_no_cited_file_exceeds_its_dominance_ceiling -q`
       goes RED, naming `snippets/state-root-resolution.md` and every one of its ~66 unanchored
       citers in the failure message.
    3. Restore the file byte-for-byte (verify with `sha256sum`) and the same test goes GREEN again.

Run: python -m pytest tests/test_ref_scope_citation_anchor.py -v
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from generator import check_orchestration as co  # noqa: E402

# The dominance ceiling for the REAL tree: comfortably above today's next-highest legitimate
# count (4, `agents/odoo-code-reviewer.md`), far below the
# magnitude of the regression this test exists to catch (66, `state-root-resolution.md`).
REF_SCOPE_DOMINANCE_CITERS = 15

# Already-documented pre-existing backlog (named in check_ref_scope_citation_anchor's own
# docstring), given a wider - but still bounded, never infinite - ceiling. Comfortably above their
# measured-today counts (22 and 19), nowhere near the 66-citer regression shape.
REF_SCOPE_KNOWN_BACKLOG_CEILING = {
    "skills/_shared/odoo-frontend-fidelity.md": 35,
    "snippets/visual-evidence-lifecycle-contract.md": 35,
}

_FINDING_RE = re.compile(r"^\[ref-scope\] (?P<citer>\S+):\d+ cites '(?P<cited>[^']+)'")


def _ref_scope_unanchored_citers() -> dict[str, set[str]]:
    """Group check_ref_scope_citation_anchor's real findings by cited file -> set of distinct
    citer files. Calls the ACTUAL check_orchestration.py function (never re-derives its regex,
    window, or threshold), against whatever PLUGIN_ROOT/SKILLS_DIR/AGENTS_DIR are currently bound
    to - the real tree by default, or a monkeypatched fake tree in the synthetic probes below."""
    findings: list[str] = []
    co.check_ref_scope_citation_anchor(findings)
    grouped: dict[str, set[str]] = defaultdict(set)
    for entry in findings:
        m = _FINDING_RE.match(entry)
        assert m, f"[ref-scope] finding format drifted, update this test's parser: {entry!r}"
        grouped[m.group("cited")].add(m.group("citer"))
    return grouped


def _ref_scope_violations(dominance_ceiling: int, known_backlog_ceiling: dict[str, int]) -> list[str]:
    """The guard itself: any cited file (by construction already over LARGE_FILE_THRESHOLD, or it
    would never appear in the findings at all) whose unanchored-citer count exceeds its ceiling -
    the default dominance ceiling, or a wider named-backlog override - is a violation. Message
    names the offending file, its size, its citer count, and the two remedies (trim or anchor)."""
    violations = []
    for cited, citers in sorted(_ref_scope_unanchored_citers().items()):
        ceiling = known_backlog_ceiling.get(cited, dominance_ceiling)
        if len(citers) <= ceiling:
            continue
        candidate = co.PLUGIN_ROOT / cited
        size = candidate.stat().st_size if candidate.is_file() else -1
        violations.append(
            f"'{cited}' ({size}B, over the {co.LARGE_FILE_THRESHOLD}B [ref-scope] threshold) is "
            f"cited without a '{co.SECTION_ANCHOR_CHARS} <anchor>' by {len(citers)} files "
            f"(ceiling {ceiling}): {sorted(citers)} - trim '{cited}' back to at most "
            f"{co.LARGE_FILE_THRESHOLD}B, or add '{co.SECTION_ANCHOR_CHARS} <anchor>' within "
            f"{co.REF_SCOPE_WINDOW} chars of the citation in each citer"
        )
    return violations


def test_ref_scope_real_tree_backlog_is_discovered():
    """Discovery floor: the real tree has a non-empty, already-documented [ref-scope] half (a)
    backlog (dominated by the two known files named above). A zero-length result here would mean
    either the detector broke or the backlog was fully swept - either way the dominance test below
    would be vacuous, so this floor makes that visible instead of silent."""
    grouped = _ref_scope_unanchored_citers()
    assert grouped, (
        "expected at least one real [ref-scope] finding (the known backlog) - if the backlog was "
        "legitimately swept to zero, that is good news, but tighten this test's assumptions "
        "deliberately rather than let it degrade into testing nothing"
    )


def test_known_backlog_ceilings_still_apply_to_real_oversize_files():
    """Every REF_SCOPE_KNOWN_BACKLOG_CEILING entry must still point at a file that is actually
    over LARGE_FILE_THRESHOLD - a stale entry (the file got trimmed or renamed) would silently
    widen the default ceiling for nothing, exactly the kind of drift this suite exists to catch."""
    for relpath in REF_SCOPE_KNOWN_BACKLOG_CEILING:
        path = co.PLUGIN_ROOT / relpath
        assert path.is_file(), f"known-backlog entry '{relpath}' no longer exists on disk"
        assert path.stat().st_size > co.LARGE_FILE_THRESHOLD, (
            f"known-backlog entry '{relpath}' is no longer over LARGE_FILE_THRESHOLD - drop its "
            f"ceiling override, it is covered by the default now"
        )


def test_no_cited_file_exceeds_its_dominance_ceiling():
    """THE guard. On the real tree, no cited file's unanchored-citer count may exceed its ceiling
    (the default REF_SCOPE_DOMINANCE_CITERS, or a named REF_SCOPE_KNOWN_BACKLOG_CEILING override).
    This is the test that goes RED when `snippets/state-root-resolution.md` (or ANY other file)
    crosses LARGE_FILE_THRESHOLD while cited widely - see the module docstring's red-before-green
    recipe."""
    violations = _ref_scope_violations(REF_SCOPE_DOMINANCE_CITERS, REF_SCOPE_KNOWN_BACKLOG_CEILING)
    assert not violations, "\n".join(violations)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _patch_fake_tree(monkeypatch, fake_root: Path) -> None:
    monkeypatch.setattr(co, "PLUGIN_ROOT", fake_root)
    monkeypatch.setattr(co, "SKILLS_DIR", fake_root / "skills")
    monkeypatch.setattr(co, "AGENTS_DIR", fake_root / "agents")


def test_synthetic_widely_cited_oversize_file_is_flagged(tmp_path, monkeypatch):
    """RED shape 1: a synthetic file over LARGE_FILE_THRESHOLD, cited by more than the dominance
    ceiling of distinct SKILL.md files, none carrying a '§' anchor near the citation - the exact
    shape state-root-resolution.md fell into. Must be flagged."""
    fake_root = tmp_path / "odoo-ai-agents"
    oversize = fake_root / "snippets" / "fake-hot.md"
    _write(oversize, "x" * (co.LARGE_FILE_THRESHOLD + 1))

    for i in range(4):  # 4 citers > ceiling of 3 used in this probe
        _write(
            fake_root / "skills" / f"s{i}" / "SKILL.md",
            "some unrelated prose here, then it cites snippets/fake-hot.md right in the middle "
            "of a sentence with no anchor character anywhere close to this citation at all.",
        )

    _patch_fake_tree(monkeypatch, fake_root)
    violations = _ref_scope_violations(dominance_ceiling=3, known_backlog_ceiling={})
    assert any("fake-hot.md" in v for v in violations), (
        f"expected a dominance violation for the synthetic oversize widely-cited file, got: {violations}"
    )


def test_synthetic_anchored_citation_is_not_flagged(tmp_path, monkeypatch):
    """GREEN counterpart: the identical oversize + wide-fan-in shape, but every citation carries a
    '§ <anchor>' within REF_SCOPE_WINDOW chars - proves the anchor exemption in the underlying
    check still reaches this test's wrapper, i.e. the guard does not fire on every hot file
    unconditionally, only on the unanchored ones."""
    fake_root = tmp_path / "odoo-ai-agents"
    oversize = fake_root / "snippets" / "fake-hot-anchored.md"
    _write(oversize, "x" * (co.LARGE_FILE_THRESHOLD + 1))

    for i in range(4):
        _write(
            fake_root / "skills" / f"s{i}" / "SKILL.md",
            "See snippets/fake-hot-anchored.md § Some Section for the full rule.",
        )

    _patch_fake_tree(monkeypatch, fake_root)
    violations = _ref_scope_violations(dominance_ceiling=3, known_backlog_ceiling={})
    assert not any("fake-hot-anchored.md" in v for v in violations), (
        f"anchored citations must not be flagged, got: {violations}"
    )


def test_synthetic_different_widely_cited_file_is_flagged(tmp_path, monkeypatch):
    """RED shape 2 (MUST-CATCH: a DIFFERENT file than state-root-resolution.md). Proves the guard
    is a relationship check (fan-in x size against the SAME imported threshold), not a hardcoded
    filename: an entirely different basename, in a different directory shape (skills/_shared/,
    mirroring odoo-frontend-fidelity.md's real location), crossing the threshold with wide
    unanchored fan-in must ALSO be flagged."""
    fake_root = tmp_path / "odoo-ai-agents"
    oversize = fake_root / "skills" / "_shared" / "completely-unrelated-name.md"
    _write(oversize, "y" * (co.LARGE_FILE_THRESHOLD + 1))

    for i in range(4):
        _write(
            fake_root / "agents" / f"a{i}.md",
            "read skills/_shared/completely-unrelated-name.md for the whole procedure before acting.",
        )

    _patch_fake_tree(monkeypatch, fake_root)
    violations = _ref_scope_violations(dominance_ceiling=3, known_backlog_ceiling={})
    assert any("completely-unrelated-name.md" in v for v in violations), (
        f"expected a dominance violation for a SECOND, differently-named oversize widely-cited "
        f"file - a filename-specific guard would miss this, got: {violations}"
    )


def test_synthetic_undersize_widely_cited_file_is_clean(tmp_path, monkeypatch):
    """GREEN control: wide fan-in alone, on a file UNDER LARGE_FILE_THRESHOLD, is not a violation -
    proves the guard gates on size x fan-in together, not fan-in alone."""
    fake_root = tmp_path / "odoo-ai-agents"
    undersize = fake_root / "snippets" / "fake-small.md"
    _write(undersize, "small file, well under the threshold")

    for i in range(4):
        _write(
            fake_root / "skills" / f"s{i}" / "SKILL.md",
            "cites snippets/fake-small.md with no anchor nearby whatsoever in this sentence.",
        )

    _patch_fake_tree(monkeypatch, fake_root)
    violations = _ref_scope_violations(dominance_ceiling=3, known_backlog_ceiling={})
    assert violations == [], f"expected zero violations for an under-threshold file, got: {violations}"


def test_synthetic_known_backlog_override_still_bounds_growth(tmp_path, monkeypatch):
    """The named-backlog ceiling is a WIDER bound, never an unconditional exemption: a synthetic
    file registered under a backlog override must still be flagged once its fan-in exceeds THAT
    override, proving the grandfather entry cannot be used to hide unbounded future growth."""
    fake_root = tmp_path / "odoo-ai-agents"
    oversize = fake_root / "snippets" / "fake-grandfathered.md"
    _write(oversize, "z" * (co.LARGE_FILE_THRESHOLD + 1))

    for i in range(5):  # 5 citers, override ceiling is 3 below
        _write(
            fake_root / "skills" / f"s{i}" / "SKILL.md",
            "cites snippets/fake-grandfathered.md with no anchor nearby whatsoever right here.",
        )

    _patch_fake_tree(monkeypatch, fake_root)
    violations = _ref_scope_violations(
        dominance_ceiling=1, known_backlog_ceiling={"snippets/fake-grandfathered.md": 3}
    )
    assert any("fake-grandfathered.md" in v for v in violations), (
        f"a named-backlog override must still fail once fan-in exceeds the override's OWN "
        f"ceiling, got: {violations}"
    )
