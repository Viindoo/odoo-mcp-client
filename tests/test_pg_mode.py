"""Behavior tests for scripts/lib/pg_mode.sh - the Postgres client-surface detector.

What these protect is a single rule: DETECTION NEVER GUESSES. The declared
`db_run_mode` decides how a libpq CLIENT BINARY is reached, and a wrong value
means acting on the WRONG cluster - so an ambiguous or unanswerable situation
must produce NOTHING on stdout and a non-zero exit, never a plausible default.

They also pin the cross-language parity invariant: pg_mode.sh's `pg_run_client`
and allocator.py's `_pg_client_argv` must build the SAME argv for the same
declared mode. Two implementations of one rule drift the moment only one is
tested, and the failure mode of a drifted docker arm is silent: a command that
runs against a cluster nobody asked for.

CPU-only: every case is driven by stub binaries on PATH. No Docker, no Postgres,
and deliberately no libpq client - the code under test must be exercisable on the
very host class whose missing client caused the original defect.
"""

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
PG_MODE_SH = LIB / "pg_mode.sh"
ALLOC = LIB / "allocator.py"


def _import_allocator():
    spec = importlib.util.spec_from_file_location("allocator_under_test", ALLOC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["allocator_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _stub(bindir: Path, name: str, body: str) -> Path:
    bindir.mkdir(parents=True, exist_ok=True)
    p = bindir / name
    p.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    p.chmod(0o755)
    return p


def _link_real(bindir: Path, name: str) -> bool:
    """Symlink the REAL system `name` into `bindir`, returning False when absent.

    PATH is REPLACED with `bindir` alone (see `_sh`), so a tool the code under
    test genuinely needs must be present there BY NAME. Linking the real binary
    keeps the fixture hermetic (nothing else on the host is reachable) while
    still exercising the arm that uses it - the difference between measuring a
    real bound and measuring nothing at all.
    """
    from shutil import which

    bindir.mkdir(parents=True, exist_ok=True)
    real = which(name)
    if not real:
        return False
    (bindir / name).symlink_to(real)
    return True


def _sh(bindir: Path, snippet: str, *args, env_extra=None, timeout=60):
    """Run a snippet with pg_mode.sh sourced and PATH restricted to `bindir`.

    PATH is REPLACED, not prepended: a stray real psql/docker on the developer's
    machine must not be able to turn a 'no client surface' case green.

    `timeout` is a HARD test-side bound: every function under test here promises
    to terminate, so a hang is a FAILURE (TimeoutExpired), never a test that
    waits forever.
    """
    env = dict(os.environ)
    env["PATH"] = str(bindir)
    env.pop("ODOO_PG_PASSWORD", None)
    env.pop("ODOO_AI_PG_PROBE_TIMEOUT", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["/bin/bash", "-c", f'source "{PG_MODE_SH}"\n{snippet}', "_", *[str(a) for a in args]],
        capture_output=True, text=True, env=env, timeout=timeout,
    )


def _detect(bindir: Path, db_port="", env_extra=None):
    return _sh(bindir, 'pg_detect_mode "$1"', db_port, env_extra=env_extra)


def _parse_kv(stdout: str) -> dict:
    out = {}
    for line in stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #
def test_detector_records_tcp_only_when_no_client_surface(tmp_path):
    """No client binaries and no docker: `tcp-only` is the honest third state, and
    naming it is what lets every other case refuse to guess."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    p = _detect(bindir)
    assert p.returncode == 0, p.stderr
    assert _parse_kv(p.stdout) == {"db_run_mode": "tcp-only"}


def test_detector_prefers_native_when_both_surfaces_present(tmp_path):
    """A native client serves every operation with no container-name dependency
    (a container is renamed by any compose project-dir change), so native WINS
    over a co-present container and NO container is recorded - one fact, one place."""
    bindir = tmp_path / "bin"
    for name in ("psql", "dropdb", "docker"):
        _stub(bindir, name, "exit 0\n")
    p = _detect(bindir, 5544)
    assert p.returncode == 0, p.stderr
    kv = _parse_kv(p.stdout)
    assert kv == {"db_run_mode": "native"}
    assert "db_container" not in kv, "a native surface must not record a container handle"


def test_detector_needs_every_native_binary_before_claiming_native(tmp_path):
    """psql alone is not a client surface: the raw fallback needs dropdb too, so a
    partial install must NOT be recorded as `native` (it would refuse at the one
    moment it is relied on)."""
    bindir = tmp_path / "bin"
    _stub(bindir, "psql", "exit 0\n")
    p = _detect(bindir)
    assert p.returncode == 0, p.stderr
    assert _parse_kv(p.stdout)["db_run_mode"] == "tcp-only"


def test_detector_records_docker_with_the_single_publishing_container(tmp_path):
    """The declared db_port is the PRIMARY reach; the container NAME is derived
    from it once, at registration, so the human never types it."""
    bindir = tmp_path / "bin"
    _stub(bindir, "docker", 'echo "pg-for-my-series"\nexit 0\n')
    p = _detect(bindir, 5544)
    assert p.returncode == 0, p.stderr
    assert _parse_kv(p.stdout) == {
        "db_run_mode": "docker", "db_container": "pg-for-my-series"}


def test_detector_refuses_ambiguous_container_match(tmp_path):
    """TWO containers publishing the declared port is the wrong-cluster hazard in
    its purest form: picking either one could drop databases on a cluster nobody
    named. The detector must exit non-zero, write NOTHING to stdout, and print
    both candidate names so a human can resolve it."""
    bindir = tmp_path / "bin"
    _stub(bindir, "docker", 'printf "pg-alpha\\npg-beta\\n"\nexit 0\n')
    p = _detect(bindir, 5544)
    assert p.returncode == 3, f"an ambiguous match must exit 3; got {p.returncode}"
    assert p.stdout.strip() == "", (
        f"NOTHING may be recorded when the answer is ambiguous; got {p.stdout!r}"
    )
    assert "pg-alpha" in p.stderr and "pg-beta" in p.stderr, (
        f"both candidates must be named so a human can choose; got {p.stderr!r}"
    )
    assert "db_container" in p.stderr, "the message must name the key to declare by hand"


def test_detector_refuses_docker_without_declared_db_port(tmp_path):
    """Docker as the only candidate surface but no declared db_port: the container
    serving this instance cannot be identified, so nothing is recorded and the
    message names BOTH ways a human can resolve it."""
    bindir = tmp_path / "bin"
    _stub(bindir, "docker", 'echo "should-not-be-consulted"\nexit 0\n')
    p = _detect(bindir, "")
    assert p.returncode == 3, f"got {p.returncode}, stderr={p.stderr!r}"
    assert p.stdout.strip() == "", f"nothing may be recorded; got {p.stdout!r}"
    assert "db_port" in p.stderr and "db_container" in p.stderr


def test_detector_records_tcp_only_when_no_container_publishes_the_port(tmp_path):
    """Docker present but no container serves this port: there is no client
    surface for THIS cluster, which is `tcp-only` - not an error, and not docker."""
    bindir = tmp_path / "bin"
    _stub(bindir, "docker", "exit 0\n")  # no output = no match
    p = _detect(bindir, 5544)
    assert p.returncode == 0, p.stderr
    assert _parse_kv(p.stdout) == {"db_run_mode": "tcp-only"}


def test_detector_refuses_when_docker_itself_could_not_be_asked(tmp_path):
    """A docker that EXITS NON-ZERO ("Cannot connect to the Docker daemon") is
    "I could not ask", not "no container publishes that port".

    Swallowing that status turns a transient daemon outage into the DURABLE
    catalog fact `db_run_mode = "tcp-only"`, and nothing ever re-derives it: a
    later release whose through-Odoo drop needs the raw fallback then refuses
    ("offers no libpq client surface"), retains the database, and keeps the lease
    for a retry that can never succeed. Detection never guesses, so an
    unanswerable docker query must exit 3 and record NOTHING.
    """
    bindir = tmp_path / "bin"
    _stub(bindir, "docker",
          'echo "Cannot connect to the Docker daemon at unix:///var/run/docker.sock" >&2\nexit 1\n')
    p = _detect(bindir, 5544)
    assert p.returncode == 3, (
        f"an unanswerable docker query must exit 3, not record a guess; got "
        f"{p.returncode} with stdout={p.stdout!r}"
    )
    assert p.stdout.strip() == "", (
        f"NOTHING may be recorded when docker could not be asked; got {p.stdout!r}"
    )
    assert "docker" in p.stderr.lower(), (
        f"the message must name docker as the thing that failed; got {p.stderr!r}"
    )


def test_detector_refuses_when_the_publishing_container_exists_but_is_stopped(tmp_path):
    """`docker ps` lists RUNNING containers only, so a stopped Postgres container
    is indistinguishable from "no container publishes that port" - and the
    difference decides a durable fact.

    Recording `tcp-only` for a user who simply has not started their compose
    stack yet is the same silent-wrong-fact defect as the daemon-down case above:
    refuse, name the container, and say what to do. Nothing is recorded.
    """
    bindir = tmp_path / "bin"
    # `docker ps ...` -> no rows; `docker ps -a ...` -> one stopped candidate.
    _stub(bindir, "docker", (
        'all=0\n'
        'for a in "$@"; do [ "$a" = "-a" ] && all=1; done\n'
        '[ "$all" = 1 ] && echo "pg-not-started"\n'
        'exit 0\n'
    ))
    p = _detect(bindir, 5544)
    assert p.returncode == 3, (
        f"a stopped publishing container must not be read as 'no client surface'; "
        f"got {p.returncode} with stdout={p.stdout!r}"
    )
    assert p.stdout.strip() == "", f"nothing may be recorded; got {p.stdout!r}"
    assert "pg-not-started" in p.stderr, (
        f"the stopped candidate must be named so a human can start it; got {p.stderr!r}"
    )


def test_detector_says_nothing_about_reachability(tmp_path):
    """Detection reports the CLIENT SURFACE only. "No client installed" and
    "cluster down" are different facts - conflating them is the original defect -
    so a detector run must never emit a reachability claim of any kind."""
    bindir = tmp_path / "bin"
    _stub(bindir, "docker", 'echo "pg-one"\nexit 0\n')
    p = _detect(bindir, 5544)
    combined = (p.stdout + p.stderr).lower()
    for banned in ("reachable", "unreachable", "connection refused", "is running"):
        assert banned not in combined, (
            f"the detector must not claim anything about reachability; found {banned!r}"
        )


# --------------------------------------------------------------------------- #
# Discovery of WHERE this host's connections arrive from, and whether that
# address may be trusted. Same contract as pg_detect_mode: never guess.
#
# A host-side connection to a PUBLISHED container port does not arrive as
# loopback - it is re-originated from the bridge gateway - and that gateway
# differs between the default bridge and a user-defined network on one machine.
# So a plausible-looking constant is WRONG on the second container, and a trust
# rule for an address nothing arrives from authorises a stranger while leaving the
# original failure in place. Refusing is strictly better.
# --------------------------------------------------------------------------- #
def test_origin_address_discovery_refuses_rather_than_defaulting_to_a_bridge_address(
        tmp_path):
    """An unanswerable `docker inspect` must produce NOTHING and a non-zero exit.

    `172.17.0.1` is the default bridge gateway on a great many hosts, which is
    exactly what makes defaulting to it so tempting and so wrong: it would be
    silently correct on the common case and silently authorise a stranger on the
    rest.
    """
    bindir = tmp_path / "bin"
    _stub(bindir, "docker", "exit 1\n")
    p = _sh(bindir, 'pg_origin_address pg-one')
    assert p.returncode == 3, (
        f"an unanswerable discovery must exit 3 (undeterminable); got {p.returncode}"
    )
    assert p.stdout.strip() == "", f"nothing may be emitted; got {p.stdout!r}"
    for banned in ("172.17.0.1", "127.0.0.1", "172.18.0.1", "10."):
        assert banned not in p.stdout, f"a plausible default leaked: {banned!r}"


def test_origin_address_discovery_refuses_when_docker_is_not_installed(tmp_path):
    """No docker means the question cannot be asked at all - which is not the same
    fact as "there is no gateway", and must not be answered as one."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    p = _sh(bindir, 'pg_origin_address pg-one')
    assert p.returncode == 3 and p.stdout.strip() == ""


def test_origin_address_attaches_a_single_host_prefix_length_per_family(tmp_path):
    """The prefix length is attached at discovery, once: a BARE address in a pg_hba
    rule is a HOST NAME to PostgreSQL, and a wider prefix would trust every other
    container on the bridge."""
    bindir = tmp_path / "bin"
    _stub(bindir, "docker", 'printf "10.44.0.1\\nfd00::1\\n"\nexit 0\n')
    p = _sh(bindir, 'pg_origin_address pg-one')
    assert p.returncode == 0, p.stderr
    assert sorted(p.stdout.split()) == ["10.44.0.1/32", "fd00::1/128"]


def test_origin_address_discards_a_value_that_is_not_an_address_literal(tmp_path):
    """A garbled inspect output must not become a trust line. Nothing parseable
    means nothing emitted, which the ladder then reports as undeterminable."""
    bindir = tmp_path / "bin"
    _stub(bindir, "docker", 'printf "not-an-address\\n\\n"\nexit 0\n')
    p = _sh(bindir, 'pg_origin_address pg-one')
    assert p.returncode == 3 and p.stdout.strip() == ""


@pytest.mark.parametrize("host_ip,expect", [
    ("127.0.0.1", 0), ("127.1.2.3", 0), ("::1", 0),
    ("0.0.0.0", 1), ("192.0.2.7", 1), ("::", 1),
])
def test_publish_gate_reads_an_empty_or_routable_host_ip_as_not_loopback(
        tmp_path, host_ip, expect):
    """Trusting the gateway trusts THE HOST, so the gate must be exact.

    An EMPTY HostIp is docker's own spelling of "every interface": reading it as
    loopback is how a routable publish slips past the one check that keeps the
    trade-off acceptable.
    """
    bindir = tmp_path / "bin"
    _stub(bindir, "docker", f'printf "5432/tcp {host_ip}\\n"\nexit 0\n')
    p = _sh(bindir, 'pg_publish_is_loopback_only pg-one')
    assert p.returncode == expect, f"HostIp {host_ip!r}: got {p.returncode}"


def test_publish_gate_refuses_when_it_cannot_be_asked_rather_than_passing(tmp_path):
    """No bindings reported, or an inspect that failed, is UNKNOWN - and unknown is
    never read as safe. 3 is distinct from 1 so a caller can say which it hit."""
    bindir = tmp_path / "bin"
    _stub(bindir, "docker", 'exit 0\n')
    assert _sh(bindir, 'pg_publish_is_loopback_only pg-one').returncode == 3
    _stub(bindir, "docker", 'exit 1\n')
    assert _sh(bindir, 'pg_publish_is_loopback_only pg-one').returncode == 3


def test_publish_gate_refuses_when_any_one_binding_is_routable(tmp_path):
    """ALL bindings must be loopback. One routable publish is enough to make the
    trust rule reachable from off-host, so a mixed answer is a refusal."""
    bindir = tmp_path / "bin"
    _stub(bindir, "docker",
          'printf "5432/tcp 127.0.0.1\\n5433/tcp 0.0.0.0\\n"\nexit 0\n')
    p = _sh(bindir, 'pg_publish_is_loopback_only pg-one')
    assert p.returncode == 1
    assert "0.0.0.0" in p.stderr, "the offending binding must be named"


def test_hba_file_path_asks_the_server_and_never_assumes_a_location(tmp_path):
    """hba_file may live inside PGDATA (every stock image) or under a distribution
    config dir. Editing a guessed path changes nothing while looking like success,
    so the path is ASKED for - and an unanswerable ask emits nothing."""
    bindir = tmp_path / "bin"
    _stub(bindir, "docker", 'printf "/somewhere/else/pg_hba.conf\\n"\nexit 0\n')
    p = _sh(bindir, 'pg_hba_file_path docker pg-one h u 5544')
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == "/somewhere/else/pg_hba.conf"

    _stub(bindir, "docker", 'exit 1\n')
    q = _sh(bindir, 'pg_hba_file_path docker pg-one h u 5544')
    assert q.returncode == 3 and q.stdout.strip() == ""

    # A relative or empty answer is not a path: it must be refused, not written to.
    _stub(bindir, "docker", 'printf "pg_hba.conf\\n"\nexit 0\n')
    r = _sh(bindir, 'pg_hba_file_path docker pg-one h u 5544')
    assert r.returncode == 3 and r.stdout.strip() == ""


def test_hba_file_path_refuses_for_a_mode_with_no_client_surface(tmp_path):
    """tcp-only declares there is no client surface here, so the server cannot be
    asked at all - and a path must not be invented for it."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    p = _sh(bindir, 'pg_hba_file_path tcp-only "" h u ""')
    assert p.returncode == 3 and p.stdout.strip() == ""


# --------------------------------------------------------------------------- #
# Client dispatch, and its cross-language parity with allocator.py
# --------------------------------------------------------------------------- #
# ${0##*/} rather than `basename`: PATH is replaced with the stub dir alone, so no
# external command is reachable - which is the point (the code under test must not
# need one either).
_TRACE_STUB = ('printf "%s\\n" "${0##*/}"\n'
               'for a in "$@"; do printf "%s\\n" "$a"; done\n'
               'exit 0\n')


def _shell_argv(bindir, mode, container, host, user, port, binary, *args, env_extra=None):
    """The argv the SHELL half actually executes, traced by a stub that echoes its
    own basename plus every argument it received."""
    p = _sh(
        bindir,
        'pg_run_client "$1" "$2" "$3" "$4" "$5" "$6" "${@:7}"',
        mode, container, host, user, port, binary, *args,
        env_extra=env_extra,
    )
    # One argv element per LINE: an argument may legitimately contain spaces (a
    # SQL string does), and a space-joined trace would silently split it.
    return p, p.stdout.splitlines()


@pytest.mark.parametrize("mode,container,port", [
    ("native", "", ""),
    ("native", "", "5544"),
    ("docker", "pg-one", "5544"),
])
def test_shell_and_python_client_dispatch_agree(tmp_path, mode, container, port):
    """PARITY: pg_mode.sh `pg_run_client` and allocator.py `_pg_client_argv` must
    build the SAME argv for the same declared mode. The shell half runs at setup
    time and the python half at release/gc time - if they drift, one of them talks
    to a cluster the other never meant."""
    alloc = _import_allocator()
    bindir = tmp_path / "bin"
    for name in ("psql", "docker"):
        _stub(bindir, name, _TRACE_STUB)

    args = ["-d", "postgres", "-tAc", "SELECT 1"]
    p, shell_argv = _shell_argv(bindir, mode, container, "db.example", "role", port, "psql", *args)
    assert p.returncode == 0, p.stderr
    py_argv = alloc._pg_client_argv(mode, container, "psql", "db.example", "role", port, args)

    assert py_argv is not None
    assert shell_argv == py_argv, (
        f"[{mode}] shell and python client dispatch disagree:\n"
        f"  shell : {shell_argv}\n  python: {py_argv}"
    )


def test_shell_and_python_agree_on_forwarding_the_password_into_the_container(tmp_path):
    """With ODOO_PG_PASSWORD set, both halves must forward it the same way
    (`docker exec -e PGPASSWORD`), or the docker arm authenticates in one language
    and fails in the other."""
    alloc = _import_allocator()
    bindir = tmp_path / "bin"
    _stub(bindir, "docker", _TRACE_STUB)
    _stub(bindir, "psql", _TRACE_STUB)

    p, shell_argv = _shell_argv(
        bindir, "docker", "pg-one", "db.example", "role", "5544", "psql", "--if-exists", "db",
        env_extra={"ODOO_PG_PASSWORD": "s3cret"})
    assert p.returncode == 0, p.stderr
    os.environ["ODOO_PG_PASSWORD"] = "s3cret"
    try:
        py_argv = alloc._pg_client_argv(
            "docker", "pg-one", "psql", "db.example", "role", "5544", ["--if-exists", "db"])
    finally:
        os.environ.pop("ODOO_PG_PASSWORD", None)

    assert shell_argv == py_argv, (
        f"password forwarding differs:\n  shell : {shell_argv}\n  python: {py_argv}")
    assert "-e" in shell_argv and "PGPASSWORD" in shell_argv
    assert "s3cret" not in " ".join(shell_argv), (
        "the password must be passed by NAME (docker exec -e PGPASSWORD), never as a "
        "literal argument visible in the process table"
    )


def test_docker_client_dispatch_never_passes_the_published_port(tmp_path):
    """The command runs INSIDE the container, where the PUBLISHED host port does
    not exist and the declared host resolves to the container's own loopback.
    Passing them through would target a port nothing listens on - or worse, a
    different cluster - so the docker arm connects over the local socket (-U only)."""
    alloc = _import_allocator()
    argv = alloc._pg_client_argv(
        "docker", "pg-one", "dropdb", "db.example", "role", "5544", ["--if-exists", "db"])
    assert argv is not None
    assert "-p" not in argv, f"the published port must not cross into the container; {argv}"
    assert "5544" not in argv, f"the published port must not appear at all; {argv}"
    assert "-h" not in argv and "db.example" not in argv, (
        f"the host-side hostname must not cross into the container; {argv}")
    assert argv[:4] == ["docker", "exec", "-i", "pg-one"]
    assert argv[4:] == ["dropdb", "-U", "role", "--if-exists", "db"]


@pytest.mark.parametrize("mode", ["tcp-only", "", "native-ish", "DOCKER"])
def test_no_client_surface_refuses_in_both_languages(tmp_path, mode):
    """A mode that offers no client surface must REFUSE in both halves - never
    fall through to some default that happens to work on the developer's host.
    The vocabulary is exact and case-sensitive: an unknown value is not a hint."""
    alloc = _import_allocator()
    bindir = tmp_path / "bin"
    for name in ("psql", "docker", "dropdb"):
        _stub(bindir, name, _TRACE_STUB)

    assert alloc._pg_client_argv(mode, "", "psql", "h", "u", "", []) is None, (
        f"_pg_client_argv({mode!r}) must return None, not an argv")
    p, _argv = _shell_argv(bindir, mode, "", "h", "u", "", "psql")
    assert p.returncode == 3, f"pg_run_client({mode!r}) must exit 3; got {p.returncode}"
    assert p.stdout.strip() == "", f"nothing may be executed; got {p.stdout!r}"


def test_docker_mode_without_a_container_refuses_in_both_languages(tmp_path):
    """A declared-but-unusable docker mode (db_container missing) is a declaration
    bug and must be VISIBLE, not silently downgraded to something that runs."""
    alloc = _import_allocator()
    bindir = tmp_path / "bin"
    for name in ("psql", "docker"):
        _stub(bindir, name, _TRACE_STUB)

    assert alloc._pg_client_argv("docker", "", "psql", "h", "u", "", []) is None
    p, _argv = _shell_argv(bindir, "docker", "", "h", "u", "", "psql")
    assert p.returncode == 3, f"got {p.returncode}, stderr={p.stderr!r}"
    assert "db_container" in p.stderr


# --------------------------------------------------------------------------- #
# The vocabulary itself has ONE source
# --------------------------------------------------------------------------- #
def test_pg_mode_header_enumerates_the_whole_vocabulary(tmp_path):
    """pg_mode.sh's header is the SSOT for the db_run_mode value set. Every value
    the code can produce or accept must be documented there, so a reader (human or
    agent) never has to reconstruct the vocabulary from scattered call sites."""
    header = PG_MODE_SH.read_text(encoding="utf-8")
    for value in ("native", "docker", "tcp-only"):
        assert value in header, f"the vocabulary value {value!r} must be named in the header"
    assert "SSOT" in header, "the header must declare itself the vocabulary's single source"
    assert "run_mode describes ODOO" in header or "describes POSTGRES" in header, (
        "the header must state that db_run_mode describes POSTGRES while run_mode "
        "describes ODOO - the confusion that made docker look optional"
    )


# --------------------------------------------------------------------------- #
# Probes are BOUNDED
#
# A probe is a preflight: it gates a launch, so it must never be able to outlive
# it. An unbounded probe through the instance's declared interpreter can hang
# forever (an unreachable cluster with no connect timeout, a broken venv
# wrapper), which stalls the spin-up entirely - strictly worse than the wrong
# answer the probe was added to prevent.
# --------------------------------------------------------------------------- #
def test_bounded_run_returns_124_when_the_command_outlives_the_bound(tmp_path):
    """A command that never returns must be cut off at the bound and reported as
    124 (`timeout`'s own code) - the caller then treats it as UNDETERMINED."""
    bindir = tmp_path / "bin"
    _stub(bindir, "hang", "while :; do sleep 1; done\n")
    p = _sh(bindir, 'pg_bounded_run 2 "$1"', bindir / "hang")
    assert p.returncode == 124, (
        f"an over-running probe must be cut off and reported as 124; got {p.returncode}"
    )


def test_bounded_run_passes_through_the_commands_own_exit_status(tmp_path):
    """A command that finishes in time keeps its OWN status: the bound must not
    flatten a real verdict (0 reachable / non-zero not reachable) into a timeout."""
    bindir = tmp_path / "bin"
    _stub(bindir, "ok", "exit 0\n")
    _stub(bindir, "nope", "exit 7\n")
    assert _sh(bindir, 'pg_bounded_run 5 "$1"', bindir / "ok").returncode == 0
    assert _sh(bindir, 'pg_bounded_run 5 "$1"', bindir / "nope").returncode == 7


def test_bounded_run_is_available_without_the_timeout_binary(tmp_path):
    """`timeout` is not POSIX and is absent on some hosts, so the fallback path
    must enforce the same bound - otherwise the guarantee silently disappears on
    exactly the hosts that cannot check it."""
    bindir = tmp_path / "bin"
    _stub(bindir, "hang", "while :; do sleep 1; done\n")
    _link_real(bindir, "sleep")  # the stub's own pacing; see the wall-clock tests
    # PATH holds ONLY the stub dir, so `timeout` is unreachable and the fallback
    # (background + bounded wait) is the code under test.
    p = _sh(bindir, 'command -v timeout >/dev/null 2>&1 && exit 99\npg_bounded_run 2 "$1"',
            bindir / "hang")
    assert p.returncode != 99, "test setup: `timeout` must NOT be reachable here"
    assert p.returncode == 124, (
        f"the no-timeout-binary fallback must still bound the probe; got {p.returncode}"
    )


# A blocker that needs NO external binary: `sleep` is deliberately absent from
# some fixtures below, and a `while :; do sleep 1; done` stub would then fail on
# every iteration instead of staying alive - the process must actually OUTLIVE
# the bound for the bound to be what is measured.
_SPIN_STUB = "while :; do :; done\n"


@pytest.mark.parametrize("with_timeout", [True, False])
def test_bounded_run_bound_is_measured_in_wall_clock_seconds(tmp_path, with_timeout):
    """The bound is SECONDS, on both arms - `timeout` and the fallback alike.

    The fallback must consult the CLOCK, never count loop iterations: pacing is
    best-effort (a host may have no `sleep`, or it may fail), so an
    iteration-counting loop makes the whole guarantee collapse to ~0s on exactly
    the hosts that have no `timeout` binary to check it with. `sleep` is
    deliberately absent here, so a bound that survives is a bound that is real.
    """
    bindir = tmp_path / "bin"
    _stub(bindir, "hang", _SPIN_STUB)
    if with_timeout and not _link_real(bindir, "timeout"):
        pytest.skip("no `timeout` binary on this host to exercise that arm")
    probe = 'command -v timeout >/dev/null 2>&1 && echo HAVE_TIMEOUT >&2\npg_bounded_run 3 "$1"'
    started = time.monotonic()
    p = _sh(bindir, probe, bindir / "hang", timeout=40)
    elapsed = time.monotonic() - started

    assert ("HAVE_TIMEOUT" in p.stderr) is with_timeout, (
        f"test setup: `timeout` reachability must be {with_timeout}; stderr={p.stderr!r}"
    )
    assert p.returncode == 124, (
        f"an over-running probe must be cut off and reported as 124; got {p.returncode}"
    )
    assert 2.0 <= elapsed <= 15.0, (
        f"the 3s bound must be WALL-CLOCK: cutting off after {elapsed:.3f}s means the "
        "bound is not measured in seconds at all"
    )


def test_bounded_run_a_larger_bound_actually_waits_longer(tmp_path):
    """The discriminator: two DIFFERENT bounds must produce two different waits.

    A test that only asserts `124` cannot tell a real 2s bound from no bound at
    all - both return 124. Comparing a small bound against a large one on the
    same fixture is what proves the number is honoured.
    """
    bindir = tmp_path / "bin"
    _stub(bindir, "hang", _SPIN_STUB)
    # No `timeout`: the fallback loop is the code under test (the arm where an
    # iteration count could masquerade as a clock).
    started = time.monotonic()
    short = _sh(bindir, 'pg_bounded_run 2 "$1"', bindir / "hang", timeout=40)
    short_s = time.monotonic() - started
    started = time.monotonic()
    long = _sh(bindir, 'pg_bounded_run 7 "$1"', bindir / "hang", timeout=40)
    long_s = time.monotonic() - started

    assert short.returncode == 124 and long.returncode == 124
    assert long_s - short_s >= 3.0, (
        f"a 7s bound must wait materially longer than a 2s one; got {short_s:.3f}s vs "
        f"{long_s:.3f}s - the bound is being counted, not timed"
    )


def test_bounded_run_survives_a_zero_padded_bound(tmp_path):
    """A bound like `08` must still terminate.

    `[[ -ge ]]` evaluates arithmetically, so `08` is an invalid octal literal:
    the comparison ERRORS, is never true, and the wait loop spins forever with
    the child still alive - the exact unbounded-probe hang this function exists
    to prevent, reintroduced by a two-digit environment value.
    """
    bindir = tmp_path / "bin"
    _stub(bindir, "hang", _SPIN_STUB)
    p = _sh(bindir, 'pg_bounded_run 08 "$1"', bindir / "hang", timeout=40)
    assert p.returncode == 124, (
        f"a zero-padded bound must be normalised, not turned into an infinite wait; "
        f"got {p.returncode}"
    )
    assert "value too great" not in p.stderr, (
        f"the octal arithmetic error must not reach the caller; stderr={p.stderr!r}"
    )


# A child that IGNORES SIGTERM. Not a contrived case: a probe reaches an
# interpreter, a wrapper script and a client binary, any of which may install a
# handler - and `trap '' TERM` in a shell wrapper is the commonest way it happens.
_TERM_TRAPPING_STUB = "trap '' TERM\nwhile :; do :; done\n"


@pytest.mark.parametrize("with_timeout", [True, False])
def test_bounded_run_still_bounds_a_child_that_ignores_sigterm(tmp_path, with_timeout):
    """A TERM-only bound is not a bound: it is defeated by any child that traps.

    `timeout <secs>` sends SIGTERM and then WAITS for a process that has already
    refused to leave - so the wait never ends and the probe outlives the launch it
    was gating, which is the exact unbounded hang the bound exists to prevent. Both
    arms must escalate to SIGKILL.

    A hang FAILS this test rather than hanging it: the subprocess call carries its
    own hard bound, so the failure is a TimeoutExpired, not a stuck suite.
    """
    bindir = tmp_path / "bin"
    _stub(bindir, "trapper", _TERM_TRAPPING_STUB)
    if with_timeout and not _link_real(bindir, "timeout"):
        pytest.skip("no `timeout` binary on this host to exercise that arm")
    probe = ('command -v timeout >/dev/null 2>&1 && echo HAVE_TIMEOUT >&2\n'
             'pg_bounded_run 3 "$1"')
    started = time.monotonic()
    p = _sh(bindir, probe, bindir / "trapper", timeout=45)
    elapsed = time.monotonic() - started

    assert ("HAVE_TIMEOUT" in p.stderr) is with_timeout, (
        f"test setup: `timeout` reachability must be {with_timeout}; stderr={p.stderr!r}"
    )
    assert p.returncode == 124, (
        f"a child that ignores SIGTERM must still be cut off AND reported as 124 - "
        f"every caller special-cases 124 alone, so any other code becomes a factual "
        f"negative about the cluster; got {p.returncode}"
    )
    assert elapsed <= 25.0, f"the bound was not enforced within a sane window ({elapsed:.1f}s)"


def test_bounded_run_kill_grace_is_shared_by_both_arms(tmp_path):
    """One named grace value, consulted by `timeout -k` and by the fallback's
    TERM/sleep/KILL sequence alike - so the two arms cannot drift into enforcing
    different bounds for the same probe."""
    text = PG_MODE_SH.read_text(encoding="utf-8")
    assert "PG_MODE_KILL_GRACE" in text
    assert 'timeout -k "$PG_MODE_KILL_GRACE"' in text, (
        "the `timeout` arm must pass a kill-after, or a trapping child defeats it"
    )
    assert 'sleep "$PG_MODE_KILL_GRACE"' in text, (
        "the fallback arm must use the SAME grace, not a hardcoded second"
    )


def test_bounded_run_refuses_a_non_numeric_bound_instead_of_answering(tmp_path):
    """A non-numeric bound is a CALLER bug, and it must never be answered.

    Resolved to 0 it yields an instant 124 - a probe that would have answered is
    reported UNDETERMINED. Handed to `timeout` it yields 125, which no caller
    special-cases, so every caller reads it as a factual negative ("the cluster
    is down"). Both are wrong: refuse with 125 and SAY so, and make 125 mean
    exactly one thing - the bound itself could not be applied.
    """
    bindir = tmp_path / "bin"
    _stub(bindir, "ok", "exit 0\n")
    p = _sh(bindir, 'pg_bounded_run abc "$1"', bindir / "ok")
    assert p.returncode == 125, (
        f"a non-numeric bound must return 125 (bound unusable), never 124 (probe "
        f"did not answer) and never a probe verdict; got {p.returncode}"
    )
    assert "abc" in p.stderr, (
        f"the message must name the rejected value; got {p.stderr!r}"
    )


# --------------------------------------------------------------------------- #
# The bound COMPOSED with the client dispatch
#
# This is the composition both real callers use - 50-instance-spinup.sh's docker
# preflight rung and 05-prereq-check.sh's - and neither half's own tests covered
# it: `timeout` is a coreutils BINARY, so it execs its argument and can NEVER run
# a shell FUNCTION. The bug is invisible on a host with no `timeout` (the
# background fallback runs functions fine) and fires on every GNU host.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("with_timeout", [True, False])
def test_bounded_run_can_bound_the_client_dispatch_function(tmp_path, with_timeout):
    """`pg_bounded_run <secs> pg_run_client docker ...` must actually RUN.

    Unbounded, this composition is what probes a containerised cluster; broken,
    it returns 127 and the caller reports `PREFLIGHT FAILED: PostgreSQL is not
    reachable` on a cluster that is perfectly healthy - refusing to launch on
    exactly the host class the docker arm exists for.
    """
    bindir = tmp_path / "bin"
    _stub(bindir, "docker", _TRACE_STUB)
    if with_timeout and not _link_real(bindir, "timeout"):
        pytest.skip("no `timeout` binary on this host to exercise that arm")

    p = _sh(bindir,
            'pg_bounded_run 20 pg_run_client docker pg-one db.example role 5544 pg_isready -q')
    argv = p.stdout.splitlines()

    assert p.returncode == 0, (
        f"the bounded client dispatch must run and pass its status through; got "
        f"{p.returncode}, stderr={p.stderr!r}"
    )
    assert argv[:4] == ["docker", "exec", "-i", "pg-one"], (
        f"the bound must not disturb the argv the client dispatch builds; got {argv}"
    )
    assert argv[4:] == ["pg_isready", "-U", "role", "-q"], f"got {argv}"


@pytest.mark.parametrize("with_timeout", [True, False])
def test_bounded_run_passes_through_the_client_dispatch_refusal(tmp_path, with_timeout):
    """A mode with no client surface refuses with 3 THROUGH the bound too.

    3 must reach the caller unchanged: flattened to 127 it becomes an
    exec failure, and every caller reads a non-zero, non-124 status as a factual
    "not reachable" verdict about the cluster.
    """
    bindir = tmp_path / "bin"
    _stub(bindir, "psql", _TRACE_STUB)
    if with_timeout and not _link_real(bindir, "timeout"):
        pytest.skip("no `timeout` binary on this host to exercise that arm")

    p = _sh(bindir, 'pg_bounded_run 20 pg_run_client tcp-only "" h u "" psql')
    assert p.returncode == 3, (
        f"the client dispatch's own refusal (3) must survive the bound; got {p.returncode}"
    )
    assert p.stdout.strip() == "", f"nothing may be executed; got {p.stdout!r}"


# --------------------------------------------------------------------------- #
# Prose guards
#
# The repo's recorded failure mode is a guard bound to ONE phrasing that goes
# green while missing every other. These therefore scan the WHOLE plugin tree,
# normalize whitespace so a line wrap cannot hide a sentence, and match a VERB
# SET rather than a single spelling. A qualifier allowance keeps a sentence that
# FORBIDS the behavior from being mistaken for one that documents it.
# --------------------------------------------------------------------------- #
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

_DEGRADE_VERBS = (
    "degrade", "degrades", "degraded", "degrading",
    "downgrade", "downgrades", "downgraded", "downgrading",
    "fall back", "falls back", "fell back", "falling back", "fallback",
    "borrows", "borrow",
)
# A sentence that FORBIDS or NEGATES the behavior is exactly what we want to keep.
_NEGATED = (
    "never", "no longer", "instead of", "refus",  # refuse/refuses/refusing/refusal
    "must not", "cannot", "can never", "not degrade", "stop", "deleted",
)


def _md_files():
    return sorted(PLUGIN.rglob("*.md"))


def _stale_claim_corpus():
    """Every file a stale degrade claim can hide in.

    Deliberately wider than `plugins/**/*.md`: `hooks/*.json` is the machine-
    readable registration an agent trusts most, `hooks/*.sh` and the plugin's
    `scripts/**` carry the headers and docstrings that JUSTIFY the rule (the
    allocator's own module docstring is the likeliest home for a superseded
    degrade claim of all), and the repo's own `tests/*.py` section banners are
    read as the contract. Every one of those classes was unscanned - which is
    precisely where a claim survives the rule change that deleted it. This file is
    excluded: a guard must be able to NAME what it bans.
    """
    self_path = Path(__file__).resolve()
    files = set(PLUGIN.rglob("*.md"))
    files |= set((PLUGIN / "hooks").glob("*.json")) | set((PLUGIN / "hooks").glob("*.sh"))
    files |= set((PLUGIN / "scripts").rglob("*.py")) | set((PLUGIN / "scripts").rglob("*.sh"))
    files |= set((ROOT / "tests").glob("*.py"))
    return sorted(p for p in files if p.resolve() != self_path)


def test_stale_claim_corpus_covers_the_historical_blind_spots():
    """Discovery floor: silently dropping a file class would make the scans below
    vacuous - which is how the blind spot went unnoticed in the first place."""
    corpus = _stale_claim_corpus()
    for required in (
        PLUGIN / "hooks" / "hooks.json",
        PLUGIN / "hooks" / "enforce-teardown.sh",
        PLUGIN / "scripts" / "lib" / "allocator.py",
        PLUGIN / "scripts" / "lib" / "pg_mode.sh",
        PLUGIN / "docs" / "reference" / "INSTANCE-ALLOCATION.md",
    ):
        assert required in corpus, f"{required.name} must be scanned"
    assert any(p.suffix == ".py" and p.parent.name == "tests" for p in corpus), (
        "the repo's own tests/*.py must be scanned"
    )
    assert Path(__file__).resolve() not in corpus, (
        "the scanning file itself must be excluded - it has to be able to NAME the "
        "claims it bans"
    )


def _sentences(text: str):
    """Whitespace-normalized sentences. Joining wrapped lines first is the whole
    point: the defect prose spanned four lines, so a per-line scan missed it."""
    import re
    flat = " ".join(text.split())
    return [s for s in re.split(r"(?<=[.;:!?])\s+", flat) if s]


def _sentence_windows(text: str, size: int = 2):
    """Overlapping windows of `size` consecutive sentences.

    A single-sentence scan cannot see a claim split across a boundary ("an
    ephemeral request may be serialised instead. It then becomes exclusive."), and
    that is the cheapest way for the banned claim to survive a guard. Windows are
    what make the ban depend on MEANING spanning the text rather than on where the
    author happened to put a full stop.
    """
    sents = _sentences(text)
    if not sents:
        return []
    if len(sents) < size:
        return [" ".join(sents)]
    return [" ".join(sents[i:i + size]) for i in range(len(sents) - size + 1)]


def _degrade_claim_hits(text: str):
    """Windows of `text` that CLAIM an ephemeral lease turns into an exclusive one.

    The single predicate both the whole-tree scan and its efficacy floor use, so
    the scan can never be narrowed without a test that says so.
    """
    hits = []
    for window in _sentence_windows(text):
        low = window.lower()
        if "ephemeral" not in low or "exclusive" not in low:
            continue
        if not any(v in low for v in _DEGRADE_VERBS):
            continue
        if any(n in low for n in _NEGATED):
            continue
        hits.append(window)
    return hits


def test_no_prose_documents_an_ephemeral_to_exclusive_degrade():
    """No agent-facing prose may describe `ephemeral` turning into `exclusive`.

    That behavior is DELETED, not merely discouraged: an agent that reads a doc
    saying the allocator "degrades ephemeral to exclusive" will handle a mode it
    can no longer receive, and - worse - will trust that a non-isolated lease is a
    normal, expected outcome. Stale text is deleted, never annotated.

    Scanned over the WIDE corpus (`_stale_claim_corpus`) and over two-sentence
    WINDOWS: the previous single-file-class, single-sentence version could not see
    a claim in a hook, a script docstring or a test banner, nor one worded across a
    full stop.
    """
    offenders = []
    for path in _stale_claim_corpus():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for hit in _degrade_claim_hits(text):
            offenders.append(f"{path.relative_to(ROOT)}: {hit[:240]}")
    assert not offenders, (
        "prose still documents the deleted ephemeral -> exclusive degrade:\n  "
        + "\n  ".join(offenders)
    )


def test_the_degrade_scan_sees_a_claim_split_across_a_sentence_boundary():
    """Efficacy floor for the scan above, driven on synthetic text.

    A whole-tree scan that currently finds nothing proves nothing about its own
    reach - the repo's recorded failure mode is exactly a guard that goes green
    while missing every phrasing but one. These cases pin what the predicate MUST
    catch and what it must leave alone, and they fail the moment the window or the
    verb set is narrowed back.
    """
    split = ("An ephemeral request may be serialised instead. It then falls back to "
             "an exclusive lease on the declared database.")
    assert _degrade_claim_hits(split), (
        "a degrade claim worded across a full stop must still be caught"
    )
    one_sentence = "The allocator degrades an ephemeral request to an exclusive lease."
    assert _degrade_claim_hits(one_sentence), "the single-sentence shape must still be caught"
    negated = ("An ephemeral request NEVER degrades to an exclusive lease. It refuses "
               "with exit 6, 7, 8 or 9 instead.")
    assert not _degrade_claim_hits(negated), (
        "a sentence that FORBIDS the behavior is what we want to keep, not a finding"
    )
    unrelated = "The raw client drop is a fallback used only when the venv is unavailable."
    assert not _degrade_claim_hits(unrelated), (
        "a fallback that has nothing to do with lease modes must not be a finding"
    )


def test_ephemeral_ok_key_is_gone_everywhere():
    """`ephemeral_ok` was a documented catalog key that NOTHING ever read, wrote,
    or cached - the plugin's documented-mechanism-never-reached defect class. One
    fact needs one name: the real capability check is a live query, so the phantom
    key must not survive anywhere to be mistaken for it."""
    self_path = Path(__file__).resolve()
    hits = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or ".git/" in str(path) or path.suffix in (".pyc",):
            continue
        rel = str(path.relative_to(ROOT))
        # Skip what is not committed source: the venv, pytest's own cache (it
        # stores test NAMES, including this guard's), and release history.
        if rel.startswith((".venv/", ".pytest_cache/")) or rel == "CHANGELOG.md":
            continue
        # This guard must be allowed to NAME the token it bans; CHANGELOG.md is
        # release history, which records what was removed and is never read as a
        # live instruction.
        if path.resolve() == self_path:
            continue
        try:
            if "ephemeral_ok" in path.read_text(encoding="utf-8"):
                hits.append(str(path.relative_to(ROOT)))
        except (UnicodeDecodeError, OSError):
            continue
    assert not hits, f"the phantom `ephemeral_ok` key still appears in: {hits}"


def test_no_prose_hands_a_human_a_bare_libpq_privilege_probe():
    """No prose may instruct a raw `psql`/`createuser` privilege probe.

    Both are absent on an entire host class (Postgres in a container), so such an
    instruction fails for exactly the users who need the answer - and its failure
    reads as "the role lacks the privilege", which is the false negative this whole
    change removes. The capability is auto-detected instead.
    """
    import re
    probe = re.compile(r"\b(psql|createuser)\b[^.\n]{0,80}(rolcreatedb|--createdb|CREATEDB)", re.I)
    offenders = []
    for path in _md_files():
        for sentence in _sentences(path.read_text(encoding="utf-8")):
            if probe.search(sentence) and not any(n in sentence.lower() for n in _NEGATED):
                offenders.append(f"{path.relative_to(ROOT)}: {sentence[:200]}")
    assert not offenders, (
        "prose still tells someone to probe CREATEDB with a raw client binary:\n  "
        + "\n  ".join(offenders)
    )


def test_docs_do_not_call_docker_optional_for_postgres():
    """`run_mode` describes ODOO; `db_run_mode` describes POSTGRES. Calling docker
    "optional - only for run_mode=docker" told users docker was irrelevant to their
    containerised cluster, when it is REQUIRED to reach any client binary there."""
    import re
    pattern = re.compile(r"docker.{0,40}optional.{0,40}run_mode\s*=\s*docker", re.I)
    offenders = [
        str(p.relative_to(ROOT))
        for p in list(_md_files()) + sorted((PLUGIN / "scripts").rglob("*.sh"))
        if pattern.search(" ".join(p.read_text(encoding="utf-8").split()))
    ]
    assert not offenders, (
        f"docker is REQUIRED when Postgres is containerised, whatever run_mode says: {offenders}"
    )


# --------------------------------------------------------------------------- #
# The bound must hold when the callee has DESCENDANTS - the only shape that
# actually occurs in production.
#
# Every real callee is reached through at least one intermediate shell: the
# FUNCTION arm re-enters bash, and `pg_run_client` then forks psql. Signalling the
# direct child alone leaves the grandchild alive holding the caller's stdout pipe,
# and `out="$(pg_bounded_run ...)"` cannot return until that pipe closes - so a 2s
# bound waited for libpq's full TCP timeout and then delivered the LATE bytes
# alongside status 124.
#
# MEASURED before the fix, with this exact stub shape: rc=124, elapsed 8s for a 2s
# bound, `LATE` in the captured output, grandchild still running afterwards.
# --------------------------------------------------------------------------- #
# The child exits immediately; the GRANDCHILD holds stdout and outlives it, which
# is what a killed-parent-but-live-client looks like.
_GRANDCHILD_STUB = (
    'marker="$1"\n'
    '( sleep 8; echo "LATE-OUTPUT"; echo survived > "$marker" ) &\n'
    'sleep 8\n'
)


@pytest.mark.parametrize("with_timeout", [True, False])
def test_bounded_run_bounds_a_callee_whose_grandchild_outlives_it(tmp_path, with_timeout):
    """Three properties at once, because they are one failure: the bound holds in
    WALL CLOCK, the caller's captured output carries nothing from the timed-out
    tree, and no descendant is left running to keep the pipe open."""
    bindir = tmp_path / "bin"
    _stub(bindir, "spawner", _GRANDCHILD_STUB)
    _link_real(bindir, "sleep")
    if with_timeout:
        if not _link_real(bindir, "timeout"):
            pytest.skip("no `timeout` binary on this host to exercise that arm")
    marker = tmp_path / "grandchild-marker"
    # Captured with $( ), exactly as _psql_scalar and pg_hba_file_path capture it -
    # the capture is what turns a surviving grandchild into an unbounded wait.
    probe = ('out="$(pg_bounded_run 2 "$1" "$2")" || rc=$?\n'
             'echo "RC=${rc:-0}"\n'
             'echo "OUT=[$out]"\n')
    started = time.monotonic()
    p = _sh(bindir, probe, bindir / "spawner", marker, timeout=45)
    elapsed = time.monotonic() - started

    assert "RC=124" in p.stdout, (
        f"the bound must report 124; got {p.stdout!r} stderr={p.stderr!r}")
    assert elapsed < 6.0, (
        f"a 2s bound took {elapsed:.1f}s - the wait is ending when the GRANDCHILD "
        f"gives up, not when the bound elapses")
    assert "OUT=[]" in p.stdout, (
        f"a timed-out tree must deliver NOTHING to the caller's variable, or 124 "
        f"arrives beside a value the caller may use; got {p.stdout!r}")
    # Give the grandchild the rest of its own lifetime; if it was never signalled
    # it writes the marker.
    time.sleep(8.5)
    assert not marker.exists(), (
        "a descendant of the timed-out callee is still running after the bound - it "
        "holds the caller's pipe, and on a real probe it is a live psql against the "
        "cluster the caller was told nothing about")


@pytest.mark.parametrize("with_timeout", [True, False])
def test_pg_hba_file_path_is_bounded_like_every_other_question(tmp_path, with_timeout):
    """`SHOW hba_file` is on the MUTATING path (48-db-local-auth.sh asks it before it
    edits anything) and on the advisory path. Unbounded, a daemon that wedges AFTER
    the earlier `docker ps` probe succeeded left `apply` never returning at all -
    and pg_mode.sh's own header promises every question here honours the bound.

    "Could not ask in time" is exit 3 with nothing on stdout: the same answer this
    function already gives for a server that refused, because both mean the path to
    edit is unknown and nothing may be guessed."""
    bindir = tmp_path / "bin"
    # A stub that SLEEPS rather than spins: a bound that is broken makes this test
    # fail by TIMING OUT, and a busy-loop survivor would then burn a core for the
    # rest of the suite. Not answering is the property under test either way.
    _stub(bindir, "docker", "sleep 120\n")
    _link_real(bindir, "sleep")
    if with_timeout and not _link_real(bindir, "timeout"):
        pytest.skip("no `timeout` binary on this host to exercise that arm")
    started = time.monotonic()
    p = _sh(bindir,
            'out="$(pg_hba_file_path docker "$1" "" "$2" "")" || rc=$?\n'
            'echo "RC=${rc:-0}"\n'
            'echo "OUT=[$out]"\n',
            "pg-stub", "odoo",
            env_extra={"ODOO_AI_PG_PROBE_TIMEOUT": "2", "ODOO_AI_PG_KILL_GRACE": "1"},
            timeout=45)
    elapsed = time.monotonic() - started
    assert "RC=3" in p.stdout, (
        f"a question that could not be asked must be exit 3; got {p.stdout!r}")
    assert "OUT=[]" in p.stdout, (
        f"and nothing may be emitted for a path nobody answered; got {p.stdout!r}")
    assert elapsed < 12.0, (
        f"a 2s bound took {elapsed:.1f}s - this call is not bounded at all")
