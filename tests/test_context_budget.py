"""Guard [card-budget] (rule 13 in generator/check_orchestration.py, M9 in 12-design-final.md).

A "hot" contract is loaded into many cold agent contexts per run. Its size is therefore a
per-invocation cost, not a one-time one. `[card-budget]` asserts every hot file stays under its
declared budget, and a file becomes subject to the rule through EITHER of two doors:

  (a) DECLARED - it carries an entry in `tests/fixtures/card_budget_grandfather.json`. The entry
      is both the qualification and the budget, and it is measured wherever the file lives.
  (b) DISCOVERED - it is a `snippets/*.md` or `skills/_shared/*.md` file cited by >=3 distinct
      skills+agents, and its budget is the default 4,096 B cap.

Door (b) is a basename-keyed HEURISTIC for hotness; door (a) states the same fact outright, which
is the only way to cap a hot contract the heuristic structurally cannot see - a top-level
`skills/<name>/SKILL.md` runtime contract shares the basename `SKILL.md` with every skill, so no
basename citer count can single it out. `run-harness/SKILL.md` (the drive-to-done loop re-entered
on every RUN-DAG node and every resume) is capped through door (a) for exactly that reason.

The rule fires only on (a) a listed file that GREW past its recorded budget, or (b) a NEW file
entering the >=3-citer set above the default cap - never on a file merely existing above 4,096 B
with a grandfather/wave-13 entry that covers it.

This file is parametrized over the DISCOVERED hot set (never a hardcoded file list, mirroring
[role-scope]'s data-driven design) and includes synthetic-fixture self-checks that prove the
detector can actually go RED for the right reason - once per door - not just print "clean" forever.

Red-before-green proof for the self-checks (run manually):
    1. `test_synthetic_oversize_file_is_flagged` builds a >4096B fake file with 3 citers in a
       tmp_path tree and asserts check_card_budget flags it - this IS the red-before-green proof,
       committed as an executable test (not a manual step): comment out the size check in
       check_orchestration.py's check_card_budget and this test goes RED; restore it and it goes
       GREEN again.
    2. `test_synthetic_declared_file_outside_the_corpus_is_flagged` does the same for door (a):
       drop the grandfather-path union out of `_card_budget_candidates`, or restore the old
       "skip unless >=3 citers" gate ahead of the declared branch, and it goes RED.

Run: python -m pytest tests/test_context_budget.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
GRANDFATHER_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "card_budget_grandfather.json"

if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from generator import check_orchestration as co  # noqa: E402


def _grandfather() -> dict:
    return json.loads(GRANDFATHER_FIXTURE.read_text(encoding="utf-8"))


def test_grandfather_fixture_loads_and_is_nonempty():
    """Discovery floor - a broken/empty grandfather file would silently make every currently
    over-cap file (dozens on the real tree) fail [card-budget], which is exactly the false-red
    the fixture exists to prevent."""
    data = _grandfather()
    assert "budgets" in data and isinstance(data["budgets"], dict)
    assert len(data["budgets"]) >= 10, (
        f"expected a substantial grandfather list (>=10 entries), found {len(data['budgets'])} - "
        f"if this ever legitimately shrinks, update this floor deliberately, do not silently drop it"
    )


def test_wave13_grandfather_entries_match_actual_post_trim_size():
    """The base 27-ish-file block was generated ONCE, at the start of the wave, EXCLUDING wave 7's
    own 13 inverted files. Each of those 13 earns its OWN entry the moment it is trimmed and
    committed - that entry must be its file's actual post-trim size (never a stale earlier size,
    and never larger than what is really on disk, which would silently hide future regrowth)."""
    data = _grandfather()
    budgets = data["budgets"]
    missing = []
    mismatched = []
    for relpath in co.INVERTED_SNIPPETS:
        path = PLUGIN / relpath
        if not path.is_file():
            missing.append(relpath)
            continue
        actual = path.stat().st_size
        if actual <= co.CARD_BUDGET_DEFAULT_CAP:
            continue  # under the default cap - no entry needed, the default cap already covers it
        recorded = budgets.get(relpath)
        if recorded != actual:
            mismatched.append((relpath, recorded, actual))
    assert not missing, f"wave-13 file(s) missing from disk: {missing}"
    assert not mismatched, (
        f"wave-13 grandfather entries must equal the file's actual current size (recorded, actual): "
        f"{mismatched}"
    )


def test_card_budget_candidates_discovered():
    """Discovery floor for the parametrized real-tree check below."""
    candidates = co._card_budget_candidates()
    assert len(candidates) >= 40, f"expected >=40 candidate files, found {len(candidates)}"


REAL_CANDIDATES = sorted(co._card_budget_candidates())


@pytest.mark.parametrize(
    "path", REAL_CANDIDATES, ids=[str(p.relative_to(PLUGIN)) for p in REAL_CANDIDATES]
)
def test_real_tree_file_is_under_its_budget(path):
    """Every candidate on the real tree, individually - a per-file case (not one loop with one
    assertion) so a single regression names its own file instead of hiding behind an aggregate
    finding count. Budget resolution mirrors check_card_budget's two doors: a declared entry
    qualifies the file on its own; otherwise the >=3-citer heuristic decides."""
    grandfather = co._load_card_budget_grandfather()
    relpath = str(path.relative_to(PLUGIN))
    size = path.stat().st_size
    if relpath in grandfather:
        budget = grandfather[relpath]
        why = "declared hot contract - explicit budget entry"
    else:
        bodies = co._consumer_bodies()
        citers = sum(1 for text in bodies.values() if path.name in text)
        if citers < co.CARD_BUDGET_MIN_CITERS:
            pytest.skip(
                f"{path.name} is cited by {citers} < {co.CARD_BUDGET_MIN_CITERS}, not a hot file"
            )
        budget = co.CARD_BUDGET_DEFAULT_CAP
        why = f"cited by {citers} skills/agents"
    assert size <= budget, (
        f"{relpath} is {size}B, over its budget of {budget}B ({why}) - "
        f"either the trim regressed or a deliberate grandfather-file bump is needed"
    )


def test_every_declared_budget_path_exists_on_disk():
    """A budget entry is a live cap only while its path resolves. A rename or delete that leaves
    the entry behind silently drops the cap AND leaves the fixture asserting a file that is gone -
    both are how a capped contract quietly escapes the ratchet."""
    stale = [rel for rel in _grandfather()["budgets"] if not (PLUGIN / rel).is_file()]
    assert not stale, (
        f"grandfather entries point at path(s) that no longer exist: {stale} - move the budget to "
        f"the new path (keeping the cap) or delete the entry deliberately"
    )


def test_declared_paths_are_all_measured_wherever_they_live():
    """Door (a) contract: a declared entry qualifies the file on its own, so EVERY declared path
    must appear in the measured candidate set - including paths outside the snippets/ +
    skills/_shared/ corpus door (b) scans. Restrict `_card_budget_candidates` back to that corpus
    and this goes RED."""
    candidates = {str(p.relative_to(PLUGIN)) for p in co._card_budget_candidates()}
    missing = sorted(set(_grandfather()["budgets"]) - candidates)
    assert not missing, (
        f"declared budget path(s) never measured by [card-budget]: {missing} - the declaration is "
        f"supposed to be its own entry ticket, not decoration"
    )


def test_run_harness_runtime_contract_carries_a_budget():
    """`run-harness/SKILL.md` is the plugin's drive-to-done runtime contract: it is re-read on
    every RUN-DAG node dispatch and on every resume, so its size is a per-node cost - exactly what
    [card-budget] exists to ratchet. Door (b) cannot reach it (basename `SKILL.md` is shared by
    every skill), so it must be DECLARED. Drop the entry and this goes RED; grow the file past the
    recorded cap and the parametrized case above goes RED."""
    relpath = "skills/run-harness/SKILL.md"
    budgets = _grandfather()["budgets"]
    assert relpath in budgets, (
        f"{relpath} must carry an explicit [card-budget] entry - it is the most re-entered runtime "
        f"contract in the plugin and the citer heuristic structurally cannot cap it"
    )
    assert (PLUGIN / relpath).stat().st_size <= budgets[relpath]


def test_synthetic_oversize_file_is_flagged(tmp_path, monkeypatch):
    """Red-before-green self-check: a synthetic hot file over the default cap, with NO grandfather
    entry, must be flagged - proves the detector can actually fire, not just print clean forever."""
    fake_root = tmp_path / "odoo-ai-agents"
    (fake_root / "snippets").mkdir(parents=True)
    (fake_root / "skills" / "s1").mkdir(parents=True)
    (fake_root / "skills" / "s2").mkdir(parents=True)
    (fake_root / "skills" / "s3").mkdir(parents=True)
    (fake_root / "agents").mkdir(parents=True)

    oversize = fake_root / "snippets" / "fake-oversize.md"
    oversize.write_text("x" * (co.CARD_BUDGET_DEFAULT_CAP + 1), encoding="utf-8")

    for i in (1, 2, 3):
        (fake_root / "skills" / f"s{i}" / "SKILL.md").write_text(
            "cites fake-oversize.md right here", encoding="utf-8"
        )

    monkeypatch.setattr(co, "PLUGIN_ROOT", fake_root)
    monkeypatch.setattr(co, "SNIPPETS_DIR", fake_root / "snippets")
    monkeypatch.setattr(co, "SHARED_DIR", fake_root / "skills" / "_shared")
    monkeypatch.setattr(co, "SKILLS_DIR", fake_root / "skills")
    monkeypatch.setattr(co, "AGENTS_DIR", fake_root / "agents")
    monkeypatch.setattr(co, "REFERENCES_DIR", fake_root / "snippets" / "references")
    monkeypatch.setattr(co, "CARD_BUDGET_GRANDFATHER_FILE", tmp_path / "does-not-exist.json")

    findings: list[str] = []
    co.check_card_budget(findings)
    assert any("fake-oversize.md" in f for f in findings), (
        f"expected a [card-budget] finding for the synthetic oversize file, got: {findings}"
    )


def test_synthetic_declared_file_outside_the_corpus_is_flagged(tmp_path, monkeypatch):
    """Door (a) red-before-green: a file OUTSIDE the snippets/ + skills/_shared/ corpus, cited by
    NOBODY (0 citers - so door (b) can never reach it), carrying a declared budget it exceeds,
    must be flagged. This is the exact shape of `skills/run-harness/SKILL.md`; without the
    declared-path union in `_card_budget_candidates` the file is never even measured and the
    checker prints clean forever."""
    fake_root = tmp_path / "odoo-ai-agents"
    (fake_root / "snippets").mkdir(parents=True)
    (fake_root / "skills" / "driver").mkdir(parents=True)
    (fake_root / "agents").mkdir(parents=True)

    declared = fake_root / "skills" / "driver" / "SKILL.md"
    declared.write_text("y" * 500, encoding="utf-8")

    fixture = tmp_path / "budgets.json"
    fixture.write_text(
        json.dumps({"budgets": {"skills/driver/SKILL.md": 499}}), encoding="utf-8"
    )

    monkeypatch.setattr(co, "PLUGIN_ROOT", fake_root)
    monkeypatch.setattr(co, "SNIPPETS_DIR", fake_root / "snippets")
    monkeypatch.setattr(co, "SHARED_DIR", fake_root / "skills" / "_shared")
    monkeypatch.setattr(co, "SKILLS_DIR", fake_root / "skills")
    monkeypatch.setattr(co, "AGENTS_DIR", fake_root / "agents")
    monkeypatch.setattr(co, "REFERENCES_DIR", fake_root / "snippets" / "references")
    monkeypatch.setattr(co, "CARD_BUDGET_GRANDFATHER_FILE", fixture)

    findings: list[str] = []
    co.check_card_budget(findings)
    assert any("skills/driver/SKILL.md" in f for f in findings), (
        f"expected a [card-budget] finding for the declared out-of-corpus file, got: {findings}"
    )

    # GREEN counterpart on the same fixture: raise the budget to the actual size and it goes quiet,
    # proving the finding tracks SIZE-vs-BUDGET and not merely "this path is declared".
    fixture.write_text(
        json.dumps({"budgets": {"skills/driver/SKILL.md": 500}}), encoding="utf-8"
    )
    findings = []
    co.check_card_budget(findings)
    assert findings == [], f"expected zero findings once the budget covers the file, got: {findings}"


def test_synthetic_undersize_file_is_clean(tmp_path, monkeypatch):
    """GREEN counterpart: the same fixture shape but under the cap must produce zero findings -
    proves the detector does not fire on every hot file unconditionally."""
    fake_root = tmp_path / "odoo-ai-agents"
    (fake_root / "snippets").mkdir(parents=True)
    (fake_root / "skills" / "s1").mkdir(parents=True)
    (fake_root / "skills" / "s2").mkdir(parents=True)
    (fake_root / "skills" / "s3").mkdir(parents=True)
    (fake_root / "agents").mkdir(parents=True)

    undersize = fake_root / "snippets" / "fake-small.md"
    undersize.write_text("small file", encoding="utf-8")

    for i in (1, 2, 3):
        (fake_root / "skills" / f"s{i}" / "SKILL.md").write_text(
            "cites fake-small.md right here", encoding="utf-8"
        )

    monkeypatch.setattr(co, "PLUGIN_ROOT", fake_root)
    monkeypatch.setattr(co, "SNIPPETS_DIR", fake_root / "snippets")
    monkeypatch.setattr(co, "SHARED_DIR", fake_root / "skills" / "_shared")
    monkeypatch.setattr(co, "SKILLS_DIR", fake_root / "skills")
    monkeypatch.setattr(co, "AGENTS_DIR", fake_root / "agents")
    monkeypatch.setattr(co, "REFERENCES_DIR", fake_root / "snippets" / "references")
    monkeypatch.setattr(co, "CARD_BUDGET_GRANDFATHER_FILE", tmp_path / "does-not-exist.json")

    findings: list[str] = []
    co.check_card_budget(findings)
    assert findings == [], f"expected zero findings on an under-cap file, got: {findings}"
