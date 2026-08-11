"""Behavior tests for scripts/setup-steps/48-db-local-auth.sh.

This step edits a file it does not own, inside a cluster it does not own, to
remove a password requirement. So what needs protecting is not "it wrote
something" but the four properties that make that acceptable:

  * the address it trusts is DISCOVERED, and is the gateway a published-port
    connection actually arrives from - never loopback, which is already present in
    every stock image and already dead;
  * privilege and safety are probed BEFORE anything is touched, so a refusal can
    never leave a half-applied change;
  * a port published anywhere but loopback refuses, because trusting the gateway
    trusts the host;
  * success is claimed only after RECONNECTING - the two rungs that read the
    server's opinion of its own config can explain a failure, never prove one.

Everything is CONSTRUCTED: `docker` and `sudo` are made unreachable and replaced
by recording stubs, the "container filesystem" is a tmp directory, and the
instance's interpreter is a stub whose preflight verdict the test pins. No Docker
daemon, no PostgreSQL, no privilege - so a CI runner with no daemon and a dev host
with eight containers must produce identical results.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
STEP48 = PLUGIN / "scripts" / "setup-steps" / "48-db-local-auth.sh"
SETUP_CMD = "/odoo-ai-agents:odoo-setup"

requires_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")

# The binaries whose ABSENCE some cases depend on. Absence is constructed, never
# inherited: a runner image that preinstalls docker and a dev box that does not
# must run the SAME test.
_SHADOWED = ("docker", "sudo", "podman")

STOCK_HBA = """\
# PostgreSQL Client Authentication Configuration File
# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host all all all scram-sha-256
"""

MANAGED_BEGIN = "# BEGIN odoo-ai-agents managed block - generated, do not edit by hand"


# --------------------------------------------------------------------------- #
# PATH construction
# --------------------------------------------------------------------------- #
def _shadowed_path(tmp_path: Path, *stub_dirs: Path) -> str:
    """A PATH with `docker`/`sudo` provably absent and everything else intact.

    Every ambient PATH entry is re-exposed through one symlink farm with the
    shadowed names left out (first hit wins, so ambient precedence survives).
    python3, bash, coreutils and `timeout` stay reachable and identical to a real
    run - only the binaries a case is making a claim about are gone. A whitelist
    instead would silently change WHICH code path runs the moment the script
    starts using one more tool.
    """
    farm = tmp_path / "path-shadowed"
    farm.mkdir(exist_ok=True)
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        try:
            names = os.listdir(entry)
        except OSError:
            continue
        for name in names:
            if name in _SHADOWED:
                continue
            link = farm / name
            if link.is_symlink() or link.exists():
                continue
            src = Path(entry) / name
            if src.is_dir() or not os.access(src, os.X_OK):
                continue
            try:
                link.symlink_to(src)
            except OSError:
                continue
    path = os.pathsep.join([*(str(d) for d in stub_dirs), str(farm)])
    for name in _SHADOWED:
        found = shutil.which(name, path=path)
        if found and Path(found).parent not in [Path(d) for d in stub_dirs]:
            raise AssertionError(
                f"fixture is not hermetic: {name!r} still resolves to {found}")
    assert shutil.which("python3", path=path), "python3 must stay reachable"
    return path


# --------------------------------------------------------------------------- #
# The stub `docker`: a container whose filesystem is a tmp directory
# --------------------------------------------------------------------------- #
_DOCKER_STUB = r'''
import json, os, re, shutil, subprocess, sys

CONF = json.load(open(os.environ["STUB_DOCKER_CONF"]))
with open(os.environ["STUB_DOCKER_LOG"], "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\n")

argv = sys.argv[1:]
hba = CONF["hba"]


def out(text):
    sys.stdout.write(text)
    return 0


def inspect_format(tmpl):
    if ".Config.Env" in tmpl:
        return out("".join("%s\n" % e for e in CONF.get("env", [])))
    if "IPv6Gateway" in tmpl:
        return out("".join("%s\n\n" % g for g in CONF.get("gateways", [])))
    if "$n, $v := .NetworkSettings.Networks" in tmpl:
        return out("".join("%s\n" % n for n in CONF.get("networks", [])))
    if ".IPAM.Config" in tmpl:
        return out("".join("%s\n" % g for g in CONF.get("net_gateways", [])))
    if ".NetworkSettings.Ports" in tmpl:
        return out("".join("%s %s\n" % (p, ip) for p, ip in CONF.get("ports", [])))
    if "range .Mounts" in tmpl:
        return out("".join("%s %s %s\n" % tuple(m) for m in CONF.get("mounts", [])))
    return 1


def denied(what):
    # The shape a real cluster refuses a superuser-only question with. It ANSWERED:
    # the wording is what separates "not permitted" from "not available".
    sys.stderr.write("ERROR:  permission denied to examine %s\n" % what)
    return 1


def psql(args):
    sql = args[-1]
    user = args[args.index("-U") + 1] if "-U" in args else ""
    # Superuser-only by default, because that is what a stock cluster IS:
    # hba_file is GUC_SUPERUSER_ONLY and pg_reload_conf / pg_hba_file_rules are
    # restricted too. A fixture that let any role ask could not tell whether the
    # step asks as a role the cluster will actually answer.
    supers = CONF.get("superusers", ["postgres"])
    su_only = CONF.get("superuser_only", True)
    permitted = (not su_only) or user in supers
    if "rolsuper" in sql:
        return out("t\n" if user in supers else "f\n")
    if "SHOW hba_file" in sql:
        if not CONF.get("hba_path_ok", True):
            return 1
        if not permitted:
            return denied('"hba_file"')
        return out(hba + "\n")
    if "pg_reload_conf" in sql:
        if not permitted:
            return denied("function pg_reload_conf")
        rc = CONF.get("reload_rc", 0)
        return out("t\n") if rc == 0 else rc
    if not CONF.get("hba_view", True):
        return 1
    if "pg_hba_file_rules" in sql and (not permitted or CONF.get("rules_denied")):
        # rules_denied models a cluster where the view EXISTS but SELECT on it was
        # revoked - the case that is not the same fact as "PostgreSQL is too old".
        return denied("view pg_hba_file_rules")
    body = open(hba).read() if os.path.exists(hba) else ""
    if "error IS NOT NULL" in sql:
        key = "errors_after" if MANAGED in body else "errors_before"
        return out("%d\n" % CONF.get(key, 0))
    if "auth_method = 'trust'" in sql:
        live = CONF.get("rule_live", "auto")
        if live is not True and live is not False:
            m_addr = re.search(r"address = '([^']+)'", sql)
            m_user = re.search(r"'([^']+)' = ANY", sql)
            live = False
            for line in body.splitlines():
                f = line.split()
                if (len(f) == 5 and f[0] == "host" and f[4] == "trust"
                        and f[2] == (m_user.group(1) if m_user else "")
                        and f[3].split("/")[0] == (m_addr.group(1) if m_addr else "")):
                    live = True
        return out("1\n" if live else "0\n")
    return out("\n")


MANAGED = "# BEGIN odoo-ai-agents managed block"

if argv[:1] == ["ps"]:
    rc = CONF.get("ps_rc", 0)
    if rc == 0 and "--format" in argv:
        # `docker ps --filter publish=<port> --format '{{.Names}}'` - which
        # containers publish the declared db_port. Empty by default: a host with a
        # native client and NO container is a real host class too.
        out("".join("%s\n" % n for n in CONF.get("publishers", [])))
    sys.exit(rc)

if argv[:1] == ["inspect"]:
    tmpl = argv[argv.index("--format") + 1] if "--format" in argv else ""
    sys.exit(inspect_format(tmpl))

if argv[:2] == ["network", "inspect"]:
    tmpl = argv[argv.index("--format") + 1] if "--format" in argv else ""
    sys.exit(inspect_format(tmpl))

if argv[:1] == ["exec"]:
    # Flags belong BEFORE the container name and the command's own argv AFTER it:
    # `-i` for a piped stdin, `-e NAME` to forward a variable by name (how the
    # client dispatch hands a password to libpq without putting it in the process
    # table). Stopping at the first non-flag is what keeps a `test -e <path>` in the
    # COMMAND from being eaten as a docker flag.
    i = 1
    while i < len(argv) and argv[i].startswith("-"):
        i += 2 if argv[i] == "-e" else 1
    rest = argv[i + 1:]                  # everything after the container name
    if rest[:2] == ["test", "-e"]:
        sys.exit(0 if os.path.exists(rest[2]) else 1)
    if rest[0] == "cat":
        sys.exit(0 if out(open(rest[1]).read()) == 0 else 1)
    if rest[:2] == ["cp", "-p"]:
        shutil.copy2(rest[2], rest[3])
        sys.exit(0)
    if rest[0] == "psql":
        sys.exit(psql(rest))
    if rest[0] == "sh":
        script = rest[2]
        if "test -w" in script:
            sys.exit(0 if CONF.get("writable", True) else 1)
        if not CONF.get("writable", True):
            sys.exit(1)
        # RUN THE REAL SCRIPT against the tmp "container filesystem" - cp -p, the
        # byte-count gate and the rename all execute as written. Re-implementing
        # the write in Python instead (open(hba,"w")) verified the step's argv
        # string and nothing else: mode preservation passed because Python keeps an
        # existing file's mode, not because `cp -p` ran, and no partial write could
        # ever be modelled.
        data = sys.stdin.buffer.read()
        cut = CONF.get("truncate_write_at")
        client_rc = CONF.get("write_client_rc")
        if cut is not None:
            # The bound elapsed mid-transfer: `timeout` killed the local docker
            # CLIENT, and docker does not kill the process inside the container, so
            # the in-container reader sees EOF after `cut` bytes and the host sees
            # only a non-zero status (124).
            data = data[:cut]
            if client_rc is None:
                client_rc = 124
        p = subprocess.run(["sh", "-c", script, *rest[3:]], input=data)
        sys.exit(client_rc if client_rc is not None else p.returncode)
    sys.exit(0)

sys.exit(1)
'''


def _write_stub(path: Path, body: str, shebang="#!/bin/sh\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(shebang + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _fake_venv_python(bindir: Path, preflight_rc=0, state=None):
    """The instance's DECLARED interpreter, answering `odoo_db.py preflight` only.

    The step must ask THIS interpreter (not a client binary, not pg_isready) for
    rung 3, because it is the route a build takes. Its verdict is pinned per case
    so "the reload worked" and "Odoo can now connect" stay distinguishable.
    """
    if state is None:
        state = {0: "ok", 8: "denied", 9: "unreachable"}.get(preflight_rc, "unknown")
    return _write_stub(bindir / "fake_python", (
        'if [ "$(basename "$1")" = "odoo_db.py" ] && [ "$2" = "preflight" ]; then\n'
        '  echo "DB_AUTH=%s"; echo "DB_AUTH_WHY=stub"; exit %d\n'
        'fi\n'
        'exit 0\n' % (state, preflight_rc)))


def _instances_toml(path: Path, py: Path, *, run_mode="docker", container="pg-stub",
                    user="odoo", extra=""):
    body = (
        '[[instance]]\n'
        'series = "17.0"\n'
        'addons_path = ["/does/not/matter"]\n'
        'run_mode = "source"\n'
        'http_port = 8069\n'
        'db_name = "probe_db"\n'
        'db_host = "localhost"\n'
        f'db_user = "{user}"\n'
        'db_port = 5432\n'
        f'python = "{py}"\n'
        'odoo_root = "/does/not/matter"\n'
    )
    if run_mode:
        body += f'db_run_mode = "{run_mode}"\n'
    if container:
        body += f'db_container = "{container}"\n'
    body += extra
    path.write_text(body, encoding="utf-8")
    return path


class Fixture:
    """One constructed world: a stub docker, a stub interpreter, a catalog, a file."""

    def __init__(self, tmp_path, **conf):
        self.tmp = tmp_path
        self.bindir = tmp_path / "stubbin"
        self.bindir.mkdir(parents=True, exist_ok=True)
        self.cdir = tmp_path / "container-fs"
        self.cdir.mkdir(exist_ok=True)
        self.hba = self.cdir / "pg_hba.conf"
        self.hba.write_text(conf.pop("hba_text", STOCK_HBA), encoding="utf-8")
        self.hba.chmod(0o600)
        self.log = tmp_path / "docker-argv.log"
        self.log.write_text("", encoding="utf-8")
        self.with_docker = conf.pop("with_docker", True)
        self.with_sudo = conf.pop("with_sudo", True)
        self.run_mode = conf.pop("run_mode", "docker")
        self.container = conf.pop("container", "pg-stub")
        self.user = conf.pop("user", "odoo")
        self.preflight_rc = conf.pop("preflight_rc", 0)
        self.toml_extra = conf.pop("toml_extra", "")
        self.conf = {
            "hba": str(self.hba),
            "gateways": ["172.30.9.1"],
            "networks": ["a-network"],
            "net_gateways": [],
            "ports": [["5432/tcp", "127.0.0.1"]],
            "mounts": [["volume", str(self.cdir), "pgdata-vol"]],
            "writable": True,
            "ps_rc": 0,
            "reload_rc": 0,
            "errors_before": 0,
            "errors_after": 0,
        }
        self.conf.update(conf)
        self.conf_path = tmp_path / "docker-conf.json"
        self.conf_path.write_text(json.dumps(self.conf), encoding="utf-8")

        if self.with_docker:
            _write_stub(self.bindir / "docker",
                        f'exec "{sys.executable}" "{tmp_path}/docker_stub.py" "$@"\n')
            (tmp_path / "docker_stub.py").write_text(_DOCKER_STUB, encoding="utf-8")
        self.sudo_log = tmp_path / "sudo-calls.log"
        if self.with_sudo:
            _write_stub(self.bindir / "sudo", f'echo "$@" >> "{self.sudo_log}"\nexit 0\n')

        self.py = _fake_venv_python(self.bindir, preflight_rc=self.preflight_rc)
        self.toml = _instances_toml(
            tmp_path / "instances.toml", self.py,
            run_mode=self.run_mode, container=self.container, user=self.user,
            extra=self.toml_extra)

    def env(self, **extra):
        env = dict(os.environ)
        env["PATH"] = _shadowed_path(self.tmp, self.bindir)
        env["STUB_DOCKER_CONF"] = str(self.conf_path)
        env["STUB_DOCKER_LOG"] = str(self.log)
        env["ODOO_AI_INSTANCES"] = str(self.toml)
        env["ODOO_AI_HOME"] = str(self.tmp / "state")
        env["ODOO_AI_PG_PROBE_TIMEOUT"] = "10"
        env["ODOO_AI_BACKUP_TS"] = "20250101T000000Z"
        env.pop("ODOO_PG_PASSWORD", None)
        env.update(extra)
        return env

    def run(self, *args, **envextra):
        return subprocess.run(
            ["bash", str(STEP48), *args],
            capture_output=True, text=True, env=self.env(**envextra), timeout=120)

    def docker_calls(self):
        return [json.loads(ln) for ln in self.log.read_text().splitlines() if ln.strip()]

    def backups(self):
        return sorted(p.name for p in self.cdir.iterdir() if ".bak" in p.name)

    def managed_lines(self):
        body, out, inside = self.hba.read_text(), [], False
        for ln in body.splitlines():
            if ln.strip() == MANAGED_BEGIN:
                inside = True
                continue
            if ln.strip().startswith("# END odoo-ai-agents"):
                inside = False
                continue
            if inside and ln.strip():
                out.append(ln)
        return out


# --------------------------------------------------------------------------- #
# Guard 16 - the regression that matters most
# --------------------------------------------------------------------------- #
@requires_bash
def test_step_trusts_the_discovered_gateway_and_never_loopback_for_a_container(tmp_path):
    """A published-port connection arrives from the bridge GATEWAY, not loopback.

    Every stock PostgreSQL image already ships `host all all 127.0.0.1/32 trust`,
    and host TCP still demands a password - so an implementation that writes a
    loopback rule for a container produces a change that verifies green on disk and
    fixes nothing. This test fails against exactly that implementation.
    """
    fx = Fixture(tmp_path, gateways=["172.30.9.1"])
    res = fx.run("apply")
    assert res.returncode == 0, res.stdout + res.stderr
    lines = fx.managed_lines()
    assert lines == ["host    all     odoo    172.30.9.1/32    trust"], (
        f"the rule must carry the DISCOVERED gateway; got {lines!r}"
    )
    assert not any("127.0.0.1" in ln for ln in lines), (
        "a loopback rule for a container is a silent no-op"
    )


@requires_bash
def test_step_never_writes_a_wider_rule_than_one_host_for_one_role(tmp_path):
    """The rule is narrow on BOTH axes it can be narrowed on, end to end - not only
    in the transform's unit tests but in what the step actually writes."""
    fx = Fixture(tmp_path, gateways=["172.30.9.1"])
    assert fx.run("apply").returncode == 0
    fields = fx.managed_lines()[0].split()
    assert fields[0] == "host" and fields[1] == "all"
    assert fields[2] == "odoo" and fields[2] != "all"
    assert fields[3].endswith("/32")
    assert fields[4] == "trust"


# --------------------------------------------------------------------------- #
# Guard 17 - rung 2 of the discovery ladder
# --------------------------------------------------------------------------- #
@requires_bash
def test_step_uses_the_network_object_gateway_when_the_container_reports_none(tmp_path):
    """A container on a user-defined network may report no Gateway of its own while
    the network object still declares one. Without rung 2 that host class gets a
    refusal it did not need."""
    fx = Fixture(tmp_path, gateways=[], networks=["compose-net"],
                 net_gateways=["10.44.0.1"])
    res = fx.run("apply")
    assert res.returncode == 0, res.stdout + res.stderr
    assert fx.managed_lines() == ["host    all     odoo    10.44.0.1/32    trust"]


@requires_bash
def test_a_gateway_on_two_networks_yields_one_rule_per_distinct_address(tmp_path):
    """Two attached networks with two DIFFERENT gateways are two real origins, so
    both are authorised - each still a single /32."""
    fx = Fixture(tmp_path, gateways=["172.30.9.1", "10.44.0.1"])
    assert fx.run("apply").returncode == 0
    addrs = sorted(ln.split()[3] for ln in fx.managed_lines())
    assert addrs == ["10.44.0.1/32", "172.30.9.1/32"]


# --------------------------------------------------------------------------- #
# Guard 18 - discovery refuses rather than guessing
# --------------------------------------------------------------------------- #
@requires_bash
def test_step_refuses_and_writes_nothing_when_no_gateway_can_be_discovered(tmp_path):
    """Both rungs silent: a guessed gateway would authorise a stranger AND leave
    Odoo refused, which is strictly worse than authorising nobody."""
    fx = Fixture(tmp_path, gateways=[], networks=[], net_gateways=[])
    before = fx.hba.read_bytes()
    res = fx.run("apply")
    assert res.returncode != 0
    assert fx.hba.read_bytes() == before, "the file must be untouched"
    assert fx.backups() == [], "no backup - nothing was going to be edited"
    out = res.stdout + res.stderr
    assert SETUP_CMD in out
    writes = [c for c in fx.docker_calls() if "sh" in c and any("mv " in a for a in c)]
    assert writes == [], f"no write may be attempted; got {writes!r}"


# --------------------------------------------------------------------------- #
# Guard 19 - the loopback-publish safety gate
# --------------------------------------------------------------------------- #
@requires_bash
@pytest.mark.parametrize("host_ip", ["0.0.0.0", "203.0.113.9", "", "::"])
def test_step_refuses_when_the_published_host_ip_is_not_loopback(tmp_path, host_ip):
    """Trusting the gateway trusts THE HOST. A port published on a routable address
    would extend that trust to anyone who can reach it, so the gate refuses.

    An EMPTY HostIp is docker's own spelling of "every interface" and must be read
    as NON-loopback: reading it as loopback is how a routable publish slips past.
    """
    fx = Fixture(tmp_path, ports=[["5432/tcp", host_ip]])
    before = fx.hba.read_bytes()
    res = fx.run("apply")
    assert res.returncode != 0
    assert fx.hba.read_bytes() == before
    assert fx.backups() == []
    out = res.stdout + res.stderr
    assert "127.0.0.1" in out, "the remedy (re-publish on loopback) must be named"
    assert "ODOO_PG_PASSWORD" in out, "the alternative must be named"
    assert SETUP_CMD in out


@requires_bash
def test_step_refuses_when_where_the_port_is_published_cannot_be_determined(tmp_path):
    """No bindings reported at all is UNKNOWN, and unknown is never read as safe."""
    fx = Fixture(tmp_path, ports=[])
    res = fx.run("apply")
    assert res.returncode != 0
    assert MANAGED_BEGIN not in fx.hba.read_text()
    assert SETUP_CMD in res.stdout + res.stderr


# --------------------------------------------------------------------------- #
# Guard 20 - privilege probing comes FIRST, proven by the absence of a backup
# --------------------------------------------------------------------------- #
@requires_bash
@pytest.mark.parametrize("case", ["docker-absent", "docker-ps-fails", "not-writable",
                                  "no-hba-path"])
def test_step_refuses_before_touching_anything_when_it_lacks_privilege(tmp_path, case):
    """Every privilege failure must refuse with NOTHING touched.

    The backup is the tell: it is the first mutating action in the sequence, so its
    absence proves the probe ran before the edit rather than alongside it. Asserting
    only "the file is unchanged" would also pass for an implementation that backs
    up, tries, fails and rolls back.
    """
    kw = {"docker-absent": {"with_docker": False},
          "docker-ps-fails": {"ps_rc": 1},
          "not-writable": {"writable": False},
          "no-hba-path": {"hba_path_ok": False}}[case]
    fx = Fixture(tmp_path, **kw)
    before = fx.hba.read_bytes()
    res = fx.run("apply")
    assert res.returncode != 0, res.stdout
    assert fx.backups() == [], (
        f"[{case}] a backup was taken, so the edit was attempted before the probe"
    )
    assert fx.hba.read_bytes() == before
    assert SETUP_CMD in res.stdout + res.stderr


@requires_bash
def test_the_write_probe_covers_the_directory_the_atomic_rename_needs(tmp_path):
    """The rename happens in the file's DIRECTORY, so directory write access is part
    of the privilege question - a file-only probe passes and the rename then fails
    after the backup was already taken."""
    fx = Fixture(tmp_path)
    fx.run("apply")
    probes = [c for c in fx.docker_calls()
              if "sh" in c and any("test -w" in a for a in c)]
    assert probes, "the write probe must run"
    script = [a for a in probes[0] if "test -w" in a][0]
    assert "dirname" in script, (
        "the probe must also test the directory the atomic rename needs"
    )


# --------------------------------------------------------------------------- #
# Guard 21 - the native arm advises, and there is no flag that changes that
# --------------------------------------------------------------------------- #
@requires_bash
def test_native_arm_is_advise_only_and_never_runs_sudo(tmp_path):
    """Editing a system cluster's config needs root, this plugin never runs sudo,
    and this arm is the one no observation covers. So it PRINTS the block, the path
    and the reload command, then refuses - a wrong address there costs a printed
    suggestion, not a bad edit."""
    fx = Fixture(tmp_path, run_mode="native", container="")
    before = fx.hba.read_bytes()
    res = fx.run("apply")
    out = res.stdout + res.stderr
    assert res.returncode != 0, "an advisory must not be reported as a completed change"
    assert MANAGED_BEGIN in out, "the exact block must be printed"
    assert "pg_reload_conf" in out, "the reload command must be printed"
    # The literal line the advice prints, not the substring "hba_file" - which also
    # appears in the SQL the step echoes, so the weaker form could pass with no path
    # line at all.
    assert re.search(r"^\s+File: \S", out, re.M), (
        f"the advice must name the file to edit on its own line; got {out!r}")
    assert fx.hba.read_bytes() == before
    assert not fx.sudo_log.exists() or fx.sudo_log.read_text() == "", (
        f"sudo was invoked: {fx.sudo_log.read_text()!r}"
    )
    assert SETUP_CMD in out
    # The alternative that needs NO server-side change must be named here too. A
    # remote or managed cluster reached through a native client cannot be
    # hand-edited by this reader at all, so without this line whether they got a
    # usable answer depended on which client binaries happen to be installed.
    assert "ODOO_PG_PASSWORD" in out, (
        f"the advice must name the no-server-change alternative; got {out!r}")


@requires_bash
@pytest.mark.parametrize("mode,container", [("tcp-only", ""), ("", ""), ("docker", "")])
def test_a_cluster_that_cannot_be_reconfigured_gets_the_explicit_refusal(tmp_path,
                                                                        mode, container):
    """A managed or remote cluster is a first-class outcome, not a dead end: the
    refusal names ODOO_PG_PASSWORD, which needs no server-side change at all."""
    fx = Fixture(tmp_path, run_mode=mode, container=container)
    res = fx.run("apply")
    out = res.stdout + res.stderr
    assert res.returncode != 0
    assert "ODOO_PG_PASSWORD" in out
    assert SETUP_CMD in out
    assert MANAGED_BEGIN not in fx.hba.read_text()


# --------------------------------------------------------------------------- #
# Guard 22 - the backup, and the one that must never be overwritten
# --------------------------------------------------------------------------- #
@requires_bash
def test_step_backs_up_before_editing_and_never_overwrites_an_existing_backup(tmp_path):
    """The FIRST backup is the state the cluster was in before this plugin ever
    touched it, and that is the one worth keeping. A second edit must add a backup,
    never replace one - and the file's mode must survive both."""
    fx = Fixture(tmp_path)
    assert fx.run("apply").returncode == 0
    first = fx.backups()
    assert len(first) == 1, f"one backup after the first edit; got {first}"
    pristine = (fx.cdir / first[0]).read_text()
    assert MANAGED_BEGIN not in pristine, "the backup must hold the PRE-edit content"
    assert (fx.cdir / first[0]).stat().st_mode & 0o777 == 0o600, (
        "the backup must carry the original's mode"
    )

    # External configuration management rewrote pg_hba.conf and the managed block
    # is gone (the residual the design names explicitly). The next apply edits
    # again - and must not clobber the pristine copy.
    fx.hba.write_text(STOCK_HBA, encoding="utf-8")
    fx.hba.chmod(0o600)
    assert fx.run("apply", ODOO_AI_BACKUP_TS="20250202T000000Z").returncode == 0
    second = fx.backups()
    assert len(second) == 2, f"two distinct timestamped backups; got {second}"
    assert (fx.cdir / first[0]).read_text() == pristine, (
        "the first backup was overwritten - the pre-plugin state is gone"
    )
    assert fx.hba.stat().st_mode & 0o777 == 0o600, "the edited file's mode must survive"


@requires_bash
def test_an_idempotent_reapply_adds_no_backup_and_changes_no_byte(tmp_path):
    """Setup is re-run freely. A no-op run that still took a backup would leave one
    more file in PGDATA on every single run, forever."""
    fx = Fixture(tmp_path)
    assert fx.run("apply").returncode == 0
    after_first = fx.hba.read_bytes()
    assert fx.run("apply").returncode == 0
    assert fx.hba.read_bytes() == after_first, "the second apply must change nothing"
    assert len(fx.backups()) == 1, f"no second backup for a no-op; got {fx.backups()}"


# --------------------------------------------------------------------------- #
# Guard 23 - the anti-assumption guard: verify by RECONNECTING
# --------------------------------------------------------------------------- #
@requires_bash
def test_step_fails_loudly_when_the_post_reload_preflight_still_reports_denied(tmp_path):
    """The two rungs that read pg_hba_file_rules can only ever explain a failure.

    Only reconnecting over Odoo's own connection proves the thing that was wanted,
    so a `denied` there must fail the step - never leave the user believing
    passwordless auth is enabled when it is not, which is precisely the failure mode
    the loopback rule already demonstrates.
    """
    fx = Fixture(tmp_path, preflight_rc=8)
    res = fx.run("apply")
    out = res.stdout + res.stderr
    assert res.returncode != 0, "a failed reconnect must not exit 0"
    assert "rung 3 FAILED" in res.stderr, (
        "the failing rung must be NAMED on the failure channel; got "
        f"{res.stderr!r}")
    assert "rung 3 ok" not in out, "success must not be claimed anywhere"
    # SCOPED to the failure output. `apply` prints an unconditional
    # "revert with: ..." line on stdout for every cluster it edited, BEFORE this
    # rung runs - so asserting on the combined output passed even with the
    # rung-3 failure's own way-back deleted, which is the one place a user is
    # left with an edited pg_hba.conf and no named way out.
    assert re.search(r"Undo with\s+'[^']*revert'", res.stderr), (
        f"the rung-3 failure itself must name the way back; got {res.stderr!r}")


@requires_bash
@pytest.mark.parametrize("rc", [1, 10])
def test_an_undeterminable_reconnect_is_never_read_as_success(tmp_path, rc):
    """Exit 1 (undeterminable) and 10 (that interpreter cannot import odoo) say
    NOTHING about the connection. Treating either as proof is how a step comes to
    claim a change worked without evidence."""
    fx = Fixture(tmp_path, preflight_rc=rc)
    res = fx.run("apply")
    out = res.stdout + res.stderr
    assert res.returncode != 0, f"exit {rc} must not be read as success"
    # The SPECIFIC observable, not just a non-zero: a test that only asserts
    # "refused" cannot fail for the reason it names, so any other refusal on the
    # way - a probe, the write, the reload - would keep it green.
    assert "rung 3 FAILED" in res.stderr, (
        f"the reconnect must be the rung that refused; got {res.stderr!r}")
    assert f"(exit {rc})" in res.stderr, (
        f"the undeterminable code must be REPORTED, not swallowed; got {res.stderr!r}")
    assert "rung 3 ok" not in out, "an undeterminable answer must claim nothing"


@requires_bash
def test_step_fails_when_the_running_server_does_not_report_the_new_rule(tmp_path):
    """Bytes on disk are not a live rule. If the server has not re-read the file,
    the step must say so rather than report the write as the outcome."""
    fx = Fixture(tmp_path, rule_live=False)
    res = fx.run("apply")
    assert res.returncode != 0
    assert "does not parse a trust rule" in res.stderr, (
        "rung 2 must be the rung that refused, and it must say WHAT the server "
        f"did not report; got {res.stderr!r}")
    assert "rung 2 ok" not in res.stdout + res.stderr


@requires_bash
def test_step_fails_when_the_edit_added_a_parse_error(tmp_path):
    """A pg_hba.conf the server cannot parse is worse than one that refuses us:
    compare against the PRE-edit baseline so a file that was already broken is not
    blamed on this step."""
    fx = Fixture(tmp_path, errors_before=0, errors_after=1)
    res = fx.run("apply")
    assert res.returncode != 0
    assert "parse error" in res.stderr, (
        f"the rung that refused must be named; got {res.stderr!r}")
    # Scoped to the failure channel - see the rung-3 test above for why the
    # combined output cannot prove this.
    assert "Revert with:" in res.stderr, (
        f"this failure must name the way back itself; got {res.stderr!r}")


@requires_bash
def test_an_old_cluster_without_the_rules_view_degrades_rather_than_faking_a_rung(
        tmp_path):
    """pg_hba_file_rules is PostgreSQL 10+. On an older cluster rungs 1 and 2 are
    SKIPPED and said to be skipped; rung 3 still decides, because it needs no view
    at all."""
    fx = Fixture(tmp_path, hba_view=False, writable=True)
    res = fx.run("apply")
    # `SHOW hba_file` is answered before the view is consulted, so the step gets far
    # enough to say WHICH rung it could not run.
    out = res.stdout + res.stderr
    # DEGRADES means it still succeeds. The old `"SKIPPED" in out or returncode != 0`
    # accepted refusing - the exact regression the test's own name forbids - via the
    # right-hand disjunct.
    assert res.returncode == 0, (
        f"an old cluster must not be refused, only degraded; got {out!r}")
    assert "rung 1 SKIPPED" in out and "rung 2 SKIPPED" in out, (
        f"both rungs must SAY they were skipped; got {out!r}")
    assert "not available on this cluster" in out, (
        "the reason must be the VIEW's absence - not a permission problem, which "
        f"is a different remedy; got {out!r}")
    assert "rung 3 ok" in out, (
        f"rung 3 needs no view at all, so it must still decide; got {out!r}")


# --------------------------------------------------------------------------- #
# Guard 24 - every refusal names the one command that fixes it
# --------------------------------------------------------------------------- #
@requires_bash
@pytest.mark.parametrize("case,kw", [
    ("no-gateway", {"gateways": [], "networks": [], "net_gateways": []}),
    ("routable-publish", {"ports": [["5432/tcp", "0.0.0.0"]]}),
    ("no-publish-info", {"ports": []}),
    ("docker-absent", {"with_docker": False}),
    ("docker-ps-fails", {"ps_rc": 1}),
    ("not-writable", {"writable": False}),
    ("native", {"run_mode": "native", "container": ""}),
    ("tcp-only", {"run_mode": "tcp-only", "container": ""}),
])
def test_every_step_refusal_names_the_setup_command(tmp_path, case, kw):
    """Asserted across EVERY refusal path, on the literal command name rather than
    on a sentence: a guard bound to one phrasing goes green while missing the rest."""
    fx = Fixture(tmp_path, **kw)
    res = fx.run("apply")
    assert res.returncode != 0, f"[{case}] must refuse"
    assert SETUP_CMD in res.stdout + res.stderr, f"[{case}] must name {SETUP_CMD}"


# --------------------------------------------------------------------------- #
# revert, and the contract with the catalog
# --------------------------------------------------------------------------- #
@requires_bash
def test_revert_restores_the_original_bytes_and_reloads(tmp_path):
    fx = Fixture(tmp_path)
    original = fx.hba.read_bytes()
    assert fx.run("apply").returncode == 0
    assert fx.hba.read_bytes() != original
    assert fx.run("revert").returncode == 0
    assert fx.hba.read_bytes() == original, "revert must be exact, not close"
    reloads = [c for c in fx.docker_calls() if any("pg_reload_conf" in a for a in c)]
    assert len(reloads) >= 2, "the revert must reload too, or the old rules stay live"


@requires_bash
def test_revert_of_an_untouched_cluster_is_a_no_op(tmp_path):
    fx = Fixture(tmp_path)
    original = fx.hba.read_bytes()
    res = fx.run("revert")
    assert res.returncode == 0
    assert fx.hba.read_bytes() == original
    assert fx.backups() == []


@requires_bash
def test_the_step_never_writes_the_instance_catalog_or_a_password(tmp_path):
    """This step declares nothing and stores nothing. The catalog is INPUT, and no
    credential may appear in any file it writes - the whole point of the design is
    that there is no secret at rest."""
    fx = Fixture(tmp_path)
    before = fx.toml.read_bytes()
    res = fx.run("apply", ODOO_PG_PASSWORD="s3ntinel-not-a-real-secret")
    assert res.returncode == 0, res.stdout + res.stderr
    assert fx.toml.read_bytes() == before, "instances.toml was modified"
    assert "s3ntinel" not in fx.hba.read_text()
    assert "s3ntinel" not in res.stdout + res.stderr
    for path in fx.cdir.iterdir():
        assert "s3ntinel" not in path.read_text(errors="replace")


# --------------------------------------------------------------------------- #
# check - read-only, and honest about what it does not know
# --------------------------------------------------------------------------- #
@requires_bash
def test_check_reports_needed_only_when_authentication_is_provably_refused(tmp_path):
    """`check` drives the setup loop, so its exit code decides whether the user is
    asked to run this step. A proven `denied` is the ONE state it fixes."""
    denied = Fixture(tmp_path / "a", preflight_rc=8)
    assert denied.run("check").returncode == 1
    ok = Fixture(tmp_path / "b", preflight_rc=0)
    assert ok.run("check").returncode == 0


@requires_bash
@pytest.mark.parametrize("rc", [9, 1, 10])
def test_check_does_not_nag_for_a_state_this_step_cannot_fix(tmp_path, rc):
    """An unreachable cluster and an undeterminable answer are not this step's
    business: it cannot start a cluster, and undeterminable is never read as a yes
    OR as a no. Reporting them as "needed" would make setup offer a fix that
    changes nothing, run after run."""
    fx = Fixture(tmp_path, preflight_rc=rc)
    res = fx.run("check")
    assert res.returncode == 0, res.stdout + res.stderr
    assert fx.hba.read_text().count(MANAGED_BEGIN) == 0


@requires_bash
def test_check_writes_nothing_at_all(tmp_path):
    fx = Fixture(tmp_path, preflight_rc=8)
    before = fx.hba.read_bytes()
    fx.run("check")
    assert fx.hba.read_bytes() == before
    assert fx.backups() == []
    mutating = [c for c in fx.docker_calls()
                if c[:1] == ["exec"] and any(a in ("cp", "sh") for a in c)]
    assert mutating == [], f"check must not mutate; got {mutating!r}"


@requires_bash
def test_describe_is_one_line(tmp_path):
    fx = Fixture(tmp_path)
    res = fx.run("describe")
    assert res.returncode == 0
    assert len(res.stdout.strip().splitlines()) == 1


@requires_bash
def test_an_unknown_subcommand_refuses_with_the_usage_contract(tmp_path):
    fx = Fixture(tmp_path)
    res = fx.run("frobnicate")
    assert res.returncode == 2
    assert "revert" in res.stderr


# --------------------------------------------------------------------------- #
# Guard 25 - the fix is chosen by where the SERVER runs, not by which client
# binaries this host happens to have.
#
# `pg_mode.sh` decides db_run_mode from PATH and deliberately prefers `native`
# over a co-present container. `postgresql-client` installed PLUS PostgreSQL in a
# container publishing a loopback port is the modal developer host - and it records
# db_run_mode=native. Branching the FIX on that fact sent it to the advisory arm,
# which prints loopback rules that the stock image already has and that a
# published-port connection can never match, so `check` returned 1 forever and
# setup stopped being idempotent.
# --------------------------------------------------------------------------- #
@requires_bash
def test_a_native_client_with_a_containerised_server_takes_the_container_arm(tmp_path):
    """The rule written must be the DISCOVERED gateway, exactly as for a declared
    container - and no loopback rule may be printed as the remedy."""
    fx = Fixture(tmp_path, run_mode="native", container="",
                 publishers=["pg-stub"], gateways=["172.30.9.1"])
    res = fx.run("apply")
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert fx.managed_lines() == ["host    all     odoo    172.30.9.1/32    trust"], (
        f"the container arm must run and write the gateway rule; got {out!r}")
    assert "ADVISE ONLY" not in out, (
        "the advisory arm cannot fix this host, so it must not be taken")
    assert "127.0.0.1/32" not in "\n".join(fx.managed_lines()), (
        "a loopback trust rule for a published port is a silent no-op")
    assert "rung 3 ok" in out, "the reconnect must still be what permits exit 0"


@requires_bash
def test_a_native_client_with_no_container_still_gets_the_advice(tmp_path):
    """The advisory arm is still right for a genuinely native SERVER - the routing
    must key on the container's PRESENCE, not swap one blanket assumption for
    another."""
    fx = Fixture(tmp_path, run_mode="native", container="", publishers=[])
    res = fx.run("apply")
    out = res.stdout + res.stderr
    assert res.returncode != 0
    assert "ADVISE ONLY" in out
    assert MANAGED_BEGIN not in fx.hba.read_text()


@requires_bash
def test_two_containers_publishing_the_port_refuse_to_be_guessed_between(tmp_path):
    """Ambiguity is refused and NAMED, the same way pg_mode.sh refuses it - a
    guessed cluster would be reconfigured for an instance that does not use it."""
    fx = Fixture(tmp_path, run_mode="native", container="",
                 publishers=["pg-one", "pg-two"])
    res = fx.run("apply")
    out = res.stdout + res.stderr
    assert res.returncode != 0
    assert "pg-one" in out and "pg-two" in out, (
        f"both candidates must be named; got {out!r}")
    assert MANAGED_BEGIN not in fx.hba.read_text()


@requires_bash
def test_revert_undoes_what_apply_wrote_on_a_native_client_host(tmp_path):
    """`revert` must follow the same routing as `apply`. Keyed on db_run_mode alone,
    it silently skipped exactly the hosts `apply` had edited - leaving a managed
    block with no way back through this step."""
    fx = Fixture(tmp_path, run_mode="native", container="", publishers=["pg-stub"])
    original = fx.hba.read_bytes()
    assert fx.run("apply").returncode == 0
    assert fx.hba.read_bytes() != original
    assert fx.run("revert").returncode == 0
    assert fx.hba.read_bytes() == original, "revert must be exact, not close"


# --------------------------------------------------------------------------- #
# Guard 26 - "could not ask" is not "failed", in either verb.
# --------------------------------------------------------------------------- #
@requires_bash
def test_an_instance_with_no_interpreter_does_not_fail_the_step_for_its_siblings(
        tmp_path):
    """A `run_mode = "docker"` instance declares no `python` BY DESIGN - compose
    launches Odoo - so its reconnect can never be run from here. `check` already
    treats that as undeterminable; `apply` counted it as unproven, reported FAILURE,
    and advised reverting the block that had just made the sibling instance on the
    SAME cluster work."""
    fx = Fixture(tmp_path, toml_extra=(
        '\n[[instance]]\n'
        'series = "17.0"\n'
        'profile = "compose"\n'
        'addons_path = ["/does/not/matter"]\n'
        'run_mode = "docker"\n'
        'http_port = 8070\n'
        'db_name = "probe_db2"\n'
        'db_host = "localhost"\n'
        'db_user = "odoo"\n'
        'db_port = 5432\n'
        'db_run_mode = "docker"\n'
        'db_container = "pg-stub"\n'
    ))
    res = fx.run("apply")
    out = res.stdout + res.stderr
    assert res.returncode == 0, (
        f"one undeterminable sibling must not fail the whole step; got {out!r}")
    assert "rung 3 ok" in out, "the instance that CAN be proven must be proven"
    assert "rung 3 UNDETERMINED" in out, (
        f"the one that cannot must be reported as such; got {out!r}")
    assert "Undo with" not in res.stderr, (
        "nothing failed, so nothing may advise undoing the change that worked; got "
        f"{res.stderr!r}")
    assert MANAGED_BEGIN in fx.hba.read_text(), "the edit must stand"


# --------------------------------------------------------------------------- #
# Guard 27 - a write that was cut off must not be able to commit, and a failed
# write must never ASSERT the file's state.
#
# The rename is atomic against a crash but NOT against this step's own bound:
# `timeout` kills the local `docker exec` CLIENT, and docker does not kill the
# process it exec'd (moby#9098). The in-container reader then sees EOF, and a
# `cat > tmp && mv tmp target` sequence COMMITS a truncated pg_hba.conf on a
# running cluster - which the postmaster refuses to start on afterwards - while the
# host side reports failure and claims the original is intact.
# --------------------------------------------------------------------------- #
@requires_bash
def test_a_write_cut_off_midway_cannot_commit_a_truncated_pg_hba(tmp_path):
    fx = Fixture(tmp_path, truncate_write_at=40)
    original = fx.hba.read_bytes()
    res = fx.run("apply")
    out = res.stdout + res.stderr
    assert res.returncode != 0, "a write that did not complete is not a success"
    assert fx.hba.read_bytes() == original, (
        "the cluster's pg_hba.conf was PARTIALLY WRITTEN - the postmaster refuses "
        f"to start on that. Got {fx.hba.read_text()!r}")
    # Every original rule must still be there, not just "some bytes".
    for line in ("local   all             all", "scram-sha-256"):
        assert line in fx.hba.read_text(), (
            f"the original rule {line!r} is gone; got {fx.hba.read_text()!r}")
    assert "unchanged" in res.stderr, (
        f"the report must state the file's OBSERVED state; got {res.stderr!r}")
    # The backup is the second escape route and must exist and hold the pre-edit
    # bytes, since the step took one before attempting the write.
    assert [b for b in fx.backups()], "the backup must have been taken first"
    assert (fx.cdir / fx.backups()[0]).read_bytes() == original


@requires_bash
def test_a_write_that_committed_after_the_bound_is_reported_as_committed(tmp_path):
    """The in-container writer can finish AFTER the host gave up. Claiming "the
    original is intact" then is a false statement about a live cluster, and the
    operator would have to disbelieve the message to find the truth."""
    fx = Fixture(tmp_path, write_client_rc=124)
    res = fx.run("apply")
    assert res.returncode != 0
    assert MANAGED_BEGIN in fx.hba.read_text(), (
        "fixture: the in-container write must have completed for this case")
    assert "intended content" in res.stderr, (
        f"the report must say the file DID change; got {res.stderr!r}")
    assert "the original is intact" not in res.stderr, (
        f"asserting an unverified state is the defect itself; got {res.stderr!r}")


@requires_bash
def test_the_write_preserves_the_files_mode_through_cp_p(tmp_path):
    """The temp carries the original's mode BEFORE any content exists, so the
    rename cannot loosen the permissions of a file the cluster reads secrets from.
    Asserted against a mode that is NOT the default, so a fixture that recreates
    the file instead of copying it fails here."""
    fx = Fixture(tmp_path)
    fx.hba.chmod(0o640)
    assert fx.run("apply").returncode == 0
    assert fx.hba.stat().st_mode & 0o777 == 0o640, (
        f"mode became {oct(fx.hba.stat().st_mode & 0o777)}")


# --------------------------------------------------------------------------- #
# Guard 28 - the cluster's own questions are superuser-restricted.
#
# `SHOW hba_file`, `pg_reload_conf()` and `pg_hba_file_rules` are all restricted by
# default, while the DECLARED db_user is routinely a plain LOGIN CREATEDB role -
# the correct way to provision an Odoo role, and exactly this step's target. Asking
# as that role left the file rewritten, the reload refused, and the remedy naming
# the same powerless role, run after run.
# --------------------------------------------------------------------------- #
@requires_bash
def test_the_clusters_own_questions_are_asked_as_a_confirmed_superuser(tmp_path):
    fx = Fixture(tmp_path, env=["POSTGRES_USER=pgadmin"], superusers=["pgadmin"])
    res = fx.run("apply")
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    reloads = [c for c in fx.docker_calls() if any("pg_reload_conf" in a for a in c)]
    assert reloads, "the reload must have been issued"
    for call in reloads:
        assert "pgadmin" in call, (
            "the reload must be asked as the role the CLUSTER named as its "
            f"superuser (POSTGRES_USER), not as the Odoo role; got {call!r}")
    assert "pgadmin" in out, "the role used must be reported"


@requires_bash
def test_no_confirmable_superuser_refuses_before_touching_the_file(tmp_path):
    """With no role that may even ask where pg_hba.conf lives, the step must refuse
    BEFORE editing - and name the privilege, not "start the cluster": the cluster
    answered, so it is running, and restarting it changes nothing."""
    fx = Fixture(tmp_path, superusers=[])
    before = fx.hba.read_bytes()
    res = fx.run("apply")
    out = res.stdout + res.stderr
    assert res.returncode != 0
    assert fx.hba.read_bytes() == before, "nothing may be written"
    assert fx.backups() == [], "no backup either - nothing was attempted"
    assert "superuser" in res.stderr, (
        f"the privilege cause must be NAMED; got {res.stderr!r}")
    assert "RUNNING" in res.stderr, (
        "the message must not send the reader to start a cluster that answered; "
        f"got {res.stderr!r}")
    assert SETUP_CMD in out or "ODOO_PG_PASSWORD" in out, (
        "a refusal must still hand the reader a next step")


@requires_bash
def test_a_rung_that_is_not_permitted_is_not_reported_as_a_missing_view(tmp_path):
    """"This cluster does not have pg_hba_file_rules" and "this role may not read
    it" have DIFFERENT remedies - the first sends a reader to upgrade a cluster that
    is already new enough. The step can tell them apart because the server says
    which one it is."""
    # A superuser exists for the questions that gate the edit, but the view itself
    # is refused for everyone (a cluster with the privilege revoked).
    fx = Fixture(tmp_path, hba_view=False)
    res = fx.run("apply")
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "not available on this cluster" in out, (
        f"a view that answers nothing is reported as absent; got {out!r}")
    assert "not PERMITTED" not in out, (
        f"no permission error was reported, so none may be claimed; got {out!r}")


@requires_bash
def test_a_refused_rules_view_is_reported_as_a_privilege_not_as_an_absence(tmp_path):
    """The other half of Guard 28: the view is THERE and the answer is "you may not
    read it". Reported as an absence, that sends the reader to upgrade a cluster
    that is already new enough - and it silently disables the parse-error
    regression check, which is the one guard standing between this step and an
    unparseable pg_hba.conf."""
    fx = Fixture(tmp_path, rules_denied=True)
    res = fx.run("apply")
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "not PERMITTED" in out, (
        f"the privilege must be named; got {out!r}")
    assert "not available on this cluster" not in out, (
        f"the view answered, so it is not absent; got {out!r}")
    assert "rung 3 ok" in out, "rung 3 needs no view and must still decide"
