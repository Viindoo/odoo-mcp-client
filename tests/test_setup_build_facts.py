"""Behavior tests for the setup steps that derive an instance's build facts.

Business rules protected:
  - The supported Python range of a venv is an Odoo SOURCE fact: `45-venv.sh suggest`, the
    `create-venv` default and step 40's python hint read it from the instance's checkout, and the
    hand-kept fallback table answers ONLY when no checkout is readable - a stale or missing table
    entry never overrides the source, and a new series needs no table edit.
  - `record-env` warns when the venv's interpreter lies outside that range (advisory only).
  - `server_wide_modules` is a DEPLOYMENT fact on each catalog row: step 46 PROPOSES it from
    evidence (self-checking addons, a probe build's log warnings, what the row already declares)
    without Odoo's core default, and RECORDS only an explicit, validated list. An operator's own
    addition that no evidence re-finds is kept in the proposal, never dropped silently.
  - Recording upserts one key on one row: every other key, comment and row survives byte for byte,
    a multi-line array is replaced whole, the file stays parseable by tomllib AND by the text-scan
    fallback older interpreters use, and step 40 never overwrites a declared row.

Every case builds throwaway fixtures under tmp_path; nothing touches the host's catalog.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import textwrap
import tomllib
from pathlib import Path

import pytest

from conftest import farm_path, real_python3

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
STEPS = PLUGIN / "scripts" / "setup-steps"
STEP40 = STEPS / "40-instance-profile.sh"
STEP45 = STEPS / "45-venv.sh"
STEP46 = STEPS / "46-server-wide.sh"
CONFIG_MERGE = PLUGIN / "scripts" / "lib" / "config_merge.py"
INSTANCES_IO = PLUGIN / "scripts" / "lib" / "instances_io.py"
MATRIX = PLUGIN / "scripts" / "lib" / "odoo-python-matrix.json"

requires_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def _load_io():
    spec = importlib.util.spec_from_file_location("instances_io_under_test", INSTANCES_IO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _core(tmp_path: Path, *, min_py=(3, 11), max_py=(3, 13), load="base,web", name="core") -> Path:
    """A fake Odoo checkout: a core package declaring its Python range and --load default."""
    root = tmp_path / name
    _write(root / "odoo" / "release.py",
           "version_info = (17, 0, 0, 'final', 0, '')\n"
           "MIN_PY_VERSION = %r\nMAX_PY_VERSION = %r\n" % (min_py, max_py))
    _write(root / "odoo" / "tools" / "config.py",
           'group.add_option("--load", dest="server_wide_modules", my_default=%r)\n' % load)
    (root / "addons").mkdir(parents=True, exist_ok=True)
    return root


SELF_CHECK = (
    "def _test_if_loaded_in_server_wide():\n"
    "    if '{m}' in config.options.get('server_wide_modules', '').split(','):\n"
    "        return True\n"
)


def _addon(base: Path, name: str, init: str = "") -> None:
    _write(base / name / "__manifest__.py", "{'name': '%s'}\n" % name)
    _write(base / name / "__init__.py", init)


def _env(tmp_path: Path, catalog: Path) -> dict:
    env = dict(os.environ)
    env["ODOO_AI_INSTANCES"] = str(catalog)
    env["ODOO_AI_HOME"] = str(tmp_path / "home")
    env.pop("ODOO_AI_PROFILE_SPEC", None)
    return env


def _run(args, env, cwd=None, timeout=180):
    return subprocess.run(["bash", *map(str, args)], capture_output=True, text=True, env=env,
                          cwd=str(cwd) if cwd else None, timeout=timeout)


def _upsert(catalog: Path, series: str, profile: str, *pairs):
    return subprocess.run([real_python3(), str(CONFIG_MERGE), "toml-upsert-instance-keys",
                           str(catalog), series, profile, *pairs],
                          capture_output=True, text=True, timeout=60)


def _kv(stdout: str) -> dict:
    out = {}
    for line in stdout.splitlines():
        if "=" in line and line.split("=", 1)[0].isupper():
            k, v = line.split("=", 1)
            out[k] = v.strip("'")
    return out


# ============================================================ catalog writer (upsert)

CATALOG = textwrap.dedent("""\
    # host catalog - hand comments must survive
    [[instance]]
    series = "17.0"
    profile = "p1"
    addons_path = [
      "/a/custom",   # own repo
      "/a/core/addons",
    ]
    custom_key = "keep me"  # unknown to the plugin
    server_wide_modules = [
      "old_one",
      "old_two",
    ]

    [[instance]]
    series = "17.0"
    addons_path = ["/b"]
    python = "/venv/bin/python"

    [other_table]
    x = 1
""")


def test_array_upsert_replaces_a_multiline_array_whole_and_keeps_everything_else(tmp_path):
    catalog = _write(tmp_path / "instances.toml", CATALOG)
    res = _upsert(catalog, "17.0", "p1", "server_wide_modules[]=to_base,viin_brand")
    assert res.returncode == 0, res.stderr
    data = tomllib.loads(catalog.read_text())
    first, second = data["instance"]
    assert first["server_wide_modules"] == ["to_base", "viin_brand"]
    assert first["addons_path"] == ["/a/custom", "/a/core/addons"]
    assert first["custom_key"] == "keep me"
    assert "server_wide_modules" not in second, "another row must never gain the key"
    assert data["other_table"] == {"x": 1}
    text = catalog.read_text()
    for kept in ("# host catalog - hand comments must survive", '"/a/custom",   # own repo',
                 'custom_key = "keep me"  # unknown to the plugin'):
        assert kept in text
    assert "old_one" not in text and "old_two" not in text, "the old array must not linger"


def test_array_upsert_inserts_when_absent_and_empty_list_is_a_declared_none(tmp_path):
    catalog = _write(tmp_path / "instances.toml", CATALOG)
    assert _upsert(catalog, "17.0", "", "server_wide_modules[]=").returncode == 0
    second = tomllib.loads(catalog.read_text())["instance"][1]
    assert second["server_wide_modules"] == []
    assert second["python"] == "/venv/bin/python"


def test_array_upsert_is_readable_by_the_text_scan_fallback(tmp_path):
    """Older interpreters (no tomllib) read the catalog with instances_io's text scanner."""
    catalog = _write(tmp_path / "instances.toml", CATALOG)
    assert _upsert(catalog, "17.0", "p1", "server_wide_modules[]=to_base,viin_brand").returncode == 0
    assert _upsert(catalog, "17.0", "", "server_wide_modules[]=").returncode == 0
    rows = _load_io()._load_textscan(str(catalog))["instance"]
    assert rows[0]["server_wide_modules"] == ["to_base", "viin_brand"]
    assert rows[0]["custom_key"] == "keep me"
    assert rows[1]["server_wide_modules"] == []


def test_string_upsert_still_escapes_and_round_trips(tmp_path):
    catalog = _write(tmp_path / "instances.toml", CATALOG)
    hostile = 'pa"th\\with\\tbackslash'
    assert _upsert(catalog, "17.0", "", "python=%s" % hostile).returncode == 0
    assert tomllib.loads(catalog.read_text())["instance"][1]["python"] == hostile


@pytest.mark.parametrize("series, profile, needle", [
    ("16.0", "", "declare it first"),
    ("17.0", "nope", "declare it first"),
])
def test_upsert_refuses_an_undeclared_row_and_leaves_the_file_untouched(tmp_path, series, profile,
                                                                         needle):
    catalog = _write(tmp_path / "instances.toml", CATALOG)
    res = _upsert(catalog, series, profile, "server_wide_modules[]=x")
    assert res.returncode == 1 and needle in res.stderr
    assert catalog.read_text() == CATALOG


def test_upsert_refuses_to_guess_a_profile(tmp_path):
    only_profiled = CATALOG.split("[[instance]]\nseries = \"17.0\"\naddons_path = [\"/b\"]")[0]
    catalog = _write(tmp_path / "instances.toml", only_profiled)
    res = _upsert(catalog, "17.0", "", "server_wide_modules[]=x")
    assert res.returncode == 1 and "--profile" in res.stderr
    assert catalog.read_text() == only_profiled


def test_upsert_keeps_the_catalogs_permission_bits(tmp_path):
    """A catalog locked to its owner (it can name hosts, users and paths) must not come back
    world-readable because a setup step recorded one fact on it."""
    catalog = _write(tmp_path / "instances.toml", CATALOG)
    catalog.chmod(0o600)
    assert _upsert(catalog, "17.0", "", "python=/v/bin/python").returncode == 0
    assert (catalog.stat().st_mode & 0o777) == 0o600


def test_upsert_through_a_symlinked_catalog_writes_the_target_and_keeps_the_link(tmp_path):
    """A catalog kept in a dotfiles repo and symlinked into place must stay a symlink: replacing
    the link with a regular file silently forks the catalog from the one the operator edits."""
    target = _write(tmp_path / "dotfiles" / "instances.toml", CATALOG)
    target.chmod(0o640)
    link = tmp_path / "home" / "instances.toml"
    link.parent.mkdir()
    link.symlink_to(target)
    assert _upsert(link, "17.0", "", "python=/v/bin/python").returncode == 0
    assert link.is_symlink() and link.resolve() == target.resolve()
    assert tomllib.loads(target.read_text())["instance"][1]["python"] == "/v/bin/python"
    assert (target.stat().st_mode & 0o777) == 0o640
    assert sorted(p.name for p in link.parent.iterdir()) == ["instances.toml"], "no temp debris"


@pytest.mark.parametrize("before, after", [
    ('python = "/old/bin/python"   # the team venv\n',
     'python = "/v/bin/python"   # the team venv\n'),
    ('python = "/o#ld"\n', 'python = "/v/bin/python"\n'),
    ('server_wide_modules = [\n  "a",  # item note\n]  # why these\n',
     'server_wide_modules = ["/v/bin/python"]  # why these\n'),
], ids=["inline-comment", "hash-inside-the-string-is-not-a-comment", "multi-line-array"])
def test_upsert_keeps_a_replaced_keys_inline_comment(tmp_path, before, after):
    key = before.split(" ", 1)[0]
    pair = ("%s[]=/v/bin/python" if key == "server_wide_modules" else "%s=/v/bin/python") % key
    text = '[[instance]]\nseries = "17.0"\n' + before + 'db_name = "d"\n'
    catalog = _write(tmp_path / "instances.toml", text)
    assert _upsert(catalog, "17.0", "", pair).returncode == 0
    assert catalog.read_text() == '[[instance]]\nseries = "17.0"\n' + after + 'db_name = "d"\n'
    tomllib.loads(catalog.read_text())


def _old_python(version: str) -> str | None:
    """An ALREADY-INSTALLED interpreter of `version` (PATH, else uv without downloading)."""
    found = shutil.which("python" + version)
    if found:
        return found
    uv = shutil.which("uv")
    if uv:
        res = subprocess.run([uv, "python", "find", version], capture_output=True, text=True,
                             env={**os.environ, "UV_PYTHON_DOWNLOADS": "never"}, timeout=60)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    return None


def _annotations_need_the_future_import(tree) -> bool:
    """True when an annotation uses a builtin generic (`list[str]`) or a `X | Y` union - forms
    Python 3.8 evaluates, and fails on, at import unless annotations are postponed."""
    import ast
    notes = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for a in args.posonlyargs + args.args + args.kwonlyargs + [args.vararg, args.kwarg]:
                if a is not None and a.annotation is not None:
                    notes.append(a.annotation)
            if node.returns is not None:
                notes.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            notes.append(node.annotation)
    for note in notes:
        for sub in ast.walk(note):
            if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr):
                return True
            if (isinstance(sub, ast.Subscript) and isinstance(sub.value, ast.Name)
                    and sub.value.id in ("list", "dict", "tuple", "set", "frozenset", "type")):
                return True
    return False


def test_config_merge_imports_on_python_3_8_grammar_and_annotations():
    """config_merge.py serves the JSON-only setup steps, which do not require a 3.11 host."""
    import ast
    src = CONFIG_MERGE.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(CONFIG_MERGE), feature_version=(3, 8))
    postponed = any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
                    and any(a.name == "annotations" for a in n.names) for n in tree.body)
    assert postponed or not _annotations_need_the_future_import(tree), (
        "config_merge.py has annotations Python 3.8 evaluates and rejects at import")


def test_config_merge_runs_its_json_and_toml_writers_under_a_real_python_3_8(tmp_path):
    py38 = _old_python("3.8")
    if py38 is None:
        pytest.skip("no Python 3.8 interpreter installed (the grammar test above still guards)")
    settings = tmp_path / "settings.json"
    res = subprocess.run([py38, str(CONFIG_MERGE), "json-merge", str(settings)], input='{"a": 1}',
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    assert json.loads(settings.read_text()) == {"a": 1}
    catalog = _write(tmp_path / "instances.toml", CATALOG)
    res = subprocess.run([py38, str(CONFIG_MERGE), "toml-upsert-instance-keys", str(catalog),
                          "17.0", "", "python=/v/bin/python"],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    assert tomllib.loads(catalog.read_text())["instance"][1]["python"] == "/v/bin/python"


# ============================================================ step 46 (server-wide)

def _catalog_for(tmp_path: Path, core: Path, addons: Path, extra: str = "") -> Path:
    return _write(tmp_path / "instances.toml", textwrap.dedent(f"""\
        [[instance]]
        series = "17.0"
        profile = "p1"
        addons_path = ["{addons}", "{core / 'addons'}"]
        odoo_root = "{core}"
        {extra}
    """))


@requires_bash
def test_propose_unions_evidence_minus_core_and_keeps_undetected_declared_modules(tmp_path):
    core = _core(tmp_path, load="base,web")
    addons = tmp_path / "custom"
    _addon(addons, "mod_self", SELF_CHECK.format(m="mod_self"))
    _addon(addons, "mod_plain", "x = 1\n")
    log = _write(tmp_path / "probe.log",
                 "2026-01-01 00:00:00,000 1 WARNING db odoo.addons.mod_logged: The module "
                 "`mod_logged` should be loaded in server wide mode using `--load` option\n")
    catalog = _catalog_for(tmp_path, core, addons,
                           'server_wide_modules = ["operator_added", "web"]')
    res = _run([STEP46, "propose", "--series", "17.0", "--profile", "p1", "--log", log],
               _env(tmp_path, catalog))
    assert res.returncode == 0, res.stderr
    facts = _kv(res.stdout)
    assert facts["CORE_SERVER_WIDE_MODULES"] == "base,web"
    assert facts["SELF_DECLARED_SERVER_WIDE"] == "mod_self"
    assert facts["LOG_WARNINGS"] == "mod_logged"
    assert facts["UNDETECTED_CURRENT"] == "operator_added"
    assert facts["PROPOSED_SERVER_WIDE_MODULES"] == "mod_logged,mod_self,operator_added", (
        "the proposal is every piece of evidence plus what the row declares, WITHOUT the core "
        "default the tools apply on their own")
    assert facts["DECLARED"] == "1"


@requires_bash
def test_propose_says_when_the_core_default_is_unreadable(tmp_path):
    addons = tmp_path / "custom"
    _addon(addons, "mod_self", SELF_CHECK.format(m="mod_self"))
    catalog = _write(tmp_path / "instances.toml",
                     '[[instance]]\nseries = "17.0"\naddons_path = ["%s"]\n' % addons)
    res = _run([STEP46, "propose", "--series", "17.0"], _env(tmp_path, catalog))
    assert res.returncode == 0, res.stderr
    facts = _kv(res.stdout)
    assert facts["CORE_READABLE"] == "0" and facts["CORE_SERVER_WIDE_MODULES"] == ""
    assert facts["DECLARED"] == "0"
    assert facts["PROPOSED_SERVER_WIDE_MODULES"] == "mod_self"


@requires_bash
def test_propose_refuses_an_undeclared_row(tmp_path):
    catalog = _write(tmp_path / "instances.toml", '[[instance]]\nseries = "16.0"\naddons_path = []\n')
    res = _run([STEP46, "propose", "--series", "17.0"], _env(tmp_path, catalog))
    assert res.returncode == 1 and "declare it first" in res.stderr


@requires_bash
def test_check_lists_unconfirmed_rows_and_record_confirms_them(tmp_path):
    core = _core(tmp_path)
    addons = tmp_path / "custom"
    addons.mkdir()
    catalog = _catalog_for(tmp_path, core, addons)
    env = _env(tmp_path, catalog)

    res = _run([STEP46, "check"], env)
    assert res.returncode == 1 and "17.0:p1" in res.stdout

    res = _run([STEP46, "apply"], env)
    assert res.returncode == 1, "apply proposes only; confirmation is the operator's"
    assert "server_wide_modules" not in catalog.read_text(), "apply must write nothing"

    res = _run([STEP46, "record", "--series", "17.0", "--profile", "p1",
                "--modules", " to_base, viin_brand ,to_base"], env)
    assert res.returncode == 0, res.stderr
    row = tomllib.loads(catalog.read_text())["instance"][0]
    assert row["server_wide_modules"] == ["to_base", "viin_brand"]
    assert row["odoo_root"] == str(core)
    assert _run([STEP46, "check"], env).returncode == 0


@requires_bash
def test_record_of_an_empty_list_is_a_confirmed_none(tmp_path):
    core = _core(tmp_path)
    catalog = _catalog_for(tmp_path, core, tmp_path / "custom")
    env = _env(tmp_path, catalog)
    assert _run([STEP46, "record", "--series", "17.0", "--profile", "p1", "--modules", ""],
                env).returncode == 0
    assert tomllib.loads(catalog.read_text())["instance"][0]["server_wide_modules"] == []
    assert _run([STEP46, "check"], env).returncode == 0


@requires_bash
@pytest.mark.parametrize("args, needle", [
    (["--series", "17.0", "--profile", "p1"], "--modules is required"),
    (["--series", "17.0", "--profile", "p1", "--modules", "good,bad-name"], "not an Odoo module"),
    (["--series", "17.0", "--profile", "p1", "--modules", "a;rm -rf x"], "not an Odoo module"),
])
def test_record_refuses_an_unconfirmed_or_invalid_list(tmp_path, args, needle):
    core = _core(tmp_path)
    catalog = _catalog_for(tmp_path, core, tmp_path / "custom")
    before = catalog.read_text()
    res = _run([STEP46, "record", *args], _env(tmp_path, catalog))
    assert res.returncode == 2 and needle in res.stderr
    assert catalog.read_text() == before


@requires_bash
def test_step40_never_overwrites_a_row_whose_server_wide_set_was_confirmed(tmp_path):
    core = _core(tmp_path)
    addons = tmp_path / "custom"
    addons.mkdir()
    catalog = tmp_path / "home" / "instances.toml"
    spec = _write(tmp_path / "spec.json", json.dumps(
        [{"series": "17.0", "addons_path": [str(addons), str(core / "addons")]}]))
    env = _env(tmp_path, catalog)
    env["ODOO_AI_PROFILE_SPEC"] = str(spec)
    project = tmp_path / "project"
    project.mkdir()
    assert _run([STEP40, "apply"], env, cwd=project).returncode == 0
    env46 = _env(tmp_path, catalog)
    assert _run([STEP46, "record", "--series", "17.0", "--modules", "to_base"],
                env46).returncode == 0
    res = _run([STEP40, "apply"], env, cwd=project)
    assert res.returncode == 0 and "already present" in res.stdout
    assert tomllib.loads(catalog.read_text())["instance"][0]["server_wide_modules"] == ["to_base"]


# ============================================================ python range (steps 40 / 45)

def _catalog_with_core(tmp_path: Path, core: Path | None, series: str = "17.0") -> Path:
    addons = core / "addons" if core else tmp_path / "nowhere" / "addons"
    return _write(tmp_path / "instances.toml",
                  '[[instance]]\nseries = "%s"\naddons_path = ["%s"]\n' % (series, addons))


@requires_bash
def test_suggest_reads_the_range_from_the_checkout_not_the_table(tmp_path):
    table = json.loads(MATRIX.read_text())["odoo_python_matrix"]["17.0"]
    core = _core(tmp_path, min_py=(3, 11), max_py=(3, 13))
    res = _run([STEP45, "suggest", "17.0"], _env(tmp_path, _catalog_with_core(tmp_path, core)))
    assert res.returncode == 0, res.stderr
    assert "3.11-3.13" in res.stdout and "release.py" in res.stdout
    assert "(%s-%s" % (table["min"], table["max"]) not in res.stdout
    # the table's editorial pick is honoured while it lies inside the source range
    assert "Recommended Python for Odoo 17.0: %s" % table["recommended"] in res.stdout


@requires_bash
def test_suggest_recommends_the_source_minimum_when_the_table_pick_is_out_of_range(tmp_path):
    core = _core(tmp_path, min_py=(3, 40), max_py=(3, 41))
    res = _run([STEP45, "suggest", "17.0"], _env(tmp_path, _catalog_with_core(tmp_path, core)))
    assert "Recommended Python for Odoo 17.0: 3.40" in res.stdout


@requires_bash
def test_suggest_covers_a_series_the_table_does_not_know(tmp_path):
    core = _core(tmp_path, min_py=(3, 13), max_py=(3, 15))
    res = _run([STEP45, "suggest", "99.0"],
               _env(tmp_path, _catalog_with_core(tmp_path, core, series="99.0")))
    assert "3.13-3.15" in res.stdout and "Recommended Python for Odoo 99.0: 3.13" in res.stdout


@requires_bash
def test_suggest_falls_back_to_the_table_only_without_a_readable_checkout(tmp_path):
    table = json.loads(MATRIX.read_text())["odoo_python_matrix"]["17.0"]
    res = _run([STEP45, "suggest", "17.0"], _env(tmp_path, _catalog_with_core(tmp_path, None)))
    assert "fallback table" in res.stdout
    assert "Recommended Python for Odoo 17.0: %s" % table["recommended"] in res.stdout


@requires_bash
def test_step40_python_hint_is_read_from_the_spec_checkout(tmp_path):
    core = _core(tmp_path, min_py=(3, 40), max_py=(3, 41))
    catalog = tmp_path / "home" / "instances.toml"
    spec = _write(tmp_path / "spec.json", json.dumps(
        [{"series": "17.0", "addons_path": [str(core / "addons")]}]))
    env = _env(tmp_path, catalog)
    env["ODOO_AI_PROFILE_SPEC"] = str(spec)
    project = tmp_path / "project"
    project.mkdir()
    res = _run([STEP40, "apply"], env, cwd=project)
    assert res.returncode == 0, res.stderr
    text = catalog.read_text()
    assert "suggested Python for 17.0: 3.40 (supported 3.40-3.41" in text, text


@requires_bash
def test_record_env_warns_when_the_venv_python_is_outside_the_source_range(tmp_path):
    core = _core(tmp_path, min_py=(3, 40), max_py=(3, 41))
    odoo_bin = core / "odoo-bin"
    odoo_bin.write_text("#!/usr/bin/env bash\necho 'Odoo Server 17.0'\n")
    odoo_bin.chmod(0o755)
    (core / "requirements.txt").write_text("")
    venv_py = tmp_path / "venv" / "bin" / "python"
    venv_py.parent.mkdir(parents=True)
    venv_py.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi\n'
        'if [[ "$1" == "-c" && "$2" == *version_info* ]]; then echo "3.9"; exit 0; fi\n'
        'exec %s "$@"\n' % real_python3())
    venv_py.chmod(0o755)
    catalog = _write(tmp_path / "instances.toml",
                     '[[instance]]\nseries = "17.0"\naddons_path = ["%s"]\npython = "%s"\n'
                     % (core / "addons", venv_py))
    env = _env(tmp_path, catalog)
    env["PG_MODE_PROBE_TIMEOUT"] = "2"
    res = _run([STEP45, "record-env", "--series", "17.0"], env)
    assert "Python 3.9, outside the range Odoo 17.0 declares" in res.stderr, res.stderr
    row = tomllib.loads(catalog.read_text())["instance"][0]
    assert row["python"] == str(venv_py) and row["odoo_root"] == str(core), (
        "the warning is advisory: verified facts are still recorded")


# ============================================================ create-venv --tool pip interpreter selection
#
# Defect this guards: `create-venv --tool pip` used to try `python$pyver` and, the
# moment that exact binary was missing, silently fall back to bare `python3` -
# whatever version that happened to be - building (and RECORDING) a venv with the
# wrong interpreter. It must instead look for another interpreter still inside the
# series' declared range (PATH, pyenv, an already-installed uv-managed python - never
# fetched) and say which it picked, or refuse with NEEDS_CONTEXT (exit 3, like the
# Python 2 path) and record nothing.

def _core_launcher(core: Path, series_label: str = "17.0") -> None:
    """Add an executable odoo-bin launcher + requirements.txt to a `_core()` checkout -
    what `_core_odoo_bin_for_series` needs to find a launcher on the addons_path."""
    odoo_bin = core / "odoo-bin"
    odoo_bin.write_text("#!/usr/bin/env bash\necho 'Odoo Server %s'\n" % series_label)
    odoo_bin.chmod(0o755)
    (core / "requirements.txt").write_text("", encoding="utf-8")


def _pip_range_python_stub(real_py3: str) -> str:
    """A fake `python3.NN` whose `-m venv <dir>` fabricates a venv good enough for
    create-venv's own verification gate: bin/python intercepts the `<odoo-bin>
    --version` call create-venv makes to prove the venv can run Odoo, and delegates
    everything else to the REAL python3; bin/pip is a no-op. Same style the other
    step-45 tests use to stub the `uv` tool, adapted to stand in for the interpreter
    `--tool pip` invokes directly."""
    return f"""#!/usr/bin/env bash
if [[ "$1" == "-m" && "$2" == "venv" ]]; then
  dir="$3"
  mkdir -p "$dir/bin"
  cat > "$dir/bin/python" <<'PYEOF'
#!/usr/bin/env bash
if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
exec {real_py3} "$@"
PYEOF
  chmod +x "$dir/bin/python"
  printf '#!/usr/bin/env bash\\nexit 0\\n' > "$dir/bin/pip"
  chmod +x "$dir/bin/pip"
  exit 0
fi
exec {real_py3} "$@"
"""


@requires_bash
def test_create_venv_pip_refuses_rather_than_fall_back_to_an_out_of_range_python3(tmp_path, path_farm):
    """No interpreter anywhere is inside the checkout's declared range (3.40-3.41,
    unreachable on a real host - the same exotic pair other tests in this file use to
    guarantee a real host's ambient `python3` is NOT in range): refuse, build nothing,
    record nothing."""
    core = _core(tmp_path, min_py=(3, 40), max_py=(3, 41))
    _core_launcher(core)
    catalog = _write(tmp_path / "instances.toml",
                     '[[instance]]\nseries = "17.0"\naddons_path = ["%s"]\n' % (core / "addons"))
    env = _env(tmp_path, catalog)
    env["PATH"] = farm_path(path_farm())
    env["PG_MODE_PROBE_TIMEOUT"] = "2"
    venv_path = tmp_path / "venv"
    res = _run([STEP45, "create-venv", "--series", "17.0", "--tool", "pip",
                "--path", str(venv_path)], env)
    assert res.returncode == 3, res.stderr
    assert "NEEDS_CONTEXT" in res.stderr
    assert "3.40" in res.stderr and "3.41" in res.stderr
    assert "was NOT recorded" in res.stderr
    assert not (venv_path / "bin" / "python").exists(), "nothing must be built on refusal"
    assert "python" not in tomllib.loads(catalog.read_text())["instance"][0]


@requires_bash
def test_create_venv_pip_locates_an_in_range_interpreter_instead_of_a_silent_wrong_version(
        tmp_path, path_farm):
    """The recommended python3.40 is missing, but python3.41 - still inside the
    checkout's declared 3.40-3.41 range - is on PATH: create-venv must use IT, say so,
    and record it. It must never silently reach for bare `python3` instead."""
    core = _core(tmp_path, min_py=(3, 40), max_py=(3, 41))
    _core_launcher(core)
    catalog = _write(tmp_path / "instances.toml",
                     '[[instance]]\nseries = "17.0"\naddons_path = ["%s"]\n' % (core / "addons"))
    own_bin = tmp_path / "own_bin"
    own_bin.mkdir()
    stub = own_bin / "python3.41"
    stub.write_text(_pip_range_python_stub(real_python3()), encoding="utf-8")
    stub.chmod(0o755)
    env = _env(tmp_path, catalog)
    env["PATH"] = farm_path(path_farm(), own_bin)
    env["PG_MODE_PROBE_TIMEOUT"] = "2"
    venv_path = tmp_path / "venv"
    res = _run([STEP45, "create-venv", "--series", "17.0", "--tool", "pip",
                "--path", str(venv_path)], env)
    assert res.returncode == 0, res.stderr
    assert "using python3.41" in res.stderr, res.stderr
    assert "falling back to python3" not in (res.stdout + res.stderr)
    row = tomllib.loads(catalog.read_text())["instance"][0]
    assert row["python"] == str(venv_path / "bin" / "python")


# ------------------------------------------------ no source upper bound: never claim one
#
# Defect this guards: with a checkout that declares only a MINIMUM (setup.py `>=3.6`, the
# 11.0-14.0 shape), the pip interpreter search used to start at min+20 and walk DOWN, so
# it picked the NEWEST installed python (3.14 for 13.0) and said it was "inside Odoo's
# supported range". The source says nothing of the kind. The search must start at the
# recommended version and go UP (oldest acceptable first), say that no upper bound is
# declared, and treat the fallback table's editorial max - when it has one - as a soft cap.

def _poisoned_python_stub(marker: Path) -> str:
    """A `python3.NN` that must NOT be chosen: building a venv with it leaves a marker."""
    return (f"#!/usr/bin/env bash\n"
            f'if [[ "$1" == "-m" && "$2" == "venv" ]]; then touch {marker}; exit 1; fi\n'
            f'exec {real_python3()} "$@"\n')


def _open_range_world(tmp_path: Path, path_farm, series: str, good: list[str], bad: list[str],
                      drop: tuple[str, ...]):
    """A checkout declaring only a minimum Python, a catalog row for `series`, and a PATH
    offering the `good` interpreters (working stubs) and the `bad` ones (poisoned)."""
    core = _core(tmp_path, min_py=(3, 6) if series == "13.0" else (3, 10), max_py=None)
    _core_launcher(core, series)
    catalog = _write(tmp_path / "instances.toml",
                     '[[instance]]\nseries = "%s"\naddons_path = ["%s"]\n' % (series, core / "addons"))
    own_bin = tmp_path / "own_bin"
    own_bin.mkdir()
    marker = tmp_path / "poisoned-python-used"
    for ver in good:
        stub = own_bin / ("python" + ver)
        stub.write_text(_pip_range_python_stub(real_python3()), encoding="utf-8")
        stub.chmod(0o755)
    for ver in bad:
        stub = own_bin / ("python" + ver)
        stub.write_text(_poisoned_python_stub(marker), encoding="utf-8")
        stub.chmod(0o755)
    env = _env(tmp_path, catalog)
    # uv and pyenv would otherwise offer the host's own interpreters ahead of the stubs.
    env["PATH"] = farm_path(path_farm(drop=("uv", "uvx") + drop), own_bin)
    env["PYENV_ROOT"] = str(tmp_path / "no-pyenv")
    env["PG_MODE_PROBE_TIMEOUT"] = "2"
    return core, catalog, env, marker


def _minor_names(lo: int, hi: int) -> tuple[str, ...]:
    return tuple("python3.%d" % m for m in range(lo, hi + 1))


@requires_bash
def test_create_venv_pip_without_a_source_max_picks_the_oldest_acceptable_not_the_newest(
        tmp_path, path_farm):
    table = json.loads(MATRIX.read_text())["odoo_python_matrix"]["13.0"]
    assert table["max"] is None, "fixture premise: 13.0's table entry declares no max"
    # recommended (the table pick) is missing; 3.8 and 3.14 are installed
    core, catalog, env, marker = _open_range_world(
        tmp_path, path_farm, "13.0", good=["3.8"], bad=["3.14"],
        drop=_minor_names(6, 7) + _minor_names(9, 13))
    venv_path = tmp_path / "venv"
    res = _run([STEP45, "create-venv", "--series", "13.0", "--tool", "pip",
                "--path", str(venv_path)], env)
    assert res.returncode == 0, res.stderr
    assert not marker.exists(), "the newest installed python was chosen over the oldest acceptable"
    assert "using python3.8 on PATH" in res.stderr, res.stderr
    assert "declares no upper Python bound" in res.stderr, res.stderr
    assert "inside" not in res.stderr, "must not claim a range the source never declared"
    assert tomllib.loads(catalog.read_text())["instance"][0]["python"] == str(venv_path / "bin" / "python")


@requires_bash
def test_create_venv_pip_prefers_an_interpreter_within_the_tables_soft_cap(tmp_path, path_farm):
    table = json.loads(MATRIX.read_text())["odoo_python_matrix"]["17.0"]
    cap = int(table["max"].split(".")[1])
    rec = int(table["recommended"].split(".")[1])
    below, above = "3.%d" % (rec - 1), "3.%d" % (cap + 1)
    core, catalog, env, marker = _open_range_world(
        tmp_path, path_farm, "17.0", good=[below], bad=[above],
        drop=_minor_names(rec, cap))
    res = _run([STEP45, "create-venv", "--series", "17.0", "--tool", "pip",
                "--path", str(tmp_path / "venv")], env)
    assert res.returncode == 0, res.stderr
    assert not marker.exists(), "an interpreter above the soft cap won over one within it"
    assert "using python%s on PATH" % below in res.stderr, res.stderr
    assert "editorial cap (%s)" % table["max"] in res.stderr, res.stderr


@requires_bash
def test_create_venv_pip_uses_an_interpreter_above_the_soft_cap_only_with_a_warning(
        tmp_path, path_farm):
    table = json.loads(MATRIX.read_text())["odoo_python_matrix"]["17.0"]
    cap = int(table["max"].split(".")[1])
    above = "3.%d" % (cap + 1)
    core, catalog, env, marker = _open_range_world(
        tmp_path, path_farm, "17.0", good=[above], bad=[],
        drop=_minor_names(10, cap))
    res = _run([STEP45, "create-venv", "--series", "17.0", "--tool", "pip",
                "--path", str(tmp_path / "venv")], env)
    assert res.returncode == 0, res.stderr
    assert "using python%s on PATH" % above in res.stderr, res.stderr
    assert "Warning" in res.stderr and "above it" in res.stderr, res.stderr


# ------------------------------------------------ record-env selects its row before probing
#
# Defect this guards: `record-env --series S` with no --profile on a series whose rows are all
# profiled read one of them anyway, printed its DB_AUTH / CREATEDB preflight lines and only then
# refused to record - facts for a row nobody selected. And with a profiled row listed BEFORE the
# unprofiled one, it read the profiled row's python and recorded it onto the unprofiled row.

def _stub_venv_python(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi\n'
        'exec %s "$@"\n' % real_python3())
    path.chmod(0o755)
    return path


@requires_bash
def test_record_env_without_profile_on_a_profiled_only_series_refuses_before_any_probe(tmp_path):
    core = _core(tmp_path)
    _core_launcher(core)
    venv_py = _stub_venv_python(tmp_path / "venv" / "bin" / "python")
    catalog = _write(tmp_path / "instances.toml",
                     '[[instance]]\nseries = "17.0"\nprofile = "p1"\naddons_path = ["%s"]\n'
                     'python = "%s"\n' % (core / "addons", venv_py))
    before = catalog.read_bytes()
    env = _env(tmp_path, catalog)
    env["PG_MODE_PROBE_TIMEOUT"] = "2"
    res = _run([STEP45, "record-env", "--series", "17.0"], env)
    out = res.stdout + res.stderr
    assert res.returncode != 0, out
    assert "--profile" in res.stderr, res.stderr
    for probe in ("DB_AUTH", "CREATEDB", "DB_PREFLIGHT"):
        assert probe not in out, "a probe ran for a row nobody selected:\n" + out
    assert catalog.read_bytes() == before


@requires_bash
def test_record_env_without_profile_reads_and_records_the_unprofiled_row(tmp_path):
    core = _core(tmp_path)
    _core_launcher(core)
    profiled_py = _stub_venv_python(tmp_path / "venv-p1" / "bin" / "python")
    plain_py = _stub_venv_python(tmp_path / "venv-plain" / "bin" / "python")
    catalog = _write(tmp_path / "instances.toml",
                     '[[instance]]\nseries = "17.0"\nprofile = "p1"\naddons_path = ["%s"]\n'
                     'python = "%s"\n\n'
                     '[[instance]]\nseries = "17.0"\naddons_path = ["%s"]\npython = "%s"\n'
                     % (core / "addons", profiled_py, core / "addons", plain_py))
    env = _env(tmp_path, catalog)
    env["PG_MODE_PROBE_TIMEOUT"] = "2"
    _run([STEP45, "record-env", "--series", "17.0"], env)
    rows = tomllib.loads(catalog.read_text())["instance"]
    assert rows[0]["python"] == str(profiled_py)
    assert rows[1]["python"] == str(plain_py), "the profiled row's python was recorded on the unprofiled row"
