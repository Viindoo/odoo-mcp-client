"""Guard: the generated `odoo.conf` is keyed by the RESOURCE, and the sweep that reclaims it runs.

Business rules protected here:

GT1 - **a spin-up's conf file is bounded by the set of declared instances, not by the number of
  launches.** `50-instance-spinup.sh` materialises an `odoo.conf` and hands it to the server as
  `-c <conf>`, which keeps the file open for the server's ENTIRE lifetime - so "delete it after
  launch" is not an available fix. When the name was minted per invocation (`mktemp` under the
  ambient temp dir) it therefore had no owner on any exit path: only the poll-timeout branch ever
  removed one, and every SUCCESSFUL spin-up left a file behind forever. The fix is the uniqueness
  KEY, not another `rm`: the allocator already guarantees `(db_name, http port)` is exclusive per
  live instance, so `$ODOO_AI_HOME/conf/<db>-<port>.conf` is a complete identity and every re-spin
  of the same instance overwrites in place.

  These tests assert on the FILESYSTEM after real script runs - never on stdout wording - because
  the leak was a filesystem fact that stdout described correctly the whole time.

GT2 - **the sweep is actually REACHED, from BOTH of its named callers.** This repo's dominant
  defect is correct code that nothing ever calls: the reclamation mechanism used to live inside
  `55-instance-ops.sh`, where `50-instance-spinup.sh` could not reach it (neither script sources
  the other), which is exactly why a second artifact family grew with no reclamation at all. So
  this guard is PARAMETRIZED over the two entry points - `50-instance-spinup.sh apply` and a
  `55-instance-ops.sh` build - and a sweep wired into only one of them turns the other parameter
  red. A sweeper defined in the lib and called from neither turns BOTH red.

  The sweep's two safety properties are asserted at the same time, because a sweep that deletes
  a LIVE instance's open conf is worse than no sweep: the lease-registry reachability guard
  (a leased db survives regardless of age) and the fail-closed posture (an unreadable registry
  prunes NOTHING).

Retention SSOT - **the bound is declared in exactly ONE place.** `_LOG_RETENTION_DAYS` owns the
  number. A prose copy of it lies the day someone changes the lease, and this repo has been bitten
  repeatedly by a restatement outliving its definition - so any block of documentation or code
  that talks about the sweeper must NAME the constant and must not spell a day count.

Offline: no PostgreSQL, no real Odoo, no network. odoo-bin / python / curl / pg_isready are stubs.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import textwrap
import time
from pathlib import Path
from shutil import which

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
PLUGINS_DIR = ROOT / "plugins"
STEP50 = PLUGIN / "scripts" / "setup-steps" / "50-instance-spinup.sh"
STEP55 = PLUGIN / "scripts" / "setup-steps" / "55-instance-ops.sh"
STATE_RECLAIM = PLUGIN / "scripts" / "lib" / "state_reclaim.sh"

DB = "odoo_test"
PORT = 18069
ALT_PORT = 18070

requires_bash = pytest.mark.skipif(which("bash") is None, reason="bash not available")

# The sweep's own entry points, named the way the scripts name them. Parametrizing over BOTH is
# the whole point of GT2 - see the module docstring.
ENTRY_POINTS = ("50-instance-spinup.sh apply", "55-instance-ops.sh init")


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------


def _write_stub(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


class Sandbox:
    """A hermetic state root + an ambient temp dir nothing is allowed to write to.

    `TMPDIR` points at `self.ambient_tmp`, which starts empty and MUST stay empty: that is the
    observable form of "the plugin has no ambient-temp destination". Pointing it at a dir of our
    own (rather than trusting the host's) is what makes the count assertion meaningful.
    """

    def __init__(self, tmp_path: Path, *, port: int = PORT, db: str = DB):
        self.tmp = tmp_path
        self.home = tmp_path / "state-root"
        self.ambient_tmp = tmp_path / "ambient-tmp"
        self.ambient_tmp.mkdir(parents=True, exist_ok=True)
        self.bindir = tmp_path / "stub-bin"
        self.marker = tmp_path / "server-answers.marker"
        self.launch_log = tmp_path / "odoo-launch.log"
        self.port = port
        self.db = db
        self.pids: list[int] = []

        real_py3 = which("python3") or "/usr/bin/python3"
        # One fake python covering every call step 50 / step 55 makes through it:
        #   `<py> <odoo-bin> --version`      -> the venv/preflight gate, always passes
        #   `<py> <odoo_db.py> preflight`    -> the DB-auth preflight, always passes (it is
        #                                       otherwise only bounded, which just costs time)
        #   `<py> <odoo-bin> --stop-after-init ...`
        #                                    -> a BUILD (step 55): print the completion marker
        #                                       `_install_confirmed` requires, then exit 0
        #   `<py> <odoo-bin> ...`            -> a LISTENER launch (step 50): record it, start
        #                                       answering HTTP 200, stay alive with a clean pid
        #   anything else                    -> real python3 (instances_io.py, allocator.py, ...)
        # The --stop-after-init split is the real odoo-bin's own behavioural split, which is why
        # one stub can serve both callers without either test bending the other's contract.
        self.fake_py = tmp_path / "fake-py-bin" / "python"
        _write_stub(
            self.fake_py,
            textwrap.dedent(f"""\
                if [[ "$2" == "--version" ]]; then echo "Odoo Server 17.0"; exit 0; fi
                if [[ "$2" == "preflight" ]]; then exit 0; fi
                case "$1" in
                    *odoo-bin*)
                        echo "odoo-bin launched $*" >> "{self.launch_log}"
                        if [[ "$*" == *--stop-after-init* ]]; then
                            echo "Modules loaded."
                            exit 0
                        fi
                        : > "{self.marker}"
                        exec sleep 20 ;;
                esac
                exec {real_py3} "$@"
            """),
        )
        self.odoo_bin = tmp_path / "odoo-bin"
        _write_stub(self.odoo_bin, "exit 0\n")

        # curl answers 200 only once a launch has happened. That keeps every `apply` on the
        # SOURCE spin-up branch (which is where the conf is written) instead of short-circuiting
        # on the "already up" pre-check, and it resets by deleting one marker file.
        _write_stub(
            self.bindir / "curl",
            f'if [[ -e "{self.marker}" ]]; then echo "200"; else echo "000"; fi\n',
        )
        _write_stub(self.bindir / "pg_isready", "exit 0\n")

        fake_addons = tmp_path / "fake-core" / "addons"
        fake_addons.mkdir(parents=True, exist_ok=True)
        self.addons = fake_addons
        self.toml = tmp_path / "instances.toml"
        self.toml.write_text(
            textwrap.dedent(f"""\
                [[instance]]
                series = "17.0"
                python = "{self.fake_py}"
                http_port = {port}
                db_name = "{db}"
                db_host = "localhost"
                db_user = "odoo"
                run_mode = "source"
                addons_path = "{fake_addons}"
            """),
            encoding="utf-8",
        )

    # -- env ---------------------------------------------------------------
    @property
    def conf_dir(self) -> Path:
        return self.home / "conf"

    def env(self) -> dict:
        env = dict(os.environ)
        env["PATH"] = f"{self.bindir}{os.pathsep}{env.get('PATH', '')}"
        env["ODOO_AI_INSTANCES"] = str(self.toml)
        env["ODOO_AI_HOME"] = str(self.home)
        env["TMPDIR"] = str(self.ambient_tmp)
        env["SPINUP_TIMEOUT"] = "3"
        env["ODOO_AI_PG_PROBE_TIMEOUT"] = "1"
        env["ODOO_BIN"] = str(self.odoo_bin)
        env.pop("ODOO_PG_PASSWORD", None)
        return env

    # -- runs --------------------------------------------------------------
    def apply(self, *extra: str) -> subprocess.CompletedProcess:
        """One `50-instance-spinup.sh apply` (the listener spin-up path)."""
        res = subprocess.run(
            ["bash", str(STEP50), "apply", "--version", "17.0", *extra],
            capture_output=True, text=True, env=self.env(), timeout=60,
        )
        self._collect_pids(res)
        return res

    def init(self, *extra: str) -> subprocess.CompletedProcess:
        """One `55-instance-ops.sh init` (a build - the other named sweep caller)."""
        res = subprocess.run(
            [
                "bash", str(STEP55), "init",
                "--db", self.db,
                "--python", str(self.fake_py),
                "--addons", str(self.addons),
                "--modules", "base",
                *extra,
            ],
            capture_output=True, text=True, env=self.env(), timeout=60,
        )
        self._collect_pids(res)
        return res

    def run_entry_point(self, entry_point: str, *extra: str) -> subprocess.CompletedProcess:
        if entry_point.startswith("50-"):
            return self.apply(*extra)
        return self.init(*extra)

    def reset_server(self) -> None:
        """Make the next `apply` a fresh spin-up again: reap the launched process and stop
        answering HTTP 200. Models a host whose previous listener died - the case the leak
        accumulated on."""
        self.reap()
        self.marker.unlink(missing_ok=True)
        self.launch_log.unlink(missing_ok=True)

    def _collect_pids(self, res: subprocess.CompletedProcess) -> None:
        for m in re.finditer(r"pid:? (\d+)", res.stdout + res.stderr):
            self.pids.append(int(m.group(1)))

    def reap(self) -> None:
        for pid in self.pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        self.pids = []

    # -- assertions helpers ------------------------------------------------
    def confs(self) -> list[str]:
        if not self.conf_dir.is_dir():
            return []
        return sorted(p.name for p in self.conf_dir.iterdir() if p.is_file())

    def ambient_files(self) -> list[str]:
        return sorted(str(p.relative_to(self.ambient_tmp)) for p in self.ambient_tmp.rglob("*"))


@pytest.fixture
def sandbox(tmp_path):
    sb = Sandbox(tmp_path)
    try:
        yield sb
    finally:
        sb.reap()


def _seed_conf(conf_dir: Path, name: str, *, days_old: float) -> Path:
    conf_dir.mkdir(parents=True, exist_ok=True)
    path = conf_dir / name
    path.write_text("[options]\nseeded = 1\n", encoding="utf-8")
    stamp = time.time() - days_old * 86400
    os.utime(path, (stamp, stamp))
    return path


# A pid no process can hold, paired with a host name that is deliberately NOT this host.
#
# This is load-bearing, not cosmetic. `allocator.py`'s gc pass - which `acquire` runs, and which
# `50-instance-spinup.sh` reaches through `_register_shared` - SIGTERMs the process GROUP recorded
# on a lease it judges stale, and its recycled-pid guard only engages when the row carries a
# `pid_started` fingerprint. A hand-seeded row naming a LIVE local pid and no fingerprint therefore
# gets that pid's whole process group killed: seeding this fixture with `os.getpid()` kills the
# pytest process itself, mid-run, with no failure message. Both fields below independently defeat
# that (wrong host -> no signal; dead pid -> nothing to signal), which keeps this fixture about the
# ONE thing it is for: the db names the sweep's reachability guard reads.
_UNREACHABLE_PID = 2 ** 30
_FOREIGN_HOST = "seeded-not-this-host"


def _seed_leases(home: Path, db_names) -> Path:
    """A lease registry shaped like allocator.py's (`{"leases": [...]}`)."""
    runtime = home / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    registry = runtime / "leases.json"
    registry.write_text(
        json.dumps(
            {
                "leases": [
                    {
                        "token": f"seed-{name}",
                        "db_name": name,
                        "series": "17.0",
                        "mode": "shared",
                        "ports": [8070],
                        "owner": {"pid": _UNREACHABLE_PID, "host": _FOREIGN_HOST},
                        "created_db": False,
                        "drop_on_release": False,
                    }
                    for name in db_names
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return registry


# ---------------------------------------------------------------------------
# GT1 - the conf path is keyed by the resource, and nothing lands in the ambient temp dir
# ---------------------------------------------------------------------------


@requires_bash
def test_two_spinups_of_one_instance_leave_exactly_one_conf(sandbox):
    """GT1(1)+(2) - the SAME instance spun up twice leaves ONE conf, and the ambient temp dir
    stays empty.

    This is the leak, stated as a filesystem fact: under the old per-invocation `mktemp` name the
    second run added a second file and neither was ever removed on the success path.
    """
    first = sandbox.apply()
    assert first.returncode == 0, f"first apply failed:\n{first.stdout}\n{first.stderr}"
    sandbox.reset_server()
    second = sandbox.apply()
    assert second.returncode == 0, f"second apply failed:\n{second.stdout}\n{second.stderr}"

    assert sandbox.ambient_files() == [], (
        "a spin-up must write NOTHING to the ambient temp dir ($TMPDIR): a file there is not "
        "namespaced per project, is wiped on reboot, and has no owner on any exit path. Found: "
        f"{sandbox.ambient_files()}"
    )
    assert sandbox.confs() == [f"{DB}-{PORT}.conf"], (
        "two spin-ups of the SAME declared instance must leave exactly ONE conf, named "
        f"<db>-<port>.conf, under $ODOO_AI_HOME/conf/. Found: {sandbox.confs()}"
    )


@requires_bash
def test_conf_key_includes_the_port_so_a_second_port_gets_its_own_file(sandbox):
    """GT1(3) - the key is `(db, port)`, not `db` alone.

    Two live instances of the same database on different ports are legal (the allocator issues
    the pair), and they must NOT share one conf file - that would make one launch rewrite the
    other's live, open configuration. A `db`-only key passes the "one file per instance" test
    above while silently reintroducing exactly that collision.
    """
    assert sandbox.apply().returncode == 0
    sandbox.reset_server()
    res = sandbox.apply("--http-port", str(ALT_PORT))
    assert res.returncode == 0, f"apply on the alternate port failed:\n{res.stdout}\n{res.stderr}"

    assert sandbox.confs() == sorted([f"{DB}-{PORT}.conf", f"{DB}-{ALT_PORT}.conf"]), (
        "the conf key must include the http port: the same db on a second port needs its OWN "
        f"conf file, or one live instance overwrites another's open config. Found: {sandbox.confs()}"
    )
    assert sandbox.ambient_files() == []


@requires_bash
def test_respinning_an_instance_overwrites_its_conf_in_place(sandbox):
    """GT1(4) - the conf holds the MOST RECENT run's config, written by truncation.

    Two independent failure modes are excluded at once: an append (which would leave two
    `[options]` sections and a server reading a stale first one) and a stale keep (which would
    silently launch the next run against the previous run's flags).
    """
    assert sandbox.apply().returncode == 0
    conf = sandbox.conf_dir / f"{DB}-{PORT}.conf"
    first_text = conf.read_text(encoding="utf-8")
    assert "gevent_port" not in first_text

    sandbox.reset_server()
    res = sandbox.apply("--gevent-port", "18072", "--gevent-port-key", "gevent_port")
    assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    text = conf.read_text(encoding="utf-8")
    assert "gevent_port = 18072" in text, (
        "the conf must carry the MOST RECENT run's configuration - a re-spin that leaves the "
        f"previous run's file untouched launches against stale flags. Got:\n{text}"
    )
    assert text.count("[options]") == 1, (
        "the conf must be written by TRUNCATION, not appended to: a second [options] section "
        f"means the server may read a stale first one. Got:\n{text}"
    )
    assert sandbox.confs() == [f"{DB}-{PORT}.conf"]


@requires_bash
def test_conf_dir_follows_the_state_root_home_fallback(sandbox, tmp_path):
    """GT1(6), the MUST-NOT-CATCH control - BOTH state-root resolutions are correct.

    With `ODOO_AI_HOME` unset the resolver falls back to `$HOME/.odoo-ai`. That is a valid
    resolution, so the conf landing there must NOT read as a leak; a guard that only recognises
    the explicit env var would fail every host that does not set it.
    """
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    env = sandbox.env()
    env.pop("ODOO_AI_HOME")
    env["HOME"] = str(fake_home)
    res = subprocess.run(
        ["bash", str(STEP50), "apply", "--version", "17.0"],
        capture_output=True, text=True, env=env, timeout=60,
    )
    sandbox._collect_pids(res)
    assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"

    fallback_conf_dir = fake_home / ".odoo-ai" / "conf"
    assert [p.name for p in fallback_conf_dir.iterdir()] == [f"{DB}-{PORT}.conf"], (
        "with ODOO_AI_HOME unset the conf must land under the $HOME/.odoo-ai fallback - the "
        f"resolver's other correct answer. Found: {list(fallback_conf_dir.glob('*'))}"
    )
    assert sandbox.ambient_files() == []


# ---------------------------------------------------------------------------
# GT2 - the sweep is reached, from BOTH callers, and it is safe
# ---------------------------------------------------------------------------


@requires_bash
@pytest.mark.parametrize("entry_point", ENTRY_POINTS)
def test_sweep_is_reached_from_this_entry_point(sandbox, entry_point):
    """GT2 - running EITHER entry point reclaims a stale, unleased conf, and only that one.

    Three seeded files separate the three possible reasons a file may be kept:
      - `retired_db-8069.conf`  stale + unleased -> must be GONE (the sweep ran at all)
      - `live_db-8070.conf`     stale + LEASED   -> must SURVIVE (reachability guard; its
                                                    instance may still hold the file open)
      - `new_db-8071.conf`      fresh            -> must SURVIVE (age guard; deleting a conf a
                                                    concurrent run just wrote is the worst case)
    A sweep wired into only one of the two scripts turns the OTHER parameter red; a sweeper
    defined in the lib and called from neither turns BOTH red.
    """
    conf_dir = sandbox.conf_dir
    retired = _seed_conf(conf_dir, "retired_db-8069.conf", days_old=20)
    leased = _seed_conf(conf_dir, "live_db-8070.conf", days_old=20)
    fresh = _seed_conf(conf_dir, "new_db-8071.conf", days_old=0)
    _seed_leases(sandbox.home, ["live_db"])

    res = sandbox.run_entry_point(entry_point)
    assert res.returncode == 0, f"{entry_point} failed:\n{res.stdout}\n{res.stderr}"

    assert not retired.exists(), (
        f"{entry_point} must reclaim a stale, unleased conf - the sweep is not reached from this "
        f"entry point (this is the 'correct code nothing invokes' failure mode). Conf dir: "
        f"{sandbox.confs()}"
    )
    assert leased.exists(), (
        "a conf whose database the lease registry still references must SURVIVE regardless of "
        "age: `-c <conf>` holds the file open for the server's whole lifetime, so unlinking it "
        "pulls the configuration out from under a live listener"
    )
    assert fresh.exists(), (
        "a conf inside the retention window must survive - an age-blind sweep would delete the "
        "file a concurrent spin-up just wrote"
    )


@requires_bash
@pytest.mark.parametrize("entry_point", ENTRY_POINTS)
def test_sweep_proceeds_when_no_lease_registry_exists_at_all(sandbox, entry_point):
    """GT2 probe 7, must stay GREEN - an ABSENT registry means nothing was ever leased here.

    That is a legitimate host state (a plain spin-up never registers a lease), and it must not
    disable reclamation - otherwise the sweep silently does nothing on exactly the hosts that
    accumulate the most.
    """
    retired = _seed_conf(sandbox.conf_dir, "retired_db-8069.conf", days_old=20)
    assert not (sandbox.home / "runtime" / "leases.json").exists()

    res = sandbox.run_entry_point(entry_point)
    assert res.returncode == 0, f"{entry_point} failed:\n{res.stdout}\n{res.stderr}"
    assert not retired.exists(), (
        "with no lease registry on the host the sweep must still proceed - 'nothing was ever "
        "leased' is an ANSWER, not a reason to prune nothing"
    )


@requires_bash
@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses the unreadable-file check")
@pytest.mark.parametrize("entry_point", ENTRY_POINTS)
def test_sweep_fails_closed_on_an_unreadable_lease_registry(sandbox, entry_point):
    """GT2 probe 6 - a registry that EXISTS but cannot be read must prune NOTHING.

    The distinction is the whole safety argument: "no registry" means nothing is leased, while
    "unreadable registry" means no artifact can be PROVEN unleased. Failing open there would
    unlink live listeners' open confs on any host with a permissions problem.
    """
    retired = _seed_conf(sandbox.conf_dir, "retired_db-8069.conf", days_old=20)
    registry = _seed_leases(sandbox.home, ["live_db"])
    registry.chmod(0o000)
    try:
        res = sandbox.run_entry_point(entry_point)
        assert res.returncode == 0, f"{entry_point} failed:\n{res.stdout}\n{res.stderr}"
        assert retired.exists(), (
            "an unreadable lease registry must make the sweep prune NOTHING (fail closed) - "
            "otherwise a permissions problem becomes data loss on a live instance's open conf"
        )
    finally:
        registry.chmod(0o600)


@requires_bash
@pytest.mark.parametrize("entry_point", ENTRY_POINTS)
def test_sweep_never_touches_a_neighbouring_family_or_a_subdirectory(sandbox, entry_point):
    """The sweep is scoped: one directory deep, and only the globs its caller passed.

    Both swept families share one directory tree under the state root, so a sweeper that
    recursed or that matched every file would reclaim another family's live artifacts.
    """
    conf_dir = sandbox.conf_dir
    keep_other_ext = _seed_conf(conf_dir, "retired_db-8069.notconf", days_old=20)
    nested = conf_dir / "nested"
    keep_nested = _seed_conf(nested, "retired_db-8069.conf", days_old=20)

    res = sandbox.run_entry_point(entry_point)
    assert res.returncode == 0, f"{entry_point} failed:\n{res.stdout}\n{res.stderr}"
    assert keep_other_ext.exists(), (
        "the sweep must only match the globs its caller passed - a file of another family in the "
        "same dir is not this caller's to reclaim"
    )
    assert keep_nested.exists(), (
        "the sweep must stay one directory deep (-maxdepth 1) - recursing would reach state the "
        "caller never claimed"
    )


# ---------------------------------------------------------------------------
# Retention SSOT - the bound is declared once, and documented by NAME
# ---------------------------------------------------------------------------

RETENTION_CONST = "_LOG_RETENTION_DAYS"
_RETENTION_ASSIGN_RE = re.compile(rf"^\s*{RETENTION_CONST}\s*=", re.MULTILINE)

# The sweeper's public surface. A block of text that names any of these is TALKING ABOUT the
# mechanism, and is therefore where a restatement of its bound would land.
_SWEEPER_TOKENS = ("prune_stale_run_artifacts", "_prune_stale_logs", "state_reclaim.sh")

# Numeric retention bounds, in every notation this repo actually uses for one: `14 days`,
# `14-day`, `30d`, `-mtime +14`, `-mmin +43200`.
_DAY_LITERAL_RE = re.compile(
    r"\b\d+\s*-?\s*days?\b|\b\d+\s*d\b|-m(?:time|min)\s+\+?\s*\d+", re.IGNORECASE
)

_SKIP_DIR_PARTS = {"__pycache__", ".git", "node_modules", ".pytest_cache"}


def _iter_plugin_texts():
    for path in sorted(PLUGINS_DIR.rglob("*")):
        if not path.is_file() or any(p in _SKIP_DIR_PARTS for p in path.parts):
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue


def blocks_with_lines(text: str) -> list[tuple[int, str]]:
    """Split `text` into blank-line-separated blocks, each tagged with its first line number.

    Blank-line blocks are the natural unit for BOTH markdown (a paragraph / table / list) and
    shell (a comment header plus the code it documents), which is why the same scan can cover
    prose and script without a per-language parser.
    """
    out, start, buf = [], 1, []
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.strip() == "":
            if buf:
                out.append((start, "\n".join(buf)))
                buf = []
            start = lineno + 1
        else:
            if not buf:
                start = lineno
            buf.append(line)
    if buf:
        out.append((start, "\n".join(buf)))
    return out


def restated_bounds(text: str, relpath: str = "<text>") -> list[str]:
    """Blocks of `text` that discuss the sweeper AND spell a numeric bound. Empty == compliant."""
    findings = []
    for lineno, block in blocks_with_lines(text):
        if not any(token in block for token in _SWEEPER_TOKENS):
            continue
        for m in _DAY_LITERAL_RE.finditer(block):
            findings.append(f"{relpath}:{lineno}: restates a bound as {m.group(0)!r}")
    return findings


def test_retention_bound_is_declared_in_exactly_one_place():
    """One assignment, in the file that owns the mechanism. Two would drift on the first change."""
    sites = [
        str(path.relative_to(ROOT))
        for path, text in _iter_plugin_texts()
        if _RETENTION_ASSIGN_RE.search(text)
    ]
    assert sites == [str(STATE_RECLAIM.relative_to(ROOT))], (
        f"{RETENTION_CONST} must be assigned in exactly ONE file - the sweeper's own lib - so "
        f"there is a single bound to change. Assignment sites found: {sites}"
    )
    value = re.search(rf"{RETENTION_CONST}\s*=\s*(\d+)", STATE_RECLAIM.read_text(encoding="utf-8"))
    assert value, f"{RETENTION_CONST} must be assigned an integer day count"
    assert int(value.group(1)) > 0, "a retention bound of 0 days would reclaim live artifacts"


def test_no_file_restates_the_retention_bound_as_a_number():
    """Anything that documents the sweeper must name the CONSTANT, never copy its value.

    This is value-INDEPENDENT on purpose: it fires on `14-day` today and equally on a stale
    `21-day` after someone changes the lease, which is the failure a "does the number still
    match?" check cannot see (it goes green the moment both copies agree, and stays green while
    the second copy rots).
    """
    findings = []
    for path, text in _iter_plugin_texts():
        if path == STATE_RECLAIM:
            continue  # the owner is allowed - indeed required - to state the number
        findings.extend(restated_bounds(text, str(path.relative_to(ROOT))))
    assert findings == [], (
        f"the retention bound's SSOT is {RETENTION_CONST} in "
        f"{STATE_RECLAIM.relative_to(ROOT)}. Reference the constant by name instead of copying "
        "its value - a literal copy lies the day the bound changes:\n" + "\n".join(findings)
    )


def test_the_sweeper_is_documented_by_the_name_of_its_bound():
    """The positive half: deleting the pointer must not be a way to pass the rule above.

    Searched by CONTENT across every prose file - not pinned to one section - so the
    documentation may move.
    """
    naming = [
        str(path.relative_to(ROOT))
        for path, text in _iter_plugin_texts()
        if path != STATE_RECLAIM and path.suffix == ".md"
        for lineno, block in blocks_with_lines(text)
        if any(token in block for token in _SWEEPER_TOKENS) and RETENTION_CONST in block
    ]
    assert naming, (
        f"at least one prose file must document the Tier-1 sweep BY THE NAME of its bound "
        f"({RETENTION_CONST}), so a reader can find the number without a copy of it existing in "
        f"prose. No such block found - the pointer was deleted rather than kept."
    )


# ---------------------------------------------------------------------------
# Retention-SSOT probe corpus - the committed red-before-green proof.
# ---------------------------------------------------------------------------

_BOUND_MUST_CATCH = [
    ("hyphenated day count", "Reclaimed by `prune_stale_run_artifacts`: a 14-day mtime bound."),
    ("spaced day count", "`prune_stale_run_artifacts` keeps a conf for 14 days, then unlinks it."),
    ("stale day count after a lease change", "`state_reclaim.sh` retains logs for 21 days."),
    ("compact d notation", "`_prune_stale_logs` bound: 30d, lease-guarded."),
    ("find flag copied into prose", "The sweep runs `find ... -mtime +14` in `state_reclaim.sh`."),
    ("minutes flavour", "`prune_stale_run_artifacts` uses -mmin +20160 under the lease guard."),
]

_BOUND_MUST_NOT_CATCH = [
    (
        "names the constant instead of the number",
        "Reclaimed by `prune_stale_run_artifacts` (`state_reclaim.sh`): its "
        "`_LOG_RETENTION_DAYS` mtime bound PLUS a lease-registry reachability guard.",
    ),
    (
        "a day bound in a block that is NOT about the sweeper",
        "| `worklog/<run-or-slug>/` | every multi-agent run | 30d | decision log stays useful |",
    ),
    (
        "the sweeper named with no bound claim at all",
        "prune_stale_run_artifacts \"$(odoo_ai_state_root)/conf\" '*.conf'",
    ),
]


@pytest.mark.parametrize("shape,block", _BOUND_MUST_CATCH, ids=[s for s, _ in _BOUND_MUST_CATCH])
def test_bound_guard_catches_every_restatement_shape(shape, block):
    assert restated_bounds(block, "probe.md"), (
        f"the retention-SSOT guard let a {shape} through: {block!r}. A guard that knows one "
        f"notation lets the other five restate the bound freely."
    )


@pytest.mark.parametrize(
    "shape,block", _BOUND_MUST_NOT_CATCH, ids=[s for s, _ in _BOUND_MUST_NOT_CATCH]
)
def test_bound_guard_leaves_compliant_blocks_alone(shape, block):
    assert restated_bounds(block, "probe.md") == [], (
        f"the retention-SSOT guard fired on compliant text ({shape}): {block!r} -> "
        f"{restated_bounds(block, 'probe.md')}. Unrelated TTL tables must stay untouched, or the "
        f"guard becomes a reason to delete the rule."
    )


def test_block_splitter_keeps_a_comment_header_with_the_code_it_documents():
    """Discovery floor for the splitter: if it split per line, no block would ever contain both
    a sweeper mention and its bound, and both rules above would report clean forever."""
    text = "# uses prune_stale_run_artifacts\n# with a 14-day bound\ncall_it\n\nunrelated 30d\n"
    assert restated_bounds(text, "probe.sh"), (
        "a comment header and the bound it states must land in the SAME block"
    )
    assert len(blocks_with_lines(text)) == 2, blocks_with_lines(text)
