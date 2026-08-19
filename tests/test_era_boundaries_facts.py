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


def _row(n: int | str) -> str:
    """Return the raw markdown table row starting with '| n |' from the era-boundaries snippet.

    Accepts a string id so the sub-row `1b` is addressable the same way rows 1-7 are."""
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


def _count_normalized_repo(phrase: str) -> dict:
    """`_count_normalized`'s repo-wide sibling: `.md` files under the whole repo, not just the
    plugin tree. Needed because a wrong fact also gets restated in repo-root prose (CHANGELOG),
    which the plugin-scoped sweep cannot see - and a deletion that survives one file is not a
    deletion."""
    needle = _WS.sub(" ", phrase)
    hits = {}
    for p in ROOT.rglob("*.md"):
        if not p.is_file() or ".git" in p.parts or ".venv" in p.parts:
            continue
        n = _WS.sub(" ", p.read_text(encoding="utf-8")).count(needle)
        if n:
            hits[str(p.relative_to(ROOT))] = n
    return hits


# ---------------------------------------------------------------------------
# Row 1 - frontend module system (and the narrative that must NOT come back)
# ---------------------------------------------------------------------------

def test_row1_states_the_module_system_boundary_and_the_compat_shim():
    """Row 1 is the SSOT for the module-system era. Both halves are load-bearing: the boundary
    itself (legacy AMD/Widget through v14, ES6 modules from v15), AND the fact that `odoo.define()`
    stays LOADABLE past it - an adapt that deletes a working `odoo.define()` call on v16/v17
    because "the legacy system was removed" is the concrete harm this row prevents."""
    row1 = _row(1)
    assert "v8-v14" in row1, "row 1 must state the legacy module-system window"
    assert "v15+" in row1, "row 1 must state the modern ES6 module-system window"
    assert "compat shim" in row1, "row 1 must state that odoo.define() survives via a compat shim"
    assert "NOT removed at v16" in row1, (
        "row 1 must state that the legacy module system is NOT removed at v16 - the claim an "
        "agent will otherwise carry over from the pattern text it reads"
    )


def test_row1_carries_no_narrative_about_the_osm_server_being_wrong():
    """A boundary row's evidence column cites CALLS AND RESULTS. It must not argue with the OSM
    server, narrate a re-grounding session, or quote the wrong claim it is correcting: an executing
    agent gains nothing from the argument, and a quoted wrong claim is a wrong claim the next
    reader can lift out of context. Swept over the whole repo, not just this row, because the
    narrative's whole failure mode is being copied elsewhere."""
    for phrase in (
        "REFUTED server-text inaccuracy",
        "known wording bug in the SEPARATE OSM-server repo",
        "Re-grounded this session",
        "removed in v16",
    ):
        hits = _count_normalized_repo(phrase)
        assert not hits, (
            f"{phrase!r} must not survive in any committed markdown - it is narrative, or the "
            f"very claim the row corrects, not an instruction; found: {hits}"
        )


# ---------------------------------------------------------------------------
# Row 1b - OWL library major vs patch() arity (a DECOUPLED axis)
# ---------------------------------------------------------------------------

def test_row1b_keeps_owl_major_and_patch_arity_decoupled():
    """The two facts on this row travel together and are routinely conflated: OWL 2.x lands at
    v16, but `patch()` drops its `name` argument only at v17. Reading arity off the OWL major
    produces a 2-arg call on a v16 target (broken) or a 3-arg call on v17 (equally broken)."""
    row1b = _row("1b")
    assert "DECOUPLED" in row1b, "row 1b must state that the two axes are decoupled"
    assert "v16" in row1b, "row 1b must state where OWL 2.x lands"
    assert "patch(proto, name, obj)" in row1b, "row 1b must show the 3-arg signature"
    assert "patch(proto, obj)" in row1b, "row 1b must show the 2-arg signature"
    assert "v17" in row1b, "row 1b must state the series where the arity changes"
    assert "NOT a v16 marker" in row1b, (
        "row 1b must state explicitly that a 2-arg patch() call is a v17 marker, not a v16 one"
    )


# ---------------------------------------------------------------------------
# Row 2 - JS test framework: DOMINANCE, not replacement
# ---------------------------------------------------------------------------

def test_row2_states_dominance_not_replacement():
    """Row 2's rule is the one a JS test author, a log parser and a failure counter all read.
    Stated as a REPLACEMENT it makes every one of them series-gate to a single framework and drop
    real QUnit failures that still occur on v18/v19 (observed at runtime on both). Stated as
    DOMINANCE it makes them read both vocabularies, which is the only correct behavior."""
    row2 = _row(2)
    assert "DOMINANT" in row2, "row 2 must state Hoot becomes DOMINANT, not that it replaces QUnit"
    assert "does NOT replace QUnit" in row2, (
        "row 2 must say outright that Hoot does NOT replace QUnit - the absolute this row corrects"
    )
    assert "v18.0" in row2, "row 2 must name the series where Hoot becomes dominant"
    assert "still FAIL" in row2, (
        "row 2 must state that a QUnit suite can still FAIL after that point - the reason a "
        "counter may not skip it"
    )
    assert "NEVER series-gate" in row2, "row 2 must forbid series-gating a JS reader"
    assert "js_test_inspect(" in row2, (
        "row 2 must name the call that resolves the real per-module framework mix"
    )


def test_row2_evidence_shows_qunit_surviving_on_both_later_series():
    """The evidence column must show QUnit files present at BOTH v18 and v19. An evidence column
    that only proves Hoot's arrival is exactly what let the refuted absolute stand for so long -
    the row's own evidence already contradicted its rule."""
    row2 = _row(2)
    assert "'18.0'" in row2 and "'19.0'" in row2, (
        "row 2's evidence must cite the js_test_inspect calls for both later series"
    )
    assert "qunit 16" in row2 and "qunit 4" in row2, (
        "row 2's evidence must carry the surviving QUnit file counts at v18 and v19"
    )


def test_the_replaced_qunit_absolute_does_not_regrow_anywhere():
    """Whole-repo negative sweep for the refuted absolute, in every phrasing it shipped in."""
    for phrase in (
        "Hoot replaces QUnit",
        "QUnit through v17.0",
        "QUnit through v17",
    ):
        hits = _count_normalized_repo(phrase)
        assert not hits, (
            f"The refuted absolute {phrase!r} must not survive anywhere: QUnit still ships and "
            f"still fails on v18/v19. Found: {hits}"
        )


# ---------------------------------------------------------------------------
# Row 7 - core stylesheet language
# ---------------------------------------------------------------------------

def test_row7_states_the_stylesheet_language_boundary():
    """Row 7 exists because no SSOT owned this axis, so eleven files each invented a window and
    all eleven were wrong (core `web` ships ZERO `.less` files at v8 and ZERO at v12). The row
    must carry the real windows AND the per-module resolution instruction, because the windows
    describe core `web` only."""
    row7 = _row(7)
    assert "v8.0" in row7 and "CSS" in row7, "row 7 must state that v8.0 is plain CSS only"
    assert "v9.0-v11.0" in row7, "row 7 must state the LESS window as v9.0-v11.0"
    assert "v12.0 onward" in row7, "row 7 must state SCSS from v12.0 onward"
    assert "resolve_stylesheet(" in row7, (
        "row 7 must name the call that resolves a module's real stylesheet language"
    )
    assert "never infer" in row7.lower(), (
        "row 7 must forbid inferring a module's stylesheet language from the series alone"
    )


def test_row7_evidence_proves_both_edges_of_the_less_window():
    """Both edges, not one: the committed wrong windows (`v8-v11`, `~v8-v12`) were wrong at the
    LOW end and the HIGH end respectively, so evidence for only one edge would have left half of
    them looking defensible."""
    row7 = _row(7)
    assert "'8.0'" in row7 and "zero `.less`" in row7, (
        "row 7's evidence must show v8.0 shipping zero .less files (the low edge)"
    )
    assert "'12.0'" in row7 and "63 `scss`" in row7, (
        "row 7's evidence must show v12.0 already fully SCSS (the high edge)"
    )


def test_no_committed_file_states_a_stylesheet_language_window():
    """Whole-repo sweep: with row 7 in place, no other file may restate a LESS/SCSS era window.

    Every phrase below was committed somewhere in this repo and every one of them is refuted by
    `resolve_stylesheet('web', <series>)`."""
    for phrase in (
        "LESS covers legacy v8-v11",
        "LESS covers the legacy pre-SCSS era",
        "LESS for the legacy pre-SCSS era",
        "LESS targets legacy v8-v11 modules",
        "LESS bao phủ kỷ nguyên cũ tiền-SCSS",
        "LESS cho kỷ nguyên cũ tiền-SCSS",
    ):
        hits = _count_normalized_repo(phrase)
        assert not hits, (
            f"Stylesheet-era window {phrase!r} must live only in odoo-era-boundaries.md row 7; "
            f"found: {hits}"
        )
    row7 = _row(7)
    assert "less" in row7.lower(), "row 7 itself must still own the LESS window"


# ---------------------------------------------------------------------------
# The other corrected facts must not regrow either
# ---------------------------------------------------------------------------

def test_corrected_version_facts_do_not_regrow():
    """One sweep per corrected fact, each phrase verified WRONG against the odoo-semantic index:

    - `--load-language` is `Status: stable` on every indexed series, 8.0 through 19.0; only
      `--i18n-export` is absent at 19.0, so "the server-flag form ... is GONE" is false.
    - `.svg` is already in `_get_icon_image`'s accepted extension set well before v19 (and v13 has
      no extension filter at all), so gating an SVG icon on v19 is false.
    - the server registers `standard_viindoo_8` through `standard_viindoo_19`, so naming only
      17/18 teaches an agent the family stops there.
    - neither `odoo-forward-port` nor `odoo-solution-design` contains any file-count or
      module-count threshold, so attributing one to them is a borrowed authority that does not
      exist."""
    for phrase, why in (
        ("`--load-language`) is GONE",
         "--load-language is stable on every indexed series"),
        ("plus icon.svg on v19",
         "SVG module icons predate v19"),
        ("`icon` key on v19",
         "the manifest icon key is read well before v19"),
        ("`standard_viindoo_17/18`",
         "the profile family spans every indexed series"),
        ("> 3 files** OR **>= 2 modules",
         "no named source defines that threshold"),
        ("spans > 3 files or >= 2 modules",
         "no named source defines that threshold"),
        ("spans > 3 files / >= 2 modules",
         "no named source defines that threshold"),
        ("small/large boundary forward-port and solution-design already use",
         "neither file contains the threshold it is attributed to"),
    ):
        hits = _count_normalized_repo(phrase)
        assert not hits, f"{phrase!r} must not survive ({why}); found: {hits}"
