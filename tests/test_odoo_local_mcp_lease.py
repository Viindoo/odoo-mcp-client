"""Behavior tests for the odoo-local lease tools, driven over stdio against the REAL server and the
REAL allocator (tests/odoo_local_mcp_harness.py).

Every server runs hermetically: a temp ODOO_AI_HOME holding a fixture instances.toml, `no_create`
acquires (no Postgres needed), and ODOO_AI_SESSION_ANCHOR naming a live `sleep` process - the
stand-in for the `claude` process that owns a real session. Killing that process is how a test
ends a "session".

Contracts protected:
  - acquire returns a lease built from the allocator's own answer plus an INSTANCE_HANDLE with the
    snippets/instance-handle-contract.md field names; the lease is visible to this session and
    protected by it; release removes it.
  - ownership: only the acquiring run may release / park / adopt (NOT_OWNER), run_id is required
    for every mode but readonly (RUN_ID_REQUIRED), series is never picked (INVALID_ARGUMENTS).
  - token visibility: lease_list gives full tokens only for this session's leases.
  - gc dry-run never changes anything and never condemns a live session's lease.
  - the heartbeat thread refreshes this session's leases without being asked.
  - one input name for the lease token (lease_token) and run_id guidance on every tool taking one
    (per-tool documentation length: tests/test_odoo_local_prose_pointers.py).
  - lease_find discloses a lease's token and owner run only to its owner run; concurrent releases of
    one token report exactly one released; a venv-less lease is flagged and refused as VENV_MISSING.
"""

from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from odoo_local_mcp_harness import LIB_DIR, McpClient, hermetic_env, import_package, structured

import_package()
from odoo_local import errors  # noqa: E402

SERIES = "17.0"
RUN = "run-lease-owner"


def _load_lib(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location("lease_test_" + name, LIB_DIR / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


session_anchor = _load_lib("session_anchor")


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
class Session:
    """A stand-in agent session: a live anchor process + the env a server of that session gets."""

    def __init__(self, home: Path, session_id: str, **extra):
        self.proc = subprocess.Popen(["sleep", "900"])
        fp = session_anchor.fingerprint(self.proc.pid)
        assert fp, "test setup: cannot fingerprint the anchor process"
        self.anchor = session_anchor.format_anchor(self.proc.pid, fp)
        self.env = hermetic_env(home, ODOO_AI_SESSION_ANCHOR=self.anchor,
                                CLAUDE_CODE_SESSION_ID=session_id, **extra)

    def end(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()


@pytest.fixture
def world(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    addons = tmp_path / "addons"
    addons.mkdir()
    (home / "instances.toml").write_text(
        "[[instance]]\n"
        f'series = "{SERIES}"\n'
        f'python = "{sys.executable}"\n'
        "http_port = 38169\n"
        "http_port_base = 38170\n"
        'db_name = "leasetest"\n'
        'db_host = "localhost"\n'
        'db_user = "odoo"\n'
        f'addons_path = ["{addons}"]\n',
        encoding="utf-8",
    )
    sessions = []

    def session(session_id="sess-a", **extra):
        s = Session(home, session_id, **extra)
        sessions.append(s)
        return s

    yield {"home": home, "work": tmp_path, "addons": addons, "session": session}
    for s in sessions:
        s.end()


@pytest.fixture
def client(world):
    s = world["session"]()
    with McpClient(s.env, world["work"]) as c:
        c.initialize()
        yield c


def _ok(result):
    assert result["isError"] is False, result["structuredContent"]
    return structured(result)


def _err(result):
    assert result["isError"] is True, result["structuredContent"]
    return structured(result)["error"]


def _acquire(c, world, **over):
    args = {"series": SERIES, "run_id": RUN, "cwd": str(world["work"]), "no_create": True}
    args.update(over)
    return c.call("lease_acquire", args)


def _registry(home: Path):
    path = home / "runtime" / "leases.json"
    return json.loads(path.read_text()) if path.is_file() else {"leases": []}


# --------------------------------------------------------------------------- #
# acquire -> list -> release
# --------------------------------------------------------------------------- #
def test_acquire_list_release_round_trip(client, world):
    out = _ok(_acquire(client, world))
    lease, handle = out["lease"], out["instance_handle"]
    assert re.fullmatch(r"[0-9a-f]{32}", lease["token"])
    assert lease["mode"] == "ephemeral" and lease["run_id"] == RUN and lease["series"] == SERIES
    assert lease["db_name"].startswith("leasetest_t_")
    assert lease["addons_path"] == [str(world["addons"])]
    assert lease["venv_python"] == sys.executable
    assert lease["session_alive"] is True, "a lease acquired inside a live session is protected by it"

    # INSTANCE_HANDLE carries the contract's field names, filled from the lease.
    assert set(handle) == {"db_name", "http_port", "gevent_port", "db_port", "addons_path", "venv_python",
                           "demo", "languages_loaded", "facts_source", "log_path", "lease_token", "run_id",
                           "server_pid"}
    assert handle["lease_token"] == lease["token"] and handle["run_id"] == RUN
    assert handle["db_name"] == lease["db_name"] and handle["addons_path"] == str(world["addons"])

    listed = _ok(client.call("lease_list", {}))["leases"]
    assert [row["token"] for row in listed] == [lease["token"]]
    row = listed[0]
    assert row["mine"] is True and row["session_alive"] is True and row["protected_by"] == "session"
    assert row["condemn"] is None

    released = _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))
    assert released["status"] == "released"
    assert _ok(client.call("lease_list", {}))["leases"] == []
    assert not [lz for lz in _registry(world["home"])["leases"] if lz.get("token") == lease["token"]]

    again = _ok(client.call("lease_release", {"lease_token": lease["token"], "run_id": RUN}))
    assert again["status"] == "absent", "releasing an already-released lease is a no-op, not an error"


def test_readonly_needs_no_run_id_and_writes_no_lease(client, world):
    out = _ok(client.call("lease_acquire", {"series": SERIES, "mode": "readonly", "cwd": str(world["work"])}))
    assert out["lease"]["token"] is None and out["lease"]["db_name"] == "leasetest"
    assert out["instance_handle"]["http_port"] == 38169
    assert _registry(world["home"])["leases"] == []


def test_ports_are_reserved_from_the_pool_and_reach_the_handle(client, world):
    lease = _ok(_acquire(client, world, ports=2))
    ports = lease["lease"]["ports"]
    assert len(ports) == 2 and all(38170 <= p < 38180 for p in ports)
    assert lease["instance_handle"]["http_port"] == ports[0]
    assert lease["instance_handle"]["gevent_port"] == ports[1]


# --------------------------------------------------------------------------- #
# port pool exhaustion: the remedy must name the TRUE cause (errors.py PORT_POOL_EXHAUSTED)
# --------------------------------------------------------------------------- #
def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _one_port_catalog(world, port):
    """Rewrite world's catalog to a pool of exactly ONE port (`port`), everything else unchanged."""
    declared = port + 1000 if port < 60000 else 1
    (world["home"] / "instances.toml").write_text(
        "[[instance]]\n"
        f'series = "{SERIES}"\n'
        f'python = "{sys.executable}"\n'
        f"http_port = {declared}\n"
        f"http_port_base = {port}\n"
        "port_pool_size = 1\n"
        'db_name = "leasetest"\n'
        'db_host = "localhost"\n'
        'db_user = "odoo"\n'
        f'addons_path = ["{world["addons"]}"]\n',
        encoding="utf-8",
    )


def test_a_pool_held_by_a_lease_keeps_the_ordinary_exhausted_remedy(client, world):
    port = _free_port()
    _one_port_catalog(world, port)
    holder = _ok(_acquire(client, world, ports=1))["lease"]
    err = _err(client.call("lease_acquire", {"series": SERIES, "run_id": "another-run",
                                             "cwd": str(world["work"]), "no_create": True, "ports": 1}))
    assert err["code"] == "PORT_POOL_EXHAUSTED"
    assert "reason" not in err["diagnostics"]["fields"]
    assert err["remedy"] == errors.TOOL_REMEDIES["PORT_POOL_EXHAUSTED"]["default"]
    assert "release" in err["remedy"].lower()
    _ok(client.call("lease_release", {"lease_token": holder["token"], "run_id": RUN}))


def test_a_pool_busy_outside_the_registry_gets_a_distinct_remedy(client, world):
    """No lease in the registry holds the pool's one port, yet it cannot be bound (here: a foreign
    listener the allocator does not track). The remedy must say the ports are held OUTSIDE the
    registry and to retry - never send the agent to release a holder that lease_list has none of."""
    port = _free_port()
    _one_port_catalog(world, port)
    blocker = socket.socket()
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("", port))
    blocker.listen(1)
    try:
        err = _err(_acquire(client, world, ports=1))
        assert err["code"] == "PORT_POOL_EXHAUSTED"
        assert err["diagnostics"]["fields"]["reason"] == "ports-busy-outside-registry"
        assert err["diagnostics"]["fields"]["holders"] == []
        assert err["remedy"] == errors.TOOL_REMEDIES["PORT_POOL_EXHAUSTED"]["reasons"]["ports-busy-outside-registry"]
        assert "outside the lease registry" in err["remedy"]
        assert "release or park a lease" not in err["remedy"]
        assert _registry(world["home"])["leases"] == [], "a refused acquire must leave no lease behind"
    finally:
        blocker.close()


# --------------------------------------------------------------------------- #
# ownership + argument contract
# --------------------------------------------------------------------------- #
def test_release_by_another_run_is_refused_and_keeps_the_lease(client, world):
    token = _ok(_acquire(client, world))["lease"]["token"]
    err = _err(client.call("lease_release", {"lease_token": token, "run_id": "some-other-run"}))
    assert err["code"] == "NOT_OWNER"
    assert err["remedy"] == errors.TOOL_REMEDIES["NOT_OWNER"]
    assert [lz["token"] for lz in _registry(world["home"])["leases"]] == [token]


def test_park_by_another_run_is_refused(client, world):
    """Decided by the allocator (under its lock, ahead of the lease-state refusals - this lease has
    no server, so a later check would say NOT_RUNNING); the tool surfaces that named error with its
    own tool-vocabulary remedy, and the lease is left as it was."""
    token = _ok(_acquire(client, world))["lease"]["token"]
    err = _err(client.call("lease_park", {"lease_token": token, "run_id": "some-other-run"}))
    assert err["code"] == "NOT_OWNER"
    assert err["remedy"] == errors.TOOL_REMEDIES["NOT_OWNER"]
    rows = _registry(world["home"])["leases"]
    assert [lz["token"] for lz in rows] == [token] and "parked_at" not in rows[0]


def test_park_of_an_unknown_token_is_lease_not_found(client, world):
    err = _err(client.call("lease_park", {"lease_token": "0" * 32, "run_id": RUN}))
    assert err["code"] == "LEASE_NOT_FOUND"


def test_park_of_a_lease_never_served_keeps_it_and_a_second_park_is_refused_by_name(client, world):
    """A lease built and never served has no server to stop, yet its database is what park keeps
    (the handback gate offers park for it): the park succeeds. Parking it AGAIN is refused by name
    - a second park would only re-stamp a fresh budget."""
    token = _ok(_acquire(client, world))["lease"]["token"]
    parked = _ok(client.call("lease_park", {"lease_token": token, "run_id": RUN}))
    assert parked["parked_at"] and parked["token"] == token
    assert _registry(world["home"])["leases"][0]["parked_at"] == parked["parked_at"]
    err = _err(client.call("lease_park", {"lease_token": token, "run_id": RUN}))
    assert err["code"] == "NOT_RUNNING"
    assert "instance_serve" in err["remedy"], "the remedy speaks tool vocabulary"


@pytest.mark.parametrize("mode", ["ephemeral", "exclusive", "shared"])
def test_every_leasing_mode_requires_a_run_id(client, world, mode):
    err = _err(client.call("lease_acquire", {"series": SERIES, "mode": mode, "cwd": str(world["work"]),
                                             "no_create": True}))
    assert err["code"] == "RUN_ID_REQUIRED"
    assert "never invent" in err["remedy"].lower()
    assert _registry(world["home"])["leases"] == []


def test_missing_series_is_an_invalid_argument_naming_it(client, world):
    err = _err(client.call("lease_acquire", {"run_id": RUN, "cwd": str(world["work"])}))
    assert err["code"] == "INVALID_ARGUMENTS" and err["message"].startswith("arguments.series")


def test_unknown_series_is_no_instance_with_a_tool_remedy(client, world):
    err = _err(_acquire(client, world, series="99.0"))
    assert err["code"] == "NO_INSTANCE" and "catalog_read" in err["remedy"]


def test_relative_cwd_is_refused(client, world):
    err = _err(_acquire(client, world, cwd="relative/dir"))
    assert err["code"] == "INVALID_ARGUMENTS" and "arguments.cwd" in err["message"]


def test_scope_run_requires_a_run_id(client):
    err = _err(client.call("lease_list", {"scope": "run"}))
    assert err["code"] == "INVALID_ARGUMENTS" and "run_id" in err["message"]


# --------------------------------------------------------------------------- #
# the two acquire shapes agents/odoo-instance-ops.md builds on
# --------------------------------------------------------------------------- #
def test_a_reuse_test_run_leases_its_own_port_on_a_handles_database(client, world):
    """run-tests `reuse` on a forwarded handle - possibly one whose server is listening on the
    handle's port - takes an `exclusive`, `no_create` lease on the handle's database. It must get a
    pooled port distinct from the handle's, and releasing it must leave the handle's lease exactly as
    it was (the fixture's leases are all `no_create`, so no database exists to be dropped)."""
    handle = _ok(_acquire(client, world, run_id="run-handle-owner", ports=1))["lease"]
    port_lease = _ok(_acquire(client, world, mode="exclusive", db_name=handle["db_name"], ports=1))["lease"]
    assert port_lease["db_name"] == handle["db_name"], "the test build must run on the handle's database"
    assert port_lease["ports"] and port_lease["ports"][0] not in handle["ports"], (
        "the test build needs its own port - the handle's may already be bound by its server")

    def row(token):
        return next(r for r in _ok(client.call("lease_list", {}))["leases"] if r["token"] == token)

    assert row(port_lease["token"])["drop_on_release"] is False, "the port lease must never drop the database"
    handle_before = row(handle["token"])
    released = _ok(client.call("lease_release", {"lease_token": port_lease["token"], "run_id": RUN}))
    assert released["status"] == "released"
    handle_after = row(handle["token"])
    for key in ("db_name", "ports", "run_id", "drop_on_release", "state"):
        assert handle_after[key] == handle_before[key], f"releasing the port lease changed the handle's {key}"


def test_a_venv_recorded_on_the_catalog_reaches_only_leases_acquired_after_it(client, world):
    """The agent builds a missing or fresh venv with 45-venv.sh, which records it as the catalog
    row's `python`, and only THEN acquires. That order is correct only if the lease copies the
    catalog interpreter at acquire time: a later acquire carries the new venv, an earlier lease
    keeps the value it was minted with."""
    before = _ok(_acquire(client, world))["lease"]
    fresh_python = world["work"] / "venvs" / SERIES / "bin" / "python"
    fresh_python.parent.mkdir(parents=True)
    fresh_python.symlink_to(sys.executable)
    toml = world["home"] / "instances.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace(
        f'python = "{sys.executable}"', f'python = "{fresh_python}"'), encoding="utf-8")
    after = _ok(_acquire(client, world))
    assert after["lease"]["venv_python"] == str(fresh_python)
    assert after["instance_handle"]["venv_python"] == str(fresh_python)
    earlier = next(r for r in _ok(client.call("lease_list", {}))["leases"] if r["token"] == before["token"])
    assert earlier["venv_python"] == sys.executable, "a lease acquired before the rebuild keeps its interpreter"


# --------------------------------------------------------------------------- #
# cross-session visibility + adopt
# --------------------------------------------------------------------------- #
def test_other_sessions_leases_are_listed_without_their_token(world):
    a, b = world["session"]("sess-a"), world["session"]("sess-b")
    with McpClient(a.env, world["work"]) as ca, McpClient(b.env, world["work"]) as cb:
        ca.initialize()
        cb.initialize()
        token = _ok(_acquire(ca, world))["lease"]["token"]
        assert _ok(cb.call("lease_list", {}))["leases"] == [], "scope mine is this session only"
        rows = _ok(cb.call("lease_list", {"scope": "all"}))["leases"]
        assert len(rows) == 1
        row = rows[0]
        assert row["mine"] is False and row["token"] is None and row["token_prefix"] == token[:8]
        assert row["run_id"] is None, "a foreign session's owner run is half of a release: never listed"
        by_run = _ok(cb.call("lease_list", {"scope": "run", "run_id": RUN}))["leases"]
        assert [r["token_prefix"] for r in by_run] == [token[:8]]
        assert by_run[0]["token"] is None and by_run[0]["run_id"] is None
        assert RUN not in json.dumps(rows) and token not in json.dumps(rows)
        own = _ok(ca.call("lease_list", {"scope": "all"}))["leases"]
        assert own[0]["token"] == token and own[0]["run_id"] == RUN, "this session's rows keep both"


def test_adopt_moves_the_anchor_to_the_calling_session_for_the_owner_only(world):
    a, b = world["session"]("sess-a"), world["session"]("sess-b")
    with McpClient(a.env, world["work"]) as ca:
        ca.initialize()
        token = _ok(_acquire(ca, world))["lease"]["token"]
    a.end()  # the acquiring session is gone (e.g. the process was restarted)
    with McpClient(b.env, world["work"]) as cb:
        cb.initialize()
        assert _err(cb.call("lease_adopt", {"lease_token": token, "run_id": "not-the-owner"}))["code"] == "NOT_OWNER"
        adopted = _ok(cb.call("lease_adopt", {"lease_token": token, "run_id": RUN}))
        assert adopted["anchor"] == b.anchor
        mine = _ok(cb.call("lease_list", {}))["leases"]
        assert [r["token"] for r in mine] == [token] and mine[0]["session_alive"] is True


# --------------------------------------------------------------------------- #
# gc
# --------------------------------------------------------------------------- #
def test_gc_dry_run_reclaims_nothing_live_and_changes_nothing(client, world):
    token = _ok(_acquire(client, world))["lease"]["token"]
    before = _registry(world["home"])
    for scope in ("dead-sessions", "all"):
        out = _ok(client.call("lease_gc", {"scope": scope}))
        assert out["dry_run"] is True and out["leases"] == [], scope
    assert _registry(world["home"]) == before
    assert [lz["token"] for lz in before["leases"]] == [token]


def test_gc_dry_run_names_an_ended_sessions_lease_but_removes_nothing(world):
    a, b = world["session"]("sess-a"), world["session"]("sess-b")
    with McpClient(a.env, world["work"]) as ca:
        ca.initialize()
        token = _ok(_acquire(ca, world))["lease"]["token"]
    a.end()
    with McpClient(b.env, world["work"]) as cb:
        cb.initialize()
        # The automatic scope waits out the grace window; an explicit `all` names it at once.
        assert _ok(cb.call("lease_gc", {"scope": "dead-sessions"}))["leases"] == []
        cands = _ok(cb.call("lease_gc", {"scope": "all"}))["leases"]
        assert [(c["token_prefix"], c["reason"]) for c in cands] == [(token[:8], "owner-session-ended")]
        assert "token" not in cands[0], "gc never hands out a full token"
        assert cands[0]["run_id"] is None and cands[0]["action"] == "reclaim"
    assert [lz["token"] for lz in _registry(world["home"])["leases"]] == [token]


def _set_owner_flag(home, token, key, value):
    path = home / "runtime" / "leases.json"
    doc = json.loads(path.read_text())
    row = next(lz for lz in doc["leases"] if lz["token"] == token)
    row.setdefault("owner", {})[key] = value
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_gc_reports_a_return_to_park_lease_as_parked_not_reclaimed(world):
    """A lease adopted/resumed out of a park carries owner.return_to_park: when its session ends,
    gc sends it BACK to the park (database + ports kept) instead of reclaiming it. The tool must say
    so - per lease (action park) and in `parked` after a real run - never report it as reclaimed."""
    a, b = world["session"]("sess-a"), world["session"]("sess-b")
    with McpClient(a.env, world["work"]) as ca:
        ca.initialize()
        back = _ok(_acquire(ca, world))["lease"]["token"]
        gone = _ok(_acquire(ca, world))["lease"]["token"]
    _set_owner_flag(world["home"], back, "return_to_park", True)
    a.end()
    with McpClient(b.env, world["work"]) as cb:
        cb.initialize()
        dry = _ok(cb.call("lease_gc", {"scope": "all"}))
        actions = {c["token_prefix"]: c["action"] for c in dry["leases"]}
        assert actions == {back[:8]: "park", gone[:8]: "reclaim"}
        assert dry["parked"] == []
        real = _ok(cb.call("lease_gc", {"scope": "all", "dry_run": False}, timeout=120))
        assert real["parked"] == [back[:8]]
        assert [c["token_prefix"] for c in real["leases"]] == [gone[:8]]
    rows = {lz["token"]: lz for lz in _registry(world["home"])["leases"]}
    assert list(rows) == [back] and rows[back].get("parked_at") is not None


# --------------------------------------------------------------------------- #
# find / preflight
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("state", ["shared", "parked"])
def test_find_with_nothing_to_reuse_is_a_normal_answer(client, state):
    out = _ok(client.call("lease_find", {"series": SERIES, "state": state}))
    assert out == {"found": False, "state": state, "lease": None}


def test_find_returns_the_shared_render_lease(client, world):
    token = _ok(_acquire(client, world, mode="shared"))["lease"]["token"]
    out = _ok(client.call("lease_find", {"series": SERIES, "run_id": RUN}))
    assert out["found"] is True and out["lease"]["token"] == token and out["lease"]["mode"] == "shared"
    assert out["lease"]["yours"] is True and out["lease"]["run_id"] == RUN


def test_db_preflight_for_an_undeclared_series_is_no_instance(client):
    assert _err(client.call("db_preflight", {"series": "99.0"}))["code"] == "NO_INSTANCE"


# --------------------------------------------------------------------------- #
# heartbeat
# --------------------------------------------------------------------------- #
def test_heartbeat_refreshes_this_sessions_leases_unasked(world):
    s = world["session"]("sess-hb", ODOO_LOCAL_MCP_HEARTBEAT_S="1")
    with McpClient(s.env, world["work"]) as c:
        c.initialize()
        token = _ok(_acquire(c, world))["lease"]["token"]

        def seen_at():
            row = next(lz for lz in _registry(world["home"])["leases"] if lz["token"] == token)
            return row["owner"]["session"]["seen_at"]

        first = seen_at()
        deadline = time.monotonic() + 15
        while seen_at() == first and time.monotonic() < deadline:
            time.sleep(0.3)
        assert seen_at() > first, "the heartbeat thread must touch the session's leases on its own"


# --------------------------------------------------------------------------- #
# documentation contract
# --------------------------------------------------------------------------- #
def test_every_tool_remedy_translates_a_live_allocator_code():
    allocator = _load_lib("allocator")
    dead = sorted(set(errors.TOOL_REMEDIES) - set(allocator.ERROR_CODES))
    assert not dead, "TOOL_REMEDIES re-words codes the allocator no longer has: %s" % dead
    for code, remedy in errors.TOOL_REMEDIES.items():
        # A code whose refusal SPLITS by fields.reason (see errors.py module docstring) carries
        # {"default": ..., "reasons": {...}} instead of a bare string: check every string it holds.
        strings = [remedy] if isinstance(remedy, str) else \
            [remedy["default"]] + list((remedy.get("reasons") or {}).values())
        for text in strings:
            assert "--" not in text, "%s remedy names a CLI flag an agent cannot pass" % code


# --------------------------------------------------------------------------- #
# venv not built yet: flagged at acquire, refused by name at build
# --------------------------------------------------------------------------- #
def test_a_lease_on_a_row_without_python_is_flagged_and_its_build_refused_as_venv_missing(client, world):
    toml = world["home"] / "instances.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace(f'python = "{sys.executable}"\n', ""),
                    encoding="utf-8")
    out = _ok(_acquire(client, world))
    assert out["venv_missing"] is True and out["lease"]["venv_python"] == ""
    assert out["warnings"] and "venv" in out["warnings"][0]
    err = _err(client.call("instance_build", {"lease_token": out["lease"]["token"], "op": "init",
                                              "modules": ["base"], "demo": "off",
                                              "cwd": str(world["work"])}))
    assert err["code"] == "VENV_MISSING", "a venv that was never built is not a stale lease"
    assert "venv" in err["remedy"] and "lease_acquire" in err["remedy"]
    jobs_dir = world["home"] / "runtime" / "jobs"
    assert not jobs_dir.is_dir() or not list(jobs_dir.glob("*.json")), "nothing may start"


def test_a_lease_with_a_venv_is_not_flagged(client, world):
    out = _ok(_acquire(client, world))
    assert out["venv_missing"] is False and out["warnings"] == []


# --------------------------------------------------------------------------- #
# lease_find disclosure: a lease's token and owner run only to its owner run
# --------------------------------------------------------------------------- #
def test_find_hides_another_runs_token_and_owner_run(world):
    a, b = world["session"]("sess-a"), world["session"]("sess-b")
    with McpClient(a.env, world["work"]) as ca, McpClient(b.env, world["work"]) as cb:
        ca.initialize()
        cb.initialize()
        token = _ok(_acquire(ca, world, mode="shared"))["lease"]["token"]
        for c, args in ((cb, {}), (cb, {"run_id": "another-run"}), (ca, {})):
            lease = _ok(c.call("lease_find", dict({"series": SERIES}, **args)))["lease"]
            assert lease["token"] is None and lease["run_id"] is None and lease["yours"] is False, args
            assert lease["token_prefix"] == token[:8]
            assert RUN not in json.dumps(lease), "the owner's run id must not leak through any field"
        # A prefix is useless for mutating: the release sees no such lease and nothing is dropped.
        assert _ok(cb.call("lease_release", {"lease_token": token[:8], "run_id": "another-run"}))["status"] == "absent"
        owner_view = _ok(ca.call("lease_find", {"series": SERIES, "run_id": RUN}))["lease"]
        assert owner_view["token"] == token and owner_view["run_id"] == RUN and owner_view["yours"] is True
    assert [lz["token"] for lz in _registry(world["home"])["leases"]] == [token]


def test_find_never_hands_a_live_foreign_sessions_lease_to_a_caller_naming_its_run(world):
    """A run id is a guessable slug: naming it from ANOTHER, LIVE session must not yield the token
    (token + run id is a release). Once the acquiring session has ended, the same call is how the
    owner resumes its run from a new session - then, and only then, the token comes back."""
    a, b = world["session"]("sess-a"), world["session"]("sess-b")
    with McpClient(a.env, world["work"]) as ca:
        ca.initialize()
        token = _ok(_acquire(ca, world, mode="shared"))["lease"]["token"]
        with McpClient(b.env, world["work"]) as cb:
            cb.initialize()
            foreign = _ok(cb.call("lease_find", {"series": SERIES, "run_id": RUN}))["lease"]
            assert foreign["token"] is None and foreign["run_id"] is None and foreign["yours"] is False
            assert token not in json.dumps(foreign)
    a.end()
    with McpClient(b.env, world["work"]) as cb:
        cb.initialize()
        resumed = _ok(cb.call("lease_find", {"series": SERIES, "run_id": RUN}))["lease"]
        assert resumed["token"] == token and resumed["run_id"] == RUN and resumed["yours"] is True
        stranger = _ok(cb.call("lease_find", {"series": SERIES, "run_id": "another-run"}))["lease"]
        assert stranger["token"] is None and stranger["run_id"] is None


def test_not_owner_never_names_the_owner_run(client, world):
    token = _ok(_acquire(client, world))["lease"]["token"]
    for tool in ("lease_release", "lease_park", "lease_adopt"):
        err = _err(client.call(tool, {"lease_token": token, "run_id": "some-other-run"}))
        assert err["code"] == "NOT_OWNER", tool
        assert "owner_run_id" not in err["diagnostics"], tool
        assert RUN not in json.dumps(err), "%s leaks the owner run: %s" % (tool, err)
    assert [lz["token"] for lz in _registry(world["home"])["leases"]] == [token]


@pytest.mark.parametrize("mode", ["shared", "readonly"])
def test_ports_with_a_mode_that_reserves_none_is_refused_not_ignored(client, world, mode):
    err = _err(_acquire(client, world, mode=mode, ports=1))
    assert err["code"] == "INVALID_ARGUMENTS" and err["message"].startswith("arguments.ports")
    assert _registry(world["home"])["leases"] == [], "a refused acquire leaves no lease behind"


# --------------------------------------------------------------------------- #
# concurrent release: exactly one caller releases
# --------------------------------------------------------------------------- #
def test_two_concurrent_releases_of_one_lease_report_exactly_one_released(world):
    a, b = world["session"]("sess-a"), world["session"]("sess-b")
    with McpClient(a.env, world["work"]) as ca, McpClient(b.env, world["work"]) as cb:
        ca.initialize()
        cb.initialize()
        for _round in range(3):
            token = _ok(_acquire(ca, world))["lease"]["token"]
            args = {"name": "lease_release", "arguments": {"lease_token": token, "run_id": RUN}}
            ids = [(ca, ca.request_async("tools/call", args)), (cb, cb.request_async("tools/call", args))]
            statuses = sorted(structured(c.wait_for(i, 120)["result"])["status"] for c, i in ids)
            assert statuses == ["absent", "released"], statuses
    assert _registry(world["home"])["leases"] == []
    locks = world["home"] / "runtime" / "mcp-locks"
    assert not locks.is_dir() or not list(locks.iterdir()), "no release lock file outlives its release"


# --------------------------------------------------------------------------- #
# one name for the lease token; run_id guidance on every tool that takes it
# --------------------------------------------------------------------------- #
def test_every_tool_names_the_lease_token_input_lease_token(client):
    for tool in client.request("tools/list")["result"]["tools"]:
        props = tool["inputSchema"].get("properties", {})
        assert "token" not in props, "%s takes `token`; the lease token input is `lease_token`" % tool["name"]
    tools = {t["name"]: t for t in client.request("tools/list")["result"]["tools"]}
    for name in ("lease_release", "lease_park", "lease_adopt", "instance_build"):
        assert "lease_token" in tools[name]["inputSchema"]["required"], name


def test_every_run_id_input_says_never_invent_and_what_to_do_without_one(client):
    seen = 0
    for tool in client.request("tools/list")["result"]["tools"]:
        sub = tool["inputSchema"].get("properties", {}).get("run_id")
        if sub is None:
            continue
        seen += 1
        text = sub["description"]
        assert "NEEDS_CONTEXT(RUN_ID)" in text and "never invent" in text, tool["name"]
    assert seen >= 6
