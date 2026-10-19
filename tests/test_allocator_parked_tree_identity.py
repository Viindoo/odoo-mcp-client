"""Behavior tests: a parked lease is identified by the tree it was built from, not only by its
host and series.

A parked database holds the modules of the addons_path it was built from. Resuming it for
another tree (another worktree of the same repo, another stated addons_path) verifies the wrong
code and reports it green. The contract, stated as behavior:
  - `query --state parked` never offers a parked lease of another tree: it names it instead
    (one stderr line, JSON `addons_mismatch` with the row's addons_path and the caller's tree);
  - the caller's tree is the addons_path it states (--addons-path-override, the same ordered
    directories), else its cwd's checkout (a cwd in another worktree of a repo the row serves is
    not that row's tree);
  - a lease of another tree is never probed for its database;
  - --force-attach widens the host scope only, never tree identity;
  - `adopt` refuses a parked lease of another tree (exit 12 LEASE_ADDONS_MISMATCH) and writes
    nothing; a running lease is adopted whatever its tree;
  - a row that recorded no addons_path is never matched by a stated tree.

Every database interaction goes through the stub interpreter of `World`, which only LOGS what it
was asked (here it answers `exists` with true: the parked databases are there).
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_allocator_liveness_v3 import ALLOC, World, _kv  # noqa: E402

RUN = "run-A"


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    text = w.py.read_text(encoding="utf-8")
    assert "exists) echo false" in text, "test setup: the World stub changed shape"
    w.py.write_text(text.replace("exists) echo false", "exists) echo true"), encoding="utf-8")
    try:
        yield w
    finally:
        w.close()


def _tree(world, name):
    path = world.tmp / name / "addons"
    path.mkdir(parents=True)
    return path


def _run_in(world, env, cwd, *args):
    return subprocess.run([sys.executable, str(ALLOC), *args], capture_output=True, text=True,
                          env=env, cwd=str(cwd), timeout=60)


def _parked(world, env, tree):
    """A lease acquired for `tree` (its row records that addons_path), then parked."""
    p, out = world.acquire(env, "--no-create", "--addons-path-override", str(tree), run_id=RUN)
    assert p.returncode == 0, p.stderr
    token = out["ALLOC_TOKEN"]
    p = world.run(env, "park", token, "--run-id", RUN)
    assert p.returncode == 0, p.stderr
    return token


def _query(world, env, cwd, *extra):
    p = _run_in(world, env, cwd, "query", "--series", "17.0", "--state", "parked",
                "--format", "json", *extra)
    return p, json.loads(p.stdout)


def _exists_probes(world):
    if not world.calls.is_file():
        return []
    return [ln for ln in world.calls.read_text(encoding="utf-8").splitlines()
            if ln.startswith("exists ")]


def test_a_parked_lease_of_another_tree_is_not_offered_and_is_named_as_a_mismatch(world):
    env = world.env(world.session("sess-A"))
    theirs, mine = _tree(world, "theirs"), _tree(world, "mine")
    token = _parked(world, env, theirs)
    p, out = _query(world, env, world.tmp, "--addons-path-override", str(mine))
    assert p.returncode == 1 and out["error"]["code"] == "NOT_FOUND", p.stderr
    assert "ALLOC_TOKEN" not in out["fields"], "a lease of another tree must never be offered"
    assert out["fields"]["addons_mismatch"] == [{
        "token": token, "db_name": world.lease(token)["db_name"], "addons_path": [str(theirs)],
        "wanted": [str(mine)], "reason": "addons-path-differs"}]
    assert "SKIPPING parked lease %s" % token[:8] in p.stderr and str(theirs) in p.stderr


def test_a_parked_lease_of_the_callers_tree_is_still_offered(world):
    env = world.env(world.session("sess-A"))
    mine = _tree(world, "mine")
    token = _parked(world, env, mine)
    p, out = _query(world, env, world.tmp, "--addons-path-override", str(mine))
    assert p.returncode == 0, p.stderr
    assert out["fields"]["ALLOC_TOKEN"] == token


def _git(*args, cwd):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "-c", "commit.gpgsign=false", *args], cwd=str(cwd), env=env, check=True,
                   capture_output=True, timeout=60)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not available")
def test_a_worktree_caller_is_not_offered_the_principal_checkouts_parked_lease(world):
    """No addons_path stated: the cwd decides. The principal checkout's parked database holds
    the principal checkout's code, so a caller working in a linked worktree of the same repo
    must not resume it - while the principal checkout itself still does."""
    principal = world.tmp / "repo"
    (principal / "addons").mkdir(parents=True)
    (principal / "addons" / "README").write_text("x\n", encoding="utf-8")
    _git("init", "-q", cwd=principal)
    _git("add", "-A", cwd=principal)
    _git("commit", "-q", "-m", "init", cwd=principal)
    linked = world.tmp / "linked"
    _git("worktree", "add", "-q", str(linked), cwd=principal)
    env = world.env(world.session("sess-A"))
    token = _parked(world, env, principal / "addons")

    p, out = _query(world, env, linked)
    assert p.returncode == 1 and out["error"]["code"] == "NOT_FOUND", p.stderr
    [mismatch] = out["fields"]["addons_mismatch"]
    assert mismatch["token"] == token and mismatch["reason"] == "worktree-differs"
    assert mismatch["wanted"] == [os.path.realpath(linked)]

    p, out = _query(world, env, principal)
    assert p.returncode == 0 and out["fields"]["ALLOC_TOKEN"] == token, p.stderr


def test_a_mismatched_parked_lease_is_never_probed_for_its_database(world):
    env = world.env(world.session("sess-A"))
    _parked(world, env, _tree(world, "theirs"))
    before = _exists_probes(world)
    p, _out = _query(world, env, world.tmp, "--addons-path-override", str(_tree(world, "mine")))
    assert p.returncode == 1, p.stderr
    assert _exists_probes(world) == before, "the database of a lease of another tree was probed"


def test_force_attach_never_overrides_tree_identity(world):
    """--force-attach widens the HOST scope: an off-host parked lease of the caller's tree is
    offered with it, one of another tree is not - on this host or off it."""
    env = world.env(world.session("sess-A"))
    theirs, mine = _tree(world, "theirs"), _tree(world, "mine")
    local_theirs = _parked(world, env, theirs)
    p, out = _query(world, env, world.tmp, "--force-attach", "--addons-path-override", str(mine))
    assert p.returncode == 1 and out["error"]["code"] == "NOT_FOUND", p.stderr

    off_host = _parked(world, env, theirs)
    world.edit(off_host, lambda lz: lz["owner"].update(host="another-host"))
    p, out = _query(world, env, world.tmp, "--force-attach", "--addons-path-override", str(mine))
    assert p.returncode == 1, p.stderr
    assert {m["token"] for m in out["fields"]["addons_mismatch"]} == {local_theirs, off_host}

    p, out = _query(world, env, world.tmp, "--force-attach", "--addons-path-override", str(theirs))
    assert p.returncode == 0 and out["fields"]["ALLOC_TOKEN"] in (local_theirs, off_host), p.stderr


def test_a_row_with_no_recorded_addons_path_is_not_matched_by_a_stated_tree(world):
    env = world.env(world.session("sess-A"))
    mine = _tree(world, "mine")
    token = _parked(world, env, mine)
    world.edit(token, lambda lz: lz.pop("addons_path"))
    p, out = _query(world, env, world.tmp, "--addons-path-override", str(mine))
    assert p.returncode == 1, p.stderr
    [mismatch] = out["fields"]["addons_mismatch"]
    assert mismatch["reason"] == "addons-path-unrecorded" and mismatch["addons_path"] == []


def test_adopt_refuses_a_parked_lease_of_another_tree_and_writes_nothing(world):
    a = world.session("sess-A")
    token = _parked(world, world.env(a), _tree(world, "theirs"))
    before = world.registry_path().read_bytes()
    b = world.session("sess-B")
    p = _run_in(world, world.env(b), world.tmp, "adopt", token, "--run-id", RUN,
                "--addons-path-override", str(_tree(world, "mine")), "--format", "json")
    assert p.returncode == 12, p.stderr
    assert json.loads(p.stdout)["error"]["code"] == "LEASE_ADDONS_MISMATCH"
    assert world.registry_path().read_bytes() == before, "a refused adopt must write nothing"


def test_adopt_of_a_parked_lease_of_the_callers_tree_moves_the_anchor(world):
    a = world.session("sess-A")
    mine = _tree(world, "mine")
    token = _parked(world, world.env(a), mine)
    b = world.session("sess-B")
    p = _run_in(world, world.env(b), world.tmp, "adopt", token, "--run-id", RUN,
                "--addons-path-override", str(mine))
    assert p.returncode == 0, p.stderr
    assert world.lease(token)["owner"]["session"]["pid"] == b.pid


def test_adopt_of_a_running_lease_ignores_the_tree(world):
    a = world.session("sess-A")
    p, out = world.acquire(world.env(a), "--no-create", "--addons-path-override",
                           str(_tree(world, "theirs")), run_id=RUN)
    assert p.returncode == 0, p.stderr
    b = world.session("sess-B")
    p = _run_in(world, world.env(b), world.tmp, "adopt", out["ALLOC_TOKEN"], "--run-id", RUN,
                "--addons-path-override", str(_tree(world, "mine")))
    assert p.returncode == 0, p.stderr
    assert _kv(p.stdout)["ALLOC_TOKEN"] == out["ALLOC_TOKEN"]


def test_an_invalid_tree_is_refused_as_an_invalid_override(world):
    env = world.env(world.session("sess-A"))
    p, out = _query(world, env, world.tmp, "--addons-path-override", str(world.tmp / "nowhere"))
    assert p.returncode == 2 and out["error"]["code"] == "ADDONS_PATH_OVERRIDE_INVALID", p.stderr
