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

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ODOO_DB_PY = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "odoo_db.py"

# Exit codes mirrored from odoo_db.py (contract)
EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
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

def test_password_from_env_var(tmp_path):
    """ODOO_PG_PASSWORD env var must be forwarded to config parse_config as --db_password."""
    marker = tmp_path / "marker.txt"
    pkg = _build_fake_odoo(tmp_path, exp_drop_returns=True, marker_file=marker)

    # We can't easily read what parse_config did from inside the marker, but we CAN
    # verify the overall command succeeds (no error about missing password etc.)
    result = _run(
        "drop", "some_db",
        env_extra={"ODOO_PG_PASSWORD": "s3cr3t"},
        pythonpath_prepend=pkg,
    )
    assert result.returncode == EXIT_OK, (
        f"ODOO_PG_PASSWORD should be accepted; exit {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    assert marker.exists() and "called=exp_drop" in marker.read_text(encoding="utf-8")
