"""Behavior tests for scripts/lib/odoo_db.py - through-Odoo DB drop/exists.

Tests are run as subprocess (the script is intended to run under a venv python)
with a FAKE ``odoo`` package injected on PYTHONPATH. This lets us verify the
contract without a real Odoo installation:

  1. ``drop foo``  - calls exp_drop('foo') exactly once AND set config['list_db']=True
     before the call; never spawns raw dropdb/psql.
  2. ``drop foo``  - NEVER invokes dropdb/psql even if they are on PATH.
  3. ``exists foo``- prints 'true' when fake exp_db_exist returns True, 'false' otherwise.
  4. Route-unavailable path - when Odoo cannot be driven the exit code is EXIT_NO_VENV (10)
     and stderr names the cause that was observed: the base package missing (naming the
     interpreter and odoo_root), a module or dependency that failed to import (naming it),
     or a checkout whose database API is not recognised.
  5. The database API (legacy service/db.py on 8.0-19.0, modern modules/db.py on 20.0) is
     read from the imported package's source; read-only subcommands need neither.

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


# A sql_db for fakes that never open a connection. The real package always has one and
# _import_odoo binds it for EVERY subcommand, so a fake without it is not a loadable Odoo.
_NO_CONNECTION_SQL_DB = (
    "def db_connect(to, allow_uri=False):\n"
    "    raise RuntimeError('this stub opens no connection')\n"
)

_FAKE_CONFIG = textwrap.dedent("""\
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

    config = _Config()
    """)


def _build_fake_odoo(tmp_path, *, layout="legacy", pkg_name="odoo", exp_drop_returns=True,
                     exp_db_exist_returns=True, exist_returns=True, in_catalog=True,
                     connect_error=None, marker_file=None, dirname="fake_odoo_pkg"):
    """Write a minimal fake Odoo package under tmp_path/<dirname>/.

    ``layout`` picks the database API the fake ships, as the real series do:
      "legacy"  <pkg>/service/db.py with exp_drop / exp_db_exist (8.0 - 19.0; the package
                is ``openerp`` on 8.0 / 9.0, hence ``pkg_name``)
      "modern"  <pkg>/modules/db.py with drop / exist and NO service/ (20.0)
      "both"    the two together
      "none"    neither (a series this script has never seen)
    The fake records:
      - config['list_db'] value AT THE MOMENT a db function is called
        (written to marker_file as a line ``list_db=<value>``)
      - a line ``called=<fn_name>`` for which function fired
      - optionally raises if a legacy return value is an Exception instance

    Modern ``drop`` raises when ``in_catalog`` is False (the real one raises for a database
    that is not there) and ``exist`` answers ``exist_returns`` (False for an absent database
    AND for a cluster it could not reach). ``in_catalog`` is also what the maintenance
    database's pg_database says, and ``connect_error`` makes every connection fail with that
    message (an unreachable cluster).
    """
    pkg_dir = tmp_path / dirname / pkg_name
    tools_dir = pkg_dir / "tools"
    tools_dir.mkdir(parents=True)
    marker_str = repr(str(marker_file)) if marker_file else "None"

    # The package __init__ imports only tools, so a submodule the layout does not ship is
    # never reached through it - the script must bind what it needs itself.
    (pkg_dir / "__init__.py").write_text(
        "from {pkg} import tools\n".format(pkg=pkg_name), encoding="utf-8")
    (tools_dir / "__init__.py").write_text(_FAKE_CONFIG, encoding="utf-8")
    (tools_dir / "config.py").write_text("# placeholder\n", encoding="utf-8")

    # sql_db answers the catalog question the modern drop asks.
    (pkg_dir / "sql_db.py").write_text(
        textwrap.dedent("""\
        _ERROR = {err!r}
        _IN_CATALOG = {in_catalog!r}


        class _Cursor(object):
            def execute(self, sql, params=None):
                low = " ".join(sql.split()).lower()
                if "from pg_database where datname" in low:
                    self._rows = [(1,)] if _IN_CATALOG else []
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
            if _ERROR:
                raise RuntimeError(_ERROR)
            return _Connection()
        """).format(err=connect_error or "", in_catalog=in_catalog),
        encoding="utf-8")

    marker_helpers = textwrap.dedent(f"""\
        from {pkg_name}.tools import config

        _MARKER_FILE = {marker_str}

        def _write_marker(fn_name):
            if _MARKER_FILE is None:
                return
            with open(_MARKER_FILE, 'a', encoding='utf-8') as fh:
                fh.write(f'list_db={{config.get("list_db", "NOT_SET")}}\\n')
                fh.write(f'called={{fn_name}}\\n')

        """)

    if layout in ("legacy", "both"):
        (pkg_dir / "service").mkdir()
        (pkg_dir / "service" / "__init__.py").write_text("", encoding="utf-8")
        (pkg_dir / "service" / "db.py").write_text(
            marker_helpers + textwrap.dedent(f"""\
            def exp_drop(db_name):
                _write_marker('exp_drop')
                ret = {exp_drop_returns!r}
                if isinstance(ret, BaseException):
                    raise ret
                return ret

            def exp_db_exist(db_name):
                _write_marker('exp_db_exist')
                ret = {exp_db_exist_returns!r}
                if isinstance(ret, BaseException):
                    raise ret
                return ret
            """),
            encoding="utf-8",
        )
    if layout in ("modern", "both"):
        (pkg_dir / "modules").mkdir()
        (pkg_dir / "modules" / "__init__.py").write_text("", encoding="utf-8")
        (pkg_dir / "modules" / "db.py").write_text(
            marker_helpers + textwrap.dedent(f"""\
            def drop(db_name):
                _write_marker('drop')
                if not {in_catalog!r}:
                    raise RuntimeError('database %r does not exist' % db_name)

            def exist(db_name):
                _write_marker('exist')
                return {exist_returns!r}
            """),
            encoding="utf-8",
        )

    return tmp_path / dirname


def _calls(marker):
    """The ``called=<fn>`` lines a fake wrote, in order ([] when it was never called)."""
    if not marker.exists():
        return []
    return [line.split("=", 1)[1] for line in marker.read_text(encoding="utf-8").splitlines()
            if line.startswith("called=")]


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

def test_missing_base_package_exits_10_and_names_the_interpreter_and_odoo_root(tmp_path):
    """When the base package is not importable the exit is 10 and stderr names what a
    reader can act on: the interpreter that failed and the declared (or undeclared)
    odoo_root - not a guess about a venv."""
    # PYTHONPATH pointing to an empty dir ensures neither odoo nor openerp is importable.
    empty = tmp_path / "empty_pythonpath"
    empty.mkdir()

    undeclared = _run("drop", "some_db", pythonpath_prepend=empty)
    assert undeclared.returncode == EXIT_NO_VENV, (
        f"expected exit {EXIT_NO_VENV} (route unavailable); got {undeclared.returncode}; "
        f"stderr={undeclared.stderr!r}"
    )
    assert f"odoo not importable by {sys.executable} (odoo_root=undeclared)" in undeclared.stderr, (
        f"stderr must name the interpreter and the undeclared odoo_root; "
        f"stderr={undeclared.stderr!r}")

    declared = _run("drop", "some_db", "--odoo-root", str(tmp_path / "no_such_checkout"),
                    pythonpath_prepend=empty)
    assert declared.returncode == EXIT_NO_VENV
    assert f"odoo_root={tmp_path / 'no_such_checkout'} (not a directory)" in declared.stderr, (
        f"a declared odoo_root that is not a directory must be named as such; "
        f"stderr={declared.stderr!r}")


def test_a_dependency_that_fails_to_import_is_named_and_odoo_root_is_not_blamed(tmp_path):
    """The package IS found, a module under it fails on a missing dependency: stderr says
    where Odoo was imported from and WHICH module failed. Telling this reader to check the
    venv or declare odoo_root would send them after a fault they do not have."""
    pkg = _build_fake_odoo(tmp_path, layout="legacy")
    (pkg / "odoo" / "__init__.py").write_text("", encoding="utf-8")  # 19.0: binds nothing
    (pkg / "odoo" / "tools" / "__init__.py").write_text(
        "import psycopg2_missing_dependency\n", encoding="utf-8")

    res = _run("drop", "some_db", "--odoo-root", str(pkg), pythonpath_prepend=pkg)
    assert res.returncode == EXIT_NO_VENV, f"stderr={res.stderr!r}"
    assert f"odoo imported from {pkg / 'odoo'}, but psycopg2_missing_dependency failed" in res.stderr, (
        f"stderr must name the package location and the failing module; stderr={res.stderr!r}")
    assert "odoo_root" not in res.stderr and "no venv" not in res.stderr, (
        f"a found package must not be diagnosed as a missing venv or odoo_root; "
        f"stderr={res.stderr!r}")


def test_an_odoo_namespace_with_no_core_in_it_is_reported_as_a_missing_checkout(tmp_path):
    """An addons-only install leaves a bare `odoo` namespace on the import path: the name
    resolves, the core does not. That is a checkout that is missing - odoo_root is the
    fact to look at - not a broken dependency."""
    portion = tmp_path / "addons_only" / "odoo" / "addons" / "some_addon"
    portion.mkdir(parents=True)
    res = _run("drop", "some_db", pythonpath_prepend=tmp_path / "addons_only")
    assert res.returncode == EXIT_NO_VENV, f"stderr={res.stderr!r}"
    assert f"odoo not importable by {sys.executable} (odoo_root=undeclared)" in res.stderr, (
        res.stderr)
    assert "holds no odoo.tools" in res.stderr, res.stderr


def test_a_dependency_of_the_package_init_is_named_not_reported_as_a_missing_package(tmp_path):
    """Before 19.0 `import odoo` itself runs the package __init__, which imports its
    dependencies: a missing one must not read as "odoo not importable"."""
    pkg = _build_fake_odoo(tmp_path, layout="legacy")
    (pkg / "odoo" / "__init__.py").write_text("import psycopg2_missing_dependency\n",
                                              encoding="utf-8")
    res = _run("exists", "some_db", pythonpath_prepend=pkg)
    assert res.returncode == EXIT_NO_VENV, f"stderr={res.stderr!r}"
    assert "psycopg2_missing_dependency failed" in res.stderr, res.stderr
    assert "not importable" not in res.stderr, (
        f"the package was found; it must not be reported as missing: {res.stderr!r}")


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
    (odoo_dir / "sql_db.py").write_text(_NO_CONNECTION_SQL_DB, encoding="utf-8")

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
    (odoo_dir / "sql_db.py").write_text(_NO_CONNECTION_SQL_DB, encoding="utf-8")
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


def test_import_odoo_binds_tools_and_sql_db_and_nothing_a_series_may_lack(tmp_path, monkeypatch):
    """_import_odoo() must bind .tools and .sql_db even when a bare import does NOT
    (Odoo 19.0 behaviour: the base package's __init__ no longer re-exports submodules
    transitively - regression guard for #154), and it must NOT demand ``.service.db``:
    Odoo 20.0 has no such module, and every read-only subcommand needs only the two it
    binds (issue #272).

    The fake ``odoo`` is an in-memory package whose bare import binds NOTHING; only
    ``.tools`` and ``.sql_db`` live on disk (reachable via ``__path__``) - there is no
    ``service/`` at all, exactly like a 20.0 checkout.
    """
    pkg_dir = tmp_path / "fake_odoo_pkg_root"
    (pkg_dir / "tools").mkdir(parents=True)
    (pkg_dir / "tools" / "__init__.py").write_text(
        "class _Config(dict):\n    pass\n\nconfig = _Config()\n", encoding="utf-8")
    (pkg_dir / "sql_db.py").write_text(_NO_CONNECTION_SQL_DB, encoding="utf-8")

    fake_odoo = types.ModuleType("odoo")
    fake_odoo.__path__ = [str(pkg_dir)]
    monkeypatch.setitem(sys.modules, "odoo", fake_odoo)

    # Confirm the fixture's own premise: bare import leaves the submodules unbound.
    assert not hasattr(fake_odoo, "tools")
    assert not hasattr(fake_odoo, "sql_db")

    try:
        spec = importlib.util.spec_from_file_location("odoo_db_under_test", ODOO_DB_PY)
        odoo_db_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(odoo_db_mod)

        result = odoo_db_mod._import_odoo()

        assert hasattr(result, "tools") and hasattr(result.tools, "config"), (
            "_import_odoo() must bind .tools (with .config) even when a bare import does not")
        assert hasattr(result, "sql_db"), (
            "_import_odoo() must bind .sql_db even when a bare import does not")
        assert not hasattr(result, "service") and "odoo.service.db" not in sys.modules, (
            "_import_odoo() must not require the legacy database API module: a series "
            "without service/db.py must still load")
    finally:
        # Self-cleaning: importlib.import_module() adds the submodules to sys.modules as a
        # side effect of the fresh load; monkeypatch only reverts the 'odoo' key set above.
        for name in ("odoo.tools", "odoo.sql_db"):
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
                                 pkg_name="odoo", dirname="fake_odoo_sqldb",
                                 layout="legacy"):
    """A fake Odoo package that also exposes sql_db.db_connect.

    `pkg_name` is a parameter because v8/v9 ship the SAME api under `openerp`:
    the script resolves the namespace and imports `<pkg>.sql_db` through it, so
    the openerp case must be exercised, not assumed. `layout` is "legacy"
    (service/db.py, 8.0-19.0), "modern" (modules/db.py and NO service/, 20.0) or "none".
    """
    pkg_root = tmp_path / dirname
    pkg_dir = pkg_root / pkg_name
    (pkg_dir / "tools").mkdir(parents=True)

    (pkg_dir / "__init__.py").write_text(
        f"from {pkg_name} import tools\n", encoding="utf-8")
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
    if layout == "legacy":
        (pkg_dir / "service").mkdir()
        (pkg_dir / "service" / "__init__.py").write_text("", encoding="utf-8")
        (pkg_dir / "service" / "db.py").write_text(
            "def exp_drop(db_name):\n    return True\n\n"
            "def exp_db_exist(db_name):\n    return True\n", encoding="utf-8")
    elif layout == "modern":
        (pkg_dir / "modules").mkdir()
        (pkg_dir / "modules" / "__init__.py").write_text("", encoding="utf-8")
        (pkg_dir / "modules" / "db.py").write_text(
            "def drop(db_name):\n    return None\n\n"
            "def exist(db_name):\n    return True\n", encoding="utf-8")

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
                elif "from pg_database where datname" in low:
                    self._rows = [(1,)] if params[0] in _DATABASES else []
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
                                  dirname="fake_odoo_drop_raise", layout="legacy"):
    """A fake `odoo` whose drop raises a psycopg2-SHAPED exception (``exp_drop`` on the
    legacy layout, ``drop`` on the modern one - which reports the database present).

    `exc_class` and `pgcode` are what a caller has to classify on: psycopg2 reports
    a connection or handshake failure as OperationalError with NO SQLSTATE, and
    anything the server itself rejected with one.
    """
    pkg_root = tmp_path / dirname
    pkg = pkg_root / "odoo"
    (pkg / "tools").mkdir(parents=True)
    (pkg / "__init__.py").write_text("from odoo import tools\n", encoding="utf-8")
    (pkg / "tools" / "__init__.py").write_text(
        "class _Config(dict):\n"
        "    def parse_config(self, args=None):\n"
        "        pass\n\n"
        "config = _Config()\n", encoding="utf-8")
    (pkg / "sql_db.py").write_text(_NO_CONNECTION_SQL_DB, encoding="utf-8")
    exception = textwrap.dedent("""\
        class {cls}(Exception):
            pgcode = {code!r}


        """).format(cls=exc_class, code=pgcode)
    if layout == "legacy":
        (pkg / "service").mkdir()
        (pkg / "service" / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "service" / "db.py").write_text(
            exception + textwrap.dedent("""\
            def exp_drop(db_name):
                raise {cls}({msg!r})


            def exp_db_exist(db_name):
                return True
            """).format(cls=exc_class, msg=message), encoding="utf-8")
    else:
        (pkg / "modules").mkdir()
        (pkg / "modules" / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "modules" / "db.py").write_text(
            exception + textwrap.dedent("""\
            def drop(db_name):
                raise {cls}({msg!r})


            def exist(db_name):
                return True
            """).format(cls=exc_class, msg=message), encoding="utf-8")
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
@pytest.mark.parametrize("layout", ["legacy", "modern"])
def test_drop_classifies_a_connection_failure_apart_from_a_failed_drop(
        tmp_path, layout, case, exc_class, pgcode, message, expected):
    pkg = _build_fake_odoo_drop_raising(
        tmp_path, exc_class=exc_class, pgcode=pgcode, message=message, layout=layout,
        dirname="fake_odoo_drop_" + case.replace(" ", "_"))
    pgpass = tmp_path / "pgpass-empty"
    pgpass.write_text("", encoding="utf-8")
    res = _run("drop", "some_db", "--db-host", "h", "--db-user", "u",
               env_extra={"PGPASSFILE": str(pgpass), "ODOO_PG_PASSWORD": ""},
               pythonpath_prepend=pkg)
    assert res.returncode == expected, (
        "[{c}] expected exit {e}; got {rc}, stderr={err!r}".format(
            c=case, e=expected, rc=res.returncode, err=res.stderr))


# ---------------------------------------------------------------------------
# The database API is chosen from the SOURCE of the package the interpreter imported
# (issue #272). Odoo 20.0 has no service/db.py: its drop / exist are module-level
# functions in modules/db.py, and `drop` raises for a database that is not there.
# ---------------------------------------------------------------------------

def _load_odoo_db():
    spec = importlib.util.spec_from_file_location("odoo_db_probe_under_test", ODOO_DB_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("layout", ["modern", "none"])
@pytest.mark.parametrize("argv,stdout", [
    (("preflight", "--db-host", "h"), "DB_AUTH=ok"),
    (("can-createdb", "--db-host", "h"), "true"),
    (("list-databases", "--db-host", "h"), "a_db"),
    (("db-age-s", "some_db", "--db-host", "h"), "1234.5"),
    (("db-size-bytes", "some_db", "--db-host", "h"), "4096"),
])
def test_read_only_subcommands_need_no_database_api_module(tmp_path, layout, argv, stdout):
    """Every read-only question needs only odoo.tools and odoo.sql_db, so it must be
    answered on a checkout that has no service/db.py - and even on one whose database
    API this script does not recognise. Before #272 all of these exited 10 on 20.0."""
    pkg = _build_fake_odoo_with_sql_db(tmp_path, layout=layout)
    res = _run(*argv, pythonpath_prepend=pkg)
    assert res.returncode == EXIT_OK, f"stderr={res.stderr!r}"
    assert stdout in res.stdout, f"stdout={res.stdout!r}"


def test_modern_drop_of_an_existing_database_is_performed_once(tmp_path):
    marker = tmp_path / "marker.txt"
    pkg = _build_fake_odoo(tmp_path, layout="modern", marker_file=marker,
                           exist_returns=True, in_catalog=True)
    res = _run("drop", "live_db", "--db-host", "pghost", pythonpath_prepend=pkg)
    assert res.returncode == EXIT_OK, f"stderr={res.stderr!r}"
    assert "odoo_db: drop 'live_db' on pghost:libpq-default -> performed" in res.stderr
    assert _calls(marker).count("drop") == 1, f"drop must run exactly once: {_calls(marker)}"
    lines = marker.read_text(encoding="utf-8").splitlines()
    assert all(line == "list_db=True" for line in lines if line.startswith("list_db=")), (
        f"config['list_db'] must be True whenever the db API is called; marker={lines}")


def test_modern_drop_of_an_absent_database_is_idempotent_and_never_calls_drop(tmp_path):
    """The real `drop` raises for a missing database, so reaching it would turn the
    idempotent verb into a failure the allocator then retains the lease for."""
    marker = tmp_path / "marker.txt"
    pkg = _build_fake_odoo(tmp_path, layout="modern", marker_file=marker,
                           exist_returns=False, in_catalog=False)
    res = _run("drop", "gone_db", pythonpath_prepend=pkg)
    assert res.returncode == EXIT_OK, f"stderr={res.stderr!r}"
    assert "-> already-absent" in res.stderr, res.stderr
    assert "drop" not in _calls(marker), f"drop() must not be called: {_calls(marker)}"


def test_modern_drop_proceeds_for_a_database_that_exists_but_refuses_connections(tmp_path):
    """`exist` answers False for any OperationalError, a database nobody may connect to
    included. The catalog still lists it, so it is dropped rather than called absent."""
    marker = tmp_path / "marker.txt"
    pkg = _build_fake_odoo(tmp_path, layout="modern", marker_file=marker,
                           exist_returns=False, in_catalog=True)
    res = _run("drop", "locked_db", pythonpath_prepend=pkg)
    assert res.returncode == EXIT_OK, f"stderr={res.stderr!r}"
    assert "-> performed" in res.stderr, res.stderr
    assert _calls(marker).count("drop") == 1


@pytest.mark.parametrize("message,expected", [
    ("could not connect to server: Connection refused", EXIT_UNREACHABLE),
    ("FATAL: password authentication failed for user", EXIT_AUTH_DENIED),
])
def test_modern_drop_on_a_cluster_that_refuses_us_is_not_reported_as_absent(
        tmp_path, message, expected):
    """`exist` swallows the connection failure and says False. Reporting that as
    "already absent" (exit 0) would let a caller release the lease over a database that
    is still there. The refusal must surface as the classified exit, with nothing dropped."""
    marker = tmp_path / "marker.txt"
    pkg = _build_fake_odoo(tmp_path, layout="modern", marker_file=marker,
                           exist_returns=False, connect_error=message)
    res = _run("drop", "some_db", "--db-host", "h", "--db-user", "u", pythonpath_prepend=pkg)
    assert res.returncode == expected, f"stderr={res.stderr!r}"
    assert "already-absent" not in res.stderr and "performed" not in res.stderr
    assert "drop" not in _calls(marker)


@pytest.mark.parametrize("present", [True, False])
def test_modern_exists_prints_what_exist_answers(tmp_path, present):
    marker = tmp_path / "marker.txt"
    pkg = _build_fake_odoo(tmp_path, layout="modern", marker_file=marker,
                           exist_returns=present)
    res = _run("exists", "some_db", pythonpath_prepend=pkg)
    assert res.returncode == EXIT_OK, f"stderr={res.stderr!r}"
    assert res.stdout.strip() == ("true" if present else "false")
    assert _calls(marker) == ["exist"]


def test_modern_layout_works_as_a_namespace_package(tmp_path):
    """Odoo 19.0+ ships no odoo/__init__.py: the package is a namespace package, whose
    __path__ is not a list. The API must still be found and driven."""
    marker = tmp_path / "marker.txt"
    pkg = _build_fake_odoo(tmp_path, layout="modern", marker_file=marker)
    (pkg / "odoo" / "__init__.py").unlink()
    res = _run("drop", "live_db", pythonpath_prepend=pkg)
    assert res.returncode == EXIT_OK, f"stderr={res.stderr!r}"
    assert "-> performed" in res.stderr
    assert _calls(marker).count("drop") == 1


def test_legacy_layout_under_the_openerp_namespace_still_drops_and_answers(tmp_path):
    """8.0 / 9.0: package `openerp`, service/db.py with exp_drop / exp_db_exist."""
    marker = tmp_path / "marker.txt"
    pkg = _build_fake_odoo(tmp_path, layout="legacy", pkg_name="openerp",
                           marker_file=marker, dirname="fake_openerp")
    dropped = _run("drop", "old_db", pythonpath_prepend=pkg)
    assert dropped.returncode == EXIT_OK, f"stderr={dropped.stderr!r}"
    assert "-> performed" in dropped.stderr
    exists = _run("exists", "old_db", pythonpath_prepend=pkg)
    assert exists.returncode == EXIT_OK and exists.stdout.strip() == "true"
    assert _calls(marker) == ["exp_drop", "exp_db_exist"]


def test_a_checkout_shipping_both_apis_is_driven_through_the_modern_one(tmp_path):
    marker = tmp_path / "marker.txt"
    pkg = _build_fake_odoo(tmp_path, layout="both", marker_file=marker)
    res = _run("drop", "live_db", pythonpath_prepend=pkg)
    assert res.returncode == EXIT_OK, f"stderr={res.stderr!r}"
    assert _calls(marker) == ["exist", "drop"], (
        f"modern wins when both are defined; calls={_calls(marker)}")


_NOT_A_DB_API = {
    "no database module at all": {},
    "legacy module missing one of the two functions": {
        "service/db.py": "def exp_drop(db_name):\n    return True\n"},
    "modern module missing one of the two functions": {
        "modules/db.py": "def drop(db_name):\n    return None\n"},
    "functions only mentioned in comments": {
        "modules/db.py": "# def drop(db_name):\n# def exist(db_name):\nx = 1\n"},
    "functions that are methods of a class, not module-level": {
        "modules/db.py": "class A:\n    def drop(self, n):\n        pass\n"
                         "    def exist(self, n):\n        pass\n"},
}


@pytest.mark.parametrize("case", sorted(_NOT_A_DB_API))
@pytest.mark.parametrize("verb", ["drop", "exists"])
def test_a_checkout_with_no_recognisable_database_api_is_refused_not_guessed(
        tmp_path, case, verb):
    pkg = _build_fake_odoo(tmp_path, layout="none")
    for relpath, text in _NOT_A_DB_API[case].items():
        target = pkg / "odoo" / relpath
        target.parent.mkdir(exist_ok=True)
        (target.parent / "__init__.py").write_text("", encoding="utf-8")
        target.write_text(text, encoding="utf-8")
    res = _run(verb, "some_db", pythonpath_prepend=pkg)
    assert res.returncode == EXIT_NO_VENV, f"[{case}] stderr={res.stderr!r}"
    assert "ODOO_SOURCE_FACT_UNKNOWN" in res.stderr, res.stderr
    assert res.stdout.strip() == "", "no answer may be printed for an unrecognised API"
    assert "performed" not in res.stderr and "already-absent" not in res.stderr


@pytest.mark.parametrize("verb", ["drop", "exists"])
def test_a_database_api_module_that_fails_to_import_names_the_failing_dependency(
        tmp_path, verb):
    pkg = _build_fake_odoo(tmp_path, layout="modern")
    (pkg / "odoo" / "modules" / "db.py").write_text(
        "import a_dependency_nobody_installed\n\n"
        "def drop(db_name):\n    pass\n\ndef exist(db_name):\n    return True\n",
        encoding="utf-8")
    res = _run(verb, "some_db", pythonpath_prepend=pkg)
    assert res.returncode == EXIT_NO_VENV, f"stderr={res.stderr!r}"
    assert "a_dependency_nobody_installed failed" in res.stderr, res.stderr
    assert "odoo_root" not in res.stderr


def test_preflight_reports_the_real_reason_and_a_remedy_that_fits_it(tmp_path):
    """A refusal must not blame a cause that was not observed. Package missing -> the
    remedy is to declare it; package found but a dependency broken -> the remedy is to
    repair that, and `odoo_root` is not mentioned at all."""
    empty = tmp_path / "empty_pythonpath"
    empty.mkdir()
    missing = _run("preflight", "--db-host", "h", pythonpath_prepend=empty)
    assert missing.returncode == EXIT_NO_VENV
    assert "DB_AUTH=unknown" in missing.stdout
    assert f"DB_AUTH_WHY=odoo not importable by {sys.executable} (odoo_root=undeclared)" in (
        missing.stdout)
    assert "/odoo-ai-agents:odoo-setup" in missing.stderr
    assert "not importable by" in missing.stderr

    pkg = _build_fake_odoo_with_sql_db(tmp_path, layout="modern")
    (pkg / "odoo" / "sql_db.py").write_text("import a_dependency_nobody_installed\n",
                                            encoding="utf-8")
    broken = _run("preflight", "--db-host", "h", pythonpath_prepend=pkg)
    assert broken.returncode == EXIT_NO_VENV
    assert "a_dependency_nobody_installed failed" in broken.stdout
    assert "odoo_root" not in broken.stdout + broken.stderr, (
        f"a found package must not be blamed on odoo_root; got {broken.stdout + broken.stderr!r}")
    assert "odoo-setup" not in broken.stderr, "setup cannot repair a broken dependency"
    assert "missing or incompatible dependency" in broken.stderr


# --- real checkouts (skipped when absent) ------------------------------------------

CHECKOUTS = Path(os.environ.get("ODOO_SOURCE_CHECKOUTS") or (Path.home() / "git"))

# Surveyed by reading each series' own source: service/db.py defines exp_drop and
# exp_db_exist on 8.0 - 19.0 (19.0 also has modules/db.py, but without drop / exist);
# 20.0 has no service/db.py and defines drop / exist in modules/db.py.
REAL_SERIES_API = dict({s: "legacy" for s in (
    "8.0", "9.0", "10.0", "11.0", "12.0", "13.0", "14.0", "15.0", "16.0", "17.0", "18.0",
    "19.0")}, **{"20.0": "modern"})


@pytest.mark.parametrize("series", sorted(REAL_SERIES_API, key=float))
def test_real_checkout_database_api_is_read_from_its_source(series):
    root = CHECKOUTS / ("odoo_%s" % series)
    pkg = next((p for p in ("odoo", "openerp") if (root / p / "modules").is_dir()), None)
    if pkg is None:
        pytest.skip("no Odoo %s checkout at %s" % (series, root))
    base = types.ModuleType(pkg)
    base.__path__ = [str(root / pkg)]
    kind, _relpath = _load_odoo_db()._detect_db_api(base)
    assert kind == REAL_SERIES_API[series], (
        f"{series}: expected the {REAL_SERIES_API[series]} database API, read {kind}")


def test_every_directory_of_a_namespace_package_is_searched(tmp_path):
    """A namespace package's __path__ can name several directories; the module is
    wherever one of them holds it."""
    (tmp_path / "first").mkdir()
    (tmp_path / "second" / "modules").mkdir(parents=True)
    (tmp_path / "second" / "modules" / "db.py").write_text(
        "def drop(n):\n    pass\n\ndef exist(n):\n    return True\n", encoding="utf-8")
    base = types.ModuleType("odoo")
    base.__path__ = [str(tmp_path / "first"), str(tmp_path / "second")]
    assert _load_odoo_db()._detect_db_api(base)[0] == "modern"
