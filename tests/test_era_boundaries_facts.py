"""Positive-content guard for the corrected Odoo test base-class facts (issue #177, P1).

Business rule: `plugins/odoo-ai-agents/snippets/odoo-era-boundaries.md` rows 3 and 4 are the SSOT
for every Odoo test base-class window fact (which class exists on which series, when it is
deprecated/removed, and how to resolve a version-sensitive claim). This test protects the FACTS
themselves - not just their absence elsewhere (`test_excision_no_duplication.py` covers that) - so
a future edit could not silently drop a class, the >=v17 BREAKING rule, or the era1 carve-out
while still passing the excision guard.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SNIPPET = PLUGIN / "snippets" / "odoo-era-boundaries.md"
DETECTOR = PLUGIN / "scripts" / "lib" / "odoo_series.py"
TEST_WRITING_SKILL = PLUGIN / "skills" / "odoo-test-writing" / "SKILL.md"

_WS = re.compile(r"\s+")

# A dotted numeric value quoted in the prose, e.g. `17.0.1.0.0` or `1.0.9`. Anything with a letter or
# a placeholder bracket (`<major>.0.x.y`) is a shape sketch, not a value that can be executed.
_QUOTED_VERSION_RE = re.compile(r"`([0-9][0-9.]*)`")
# The divider the step-3 prose keeps between the values it calls candidates and the values it says
# yield nothing. Which SIDE a value sits on is the claim; each test below executes that claim.
_NOTHING_DIVIDER = "Every other value yields NOTHING:"

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


def test_row5_states_the_core_package_dir_boundary():
    """Row 5 is the SSOT for the core package directory era: `openerp/` on v8-v9, `odoo/` on v10+.
    A checkout-derivation step that probes only one of the two names finds NOTHING on the other era
    and fails silently, so the boundary AND the probe-both instruction must both be stated."""
    row5 = _row(5)
    assert "openerp/" in row5 and "odoo/" in row5, "row 5 must name both package dirs"
    assert "v8.0-v9.0" in row5, "row 5 must state the openerp/ window as v8.0-v9.0"
    assert "v10.0+" in row5, "row 5 must state the odoo/ window as v10.0+"
    assert "10.0" in row5, "row 5 must state the flip series"
    assert "BOTH" in row5, "row 5 must instruct that BOTH package dirs are probed from a checkout"


def test_row6_states_the_manifest_filename_boundary():
    """Row 6 is the SSOT for the descriptor filename era: `__openerp__.py` on v8-v9,
    `__manifest__.py` on v10+. Globbing one name alone is the confirmed silent-miss defect, so the
    both-names glob rule and the both-present precedence must both be stated."""
    row6 = _row(6)
    assert "__openerp__.py" in row6, "row 6 must name `__openerp__.py`"
    assert "__manifest__.py" in row6, "row 6 must name `__manifest__.py`"
    assert "v8.0-v9.0" in row6, "row 6 must state the __openerp__.py window as v8.0-v9.0"
    assert "v10.0+" in row6, "row 6 must state the __manifest__.py window as v10.0+"
    assert "BOTH" in row6, "row 6 must require a module glob to cover BOTH descriptor filenames"
    assert "silently ignores" in row6, (
        "row 6 must state the both-present precedence: Odoo loads __manifest__.py and silently "
        "ignores __openerp__.py"
    )


def _derivation_body() -> str:
    text = SNIPPET.read_text(encoding="utf-8")
    assert "## Series derivation from a checkout" in text, (
        "the era snippet must own the `## Series derivation from a checkout` section that "
        "project-facts-resolution.md rung 3 cites by anchor"
    )
    return text.split("## Series derivation from a checkout", 1)[1]


def _step3_prose() -> str:
    """The step-3 item of the ordered derivation, on its own."""
    body = _derivation_body()
    start = body.find("3. **The manifest")
    assert start != -1, "the derivation section must carry a step 3 for the manifest `version` key"
    end = body.find("\n4. **", start)
    assert end != -1, "step 3 must be followed by step 4"
    return body[start:end]


def _load_detect():
    spec = importlib.util.spec_from_file_location("odoo_series_for_doc_claims", DETECTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.detect


_detect = _load_detect()


def _detect_version(tmp_path: Path, version: str) -> dict:
    """Run the shipped detector against a throwaway one-addon tree carrying `version`."""
    mod = tmp_path / ("t_" + version.replace(".", "_")) / "addons" / "mod_x"
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "__manifest__.py").write_text(
        "{{'name': 'mod_x', 'version': {0!r}}}\n".format(version), encoding="utf-8"
    )
    return _detect(mod.parent.parent)


def test_series_derivation_section_is_terminating_and_never_defaults():
    """The derivation section must terminate at NEEDS_CONTEXT rather than guessing a series, and
    must state that a manifest `version` is never one - the two failure modes a guard exercising
    only a `17.0.1.0.0` manifest would go green while missing."""
    body = _derivation_body()
    assert "odoo_series.py detect" in body, "the section must name the shipped detector to run"
    assert "NEEDS_CONTEXT" in body, "the section must name the unresolved outcome"
    assert "Never substitute a default series" in body, (
        "the section must forbid defaulting to a series when derivation fails"
    )
    assert "a HINT, never a series" in _step3_prose(), (
        "step 3 must state that a manifest `version` is a hint and never a resolved series"
    )


def test_each_value_step3_calls_a_candidate_really_classifies_as_one(tmp_path):
    """A prose claim is EXECUTED here, not string-matched.

    The predecessor of this test asserted that the section contained the literal `1.0.9` labelled
    REJECTED - a claim the shipped detector contradicted, so CI actively pinned the wrong answer
    into the doc. Running each value the prose names through the detector cannot pin a wrong answer:
    doc and code must agree or one of them goes red."""
    head, divider, _ = _step3_prose().partition(_NOTHING_DIVIDER)
    assert divider, (
        f"step 3 must keep the {_NOTHING_DIVIDER!r} divider - it is what separates the values the "
        "prose calls candidates from the values it says yield nothing, and these tests execute both"
    )
    named = _QUOTED_VERSION_RE.findall(head)
    assert named, "step 3 must name at least one qualifying series-prefixed value"
    for version in named:
        res = _detect_version(tmp_path, version)
        assert res["step"] == "3", (
            f"the prose names {version!r} as a series-prefixed candidate, but the detector did not "
            "classify it"
        )
        assert res["series"] == "", "a manifest candidate must never arrive as a resolved series"
        assert f"{version.split('.')[0]}.0" in res["hint"]


def test_each_value_step3_calls_an_addons_own_really_yields_nothing(tmp_path):
    """The other side of the same divider, likewise executed. The values named here are the ones the
    original hole admitted, so the doc must keep naming them AND the detector must keep refusing
    them - neither a doc edit nor a code edit can satisfy this test alone."""
    _, divider, tail = _step3_prose().partition(_NOTHING_DIVIDER)
    assert divider
    named = _QUOTED_VERSION_RE.findall(tail)
    for must_name in ("1.0", "1.3", "1.0.9", "1.0.0"):
        assert must_name in named, (
            f"step 3 must name {must_name!r} among the values that yield no series - it is a real "
            "addon version, and the 3-segment ones are exactly the class the detector once admitted"
        )
    for version in named:
        res = _detect_version(tmp_path, version)
        assert res["status"] == "NEEDS_CONTEXT"
        assert res["series"] == "", f"{version!r} must never be returned as a series"
        assert res["step"] != "3", f"{version!r} must not even reach the candidate channel"
        assert res["hint"] == ""


def _count_normalized(phrase: str) -> dict:
    """Return {relpath: count} for `.md` files under the plugin tree where the
    whitespace-normalized `phrase` occurs (a full-tree scan, not just the SSOT snippet)."""
    needle = _WS.sub(" ", phrase)
    hits = {}
    for p in PLUGIN.rglob("*.md"):
        if p.is_file():
            n = _WS.sub(" ", p.read_text(encoding="utf-8")).count(needle)
            if n:
                hits[str(p.relative_to(PLUGIN))] = n
    return hits


def test_form_helper_window_is_v12_everywhere_not_v13():
    """Issue #177 twin survivor (R3 FIX 1): row 3 above and
    skills/odoo-test-writing/references/fp-adapt-mode.md both correctly state the Form/O2MForm
    window as v12+; skills/odoo-test-writing/SKILL.md Round 1 must not restate a divergent v13+
    window for the identical fact - it must cross-ref this SSOT instead. Guards against the wrong
    window drifting back in anywhere under plugins/."""
    for phrase in ("Form` helper (v13+)", "Form (v13"):
        hits = _count_normalized(phrase)
        assert sum(hits.values()) == 0, (
            f"Wrong Form-helper window {phrase!r} must not survive anywhere under plugins/; "
            f"found: {hits}"
        )
    text = TEST_WRITING_SKILL.read_text(encoding="utf-8")
    assert "Form` helper (v12+" in text, (
        "odoo-test-writing/SKILL.md Round 1 must state the Form helper window as v12+"
    )
    assert "odoo-era-boundaries.md" in text, (
        "odoo-test-writing/SKILL.md must cross-ref odoo-era-boundaries.md rather than restate "
        "the Form window inline"
    )
