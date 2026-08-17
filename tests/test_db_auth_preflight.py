"""Behavior tests for the DB-authentication preflight - the gate that must fire
BEFORE any odoo-bin process is launched.

The rule these protect: no build verb (init / update / test / spin-up) may start
until something has PROVEN that Odoo itself can authenticate to the cluster.
Odoo's CLI opens a connection to the maintenance database for EVERY `-d <name>`
run - before any registry and before any module loads - so authentication is a
precondition of every build verb, not of a create alone. When it fails the
process dies mid-build with a raw traceback, having opened a log and left a
half-built database behind.

Three states stay DISTINCT at every layer and none of them is ever reported as a
fourth: `ok`, `denied`, `unreachable`, `unknown`. `unknown` is never read as
`ok`, and a refusal names `/odoo-ai-agents:odoo-setup` so the reader has a next
step rather than a verdict.

Hermetic by construction: every fixture REPLACES PATH with a directory it built,
points PGPASSFILE at a file under tmp_path, and constructs the interpreter,
`docker`, `psql` and `odoo-bin` it depends on. No test asserts that a binary is
ABSENT from the host (a CI image that ships a Postgres client would then run a
different test under the same name), and no test inherits the developer's real
~/.pgpass.
"""

import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import farm_path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
LIB = PLUGIN / "scripts" / "lib"
ODOO_DB_PY = LIB / "odoo_db.py"
STEP50 = PLUGIN / "scripts" / "setup-steps" / "50-instance-spinup.sh"
STEP55 = PLUGIN / "scripts" / "setup-steps" / "55-instance-ops.sh"

# Exit codes mirrored from odoo_db.py's contract.
EXIT_OK = 0
EXIT_UNKNOWN = 1
EXIT_AUTH_DENIED = 8
EXIT_UNREACHABLE = 9
EXIT_NO_VENV = 10

BUILD_VERBS = ("init", "update", "test")

requires_bash = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash not available"
)

# A value that can only have come from the fixture, so its appearance anywhere in
# the output is proof of a leak rather than a coincidence.
SENTINEL = "Zq7-preflight-sentinel-Xk2"

# Every binary that can hand this plugin a PostgreSQL client surface, plus the
# container runtime that can lend it one. A probe rung is selected by
# `command -v <one of these>`, so their PRESENCE is what decides which code path
# runs - which is exactly why a test must construct their absence rather than
# inherit it.
_PG_CLIENT_BINS = ("pg_isready", "psql", "createdb", "dropdb", "pg_dump",
                   "pg_restore", "docker")


# `_hermetic_path` used to build its own per-test symlink farm here. The farm is
# a pure function of (ambient PATH, drop-set) - a session-level constant - so it
# now comes from the shared, session-scoped `path_farm` fixture in conftest.py
# (one farm per distinct drop-set for the whole run, not one per test). The
# builder functions below (`_step55_env` etc.) are plain functions, not fixture
# consumers, so they receive the farm through `_bind_path_farm`'s bridge.
_PATH_FARM: dict = {}


@pytest.fixture(autouse=True)
def _bind_path_farm(path_farm):
    """Bridge the session-scoped `path_farm` factory into this file's builders."""
    _PATH_FARM["get"] = path_farm


# --------------------------------------------------------------------------- #
# Fixtures - a fake Odoo whose sql_db raises exactly what we want to classify
# --------------------------------------------------------------------------- #
def _fake_odoo_raising(tmp_path, *, message, pgcode=None, dirname="fake_odoo_auth",
                       exc_class="OperationalError", record_env_to=None):
    """A fake `odoo` package whose db_connect raises a psycopg2-shaped error.

    The exception carries a `pgcode` attribute exactly as psycopg2's does, so the
    classifier's rules can be exercised with no Postgres and no psycopg2 installed.

    `exc_class` names the exception's CLASS, because the classifier reads the MRO:
    psycopg2 delivers a connection or handshake failure as OperationalError, and a
    failure the server reported about a STATEMENT as something else with a SQLSTATE.
    MEASURED with psycopg2 2.9.12 against a live cluster: a connect-time failure -
    including a genuine 28P01 "password authentication failed" - arrives as
    OperationalError with `pgcode is None` and `diag.sqlstate is None`, so a
    SQLSTATE-BEARING exception can only be a statement-level failure.

    `record_env_to` makes db_connect write the locale environment it was called
    with to that path before raising, so "the locale was pinned BEFORE the
    connection was opened" is observable rather than asserted about source text.
    """
    pkg_root = tmp_path / dirname
    pkg = pkg_root / "odoo"
    (pkg / "service").mkdir(parents=True)
    (pkg / "tools").mkdir()
    (pkg / "__init__.py").write_text("from odoo import tools, service\n", encoding="utf-8")
    (pkg / "tools" / "__init__.py").write_text(
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
    (pkg / "service" / "__init__.py").write_text(
        "from odoo.service import db\n", encoding="utf-8")
    (pkg / "service" / "db.py").write_text(
        "def exp_drop(db_name):\n    return True\n\n"
        "def exp_db_exist(db_name):\n    return True\n", encoding="utf-8")
    (pkg / "sql_db.py").write_text(
        textwrap.dedent("""\
        import os


        class {cls}(Exception):
            pgcode = {pgcode!r}


        def db_connect(to, allow_uri=False):
            record = {record!r}
            if record:
                with open(record, "w") as fh:
                    for name in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
                        fh.write("%s=%s\\n" % (name, os.environ.get(name, "<unset>")))
            raise {cls}({message!r})
        """).format(cls=exc_class, pgcode=pgcode, message=message,
                    record=str(record_env_to) if record_env_to else ""),
        encoding="utf-8")
    return pkg_root


def _fake_odoo_ok(tmp_path, dirname="fake_odoo_ok"):
    """A fake `odoo` whose db_connect answers `SELECT 1` successfully."""
    pkg_root = tmp_path / dirname
    pkg = pkg_root / "odoo"
    (pkg / "service").mkdir(parents=True)
    (pkg / "tools").mkdir()
    (pkg / "__init__.py").write_text("from odoo import tools, service\n", encoding="utf-8")
    (pkg / "tools" / "__init__.py").write_text(
        textwrap.dedent("""\
        class _Config(dict):
            def parse_config(self, args=None):
                pass

        config = _Config()
        """), encoding="utf-8")
    (pkg / "service" / "__init__.py").write_text(
        "from odoo.service import db\n", encoding="utf-8")
    (pkg / "service" / "db.py").write_text(
        "def exp_drop(db_name):\n    return True\n\n"
        "def exp_db_exist(db_name):\n    return True\n", encoding="utf-8")
    (pkg / "sql_db.py").write_text(
        textwrap.dedent("""\
        class _Cursor(object):
            def execute(self, sql, params=None):
                self._rows = [(1,)]

            def fetchall(self):
                return self._rows

            def close(self):
                pass


        class _Connection(object):
            def cursor(self, *args, **kwargs):
                return _Cursor()


        def db_connect(to, allow_uri=False):
            return _Connection()
        """), encoding="utf-8")
    return pkg_root


def _preflight(pkg, tmp_path, *args, env_extra=None, pgpass_lines=None):
    """Run `odoo_db.py preflight` with a CONSTRUCTED credential environment.

    PGPASSFILE always points inside tmp_path, so the developer's own ~/.pgpass can
    never decide the verdict, and ODOO_PG_PASSWORD is cleared unless a test sets
    it deliberately.
    """
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("ODOO_PG_PASSWORD", None)
    env["PYTHONPATH"] = str(pkg)
    pgpass = tmp_path / "pgpass"
    pgpass.write_text("" if pgpass_lines is None else "\n".join(pgpass_lines) + "\n",
                      encoding="utf-8")
    pgpass.chmod(0o600)
    env["PGPASSFILE"] = str(pgpass)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(ODOO_DB_PY), "preflight", *args],
        capture_output=True, text=True, env=env, timeout=60,
    )


def _keys(stdout):
    out = {}
    for line in stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


# --------------------------------------------------------------------------- #
# The primitive - classification
# --------------------------------------------------------------------------- #
def test_preflight_classifies_a_server_side_auth_rejection_as_denied(tmp_path):
    """A SQLSTATE in the 28 class is the server itself rejecting the credentials.

    Classifying on the code rather than on the message is what makes the verdict
    hold on a cluster whose messages are localised - the reason it is rule one.
    """
    pkg = _fake_odoo_raising(tmp_path, message="voll uebersetzt, kein Signalwort",
                             pgcode="28P01")
    res = _preflight(pkg, tmp_path, "--db-host", "h", "--db-user", "u",
                     env_extra={"ODOO_PG_PASSWORD": SENTINEL})
    assert res.returncode == EXIT_AUTH_DENIED, (
        "a 28-class SQLSTATE must exit {code}; got {rc}, stderr={err!r}".format(
            code=EXIT_AUTH_DENIED, rc=res.returncode, err=res.stderr))
    assert _keys(res.stdout).get("DB_AUTH") == "denied", res.stdout


def test_preflight_classifies_a_missing_credential_as_denied_without_reading_the_message(
        tmp_path):
    """No resolvable credential is a fact the preflight computes for ITSELF.

    `fe_sendauth: no password supplied` carries no SQLSTATE, so a classifier that
    only reads codes misses it and one that only reads messages breaks under a
    translated libpq. Asserting on an UNRECOGNISABLE message is what proves the
    verdict came from the credential question and not from a substring.
    """
    pkg = _fake_odoo_raising(tmp_path, message="wholly unrecognisable failure text")
    res = _preflight(pkg, tmp_path, "--db-host", "h", "--db-user", "u",
                     pgpass_lines=["other-host:5432:*:someone:irrelevant"])
    assert res.returncode == EXIT_AUTH_DENIED, (
        "an unresolvable credential must exit {code}; got {rc}, stderr={err!r}".format(
            code=EXIT_AUTH_DENIED, rc=res.returncode, err=res.stderr))
    assert _keys(res.stdout).get("DB_AUTH") == "denied", res.stdout


def test_preflight_classifies_a_refused_connection_as_unreachable_not_denied(tmp_path):
    """A cluster that never answered is NOT a credential problem.

    Collapsing the two sends the reader to fix a password when the remedy is to
    start the cluster, which is the defect family this whole gate exists to end.
    """
    pkg = _fake_odoo_raising(
        tmp_path, message="could not connect to server: Connection refused")
    res = _preflight(pkg, tmp_path, "--db-host", "h", "--db-user", "u",
                     env_extra={"ODOO_PG_PASSWORD": SENTINEL})
    assert res.returncode == EXIT_UNREACHABLE, (
        "a refused connection must exit {code}; got {rc}, stderr={err!r}".format(
            code=EXIT_UNREACHABLE, rc=res.returncode, err=res.stderr))
    assert _keys(res.stdout).get("DB_AUTH") == "unreachable", res.stdout


def test_a_proven_unreachable_cluster_stays_unreachable_with_no_credential_at_all(
        tmp_path):
    """Precedence, pinned: transport evidence outranks the credential question.

    Both states refuse, so the only thing at stake is WHICH remedy the reader is
    given - and telling someone to fix authentication for a cluster that did not
    answer at all is a false statement about their machine.
    """
    pkg = _fake_odoo_raising(
        tmp_path, message="could not connect to server: Connection refused")
    res = _preflight(pkg, tmp_path, "--db-host", "h", "--db-user", "u")
    assert res.returncode == EXIT_UNREACHABLE, (
        "no resolvable credential must not overwrite a PROVEN transport failure; "
        "got {rc}, stderr={err!r}".format(rc=res.returncode, err=res.stderr))
    assert _keys(res.stdout).get("DB_AUTH") == "unreachable", res.stdout


def test_preflight_never_reports_ok_for_an_unrecognised_failure(tmp_path):
    """Undeterminable is its own state. It is never `ok` and never a factual `no`."""
    pkg = _fake_odoo_raising(tmp_path, message="wholly unrecognisable failure text")
    res = _preflight(pkg, tmp_path, "--db-host", "h", "--db-user", "u",
                     env_extra={"ODOO_PG_PASSWORD": SENTINEL})
    keys = _keys(res.stdout)
    assert keys.get("DB_AUTH") == "unknown", res.stdout
    assert keys.get("DB_AUTH") != "ok", "an unrecognised failure must never read as ok"
    assert res.returncode == EXIT_UNKNOWN, (
        "got {rc}, stderr={err!r}".format(rc=res.returncode, err=res.stderr))


def test_preflight_reports_ok_only_when_the_connection_actually_answered(tmp_path):
    """The positive case must be reachable, or the gate is a permanent refusal."""
    pkg = _fake_odoo_ok(tmp_path)
    res = _preflight(pkg, tmp_path, "--db-host", "h", "--db-user", "u")
    assert res.returncode == EXIT_OK, (
        "got {rc}, stderr={err!r}".format(rc=res.returncode, err=res.stderr))
    assert _keys(res.stdout).get("DB_AUTH") == "ok", res.stdout


# --------------------------------------------------------------------------- #
# The credential INFERENCE must not swallow failures that are not about
# credentials.
#
# "No credential is resolvable" is permanently TRUE on the default developer
# setup: a trust cluster, no --db-password, no $ODOO_PG_PASSWORD, no ~/.pgpass. An
# unguarded inference from it therefore turned EVERY failure that reached it into
# exit 8 - a BLOCKED build told to fix an authentication problem it does not have,
# where the previous release let the build run and let Odoo report the real error.
# Each case below is a failure a real cluster produces while ACCEPTING the
# connection, and none of them is remedied by anything the refusal would advise.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("case,pgcode,message", [
    # A SQLSTATE at all proves the server reported it about a statement, so the
    # handshake completed - whatever the credential situation is.
    ("too many connections (SQLSTATE)", "53300",
     'FATAL:  too many connections for role "odoo"'),
    ("out of memory (SQLSTATE)", "53200", "ERROR:  out of memory"),
    # The shape psycopg2 ACTUALLY delivers at connect time: no SQLSTATE at all, so
    # only the server's own words separate these from a refusal.
    ("too many connections (no SQLSTATE)", None,
     'connection to server at "h" failed: FATAL:  too many connections for role "odoo"'),
    ("cluster still starting up", None,
     'connection to server at "h" failed: FATAL:  the database system is starting up'),
    ("maintenance database absent", None,
     'connection to server at "h" failed: FATAL:  database "postgres" does not exist'),
    ("server out of memory", None,
     'connection to server at "h" failed: FATAL:  out of memory'),
])
def test_a_failure_the_server_explained_is_never_reported_as_denied(
        tmp_path, case, pgcode, message):
    """UNDETERMINABLE, so the build proceeds and Odoo reports the real error.

    Not `denied`: the remedy a denial names (run setup, or export a password)
    cannot fix a full connection-slot table, a cluster mid-startup, an absent
    maintenance database or an out-of-memory server - and exit 8 blocks the build
    outright, so the user is left with a wrong diagnosis and no way forward.
    """
    pkg = _fake_odoo_raising(
        tmp_path, message=message, pgcode=pgcode,
        dirname="fake_odoo_" + re.sub(r"[^a-z0-9]+", "_", case.lower()))
    # NOTHING can supply a credential here: no flag, no env var, an empty pgpass.
    res = _preflight(pkg, tmp_path, "--db-host", "h", "--db-user", "u")
    keys = _keys(res.stdout)
    assert keys.get("DB_AUTH") == "unknown", (
        "[{c}] the server explained itself, so this is not a credential verdict; "
        "got DB_AUTH={a!r} (stdout={out!r})".format(
            c=case, a=keys.get("DB_AUTH"), out=res.stdout))
    assert res.returncode == EXIT_UNKNOWN, (
        "[{c}] expected exit {e} (undeterminable never blocks); got {rc}, "
        "stderr={err!r}".format(c=case, e=EXIT_UNKNOWN, rc=res.returncode,
                                err=res.stderr))


def test_a_statement_level_failure_is_never_reported_as_denied(tmp_path):
    """A failure that is not connection-shaped at all keeps `unknown` too.

    The same guard the drop classifier already applied: an exception whose class is
    not OperationalError did not come from the handshake, so the credential
    inference has nothing to say about it.
    """
    pkg = _fake_odoo_raising(
        tmp_path, message="filestore removal failed", exc_class="RuntimeError",
        dirname="fake_odoo_not_operational")
    res = _preflight(pkg, tmp_path, "--db-host", "h", "--db-user", "u")
    assert _keys(res.stdout).get("DB_AUTH") == "unknown", res.stdout
    assert res.returncode == EXIT_UNKNOWN, (
        "got {rc}, stderr={err!r}".format(rc=res.returncode, err=res.stderr))


def test_a_verdict_does_not_depend_on_whether_a_password_file_happens_to_exist(
        tmp_path):
    """The SAME server error must get the SAME verdict on two different hosts.

    Before the guard, a host with a matching ~/.pgpass got `unknown` for a server
    error while a host without one got `denied` and a blocked build - so the
    verdict was decided by a local file rather than by what the server said, which
    contradicts the invariant that only a PROVEN state may block.
    """
    message = ('connection to server at "h" failed: FATAL:  too many connections '
               'for role "odoo"')
    host_a, host_b = tmp_path / "a", tmp_path / "b"
    host_a.mkdir()
    host_b.mkdir()
    with_file = _preflight(
        _fake_odoo_raising(tmp_path, message=message, dirname="fake_odoo_pgpass_yes"),
        host_a, "--db-host", "h", "--db-user", "u",
        pgpass_lines=["h:*:*:u:irrelevant"])
    without_file = _preflight(
        _fake_odoo_raising(tmp_path, message=message, dirname="fake_odoo_pgpass_no"),
        host_b, "--db-host", "h", "--db-user", "u")
    assert _keys(with_file.stdout).get("DB_AUTH") == \
        _keys(without_file.stdout).get("DB_AUTH"), (
        "the verdict changed with the presence of a password file: with={w!r} "
        "without={o!r}".format(w=with_file.stdout, o=without_file.stdout))
    assert with_file.returncode == without_file.returncode, (
        "the exit code changed with the presence of a password file: {a} vs {b}".format(
            a=with_file.returncode, b=without_file.returncode))


def test_the_credential_inference_still_catches_a_server_that_demanded_a_password(
        tmp_path):
    """The belt must keep working: an UNRECOGNISABLE message plus no resolvable
    credential is still `denied`.

    This is the case the inference exists for - a server whose own messages are
    localised, where no signature can match - so narrowing the rule must not have
    turned it off.
    """
    pkg = _fake_odoo_raising(tmp_path, message="voellig unlesbarer Fehlertext",
                             dirname="fake_odoo_belt")
    res = _preflight(pkg, tmp_path, "--db-host", "h", "--db-user", "u")
    assert _keys(res.stdout).get("DB_AUTH") == "denied", res.stdout
    assert res.returncode == EXIT_AUTH_DENIED, (
        "got {rc}, stderr={err!r}".format(rc=res.returncode, err=res.stderr))


# --------------------------------------------------------------------------- #
# The locale pin - the classifier reads libpq's own strings, so the pin is part
# of the contract, not a nicety.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("env_extra,expect_lc_all", [
    # LC_ALL outranks LC_MESSAGES in POSIX and in glibc, so pinning LC_MESSAGES
    # alone leaves the messages translated and every signature table dead.
    ({"LC_ALL": "de_DE.UTF-8", "LANGUAGE": "de:en"}, "C"),
    # Not set beforehand -> not set by us either: pinning LC_ALL unconditionally
    # would also pin LC_NUMERIC / LC_CTYPE for a process that asked for neither.
    ({"LANGUAGE": "de:en"}, "<unset>"),
])
def test_message_translation_is_pinned_before_the_connection_is_opened(
        tmp_path, env_extra, expect_lc_all):
    """Observed from INSIDE db_connect, which is the only place it matters."""
    recorded = tmp_path / "locale-at-connect.txt"
    pkg = _fake_odoo_raising(
        tmp_path, message="could not connect to server: Connection refused",
        dirname="fake_odoo_locale", record_env_to=recorded)
    res = _preflight(pkg, tmp_path, "--db-host", "h", "--db-user", "u",
                     env_extra=env_extra)
    assert recorded.exists(), (
        "db_connect was never reached, so nothing was observed; stdout={out!r} "
        "stderr={err!r}".format(out=res.stdout, err=res.stderr))
    seen = _keys(recorded.read_text(encoding="utf-8"))
    assert seen.get("LC_MESSAGES") == "C", (
        "LC_MESSAGES must be pinned before the connection; got {s!r}".format(s=seen))
    assert seen.get("LC_ALL") == expect_lc_all, (
        "LC_ALL handling is wrong; got {s!r}".format(s=seen))
    assert seen.get("LANGUAGE") == "", (
        "LANGUAGE outranks both whenever the locale is not C, so it must be "
        "cleared; got {s!r}".format(s=seen))


@pytest.mark.parametrize("state,message,pgcode,expected_rc", [
    ("denied", "any text at all", "28P01", EXIT_AUTH_DENIED),
    ("unreachable", "could not connect to server: Connection refused", None,
     EXIT_UNREACHABLE),
    ("unknown", "wholly unrecognisable failure text", None, EXIT_UNKNOWN),
])
def test_every_non_ok_preflight_message_names_the_setup_command(
        tmp_path, state, message, pgcode, expected_rc):
    """Every refusal hands the reader the ONE command that resolves it.

    Asserted over all three states from one parametrisation, so the guard cannot
    pass on a single phrasing while another refusal path says nothing.
    """
    pkg = _fake_odoo_raising(tmp_path, message=message, pgcode=pgcode,
                             dirname="fake_odoo_" + state)
    res = _preflight(pkg, tmp_path, "--db-host", "h", "--db-user", "u",
                     env_extra={"ODOO_PG_PASSWORD": SENTINEL})
    assert res.returncode == expected_rc, (
        "[{s}] got {rc}, stderr={err!r}".format(s=state, rc=res.returncode,
                                                err=res.stderr))
    assert "/odoo-ai-agents:odoo-setup" in res.stderr, (
        "[{s}] the refusal must name the setup command; got {err!r}".format(
            s=state, err=res.stderr))


@pytest.mark.parametrize("state,message,pgcode", [
    ("ok", None, None),
    ("denied", "any text at all", "28P01"),
    ("unreachable", "could not connect to server: Connection refused", None),
    ("unknown", "wholly unrecognisable failure text", None),
])
def test_preflight_never_prints_the_credential_value(tmp_path, state, message, pgcode):
    """A verdict is not worth leaking a secret for.

    Both credential sources carry a distinctive sentinel; neither may appear on
    stdout or stderr in ANY of the four states.
    """
    if message is None:
        pkg = _fake_odoo_ok(tmp_path)
    else:
        pkg = _fake_odoo_raising(tmp_path, message=message, pgcode=pgcode,
                                 dirname="fake_odoo_leak_" + state)
    res = _preflight(pkg, tmp_path, "--db-host", "h", "--db-user", "u",
                     env_extra={"ODOO_PG_PASSWORD": SENTINEL},
                     pgpass_lines=["h:*:*:u:" + SENTINEL])
    # The subcommand must have RUN: a usage error leaks nothing, so this guard
    # would otherwise pass on a preflight that does not exist.
    assert res.returncode in (EXIT_OK, EXIT_UNKNOWN, EXIT_AUTH_DENIED, EXIT_UNREACHABLE), (
        "[{s}] preflight must return a contract code, not a usage error; got {rc}, "
        "stderr={err!r}".format(s=state, rc=res.returncode, err=res.stderr))
    assert _keys(res.stdout).get("DB_AUTH") == state, res.stdout
    assert SENTINEL not in res.stdout, "[{s}] stdout leaked the credential".format(s=state)
    assert SENTINEL not in res.stderr, "[{s}] stderr leaked the credential".format(s=state)


# --------------------------------------------------------------------------- #
# Placement - the build verbs refuse BEFORE they open a log or launch odoo-bin
# --------------------------------------------------------------------------- #
def _step55_env(tmp_path, *, preflight_rc, record_argv=None, record_env=None,
                preflight_sleep_s=0):
    """A stub interpreter + stub odoo-bin for a 55-instance-ops.sh build verb.

    The interpreter answers `odoo_db.py preflight` with `preflight_rc` and RECORDS
    every odoo-bin invocation, so "no odoo-bin was launched" is asserted from a
    positive recording rather than from the absence of a side effect.
    """
    bindir = tmp_path / "bin55"
    bindir.mkdir(parents=True, exist_ok=True)
    addons = tmp_path / "core" / "addons"
    addons.mkdir(parents=True, exist_ok=True)
    odoo_bin = tmp_path / "core" / "odoo-bin"
    odoo_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    odoo_bin.chmod(0o755)

    argv_log = record_argv or (tmp_path / "odoo_bin_argv.log")
    env_log = record_env or (tmp_path / "odoo_bin_env.log")
    py = bindir / "stub_python"
    py.write_text(textwrap.dedent("""\
        #!/bin/sh
        case "$1" in
          *odoo_db.py)
            if [ "$2" = "preflight" ]; then
                # An interpreter that never answers is what an unreachable
                # cluster looks like from here: psycopg2 opens the connection
                # with no libpq connect timeout, so a dropped SYN never
                # replies at all.
                [ {sleep} -gt 0 ] && sleep {sleep}
                echo "DB_AUTH=probe"
                if [ {rc} -ne 0 ]; then
                    echo "odoo_db: BLOCKED - run /odoo-ai-agents:odoo-setup" >&2
                fi
                exit {rc}
            fi
            exit 0 ;;
          *odoo-bin)
            # The `--version` venv probe is NOT a build: only a real launch is
            # recorded, so "odoo-bin was never launched" means what it says.
            case "$2" in
              --version) echo "Odoo Server 17.0"; exit 0 ;;
            esac
            echo "$@" >> "{argv}"
            echo "PGPASSWORD=${{PGPASSWORD:-<unset>}}" >> "{envlog}"
            echo "Modules loaded."
            exit 0 ;;
        esac
        exit 0
        """).format(rc=preflight_rc, argv=argv_log, envlog=env_log,
                    sleep=preflight_sleep_s), encoding="utf-8")
    py.chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = farm_path(_PATH_FARM["get"](drop=_PG_CLIENT_BINS), bindir)
    env["ODOO_AI_HOME"] = str(tmp_path / "home")
    env.pop("ODOO_PG_PASSWORD", None)
    return env, py, addons, argv_log, env_log


def _run_step55(env, verb, py, addons, *extra):
    return subprocess.run(
        ["bash", str(STEP55), verb, "--db", "somedb", "--python", str(py),
         "--addons", str(addons), "--modules", "base", *extra],
        capture_output=True, text=True, env=env, timeout=120,
    )


@requires_bash
@pytest.mark.parametrize("verb", BUILD_VERBS)
def test_build_verbs_refuse_before_opening_a_log_or_launching_odoo_bin(tmp_path, verb):
    """A refusal must cost nothing: no log file, no odoo-bin, no partial database.

    Odoo opens the maintenance-database connection on EVERY `-d` run, so a denied
    cluster kills the process mid-build. Refusing after the log is opened leaves a
    log that documents nothing; refusing after the launch leaves a half-built
    database. Parametrised across all three verbs so a verb added later is covered
    by shape rather than by a second hand-typed list.
    """
    env, py, addons, argv_log, _env_log = _step55_env(
        tmp_path / verb, preflight_rc=EXIT_AUTH_DENIED)
    res = _run_step55(env, verb, py, addons)

    assert res.returncode == EXIT_AUTH_DENIED, (
        "[{v}] a denied cluster must exit {code}; got {rc}, stdout={out!r} "
        "stderr={err!r}".format(v=verb, code=EXIT_AUTH_DENIED, rc=res.returncode,
                                out=res.stdout, err=res.stderr))
    assert "LOG_PATH=" not in res.stdout, (
        "[{v}] a refusal must open NO log; got {out!r}".format(v=verb, out=res.stdout))
    assert not argv_log.exists(), (
        "[{v}] odoo-bin must NOT be launched on a refusal; got {log!r}".format(
            v=verb, log=argv_log.read_text(encoding="utf-8") if argv_log.exists() else ""))
    assert "STATUS=error" in res.stdout, (
        "[{v}] the machine-readable failure line must still be emitted; got "
        "{out!r}".format(v=verb, out=res.stdout))
    assert "/odoo-ai-agents:odoo-setup" in res.stderr, (
        "[{v}] the primitive's refusal must be FORWARDED verbatim, not re-worded; "
        "got {err!r}".format(v=verb, err=res.stderr))


@requires_bash
@pytest.mark.parametrize("verb", BUILD_VERBS)
def test_build_verbs_forward_odoo_pg_password_to_libpq_by_name_not_on_argv(tmp_path, verb):
    """The escape-hatch credential reaches libpq through the ENVIRONMENT.

    Odoo omits the password from its connection unless `db_password` is set, in
    which case libpq resolves `PGPASSWORD` itself - so exporting it for the launch
    is enough, and putting it on argv would publish it in the process table.
    """
    env, py, addons, argv_log, env_log = _step55_env(
        tmp_path / verb, preflight_rc=EXIT_OK)
    env["ODOO_PG_PASSWORD"] = SENTINEL
    res = _run_step55(env, verb, py, addons)

    assert argv_log.exists(), (
        "[{v}] test setup: odoo-bin must have been launched; stdout={out!r} "
        "stderr={err!r}".format(v=verb, out=res.stdout, err=res.stderr))
    argv = argv_log.read_text(encoding="utf-8")
    assert SENTINEL not in argv, (
        "[{v}] the credential must never appear on odoo-bin's argv; got {a!r}".format(
            v=verb, a=argv))
    assert "--db_password" not in argv, (
        "[{v}] the password flag must not be on argv; got {a!r}".format(v=verb, a=argv))
    assert "PGPASSWORD=" + SENTINEL in env_log.read_text(encoding="utf-8"), (
        "[{v}] libpq must receive the credential BY NAME in the launch "
        "environment".format(v=verb))


@requires_bash
def test_the_step55_preflight_cannot_hang_before_a_log_exists(tmp_path):
    """A preflight that never answers must not become an UNBOUNDED build.

    This one runs BEFORE the log is opened, so an unbounded hang emits no
    `LOG_PATH=` at all - and the dispatching agent's mandatory `wait-log --timeout`
    then has nothing to bind to, turning one logged failure into a silent forever
    stall. psycopg2 opens the connection with no libpq connect timeout, so a host
    that DROPS the SYN (a firewall DROP, a paused container, a VPN-gated remote)
    never replies at all: only the bound ends the wait.

    A bound that elapsed is UNDETERMINED, so the build must go ON and reach
    odoo-bin - which is where the real outcome gets written to a log a caller can
    bound.
    """
    env, py, addons, argv_log, _env_log = _step55_env(
        tmp_path, preflight_rc=EXIT_OK, preflight_sleep_s=600)
    env["ODOO_AI_PG_PROBE_TIMEOUT"] = "2"
    env["ODOO_AI_PG_KILL_GRACE"] = "1"
    deadline_s = 45
    try:
        res = subprocess.run(
            ["bash", str(STEP55), "test", "--db", "somedb", "--python", str(py),
             "--addons", str(addons), "--modules", "base"],
            capture_output=True, text=True, env=env, timeout=deadline_s)
    except subprocess.TimeoutExpired:
        raise AssertionError(
            "55-instance-ops.sh did not return within {d}s with a {b}s probe bound - "
            "the preflight is UNBOUNDED, and it runs before any LOG_PATH= is "
            "emitted".format(d=deadline_s, b=env["ODOO_AI_PG_PROBE_TIMEOUT"]))
    assert argv_log.exists(), (
        "a bound that elapsed says NOTHING about the cluster, so the build must "
        "proceed to odoo-bin; stdout={out!r} stderr={err!r}".format(
            out=res.stdout, err=res.stderr))
    assert "LOG_PATH=" in res.stdout, (
        "the run must still emit the log path a caller can bound; got {out!r}".format(
            out=res.stdout))


# --------------------------------------------------------------------------- #
# Placement - the spin-up listener
# --------------------------------------------------------------------------- #
def _step50_env(tmp_path, *, preflight_rc, pg_isready_rc=0):
    """A spin-up fixture whose `pg_isready` says YES and whose preflight decides.

    `pg_isready` reports a cluster as accepting connections regardless of
    credentials, so it can prove `unreachable` and can never prove `ok`. This
    fixture is the exact shape where the two answers disagree.
    """
    bindir = tmp_path / "bin50"
    bindir.mkdir(parents=True, exist_ok=True)
    docker = bindir / "docker"
    docker.write_text("#!/bin/sh\nexit {rc}\n".format(rc=pg_isready_rc), encoding="utf-8")
    docker.chmod(0o755)
    launch_log = tmp_path / "launched.log"
    conf_log = tmp_path / "conf_seen.log"
    core = tmp_path / "core"
    (core / "addons").mkdir(parents=True, exist_ok=True)
    odoo_bin = core / "odoo-bin"
    odoo_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    odoo_bin.chmod(0o755)
    py = bindir / "stub_python"
    py.write_text(textwrap.dedent("""\
        #!/bin/sh
        case "$1" in
          *odoo_db.py)
            if [ "$2" = "preflight" ]; then
                echo "DB_AUTH=probe"
                if [ {rc} -ne 0 ]; then
                    echo "odoo_db: BLOCKED - run /odoo-ai-agents:odoo-setup" >&2
                fi
                exit {rc}
            fi
            exit 0 ;;
          *odoo-bin)
            case "$2" in
              --version) echo "Odoo Server 17.0"; exit 0 ;;
            esac
            echo "launched $@" >> "{launched}"
            echo "PGPASSWORD=${{PGPASSWORD:-<unset>}}" >> "{launched}"
            for a in "$@"; do
                case "$prev" in -c) cp "$a" "{conf}" ;; esac
                prev="$a"
            done
            while : ; do sleep 1; done ;;
        esac
        exit 0
        """).format(rc=preflight_rc, launched=launch_log, conf=conf_log),
        encoding="utf-8")
    py.chmod(0o755)

    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    toml = tmp_path / "instances.toml"
    toml.write_text(textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        run_mode = "source"
        http_port = 8069
        db_name = "odoo_17_0"
        db_host = "localhost"
        db_port = 5544
        db_user = "odoo"
        db_run_mode = "docker"
        db_container = "declared-container"
        addons_path = "{addons}"
        python = "{py}"
        odoo_root = "{root}"
        """).format(addons=core / "addons", py=py, root=core), encoding="utf-8")

    env = dict(os.environ)
    # `docker` comes from the stub dir (so the container rung IS selected); every
    # other client name is constructed absent, so the rung selection is decided by
    # this fixture and not by whatever the runner image ships.
    env["PATH"] = farm_path(_PATH_FARM["get"](drop=_PG_CLIENT_BINS), bindir)
    env["ODOO_AI_HOME"] = str(home)
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_BIN"] = str(odoo_bin)
    env["SPINUP_TIMEOUT"] = "3"
    env["ODOO_AI_ALLOCATOR"] = ""
    env.pop("ODOO_PG_PASSWORD", None)
    return env, launch_log, conf_log


@requires_bash
def test_spinup_refuses_when_only_pg_isready_would_have_said_yes(tmp_path):
    """`pg_isready` answers a question nobody asked.

    It reports a cluster as accepting connections whatever the credentials are, so
    treating it as terminal-green validates a route the launch never takes. The
    preflight through Odoo's own connection layer is the rung that decides.
    """
    env, launch_log, _conf = _step50_env(tmp_path, preflight_rc=EXIT_AUTH_DENIED,
                                        pg_isready_rc=0)
    res = subprocess.run(["bash", str(STEP50), "apply", "--version", "17.0"],
                         capture_output=True, text=True, env=env, timeout=120)
    assert res.returncode != 0, (
        "a denied cluster must block the spin-up; stdout={out!r} stderr={err!r}".format(
            out=res.stdout, err=res.stderr))
    assert not launch_log.exists(), (
        "no server may be launched on a refusal; got {log!r}".format(
            log=launch_log.read_text(encoding="utf-8") if launch_log.exists() else ""))
    assert "/odoo-ai-agents:odoo-setup" in (res.stdout + res.stderr), (
        "the refusal must name the setup command; stdout={out!r} stderr={err!r}".format(
            out=res.stdout, err=res.stderr))


@requires_bash
def test_spinup_writes_no_db_password_into_the_generated_conf(tmp_path):
    """The plugin writes no secret to disk, anywhere.

    The generated conf outlives the process it configures (`-c <conf>` keeps it
    open for the server's whole life) and was removed only on the poll-timeout
    path, so a SUCCESSFUL spin-up left a plaintext credential behind forever. The
    launch environment carries it instead, which needs no cleanup at all.
    """
    env, launch_log, conf_log = _step50_env(tmp_path, preflight_rc=EXIT_OK)
    env["ODOO_PG_PASSWORD"] = SENTINEL
    subprocess.run(["bash", str(STEP50), "apply", "--version", "17.0"],
                   capture_output=True, text=True, env=env, timeout=120)

    assert launch_log.exists(), "test setup: the server must have been launched"
    launched = launch_log.read_text(encoding="utf-8")
    assert "PGPASSWORD=" + SENTINEL in launched, (
        "libpq must receive the credential by name in the launch environment; got "
        "{l!r}".format(l=launched))
    assert conf_log.exists(), "test setup: the generated conf must have been captured"
    conf = conf_log.read_text(encoding="utf-8")
    assert "db_password" not in conf, (
        "the generated conf must carry no db_password line; got:\n{c}".format(c=conf))
    assert SENTINEL not in conf, (
        "the credential value must never be written to a file; got:\n{c}".format(c=conf))


# --------------------------------------------------------------------------- #
# The refusal text lives in ONE place
# --------------------------------------------------------------------------- #
# Every caller of the preflight primitive. A caller missing from this list is not
# guarded at all, which is how the one caller this change added restated the
# diagnosis at leisure.
_PREFLIGHT_CALLERS = (
    "55-instance-ops.sh",
    "50-instance-spinup.sh",
    "48-db-local-auth.sh",
    "45-venv.sh",
    "05-prereq-check.sh",
)

# The sentences that MAKE UP the owned verdict block. Asserted present in
# odoo_db.py, so this guard cannot pass by watching for text nobody writes.
_OWNED_VERDICT_SENTENCES = (
    r"cannot authenticate to PostgreSQL as",
    r"Every odoo-bin run opens this connection",
    r"NOTHING was created and NOTHING was dropped",
)

# What no CALLER may compose: the owned sentences PLUS the paraphrases a second
# copy actually shows up as. An alternation, not one exact string - a guard bound
# to a single phrasing goes green against every rewording, and a rewording is
# exactly what a duplicated verdict looks like. Matched case-insensitively.
# A one-line SURVEY entry in a checklist ("[ -- ] Odoo CANNOT authenticate ... for
# <label>") is deliberately NOT matched: it names which instance is affected and
# points at the fix, and it is the only thing a per-instance loop can print without
# repeating the whole block once per instance.
_FORBIDDEN_IN_CALLERS = _OWNED_VERDICT_SENTENCES + (
    r"still cannot authenticate",
    r"refused Odoo's credentials",
    r"authentication (?:has )?failed for role",
)


def test_only_the_primitive_composes_the_refusal_text():
    """One message, one place: every caller forwards the primitive's bytes.

    A second copy of a verdict is how a setup step came to contradict the command
    that runs next, so the shell callers must forward stderr rather than re-word
    the diagnosis.
    """
    owner = ODOO_DB_PY.read_text(encoding="utf-8")
    assert owner.count("DB_AUTH=denied") >= 1, (
        "odoo_db.py must own the denied refusal block")
    for pattern in _OWNED_VERDICT_SENTENCES:
        assert re.search(pattern, owner, re.IGNORECASE), (
            "odoo_db.py no longer carries {p!r} - either the owned text moved or this "
            "guard is now watching for a sentence nobody writes".format(p=pattern))
    steps = PLUGIN / "scripts" / "setup-steps"
    for name in _PREFLIGHT_CALLERS:
        path = steps / name
        assert path.is_file(), "missing preflight caller: {p}".format(p=path)
        text = path.read_text(encoding="utf-8")
        for pattern in _FORBIDDEN_IN_CALLERS:
            assert not re.search(pattern, text, re.IGNORECASE), (
                "{p} restates the owned verdict ({q!r}) instead of forwarding the "
                "primitive's bytes".format(p=name, q=pattern))


# --------------------------------------------------------------------------- #
# The prerequisite checklist must not answer two different questions two
# different ways.
#
# A cluster that ANSWERED and refused Odoo's credentials is REACHABLE. Reporting
# it as unreachable put two contradicting lines in one checklist - "PostgreSQL is
# not reachable" directly above "Odoo CANNOT authenticate ... run setup" - and
# told the reader to start a cluster that was already running. The reachability
# rung must therefore use the verb that CLASSIFIES (`preflight`); `exists`
# collapses every failure into 1 by contract ("exit 0 always"), so the arms that
# separate refused from absent were unreachable code.
# --------------------------------------------------------------------------- #
STEP05 = PLUGIN / "scripts" / "setup-steps" / "05-prereq-check.sh"


def _step05_tcp_only_env(tmp_path, *, preflight_rc):
    """A declared `tcp-only` instance whose only probe surface is its own python.

    tcp-only DECLARES that this host has no client binaries for the cluster, so the
    pg_isready and docker rungs are skipped by the code itself - and the hermetic
    PATH makes sure a client on the developer's machine cannot supply one either.
    """
    bindir = tmp_path / "bin05"
    bindir.mkdir(parents=True, exist_ok=True)
    (bindir / "curl").write_text('#!/bin/sh\necho 200\n', encoding="utf-8")
    (bindir / "curl").chmod(0o755)
    py = bindir / "stub_python"
    py.write_text(textwrap.dedent("""\
        #!/bin/sh
        case "$1" in
          *odoo_db.py)
            case "$2" in
              preflight) echo "DB_AUTH=denied"; echo "DB_AUTH_WHY=stub"; exit {rc} ;;
              exists) exit 1 ;;
              can-createdb) echo "true"; exit 0 ;;
            esac
            exit 0 ;;
        esac
        exit 0
        """).format(rc=preflight_rc), encoding="utf-8")
    py.chmod(0o755)
    addons = tmp_path / "addons"
    addons.mkdir(exist_ok=True)
    toml = tmp_path / "instances.toml"
    toml.write_text(textwrap.dedent("""\
        [[instance]]
        series = "17.0"
        run_mode = "source"
        addons_path = ["{addons}"]
        http_port = 8069
        db_name = "probe_db"
        db_host = "localhost"
        db_user = "odoo"
        db_port = 5432
        python = "{py}"
        odoo_root = "{root}"
        db_run_mode = "tcp-only"
        """).format(addons=addons, py=py, root=tmp_path), encoding="utf-8")
    env = dict(os.environ)
    env["PATH"] = farm_path(_PATH_FARM["get"](drop=_PG_CLIENT_BINS), bindir)
    env["SETUP_FILTER"] = "instance"
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["ODOO_AI_HOME"] = str(tmp_path / "home")
    env["ODOO_GIT_BASE"] = str(tmp_path / "git")
    env.pop("ODOO_PG_PASSWORD", None)
    return env


@requires_bash
def test_a_cluster_that_refused_our_credentials_is_reported_as_reachable(tmp_path):
    """One question, one answer - and the remedy belongs to the line that owns it."""
    env = _step05_tcp_only_env(tmp_path, preflight_rc=EXIT_AUTH_DENIED)
    res = subprocess.run(["bash", str(STEP05), "apply"],
                         capture_output=True, text=True, env=env, timeout=120)
    out = res.stdout
    assert "PostgreSQL reachable" in out, (
        "a cluster that answered and refused us is REACHABLE; got {out!r}".format(out=out))
    assert "NOT reachable" not in out, (
        "the checklist contradicted itself: the same cluster cannot be unreachable "
        "AND have refused our credentials; got {out!r}".format(out=out))
    assert "start PostgreSQL" not in out, (
        "this reader's cluster is running, so the remedy must not be to start it; "
        "got {out!r}".format(out=out))
    assert "authenticate" in out, (
        "the credential fact must still be reported by the line that owns it; got "
        "{out!r}".format(out=out))


@requires_bash
def test_a_cluster_that_never_answered_is_still_reported_as_unreachable(tmp_path):
    """The other side of the same rung: only a PROVEN 9 may report a down cluster,
    and that reader IS the one who should be told to start it."""
    env = _step05_tcp_only_env(tmp_path, preflight_rc=EXIT_UNREACHABLE)
    res = subprocess.run(["bash", str(STEP05), "apply"],
                         capture_output=True, text=True, env=env, timeout=120)
    out = res.stdout
    assert "NOT reachable" in out, (
        "a cluster that did not answer must be reported as down; got {out!r}".format(
            out=out))
    assert "start PostgreSQL" in out, (
        "and that is the one reader who must be told to start it; got {out!r}".format(
            out=out))


@requires_bash
@pytest.mark.parametrize("rc", [EXIT_UNKNOWN, EXIT_NO_VENV])
def test_an_unanswerable_probe_is_reported_as_no_verdict_not_as_a_down_cluster(
        tmp_path, rc):
    """`unknown` and "this venv cannot import odoo" are not cluster facts. Reported
    as a down cluster they send a reader to restart something that may be fine, and
    they would also BLOCK `check` - which only a proven negative may do."""
    env = _step05_tcp_only_env(tmp_path, preflight_rc=rc)
    res = subprocess.run(["bash", str(STEP05), "apply"],
                         capture_output=True, text=True, env=env, timeout=120)
    out = res.stdout
    assert "no way to probe yet" in out, (
        "[exit {rc}] must be reported as no verdict; got {out!r}".format(rc=rc, out=out))
    assert "NOT reachable" not in out, (
        "[exit {rc}] says nothing about the cluster; got {out!r}".format(rc=rc, out=out))
