"""Behavior tests for the `locate` subcommand on scripts/lib/instances_io.py
and the `--path` flag on scripts/lib/resolve_instances.sh - rung 2 of the
project-facts resolution ladder (design doc Sections A.2, C.1, C.2): given the
declared instance catalog and a repo path, answer "which declared Odoo
instance covers this repo?".

Contract under test:
  instances_io.py locate <instances.toml> <repo-path>
    - Match rule: the [[instance]] whose addons_path CONTAINS repo-path -
      repo-path equals the addons_path entry, or is strictly BELOW it
      (descendant). An addons_path entry nested BELOW repo-path (repo-path is
      an ANCESTOR of the declared entry) does NOT match - only
      descendant-or-equal counts. Pinned explicitly by
      test_locate_ancestor_of_addons_path_does_not_match below.
    - Longest matching addons_path entry wins; ties break to the highest
      series.
    - Match -> exit 0, INST_SERIES / INST_PROFILE / INST_ADDONS_PATH /
      INST_HTTP_PORT / INST_PYTHON / INST_DB_NAME / INST_DB_HOST /
      INST_DB_USER / INST_DB_PORT emitted as shell-eval KEY=VALUE lines.
    - No match -> exit 1, EMPTY stdout, NO stderr noise - a normal, designed
      ladder miss, not an error; the caller falls through to rung 3.
    - Catalog file PRESENT but unparseable (malformed TOML, a directory at
      that path, ...) -> exit 3, ONE clear stderr line naming the file.
      DISTINCT from exit 1: a caller who declared an instance and typo'd the
      file must see a diagnostic, not a silent miss indistinguishable from
      "nothing declared".
    - Catalog file ABSENT (no file at all at that path) -> exit 1, EMPTY
      stdout, NO stderr noise - same genuine-miss contract as "no match":
      most repos have declared nothing yet, so a missing catalog is a normal
      ladder miss, not an error.
    - Reuses split_addons_path (never a second, hand-rolled path splitter):
      an addons_path declared as a single flattened comma-joined string must
      split and match exactly like a native TOML array.

  resolve_instances.sh --path
    - Prints the resolved instances.toml path (same resolution the existing
      _resolve_instances function already performs) on stdout, exit 0.

CPU-only: no PostgreSQL, no Odoo, no network. Hermetic: every catalog is a
tmp_path fixture; the real ~/.odoo-ai/instances.toml is never read.
"""
import os
import shlex
import subprocess
import sys
from pathlib import Path
from shutil import which

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
INSTANCES_IO = LIB / "instances_io.py"
RESOLVE_INSTANCES_SH = LIB / "resolve_instances.sh"

requires_bash = pytest.mark.skipif(which("bash") is None, reason="bash not available")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _make_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "instances.toml"
    p.write_text(content, encoding="utf-8")
    return p


def _entry(series, addons_path, profile=None, db_name="odoo", http_port=8069,
           python_="", db_host="localhost", db_user="odoo", db_port=None):
    """Build one [[instance]] block. addons_path may be a list (rendered as a
    native TOML array) or a str (rendered as a single flattened value, e.g.
    a hand-typed comma-joined override)."""
    lines = ["[[instance]]", f'series = "{series}"']
    if profile is not None:
        lines.append(f'profile = "{profile}"')
    if isinstance(addons_path, str):
        lines.append(f'addons_path = "{addons_path}"')
    else:
        joined = ", ".join(f'"{p}"' for p in addons_path)
        lines.append(f"addons_path = [{joined}]")
    lines += [
        'run_mode = "source"',
        f"http_port = {http_port}",
        f'db_name = "{db_name}"',
        f'db_host = "{db_host}"',
        f'db_user = "{db_user}"',
    ]
    if db_port is not None:
        lines.append(f"db_port = {db_port}")
    lines.append(f'python = "{python_}"')
    return "\n".join(lines) + "\n"


def _run_locate(catalog: Path, repo_path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(INSTANCES_IO), "locate", str(catalog), str(repo_path)],
        capture_output=True, text=True,
    )


def _parse_facts(stdout: str) -> dict:
    out = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, _, raw = line.partition("=")
        vals = shlex.split(raw)
        out[key] = vals[0] if vals else ""
    return out


# --------------------------------------------------------------------------- #
# instances_io.py locate
# --------------------------------------------------------------------------- #

def test_locate_exact_match_resolves_facts(tmp_path):
    repo = tmp_path / "repos" / "17_0" / "custom"
    repo.mkdir(parents=True)
    toml = _make_toml(tmp_path, _entry(
        "17.0", [str(repo)], profile="standard_17",
        db_name="odoo_17", http_port=8069, python_="/fake/venv/bin/python3",
    ))
    result = _run_locate(toml, repo)
    assert result.returncode == 0, result.stderr
    facts = _parse_facts(result.stdout)
    assert facts["INST_SERIES"] == "17.0"
    assert facts["INST_PROFILE"] == "standard_17"
    assert facts["INST_ADDONS_PATH"] == str(repo)
    assert facts["INST_HTTP_PORT"] == "8069"
    assert facts["INST_PYTHON"] == "/fake/venv/bin/python3"
    assert facts["INST_DB_NAME"] == "odoo_17"
    assert facts["INST_DB_HOST"] == "localhost"
    assert facts["INST_DB_USER"] == "odoo"
    assert facts["INST_DB_PORT"] == "", "undeclared db_port must stay EMPTY, never a fabricated 5432"


def test_locate_descendant_of_addons_path_matches(tmp_path):
    """repo-path nested BELOW the declared addons_path entry is a match -
    the normal case of a module subdirectory inside a declared checkout."""
    addons_root = tmp_path / "repos" / "17_0"
    addons_root.mkdir(parents=True)
    nested_repo = addons_root / "my_module" / "sub"
    toml = _make_toml(tmp_path, _entry("17.0", [str(addons_root)], profile="p17"))
    result = _run_locate(toml, nested_repo)
    assert result.returncode == 0, result.stderr
    facts = _parse_facts(result.stdout)
    assert facts["INST_SERIES"] == "17.0"
    assert facts["INST_PROFILE"] == "p17"


def test_locate_no_match_exits_1_with_no_facts_and_no_noise(tmp_path):
    """A repo covered by no declared instance is a NORMAL ladder miss, not an
    error: exit 1, nothing on stdout, and no stderr noise (no traceback, no
    scary message) - the caller falls through to rung 3."""
    toml = _make_toml(tmp_path, _entry("17.0", [str(tmp_path / "repos" / "17_0")]))
    unrelated = tmp_path / "elsewhere" / "other_repo"
    result = _run_locate(toml, unrelated)
    assert result.returncode == 1
    assert result.stdout == "", "no facts must be emitted on a ladder miss"
    assert result.stderr == "", "a no-match is a normal, designed outcome - no stderr noise"


def test_locate_malformed_toml_exits_3_with_diagnostic_naming_the_file(tmp_path):
    """A catalog that IS present but fails to parse (e.g. a `[[instance]`
    typo - one missing closing bracket) must be DISTINGUISHABLE from a
    genuine "no declared instance covers this repo" miss: a distinct exit
    code, plus exactly one clear stderr line naming the broken file."""
    toml = _make_toml(tmp_path, "[[instance]\nseries = \"17.0\"\n")
    result = _run_locate(toml, tmp_path / "repos" / "17_0")
    assert result.returncode == 3
    assert result.stdout == "", "no facts must be emitted for an unparseable catalog"
    assert result.stderr != "", "a broken catalog must produce a diagnostic, not silence"
    assert str(toml) in result.stderr, "the diagnostic must name the broken file"


def test_locate_catalog_path_is_a_directory_exits_3_with_diagnostic(tmp_path):
    """The catalog path pointing at a directory instead of a file is another
    'present but unparseable' case - same distinct exit code and diagnostic
    as malformed TOML, never a silent genuine-miss."""
    catalog_dir = tmp_path / "instances.toml"
    catalog_dir.mkdir()
    result = _run_locate(catalog_dir, tmp_path / "repos" / "17_0")
    assert result.returncode == 3
    assert result.stdout == ""
    assert result.stderr != ""
    assert str(catalog_dir) in result.stderr


def test_locate_catalog_path_does_not_exist_stays_a_silent_genuine_miss(tmp_path):
    """A catalog path with NO file at all is a NORMAL ladder miss (most repos
    have declared nothing yet) - it must stay on the exit-1, silent-both-
    streams contract, NOT the new exit-3 diagnostic path reserved for a
    catalog that is present but broken."""
    missing = tmp_path / "does_not_exist" / "instances.toml"
    result = _run_locate(missing, tmp_path / "repos" / "17_0")
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "", "an absent catalog is a normal miss, not a diagnostic-worthy error"


def test_locate_ancestor_of_addons_path_does_not_match(tmp_path):
    """PINNED DECISION: repo-path being a PARENT of the declared addons_path
    entry does NOT match. Only descendant-or-equal counts - an ancestor repo
    merely CONTAINS the declared addons root rather than being covered BY
    it, so it must fall through to rung 3 exactly like a total miss."""
    addons_root = tmp_path / "repos" / "17_0" / "custom"
    addons_root.mkdir(parents=True)
    parent_repo = addons_root.parent  # tmp_path/repos/17_0 - an ANCESTOR of addons_root
    toml = _make_toml(tmp_path, _entry("17.0", [str(addons_root)]))
    result = _run_locate(toml, parent_repo)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == ""


def test_locate_longest_addons_path_wins(tmp_path):
    """Two entries both cover the target (one via an outer root, one via a
    nested, more specific root) - the LONGEST (most specific) match wins."""
    outer = tmp_path / "repos" / "17_0"
    inner = outer / "custom"
    inner.mkdir(parents=True)
    target = inner / "my_module"

    content = (
        _entry("17.0", [str(outer)], profile="outer_profile", db_name="odoo_outer")
        + "\n"
        + _entry("17.0", [str(inner)], profile="inner_profile", db_name="odoo_inner")
    )
    toml = _make_toml(tmp_path, content)
    result = _run_locate(toml, target)
    assert result.returncode == 0, result.stderr
    facts = _parse_facts(result.stdout)
    assert facts["INST_PROFILE"] == "inner_profile", "the longer, more specific addons_path must win"
    assert facts["INST_DB_NAME"] == "odoo_inner"


def test_locate_tie_breaks_to_highest_series(tmp_path):
    """Two entries with the IDENTICAL addons_path (same match length) but
    different series - the tie breaks to the HIGHEST series."""
    shared = tmp_path / "repos" / "shared"
    shared.mkdir(parents=True)
    content = (
        _entry("16.0", [str(shared)], profile="p16", db_name="odoo_16")
        + "\n"
        + _entry("18.0", [str(shared)], profile="p18", db_name="odoo_18")
    )
    toml = _make_toml(tmp_path, content)
    result = _run_locate(toml, shared)
    assert result.returncode == 0, result.stderr
    facts = _parse_facts(result.stdout)
    assert facts["INST_SERIES"] == "18.0", "an equal-length match must tie-break to the HIGHEST series"
    assert facts["INST_PROFILE"] == "p18"


def test_locate_matches_second_path_in_a_multi_entry_addons_path_array(tmp_path):
    """A 2+-entry addons_path (native TOML array) must be scanned entry-by-
    entry - a match on the SECOND path must be found, not just the first."""
    core = tmp_path / "repos" / "core"
    custom = tmp_path / "repos" / "custom"
    core.mkdir(parents=True)
    custom.mkdir(parents=True)
    toml = _make_toml(tmp_path, _entry("17.0", [str(core), str(custom)], profile="p17"))
    result = _run_locate(toml, custom / "my_module")
    assert result.returncode == 0, result.stderr
    facts = _parse_facts(result.stdout)
    assert facts["INST_PROFILE"] == "p17"
    assert facts["INST_ADDONS_PATH"] == f"{core},{custom}"


def test_locate_splits_a_flattened_comma_joined_addons_path_via_split_addons_path(tmp_path):
    """A hand-typed instances.toml entry may declare addons_path as a single
    flattened string (the SSOT wire format split_addons_path already
    tolerates) instead of a proper TOML array. `locate` must split it via
    the SAME existing helper - not a second, hand-rolled parser."""
    core = tmp_path / "repos" / "core"
    custom = tmp_path / "repos" / "custom"
    core.mkdir(parents=True)
    custom.mkdir(parents=True)
    flattened = f"{core},{custom}"
    toml = _make_toml(tmp_path, _entry("17.0", flattened, profile="p17"))
    result = _run_locate(toml, custom / "my_module")
    assert result.returncode == 0, result.stderr
    facts = _parse_facts(result.stdout)
    assert facts["INST_PROFILE"] == "p17"


def test_locate_never_abbreviates_profile_name(tmp_path):
    """The emitted INST_PROFILE must be the EXACT declared string - never
    invented or abbreviated."""
    repo = tmp_path / "repos" / "19_0"
    repo.mkdir(parents=True)
    toml = _make_toml(tmp_path, _entry("19.0", [str(repo)], profile="standard_viindoo_full_stack"))
    result = _run_locate(toml, repo)
    assert result.returncode == 0, result.stderr
    facts = _parse_facts(result.stdout)
    assert facts["INST_PROFILE"] == "standard_viindoo_full_stack"


# --------------------------------------------------------------------------- #
# resolve_instances.sh --path
# --------------------------------------------------------------------------- #

@requires_bash
def test_resolve_instances_path_flag_prints_explicit_override(tmp_path):
    catalog = tmp_path / "custom-instances.toml"
    catalog.write_text('[[instance]]\nseries = "17.0"\n', encoding="utf-8")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "ODOO_AI_INSTANCES": str(catalog)}
    result = subprocess.run(
        ["bash", str(RESOLVE_INSTANCES_SH), "--path"],
        capture_output=True, text=True, env=env, cwd=str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(catalog)


@requires_bash
def test_resolve_instances_path_flag_prints_global_default_when_nothing_declared(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home)}
    result = subprocess.run(
        ["bash", str(RESOLVE_INSTANCES_SH), "--path"],
        capture_output=True, text=True, env=env, cwd=str(cwd),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(home / ".odoo-ai" / "instances.toml")


@requires_bash
def test_resolve_instances_path_flag_matches_pwd_instances_toml_fallback(tmp_path):
    """When the global catalog is absent but a project-local
    $PWD/.odoo-ai/instances.toml has >=1 [[instance]], --path must resolve to
    that transitional fallback - the same order _resolve_instances documents."""
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "cwd"
    (cwd / ".odoo-ai").mkdir(parents=True)
    proj_catalog = cwd / ".odoo-ai" / "instances.toml"
    proj_catalog.write_text('[[instance]]\nseries = "17.0"\n', encoding="utf-8")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home)}
    result = subprocess.run(
        ["bash", str(RESOLVE_INSTANCES_SH), "--path"],
        capture_output=True, text=True, env=env, cwd=str(cwd),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(proj_catalog)


@requires_bash
def test_resolve_instances_unknown_flag_is_a_usage_error(tmp_path):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path)}
    result = subprocess.run(
        ["bash", str(RESOLVE_INSTANCES_SH), "--bogus"],
        capture_output=True, text=True, env=env, cwd=str(tmp_path),
    )
    assert result.returncode != 0
    assert result.stdout == ""


@requires_bash
def test_resolve_instances_sourcing_still_defines_no_cli_side_effects(tmp_path):
    """Sourcing the file (the pre-existing usage from every other consumer)
    must NOT execute the new --path CLI branch - it only defines functions,
    exactly like before this change."""
    result = subprocess.run(
        ["bash", "-c", f'source "{RESOLVE_INSTANCES_SH}" && echo SOURCED_OK'],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "SOURCED_OK" in result.stdout


# --------------------------------------------------------------------------- #
# End-to-end: the exact ladder rung-2 invocation
# --------------------------------------------------------------------------- #

@requires_bash
def test_ladder_rung2_end_to_end_invocation(tmp_path):
    """Reproduces the EXACT invocation the resolution ladder documents
    (project-facts-resolution.md rung 2): resolve the catalog path via
    resolve_instances.sh --path, then feed it straight into
    instances_io.py locate as its first positional argument."""
    home = tmp_path / "home"
    (home / ".odoo-ai").mkdir(parents=True)
    catalog = home / ".odoo-ai" / "instances.toml"
    repo = tmp_path / "repos" / "19_0"
    repo.mkdir(parents=True)
    catalog.write_text(_entry("19.0", [str(repo)], profile="standard_19"), encoding="utf-8")

    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home)}
    script = (
        f'"{sys.executable}" "{INSTANCES_IO}" locate '
        f'"$(bash "{RESOLVE_INSTANCES_SH}" --path)" "{repo}"'
    )
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    facts = _parse_facts(result.stdout)
    assert facts["INST_SERIES"] == "19.0"
    assert facts["INST_PROFILE"] == "standard_19"
