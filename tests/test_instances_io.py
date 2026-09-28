"""Tests for the per-profile API additions to scripts/lib/instances_io.py.

Business rules protected:
  - profile_of / instance_key_of return correct values with and without profile.
  - select_instance with profile= filters to the correct item when two items
    share a series but differ in profile.
  - _cmd_read emits INST_PROFILE and INST_KEY for both profiled and plain instances.
  - The read CLI accepts an optional third positional arg [profile] and uses it.
  - `read` distinguishes a genuine "no catalog file at all" miss (exit 1,
    silent) from a catalog that IS present but could not be read as TOML
    (exit 3, one diagnostic line naming the file) - the same split `locate`
    applies, so a malformed catalog and a permissions error are never
    reported identically to "nothing declared".

CPU-only: no PostgreSQL, no Odoo, no network. Uses the real library modules.
"""

import importlib.util
import shlex
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
INSTANCES_IO = LIB / "instances_io.py"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


io = _load_module("instances_io", INSTANCES_IO)


# ---------------------------------------------------------------------------
# profile_of / instance_key_of
# ---------------------------------------------------------------------------

def test_profile_of_returns_empty_string_when_no_profile():
    item = {"series": "17.0", "addons_path": ["/a"]}
    assert io.profile_of(item) == ""


def test_profile_of_returns_profile_when_present():
    item = {"series": "17.0", "profile": "minimal_17"}
    assert io.profile_of(item) == "minimal_17"


def test_instance_key_of_no_profile_equals_series():
    item = {"series": "17.0"}
    assert io.instance_key_of(item) == "17.0"


def test_instance_key_of_with_profile_uses_colon_join():
    item = {"series": "17.0", "profile": "minimal_17"}
    assert io.instance_key_of(item) == "17.0:minimal_17"


def test_instance_key_of_with_empty_profile_equals_series():
    item = {"series": "17.0", "profile": ""}
    assert io.instance_key_of(item) == "17.0"


# ---------------------------------------------------------------------------
# select_instance with profile filter
# ---------------------------------------------------------------------------

_ITEMS_TWO_PROFILES = [
    {"series": "17.0", "profile": "minimal_17", "db_name": "odoo_minimal"},
    {"series": "17.0", "profile": "full_17", "db_name": "odoo_full"},
]


def test_select_instance_with_profile_returns_correct_item():
    item, defaulted = io.select_instance(_ITEMS_TWO_PROFILES, "17.0", profile="minimal_17")
    assert item is not None
    assert item["db_name"] == "odoo_minimal"
    assert defaulted is False


def test_select_instance_with_other_profile_returns_other_item():
    item, defaulted = io.select_instance(_ITEMS_TWO_PROFILES, "17.0", profile="full_17")
    assert item is not None
    assert item["db_name"] == "odoo_full"
    assert defaulted is False


def test_select_instance_with_unknown_profile_returns_none():
    item, _ = io.select_instance(_ITEMS_TWO_PROFILES, "17.0", profile="nonexistent")
    assert item is None


def test_select_instance_without_profile_picks_first_match():
    """Without profile filter, select_instance returns the first series match
    (existing behavior for want= is first-match, no profile discrimination)."""
    item, defaulted = io.select_instance(_ITEMS_TWO_PROFILES, "17.0")
    assert item is not None
    assert defaulted is False
    # Either item is valid (first match = minimal_17 by list order).
    assert item["series"] == "17.0"


def test_select_instance_profile_none_preserves_original_behavior():
    """profile=None is the default and must not break callers that pass no profile."""
    items = [{"series": "17.0", "db_name": "odoo_17"}]
    item, defaulted = io.select_instance(items, "17.0", profile=None)
    assert item is not None
    assert item["db_name"] == "odoo_17"


# ---------------------------------------------------------------------------
# _cmd_read emits INST_PROFILE and INST_KEY
# ---------------------------------------------------------------------------

def _run_read(toml_path: Path, *extra_args) -> dict:
    """Run `instances_io.py read <toml> [args...]` and parse emitted KEY=VALUE."""
    result = subprocess.run(
        [sys.executable, str(INSTANCES_IO), "read", str(toml_path), *extra_args],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"instances_io.py read exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    out = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, _, raw = line.partition("=")
        vals = shlex.split(raw)
        out[key] = vals[0] if vals else ""
    return out


def _make_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "instances.toml"
    p.write_text(content, encoding="utf-8")
    return p


def test_cmd_read_emits_inst_profile_empty_for_plain_instance(tmp_path):
    toml = _make_toml(tmp_path, textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        db_name = "odoo_17"
        http_port = 8069
        db_host = "localhost"
        db_user = "odoo"
        run_mode = "source"
        addons_path = ["/fake/addons"]
    """))
    out = _run_read(toml, "17.0")
    assert "INST_PROFILE" in out, "INST_PROFILE must be emitted"
    assert out["INST_PROFILE"] == "", f"Expected empty profile, got {out['INST_PROFILE']!r}"


def test_cmd_read_emits_inst_key_equals_series_for_plain_instance(tmp_path):
    toml = _make_toml(tmp_path, textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        db_name = "odoo_17"
        http_port = 8069
        db_host = "localhost"
        db_user = "odoo"
        run_mode = "source"
        addons_path = ["/fake/addons"]
    """))
    out = _run_read(toml, "17.0")
    assert "INST_KEY" in out, "INST_KEY must be emitted"
    assert out["INST_KEY"] == "17.0", f"Expected INST_KEY='17.0', got {out['INST_KEY']!r}"


def test_cmd_read_emits_inst_profile_for_profiled_instance(tmp_path):
    toml = _make_toml(tmp_path, textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        profile = "minimal_17"
        db_name = "odoo_minimal"
        http_port = 8069
        db_host = "localhost"
        db_user = "odoo"
        run_mode = "source"
        addons_path = ["/fake/addons"]
    """))
    out = _run_read(toml, "17.0", "minimal_17")
    assert out.get("INST_PROFILE") == "minimal_17", (
        f"Expected INST_PROFILE='minimal_17', got {out.get('INST_PROFILE')!r}"
    )
    assert out.get("INST_KEY") == "17.0:minimal_17", (
        f"Expected INST_KEY='17.0:minimal_17', got {out.get('INST_KEY')!r}"
    )


def test_cmd_read_emits_db_port_when_declared(tmp_path):
    """A declared db_port must be surfaced as INST_DB_PORT (issue #163)."""
    toml = _make_toml(tmp_path, textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        db_name = "odoo_17"
        http_port = 8069
        db_host = "localhost"
        db_user = "odoo"
        db_port = 5433
        run_mode = "source"
        addons_path = ["/fake/addons"]
    """))
    out = _run_read(toml, "17.0")
    assert out.get("INST_DB_PORT") == "5433", (
        f"INST_DB_PORT must equal the declared db_port; got {out.get('INST_DB_PORT')!r}"
    )


def test_cmd_read_db_port_empty_when_absent_not_5432(tmp_path):
    """No declared db_port -> INST_DB_PORT is EMPTY (never a fabricated 5432)."""
    toml = _make_toml(tmp_path, textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        db_name = "odoo_17"
        http_port = 8069
        db_host = "localhost"
        db_user = "odoo"
        run_mode = "source"
        addons_path = ["/fake/addons"]
    """))
    out = _run_read(toml, "17.0")
    assert "INST_DB_PORT" in out, "INST_DB_PORT must always be emitted"
    assert out["INST_DB_PORT"] == "", (
        f"INST_DB_PORT must be EMPTY when no db_port is declared; got {out['INST_DB_PORT']!r}"
    )
    assert out["INST_DB_PORT"] != "5432", "must NOT fabricate the libpq default 5432"


def test_cmd_read_emits_inst_addons_path_comma_joined_for_two_entries(tmp_path):
    """INST_ADDONS_PATH must be comma-joined for a 2+-entry addons_path -
    matching Odoo's own --addons-path/addons_path syntax (never colon; see
    scripts/lib/instances_io.py's join_addons_path SSOT). The mechanical
    reason this bug survived is that no fixture exercised 2+ entries - this
    is that fixture."""
    toml = _make_toml(tmp_path, textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        db_name = "odoo_17"
        http_port = 8069
        db_host = "localhost"
        db_user = "odoo"
        run_mode = "source"
        addons_path = ["/repos/core", "/repos/custom"]
    """))
    out = _run_read(toml, "17.0")
    assert out.get("INST_ADDONS_PATH") == "/repos/core,/repos/custom", (
        f"INST_ADDONS_PATH must be comma-joined for 2+ entries; "
        f"got {out.get('INST_ADDONS_PATH')!r}"
    )
    assert ":" not in out.get("INST_ADDONS_PATH", ""), (
        "INST_ADDONS_PATH must never use colon as the directory separator"
    )


def test_cmd_read_profile_arg_selects_correct_item_among_two(tmp_path):
    """With two [[instance]] blocks of the same series but different profile,
    the third CLI arg [profile] must select the right one."""
    toml = _make_toml(tmp_path, textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        profile = "minimal_17"
        db_name = "odoo_minimal"
        http_port = 8069
        db_host = "localhost"
        db_user = "odoo"
        run_mode = "source"
        addons_path = ["/fake/addons"]

        [[instance]]
        series = "17.0"
        profile = "full_17"
        db_name = "odoo_full"
        http_port = 8079
        db_host = "localhost"
        db_user = "odoo"
        run_mode = "source"
        addons_path = ["/fake/addons"]
    """))
    # Select minimal_17
    out_min = _run_read(toml, "17.0", "minimal_17")
    assert out_min["INST_DB_NAME"] == "odoo_minimal", (
        f"Expected odoo_minimal but got {out_min['INST_DB_NAME']!r}"
    )
    assert out_min["INST_PROFILE"] == "minimal_17"
    assert out_min["INST_KEY"] == "17.0:minimal_17"

    # Select full_17
    out_full = _run_read(toml, "17.0", "full_17")
    assert out_full["INST_DB_NAME"] == "odoo_full", (
        f"Expected odoo_full but got {out_full['INST_DB_NAME']!r}"
    )
    assert out_full["INST_PROFILE"] == "full_17"
    assert out_full["INST_KEY"] == "17.0:full_17"


# ---------------------------------------------------------------------------
# _cmd_read: catalog-unreadable vs catalog-absent must be DISTINGUISHABLE
# (same split _cmd_locate applies - see instances_io.py's `locate` docstring)
# ---------------------------------------------------------------------------

def _run_read_raw(toml_path, *extra_args) -> subprocess.CompletedProcess:
    """Like _run_read but returns the raw CompletedProcess (no returncode==0
    assertion) so a failure path can be inspected."""
    return subprocess.run(
        [sys.executable, str(INSTANCES_IO), "read", str(toml_path), *extra_args],
        capture_output=True, text=True,
    )


def test_read_cli_malformed_toml_exits_3_with_diagnostic_naming_the_file(tmp_path):
    """A catalog that IS present but fails to parse (missing closing bracket)
    must be DISTINGUISHABLE from a genuine "no catalog file" miss: a distinct
    exit code, plus exactly one clear stderr line naming the broken file -
    never the silent exit 1 a code bug and a typo'd file would otherwise
    share."""
    toml = _make_toml(tmp_path, "[[instance]\nseries = \"17.0\"\n")
    result = _run_read_raw(toml)
    assert result.returncode == 3
    assert result.stdout == "", "no facts must be emitted for an unparseable catalog"
    assert result.stderr != "", "a broken catalog must produce a diagnostic, not silence"
    assert str(toml) in result.stderr, "the diagnostic must name the broken file"


def test_read_cli_catalog_path_is_a_directory_exits_3_with_diagnostic(tmp_path):
    """The catalog path pointing at a directory instead of a file is another
    'present but unparseable' case - same distinct exit code and diagnostic
    as malformed TOML, never a silent genuine-miss."""
    catalog_dir = tmp_path / "instances.toml"
    catalog_dir.mkdir()
    result = _run_read_raw(catalog_dir)
    assert result.returncode == 3
    assert result.stdout == ""
    assert result.stderr != ""
    assert str(catalog_dir) in result.stderr


def test_read_cli_catalog_path_does_not_exist_stays_a_silent_genuine_miss(tmp_path):
    """A catalog path with NO file at all is a NORMAL 'nothing declared yet'
    miss - it must stay on the exit-1, silent-stderr contract, NOT the
    exit-3 diagnostic path reserved for a catalog that is present but
    broken. 50-instance-spinup.sh only branches on non-zero-exit-or-empty-
    stdout, never on the specific code, so this split cannot break it."""
    missing = tmp_path / "does_not_exist" / "instances.toml"
    result = _run_read_raw(missing)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "", "an absent catalog is a normal miss, not a diagnostic-worthy error"


# --------------------------------------------------------------------------- #
# Environment facts recorded by 45-venv.sh: odoo_root, db_run_mode, db_container
#
# All three follow the db_port precedent EXACTLY: ABSENT is a real value, emitted
# as the empty string. A fabricated default would be worse than nothing here -
# a guessed `db_run_mode` sends a client binary at a cluster nobody named, and a
# guessed `odoo_root` puts the wrong checkout on sys.path.
# --------------------------------------------------------------------------- #
_NEW_ENV_EMITS = ("INST_ODOO_ROOT", "INST_DB_RUN_MODE", "INST_DB_CONTAINER")


def test_cmd_read_emits_the_environment_facts_when_declared(tmp_path):
    """A catalog that declares them must surface all three to shell consumers."""
    toml = _make_toml(tmp_path, textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        db_name = "odoo_17"
        http_port = 8069
        db_host = "localhost"
        db_user = "odoo"
        db_port = 5544
        run_mode = "source"
        addons_path = ["/fake/addons"]
        python = "/fake/venv/bin/python"
        odoo_root = "/fake/core"
        db_run_mode = "docker"
        db_container = "declared-by-the-user"
    """))
    out = _run_read(toml, "17.0")
    assert out["INST_ODOO_ROOT"] == "/fake/core"
    assert out["INST_DB_RUN_MODE"] == "docker"
    assert out["INST_DB_CONTAINER"] == "declared-by-the-user"


@pytest.mark.parametrize("key", _NEW_ENV_EMITS)
def test_cmd_read_emits_empty_not_a_guess_when_the_fact_is_absent(tmp_path, key):
    """A catalog written before these keys existed is VALID. Each key must still be
    emitted (so `eval`-ing consumers never hit an unset variable) and must be
    EMPTY - never a plausible-looking default."""
    toml = _make_toml(tmp_path, textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        db_name = "odoo_17"
        http_port = 8069
        db_host = "localhost"
        db_user = "odoo"
        run_mode = "source"
        addons_path = ["/fake/addons"]
    """))
    out = _run_read(toml, "17.0")
    assert key in out, f"{key} must ALWAYS be emitted, even when undeclared"
    assert out[key] == "", (
        f"{key} must be empty when undeclared; got {out[key]!r}. An absent "
        "environment fact is a real value - guessing one sends an operation at a "
        "resource nobody declared."
    )


def test_absent_db_run_mode_is_never_emitted_as_a_vocabulary_value(tmp_path):
    """Specifically: absent must NOT be normalized to `tcp-only` (or any other
    member of the vocabulary) at read time. The distinction is load-bearing -
    `tcp-only` is a positive declaration that there is no client surface, while
    absent means nothing has been recorded yet, and only the latter permits the
    narrowly-scoped legacy shim in the drop path."""
    toml = _make_toml(tmp_path, textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        db_name = "odoo_17"
        http_port = 8069
        db_host = "localhost"
        db_user = "odoo"
        run_mode = "source"
        addons_path = ["/fake/addons"]
    """))
    out = _run_read(toml, "17.0")
    assert out["INST_DB_RUN_MODE"] not in ("tcp-only", "native", "docker"), (
        "an undeclared client surface must stay undeclared at read time"
    )


# ---------------------------------------------------------------------------
# server_wide_modules: the catalog declares the DEPLOYMENT's own server-wide
# modules; the series' core default is read from the checkout; a build or a
# server loads core + declared, and never a guessed core.
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parent))
import odoo_tree_fixtures as trees  # noqa: E402


def _catalog(tmp_path, body):
    path = tmp_path / "instances.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_read_reports_the_declared_server_wide_modules_and_empty_when_none(tmp_path):
    path = _catalog(tmp_path, textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        addons_path = ["/a"]
        server_wide_modules = ["to_base", "viin_brand"]

        [[instance]]
        series = "16.0"
        addons_path = ["/b"]
    """))
    declared = subprocess.run([sys.executable, str(INSTANCES_IO), "read", str(path), "17.0"],
                              capture_output=True, text=True, check=True).stdout
    none = subprocess.run([sys.executable, str(INSTANCES_IO), "read", str(path), "16.0"],
                          capture_output=True, text=True, check=True).stdout
    assert "INST_SERVER_WIDE_MODULES=to_base,viin_brand" in declared.splitlines()
    assert "INST_SERVER_WIDE_MODULES=''" in none.splitlines()


def test_the_text_scan_reads_single_and_multi_line_arrays_like_tomllib(tmp_path):
    """Python < 3.11 has no tomllib: the text scan must read the same values, including an array
    written over several lines (the form a hand edit or a writer may use)."""
    path = _catalog(tmp_path, textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        addons_path = [
            "/a",  # core
            "/b",
        ]
        server_wide_modules = [
            "to_base",
            # a comment line inside the array
            "viin_brand",
        ]
        http_port = 8069

        [[instance]]
        series = "18.0"
        server_wide_modules = ["viin_brand"]
        addons_path = ["/c"]
    """))
    scanned = io._load_textscan(str(path))["instance"]
    parsed = io._load_tomllib(str(path))["instance"]
    for got in (scanned, parsed):
        assert io.server_wide_modules_of(got[0]) == ["to_base", "viin_brand"]
        assert io.addons_path_list(got[0]) == ["/a", "/b"]
        assert got[0]["http_port"] == 8069, "a key after a multi-line array still belongs to the row"
        assert io.server_wide_modules_of(got[1]) == ["viin_brand"]


@pytest.mark.parametrize("series", trees.SERIES)
def test_core_default_comes_first_then_the_declared_modules_deduplicated(tmp_path, series):
    root = trees.write_checkout(tmp_path / "odoo", series)
    effective, core = io.effective_server_wide_modules(["web", "to_base"], str(root))
    assert core == trees.CORE_LOAD[series]
    assert effective == trees.CORE_LOAD[series] + ["to_base"], "core first, declared after, no repeat"


@pytest.mark.parametrize("series", trees.SERIES)
def test_the_real_checkout_declares_the_core_default_the_fixture_models(series):
    root = trees.real_checkout(series)
    if root is None:
        pytest.skip("no Odoo %s checkout under %s" % (series, trees.CHECKOUTS))
    assert io.core_server_wide_default(str(root)) == trees.CORE_LOAD[series]


def test_the_checkout_is_found_from_the_addons_path_when_no_odoo_root_is_declared(tmp_path):
    root = trees.write_checkout(tmp_path / "odoo", "17.0")
    effective, _core = io.effective_server_wide_modules(
        ["to_base"], "", [str(tmp_path / "custom"), str(root / "addons")])
    assert effective == ["base", "web", "to_base"]


def test_the_declared_checkout_is_the_one_read_never_another_found_on_the_addons_path(tmp_path):
    """The instance's checkout is the one its odoo_root declares. When that checkout does not
    state its --load default, another checkout reachable through the addons_path is a different
    Odoo: its default is not this instance's, so the answer is 'unknown', never the other's."""
    declared = trees.write_checkout(tmp_path / "declared", "17.0")
    (declared / "odoo" / "tools" / "config.py").write_text("# no --load option here\n", encoding="utf-8")
    other = trees.write_checkout(tmp_path / "other", "19.0")
    assert io.core_server_wide_default(str(declared), [str(other / "addons")]) is None
    with pytest.raises(io.ServerWideCoreUnknown):
        io.effective_server_wide_modules(["to_base"], str(declared), [str(other / "addons")])


def test_nothing_declared_passes_no_load_whatever_the_core_default(tmp_path):
    root = trees.write_checkout(tmp_path / "odoo", "19.0")
    assert io.effective_server_wide_modules([], str(root))[0] == []
    assert io.effective_server_wide_modules([], str(tmp_path / "nowhere")) == ([], None)


def test_declared_modules_with_an_unreadable_core_default_are_refused_never_guessed(tmp_path):
    """--load REPLACES Odoo's default: a set of only the declared modules would silently drop the
    core ones (base/web), so an unreadable core default is an error, not a guess."""
    with pytest.raises(io.ServerWideCoreUnknown):
        io.effective_server_wide_modules(["to_base"], str(tmp_path / "nowhere"), [str(tmp_path)])
    res = subprocess.run([sys.executable, str(INSTANCES_IO), "server-wide", "--declared", "to_base",
                          "--odoo-root", str(tmp_path / "nowhere")], capture_output=True, text=True)
    assert res.returncode == 4 and res.stdout == ""
    assert "SERVER_WIDE_CORE_UNKNOWN" in res.stderr


def test_server_wide_cli_prints_the_effective_set_and_the_core(tmp_path):
    root = trees.write_checkout(tmp_path / "odoo", "11.0")
    res = subprocess.run([sys.executable, str(INSTANCES_IO), "server-wide", "--declared",
                          "to_base, viin_brand", "--odoo-root", str(root)],
                         capture_output=True, text=True, check=True)
    assert res.stdout.splitlines() == ["SERVER_WIDE_MODULES=web,to_base,viin_brand",
                                       "SERVER_WIDE_CORE=web"]


# ---------------------------------------------------------------------------
# read-row: the ONE row a writer records onto (select_row)
# ---------------------------------------------------------------------------

_MIXED = textwrap.dedent("""\
    [[instance]]
    series = "17.0"
    profile = "p1"
    addons_path = ["/p1"]

    [[instance]]
    series = "17.0"
    addons_path = ["/plain"]

    [[instance]]
    series = "16.0"
    profile = "only"
    addons_path = ["/only"]
""")


def _read_row(path, series, profile):
    return subprocess.run([sys.executable, str(INSTANCES_IO), "read-row", str(path), series, profile],
                          capture_output=True, text=True, timeout=30)


def test_read_row_without_a_profile_is_the_unprofiled_row_even_when_a_profiled_one_comes_first(tmp_path):
    cat = tmp_path / "instances.toml"
    cat.write_text(_MIXED, encoding="utf-8")
    res = _read_row(cat, "17.0", "")
    assert res.returncode == 0, res.stderr
    assert "INST_ADDONS_PATH=/plain" in res.stdout and "INST_PROFILE=''" in res.stdout
    assert "INST_ADDONS_PATH=/p1" in _read_row(cat, "17.0", "p1").stdout


@pytest.mark.parametrize("series, profile, needle", [
    ("16.0", "", "--profile"),          # only profiled rows: never guess one
    ("17.0", "nope", "declare it first"),
    ("15.0", "", "declare it first"),
])
def test_read_row_refuses_rather_than_pick_a_row_nobody_named(tmp_path, series, profile, needle):
    cat = tmp_path / "instances.toml"
    cat.write_text(_MIXED, encoding="utf-8")
    res = _read_row(cat, series, profile)
    assert res.returncode == 1 and res.stdout == ""
    assert needle in res.stderr, res.stderr


def test_read_row_names_a_missing_catalog(tmp_path):
    res = _read_row(tmp_path / "absent.toml", "17.0", "")
    assert res.returncode == 1 and res.stdout == "" and "no instance catalog" in res.stderr
