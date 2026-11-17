"""Behavior tests: a parked lease the lookup passes over, and a park with no database behind it,
are reported as data - never on stderr alone.

Contracts protected (allocator `query --state parked` / `park`, and the odoo-local tools over them):
  - every parked lease of the series that `lease_find` (state parked) does not offer is listed in
    `skipped_leases` with its token prefix, database name and a reason code, whether or not another
    lease is then found, and `yours` marks the caller's own run's - a run whose own parked lease was
    passed over learns it from the result that offers another run's lease;
  - reason codes: database-gone, other-tree, condemned, other-host;
  - `addons_mismatch` keeps its meaning (it still names the other-tree leases);
  - `lease_park` (ALLOC_DB_PRESENT) says whether the database exists to resume into; it still parks
    when it does not;
  - tree identity without a stated addons_path follows the cwd's checkout (docs: see
    test_allocator_parked_tree_identity.py): a lease whose custom addons lie elsewhere is still the
    caller's tree when the caller's cwd is the checkout the row also uses.

The database probe goes through a stub interpreter that answers `exists` per database name: a
database is absent when a marker file named after it exists.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from odoo_local_mcp_harness import McpClient, hermetic_env, structured  # noqa: E402
from test_allocator_liveness_v3 import ALLOC, World  # noqa: E402
from test_odoo_local_mcp_lease import Session  # noqa: E402

SERIES = "17.0"
RUN = "run-own"
OTHER_RUN = "run-other"


def _answer_exists_per_database(py: Path, absent_dir: Path) -> None:
    """Make the stub interpreter say `exists` is false for a database with a marker, else true."""
    text = py.read_text(encoding="utf-8")
    assert "exists) echo false" in text, "test setup: the stub interpreter changed shape"
    py.write_text(text.replace(
        "exists) echo false",
        'exists) if [ -e "%s/$3" ]; then echo false; else echo true; fi' % absent_dir),
        encoding="utf-8")


def _mark_absent(absent_dir: Path, db: str) -> None:
    (absent_dir / db).write_text("", encoding="utf-8")


# --------------------------------------------------------------------------- #
# allocator level
# --------------------------------------------------------------------------- #
@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    w.absent = tmp_path / "absent"
    w.absent.mkdir()
    _answer_exists_per_database(w.py, w.absent)
    try:
        yield w
    finally:
        w.close()


def _tree(world, name):
    path = world.tmp / name / "addons"
    path.mkdir(parents=True)
    return path


def _parked(world, env, tree, run_id):
    p, out = world.acquire(env, "--no-create", "--addons-path-override", str(tree), run_id=run_id)
    assert p.returncode == 0, p.stderr
    token = out["ALLOC_TOKEN"]
    p = world.run(env, "park", token, "--run-id", run_id)
    assert p.returncode == 0, p.stderr
    return token


def _query(world, env, tree, *extra):
    p = subprocess.run(
        [sys.executable, str(ALLOC), "query", "--series", SERIES, "--state", "parked",
         "--run-id", RUN, "--addons-path-override", str(tree), "--format", "json", *extra],
        capture_output=True, text=True, env=env, cwd=str(world.tmp), timeout=60)
    return p, json.loads(p.stdout)


def _skipped(out):
    return {item["token"]: item for item in out["fields"]["skipped_leases"]}


def test_a_passed_over_own_lease_is_reported_when_another_runs_lease_is_found(world):
    env = world.env(world.session("sess-A"))
    tree = _tree(world, "tree")
    own = _parked(world, env, tree, RUN)
    other = _parked(world, env, tree, OTHER_RUN)
    _mark_absent(world.absent, world.lease(own)["db_name"])
    p, out = _query(world, env, tree)
    assert p.returncode == 0, p.stderr
    assert out["fields"]["ALLOC_TOKEN"] == other, "the other run's lease is the one offered"
    assert _skipped(out) == {own: {"token": own, "db_name": world.lease(own)["db_name"],
                                   "run_id": RUN, "reason": "database-gone"}}


def test_the_skipped_leases_are_reported_when_nothing_is_found(world):
    env = world.env(world.session("sess-A"))
    tree = _tree(world, "tree")
    own = _parked(world, env, tree, RUN)
    _mark_absent(world.absent, world.lease(own)["db_name"])
    p, out = _query(world, env, tree)
    assert p.returncode == 1 and out["error"]["code"] == "NOT_FOUND"
    assert list(_skipped(out)) == [own] and _skipped(out)[own]["reason"] == "database-gone"


def test_a_lease_of_another_tree_is_skipped_as_other_tree_and_still_named_in_addons_mismatch(world):
    env = world.env(world.session("sess-A"))
    theirs, mine = _tree(world, "theirs"), _tree(world, "mine")
    token = _parked(world, env, theirs, RUN)
    p, out = _query(world, env, mine)
    assert p.returncode == 1
    assert [m["token"] for m in out["fields"]["addons_mismatch"]] == [token]
    assert _skipped(out)[token]["reason"] == "other-tree"


def test_a_lease_whose_park_budget_lapsed_is_skipped_as_condemned(world):
    env = world.env(world.session("sess-A"))
    tree = _tree(world, "tree")
    token = _parked(world, env, tree, RUN)
    world.edit(token, lambda lz: lz.update(parked_at=lz["parked_at"] - 10 * 24 * 3600))
    p, out = _query(world, env, tree)
    assert p.returncode == 1
    assert _skipped(out)[token]["reason"] == "condemned"


def test_a_parked_lease_of_another_host_is_skipped_as_other_host_unless_force_attach(world):
    env = world.env(world.session("sess-A"))
    tree = _tree(world, "tree")
    token = _parked(world, env, tree, RUN)
    world.edit(token, lambda lz: lz["owner"].update(host="another-host.invalid"))
    p, out = _query(world, env, tree)
    assert p.returncode == 1 and _skipped(out)[token]["reason"] == "other-host"
    p, out = _query(world, env, tree, "--force-attach")
    assert p.returncode == 0 and out["fields"]["ALLOC_TOKEN"] == token
    assert token not in _skipped(out), "an offered lease is not a skipped one"


def test_a_lease_that_is_offered_is_not_listed_as_skipped(world):
    env = world.env(world.session("sess-A"))
    tree = _tree(world, "tree")
    token = _parked(world, env, tree, RUN)
    p, out = _query(world, env, tree)
    assert p.returncode == 0 and out["fields"]["ALLOC_TOKEN"] == token
    assert out["fields"]["skipped_leases"] == []


def test_park_reports_whether_the_database_exists_and_parks_either_way(world):
    env = world.env(world.session("sess-A"))
    tree = _tree(world, "tree")
    present, missing = {}, {}
    for run_id, answer in ((RUN, present), (OTHER_RUN, missing)):
        p, out = world.acquire(env, "--no-create", "--addons-path-override", str(tree),
                               run_id=run_id)
        assert p.returncode == 0, p.stderr
        answer["token"] = out["ALLOC_TOKEN"]
    _mark_absent(world.absent, world.lease(missing["token"])["db_name"])
    for run_id, answer in ((RUN, present), (OTHER_RUN, missing)):
        p = subprocess.run(
            [sys.executable, str(ALLOC), "park", answer["token"], "--run-id", run_id,
             "--format", "json"], capture_output=True, text=True, env=env, timeout=60)
        assert p.returncode == 0, "park never refuses for a missing database: " + p.stderr
        answer["fields"] = json.loads(p.stdout)["fields"]
        assert world.lease(answer["token"])["parked_at"] is not None
    assert present["fields"]["ALLOC_DB_PRESENT"] == "true"
    assert missing["fields"]["ALLOC_DB_PRESENT"] == "false"


# --------------------------------------------------------------------------- #
# odoo-local tools, over stdio
# --------------------------------------------------------------------------- #
@pytest.fixture
def mcp_world(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    absent = tmp_path / "absent"
    absent.mkdir()
    addons = tmp_path / "addons"
    addons.mkdir()
    stub = tmp_path / "stubbin" / "python"
    stub.parent.mkdir()
    stub.write_text(
        "#!/bin/sh\n"
        'if [ "$(basename "$1")" = "odoo_db.py" ]; then\n'
        "  case \"$2\" in exists) echo false; exit 0 ;; esac\n"
        "  exit 0\n"
        "fi\n"
        f'exec {sys.executable} "$@"\n', encoding="utf-8")
    stub.chmod(0o755)
    _answer_exists_per_database(stub, absent)
    (home / "instances.toml").write_text(
        "[[instance]]\n"
        f'series = "{SERIES}"\n'
        f'python = "{stub}"\n'
        "http_port = 38169\n"
        "http_port_base = 38170\n"
        'db_name = "reporttest"\n'
        'db_host = "localhost"\n'
        'db_user = "odoo"\n'
        f'addons_path = ["{addons}"]\n', encoding="utf-8")
    sessions = []

    def session(session_id="sess-a"):
        s = Session(home, session_id)
        sessions.append(s)
        return s

    yield {"home": home, "work": tmp_path, "absent": absent, "session": session}
    for s in sessions:
        s.end()


def _ok(result):
    assert result["isError"] is False, result["structuredContent"]
    return structured(result)


def _acquire_and_park(c, world, run_id, absent):
    lease = _ok(c.call("lease_acquire", {"series": SERIES, "run_id": run_id, "no_create": True,
                                         "cwd": str(world["work"])}))["lease"]
    if absent:
        _mark_absent(world["absent"], lease["db_name"])
    parked = _ok(c.call("lease_park", {"lease_token": lease["token"], "run_id": run_id}))
    return lease, parked


def test_lease_park_says_when_there_is_no_database_to_resume_into(mcp_world):
    with McpClient(mcp_world["session"]().env, mcp_world["work"]) as c:
        c.initialize()
        _, no_db = _acquire_and_park(c, mcp_world, RUN, absent=True)
        _, with_db = _acquire_and_park(c, mcp_world, OTHER_RUN, absent=False)
    assert no_db["database_exists"] is False and no_db["parked_at"], "it still parks"
    assert with_db["database_exists"] is True


def test_lease_find_reports_the_own_lease_it_passed_over_beside_the_other_runs_it_found(mcp_world):
    with McpClient(mcp_world["session"]().env, mcp_world["work"]) as c:
        c.initialize()
        own, _ = _acquire_and_park(c, mcp_world, RUN, absent=True)
        other, _ = _acquire_and_park(c, mcp_world, OTHER_RUN, absent=False)
        out = _ok(c.call("lease_find", {"series": SERIES, "state": "parked", "run_id": RUN,
                                        "cwd": str(mcp_world["work"])}))
    assert out["found"] is True and out["lease"]["yours"] is False
    assert out["lease"]["token_prefix"] == other["token"][:8]
    assert out["skipped_leases"] == [{
        "token_prefix": own["token"][:8], "db_name": own["db_name"],
        "reason": "database-gone", "yours": True}]
    assert own["token"] not in json.dumps(out), "a skipped lease is named by its prefix only"


def test_lease_find_marks_another_runs_skipped_lease_as_not_yours(mcp_world):
    with McpClient(mcp_world["session"]().env, mcp_world["work"]) as c:
        c.initialize()
        theirs, _ = _acquire_and_park(c, mcp_world, OTHER_RUN, absent=True)
        out = _ok(c.call("lease_find", {"series": SERIES, "state": "parked", "run_id": RUN,
                                        "cwd": str(mcp_world["work"])}))
    assert out["found"] is False and out["lease"] is None
    assert out["skipped_leases"] == [{
        "token_prefix": theirs["token"][:8], "db_name": theirs["db_name"],
        "reason": "database-gone", "yours": False}]
    assert OTHER_RUN not in json.dumps(out), "another run's id is never named"


def test_lease_find_of_the_shared_state_has_no_skipped_leases(mcp_world):
    with McpClient(mcp_world["session"]().env, mcp_world["work"]) as c:
        c.initialize()
        out = _ok(c.call("lease_find", {"series": SERIES, "state": "shared",
                                        "cwd": str(mcp_world["work"])}))
    assert out["skipped_leases"] == []


# --------------------------------------------------------------------------- #
# tree identity: a caller that states no addons_path is judged by its cwd's checkout
# --------------------------------------------------------------------------- #
def test_without_a_stated_tree_a_lease_with_custom_addons_elsewhere_is_the_callers_when_the_cwd_is_its_core_checkout(world):
    """The row serves the core checkout (a plain directory, not a repo here) and a custom
    directory of another project; the caller states nothing and stands outside any git
    worktree of the custom directory's repo. No same-repo, other-checkout entry exists, so the
    row is the caller's tree: the cwd is the only thing the caller stated."""
    env = world.env(world.session("sess-A"))
    core, custom = _tree(world, "core"), _tree(world, "other-project")
    p, out = world.acquire(env, "--no-create", "--addons-path-override", "%s,%s" % (core, custom),
                           run_id=OTHER_RUN)
    assert p.returncode == 0, p.stderr
    token = out["ALLOC_TOKEN"]
    assert world.run(env, "park", token, "--run-id", OTHER_RUN).returncode == 0
    p = subprocess.run(
        [sys.executable, str(ALLOC), "query", "--series", SERIES, "--state", "parked",
         "--run-id", RUN, "--format", "json"],
        capture_output=True, text=True, env=env, cwd=str(core), timeout=60)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["fields"]["ALLOC_TOKEN"] == token
