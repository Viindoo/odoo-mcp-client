"""Behavior tests for scripts/lib/odoo_source_facts.py - Odoo build facts read from source text.

The contract protected here: a fact Odoo itself declares (the default `--load` set, the
supported Python range) is READ from the checkout, so a new Odoo series needs no plugin edit;
and the deployment fact "which addons must load server-wide" is PROPOSED from the addons' own
self-checks and from Odoo's own log warning, never guessed.

Two layers:
  - fixture trees under tmp_path (deterministic, portable): every source shape the readers must
    understand - including the exact self-check spellings real addons ship (comma-string
    `.split(',')` form, list form, `odoo.conf` form, a call wrapped over lines) - and the shapes
    they must NOT mistake for a self-check.
  - real Odoo checkouts, when present: `$ODOO_SOURCE_CHECKOUTS/odoo_<series>` (default: a `git`
    directory under the home directory). Each series whose checkout is absent SKIPS. The
    expected values are the ones surveyed by reading each series' source by hand, stated here
    independently of the reader under test.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "odoo_source_facts.py"


def _load():
    spec = importlib.util.spec_from_file_location("odoo_source_facts_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


facts = _load()

CHECKOUTS = Path(os.environ.get("ODOO_SOURCE_CHECKOUTS") or (Path.home() / "git"))


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _cli(*args, stdin: str | None = None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin, capture_output=True, text=True, timeout=60,
    )


def _kv(stdout: str) -> dict:
    return dict(line.split("=", 1) for line in stdout.splitlines() if "=" in line)


# ---------------------------------------------------------------- core --load default

def test_core_default_read_from_string_my_default(tmp_path):
    _write(tmp_path / "odoo" / "tools" / "config.py",
           'group.add_option("--load", dest="server_wide_modules", '
           'help="Comma-separated list of server-wide modules.", my_default=\'base,web\')\n')
    assert facts.core_server_wide_modules(tmp_path) == ["base", "web"]


def test_core_default_resolved_through_named_constant(tmp_path):
    _write(tmp_path / "odoo" / "tools" / "config.py",
           "DEFAULT_SERVER_WIDE_MODULES = [\n    'base',\n    'rpc',\n    'web',\n]\n"
           "class C:\n    def f(self, group):\n"
           "        group.add_option(\"--load\", dest=\"server_wide_modules\", type='comma',"
           " metavar='MODULE,...', my_default=DEFAULT_SERVER_WIDE_MODULES,\n"
           "                         help=\"Comma-separated list of server-wide modules.\")\n")
    assert facts.core_server_wide_modules(tmp_path) == ["base", "rpc", "web"]


def test_core_default_read_from_the_openerp_package_of_the_oldest_series(tmp_path):
    _write(tmp_path / "openerp" / "tools" / "config.py",
           'group.add_option("--load", dest="server_wide_modules", my_default=\'web,web_kanban\')\n')
    assert facts.core_server_wide_modules(tmp_path) == ["web", "web_kanban"]


@pytest.mark.parametrize("body", [
    "",  # no --load option at all
    'group.add_option("--load", dest="server_wide_modules", help="x")\n',  # no my_default
    'group.add_option("--load", dest="server_wide_modules", my_default=UNDEFINED_NAME)\n',
])
def test_core_default_unreadable_is_none_never_a_guess(tmp_path, body):
    _write(tmp_path / "odoo" / "tools" / "config.py", body)
    assert facts.core_server_wide_modules(tmp_path) is None


def test_core_default_missing_checkout_is_none(tmp_path):
    assert facts.core_server_wide_modules(tmp_path / "absent") is None
    assert facts.core_server_wide_modules("") is None


# ---------------------------------------------------------------- python support

def test_python_range_from_release_py_min_and_max(tmp_path):
    _write(tmp_path / "odoo" / "release.py", "MIN_PY_VERSION = (3, 12)\nMAX_PY_VERSION = (3, 14)\n")
    _write(tmp_path / "setup.py", "setup(python_requires='>=3.5')\n")
    assert facts.python_support(tmp_path) == {"min": "3.12", "max": "3.14", "source": "release.py"}


def test_python_range_from_package_init_when_release_py_has_none(tmp_path):
    _write(tmp_path / "odoo" / "release.py", "version_info = (16, 0, 0, 'final', 0, '')\n")
    _write(tmp_path / "odoo" / "__init__.py", "MIN_PY_VERSION = (3, 7)\nMAX_PY_VERSION = (3, 12)\n")
    assert facts.python_support(tmp_path) == {"min": "3.7", "max": "3.12", "source": "__init__.py"}


def test_python_setup_py_lower_bound_leaves_max_open(tmp_path):
    _write(tmp_path / "setup.py", "setup(\n    python_requires='>=3.6',\n)\n")
    assert facts.python_support(tmp_path) == {"min": "3.6", "max": None, "source": "setup.py"}


def test_python_setup_py_inclusive_upper_bound_is_kept(tmp_path):
    _write(tmp_path / "setup.py", "setup(python_requires='>=3.5, <=3.8')\n")
    assert facts.python_support(tmp_path) == {"min": "3.5", "max": "3.8", "source": "setup.py"}


def test_python2_series_from_debian_control(tmp_path):
    _write(tmp_path / "debian" / "control", "Source: odoo\nX-Python-Version: 2.7\n")
    assert facts.python_support(tmp_path) == {"min": "2.7", "max": "2.7", "source": "debian"}


@pytest.mark.parametrize("launcher", ["odoo-bin", "openerp-server"])
def test_python2_series_from_launcher_shebang(tmp_path, launcher):
    _write(tmp_path / launcher, "#!/usr/bin/env python\nimport sys\n")
    assert facts.python_support(tmp_path) == {"min": "2.7", "max": "2.7", "source": "shebang"}


def test_python3_shebang_alone_is_not_evidence_of_a_range(tmp_path):
    _write(tmp_path / "odoo-bin", "#!/usr/bin/env python3\n")
    assert facts.python_support(tmp_path) is None


def test_python_nothing_readable_is_none(tmp_path):
    assert facts.python_support(tmp_path) is None
    assert facts.python_support("") is None


# ---------------------------------------------------------------- locate root / recommendation

def test_locate_root_prefers_the_declared_root_then_walks_up_from_addons(tmp_path):
    core = tmp_path / "core"
    _write(core / "odoo" / "release.py", "version_info = (17, 0)\n")
    (core / "odoo" / "addons").mkdir(parents=True)
    (core / "addons").mkdir()
    assert facts.locate_odoo_root(str(core), []) == str(core)
    assert facts.locate_odoo_root(None, [str(core / "addons")]) == str(core)
    assert facts.locate_odoo_root(None, [str(core / "odoo" / "addons") + "/"]) == str(core)
    assert facts.locate_odoo_root(str(tmp_path / "wrong"), [str(core / "addons")]) == str(core)
    assert facts.locate_odoo_root(None, [str(tmp_path / "custom")]) is None
    assert facts.locate_odoo_root() is None


def _launcher(path):
    _write(path, "#!/usr/bin/env python\n")
    path.chmod(0o755)
    return path


def test_launcher_is_openerp_server_on_the_oldest_shape_and_odoo_bin_after(tmp_path):
    old = tmp_path / "old"
    _write(old / "openerp" / "release.py", "version_info = (8, 0)\n")
    (old / "openerp" / "addons").mkdir(parents=True)
    server = _launcher(old / "openerp-server")
    assert facts.core_launcher(old) == str(server)
    assert facts.locate_odoo_launcher(None, [str(old / "openerp" / "addons")]) == str(server)
    assert facts.locate_odoo_root(None, [str(old / "openerp" / "addons")]) == str(old)
    new = tmp_path / "new"
    binary = _launcher(new / "odoo-bin")
    (new / "addons").mkdir()
    assert facts.locate_odoo_launcher(str(tmp_path / "nowhere"), [str(new / "addons")]) == str(binary)
    assert facts.locate_odoo_root(None, [str(new / "addons")]) == str(new), (
        "a launcher alone marks a checkout root")


def test_launcher_must_be_executable_and_the_declared_root_comes_first(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _launcher(a / "odoo-bin")
    _write(b / "openerp-server", "#!/usr/bin/env python\n")  # not executable
    (b / "addons").mkdir()
    assert facts.core_launcher(b) is None
    assert facts.locate_odoo_launcher(str(a), [str(b / "addons")]) == str(a / "odoo-bin")
    assert facts.locate_odoo_launcher(None, [str(b / "addons")]) is None


def test_cli_locate_launcher(tmp_path):
    server = _launcher(tmp_path / "c" / "openerp-server")
    (tmp_path / "c" / "addons").mkdir()
    r = _cli("locate-launcher", str(tmp_path / "c" / "addons"))
    assert r.returncode == 0 and _kv(r.stdout) == {"ODOO_LAUNCHER": str(server),
                                                   "ODOO_ROOT": str(tmp_path / "c")}
    assert _cli("locate-launcher", str(tmp_path / "nothing")).returncode == 3


@pytest.mark.parametrize("series, launcher", [("8.0", "openerp-server"), ("9.0", "openerp-server"),
                                              ("10.0", "odoo-bin"), ("20.0", "odoo-bin")])
def test_real_checkout_launcher(series, launcher):
    root = _checkout(series)
    assert facts.locate_odoo_launcher(None, [str(root / "addons")]) == str(root / launcher)


def _matrix(tmp_path, entries):
    return str(_write(tmp_path / "matrix.json", json.dumps({"odoo_python_matrix": entries})))


def test_recommendation_takes_the_range_from_source_and_the_pick_only_inside_it(tmp_path):
    _write(tmp_path / "c" / "odoo" / "release.py", "MIN_PY_VERSION = (3, 10)\nMAX_PY_VERSION = (3, 14)\n")
    m = _matrix(tmp_path, {"17.0": {"min": "3.9", "max": "3.11", "recommended": "3.12"}})
    assert facts.python_recommendation("17.0", tmp_path / "c", m) == {
        "recommended": "3.12", "min": "3.10", "max": "3.14", "source": "release.py",
        "python2": False}
    m = _matrix(tmp_path, {"17.0": {"min": "3.9", "max": "3.11", "recommended": "3.9"}})
    assert facts.python_recommendation("17.0", tmp_path / "c", m)["recommended"] == "3.10"


def test_recommendation_for_an_unknown_series_comes_from_source_alone(tmp_path):
    _write(tmp_path / "c" / "odoo" / "release.py", "MIN_PY_VERSION = (3, 13)\nMAX_PY_VERSION = (3, 15)\n")
    info = facts.python_recommendation("99.0", tmp_path / "c", _matrix(tmp_path, {}))
    assert (info["recommended"], info["min"], info["max"]) == ("3.13", "3.13", "3.15")


def test_recommendation_falls_back_to_the_table_only_without_a_checkout(tmp_path):
    m = _matrix(tmp_path, {"10.0": {"min": "2.7", "max": "2.7", "recommended": "2.7"}})
    assert facts.python_recommendation("10.0", tmp_path / "absent", m) == {
        "recommended": "2.7", "min": "2.7", "max": "2.7", "source": "matrix", "python2": True}
    assert facts.python_recommendation("11.0", None, m) is None


def test_recommendation_open_upper_bound_accepts_any_newer_pick(tmp_path):
    _write(tmp_path / "c" / "setup.py", "setup(python_requires='>=3.6')\n")
    m = _matrix(tmp_path, {"14.0": {"min": "3.6", "max": None, "recommended": "3.8"}})
    info = facts.python_recommendation("14.0", tmp_path / "c", m)
    assert (info["recommended"], info["max"], info["source"]) == ("3.8", None, "setup.py")


def test_cli_python_suggest_and_locate_root(tmp_path):
    _write(tmp_path / "c" / "odoo" / "release.py", "MIN_PY_VERSION = (3, 13)\nMAX_PY_VERSION = (3, 15)\n")
    (tmp_path / "c" / "addons").mkdir()
    r = _cli("python-suggest", "99.0", str(tmp_path / "c"))
    assert r.returncode == 0 and _kv(r.stdout) == {
        "PY_RECOMMENDED": "3.13", "PY_MIN": "3.13", "PY_MAX": "3.15", "PY_SOURCE": "release.py",
        "PY_PYTHON2": "0"}
    assert _cli("python-suggest", "99.0").returncode == 3
    r = _cli("locate-root", "--odoo-root", str(tmp_path / "x"), str(tmp_path / "c" / "addons"))
    assert r.returncode == 0 and _kv(r.stdout) == {"ODOO_ROOT": str(tmp_path / "c")}
    assert _cli("locate-root", str(tmp_path)).returncode == 3


# ---------------------------------------------------------------- self-declared server-wide

def _addon(base: Path, name: str, files: dict, descriptor: str = "__manifest__.py") -> None:
    _write(base / name / descriptor, "{'name': '%s'}\n" % name)
    for rel, text in files.items():
        _write(base / name / rel, text)


COMMA_FORM = (
    "def _test_if_loaded_in_server_wide():\n"
    "    config_options = config.options\n"
    "    if '{m}' in config_options.get('server_wide_modules', '').split(','):\n"
    "        return True\n"
    "    return False\n"
)
LIST_FORM = (
    "def _test_if_loaded_in_server_wide():\n"
    "    if '{m}' in config_options.get('server_wide_modules', []):\n"
    "        return True\n"
)
WRAPPED_FORM = (
    'if config.get("proxy_mode") and "{m}" in config.get(\n'
    '    "server_wide_modules"\n'
    "):\n    http.db_filter = db_filter\n"
)
CONF_FORM = "if '{m}' not in odoo.conf.server_wide_modules:\n    _logger.warning('load me')\n"


@pytest.mark.parametrize("form, rel", [
    (COMMA_FORM, "__init__.py"),
    (LIST_FORM, "__init__.py"),
    (WRAPPED_FORM, "override.py"),
    (CONF_FORM, "models/hooks.py"),
])
def test_module_checking_its_own_name_is_self_declared(tmp_path, form, rel):
    _addon(tmp_path, "mod_a", {rel: form.format(m="mod_a")})
    assert facts.self_declared_server_wide([str(tmp_path)]) == ["mod_a"]


def test_oldest_series_descriptor_is_recognised(tmp_path):
    _addon(tmp_path, "mod_old", {"__init__.py": COMMA_FORM.format(m="mod_old")},
           descriptor="__openerp__.py")
    assert facts.self_declared_server_wide([str(tmp_path)]) == ["mod_old"]


@pytest.mark.parametrize("files", [
    # checks ANOTHER module's name - that module, not this one, is the candidate
    {"__init__.py": COMMA_FORM.format(m="other_mod")},
    # iterates the option without naming itself (a test helper, a controller)
    {"__init__.py": "for name in odoo.conf.server_wide_modules:\n    pass\n"},
    # a commented-out self-check is not a self-check
    {"__init__.py": "# if 'mod_b' in config.get('server_wide_modules'):\n#     pass\n"},
    # own name and the option on unrelated statements
    {"__init__.py": "if 'mod_b' in installed:\n    mods = config['server_wide_modules']\n"},
    # prose in the manifest asking the reader to add it is documentation, not code
    {"__manifest__.py": "{'name': 'mod_b', 'description': \"Add 'mod_b' in the server_wide_modules list\"}\n"},
    # a self-check shipped only as a static asset is not server-side code
    {"static/src/x.py": COMMA_FORM.format(m="mod_b")},
])
def test_non_self_checks_are_not_reported(tmp_path, files):
    _addon(tmp_path, "mod_b", files)
    assert facts.self_declared_server_wide([str(tmp_path)]) == []


def test_non_addon_directories_are_ignored(tmp_path):
    _write(tmp_path / "not_an_addon" / "__init__.py", COMMA_FORM.format(m="not_an_addon"))
    assert facts.self_declared_server_wide([str(tmp_path)]) == []


def test_results_are_sorted_and_deduplicated_across_paths(tmp_path):
    p1, p2 = tmp_path / "p1", tmp_path / "p2"
    _addon(p1, "zeta", {"__init__.py": LIST_FORM.format(m="zeta")})
    _addon(p1, "alpha", {"__init__.py": COMMA_FORM.format(m="alpha")})
    _addon(p2, "zeta", {"__init__.py": COMMA_FORM.format(m="zeta")})
    _addon(p2, "plain", {"__init__.py": "x = 1\n"})
    assert facts.self_declared_server_wide([str(p1), str(p2), str(tmp_path / "missing"), ""]) == [
        "alpha", "zeta"]


def test_no_paths_yields_empty():
    assert facts.self_declared_server_wide([]) == []
    assert facts.self_declared_server_wide(None) == []


# ---------------------------------------------------------------- log warnings

REAL_WARNING_LINES = (
    "2026-09-16 21:46:51,149 1471884 WARNING db_x odoo.addons.viin_brand: The module `viin_brand` "
    "should be loaded in server wide mode using `--load` option when starting Odoo server "
    "(e.g. --load=base,web,viin_brand). Otherwise, module icons and the favicon are only branded "
    "after an update. \n"
    "2026-09-16 21:46:52,001 1471884 WARNING db_x odoo.addons.to_base.__init__: The module `to_base` "
    "should be loaded in server wide mode using `--load` option when starting Odoo server "
    "(e.g. --load=base,web,to_base). Otherwise, some of its functions may not work properly.\n"
    "2026-09-16 21:46:53,001 1471884 WARNING db_x odoo.addons.to_base: The module `to_base` "
    "should be loaded in server wide mode using `--load` option when starting Odoo server\n"
)


def test_warning_lines_name_the_modules_once_each_sorted():
    assert facts.server_wide_warning_modules(REAL_WARNING_LINES) == ["to_base", "viin_brand"]


def test_log_without_the_warning_yields_nothing():
    log = ("2026-09-16 21:46:51,149 1 WARNING db odoo.modules.loading: The module `x` has no "
           "installable version\n2026-09-16 INFO db odoo.modules.loading: loading 42 modules...\n")
    assert facts.server_wide_warning_modules(log) == []
    assert facts.server_wide_warning_modules("") == []
    assert facts.server_wide_warning_modules(None) == []


# ---------------------------------------------------------------- CLI

def test_cli_core_load_and_python_match_the_api(tmp_path):
    _write(tmp_path / "odoo" / "tools" / "config.py",
           'group.add_option("--load", dest="server_wide_modules", my_default=\'base,web\')\n')
    _write(tmp_path / "setup.py", "setup(python_requires='>=3.6')\n")
    r = _cli("core-load", str(tmp_path))
    assert r.returncode == 0 and _kv(r.stdout) == {"CORE_SERVER_WIDE_MODULES": "base,web"}
    r = _cli("python", str(tmp_path))
    assert r.returncode == 0
    assert _kv(r.stdout) == {"PY_MIN": "3.6", "PY_MAX": "", "PY_SOURCE": "setup.py"}


def test_cli_unreadable_checkout_exits_3_without_a_fact(tmp_path):
    for sub in ("core-load", "python"):
        r = _cli(sub, str(tmp_path))
        assert r.returncode == 3 and r.stdout == ""


def test_cli_self_declared_and_warnings(tmp_path):
    _addon(tmp_path, "mod_a", {"__init__.py": COMMA_FORM.format(m="mod_a")})
    r = _cli("self-declared", str(tmp_path))
    assert r.returncode == 0 and _kv(r.stdout) == {"SELF_DECLARED_SERVER_WIDE": "mod_a"}
    log = _write(tmp_path / "run.log", REAL_WARNING_LINES)
    r = _cli("warnings", str(log))
    assert r.returncode == 0 and _kv(r.stdout) == {"SERVER_WIDE_WARNINGS": "to_base,viin_brand"}
    r = _cli("warnings", stdin=REAL_WARNING_LINES)
    assert _kv(r.stdout) == {"SERVER_WIDE_WARNINGS": "to_base,viin_brand"}


@pytest.mark.parametrize("args", [[], ["bogus"], ["core-load"], ["python", "a", "b"], ["self-declared"]])
def test_cli_usage_errors_exit_2(args):
    assert _cli(*args).returncode == 2


# ---------------------------------------------------------------- real checkouts (skip when absent)

# Surveyed by reading each series' own source (config.py `--load` my_default /
# DEFAULT_SERVER_WIDE_MODULES; release.py or __init__.py MIN/MAX_PY_VERSION, else setup.py
# python_requires, else debian/control X-Python-Version).
SURVEY = {
    "8.0": (["web", "web_kanban"], ("2.7", "2.7")),
    "9.0": (["web", "web_kanban"], ("2.7", "2.7")),
    "10.0": (["web", "web_kanban"], ("2.7", "2.7")),
    "11.0": (["web"], ("3.5", None)),
    "12.0": (["base", "web"], ("3.5", None)),
    "13.0": (["base", "web"], ("3.6", None)),
    "14.0": (["base", "web"], ("3.6", None)),
    "15.0": (["base", "web"], ("3.7", "3.12")),
    "16.0": (["base", "web"], ("3.7", "3.12")),
    "17.0": (["base", "web"], ("3.10", "3.14")),
    "18.0": (["base", "web"], ("3.10", "3.14")),
    "19.0": (["base", "rpc", "web"], ("3.10", "3.14")),
    "20.0": (["base", "rpc", "web"], ("3.12", "3.14")),
}


def _checkout(series: str) -> Path:
    root = CHECKOUTS / ("odoo_%s" % series)
    if not root.is_dir():
        pytest.skip("no Odoo %s checkout at %s" % (series, root))
    return root


@pytest.mark.parametrize("series", sorted(SURVEY, key=lambda s: float(s)))
def test_real_checkout_core_default(series):
    assert facts.core_server_wide_modules(_checkout(series)) == SURVEY[series][0]


@pytest.mark.parametrize("series", sorted(SURVEY, key=lambda s: float(s)))
def test_real_checkout_python_range(series):
    info = facts.python_support(_checkout(series))
    assert info is not None
    assert (info["min"], info["max"]) == SURVEY[series][1]


@pytest.mark.parametrize("series", ["8.0", "12.0", "17.0", "19.0"])
def test_real_core_addons_declare_no_self_checked_module(series):
    root = _checkout(series)
    pkg = "openerp" if (root / "openerp").is_dir() else "odoo"
    assert facts.self_declared_server_wide([str(root / "addons"), str(root / pkg / "addons")]) == []


# ---------------------------------------------------------------- CLI option facts
#
# Series boundaries a build depends on - whether demo loads by default, the main and second
# listening port option, the `--dev` option's shape, the logger namespace, what each short option
# stands for - are declared by the checkout's own `tools/config.py` (and its core package dir).
# They are READ from there, so a new series needs no plugin edit; a checkout that does not state
# one yields None, never a guess.

OPTS_MODERN = (
    'class configmanager:\n'
    '    def __init__(self):\n'
    '        group.add_option("-c", "--config", dest="config", type="path")\n'
    '        group.add_option("-s", "--save", action="store_true", dest="save", my_default=False)\n'
    '        group.add_option("-t", "--test-tags", dest="test_tags", file_loadable=False,\n'
    '                         help="Comma-separated list of specs")\n'
    '        group.add_option("--with-demo", dest="with_demo", action=\'store_true\', my_default=False,\n'
    '                         help="install demo data in new databases.")\n'
    '        group.add_option("--without-demo", dest="with_demo", type=\'without_demo\', metavar=\'BOOL\',\n'
    '                         nargs=\'?\', const=True, help="don\'t install demo data")\n'
    '        group.add_option("-p", "--http-port", dest="http_port", my_default=8069,\n'
    '                         help="Listen port for the main HTTP service", type="int", metavar="PORT")\n'
    '        group.add_option("--gevent-port", dest="gevent_port", my_default=8072, type="int")\n'
    '        group.add_option("--xmlrpc-port", dest="http_port", type="int", help=hidden)\n'
    "        group.add_option('--dev', dest='dev_mode', type='comma', metavar=\"FEATURE,...\")\n"
)
OPTS_LEGACY = (
    'class configmanager(object):\n'
    '    def __init__(self, fname=None):\n'
    '        group.add_option("-s", "--save", action="callback", callback=self._save, nargs=0)\n'
    '        group.add_option("--without-demo", dest="without_demo",\n'
    '                         help="disable loading demo data for modules to be installed", my_default=False)\n'
    '        group.add_option("--xmlrpc-port", dest="xmlrpc_port", my_default=8069, type="int")\n'
    '        group.add_option("--longpolling-port", dest="longpolling_port", my_default=8072, type="int")\n'
    '        group.add_option("-t", "--timezone", dest="timezone", my_default=False)\n'
    '        # group.add_option("--with-demo", dest="with_demo", action="store_true")\n'
)


def _config(root: Path, pkg: str, body: str) -> Path:
    _write(root / pkg / "release.py", "version_info = (1, 0, 0, 'final', 0, '')\n")
    _write(root / pkg / "tools" / "config.py", body)
    return root


def test_demo_is_opt_in_where_the_checkout_declares_with_demo(tmp_path):
    assert facts.demo_opt_in(_config(tmp_path / "new", "odoo", OPTS_MODERN)) is True
    assert facts.demo_opt_in(_config(tmp_path / "old", "openerp", OPTS_LEGACY)) is False, (
        "a --with-demo only inside a comment is no option: demo still loads by default there")


def test_an_explicit_no_demo_option_is_read_wherever_the_checkout_declares_one(tmp_path):
    """--without-demo is how a build states "no demo" in so many words, so no config-file value
    can flip it: declared beside --with-demo on the opt-in series and alone on the older ones."""
    assert facts.without_demo_declared(_config(tmp_path / "new", "odoo", OPTS_MODERN)) is True
    assert facts.without_demo_declared(_config(tmp_path / "old", "openerp", OPTS_LEGACY)) is True
    only_with = _config(tmp_path / "with", "odoo",
                        'group.add_option("--with-demo", dest="with_demo", action="store_true")\n')
    assert facts.without_demo_declared(only_with) is False
    assert facts.without_demo_declared(tmp_path / "absent") is None


@pytest.mark.parametrize("body", [None, "", "# placeholder\n",
                                  'group.add_option("--load", dest="server_wide_modules")\n'])
def test_demo_default_unreadable_is_none_never_a_guess(tmp_path, body):
    if body is not None:
        _config(tmp_path, "odoo", body)
    assert facts.demo_opt_in(tmp_path) is None
    assert facts.demo_opt_in("") is None


def test_port_option_keys_are_the_option_dests_the_checkout_declares(tmp_path):
    new = _config(tmp_path / "new", "odoo", OPTS_MODERN)
    old = _config(tmp_path / "old", "openerp", OPTS_LEGACY)
    assert facts.http_port_key(new) == "http_port", "--http-port wins over its hidden --xmlrpc-port alias"
    assert facts.http_port_key(old) == "xmlrpc_port"
    assert facts.second_port_key(new) == "gevent_port"
    assert facts.second_port_key(old) == "longpolling_port"
    empty = _config(tmp_path / "empty", "odoo", "# nothing\n")
    assert facts.http_port_key(empty) is None and facts.second_port_key(empty) is None
    assert facts.http_port_key(tmp_path / "absent") is None


def test_dev_value_and_short_options_and_core_package_are_read_from_the_checkout(tmp_path):
    new = _config(tmp_path / "new", "odoo", OPTS_MODERN)
    old = _config(tmp_path / "old", "openerp", OPTS_LEGACY)
    assert facts.dev_takes_value(new) is True
    assert facts.dev_takes_value(old) is False, "no --dev option at all: nothing to pass a value to"
    _config(tmp_path / "flag", "openerp", "group.add_option('--dev', dest='dev_mode', action='store_true')\n")
    assert facts.dev_takes_value(tmp_path / "flag") is False, "a boolean --dev takes no =all"
    shorts = facts.short_options(new)
    assert shorts["t"] == {"long": "test-tags", "takes_value": True}
    assert shorts["s"] == {"long": "save", "takes_value": False}
    assert shorts["p"] == {"long": "http-port", "takes_value": True}
    assert shorts["h"] == {"long": "help", "takes_value": False}, "optparse's own -h"
    legacy = facts.short_options(old)
    assert legacy["t"] == {"long": "timezone", "takes_value": True}
    assert legacy["s"] == {"long": "save", "takes_value": False}, "a callback with nargs=0 takes no value"
    assert "p" not in legacy
    assert facts.core_package(new) == "odoo" and facts.core_package(old) == "openerp"
    for fn in (facts.dev_takes_value, facts.short_options, facts.core_package):
        assert fn(tmp_path / "absent") is None


def test_cli_option_facts_prints_every_fact_and_exits_3_when_unreadable(tmp_path):
    new = _config(tmp_path / "new", "odoo", OPTS_MODERN)
    r = _cli("cli-facts", str(new))
    assert r.returncode == 0, r.stderr
    assert _kv(r.stdout) == {"CORE_PACKAGE": "odoo", "DEMO_OPT_IN": "1", "WITHOUT_DEMO": "1",
                             "HTTP_PORT_KEY": "http_port", "SECOND_PORT_KEY": "gevent_port",
                             "DEV_TAKES_VALUE": "1"}
    old = _config(tmp_path / "old", "openerp", OPTS_LEGACY)
    assert _kv(_cli("cli-facts", str(old)).stdout) == {
        "CORE_PACKAGE": "openerp", "DEMO_OPT_IN": "0", "WITHOUT_DEMO": "1",
        "HTTP_PORT_KEY": "xmlrpc_port", "SECOND_PORT_KEY": "longpolling_port",
        "DEV_TAKES_VALUE": "0"}
    r = _cli("cli-facts", str(tmp_path / "absent"))
    assert r.returncode == 3 and r.stdout == "" and "tools/config.py" in r.stderr
    assert _cli("cli-facts").returncode == 2


# Surveyed by reading each series' odoo/tools/config.py (openerp/ before 10.0) by hand:
# (demo opt-in, main port dest, second port dest, --dev takes a value, core package, -t, -p).
OPTION_SURVEY = {
    "8.0": (False, "xmlrpc_port", "longpolling_port", False, "openerp", "timezone", None),
    "9.0": (False, "xmlrpc_port", "longpolling_port", False, "openerp", None, None),
    "10.0": (False, "xmlrpc_port", "longpolling_port", True, "odoo", None, None),
    "11.0": (False, "http_port", "longpolling_port", True, "odoo", None, "http-port"),
    "12.0": (False, "http_port", "longpolling_port", True, "odoo", None, "http-port"),
    "13.0": (False, "http_port", "longpolling_port", True, "odoo", None, "http-port"),
    "14.0": (False, "http_port", "longpolling_port", True, "odoo", None, "http-port"),
    "15.0": (False, "http_port", "longpolling_port", True, "odoo", None, "http-port"),
    "16.0": (False, "http_port", "gevent_port", True, "odoo", None, "http-port"),
    "17.0": (False, "http_port", "gevent_port", True, "odoo", "test-tags", "http-port"),
    "18.0": (False, "http_port", "gevent_port", True, "odoo", "test-tags", "http-port"),
    "19.0": (True, "http_port", "gevent_port", True, "odoo", "test-tags", "http-port"),
    "20.0": (True, "http_port", "gevent_port", True, "odoo", "test-tags", "http-port"),
}
# Short options with one meaning wherever a series declares them (value-taking except -s and -h;
# long names as odoo-bin accepts them, `_` spelled `-`), and the series that no longer declare
# one: -l/--language is gone from 19.0, -s/--save from 20.0 (the long options stay).
COMMON_SHORTS = {"c": "config", "s": "save", "i": "init", "u": "update", "P": "import-partial",
                 "D": "data-dir", "d": "database", "r": "db-user", "w": "db-password",
                 "l": "language", "h": "help"}
SHORTS_ABSENT = {"19.0": {"l"}, "20.0": {"l", "s"}}


@pytest.mark.parametrize("series", sorted(OPTION_SURVEY, key=lambda s: float(s)))
def test_real_checkout_option_facts(series):
    root = _checkout(series)
    demo, main, second, dev, pkg, t_long, p_long = OPTION_SURVEY[series]
    assert facts.demo_opt_in(root) is demo
    assert facts.without_demo_declared(root) is True, "every series states --without-demo"
    assert facts.http_port_key(root) == main
    assert facts.second_port_key(root) == second
    assert facts.dev_takes_value(root) is dev
    assert facts.core_package(root) == pkg
    shorts = facts.short_options(root)
    assert (shorts.get("t") or {}).get("long") == t_long
    assert (shorts.get("p") or {}).get("long") == p_long
    for char, long_name in COMMON_SHORTS.items():
        if char in SHORTS_ABSENT.get(series, ()):
            assert char not in shorts, (series, char)
            continue
        assert shorts[char]["long"] == long_name, (series, char)
        assert shorts[char]["takes_value"] is (char not in ("s", "h")), (series, char)


@pytest.mark.parametrize("series", sorted(OPTION_SURVEY, key=lambda s: float(s)))
def test_fixture_checkouts_state_the_facts_their_real_series_states(tmp_path, series):
    """Other suites build on fixture trees (tests/odoo_tree_fixtures.py); a fixture that drifts
    from its series would let them pass against a shape no real Odoo has."""
    sys.path.insert(0, str(ROOT / "tests"))
    import odoo_tree_fixtures as trees
    fixture = trees.write_checkout(tmp_path / "fx", series)
    real = _checkout(series)
    for fn in (facts.demo_opt_in, facts.without_demo_declared, facts.http_port_key,
               facts.second_port_key, facts.dev_takes_value, facts.core_package,
               facts.core_server_wide_modules):
        assert fn(fixture) == fn(real), (series, fn.__name__)
    assert facts.locate_odoo_root(None, [str(fixture / "addons")]) == str(fixture)
    assert facts.short_options(fixture) == facts.short_options(real), series


# ---------------------------------------------------------------- the i18n export command line
#
# Surveyed by reading each series' source by hand: through 18.0 the SERVER command exports
# (config.py declares --i18n-export, --modules and -l/--language); from 19.0 those options are
# gone and the `i18n` subcommand (odoo/cli/i18n.py) owns export, with an `export` subparser taking
# -l/--languages, -o/--output and positional modules, and -c/--config + -d/--database on every
# subparser (its connection facts come from the config file only).
SERVER_FORM = {"form": "server", "export": "--i18n-export", "modules": "--modules",
               "language": "--language"}
SUBCOMMAND_FORM = {"form": "subcommand", "command": "i18n", "subcommand": "export",
                   "config": "--config", "database": "--database", "output": "--output",
                   "languages": "--languages"}
I18N_SURVEY = dict({s: SERVER_FORM for s in ("8.0", "9.0", "10.0", "11.0", "12.0", "13.0", "14.0",
                                            "15.0", "16.0", "17.0", "18.0")},
                   **{"19.0": SUBCOMMAND_FORM, "20.0": SUBCOMMAND_FORM})

I18N_CLI = '''\
class I18n(Command):
    def __init__(self, *args, **kwargs):
        subparsers = self.parser.add_subparsers(dest='subcommand', required=True)
        self.import_parser = subparsers.add_parser(
            'import', help="Import i18n files")
        self.export_parser = subparsers.add_parser(
            'export', help="Export i18n files")
        self.loadlang_parser = subparsers.add_parser('loadlang')
        for parser in (self.import_parser, self.export_parser, self.loadlang_parser):
            parser.add_argument(
                '-c', '--config', dest='config')
            parser.add_argument(
                '-d', '--database', dest='db_name', default=None)
        self.import_parser.add_argument('-l', '--language', dest='language', required=True)
        self.export_parser.add_argument(
            '-l', '--languages', dest='languages', nargs='+', default=['pot'])
        self.export_parser.add_argument(
            'modules', nargs='+', metavar='MODULE')
        self.export_parser.add_argument(
            '-o', '--output', metavar="FILE", dest='output')
'''

SERVER_OPTS = '''\
        group.add_option('-l', "--language", dest="language", help="use with --i18n-export")
        group.add_option("--i18n-export", dest="translate_out", help="export all sentences")
        group.add_option("--modules", dest="translate_modules", help="modules to export")
'''


def test_the_server_command_exports_where_config_declares_i18n_export(tmp_path):
    root = _config(tmp_path / "old", "openerp", SERVER_OPTS)
    assert facts.i18n_export_cli(root) == SERVER_FORM


@pytest.mark.parametrize("drop", ["--i18n-export", "--modules", "--language"])
def test_a_server_form_missing_one_of_its_options_is_not_the_server_form(tmp_path, drop):
    body = "".join(ln + "\n" for ln in SERVER_OPTS.splitlines() if ('"%s"' % drop) not in ln)
    assert facts.i18n_export_cli(_config(tmp_path, "odoo", body)) is None, (
        "without %s the server command cannot export one module's file for one language" % drop)


def test_the_i18n_subcommand_exports_where_config_declares_no_i18n_export(tmp_path):
    root = _config(tmp_path, "odoo", "group.add_option('--load', dest='server_wide_modules')\n")
    _write(root / "odoo" / "cli" / "i18n.py", I18N_CLI)
    assert facts.i18n_export_cli(root) == SUBCOMMAND_FORM


@pytest.mark.parametrize("mutation", [
    ("'export', help", "'dump', help"),                  # no export subparser
    ("'-o', '--output'", "'-f', '--file'"),               # export writes no chosen file
    ("self.export_parser.add_argument(\n            '-l', '--languages'",
     "self.loadlang_parser.add_argument(\n            '-l', '--languages'"),  # --languages not export's
    ("'-c', '--config'", "'-x', '--extra'"),              # no config file: no connection facts
])
def test_an_i18n_subcommand_missing_what_the_export_needs_is_unknown(tmp_path, mutation):
    root = _config(tmp_path, "odoo", "# no server export\n")
    text = I18N_CLI.replace(*mutation)
    assert text != I18N_CLI, mutation
    _write(root / "odoo" / "cli" / "i18n.py", text)
    assert facts.i18n_export_cli(root) is None


def test_no_export_command_line_at_all_is_none_never_a_guess(tmp_path):
    assert facts.i18n_export_cli(_config(tmp_path, "odoo", "# nothing\n")) is None
    assert facts.i18n_export_cli(tmp_path / "absent") is None
    assert facts.i18n_export_cli("") is None


def test_cli_i18n_facts_prints_the_form_and_its_spellings_and_exits_3_when_unknown(tmp_path):
    old = _config(tmp_path / "old", "openerp", SERVER_OPTS)
    assert _kv(_cli("i18n-facts", str(old)).stdout) == {
        "I18N_FORM": "server", "I18N_EXPORT_FLAG": "--i18n-export", "I18N_MODULES_FLAG": "--modules",
        "I18N_LANGUAGE_FLAG": "--language"}
    new = _config(tmp_path / "new", "odoo", "# no server export\n")
    _write(new / "odoo" / "cli" / "i18n.py", I18N_CLI)
    assert _kv(_cli("i18n-facts", str(new)).stdout) == {
        "I18N_FORM": "subcommand", "I18N_COMMAND": "i18n", "I18N_SUBCOMMAND": "export",
        "I18N_CONFIG_FLAG": "--config", "I18N_DATABASE_FLAG": "--database",
        "I18N_OUTPUT_FLAG": "--output", "I18N_LANGUAGES_FLAG": "--languages"}
    r = _cli("i18n-facts", str(tmp_path / "absent"))
    assert r.returncode == 3 and r.stdout == "" and "i18n" in r.stderr
    assert _cli("i18n-facts").returncode == 2


@pytest.mark.parametrize("series", sorted(I18N_SURVEY, key=lambda s: float(s)))
def test_real_checkout_i18n_export_command_line(series):
    assert facts.i18n_export_cli(_checkout(series)) == I18N_SURVEY[series]


@pytest.mark.parametrize("series", sorted(I18N_SURVEY, key=lambda s: float(s)))
def test_fixture_checkouts_state_the_i18n_command_line_their_real_series_states(tmp_path, series):
    sys.path.insert(0, str(ROOT / "tests"))
    import odoo_tree_fixtures as trees
    fixture = trees.write_checkout(tmp_path / "fx", series)
    assert facts.i18n_export_cli(fixture) == I18N_SURVEY[series]
    assert facts.i18n_export_cli(fixture) == facts.i18n_export_cli(_checkout(series))
