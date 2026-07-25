"""Positive-content guard for the corrected Odoo test base-class facts (issue #177, P1).

Business rule: `plugins/odoo-ai-agents/snippets/odoo-era-boundaries.md` rows 3 and 4 are the SSOT
for every Odoo test base-class window fact (which class exists on which series, when it is
deprecated/removed, and how to resolve a version-sensitive claim). This test protects the FACTS
themselves - not just their absence elsewhere (`test_excision_no_duplication.py` covers that) - so
a future edit could not silently drop a class, the >=v17 BREAKING rule, or the era1 carve-out
while still passing the excision guard.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNIPPET = ROOT / "plugins" / "odoo-ai-agents" / "snippets" / "odoo-era-boundaries.md"

_ALL_EIGHT_TEST_BASE_CLASSES = (
    "TransactionCase",
    "SingleTransactionCase",
    "BaseCase",
    "HttpCase",
    "SavepointCase",
    "HttpSavepointCase",
    "TreeCase",
    "HttpCaseCommon",
)


def _row(n: int) -> str:
    """Return the raw markdown table row starting with '| n |' from the era-boundaries snippet."""
    text = SNIPPET.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith(f"| {n} |"):
            return line
    raise AssertionError(f"row {n} not found in {SNIPPET}")


def test_row3_names_all_eight_test_base_classes():
    row3 = _row(3)
    for cls in _ALL_EIGHT_TEST_BASE_CLASSES:
        assert f"`{cls}`" in row3, f"row 3 must name `{cls}` with its window; missing"


def test_row3_names_form_and_o2mform():
    row3 = _row(3)
    assert "`Form`" in row3, "row 3 must name `Form`"
    assert "O2MForm" in row3, "row 3 must name `O2MForm`"


def test_row3_states_the_v17_plus_breaking_rule():
    """>=v17 targets: SavepointCase/HttpSavepointCase DO NOT EXIST, so a surviving import is
    BREAKING - never a WARN. This is the corrected severity the deprecation-audit skill depends on."""
    row3 = _row(3)
    assert ">= v17" in row3, "row 3 must state the >=v17 target boundary"
    assert "BREAKING" in row3, "row 3 must state the BREAKING severity for a >=v17 target"
    assert "DO NOT EXIST" in row3, (
        "row 3 must state that SavepointCase/HttpSavepointCase do not exist at v17+"
    )


def test_row3_states_the_v8_v14_no_finding_rule():
    row3 = _row(3)
    assert "v8-v14" in row3 and "legitimate" in row3, (
        "row 3 must state SavepointCase is legitimate (no finding) on a v8-v14 target"
    )


def test_row3_states_the_osm_pattern_tiebreaker():
    """The OSM pattern `test-savepointcase-v8-v15` carries a historical, misleading id and gotcha
    text; row 3's own boundary (deprecated at v15) must be stated as the winner."""
    row3 = _row(3)
    assert "TIE-BREAKER" in row3, "row 3 must carry the OSM-pattern tie-breaker clause"
    assert "test-savepointcase-v8-v15" in row3, "the tie-breaker must cite the pattern id"
    assert "WINS" in row3, "the tie-breaker must state row 3's boundary wins over the pattern id"


def test_row4_states_authoritative_version_scoped_use():
    row4 = _row(4)
    assert "VERSION-SCOPED" in row4, "row 4 must state test_base_classes is version-scoped"
    assert "RETIRED" in row4, "row 4 must state the old distrust-the-tool directive is retired"


def test_row4_carries_the_v8_v9_era1_carveout():
    """v8/v9 print an addon-level regex-best-effort caveat that must NOT be read as downgrading
    the framework-level window in row 3."""
    row4 = _row(4)
    assert "era1" in row4, "row 4 must carry the v8/v9 era1 carve-out"
    assert "regex best-effort" in row4, "row 4 must quote the era1 caveat text"
    assert "FRAMEWORK" in row4, "row 4 must state the framework base menu stays authoritative"
