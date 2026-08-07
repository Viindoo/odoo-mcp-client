"""Behavior tests for scripts/lib/odoo_series.py - the Odoo series derivation helper.

Protects the ORDERED DERIVATION CONTRACT (design note Section E.5/E.6), not the
implementation: given a checkout on disk, the helper must return the Odoo major
series ("X.0") the checkout actually is, using the strongest evidence available,
and must NEVER guess a series when the evidence does not support one.

This is a replacement for a version-INCORRECT prose heuristic ("find the first
__manifest__.py, read `version`, take the first two dotted components") that
failed silently in two independent ways:
  - it finds NOTHING on v8.0/v9.0, whose descriptor file is `__openerp__.py`;
  - even where it finds a file, the `version` key's first two components are
    the ADDON's own version, not the series - stock core `base` declares the
    short form `1.3`/`1.4` on every indexed series, never the series itself.

A manifest `version` is on the WEAK side of that contract: it is the ADDON's own
version number, a different kind of fact from `release.py` or a series-named
branch, and this ecosystem's upgrade convention freezes it across a code-level
upgrade. So only steps 1-2 may resolve a series; a series-prefixed manifest is
surfaced as an explicitly unconfirmed HINT with NEEDS_CONTEXT and exit 3, never
as `SERIES` and never with `SERIES_STATUS=OK`.

Every case below is built from a throwaway tmp_path fixture tree - never this
machine's real Odoo checkout, never a real ~/.odoo-ai/instances.toml - so the
suite is portable to any machine (this repo is public).

Each test asserts on the documented OBSERVABLE contract - the `detect()` result
mapping for the classifier sweeps, and the CLI's KEY=VALUE lines + exit code for
the end-to-end cases, with one parity test binding the two - never on which
internal function ran. So a correct internal refactor can never break these
tests, and each is capable of failing for the right reason (a wrong series, an
addon's own version leaking through as one, a candidate promoted to a result, or
a silent default) rather than always passing.
"""

from __future__ import annotations

import importlib.util
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "odoo_series.py"


def _load_detect():
    spec = importlib.util.spec_from_file_location("odoo_series_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.detect


detect = _load_detect()

# The era floor for a series-prefixed manifest `version`, stated here INDEPENDENTLY of the script's
# own constant so these tests check the rule rather than echo it: 8.0 is the oldest series the era
# boundaries cover (snippets/odoo-era-boundaries.md rows 5-6). A leading major below it is an
# addon's own version number. There is deliberately NO ceiling - see the no-ceiling sweep below.
ERA_FLOOR_MAJOR = 8

# ---------------------------------------------------------------------------- #
# The manifest-version corpus, pinned in ONE place so a new observation is added
# once. The real values are what the OSM index reports for core (`Viindoo/odoo`)
# and for the Viindoo addon repos (`tvtmaaddons`, `erponline-enterprise`) across
# the 12 indexed series, joined by the shapes this plugin's own manifest and
# upgrade conventions name in prose.
# ---------------------------------------------------------------------------- #
ADDON_OWN_VERSIONS = (
    # 2 segments - real, core and Viindoo addons alike
    "1.0", "1.1", "1.2", "1.3", "1.4", "1.19", "0.1", "0.2", "0.8",
    # series-SHAPED but only 2 segments: no module ships it, and it is indistinguishable from the
    # short forms above, so it must not be read as a series either
    "17.0",
    # 3 segments whose SECOND segment is `0` - the class that reads like a series and is not one.
    # `1.0.9` and `1.0.6` are real Viindoo modules at 17.0; `1.0.0` is the greenfield short form
    # this plugin's own manifest guidance names.
    "1.0.9", "1.0.6", "1.0.0", "0.0.1", "0.0.0", "2.0.1", "3.0.0",
    # 3 segments, second segment non-zero - all real, plus `1.2.0` from the upgrade conventions
    "0.1.3", "0.1.4", "0.1.6", "0.2.3", "0.2.6", "0.5.5", "1.2.0",
    # a leading major below the era floor, at every segment count that could otherwise qualify
    "7.0.1.0.0", "1.0.1.0.0", "0.0.1.0.0", "99.0.1",
    # malformed / degenerate, including a decorated series prefix: the classifier is anchored at
    # both ends, so a prefix or suffix around an otherwise-valid value does not qualify
    "", "1", "abc", ".0.1", "1.0.", "v17.0.1.0.0", "17.0.1.0.0-rc1",
)

SERIES_PREFIXED_VERSIONS = {
    "17.0.1.0.0": "17.0",  # the canonical 5-segment form
    "16.0.2.3.0": "16.0",  # the example this plugin's manifest guidance names
    "8.0.1.0.0": "8.0",  # the era floor
    "19.0.1.0.0": "19.0",  # the newest series indexed today
    "20.0.1.0.0": "20.0",  # past it - must classify with no code change when v20 ships
    "10.0.1.0": "10.0",  # 4 segments - the segment floor, pinned deliberately
    "12.0.3.0.0": "12.0",
}

# The live reproduction: six real modules from one Viindoo addons repo at 17.0. Five of the six
# have a second segment of `0` or agree on a leading `1`/`0`, so a rule keyed on either one reads
# this v17 checkout as series "1.0" - with unanimity, not disagreement, to hide behind.
REAL_VIINDOO_ADDONS_TREE = {
    "to_odoo_module": "1.0.9",
    "viin_helpdesk": "1.0.6",
    "to_base": "0.5.5",
    "viin_account": "0.2.3",
    "to_odoo_version": "0.2.6",
    "to_product_license": "0.2",
}

_GIT_ENV_EXTRA = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@test.invalid",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@test.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}

requires_git = pytest.mark.skipif(
    __import__("shutil").which("git") is None, reason="git not available"
)


def _run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "detect", str(root)],
        capture_output=True,
        text=True,
    )


def _parse(stdout: str) -> dict:
    out = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, _, raw = line.partition("=")
        vals = shlex.split(raw)
        out[key] = vals[0] if vals else ""
    return out


def _git(args, cwd: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, **_GIT_ENV_EXTRA}
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env)


def _module(root: Path, name: str, version: str) -> Path:
    """Write one addon under `<root>/addons/<name>` carrying `version`, and return its directory."""
    mod = root / "addons" / name
    mod.mkdir(parents=True)
    (mod / "__manifest__.py").write_text(
        "{{'name': {0!r}, 'version': {1!r}}}\n".format(name, version), encoding="utf-8"
    )
    return mod


def _init_repo_on_branch(path: Path, branch: str) -> None:
    """A minimal git repo, checked out on `branch` (worktree add / rev-parse
    need a real commit to resolve HEAD against)."""
    path.mkdir(parents=True, exist_ok=True)
    assert _git(["init", "-q", "-b", branch], path).returncode == 0
    (path / "README.md").write_text("x", encoding="utf-8")
    assert _git(["add", "README.md"], path).returncode == 0
    r = _git(["commit", "-q", "-m", "init"], path)
    assert r.returncode == 0, r.stderr


# --------------------------------------------------------------------------- #
# E.6 case 1 - v8/v9 era, no __manifest__.py anywhere -> step 1, not empty
# --------------------------------------------------------------------------- #
def test_v8_v9_era_release_py_resolves_series_not_empty(tmp_path):
    """The historical bug: the old heuristic found NOTHING on v8/v9 because it
    only ever looked for __manifest__.py. A checkout whose core package is
    `openerp/` (v8/v9's package dir) must still resolve a series via release.py,
    and the result must not be blank."""
    root = tmp_path / "checkout"
    (root / "openerp").mkdir(parents=True)
    (root / "openerp" / "release.py").write_text(
        "version_info = (8, 0, 0, 'final', 0, '')\n", encoding="utf-8"
    )
    mod = root / "openerp" / "addons" / "base"
    mod.mkdir(parents=True)
    (mod / "__openerp__.py").write_text("{'name': 'base'}\n", encoding="utf-8")

    proc = _run(root)
    out = _parse(proc.stdout)
    assert proc.returncode == 0, proc.stderr
    assert out["SERIES_STATUS"] == "OK"
    assert out["SERIES"] != ""
    assert out["SERIES"] in ("8.0", "9.0")
    assert out["SERIES_STEP"] == "1"


# --------------------------------------------------------------------------- #
# E.6 case 2 - stock-core short manifest version '1.3', no release.py
# -> must REJECT the short form, must NOT return '1.3'
# --------------------------------------------------------------------------- #
def test_stock_core_short_manifest_version_is_rejected_not_returned(tmp_path):
    """The historical bug: 'take the first two dotted components of `version`'
    confidently returns '1.3' - core `base`'s own short-form version - on every
    indexed series. The helper must reject that value outright: not as a series,
    and not as a candidate either. An assertion on `SERIES` alone would pass with
    step 3 deleted, so the hint channel must be asserted EMPTY too - that is what
    makes this test capable of failing when the classifier admits the value."""
    root = tmp_path / "checkout"
    mod = root / "addons" / "base"
    mod.mkdir(parents=True)
    (mod / "__manifest__.py").write_text(
        "{'name': 'base', 'version': '1.3'}\n", encoding="utf-8"
    )

    proc = _run(root)
    out = _parse(proc.stdout)
    assert out["SERIES"] != "1.3"
    assert out["SERIES"] != "1.0.0"
    # Falls to a later, weaker step (era-only here: only __manifest__.py exists,
    # no release.py, no git branch, no series-prefixed manifest version anywhere).
    assert out["SERIES_STATUS"] == "NEEDS_CONTEXT"
    assert out["SERIES"] == ""
    assert out["SERIES_STEP"] == "4"
    assert out["SERIES_HINT"] == "", (
        "an addon's own version must not surface as a candidate hint either - it is not weak "
        "evidence of a series, it is evidence of nothing"
    )
    assert proc.returncode == 3


# --------------------------------------------------------------------------- #
# E.6 case 3 - nested layout: <root>/<series>/odoo/release.py -> found
# --------------------------------------------------------------------------- #
def test_nested_release_py_is_found_past_shallow_depth(tmp_path):
    root = tmp_path / "checkout"
    nested = root / "x1" / "x2" / "x3" / "odoo"
    nested.mkdir(parents=True)
    (nested / "release.py").write_text(
        "version_info = (17, 0, 0, 'final', 0, '')\n", encoding="utf-8"
    )

    proc = _run(root)
    out = _parse(proc.stdout)
    assert proc.returncode == 0, proc.stderr
    assert out["SERIES"] == "17.0"
    assert out["SERIES_STEP"] == "1"
    assert "release.py" in out["SERIES_EVIDENCE"]


# --------------------------------------------------------------------------- #
# E.6 case 4 - addons-only repo on a series branch -> step 2
# --------------------------------------------------------------------------- #
@requires_git
def test_addons_only_repo_on_series_branch_resolves_via_branch(tmp_path):
    root = tmp_path / "checkout"
    _init_repo_on_branch(root, "17.0")
    mod = root / "addons" / "base"
    mod.mkdir(parents=True)
    # Short-form versions everywhere - must NOT be mistaken for evidence.
    (mod / "__manifest__.py").write_text(
        "{'name': 'base', 'version': '1.3'}\n", encoding="utf-8"
    )

    proc = _run(root)
    out = _parse(proc.stdout)
    assert proc.returncode == 0, proc.stderr
    assert out["SERIES"] == "17.0"
    assert out["SERIES_STEP"] == "2"
    assert out["SERIES_EVIDENCE"] == "17.0"


# --------------------------------------------------------------------------- #
# E.6 case 5 - addons-only repo on a feature branch, series-prefixed manifest
# -> the value is surfaced as a HINT at step 3, never as a resolved series
# --------------------------------------------------------------------------- #
@requires_git
def test_cli_surfaces_a_series_prefixed_manifest_as_a_weak_hint_and_exits_3(tmp_path):
    """The one shape a manifest `version` could ever speak for: a repo whose
    manifests carry a series prefix, sitting on a feature branch so the branch
    step cannot answer. The value is still not the series - the SAME bytes on
    disk describe a repo already upgraded past that prefix, because a code-level
    upgrade leaves `version` unbumped. So it arrives as an explicitly
    unconfirmed hint with NEEDS_CONTEXT and exit 3: a caller testing
    `$? -eq 0` can never spend a manifest guess as a resolved series.

    This is also the parity test binding the CLI's KEY=VALUE contract to the
    `detect()` mapping the classifier sweeps below assert on."""
    root = tmp_path / "checkout"
    _init_repo_on_branch(root, "feature/x")
    mod = _module(root, "custom_module", "17.0.1.0.0")

    proc = _run(root)
    out = _parse(proc.stdout)
    assert proc.returncode == 3, proc.stdout
    assert out["SERIES_STATUS"] == "NEEDS_CONTEXT"
    assert out["SERIES"] == "", "a manifest `version` must never populate SERIES"
    assert out["SERIES_STEP"] == "3"
    assert "17.0" in out["SERIES_HINT"]
    assert "UNCONFIRMED" in out["SERIES_HINT"]
    assert "custom_module" in out["SERIES_EVIDENCE"]

    in_process = detect(root)
    assert in_process["status"] == out["SERIES_STATUS"]
    assert in_process["series"] == out["SERIES"]
    assert in_process["step"] == out["SERIES_STEP"]
    assert in_process["hint"] == out["SERIES_HINT"]
    assert in_process["evidence"] == out["SERIES_EVIDENCE"]
    assert str(mod) in in_process["evidence"]


# --------------------------------------------------------------------------- #
# E.6 case 6 - both descriptor files in one addon -> __manifest__.py wins;
# era reported as v10+ (NEEDS_CONTEXT, never a guessed series)
# --------------------------------------------------------------------------- #
def test_both_descriptor_files_present_manifest_wins_era_v10_plus(tmp_path):
    root = tmp_path / "checkout"
    mod = root / "addons" / "legacy_dual"
    mod.mkdir(parents=True)
    (mod / "__manifest__.py").write_text(
        "{'name': 'legacy_dual', 'version': '1.0'}\n", encoding="utf-8"
    )
    (mod / "__openerp__.py").write_text("{'name': 'legacy_dual'}\n", encoding="utf-8")

    proc = _run(root)
    out = _parse(proc.stdout)
    assert out["SERIES_STATUS"] == "NEEDS_CONTEXT"
    assert out["SERIES"] == ""
    assert out["SERIES_STEP"] == "4"
    assert out["SERIES_ERA"] == "10.0+"
    assert out["SERIES_HINT"] == "", (
        "`1.0` is the addon's own version - it must reach neither SERIES nor the hint channel; "
        "without this assertion the case passes with the manifest step deleted entirely"
    )
    assert proc.returncode == 3


# --------------------------------------------------------------------------- #
# E.6 case 7 - nothing resolvable: empty tree -> NEEDS_CONTEXT, never a
# default series
# --------------------------------------------------------------------------- #
def test_empty_tree_yields_needs_context_never_a_default_series(tmp_path):
    root = tmp_path / "checkout"
    root.mkdir()

    proc = _run(root)
    out = _parse(proc.stdout)
    assert out["SERIES_STATUS"] == "NEEDS_CONTEXT"
    assert out["SERIES"] == ""
    assert out["SERIES_STEP"] == ""
    assert out["SERIES_ERA"] == ""
    assert out["SERIES_HINT"] == ""
    assert proc.returncode == 3


# --------------------------------------------------------------------------- #
# Extra coverage beyond the 7 required cases - other paths E.5 documents
# explicitly, cheap to protect once the fixtures above already exist.
# --------------------------------------------------------------------------- #
def test_major_version_plain_literal_is_preferred_over_version_info(tmp_path):
    """Step 1's stated priority: `major_version` wins over `version_info` when
    both are present as plain literals."""
    root = tmp_path / "checkout"
    (root / "odoo").mkdir(parents=True)
    (root / "odoo" / "release.py").write_text(
        "major_version = '19.0'\n"
        "version_info = (18, 0, 0, 'final', 0, '')\n",
        encoding="utf-8",
    )

    proc = _run(root)
    out = _parse(proc.stdout)
    assert proc.returncode == 0, proc.stderr
    assert out["SERIES"] == "19.0"
    assert out["SERIES_STEP"] == "1"


def test_saas_string_major_forces_minor_zero(tmp_path):
    """A SaaS build spells the first version_info element as a string like
    'saas~17.2' - the numeric major must be extracted and the minor forced to
    .0, never left as '17.2' or similarly malformed."""
    root = tmp_path / "checkout"
    (root / "odoo").mkdir(parents=True)
    (root / "odoo" / "release.py").write_text(
        "version_info = ('saas~17.2', 0, 0, 'final', 0, '')\n", encoding="utf-8"
    )

    proc = _run(root)
    out = _parse(proc.stdout)
    assert proc.returncode == 0, proc.stderr
    assert out["SERIES"] == "17.0"
    assert out["SERIES_STEP"] == "1"


def test_release_py_contradicting_its_own_package_dir_is_distrusted(tmp_path):
    """Cross-check: a release.py found under openerp/ (the v8/v9 package dir)
    that claims a v17 major contradicts the structural fact of which package
    dir it lives in. The candidate must be skipped, not returned - falling
    through to a weaker step rather than trusting the contradicted literal."""
    root = tmp_path / "checkout"
    (root / "openerp").mkdir(parents=True)
    (root / "openerp" / "release.py").write_text(
        "version_info = (17, 0, 0, 'final', 0, '')\n", encoding="utf-8"
    )

    proc = _run(root)
    out = _parse(proc.stdout)
    assert out["SERIES"] != "17.0"
    assert out["SERIES_STATUS"] == "NEEDS_CONTEXT"


def test_disagreeing_series_prefixed_manifests_emit_no_candidate_at_all(tmp_path):
    """Two modules naming different series: neither may be picked, and - the part
    an assertion on `SERIES` alone cannot see, since NEEDS_CONTEXT holds even with
    the manifest step deleted - neither may reach the hint channel either. A
    majority vote or a first-wins pick here would hand the caller a hypothesis
    the tree actively contradicts."""
    root = tmp_path / "checkout"
    _module(root, "mod_a", "16.0.1.0.0")
    _module(root, "mod_b", "17.0.2.0.0")

    proc = _run(root)
    out = _parse(proc.stdout)
    assert out["SERIES"] not in ("16.0", "17.0")
    assert out["SERIES_STATUS"] == "NEEDS_CONTEXT"
    assert out["SERIES_STEP"] == "4", "a disagreeing tree must fall past the manifest step"
    assert out["SERIES_HINT"] == ""
    assert "16.0" not in out["SERIES_HINT"] and "17.0" not in out["SERIES_HINT"]


# --------------------------------------------------------------------------- #
# The classifier, over the whole CLASS rather than one example per class. The
# hole this suite exists to close was reachable precisely because the rejection
# side was exercised by two strings, both 2-segment.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("version", ADDON_OWN_VERSIONS)
def test_an_addons_own_version_is_never_series_evidence(tmp_path, version):
    """A manifest `version` that is not series-prefixed is evidence of NOTHING:
    no series, and no candidate. Every string here is either a real value the
    index reports for a core or Viindoo module, a shape this plugin's own manifest
    and upgrade conventions name, or a degenerate form; the tree must fall through
    to the era-only step, which is all a bare `__manifest__.py` actually proves."""
    root = tmp_path / "checkout"
    _module(root, "mod_x", version)

    res = detect(root)
    assert res["status"] == "NEEDS_CONTEXT"
    assert res["series"] == ""
    assert res["step"] == "4", f"{version!r} must not be read as series evidence"
    assert res["era"] == "10.0+"
    assert res["hint"] == ""


@pytest.mark.parametrize("segment_tail", (".1", ".1.0", ".1.0.0"))
@pytest.mark.parametrize("major", tuple(range(0, ERA_FLOOR_MAJOR)))
def test_a_major_below_the_era_floor_never_qualifies_at_any_segment_count(
    tmp_path, major, segment_tail
):
    """The floor sweep: every major below the era floor, crossed with 3, 4 and 5
    segments and a second segment of `0` - the exact shape a series-prefixed
    version has. This proves the FLOOR, not one example of it: the real-world
    short-form population lives at majors 0 and 1, and the second segment
    discriminates nothing because short forms hit `0` constantly."""
    root = tmp_path / "checkout"
    _module(root, "mod_x", f"{major}.0{segment_tail}")

    res = detect(root)
    assert res["status"] == "NEEDS_CONTEXT"
    assert res["series"] == ""
    assert res["step"] == "4"
    assert res["hint"] == ""


@pytest.mark.parametrize(
    "version,series", tuple(sorted(SERIES_PREFIXED_VERSIONS.items()))
)
def test_a_series_prefixed_manifest_is_a_candidate_hint_never_a_result(tmp_path, version, series):
    """The accept side. A qualifying value earns a HINT and nothing more: the
    status stays NEEDS_CONTEXT, `SERIES` stays empty, and the hint carries both
    the candidate and the reason it cannot be trusted, so the caller confirms it
    at a later rung instead of spending it."""
    root = tmp_path / "checkout"
    mod = _module(root, "mod_x", version)

    res = detect(root)
    assert res["status"] == "NEEDS_CONTEXT"
    assert res["series"] == ""
    assert res["step"] == "3"
    assert series in res["hint"]
    assert "UNCONFIRMED" in res["hint"]
    assert "unbumped" in res["hint"], (
        "the hint must name WHY it is weak - a code-level upgrade leaves the manifest version "
        "unbumped - or a reader treats the candidate as an answer"
    )
    assert str(mod) in res["evidence"]


@pytest.mark.parametrize("major", tuple(range(ERA_FLOOR_MAJOR, 26)))
def test_the_era_floor_has_no_ceiling(tmp_path, major):
    """Every major at or above the floor classifies, including majors past the
    newest series indexed today. A closed range would pass today and start
    silently withholding the candidate the release after next; this sweep is the
    regression that closes that door, and it must stay green with no code edit
    when the next major ships."""
    root = tmp_path / "checkout"
    _module(root, "mod_x", f"{major}.0.1.0.0")

    res = detect(root)
    assert res["step"] == "3", f"major {major} must still classify - the floor has no ceiling"
    assert f"{major}.0" in res["hint"]
    assert res["series"] == "", "still a candidate, never a result"


def test_a_real_viindoo_addons_tree_yields_neither_a_series_nor_a_candidate(tmp_path):
    """The live reproduction, from real indexed module versions: six modules whose
    values agree on a leading `1`/`0` and mostly on a second segment of `0`. A
    rule keyed on either one reports series "1.0" for what is a v17 checkout, with
    unanimity rather than disagreement to hide behind - which is exactly why
    agreement across candidates can never be credited as protection."""
    root = tmp_path / "checkout"
    for name, version in REAL_VIINDOO_ADDONS_TREE.items():
        _module(root, name, version)

    proc = _run(root)
    out = _parse(proc.stdout)
    assert out["SERIES"] != "1.0"
    assert out["SERIES"] == ""
    assert out["SERIES_STATUS"] == "NEEDS_CONTEXT"
    assert out["SERIES_STEP"] == "4"
    assert out["SERIES_HINT"] == ""
    assert proc.returncode == 3


def test_agreement_across_candidates_is_not_the_classifier(tmp_path):
    """Two REAL Viindoo module versions, `1.0.9` and `1.0.6`, agree perfectly on a
    leading `1.0`. Agreement guards a heterogeneous tree; it is structurally blind
    to one rule applied uniformly to the wrong field, so the classifier - not the
    agreement gate - has to be what rejects these."""
    root = tmp_path / "checkout"
    _module(root, "to_odoo_module", "1.0.9")
    _module(root, "viin_helpdesk", "1.0.6")

    res = detect(root)
    assert res["series"] == ""
    assert res["step"] == "4"
    assert "1.0" not in res["hint"]
    assert res["hint"] == ""


def test_a_lone_series_prefixed_manifest_is_found_behind_many_short_form_siblings(tmp_path):
    """No candidate may be hidden by how many siblings a tree happens to have, or
    by the order the filesystem hands them back. The series-prefixed module is
    created FIRST here, so on any filesystem whose directory order tracks creation
    order it sits beyond the reach of a scan that stops early - and a truncating
    scan would also make the answer depend on `os.walk` ordering, which is not a
    property of the checkout at all."""
    root = tmp_path / "checkout"
    prefixed = _module(root, "series_prefixed_mod", "17.0.1.0.0")
    for i in range(25):
        _module(root, f"mod_{i:02d}", "1.0")

    res = detect(root)
    assert res["step"] == "3", "the one series-prefixed manifest must still be read"
    assert "17.0" in res["hint"]
    assert str(prefixed) in res["evidence"]
    assert res["series"] == ""


def test_a_disagreement_hidden_behind_many_siblings_is_still_seen(tmp_path):
    """The other half of the same property: if a scan stops early it can also miss
    the manifest that CONTRADICTS the candidate, turning a genuinely inconclusive
    tree into a confident one."""
    root = tmp_path / "checkout"
    _module(root, "mod_prefixed_a", "16.0.1.0.0")
    _module(root, "mod_prefixed_b", "17.0.1.0.0")
    for i in range(25):
        _module(root, f"mod_{i:02d}", "1.0")

    res = detect(root)
    assert res["step"] == "4"
    assert res["hint"] == ""
    assert res["series"] == ""


@requires_git
def test_a_stale_series_prefix_is_a_hypothesis_never_a_resolved_series(tmp_path):
    """The collision this demotion exists for. This tree is byte-identical to a
    repo genuinely on 12.0: same branch shape, same manifests. It is instead a
    repo carried up to a newer series by a code-level upgrade, which by convention
    does not bump `version`. No predicate over the string `12.0.3.0.0` can tell
    the two apart, because the defect is staleness and staleness is not a property
    of the string - so the value may only ever arrive as a hypothesis to confirm."""
    root = tmp_path / "checkout"
    _init_repo_on_branch(root, "19.0-imp-widget")
    _module(root, "mod_x", "12.0.3.0.0")

    proc = _run(root)
    out = _parse(proc.stdout)
    assert out["SERIES_STATUS"] != "OK"
    assert out["SERIES"] == ""
    assert proc.returncode != 0
    assert "12.0" in out["SERIES_HINT"], "the candidate is surfaced, not swallowed"
    assert "unbumped" in out["SERIES_HINT"], (
        "the hint must name the frozen-manifest possibility, which is the whole reason the value "
        "is not the answer"
    )


def test_release_py_outranks_a_stale_series_prefixed_manifest(tmp_path):
    """Inverse ordering proof for the same tree: add the one artifact that IS the
    series by definition and step 1 answers outright - the stale prefix never
    surfaces, not even as a hint."""
    root = tmp_path / "checkout"
    _module(root, "mod_x", "12.0.3.0.0")
    (root / "odoo").mkdir(parents=True)
    (root / "odoo" / "release.py").write_text(
        "version_info = (17, 0, 0, 'final', 0, '')\n", encoding="utf-8"
    )

    proc = _run(root)
    out = _parse(proc.stdout)
    assert proc.returncode == 0, proc.stderr
    assert out["SERIES_STATUS"] == "OK"
    assert out["SERIES"] == "17.0"
    assert out["SERIES_STEP"] == "1"
    assert out["SERIES_HINT"] == ""
    assert "12.0" not in out["SERIES_HINT"]


def test_setup_py_only_is_surfaced_as_a_hint_never_as_a_series(tmp_path):
    """Step 5 is last-resort and explicitly a HINT: its files' existence may
    be surfaced, but it must never be parsed into a SERIES value."""
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "setup.py").write_text("# not a real Odoo release file\n", encoding="utf-8")

    proc = _run(root)
    out = _parse(proc.stdout)
    assert out["SERIES_STATUS"] == "NEEDS_CONTEXT"
    assert out["SERIES"] == ""
    assert out["SERIES_STEP"] == "5"
    assert "setup.py" in out["SERIES_HINT"]


def test_nonexistent_root_is_a_distinct_error_not_a_silent_needs_context(tmp_path):
    proc = _run(tmp_path / "does-not-exist")
    assert proc.returncode == 1
    assert proc.stdout == ""


def test_missing_root_argument_is_a_usage_error(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "detect"], capture_output=True, text=True
    )
    assert proc.returncode == 2
