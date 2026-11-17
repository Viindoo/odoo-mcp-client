"""Behavior tests for instance_expose / instance_unexpose: a temporary public https address for a
served lease (a Cloudflare Quick Tunnel run by `cloudflared`), driven over stdio against the REAL
server, the REAL allocator and the REAL spin-up script of the stubbed world of
test_odoo_local_mcp_instance.py.

Nothing network-shaped is real: `cloudflared` is a script that prints a trycloudflare-style address
and stays alive, the release source of the binary is a local HTTP server, odoo_db.py is a stub that
logs the parameters it was asked to write. What IS real is what the tools answer for: the process of
the tunnel (it exists while the server runs and is gone after every way the server can stop), the
address every reader of the lease shows, the parameters written to the database, the error codes.

Contracts protected:
  - expose on a served lease starts ONE tunnel to the lease's HTTP port and returns the address;
    a second call returns the same address and starts nothing; an unserved lease is refused with a
    remedy that names instance_serve;
  - while exposed the address is visible in the tool result, the instance handle, instance_status
    and lease_list; the database holds web.base.url = the address and the freeze; unexpose puts the
    local URL back, removes the freeze and stops the tunnel;
  - the tunnel never outlives the server: a release, a park, a server stopped by a plugin version
    that knows nothing of tunnels, a killed server - no tunnel process is left;
  - cloudflared comes from PATH, else the tools directory, else the official release (fetched once);
    a machine that cannot get it receives CLOUDFLARED_UNAVAILABLE with a remedy;
  - a server launched for a lease has Odoo's database manager turned off, in the spelling the
    checkout declares, and nothing in the plugin needs that HTTP surface.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from odoo_local_mcp_harness import LIB_DIR, PLUGIN, McpClient
from test_odoo_local_mcp_instance import (RUN, SERIES, _alive, _err, _lease, _load_lib, _ok,  # noqa: F401
                                          _stub, client, world)
from test_allocator_cross_version import old_alloc, pre_anchor_lib  # noqa: F401

tunnel = _load_lib("tunnel")
FAKE_URL = "https://fake-quick-words.trycloudflare.com"
SPINUP = PLUGIN / "scripts" / "setup-steps" / "50-instance-spinup.sh"


# --------------------------------------------------------------------------- #
# the stubbed machine: a fake cloudflared on PATH, an odoo_db.py that logs set-params
# --------------------------------------------------------------------------- #
def _fake_cloudflared_body(world, tail="exec sleep 300"):
    pids, args = world["work"] / "cloudflared.pids", world["work"] / "cloudflared.args"
    return textwrap.dedent("""\
        if [[ "${1:-}" == "--version" ]]; then echo "cloudflared version 2099.1.0"; exit 0; fi
        echo $$ >> "%(pids)s"
        echo "$*" >> "%(args)s"
        echo "2099-01-01T00:00:00Z INF Requesting new quick Tunnel on trycloudflare.com..."
        echo "2099-01-01T00:00:01Z INF +--------------------------------------------+"
        echo "2099-01-01T00:00:01Z INF |  Your quick Tunnel has been created! Visit it at:  |"
        echo "2099-01-01T00:00:01Z INF |  %(url)s  |"
        %(tail)s
        """ % {"pids": pids, "args": args, "url": FAKE_URL, "tail": tail})


@pytest.fixture
def machine(world):
    """The world plus a cloudflared on PATH and an odoo_db.py stub that logs `set-params`."""
    _stub(world["work"] / "stub-bin" / "cloudflared", _fake_cloudflared_body(world))
    params_log = world["work"] / "params.log"
    fail = world["work"] / "params.fail"
    python = world["python"]
    text = python.read_text(encoding="utf-8")
    text = text.replace('*odoo_db.py)\n', textwrap.dedent("""\
        *odoo_db.py)
                if [[ "${2:-}" == "set-params" ]]; then
                    echo "$*" >> "%s"
                    if [[ -f "%s" ]]; then echo "no route to the database" >&2; exit 1; fi
                    echo "PARAMS_SET=2"; exit 0
                fi
        """) % (params_log, fail), 1)
    assert "set-params" in text
    python.write_text(text, encoding="utf-8")
    world["params_log"], world["params_fail"] = params_log, fail
    world["cf_pids"], world["cf_args"] = world["work"] / "cloudflared.pids", world["work"] / "cloudflared.args"
    yield world
    for pid in _cloudflared_pids(world):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    for record in (world["home"] / "runtime" / "tunnels").glob("*.json"):
        try:
            os.killpg(json.loads(record.read_text())["supervisor_pid"], signal.SIGKILL)
        except (OSError, ValueError, KeyError):
            pass


@pytest.fixture
def xclient(machine):
    """A server whose tunnel start does not probe the (fake) public name over the network."""
    with McpClient(machine["env"](ODOO_AI_TUNNEL_REACHABLE_WAIT_S="0"), machine["work"]) as c:
        c.initialize()
        yield c


def _cloudflared_pids(world):
    path = world["work"] / "cloudflared.pids"
    return [int(x) for x in path.read_text().split()] if path.exists() else []


def _wait_gone(pids, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(_alive(p) for p in pids):
            return True
        time.sleep(0.1)
    return False


def _params(world):
    """[{db, sets, unsets}] for every set-params the stub saw, in order."""
    out = []
    if not world["params_log"].exists():
        return out
    for line in world["params_log"].read_text().splitlines():
        words = line.split()
        sets, unsets, i = {}, [], 0
        while i < len(words):
            if words[i] == "--set":
                key, _eq, value = words[i + 1].partition("=")
                sets[key] = value
                i += 2
            elif words[i] == "--unset":
                unsets.append(words[i + 1])
                i += 2
            else:
                i += 1
        out.append({"db": words[2], "sets": sets, "unsets": unsets})
    return out


def _serve(c, world):
    """A leased, served instance: (lease, instance_serve result)."""
    world["curl_mode"].write_text("boot", encoding="utf-8")
    (world["work"] / "curl-count").unlink(missing_ok=True)
    lease = _lease(c, world, ports=1)
    out = _ok(c.call("instance_serve", {"lease_token": lease["token"], "cwd": str(world["work"])}, timeout=120))
    return lease, out


def _expose(c, world, lease, **over):
    return c.call("instance_expose", dict({"lease_token": lease["token"], "cwd": str(world["work"])}, **over),
                  timeout=120)


def _listed(c, lease):
    return next(r for r in _ok(c.call("lease_list", {}))["leases"] if r["token"] == lease["token"])


# --------------------------------------------------------------------------- #
# the contract of the two tools
# --------------------------------------------------------------------------- #
def test_expose_opens_one_tunnel_to_the_leases_port_and_every_reader_of_the_lease_shows_its_address(
        xclient, machine):
    lease, served = _serve(xclient, machine)
    assert served["instance_handle"]["public_url"] is None and _listed(xclient, lease)["public_url"] is None
    out = _ok(_expose(xclient, machine, lease))
    assert out["public_url"] == FAKE_URL and out["already_exposed"] is False
    assert out["http_port"] == lease["ports"][0]
    assert out["instance_handle"]["public_url"] == FAKE_URL
    assert out["instance_handle"]["lease_token"] == lease["token"]
    (call,) = machine["cf_args"].read_text().splitlines()
    assert "--url http://127.0.0.1:%d" % lease["ports"][0] in call and "--no-autoupdate" in call
    status = _ok(xclient.call("instance_status", {"lease_token": lease["token"], "cwd": str(machine["work"])}))
    assert status["lease"]["public_url"] == FAKE_URL
    assert _listed(xclient, lease)["public_url"] == FAKE_URL
    # A later serve of the same lease reports the address in its handle too.
    again = _ok(xclient.call("instance_serve", {"lease_token": lease["token"], "cwd": str(machine["work"])},
                             timeout=120))
    assert again["instance_handle"]["public_url"] == FAKE_URL


def test_a_second_expose_returns_the_same_address_and_starts_no_second_tunnel(xclient, machine):
    lease, _served = _serve(xclient, machine)
    first = _ok(_expose(xclient, machine, lease))
    second = _ok(_expose(xclient, machine, lease))
    assert second["public_url"] == first["public_url"] and second["already_exposed"] is True
    assert len(_cloudflared_pids(machine)) == 1 and len(machine["cf_args"].read_text().splitlines()) == 1


def test_a_lease_without_a_running_server_is_refused_with_a_remedy_that_names_instance_serve(
        xclient, machine):
    lease = _lease(xclient, machine, ports=1)
    err = _err(_expose(xclient, machine, lease))
    assert err["code"] == "LEASE_NOT_SERVED" and "instance_serve" in err["remedy"]
    assert not machine["cf_args"].exists(), "no tunnel was started"
    assert _params(machine) == []


def test_while_exposed_the_database_holds_the_public_address_frozen_and_unexpose_puts_the_local_url_back(
        xclient, machine):
    lease, _served = _serve(xclient, machine)
    _ok(_expose(xclient, machine, lease))
    (written,) = _params(machine)
    assert written["db"] == lease["db_name"]
    assert written["sets"] == {"web.base.url": FAKE_URL, "web.base.url.freeze": "True"}
    assert written["unsets"] == []
    out = _ok(xclient.call("instance_unexpose", {"lease_token": lease["token"], "cwd": str(machine["work"])}))
    assert out["was_exposed"] is True and out["public_url"] == FAKE_URL and out["base_url_restored"] is True
    assert out["base_url"] == "http://localhost:%d" % lease["ports"][0]
    restored = _params(machine)[-1]
    assert restored["sets"] == {"web.base.url": "http://localhost:%d" % lease["ports"][0]}
    assert restored["unsets"] == ["web.base.url.freeze"]


def test_unexpose_stops_the_tunnel_and_clears_the_address_and_is_safe_to_repeat(xclient, machine):
    lease, _served = _serve(xclient, machine)
    _ok(_expose(xclient, machine, lease))
    pids = _cloudflared_pids(machine)
    assert pids and all(_alive(p) for p in pids)
    out = _ok(xclient.call("instance_unexpose", {"lease_token": lease["token"], "cwd": str(machine["work"])}))
    assert out["was_exposed"] is True
    assert _wait_gone(pids), "the tunnel process is gone"
    assert _listed(xclient, lease)["public_url"] is None
    status = _ok(xclient.call("instance_status", {"lease_token": lease["token"], "cwd": str(machine["work"])}))
    assert status["lease"]["public_url"] is None and status["up"] is True, "the server keeps running"
    again = _ok(xclient.call("instance_unexpose", {"lease_token": lease["token"], "cwd": str(machine["work"])}))
    assert again["was_exposed"] is False and again["base_url_restored"] is False
    assert len(_params(machine)) == 2, "the second unexpose touched nothing"
    # Exposing again opens a NEW tunnel (the address of a Quick Tunnel changes each time).
    _ok(_expose(xclient, machine, lease))
    assert len(_cloudflared_pids(machine)) == 2


def test_an_unknown_lease_is_refused_by_both_tools(xclient, machine):
    for tool in ("instance_expose", "instance_unexpose"):
        err = _err(xclient.call(tool, {"lease_token": "f" * 32, "cwd": str(machine["work"])}))
        assert err["code"] == "LEASE_NOT_FOUND"


# --------------------------------------------------------------------------- #
# the tunnel never outlives the server
# --------------------------------------------------------------------------- #
def _exposed_server(c, world):
    """(lease, server pid, the pids that make up its tunnel: cloudflared and its supervisor)."""
    lease, served = _serve(c, world)
    _ok(_expose(c, world, lease))
    (cf_pid,) = _cloudflared_pids(world)
    supervisor = tunnel.read_record(str(world["home"]), lease["token"])["supervisor_pid"]
    assert _alive(cf_pid) and _alive(supervisor)
    return lease, served["server_pid"], [cf_pid, supervisor]


def test_the_tunnel_is_gone_after_lease_release(xclient, machine):
    lease, _pid, tunnel_pids = _exposed_server(xclient, machine)
    _ok(xclient.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))
    assert _wait_gone(tunnel_pids)
    assert not list((machine["home"] / "runtime" / "tunnels").glob("*.json")), "no record is left"
    assert _params(machine)[-1]["unsets"] == ["web.base.url.freeze"], "the base URL was put back first"


def test_the_tunnel_is_gone_after_lease_park_and_the_kept_database_points_at_its_local_url(xclient, machine):
    lease, _pid, tunnel_pids = _exposed_server(xclient, machine)
    _ok(xclient.call("lease_park", {"lease_token": lease["token"], "run_id": RUN}))
    assert _wait_gone(tunnel_pids)
    last = _params(machine)[-1]
    assert last["sets"] == {"web.base.url": "http://localhost:%d" % lease["ports"][0]}
    assert last["unsets"] == ["web.base.url.freeze"]


def test_a_park_refused_for_a_foreign_run_leaves_the_tunnel_alone(xclient, machine):
    lease, _pid, tunnel_pids = _exposed_server(xclient, machine)
    err = _err(xclient.call("lease_park", {"lease_token": lease["token"], "run_id": "run-someone-else"}))
    assert err["code"] == "NOT_OWNER"
    assert all(_alive(p) for p in tunnel_pids) and _listed(xclient, lease)["public_url"] == FAKE_URL


def test_the_tunnel_is_gone_when_an_older_plugin_version_stops_the_servers_process_group(
        xclient, machine, old_alloc):
    """A release by a plugin version that has never heard of tunnels stops the server by signalling
    its process group - the released 7.0.2 allocator's own `_stop_group` here. The tunnel must end
    with it, and a later reader of the lease must not report its address."""
    lease, server_pid, tunnel_pids = _exposed_server(xclient, machine)
    old_alloc._stop_group(server_pid)
    assert _wait_gone([server_pid]) and _wait_gone(tunnel_pids), "no tunnel process outlives the server"
    assert tunnel.public_url(str(machine["home"]), lease["token"]) is None


def test_the_tunnel_is_gone_when_the_server_is_killed_without_a_chance_to_say_anything(xclient, machine):
    lease, server_pid, tunnel_pids = _exposed_server(xclient, machine)
    os.killpg(server_pid, signal.SIGKILL)
    assert _wait_gone(tunnel_pids)
    assert _listed(xclient, lease)["public_url"] is None


def test_a_tunnel_that_died_with_its_server_leaves_no_stale_base_url_after_the_next_serve(xclient, machine):
    """gc / an older version stopped the server: the database stayed frozen on the dead address.
    Serving the lease again puts its local base URL back."""
    lease, server_pid, tunnel_pids = _exposed_server(xclient, machine)
    os.killpg(server_pid, signal.SIGKILL)
    assert _wait_gone(tunnel_pids)
    machine["curl_mode"].write_text("boot", encoding="utf-8")
    (machine["work"] / "curl-count").unlink(missing_ok=True)
    again = _ok(xclient.call("instance_serve", {"lease_token": lease["token"], "cwd": str(machine["work"])},
                             timeout=120))
    assert again["instance_handle"]["public_url"] is None
    last = _params(machine)[-1]
    assert last["sets"] == {"web.base.url": "http://localhost:%d" % lease["ports"][0]}
    assert last["unsets"] == ["web.base.url.freeze"]


# --------------------------------------------------------------------------- #
# failures leave nothing running
# --------------------------------------------------------------------------- #
def test_a_tunnel_that_cannot_open_is_an_error_with_the_end_of_its_output_and_leaves_nothing(xclient, machine):
    _stub(machine["work"] / "stub-bin" / "cloudflared",
          'echo $$ >> "%s"\necho "ERR failed to request quick Tunnel: 429 Too Many Requests" >&2\nexit 1\n'
          % machine["cf_pids"])
    lease, _served = _serve(xclient, machine)
    err = _err(_expose(xclient, machine, lease))
    assert err["code"] == "TUNNEL_FAILED" and err["remedy"]
    assert "429" in err["diagnostics"]["log_tail"]
    assert _wait_gone(_cloudflared_pids(machine))
    assert _listed(xclient, lease)["public_url"] is None and _params(machine) == []
    assert not list((machine["home"] / "runtime" / "tunnels").glob("*.json"))


def test_a_cloudflared_that_stays_up_without_an_address_is_stopped_and_reported(machine):
    """Nothing printed within the start bound: the call fails, and neither cloudflared nor its
    supervisor is left behind."""
    _stub(machine["work"] / "stub-bin" / "cloudflared",
          'echo $$ >> "%s"\necho "INF Requesting new quick Tunnel on trycloudflare.com..."\nexec sleep 300\n'
          % machine["cf_pids"])
    with McpClient(machine["env"](ODOO_AI_TUNNEL_REACHABLE_WAIT_S="0", ODOO_AI_TUNNEL_START_TIMEOUT_S="2"),
                   machine["work"]) as c:
        c.initialize()
        lease, _served = _serve(c, machine)
        err = _err(_expose(c, machine, lease))
        assert err["code"] == "TUNNEL_FAILED" and "Requesting new quick Tunnel" in err["diagnostics"]["log_tail"]
        assert _wait_gone(_cloudflared_pids(machine)), "cloudflared was left running"
        supervisors = subprocess.run(["pgrep", "-f", "tunnel.py supervise --server-pid %d" % _served["server_pid"]],
                                     capture_output=True, text=True).stdout.split()
        assert supervisors == [], "the supervisor was left running"
        assert _listed(c, lease)["public_url"] is None


def test_an_error_line_that_names_the_address_service_is_not_taken_for_a_tunnel_address(xclient, machine):
    _stub(machine["work"] / "stub-bin" / "cloudflared",
          'echo $$ >> "%s"\n'
          'echo "ERR Post \\"https://api.trycloudflare.com/tunnel\\": dial tcp: lookup failed" >&2\nexit 1\n'
          % machine["cf_pids"])
    lease, _served = _serve(xclient, machine)
    assert _err(_expose(xclient, machine, lease))["code"] == "TUNNEL_FAILED"


def test_a_database_that_cannot_take_the_base_url_stops_the_tunnel_and_says_so(xclient, machine):
    lease, _served = _serve(xclient, machine)
    machine["params_fail"].write_text("x", encoding="utf-8")
    err = _err(_expose(xclient, machine, lease))
    assert err["code"] == "BASE_URL_NOT_SET" and err["remedy"]
    assert _wait_gone(_cloudflared_pids(machine))
    assert _listed(xclient, lease)["public_url"] is None


# --------------------------------------------------------------------------- #
# the binary: PATH, the tools directory, the official release
# --------------------------------------------------------------------------- #
class _ReleaseSource:
    """A local stand-in for the release download: serves `files` (asset name -> bytes), counts hits."""

    def __init__(self, files):
        owner = self
        self.files, self.hits = files, []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                owner.hits.append(self.path)
                name = self.path.rsplit("/", 1)[-1]
                if name not in owner.files:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(owner.files[name])))
                self.end_headers()
                self.wfile.write(owner.files[name])

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d/releases/latest/download" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def release_source(machine):
    asset = tunnel.release_asset()
    if asset is None or asset[1]:
        pytest.skip("this platform's release is an archive or has none; the fetch is tested on Linux")
    (machine["work"] / "stub-bin" / "cloudflared").unlink()
    if shutil.which("cloudflared", path="%s:%s" % (machine["work"] / "stub-bin", os.environ.get("PATH", ""))):
        pytest.skip("a real cloudflared is on PATH; the fetch path would not run")
    body = ("#!/usr/bin/env bash\n" + _fake_cloudflared_body(machine)).encode("utf-8")
    source = _ReleaseSource({asset[0]: body})
    yield source
    source.close()


def test_a_missing_cloudflared_is_fetched_once_into_the_tools_directory_from_the_release_source(
        machine, release_source):
    env = machine["env"](ODOO_AI_TUNNEL_REACHABLE_WAIT_S="0", ODOO_AI_CLOUDFLARED_RELEASE_URL=release_source.url)
    with McpClient(env, machine["work"]) as c:
        c.initialize()
        first, _ = _serve(c, machine)
        assert _ok(_expose(c, machine, first))["public_url"] == FAKE_URL
        binary = machine["home"] / "tools" / "cloudflared" / "cloudflared"
        assert binary.is_file() and os.access(binary, os.X_OK)
        assert release_source.hits == ["/releases/latest/download/" + tunnel.release_asset()[0]]
        second, _ = _serve(c, machine)
        _ok(_expose(c, machine, second))
        assert len(release_source.hits) == 1, "a fetched binary is reused, never fetched again"
        assert len(_cloudflared_pids(machine)) == 2


def test_cloudflared_on_path_wins_over_a_fetch(machine, release_source):
    _stub(machine["work"] / "stub-bin" / "cloudflared", _fake_cloudflared_body(machine))
    env = machine["env"](ODOO_AI_TUNNEL_REACHABLE_WAIT_S="0", ODOO_AI_CLOUDFLARED_RELEASE_URL=release_source.url)
    with McpClient(env, machine["work"]) as c:
        c.initialize()
        lease, _ = _serve(c, machine)
        _ok(_expose(c, machine, lease))
    assert release_source.hits == [] and not (machine["home"] / "tools").exists()


@pytest.mark.parametrize("source", ["refused", "not_found", "not_a_program"])
def test_a_machine_that_cannot_obtain_cloudflared_gets_an_error_code_and_a_remedy(machine, release_source, source):
    if source == "refused":
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            url = "http://127.0.0.1:%d/releases" % probe.getsockname()[1]
    elif source == "not_found":
        release_source.files.clear()
        url = release_source.url
    else:
        release_source.files[tunnel.release_asset()[0]] = b"not a program at all"
        url = release_source.url
    env = machine["env"](ODOO_AI_TUNNEL_REACHABLE_WAIT_S="0", ODOO_AI_CLOUDFLARED_RELEASE_URL=url)
    with McpClient(env, machine["work"]) as c:
        c.initialize()
        lease, _ = _serve(c, machine)
        err = _err(_expose(c, machine, lease))
        assert err["code"] == "CLOUDFLARED_UNAVAILABLE" and err["remedy"].strip()
        assert not (machine["home"] / "tools" / "cloudflared" / "cloudflared").exists()
        assert _listed(c, lease)["public_url"] is None and _params(machine) == []


@pytest.mark.parametrize("system,machine_name,expected", [
    ("Linux", "x86_64", ("cloudflared-linux-amd64", False)),
    ("Linux", "aarch64", ("cloudflared-linux-arm64", False)),
    ("Darwin", "arm64", ("cloudflared-darwin-arm64.tgz", True)),
    ("Darwin", "x86_64", ("cloudflared-darwin-amd64.tgz", True)),
    ("Linux", "armv7l", None),
    ("Windows", "AMD64", None),
])
def test_the_official_release_asset_follows_the_platform(system, machine_name, expected):
    assert tunnel.release_asset(system, machine_name) == expected


def test_an_address_is_read_from_cloudflared_output_and_the_address_service_never_is():
    assert tunnel.find_public_url("INF |  https://a-b-c-d.trycloudflare.com  |") == "https://a-b-c-d.trycloudflare.com"
    assert tunnel.find_public_url('Post "https://api.trycloudflare.com/tunnel": EOF') is None
    assert tunnel.find_public_url('x https://api.trycloudflare.com y https://real-one.trycloudflare.com z') \
        == "https://real-one.trycloudflare.com"
    assert tunnel.find_public_url("https://example.com") is None


# --------------------------------------------------------------------------- #
# the supervisor
# --------------------------------------------------------------------------- #
def _supervise(tmp_path, server, *cmd):
    log = tmp_path / "supervised.log"
    return subprocess.Popen([sys.executable, str(LIB_DIR / "tunnel.py"), "supervise", "--server-pid",
                             str(server.pid), "--server-fp", tunnel.session_anchor.fingerprint(server.pid),
                             "--log", str(log), "--", *cmd], start_new_session=True)


def _child_pid(tmp_path, timeout=10):
    marker = tmp_path / "child.pid"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.exists() and marker.read_text().strip():
            return int(marker.read_text())
        time.sleep(0.05)
    raise AssertionError("the supervised command never started")


def _sleeper(tmp_path):
    script = tmp_path / "child.sh"
    script.write_text('#!/usr/bin/env bash\necho $$ > "%s"\nexec sleep 300\n' % (tmp_path / "child.pid"))
    script.chmod(0o755)
    return str(script)


def test_the_supervisor_stops_the_command_when_the_server_it_watches_is_gone(tmp_path):
    server = subprocess.Popen(["sleep", "300"], start_new_session=True)
    supervisor = _supervise(tmp_path, server, _sleeper(tmp_path))
    try:
        child = _child_pid(tmp_path)
        assert _alive(child) and supervisor.poll() is None
        server.kill()
        server.wait()
        assert supervisor.wait(timeout=20) == 0 and _wait_gone([child])
    finally:
        for proc in (server, supervisor):
            if proc.poll() is None:
                proc.kill()


def test_the_supervisor_stops_the_command_when_it_is_signalled_and_when_it_is_killed(tmp_path):
    server = subprocess.Popen(["sleep", "300"], start_new_session=True)
    try:
        supervisor = _supervise(tmp_path, server, _sleeper(tmp_path))
        child = _child_pid(tmp_path)
        supervisor.send_signal(signal.SIGTERM)
        assert supervisor.wait(timeout=20) == 0 and _wait_gone([child])
        (tmp_path / "child.pid").unlink()
        supervisor = _supervise(tmp_path, server, _sleeper(tmp_path))
        child = _child_pid(tmp_path)
        supervisor.kill()
        supervisor.wait()
        if sys.platform.startswith("linux"):
            assert _wait_gone([child]), "cloudflared dies with a supervisor that was killed outright"
        else:
            os.kill(child, signal.SIGKILL)
    finally:
        server.kill()


def test_the_supervisor_reports_the_command_that_exits_first(tmp_path):
    server = subprocess.Popen(["sleep", "300"], start_new_session=True)
    try:
        assert _supervise(tmp_path, server, "bash", "-c", "exit 7").wait(timeout=20) == 7
    finally:
        server.kill()


def test_a_recycled_server_pid_does_not_keep_a_tunnel_alive(tmp_path):
    """The supervisor watches pid AND fingerprint: another process holding the server's number is not
    the server."""
    server = subprocess.Popen(["sleep", "300"], start_new_session=True)
    time.sleep(0.3)  # a fingerprint is the start time in clock ticks: tell the two apart
    other = subprocess.Popen(["sleep", "300"], start_new_session=True)
    try:
        supervisor = subprocess.Popen(
            [sys.executable, str(LIB_DIR / "tunnel.py"), "supervise", "--server-pid", str(other.pid),
             "--server-fp", tunnel.session_anchor.fingerprint(server.pid), "--log", str(tmp_path / "l"),
             "--", _sleeper(tmp_path)], start_new_session=True)
        assert supervisor.wait(timeout=20) == 0
        marker = tmp_path / "child.pid"   # written only if the command got as far as starting
        assert not marker.exists() or _wait_gone([int(marker.read_text())])
    finally:
        server.kill()
        other.kill()


# --------------------------------------------------------------------------- #
# the one invisible protection: the database manager of a launched server is off
# --------------------------------------------------------------------------- #
def _declare(world, line):
    """Add one option declaration to the checkout's config.py."""
    config = next((world["odoo_bin"].parent).glob("*/tools/config.py"))
    config.write_text(config.read_text(encoding="utf-8") + "        " + line + "\n", encoding="utf-8")


def _served_conf(world, lease):
    return (world["home"] / "conf" / ("%s-%d.conf" % (lease["db_name"], lease["ports"][0]))).read_text()


@pytest.mark.parametrize("dest", ["list_db", "an_other_spelling"])
def test_a_server_launched_for_a_lease_has_the_database_manager_off_in_the_checkouts_own_spelling(
        client, world, dest):
    _declare(world, "group.add_option('--no-database-list', action='store_false', dest='%s', my_default=True)"
             % dest)
    lease, out = _serve(client, world)
    assert out["state"] == "launched"
    assert re.search(r"^%s = False$" % dest, _served_conf(world, lease), re.M)


def test_a_checkout_that_declares_no_such_option_is_served_without_it_and_never_refused(client, world):
    lease, out = _serve(client, world)
    assert out["state"] == "launched"
    conf = _served_conf(world, lease)
    assert "list_db" not in conf and "False" not in conf, conf


def test_a_declaration_that_is_not_a_switch_storing_false_is_not_taken_for_the_option(client, world):
    _declare(world, "group.add_option('--no-database-list', dest='list_db')")  # takes a value
    lease, _out = _serve(client, world)
    assert "list_db" not in _served_conf(world, lease)


def test_the_options_spelling_is_read_from_the_checkout_text(tmp_path):
    import odoo_tree_fixtures as trees
    facts = _load_lib("odoo_source_facts")
    (tmp_path / "core").mkdir()
    root = trees.write_checkout(tmp_path / "core", SERIES, with_addons=False)
    assert facts.no_database_list_key(str(root)) is None
    config = next(root.glob("*/tools/config.py"))
    config.write_text(config.read_text() + "        group.add_option('--no-database-list', action=\"store_false\", "
                      "dest='list_db', my_default=True)\n")
    assert facts.no_database_list_key(str(root)) == "list_db"
    assert facts.no_database_list_key(str(tmp_path / "nothing-here")) is None


def test_nothing_in_the_plugin_drives_the_http_database_manager_of_a_leased_server():
    """The plugin creates and drops databases through Odoo's Python API (odoo_db.py) and odoo-bin;
    the only HTTP address of the database manager it touches is the readiness probe of the selector
    page. A new caller of the manager's routes or of the `db` RPC service would break once the
    manager is off, so it must be found here first."""
    manager = re.compile(r"web/database/(manager|create|drop|duplicate|backup|restore|change_password)"
                         r"|[\"']service[\"']\s*:\s*[\"']db[\"']|/xmlrpc/2/db|/xmlrpc/db")
    hits = []
    for path in PLUGIN.rglob("*"):
        if (not path.is_file() or path.suffix not in (".py", ".sh", ".mjs", ".js", ".json", ".toml")
                or "/docs/" in str(path) or "node_modules" in path.parts
                or path.name == "tools_expose.py"):  # its probe EXPECTS the db service to refuse
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in manager.finditer(text):
            hits.append("%s: %s" % (path.relative_to(PLUGIN), m.group(0)))
    assert hits == [], hits


def test_expose_reports_a_running_server_that_still_has_its_database_manager_on(xclient, machine):
    """The server on the lease's port answers Odoo's database-listing call: the result names it
    instead of exposing it silently."""
    lease, _served = _serve(xclient, machine)

    class Answer(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": ["some_database"]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    # The stub odoo-bin only sleeps, so the lease's port is free: answer on it for the probe.
    try:
        server = http.server.HTTPServer(("127.0.0.1", lease["ports"][0]), Answer)
    except OSError:
        pytest.skip("the lease's port is taken on this machine")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        out = _ok(_expose(xclient, machine, lease))
    finally:
        server.shutdown()
        server.server_close()
    assert out["database_manager_open"] is True and len(out["warnings"]) == 1
    assert out["public_url"] == FAKE_URL, "reported, never refused"
