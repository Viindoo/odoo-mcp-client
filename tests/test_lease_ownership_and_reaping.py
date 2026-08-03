"""Behavior tests for two allocator.py gaps NOT covered by test_allocator.py:

1. Worktree-mismatch guard on `acquire` (--addons-path-override class): a
   caller standing in a LINKED git worktree of the SAME repo as a catalog
   addons_path entry, but a DIFFERENT checkout, must be REFUSED rather than
   silently handed the wrong-tree default - the false-green shape where a fix
   living in a worktree gets verified against the (pre-fix) principal
   checkout instead.

2. `reap-orphans`: a DB-side sweep for ephemeral-shaped databases that carry
   NO lease reference at all (live or stale) - the class `gc` cannot reach
   because `gc` only ever reclaims a DB a LEASE still points at. Protects the
   explicit ownership predicate (naming shape + zero lease reference + a
   POSITIVELY PROVEN age) and the fail-closed behavior on every axis: an
   unreachable cluster, an unmeasurable age, or any leased db_name (even
   stale) must never be treated as reapable.

These assert on OBSERVABLE behavior (exit code, stdout markers, the actual
psql/dropdb subprocess invocations recorded by a stub) - never on internals.
"""

import importlib.util
import os
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ALLOC = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "allocator.py"


def _import_allocator():
    spec = importlib.util.spec_from_file_location("allocator_under_test_reaping", ALLOC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(env, *args, cwd=None):
    return subprocess.run(
        [sys.executable, str(ALLOC), *args],
        capture_output=True, text=True, env=env, cwd=cwd,
    )


def _base_env(home: Path, toml: Path) -> dict:
    e = dict(os.environ)
    e["ODOO_AI_HOME"] = str(home)
    e["ODOO_AI_INSTANCES"] = str(toml)
    e["HOME"] = str(home)
    return e


# --------------------------------------------------------------------------- #
# Part 1 - worktree-mismatch guard on acquire (addons-path false-green class)
# --------------------------------------------------------------------------- #
def _git(*args, cwd):
    subprocess.run(
        ["git", *args], cwd=str(cwd), check=True,
        capture_output=True, text=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"},
    )


def _make_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", cwd=path)
    _git("config", "user.email", "t@example.com", cwd=path)
    _git("config", "user.name", "T", cwd=path)
    (path / "README").write_text("x", encoding="utf-8")
    _git("add", "README", cwd=path)
    _git("commit", "-q", "-m", "init", cwd=path)


requires_git = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git not available",
)


def _toml_with_addons(addons_path: Path) -> str:
    return textwrap.dedent(f"""\
        [[instance]]
        series = "17.0"
        addons_path = ["{addons_path}"]
        http_port = 8069
        db_name = "odoo_17_0"
        db_name_prefix = "odoo_17_0"
        db_host = "localhost"
        db_user = "odoo"
        """)


@requires_git
def test_acquire_refuses_to_default_addons_path_from_a_mismatched_worktree(tmp_path):
    """RED before the fix: acquire silently emitted the principal checkout's
    addons_path even though the caller stood in a DIFFERENT worktree of that
    same repo. GREEN after: acquire refuses (non-zero) instead of guessing."""
    principal = tmp_path / "principal"
    _make_git_repo(principal)
    worktree = tmp_path / "wt"
    _git("worktree", "add", "-q", "-b", "fixbranch", str(worktree), cwd=principal)

    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(_toml_with_addons(principal), encoding="utf-8")
    env = _base_env(home, toml)

    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral",
              "--no-create", "--ports", "0", cwd=str(worktree))

    assert p.returncode != 0, (
        "acquire from a linked worktree of the catalog's own repo must refuse "
        f"the principal-checkout default, not silently emit it.\n"
        f"stdout={p.stdout!r}\nstderr={p.stderr!r}"
    )
    assert "ALLOC_ADDONS_PATH" not in p.stdout, (
        "a refused acquire must not also emit a (wrong) ALLOC_ADDONS_PATH"
    )
    assert os.path.realpath(str(principal)) in p.stderr
    assert os.path.realpath(str(worktree)) in p.stderr


@requires_git
def test_addons_path_override_bypasses_the_worktree_mismatch_refusal(tmp_path):
    """The explicit override is exactly what the guard demands - it must
    always be honored, never re-refused."""
    principal = tmp_path / "principal"
    _make_git_repo(principal)
    worktree = tmp_path / "wt"
    _git("worktree", "add", "-q", "-b", "fixbranch", str(worktree), cwd=principal)

    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(_toml_with_addons(principal), encoding="utf-8")
    env = _base_env(home, toml)

    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral",
              "--no-create", "--ports", "0",
              "--addons-path-override", str(worktree), cwd=str(worktree))

    assert p.returncode == 0, p.stderr
    assert f"ALLOC_ADDONS_PATH={str(worktree)!r}" in p.stdout or str(worktree) in p.stdout


@requires_git
def test_acquire_from_the_principal_checkout_itself_is_not_refused(tmp_path):
    """Baseline: running from the checkout the catalog actually declares must
    stay byte-for-byte unaffected - the guard must never fire on the
    unmodified common case."""
    principal = tmp_path / "principal"
    _make_git_repo(principal)

    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(_toml_with_addons(principal), encoding="utf-8")
    env = _base_env(home, toml)

    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral",
              "--no-create", "--ports", "0", cwd=str(principal))

    assert p.returncode == 0, p.stderr
    assert str(principal) in p.stdout


@requires_git
def test_acquire_from_an_unrelated_git_repo_is_not_refused(tmp_path):
    """A caller working in a totally unrelated git repo (no shared history
    with any addons_path entry) must never trip the guard - it is not this
    check's business."""
    principal = tmp_path / "principal"
    _make_git_repo(principal)
    unrelated = tmp_path / "unrelated"
    _make_git_repo(unrelated)

    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(_toml_with_addons(principal), encoding="utf-8")
    env = _base_env(home, toml)

    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral",
              "--no-create", "--ports", "0", cwd=str(unrelated))

    assert p.returncode == 0, p.stderr
    assert str(principal) in p.stdout


@requires_git
def test_readonly_mode_is_never_blocked_by_the_worktree_mismatch_guard(tmp_path):
    """readonly builds nothing - it only surfaces the running instance's
    coordinates - so the false-green class does not apply; the guard must
    stay scoped to modes that actually drive a build."""
    principal = tmp_path / "principal"
    _make_git_repo(principal)
    worktree = tmp_path / "wt"
    _git("worktree", "add", "-q", "-b", "fixbranch", str(worktree), cwd=principal)

    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(_toml_with_addons(principal), encoding="utf-8")
    env = _base_env(home, toml)

    p = _run(env, "acquire", "--series", "17.0", "--mode", "readonly", cwd=str(worktree))
    assert p.returncode == 0, p.stderr


# --------------------------------------------------------------------------- #
# Part 2 - reap-orphans: pure decision-function tests (no I/O, no Postgres)
# --------------------------------------------------------------------------- #
def test_is_ephemeral_shaped_matches_only_the_known_prefix_shape():
    alloc = _import_allocator()
    assert alloc._is_ephemeral_shaped("odoo_17_0_t_deadbeef", ["odoo_17_0"])
    assert not alloc._is_ephemeral_shaped("odoo_17_0", ["odoo_17_0"]), (
        "a bare declared db_name must NEVER match the ephemeral shape"
    )
    assert not alloc._is_ephemeral_shaped("odoo_17_0_t_deadbeefzz", ["odoo_17_0"]), (
        "the hex suffix must be exactly 8 chars"
    )
    assert not alloc._is_ephemeral_shaped("some_other_db", ["odoo_17_0"])


def test_reap_candidates_predicate_naming_shape_lease_and_age_all_three_gate():
    alloc = _import_allocator()
    dbs = [
        {"name": "odoo_17_0_t_aaaaaaaa", "age_s": 200000},   # candidate: shaped, unleased, old
        {"name": "odoo_17_0_t_bbbbbbbb", "age_s": 200000},   # leased -> not our business
        {"name": "odoo_17_0_t_cccccccc", "age_s": 10},       # too young
        {"name": "odoo_17_0_t_dddddddd", "age_s": None},     # unmeasurable -> fail closed
        {"name": "not_ephemeral_shaped", "age_s": 200000},   # wrong shape entirely
    ]
    leased = {"odoo_17_0_t_bbbbbbbb"}
    candidates, skipped = alloc._reap_candidates(dbs, leased, ["odoo_17_0"], min_age_s=86400)

    cand_names = {d["name"] for d in candidates}
    assert cand_names == {"odoo_17_0_t_aaaaaaaa"}

    skipped_names = {n for n, _ in skipped}
    assert skipped_names == {"odoo_17_0_t_cccccccc", "odoo_17_0_t_dddddddd"}, (
        "a leased or wrongly-shaped db must appear in NEITHER list - it is not "
        "this command's business at all"
    )
    reasons = dict(skipped)
    assert "too young" in reasons["odoo_17_0_t_cccccccc"]
    assert "unknown" in reasons["odoo_17_0_t_dddddddd"]


def test_reap_candidates_returns_empty_when_nothing_qualifies():
    alloc = _import_allocator()
    dbs = [{"name": "odoo_17_0", "age_s": 999999}]  # the declared DB itself
    candidates, skipped = alloc._reap_candidates(dbs, set(), ["odoo_17_0"], min_age_s=1)
    assert candidates == []
    assert skipped == []


# --------------------------------------------------------------------------- #
# Part 3 - reap-orphans: CLI wiring, via fake psql/dropdb stubs (no real PG)
# --------------------------------------------------------------------------- #
def _write_stub(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _make_fake_psql(tmp_path, db_names, ages, sizes) -> Path:
    """A fake `psql` that answers three query shapes by sniffing the LAST argv
    token (the `-tAc` query text): the 'list non-template databases' query,
    the pg_stat_file age probe, and the pg_database_size probe. `ages`/`sizes`
    map db name -> value; a name ABSENT from the map makes that probe FAIL
    (non-zero exit, empty stdout) - simulating an unmeasurable value."""
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    psql = bindir / "psql"
    names_blob = "\n".join(db_names)

    def _case_block(mapping):
        lines = []
        for name, val in mapping.items():
            lines.append(f'      "{name}") echo "{val}"; exit 0 ;;')
        return "\n".join(lines)

    script = f"""\
last=""
for a in "$@"; do last="$a"; done
case "$last" in
  *"pg_database WHERE datistemplate"*)
    cat <<'PSQL_EOF'
{names_blob}
PSQL_EOF
    exit 0
    ;;
  *"pg_stat_file"*)
    name=$(echo "$last" | sed -n "s/.*datname = '\\([^']*\\)'.*/\\1/p")
    case "$name" in
{_case_block(ages)}
      *) exit 1 ;;
    esac
    ;;
  *"pg_database_size"*)
    name=$(echo "$last" | sed -n "s/.*pg_database_size('\\([^']*\\)').*/\\1/p")
    case "$name" in
{_case_block(sizes)}
      *) exit 1 ;;
    esac
    ;;
  *)
    exit 1
    ;;
esac
"""
    _write_stub(psql, script)
    return bindir


def _make_fake_dropdb(bindir: Path, calls_file: Path) -> None:
    dropdb = bindir / "dropdb"
    _write_stub(dropdb, f'echo "$@" >> "{calls_file}"\nexit 0\n')


CATALOG_TOML = """\
[[instance]]
series = "17.0"
addons_path = ["/srv/odoo/addons"]
http_port = 8069
db_name = "odoo_17_0"
db_name_prefix = "odoo_17_0"
db_host = "localhost"
db_user = "odoo"
"""


def _reap_env(tmp_path, home, toml, bindir):
    e = dict(os.environ)
    e["ODOO_AI_HOME"] = str(home)
    e["ODOO_AI_INSTANCES"] = str(toml)
    e["HOME"] = str(home)
    e["PATH"] = f"{bindir}:{e['PATH']}"
    return e


def test_reap_orphans_lists_an_old_unleased_ephemeral_db_as_a_candidate(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(CATALOG_TOML, encoding="utf-8")
    bindir = _make_fake_psql(
        tmp_path,
        db_names=["odoo_17_0_t_deadbeef", "odoo_17_0", "postgres"],
        ages={"odoo_17_0_t_deadbeef": 200000},
        sizes={"odoo_17_0_t_deadbeef": 104857600},
    )
    env = _reap_env(tmp_path, home, toml, bindir)

    p = _run(env, "reap-orphans")
    assert p.returncode == 0, p.stderr
    assert "REAP_CANDIDATE" in p.stdout and "odoo_17_0_t_deadbeef" in p.stdout
    assert "REAP_DROPPED" not in p.stdout, "list-only (no --yes) must never drop"


def test_reap_orphans_default_is_list_only_and_never_invokes_dropdb(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(CATALOG_TOML, encoding="utf-8")
    bindir = _make_fake_psql(
        tmp_path, db_names=["odoo_17_0_t_deadbeef"],
        ages={"odoo_17_0_t_deadbeef": 200000},
        sizes={"odoo_17_0_t_deadbeef": 1000},
    )
    calls = tmp_path / "dropdb-calls.log"
    _make_fake_dropdb(bindir, calls)
    env = _reap_env(tmp_path, home, toml, bindir)

    p = _run(env, "reap-orphans")
    assert p.returncode == 0, p.stderr
    assert not calls.exists(), "dropdb must NEVER run without --yes"


def test_reap_orphans_yes_drops_the_candidate_and_reports_it(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(CATALOG_TOML, encoding="utf-8")
    bindir = _make_fake_psql(
        tmp_path, db_names=["odoo_17_0_t_deadbeef"],
        ages={"odoo_17_0_t_deadbeef": 200000},
        sizes={"odoo_17_0_t_deadbeef": 1000},
    )
    calls = tmp_path / "dropdb-calls.log"
    _make_fake_dropdb(bindir, calls)
    env = _reap_env(tmp_path, home, toml, bindir)

    p = _run(env, "reap-orphans", "--yes")
    assert p.returncode == 0, p.stderr
    assert "REAP_DROPPED" in p.stdout and "odoo_17_0_t_deadbeef" in p.stdout
    assert calls.exists(), "dropdb must be invoked when --yes is passed"
    assert "odoo_17_0_t_deadbeef" in calls.read_text(encoding="utf-8")


def test_reap_orphans_never_touches_a_db_referenced_by_any_lease_even_stale(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(CATALOG_TOML, encoding="utf-8")
    bindir = _make_fake_psql(
        tmp_path, db_names=["odoo_17_0_t_leased1"],
        ages={"odoo_17_0_t_leased1": 999999},
        sizes={"odoo_17_0_t_leased1": 1000},
    )
    calls = tmp_path / "dropdb-calls.log"
    _make_fake_dropdb(bindir, calls)

    # Seed a STALE lease referencing this db_name - gc's job, never reap-orphans'.
    runtime = home / "runtime"
    runtime.mkdir(parents=True)
    now = int(time.time())
    (runtime / "leases.json").write_text(
        __import__("json").dumps({"schema_version": 2, "leases": [{
            "token": "ab" * 16, "mode": "ephemeral", "db_name": "odoo_17_0_t_leased1",
            "drop_on_release": True,
            "owner": {"host": socket.gethostname(), "pid": None,
                      "run_id": "old-run", "started_at": now - 999999},
            "ttl_s": 1, "heartbeat_at": now - 999999,
            "_pg": {"host": "localhost", "user": "odoo"},
        }]}), encoding="utf-8",
    )
    env = _reap_env(tmp_path, home, toml, bindir)

    p = _run(env, "reap-orphans", "--yes")
    assert p.returncode == 0, p.stderr
    assert "odoo_17_0_t_leased1" not in p.stdout, (
        "a db referenced by ANY lease (even stale) must be skipped by "
        "reap-orphans - that is gc's job exclusively"
    )
    assert not calls.exists(), "a leased db must never reach dropdb via reap-orphans"


def test_reap_orphans_skips_too_young_candidate_without_dropping(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(CATALOG_TOML, encoding="utf-8")
    bindir = _make_fake_psql(
        tmp_path, db_names=["odoo_17_0_t_0000a001"],
        ages={"odoo_17_0_t_0000a001": 10},  # 10s old
        sizes={"odoo_17_0_t_0000a001": 1000},
    )
    calls = tmp_path / "dropdb-calls.log"
    _make_fake_dropdb(bindir, calls)
    env = _reap_env(tmp_path, home, toml, bindir)

    p = _run(env, "reap-orphans", "--yes", "--min-age-s", "86400")
    assert p.returncode == 0, p.stderr
    assert "REAP_SKIPPED" in p.stdout and "odoo_17_0_t_0000a001" in p.stdout
    assert "REAP_CANDIDATE" not in p.stdout
    assert not calls.exists(), "a too-young db must never be dropped, even with --yes"


def test_reap_orphans_skips_unmeasurable_age_fail_closed_even_with_yes(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(CATALOG_TOML, encoding="utf-8")
    bindir = _make_fake_psql(
        tmp_path, db_names=["odoo_17_0_t_00000fee"],
        ages={},  # age probe fails for every name -> unmeasurable
        sizes={"odoo_17_0_t_00000fee": 1000},
    )
    calls = tmp_path / "dropdb-calls.log"
    _make_fake_dropdb(bindir, calls)
    env = _reap_env(tmp_path, home, toml, bindir)

    p = _run(env, "reap-orphans", "--yes")
    assert p.returncode == 0, p.stderr
    assert "REAP_SKIPPED" in p.stdout and "odoo_17_0_t_00000fee" in p.stdout
    assert "unknown" in p.stdout
    assert not calls.exists(), "an unmeasurable age must fail closed, even with --yes"


def test_reap_orphans_never_lists_a_declared_instance_db_name(tmp_path):
    """The declared db_name itself ('odoo_17_0') must never be a candidate or
    even a skip-reason line - it is not ephemeral-shaped, full stop."""
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(CATALOG_TOML, encoding="utf-8")
    bindir = _make_fake_psql(
        tmp_path, db_names=["odoo_17_0"],
        ages={"odoo_17_0": 999999},
        sizes={"odoo_17_0": 1000},
    )
    env = _reap_env(tmp_path, home, toml, bindir)

    p = _run(env, "reap-orphans")
    assert p.returncode == 0, p.stderr
    assert "odoo_17_0" not in p.stdout.replace("odoo_17_0_", "")


def test_reap_orphans_reports_an_unreachable_cluster_without_crashing(tmp_path):
    """No psql at all on PATH -> the cluster is unreachable; reap-orphans must
    report that and exit 0 (a diagnostic condition, not a crash), never
    silently claim zero orphans."""
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(CATALOG_TOML, encoding="utf-8")
    env = dict(os.environ)
    env["ODOO_AI_HOME"] = str(home)
    env["ODOO_AI_INSTANCES"] = str(toml)
    env["HOME"] = str(home)
    env["PATH"] = "/nonexistent-empty-bin-dir"

    p = _run(env, "reap-orphans")
    assert p.returncode == 0, p.stderr
    assert "could not reach" in p.stderr


# --------------------------------------------------------------------------- #
# Part 4 - `acquire --help` never allocates a lease (behavioral, not just an
# exit-code check) - regression guard for the exact shape issue text names.
# --------------------------------------------------------------------------- #
def test_acquire_help_never_creates_a_lease_row(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    toml = tmp_path / "instances.toml"
    toml.write_text(CATALOG_TOML, encoding="utf-8")
    env = _base_env(home, toml)

    p = _run(env, "acquire", "--series", "17.0", "--mode", "ephemeral", "--help")
    assert p.returncode != 0

    leases_file = home / "runtime" / "leases.json"
    assert not leases_file.exists(), (
        "acquire --help must never allocate a lease - reading the usage text "
        "must not consume a database name or port from the pool"
    )
