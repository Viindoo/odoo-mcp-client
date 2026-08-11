"""Behavior tests for scripts/lib/odoo_db.py - through-Odoo DB drop/exists.

Tests are run as subprocess (the script is intended to run under a venv python)
with a FAKE ``odoo`` package injected on PYTHONPATH. This lets us verify the
contract without a real Odoo installation:

  1. ``drop foo``  - calls exp_drop('foo') exactly once AND set config['list_db']=True
     before the call; never spawns raw dropdb/psql.
  2. ``drop foo``  - NEVER invokes dropdb/psql even if they are on PATH.
  3. ``exists foo``- prints 'true' when fake exp_db_exist returns True, 'false' otherwise.
  4. No-venv path - when import odoo fails, exit code is EXIT_NO_VENV (10) and stderr
     carries the ``odoo_db: cannot import odoo (no venv?)`` marker.

Each test is red without the implementation and green with it per ETHOS #10.
"""

import importlib.util
import os
import subprocess
import sys
import textwrap
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ODOO_DB_PY = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "odoo_db.py"

# Exit codes mirrored from odoo_db.py (contract)
EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_AUTH_DENIED = 8
EXIT_UNREACHABLE = 9
EXIT_NO_VENV = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(*args, env_extra=None, pythonpath_prepend=None):
    """Run odoo_db.py as a subprocess; return CompletedProcess."""
    env = dict(os.environ)
    # Strip PYTHONPATH so real odoo/openerp never leaks in from the host venv.
    env.pop("PYTHONPATH", None)
    if pythonpath_prepend:
        env["PYTHONPATH"] = str(pythonpath_prepend)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(ODOO_DB_PY), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _build_fake_odoo(tmp_path, *, exp_drop_returns=True, exp_db_exist_returns=True,
                     marker_file=None):
    """Write a minimal fake ``odoo`` package under tmp_path/fake_odoo_pkg/.

    The fake records:
      - config['list_db'] value AT THE MOMENT exp_drop/exp_db_exist is called
        (written to marker_file as a line ``list_db=<value>``)
      - a line ``called=<fn_name>`` for which function fired
      - optionally raises if the return value is an Exception instance
    """
    pkg_root = tmp_path / "fake_odoo_pkg"

    odoo_dir = pkg_root / "odoo"
    odoo_dir.mkdir(parents=True)

    service_dir = odoo_dir / "service"
    service_dir.mkdir()

    tools_dir = odoo_dir / "tools"
    tools_dir.mkdir()

    # Marker file path as a Python string literal for embedding in source
    marker_str = repr(str(marker_file)) if marker_file else "None"

    # ---- odoo/__init__.py ----
    (odoo_dir / "__init__.py").write_text(
        textwrap.dedent("""\
        from odoo import tools, service
        """),
        encoding="utf-8",
    )

    # ---- odoo/tools/__init__.py ----
    (tools_dir / "__init__.py").write_text(
        textwrap.dedent("""\
        from odoo.tools import config as _config_module

        class _Config(dict):
            def parse_config(self, args=None):
                # Parse --db_host / --db_user / --db_password from args list
                args = args or []
                i = 0
                while i < len(args):
                    a = args[i]
                    if a in ('--db_host', '--db_user', '--db_password') and i + 1 < len(args):
                        key = a.lstrip('-').replace('db_', 'db_')
                        self[a.lstrip('-')] = args[i + 1]
                        i += 2
                    else:
                        i += 1

        config = _Config()
        """),
        encoding="utf-8",
    )

    # ---- odoo/tools/config.py (imported by __init__ as config module) ----
    (tools_dir / "config.py").write_text(
        textwrap.dedent("""\
        # placeholder - actual config object lives in tools/__init__.py
        """),
        encoding="utf-8",
    )

    # ---- odoo/service/__init__.py ----
    (service_dir / "__init__.py").write_text(
        textwrap.dedent(f"""\
        from odoo.service import db
        """),
        encoding="utf-8",
    )

    drop_ret = repr(exp_drop_returns)
    exist_ret = repr(exp_db_exist_returns)

    # ---- odoo/service/db.py ----
    (service_dir / "db.py").write_text(
        textwrap.dedent(f"""\
        from odoo.tools import config

        _MARKER_FILE = {marker_str}

        def _write_marker(fn_name):
            if _MARKER_FILE is None:
                return
            with open(_MARKER_FILE, 'a', encoding='utf-8') as fh:
                fh.write(f'list_db={{config.get(\"list_db\", \"NOT_SET\")}}\\n')
                fh.write(f'called={{fn_name}}\\n')

        def exp_drop(db_name):
            _write_marker('exp_drop')
            ret = {drop_ret}
            if isinstance(ret, BaseException):
                raise ret
            return ret

        def exp_db_exist(db_name):
            _write_marker('exp_db_exist')
            ret = {exist_ret}
            if isinstance(ret, BaseException):
                raise ret
            return ret
        """),
        encoding="utf-8",
    )

    return pkg_root


# ---------------------------------------------------------------------------
# Test 1: drop calls exp_drop and sets config['list_db']=True first
# ---------------------------------------------------------------------------

def test_drop_calls_exp_drop_and_sets_list_db(tmp_path):
    """drop <db> must call exp_drop exactly once AND have set config['list_db']=True."""
    marker = tmp_path / "marker.txt"
    pkg = _build_fake_odoo(tmp_path, exp_drop_returns=True, marker_file=marker)

    result = _run("drop", "my_test_db", pythonpath_prepend=pkg)
    assert result.returncode == EXIT_OK, (
        f"exit {result.returncode}; stderr={result.stderr!r}"
    )

    assert marker.exists(), "fake exp_drop was never called (marker file not written)"
    content = marker.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Verify list_db=True was set BEFORE the call
    assert "list_db=True" in lines, (
        f"config['list_db'] must be True when exp_drop is called; marker={content!r}"
    )
    # Verify the right function was called
    assert "called=exp_drop" in lines, (
        f"exp_drop must be called; marker={content!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: drop never spawns dropdb/psql
# ---------------------------------------------------------------------------

def test_drop_never_invokes_raw_dropdb_or_psql(tmp_path):
    """drop must NEVER invoke raw dropdb or psql even when they are on PATH."""
    # Shim binaries that write to a log and exit 0 (non-failing, just recording).
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    call_log = tmp_path / "pg_calls.log"

    for tool in ("dropdb", "psql", "createdb"):
        shim = bindir / tool
        shim.write_text(
            f'#!/bin/sh\necho "{tool} $*" >> "{call_log}"\n',
            encoding="utf-8",
        )
        shim.chmod(0o755)

    pkg = _build_fake_odoo(tmp_path, exp_drop_returns=True, marker_file=None)

    env_extra = {"PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"}
    result = _run("drop", "my_test_db", env_extra=env_extra, pythonpath_prepend=pkg)

    assert result.returncode == EXIT_OK, (
        f"exit {result.returncode}; stderr={result.stderr!r}"
    )

    # The shim log must not exist or must contain no PG tool invocations.
    if call_log.exists():
        calls = call_log.read_text(encoding="utf-8")
        assert calls.strip() == "", (
            f"odoo_db.py must NEVER spawn raw dropdb/psql/createdb; calls={calls!r}"
        )


# ---------------------------------------------------------------------------
# Test 3a: exists prints 'true' when exp_db_exist returns True
# ---------------------------------------------------------------------------

def test_exists_prints_true_when_db_present(tmp_path):
    pkg = _build_fake_odoo(tmp_path, exp_db_exist_returns=True, marker_file=None)
    result = _run("exists", "live_db", pythonpath_prepend=pkg)
    assert result.returncode == EXIT_OK, (
        f"exit {result.returncode}; stderr={result.stderr!r}"
    )
    assert result.stdout.strip() == "true", (
        f"expected 'true' on stdout; got {result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# Test 3b: exists prints 'false' when exp_db_exist returns False
# ---------------------------------------------------------------------------

def test_exists_prints_false_when_db_absent(tmp_path):
    pkg = _build_fake_odoo(tmp_path, exp_db_exist_returns=False, marker_file=None)
    result = _run("exists", "missing_db", pythonpath_prepend=pkg)
    assert result.returncode == EXIT_OK, (
        f"exit {result.returncode}; stderr={result.stderr!r}"
    )
    assert result.stdout.strip() == "false", (
        f"expected 'false' on stdout; got {result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: no venv -> EXIT_NO_VENV + stderr marker
# ---------------------------------------------------------------------------

def test_no_venv_exits_10_with_marker_on_stderr(tmp_path):
    """When import odoo fails, exit code must be 10 and stderr must contain
    the 'odoo_db: cannot import odoo (no venv?)' marker."""
    # PYTHONPATH pointing to an empty dir ensures neither odoo nor openerp is importable.
    empty = tmp_path / "empty_pythonpath"
    empty.mkdir()

    result = _run("drop", "some_db", pythonpath_prepend=empty)
    assert result.returncode == EXIT_NO_VENV, (
        f"expected exit {EXIT_NO_VENV} (venv unavailable); got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    assert "odoo_db: cannot import odoo (no venv?)" in result.stderr, (
        f"stderr must carry the venv-unavailable marker; stderr={result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Test 5: drop is idempotent - exp_drop returning False is still EXIT_OK
# ---------------------------------------------------------------------------

def test_drop_is_idempotent_when_db_already_absent(tmp_path):
    """exp_drop returning False (DB already absent) must still exit 0."""
    pkg = _build_fake_odoo(tmp_path, exp_drop_returns=False, marker_file=None)
    result = _run("drop", "already_gone", pythonpath_prepend=pkg)
    assert result.returncode == EXIT_OK, (
        f"drop of absent DB must be idempotent (exit 0); got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Test 6: password comes from ODOO_PG_PASSWORD env when no --db-password flag
# ---------------------------------------------------------------------------

def _build_fake_odoo_with_pw_record(tmp_path, marker_file):
    """Like _build_fake_odoo but parse_config RECORDS the db_password it received
    into the marker file so we can assert the exact secret reaches parse_config."""
    pkg_root = tmp_path / "fake_odoo_pw_pkg"

    odoo_dir = pkg_root / "odoo"
    odoo_dir.mkdir(parents=True)
    service_dir = odoo_dir / "service"
    service_dir.mkdir()
    tools_dir = odoo_dir / "tools"
    tools_dir.mkdir()

    marker_str = repr(str(marker_file))

    (odoo_dir / "__init__.py").write_text(
        "from odoo import tools, service\n",
        encoding="utf-8",
    )

    # tools/__init__.py: parse_config records the parsed db_password to the marker.
    (tools_dir / "__init__.py").write_text(
        textwrap.dedent("""\
        class _Config(dict):
            def parse_config(self, args=None):
                args = args or []
                i = 0
                while i < len(args):
                    a = args[i]
                    if a in ('--db_host', '--db_user', '--db_password') and i + 1 < len(args):
                        self[a.lstrip('-')] = args[i + 1]
                        i += 2
                    else:
                        i += 1
                # Record the resolved password to the marker file.
                import os as _os
                mf = {marker_str}
                if mf:
                    with open(mf, 'a', encoding='utf-8') as _fh:
                        _fh.write('db_password=' + str(self.get('db_password', '')) + '\\n')

        config = _Config()
        """.format(marker_str=marker_str)),
        encoding="utf-8",
    )
    (tools_dir / "config.py").write_text("# placeholder\n", encoding="utf-8")

    (service_dir / "__init__.py").write_text(
        "from odoo.service import db\n",
        encoding="utf-8",
    )
    (service_dir / "db.py").write_text(
        textwrap.dedent("""\
        from odoo.tools import config

        def exp_drop(db_name):
            return True

        def exp_db_exist(db_name):
            return True
        """),
        encoding="utf-8",
    )

    return pkg_root


def test_password_from_env_var(tmp_path):
    """ODOO_PG_PASSWORD env var must be forwarded to config parse_config as --db_password
    and the exact secret value must reach parse_config (not just exit 0)."""
    marker = tmp_path / "pw_marker.txt"
    pkg = _build_fake_odoo_with_pw_record(tmp_path, marker)

    secret = "s3cr3t_pw_value"
    result = _run(
        "drop", "some_db",
        env_extra={"ODOO_PG_PASSWORD": secret},
        pythonpath_prepend=pkg,
    )
    assert result.returncode == EXIT_OK, (
        "ODOO_PG_PASSWORD should be accepted; exit {rc}; stderr={err!r}".format(
            rc=result.returncode, err=result.stderr)
    )
    assert marker.exists(), "parse_config marker file was not written (parse_config not called?)"
    content = marker.read_text(encoding="utf-8")
    assert "db_password={secret}".format(secret=secret) in content, (
        "ODOO_PG_PASSWORD must reach parse_config as --db_password with the correct value; "
        "marker content: {content!r}".format(content=content)
    )


# ---------------------------------------------------------------------------
# Test 7: _import_odoo() binds .tools and .service.db even when a bare
# `import odoo` does NOT (Odoo 19.0 behaviour). Regression guard for #154.
# ---------------------------------------------------------------------------

def _build_fake_odoo_recording_conn(tmp_path, marker_file):
    """Like _build_fake_odoo but parse_config records EVERY --db_* connection arg
    it received (one ``key=value`` line per arg) AND exp_drop records the db name
    it was handed (``dropped=<db>``). Lets us assert #163's port + name threading.
    """
    pkg_root = tmp_path / "fake_odoo_conn_pkg"

    odoo_dir = pkg_root / "odoo"
    odoo_dir.mkdir(parents=True)
    service_dir = odoo_dir / "service"
    service_dir.mkdir()
    tools_dir = odoo_dir / "tools"
    tools_dir.mkdir()

    marker_str = repr(str(marker_file))

    (odoo_dir / "__init__.py").write_text(
        "from odoo import tools, service\n", encoding="utf-8",
    )
    (tools_dir / "__init__.py").write_text(
        textwrap.dedent("""\
        class _Config(dict):
            def parse_config(self, args=None):
                args = args or []
                mf = {marker_str}
                i = 0
                while i < len(args):
                    a = args[i]
                    if a.startswith('--') and i + 1 < len(args):
                        key = a.lstrip('-')
                        self[key] = args[i + 1]
                        if mf:
                            with open(mf, 'a', encoding='utf-8') as _fh:
                                _fh.write(key + '=' + str(args[i + 1]) + '\\n')
                        i += 2
                    else:
                        i += 1

        config = _Config()
        """.format(marker_str=marker_str)),
        encoding="utf-8",
    )
    (tools_dir / "config.py").write_text("# placeholder\n", encoding="utf-8")
    (service_dir / "__init__.py").write_text(
        "from odoo.service import db\n", encoding="utf-8",
    )
    (service_dir / "db.py").write_text(
        textwrap.dedent("""\
        from odoo.tools import config

        _MARKER_FILE = {marker_str}

        def exp_drop(db_name):
            if _MARKER_FILE:
                with open(_MARKER_FILE, 'a', encoding='utf-8') as fh:
                    fh.write('dropped=' + str(db_name) + '\\n')
            return True

        def exp_db_exist(db_name):
            return True
        """.format(marker_str=marker_str)),
        encoding="utf-8",
    )
    return pkg_root


def test_db_port_reaches_parse_config_as_db_port(tmp_path):
    """--db-port <n> must be forwarded to Odoo's parse_config as --db_port <n> (issue #163)."""
    marker = tmp_path / "conn.txt"
    pkg = _build_fake_odoo_recording_conn(tmp_path, marker)

    result = _run("drop", "mydb", "--db-port", "5430", pythonpath_prepend=pkg)
    assert result.returncode == EXIT_OK, f"exit {result.returncode}; stderr={result.stderr!r}"
    content = marker.read_text(encoding="utf-8")
    assert "db_port=5430" in content, (
        f"--db-port must reach parse_config as --db_port; marker={content!r}"
    )


def test_issue_163_port_flag_not_swallowed_as_db_name(tmp_path):
    """#163 repro: `drop mydb --db-port 5430` must drop 'mydb' on port 5430 -
    the flag must NOT be swallowed as a positional (dropping a DB named '--db-port')."""
    marker = tmp_path / "conn.txt"
    pkg = _build_fake_odoo_recording_conn(tmp_path, marker)

    result = _run("drop", "mydb", "--db-port", "5430", pythonpath_prepend=pkg)
    assert result.returncode == EXIT_OK, f"exit {result.returncode}; stderr={result.stderr!r}"
    content = marker.read_text(encoding="utf-8")
    assert "dropped=mydb" in content, (
        f"db name must be 'mydb' (not '--db-port' swallowed as positional); marker={content!r}"
    )
    assert "db_port=5430" in content, "port must still reach parse_config"


def test_unknown_flag_is_usage_error(tmp_path):
    """An unrecognized --flag must be a hard usage error, not a silent positional (issue #163)."""
    pkg = _build_fake_odoo(tmp_path, exp_drop_returns=True, marker_file=None)
    result = _run("drop", "mydb", "--bogus-flag", "x", pythonpath_prepend=pkg)
    assert result.returncode == EXIT_USAGE, (
        f"unknown flag must exit EXIT_USAGE ({EXIT_USAGE}); got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )


def test_drop_observability_performed_names_resolved_host_port(tmp_path):
    """Every drop emits a stderr line naming the RESOLVED host:port and performed/absent."""
    pkg = _build_fake_odoo(tmp_path, exp_drop_returns=True, marker_file=None)
    result = _run("drop", "mydb", "--db-host", "pghost", "--db-port", "5430",
                  pythonpath_prepend=pkg)
    assert result.returncode == EXIT_OK, f"stderr={result.stderr!r}"
    assert "odoo_db: drop 'mydb' on pghost:5430 -> performed" in result.stderr, (
        f"drop must emit a resolved-connection observability line; stderr={result.stderr!r}"
    )


def test_drop_observability_already_absent_uses_libpq_default(tmp_path):
    """An idempotent no-op drop (exp_drop False) is now OBSERVABLE as already-absent."""
    pkg = _build_fake_odoo(tmp_path, exp_drop_returns=False, marker_file=None)
    result = _run("drop", "mydb", pythonpath_prepend=pkg)
    assert result.returncode == EXIT_OK, f"stderr={result.stderr!r}"
    assert "odoo_db: drop 'mydb' on libpq-default:libpq-default -> already-absent" in result.stderr, (
        f"an absent-DB no-op must be observable and name the resolved connection; "
        f"stderr={result.stderr!r}"
    )


def test_import_odoo_binds_tools_and_service_db(tmp_path, monkeypatch):
    """_import_odoo() must bind .tools and .service.db even when a bare import does NOT
    (Odoo 19.0 behaviour: the base package's __init__ no longer re-exports submodules
    transitively). Regression guard for #154.

    Unlike ``_build_fake_odoo`` above (whose ``odoo/__init__.py`` does
    ``from odoo import tools, service`` - a bare import that DOES bind them), this fixture's
    fake ``odoo`` module is an in-memory package whose bare import binds NEITHER submodule.
    Only ``.tools`` / ``.service`` live on disk (reachable via ``__path__``), so
    ``importlib.import_module(pkg + ".tools")`` performs a genuine fresh load and lets
    Python's own submodule-to-parent binding do the work - exactly what the fix in
    ``_import_odoo()`` relies on. RED on current code (bare import leaves `.tools` unbound in
    this fixture), GREEN after the fix.
    """
    pkg_dir = tmp_path / "fake_odoo_pkg_root"
    tools_dir = pkg_dir / "tools"
    service_dir = pkg_dir / "service"
    tools_dir.mkdir(parents=True)
    service_dir.mkdir()

    (tools_dir / "__init__.py").write_text(
        "class _Config(dict):\n    pass\n\nconfig = _Config()\n",
        encoding="utf-8",
    )
    (service_dir / "__init__.py").write_text("", encoding="utf-8")
    (service_dir / "db.py").write_text("# stand-in for odoo.service.db\n", encoding="utf-8")

    # Fake 'odoo' package registered directly under sys.modules (not on disk) so a bare
    # `import odoo` resolves to it via the import-cache without binding any submodule.
    # __path__ points at the real .tools/.service dirs so importlib.import_module(pkg +
    # ".tools") can find and load them fresh, targeting this fake.
    fake_odoo = types.ModuleType("odoo")
    fake_odoo.__path__ = [str(pkg_dir)]
    monkeypatch.setitem(sys.modules, "odoo", fake_odoo)

    # Confirm the fixture's own premise: bare import leaves both submodules unbound.
    assert not hasattr(fake_odoo, "tools")
    assert not hasattr(fake_odoo, "service")

    try:
        spec = importlib.util.spec_from_file_location("odoo_db_under_test", ODOO_DB_PY)
        odoo_db_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(odoo_db_mod)

        result = odoo_db_mod._import_odoo()

        assert hasattr(result, "tools"), (
            "_import_odoo() must bind .tools even when a bare import does not"
        )
        assert hasattr(result.tools, "config"), (
            "the bound .tools must be the real fake odoo.tools module (with .config)"
        )
        assert hasattr(result, "service"), (
            "_import_odoo() must bind .service even when a bare import does not"
        )
        assert hasattr(result.service, "db"), (
            "the bound .service must expose .db (odoo.service.db)"
        )
    finally:
        # Self-cleaning: importlib.import_module() adds 'odoo.tools' / 'odoo.service' /
        # 'odoo.service.db' to sys.modules as a side effect of the fresh load; monkeypatch
        # only reverts the 'odoo' key set explicitly above, so remove the rest ourselves.
        for name in ("odoo.tools", "odoo.service", "odoo.service.db"):
            sys.modules.pop(name, None)


# ---------------------------------------------------------------------------
# Read-only cluster queries: can-createdb / list-databases / db-age-s /
# db-size-bytes, plus --odoo-root
#
# Every one of these goes through Odoo's OWN connection layer
# (odoo.sql_db.db_connect, openerp.sql_db on v8-v9), so a question about the
# cluster resolves the connection EXACTLY like drop/exists do. That is what makes
# it impossible for the CREATEDB verdict and the drop to disagree about WHICH
# cluster they mean - and it means none of them needs a libpq client binary.
# ---------------------------------------------------------------------------

def _build_fake_odoo_with_sql_db(tmp_path, *, rolcreatedb=True, databases=("a_db",),
                                 age=1234.5, size=4096, raise_on_connect=False,
                                 pkg_name="odoo", dirname="fake_odoo_sqldb"):
    """A fake Odoo package that also exposes sql_db.db_connect.

    `pkg_name` is a parameter because v8/v9 ship the SAME api under `openerp`:
    the script resolves the namespace and imports `<pkg>.sql_db` through it, so
    the openerp case must be exercised, not assumed.
    """
    pkg_root = tmp_path / dirname
    pkg_dir = pkg_root / pkg_name
    (pkg_dir / "service").mkdir(parents=True)
    (pkg_dir / "tools").mkdir()

    (pkg_dir / "__init__.py").write_text(
        f"from {pkg_name} import tools, service\n", encoding="utf-8")
    (pkg_dir / "tools" / "__init__.py").write_text(
        textwrap.dedent("""\
        class _Config(dict):
            def parse_config(self, args=None):
                args = args or []
                i = 0
                while i < len(args):
                    if args[i].startswith('--') and i + 1 < len(args):
                        self[args[i].lstrip('-')] = args[i + 1]
                        i += 2
                    else:
                        i += 1

        config = _Config()
        """), encoding="utf-8")
    (pkg_dir / "service" / "__init__.py").write_text(
        f"from {pkg_name}.service import db\n", encoding="utf-8")
    (pkg_dir / "service" / "db.py").write_text(
        "def exp_drop(db_name):\n    return True\n\n"
        "def exp_db_exist(db_name):\n    return True\n", encoding="utf-8")

    (pkg_dir / "sql_db.py").write_text(
        textwrap.dedent(f"""\
        _RAISE = {raise_on_connect!r}
        _ROLCREATEDB = {rolcreatedb!r}
        _DATABASES = {list(databases)!r}
        _AGE = {age!r}
        _SIZE = {size!r}


        class _Cursor(object):
            def __init__(self):
                self._rows = []

            def execute(self, sql, params=None):
                low = " ".join(sql.split()).lower()
                if "rolcreatedb" in low:
                    self._rows = [] if _ROLCREATEDB is None else [(_ROLCREATEDB,)]
                elif "pg_database where datistemplate" in low:
                    self._rows = [(n,) for n in _DATABASES]
                elif "pg_stat_file" in low:
                    self._rows = [] if _AGE is None else [(_AGE,)]
                elif "pg_database_size" in low:
                    self._rows = [] if _SIZE is None else [(_SIZE,)]
                elif low.startswith("select 1"):
                    self._rows = [(1,)]
                else:
                    raise AssertionError("unexpected SQL: " + sql)

            def fetchall(self):
                return self._rows

            def close(self):
                pass


        class _Connection(object):
            def cursor(self, *args, **kwargs):
                return _Cursor()


        def db_connect(to, allow_uri=False):
            if _RAISE:
                raise RuntimeError("could not connect to server")
            return _Connection()
        """), encoding="utf-8")
    return pkg_root


def test_can_createdb_answers_true_without_any_native_binary(tmp_path):
    """The verdict comes from the CLUSTER, so it must be answerable on a host with
    NO libpq client at all - the exact host class whose missing psql used to be
    reported as "this role may not create databases"."""
    bindir = tmp_path / "emptybin"
    bindir.mkdir()
    pkg = _build_fake_odoo_with_sql_db(tmp_path, rolcreatedb=True)
    # PATH holds only an EMPTY dir: no psql, no dropdb, no createdb anywhere.
    res = _run("can-createdb", "--db-host", "h", "--db-user", "u",
               env_extra={"PATH": str(bindir)}, pythonpath_prepend=pkg)
    assert res.returncode == EXIT_OK, f"stderr={res.stderr!r}"
    assert res.stdout.strip() == "true"


def test_can_createdb_answers_false_for_a_role_without_the_privilege(tmp_path):
    """A POSITIVE negative: the role exists and genuinely lacks CREATEDB. This must
    be distinguishable from 'could not ask' - the allocator maps them to different
    exits (6 vs 7) because the remedies differ."""
    pkg = _build_fake_odoo_with_sql_db(tmp_path, rolcreatedb=False)
    res = _run("can-createdb", "--db-host", "h", "--db-user", "u", pythonpath_prepend=pkg)
    assert res.returncode == EXIT_OK, f"stderr={res.stderr!r}"
    assert res.stdout.strip() == "false"


def test_can_createdb_fails_loudly_when_the_cluster_cannot_be_reached(tmp_path):
    """An unreachable cluster must NOT print a verdict. Printing `false` here would
    resurrect the false negative in a new place.

    The exit is the CLASSIFIED one (9 = the cluster did not answer), not the
    catch-all 1: a caller that cannot tell "this route is unavailable" from "this
    route works and the cluster is absent" asks another surface about a connection
    Odoo never makes, which is how a capability probe came to contradict the build.
    """
    pkg = _build_fake_odoo_with_sql_db(tmp_path, raise_on_connect=True)
    res = _run("can-createdb", "--db-host", "h", "--db-user", "u", pythonpath_prepend=pkg)
    assert res.returncode == EXIT_UNREACHABLE, f"got {res.returncode}"
    assert res.stdout.strip() == "", (
        f"no verdict may be printed when the question could not be asked; got {res.stdout!r}")
    assert "h" in res.stderr, "the diagnostic must name the host it could not reach"


def test_can_createdb_cannot_answer_when_the_role_has_no_pg_roles_row(tmp_path):
    """No row means the question was not answered - fail, do not infer `false`."""
    pkg = _build_fake_odoo_with_sql_db(tmp_path, rolcreatedb=None)
    res = _run("can-createdb", "--db-host", "h", "--db-user", "u", pythonpath_prepend=pkg)
    assert res.returncode == EXIT_FAILURE
    assert res.stdout.strip() == ""


def test_can_createdb_works_under_the_openerp_namespace(tmp_path):
    """v8/v9 ship this API as `openerp.sql_db`. The import resolves through the
    RESOLVED package name, so both namespaces must work with no version guess."""
    pkg = _build_fake_odoo_with_sql_db(tmp_path, rolcreatedb=True, pkg_name="openerp",
                                       dirname="fake_openerp_sqldb")
    res = _run("can-createdb", "--db-host", "h", "--db-user", "u", pythonpath_prepend=pkg)
    assert res.returncode == EXIT_OK, f"stderr={res.stderr!r}"
    assert res.stdout.strip() == "true"


def test_list_databases_prints_one_name_per_line(tmp_path):
    pkg = _build_fake_odoo_with_sql_db(tmp_path, databases=("alpha", "beta"))
    res = _run("list-databases", "--db-host", "h", "--db-user", "u", pythonpath_prepend=pkg)
    assert res.returncode == EXIT_OK, f"stderr={res.stderr!r}"
    assert res.stdout.split() == ["alpha", "beta"]


def test_list_databases_prints_nothing_and_fails_when_it_cannot_enumerate(tmp_path):
    """"Could not enumerate" must never be readable as "there are zero databases":
    the caller would then treat a whole cluster as having no orphans."""
    pkg = _build_fake_odoo_with_sql_db(tmp_path, raise_on_connect=True)
    res = _run("list-databases", "--db-host", "h", "--db-user", "u", pythonpath_prepend=pkg)
    assert res.returncode != EXIT_OK
    assert res.stdout.strip() == ""


def test_db_age_and_size_print_their_measurement(tmp_path):
    pkg = _build_fake_odoo_with_sql_db(tmp_path, age=200000.0, size=104857600)
    age = _run("db-age-s", "some_db", "--db-host", "h", pythonpath_prepend=pkg)
    assert age.returncode == EXIT_OK, f"stderr={age.stderr!r}"
    assert float(age.stdout.strip()) == 200000.0
    size = _run("db-size-bytes", "some_db", "--db-host", "h", pythonpath_prepend=pkg)
    assert size.returncode == EXIT_OK, f"stderr={size.stderr!r}"
    assert int(size.stdout.strip()) == 104857600


def test_db_age_fails_closed_when_unmeasurable(tmp_path):
    """pg_stat_file needs elevated privilege on many builds. An unmeasurable age
    must fail - a caller that reads it as 0 would reap a database created seconds
    ago."""
    pkg = _build_fake_odoo_with_sql_db(tmp_path, age=None)
    res = _run("db-age-s", "some_db", "--db-host", "h", pythonpath_prepend=pkg)
    assert res.returncode == EXIT_FAILURE
    assert res.stdout.strip() == ""


def test_odoo_root_puts_the_checkout_on_sys_path_before_import(tmp_path):
    """A source checkout is not pip-installed: `import odoo` fails under the venv
    unless the repo root is on sys.path, which is the ONLY reason odoo-bin works.
    Without --odoo-root the import fails (exit 10); with it, the same call
    succeeds - so a source instance stops taking a fallback it never needed."""
    pkg = _build_fake_odoo_with_sql_db(tmp_path, rolcreatedb=True)

    without = _run("can-createdb", "--db-host", "h")  # no PYTHONPATH, no --odoo-root
    assert without.returncode == EXIT_NO_VENV, (
        f"a bare import must fail for a source checkout; got {without.returncode}")

    with_root = _run("can-createdb", "--db-host", "h", "--odoo-root", str(pkg))
    assert with_root.returncode == EXIT_OK, (
        f"--odoo-root must make the import resolve; stderr={with_root.stderr!r}")
    assert with_root.stdout.strip() == "true"


def test_odoo_root_is_accepted_by_drop_too(tmp_path):
    """The drop path is the one that was silently taking the raw fallback on every
    source instance, so it must accept the flag as well."""
    pkg = _build_fake_odoo_with_sql_db(tmp_path)
    res = _run("drop", "some_db", "--db-host", "h", "--odoo-root", str(pkg))
    assert res.returncode == EXIT_OK, f"stderr={res.stderr!r}"


@pytest.mark.parametrize("argv", [
    ("preflight", "--db-host", "h"),
    ("can-createdb", "--db-host", "h"),
    ("list-databases", "--db-host", "h"),
    ("db-age-s", "some_db", "--db-host", "h"),
    ("db-size-bytes", "some_db", "--db-host", "h"),
])
def test_no_subcommand_ever_spawns_a_client_binary(tmp_path, argv):
    """Extends the drop-path guarantee to every new subcommand: this script asks
    Postgres everything through psycopg2 and spawns NO libpq client, ever."""
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    call_log = tmp_path / "pg_calls.log"
    for tool in ("dropdb", "psql", "createdb", "createuser", "pg_isready"):
        shim = bindir / tool
        shim.write_text(f'#!/bin/sh\necho "{tool} $*" >> "{call_log}"\n', encoding="utf-8")
        shim.chmod(0o755)
    pkg = _build_fake_odoo_with_sql_db(tmp_path)

    res = _run(*argv, env_extra={"PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"},
               pythonpath_prepend=pkg)
    assert res.returncode == EXIT_OK, f"stderr={res.stderr!r}"
    assert not call_log.exists(), (
        f"{argv[0]} must never spawn a libpq client; got "
        f"{call_log.read_text(encoding='utf-8')!r}")


# ---------------------------------------------------------------------------
# The drop path must distinguish "never attempted" from "attempted and failed".
#
# Both used to exit 1, so a caller could not tell a connection that never reached
# the database from a DROP DATABASE that genuinely failed - and the two demand
# OPPOSITE handling: the first may be retried over another surface, the second
# must never be, because the database is still in use.
# ---------------------------------------------------------------------------
def _build_fake_odoo_drop_raising(tmp_path, *, exc_class, pgcode, message,
                                  dirname="fake_odoo_drop_raise"):
    """A fake `odoo` whose exp_drop raises a psycopg2-SHAPED exception.

    `exc_class` and `pgcode` are what a caller has to classify on: psycopg2 reports
    a connection or handshake failure as OperationalError with NO SQLSTATE, and
    anything the server itself rejected with one.
    """
    pkg_root = tmp_path / dirname
    pkg = pkg_root / "odoo"
    (pkg / "service").mkdir(parents=True)
    (pkg / "tools").mkdir()
    (pkg / "__init__.py").write_text("from odoo import tools, service\n", encoding="utf-8")
    (pkg / "tools" / "__init__.py").write_text(
        "class _Config(dict):\n"
        "    def parse_config(self, args=None):\n"
        "        pass\n\n"
        "config = _Config()\n", encoding="utf-8")
    (pkg / "service" / "__init__.py").write_text(
        "from odoo.service import db\n", encoding="utf-8")
    (pkg / "service" / "db.py").write_text(
        textwrap.dedent("""\
        class {cls}(Exception):
            pgcode = {code!r}


        def exp_drop(db_name):
            raise {cls}({msg!r})


        def exp_db_exist(db_name):
            return True
        """).format(cls=exc_class, code=pgcode, msg=message), encoding="utf-8")
    return pkg_root


@pytest.mark.parametrize("case,exc_class,pgcode,message,expected", [
    # The server ANSWERED and rejected the credentials: the drop was never issued.
    ("auth rejected by the server", "OperationalError", "28P01",
     "voll uebersetzt", EXIT_AUTH_DENIED),
    # No cluster answered at all: likewise never issued.
    ("cluster absent", "OperationalError", None,
     "could not connect to server: Connection refused", EXIT_UNREACHABLE),
    # A GENUINE drop failure - the database is in use. The drop WAS attempted, so
    # this must keep the catch-all code: a caller that read it as "never
    # attempted" would paper it over with a client-side drop.
    ("database in use", "ObjectInUse", "55006",
     "database is being accessed by other users", EXIT_FAILURE),
    # An exception that is not connection-shaped at all keeps the catch-all code
    # too, even though no credential is resolvable in this environment.
    ("not a connection failure", "RuntimeError", None,
     "filestore removal failed", EXIT_FAILURE),
])
def test_drop_classifies_a_connection_failure_apart_from_a_failed_drop(
        tmp_path, case, exc_class, pgcode, message, expected):
    pkg = _build_fake_odoo_drop_raising(
        tmp_path, exc_class=exc_class, pgcode=pgcode, message=message,
        dirname="fake_odoo_drop_" + case.replace(" ", "_"))
    pgpass = tmp_path / "pgpass-empty"
    pgpass.write_text("", encoding="utf-8")
    res = _run("drop", "some_db", "--db-host", "h", "--db-user", "u",
               env_extra={"PGPASSFILE": str(pgpass), "ODOO_PG_PASSWORD": ""},
               pythonpath_prepend=pkg)
    assert res.returncode == expected, (
        "[{c}] expected exit {e}; got {rc}, stderr={err!r}".format(
            c=case, e=expected, rc=res.returncode, err=res.stderr))
