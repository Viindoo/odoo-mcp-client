"""Guard: `50-instance-spinup.sh apply` serves the tree the LEASE reserved, and SAYS which one.

Business rules protected here:

ST1 - **the bound lease outranks the static catalog row.** A caller that acquired its lease with
  `allocator.py acquire --addons-path-override <worktree list>` is deliberately serving a
  DIFFERENT checkout than the one `instances.toml` declares. `cmd_apply` used to re-derive
  `addons_path` from the catalog row alone, so the listening server it launched served the
  PRINCIPAL checkout - and nothing said so. That is the one failure direction that still reports
  success: the port answers 200, the tests/QA/visual pass all run, and the green means nothing
  because it was measured against code that is not the code under verification.

ST2 - **a resolved server-wide module set is not dropped.** The `--load` set a caller resolved
  (any distribution's server-wide module) has to reach the generated conf's `server_wide_modules`
  key - Odoo's `--load` dest, comma-separated on every indexed series. There was no passthrough at
  all, so the launch silently fell back to Odoo's own default.

ST3 - **the served tree is OBSERVABLE without parsing Odoo's log.** `apply` prints
  `SERVED_ADDONS_PATH` / `SERVED_ADDONS_SOURCE` / `SERVED_SERVER_WIDE_MODULES` on the same stdout
  KEY=value channel it already uses for `LOG_PATH`, so a caller can verify the tree instead of
  hunting for the server's own `addons paths: [...]` startup line.

ST4 - **an unresolvable lease REFUSES, loudly, before launch.** When `--alloc-token` names a lease
  this run cannot read, the two candidate trees cannot be told apart - so nothing is launched. A
  loud refusal is strictly better than a quiet wrong tree.

Non-regressions asserted at the same time, because a fix that breaks these is not a fix:
  - NO lease at all: the catalog row IS the right answer and must still work, unchanged.
  - a lease whose `addons_path` EQUALS the catalog row: not a conflict, no refusal.

Every assertion here is on the GENERATED CONF and on the script's own machine output after a REAL
`50-instance-spinup.sh apply` run - never on prose - because the defect was a conf fact that the
script's human-readable output described as success the whole time.

Offline: no PostgreSQL, no real Odoo, no network. odoo-bin / python / curl / pg_isready are stubs
from `test_conf_lifecycle.py`'s Sandbox, reused rather than re-implemented (it already drives the
real script deep enough to write the conf and launch the stand-in server).
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from shutil import which

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
ALLOCATOR = PLUGIN / "scripts" / "lib" / "allocator.py"

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_conf_lifecycle import Sandbox  # noqa: E402

requires_bash = pytest.mark.skipif(which("bash") is None, reason="bash not available")

# The exclusive-running coordinates a real caller would have got from the allocator. Distinct from
# the Sandbox's declared db/port so a run that ignored the overrides is visible.
EXCL_DB = "odoo_test_excl"
EXCL_PORT = 18271

# Deliberately generic module names: the mechanism is distribution-agnostic, so no test may pin a
# module that only one Odoo distribution ships.
LOAD_SET = "mod_alpha,mod_beta"


@pytest.fixture
def sandbox(tmp_path):
    sb = Sandbox(tmp_path)
    try:
        yield sb
    finally:
        sb.reap()


@pytest.fixture
def worktree_addons(tmp_path) -> Path:
    """A second, EXISTING addons dir standing in for a linked worktree's re-rooted tree.

    It must exist: `allocator.py` refuses an `--addons-path-override` naming a non-existent
    directory, which is itself part of why the override is trustworthy.
    """
    path = tmp_path / "worktree-checkout" / "addons"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _acquire(sandbox: Sandbox, *extra: str) -> str:
    """Acquire a real exclusive lease through the real allocator; return its token.

    `--no-create` keeps the acquire off the DB-capability gate: this file is about which TREE a
    lease reserves, not about cluster privileges.
    """
    res = subprocess.run(
        [
            sys.executable, str(ALLOCATOR), "acquire",
            "--series", "17.0", "--mode", "exclusive",
            "--db-name", EXCL_DB, "--run-id", "run-served-tree", "--no-create",
            *extra,
        ],
        capture_output=True, text=True, env=sandbox.env(), timeout=60,
    )
    assert res.returncode == 0, f"acquire failed:\n{res.stdout}\n{res.stderr}"
    token = next(
        (
            line.split("=", 1)[1].strip().strip("'")
            for line in res.stdout.splitlines()
            if line.startswith("ALLOC_TOKEN=")
        ),
        "",
    )
    assert token, f"acquire must mint a token:\n{res.stdout}"
    return token


def _use_array_form_addons_path(sandbox: Sandbox) -> None:
    """Declare the catalog's `addons_path` as a TOML ARRAY - the shape `40-instance-profile.sh`
    records in a real catalog.

    Load-bearing for any test that compares a LEASE's recorded addons_path against the catalog
    row: `allocator.py`'s `_resolve_addons_csv` runs the catalog value through
    `instances_io.join_addons_path`, which comma-joins a LIST but iterates a bare STRING
    character by character - so a scalar `addons_path = "/a/b"` is recorded on the lease as
    `/,a,/,b`. `instances_io`'s own reader normalizes both shapes (`_addons_path_list`), so the
    two producers disagree on the scalar shape only. That is a defect in `allocator.py`, not in
    the script under test here; these tests pin the array shape so they measure the resolution,
    and `test_a_lease_row_that_is_not_a_directory_list_falls_back_loudly` below covers what the
    script does when it meets the scalar-shape damage.
    """
    text = sandbox.toml.read_text(encoding="utf-8")
    replaced = text.replace(
        f'addons_path = "{sandbox.addons}"', f'addons_path = ["{sandbox.addons}"]'
    )
    assert replaced != text, "the sandbox catalog no longer declares a scalar addons_path"
    sandbox.toml.write_text(replaced, encoding="utf-8")


def _apply_exclusive(sandbox: Sandbox, *extra: str) -> subprocess.CompletedProcess:
    return sandbox.apply(
        "--exclusive", "--db-name", EXCL_DB,
        "--http-port", str(EXCL_PORT), "--port-key", "http_port",
        *extra,
    )


def _conf_text(res: subprocess.CompletedProcess) -> str:
    """The conf the script SAYS it generated, read off disk.

    Going through the script's own `Generated conf:` line (rather than recomputing the path)
    keeps this test honest about the file the launch actually used.
    """
    out = res.stdout + res.stderr
    lines = [ln for ln in res.stdout.splitlines() if "Generated conf:" in ln]
    assert lines, f"no 'Generated conf:' line on stdout\n{out}"
    path = Path(lines[-1].split("Generated conf:", 1)[1].strip())
    assert path.is_file(), f"the generated conf is missing at {path}\n{out}"
    return path.read_text(encoding="utf-8")


def _conf_value(conf: str, key: str) -> str | None:
    for line in conf.splitlines():
        if line.strip().startswith(f"{key} "):
            return line.split("=", 1)[1].strip()
    return None


def _facts(res: subprocess.CompletedProcess) -> dict[str, str]:
    """The KEY=value machine facts `apply` prints on stdout."""
    keys = ("SERVED_ADDONS_PATH", "SERVED_ADDONS_SOURCE", "SERVED_SERVER_WIDE_MODULES")
    found: dict[str, str] = {}
    for line in res.stdout.splitlines():
        for key in keys:
            if line.startswith(f"{key}="):
                found[key] = line.split("=", 1)[1].strip()
    return found


# ---------------------------------------------------------------------------
# ST1 - the lease's tree wins over the catalog row
# ---------------------------------------------------------------------------


@requires_bash
def test_lease_addons_path_override_beats_the_catalog_row(sandbox, worktree_addons):
    """ST1 - the conf must carry the tree the LEASE reserved, and NOT the catalog row.

    This is the defect stated as a filesystem fact: before the fix the generated conf's
    `addons_path` was the catalog entry, so the launched listener served the principal checkout
    while the caller believed it was serving its worktree.
    """
    token = _acquire(sandbox, "--addons-path-override", str(worktree_addons))
    res = _apply_exclusive(sandbox, "--alloc-token", token)
    out = res.stdout + res.stderr
    assert res.returncode == 0, f"a well-specified exclusive apply must succeed\n{out}"

    conf = _conf_text(res)
    served = _conf_value(conf, "addons_path")
    assert served == str(worktree_addons), (
        "the generated conf must serve the addons_path the BOUND LEASE reserved "
        f"({worktree_addons}), not the instances.toml catalog row. Got: {served!r}\n{conf}"
    )
    assert str(sandbox.addons) not in conf, (
        "the catalog row must NOT survive anywhere in the conf once a lease reserved a "
        f"different tree - a launch against {sandbox.addons} is the silent wrong-tree green\n"
        f"{conf}"
    )


@requires_bash
def test_explicit_addons_path_argument_outranks_the_lease(sandbox, worktree_addons, tmp_path):
    """ST1 (precedence) - an explicit `--addons-path` is the caller stating the tree, so it wins
    over the lease as well as over the catalog."""
    stated = tmp_path / "stated-checkout" / "addons"
    stated.mkdir(parents=True, exist_ok=True)
    token = _acquire(sandbox, "--addons-path-override", str(worktree_addons))

    res = _apply_exclusive(sandbox, "--alloc-token", token, "--addons-path", str(stated))
    out = res.stdout + res.stderr
    assert res.returncode == 0, out

    conf = _conf_text(res)
    assert _conf_value(conf, "addons_path") == str(stated), (
        f"--addons-path must outrank the lease. Got: {_conf_value(conf, 'addons_path')!r}\n{conf}"
    )
    assert _facts(res).get("SERVED_ADDONS_SOURCE") == "argument", (
        f"the reported source must name the argument rung\n{out}"
    )


# ---------------------------------------------------------------------------
# ST2 - the --load set reaches the conf
# ---------------------------------------------------------------------------


@requires_bash
def test_load_set_reaches_the_generated_conf_as_server_wide_modules(sandbox):
    """ST2 - `--load <modules>` must land in the conf as `server_wide_modules`.

    With no passthrough the resolved set was dropped and the launch fell back to Odoo's own
    default, which no output mentioned.
    """
    res = sandbox.apply("--load", LOAD_SET)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out

    conf = _conf_text(res)
    assert _conf_value(conf, "server_wide_modules") == LOAD_SET, (
        "the conf must carry the caller's server-wide module set verbatim as "
        f"`server_wide_modules = {LOAD_SET}`. Got: "
        f"{_conf_value(conf, 'server_wide_modules')!r}\n{conf}"
    )


@requires_bash
def test_load_set_is_normalized_not_passed_through_malformed(sandbox):
    """ST2 - a hand-spaced list must reach Odoo as a clean comma list, not as module names with
    leading spaces that no import can resolve."""
    res = sandbox.apply("--load", " mod_alpha , mod_beta ,")
    assert res.returncode == 0, res.stdout + res.stderr
    conf = _conf_text(res)
    assert _conf_value(conf, "server_wide_modules") == LOAD_SET, (
        f"expected the normalized list {LOAD_SET!r}\n{conf}"
    )


@requires_bash
def test_a_load_flag_naming_no_module_is_blocked_before_launch(sandbox):
    """ST2 (fail-loud) - `--load` that names no module must BLOCK. A caller that resolved a
    server-wide set and silently got Odoo's default is the exact drop this passthrough exists to
    prevent, so an empty set is refused rather than quietly ignored."""
    res = sandbox.apply("--load", " , ")
    out = res.stdout + res.stderr
    assert res.returncode != 0, f"an empty --load must be refused\n{out}"
    assert "BLOCKED" in out, f"expected the file's BLOCKED refusal idiom\n{out}"
    assert not sandbox.launch_log.exists(), f"nothing may launch on a refusal\n{out}"


@requires_bash
def test_no_load_flag_writes_no_server_wide_modules_key(sandbox):
    """ST2 (no fabrication) - with no `--load`, the key must be ABSENT so Odoo's own per-series
    default applies. Writing a hardcoded default here would pin one series' default onto all of
    them."""
    res = sandbox.apply()
    assert res.returncode == 0, res.stdout + res.stderr
    conf = _conf_text(res)
    assert "server_wide_modules" not in conf, (
        f"no --load means no server_wide_modules key at all\n{conf}"
    )
    assert _facts(res).get("SERVED_SERVER_WIDE_MODULES") == "", (
        "the reported module set must be empty when none was requested"
    )


# ---------------------------------------------------------------------------
# ST3 - the served tree is reported
# ---------------------------------------------------------------------------


@requires_bash
def test_apply_reports_the_served_tree_as_machine_output(sandbox, worktree_addons):
    """ST3 - the resolved tree, its source rung, and the server-wide module set must all appear as
    KEY=value stdout facts, so a caller verifies the served tree without parsing Odoo's log."""
    token = _acquire(sandbox, "--addons-path-override", str(worktree_addons))
    res = _apply_exclusive(sandbox, "--alloc-token", token, "--load", LOAD_SET)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out

    facts = _facts(res)
    assert facts.get("SERVED_ADDONS_PATH") == str(worktree_addons), (
        "SERVED_ADDONS_PATH must name the tree actually served (the lease's), so a caller can "
        f"verify it from this output alone. Got: {facts!r}\n{out}"
    )
    assert facts.get("SERVED_ADDONS_SOURCE") == "lease", (
        f"SERVED_ADDONS_SOURCE must name the rung that won (lease). Got: {facts!r}\n{out}"
    )
    assert facts.get("SERVED_SERVER_WIDE_MODULES") == LOAD_SET, (
        f"SERVED_SERVER_WIDE_MODULES must name the module set served. Got: {facts!r}\n{out}"
    )
    # The reported fact and the conf the server was handed must be the SAME value - a report that
    # can disagree with the launch is not observability.
    conf = _conf_text(res)
    assert _conf_value(conf, "addons_path") == facts.get("SERVED_ADDONS_PATH"), (
        f"the reported served tree must equal the conf's addons_path\n{conf}"
    )
    assert _conf_value(conf, "server_wide_modules") == facts.get("SERVED_SERVER_WIDE_MODULES"), (
        f"the reported module set must equal the conf's server_wide_modules\n{conf}"
    )


# ---------------------------------------------------------------------------
# ST4 - an unresolvable lease refuses
# ---------------------------------------------------------------------------


@requires_bash
def test_an_unreadable_lease_token_blocks_before_launch(sandbox):
    """ST4 - `--alloc-token` naming no live lease row means the tree is UNRESOLVED: refuse, do not
    fall back to the catalog row."""
    res = _apply_exclusive(sandbox, "--alloc-token", "0" * 32)
    out = res.stdout + res.stderr
    assert res.returncode != 0, f"an unreadable lease must be refused\n{out}"
    assert "BLOCKED" in out, f"expected the file's BLOCKED refusal idiom\n{out}"
    assert "alloc-token" in out, f"the refusal must name the flag that could not be resolved\n{out}"
    assert not sandbox.launch_log.exists(), (
        f"a refusal must launch NOTHING - a wrong tree already listening is the harm\n{out}"
    )
    assert sandbox.confs() == [], f"a refusal must write no conf\n{out}"


@requires_bash
def test_a_lease_naming_a_tree_that_is_gone_blocks_instead_of_serving_the_catalog(
    sandbox, worktree_addons
):
    """ST4 - a lease that reserved a REAL tree which is no longer on this host cannot be honoured,
    and the catalog row is NOT a substitute for it: substituting is precisely the wrong-tree green.
    So refuse, and say which tree is missing."""
    token = _acquire(sandbox, "--addons-path-override", str(worktree_addons))
    worktree_addons.rmdir()  # the worktree went away between acquire and apply

    res = _apply_exclusive(sandbox, "--alloc-token", token)
    out = res.stdout + res.stderr
    assert res.returncode != 0, f"a lease naming an absent tree must be refused\n{out}"
    assert "BLOCKED" in out, f"expected the file's BLOCKED refusal idiom\n{out}"
    assert str(worktree_addons) in out, f"the refusal must name the missing tree\n{out}"
    assert not sandbox.launch_log.exists(), f"nothing may launch on a refusal\n{out}"
    assert sandbox.confs() == [], f"a refusal must write no conf\n{out}"


@requires_bash
def test_an_addons_path_argument_naming_a_missing_directory_blocks(sandbox, tmp_path):
    """ST4 - a stated tree is checked before launch. A mistyped path would otherwise start a
    server that finds no module under it, which reads as broken code rather than a typo."""
    res = sandbox.apply("--addons-path", str(tmp_path / "never-created"))
    out = res.stdout + res.stderr
    assert res.returncode != 0, f"a non-existent --addons-path must be refused\n{out}"
    assert "BLOCKED" in out, f"expected the file's BLOCKED refusal idiom\n{out}"
    assert not sandbox.launch_log.exists(), f"nothing may launch on a refusal\n{out}"


@requires_bash
def test_a_lease_row_that_is_not_a_directory_list_falls_back_loudly(sandbox):
    """ST3/ST4 boundary - a lease row whose `addons_path` is not a directory list at all makes NO
    statement about any tree, so it cannot be served and cannot be refused on: the catalog row
    stands, a warning says so, and SERVED_ADDONS_SOURCE reports `catalog` rather than claiming the
    caller got the lease's tree.

    Reachable today because `allocator.py` records a SCALAR catalog `addons_path` character-joined
    (see `_use_array_form_addons_path`); the point of this test is that the script degrades
    truthfully whatever a producer wrote, not that the producer is correct.
    """
    token = _acquire(sandbox)  # scalar-form catalog left in place on purpose
    res = _apply_exclusive(sandbox, "--alloc-token", token)
    out = res.stdout + res.stderr
    assert res.returncode == 0, f"an unusable lease row must not break the spin-up\n{out}"
    facts = _facts(res)
    assert facts.get("SERVED_ADDONS_PATH") == str(sandbox.addons), (
        f"the catalog row must be what is served - and reported\n{out}"
    )
    assert facts.get("SERVED_ADDONS_SOURCE") == "catalog", (
        "the reported source must NOT claim the lease's tree was served when it was not: "
        f"{facts!r}\n{out}"
    )
    assert "Warning" in res.stderr and "CATALOG ROW" in res.stderr, (
        f"the fallback must be stated out loud on stderr\n{res.stderr}"
    )
    conf = _conf_text(res)
    assert _conf_value(conf, "addons_path") == str(sandbox.addons), conf


@requires_bash
def test_docker_run_mode_refuses_an_override_it_cannot_honour(sandbox, worktree_addons):
    """ST4 (no false report) - this step only hands a generated conf to odoo-bin on the SOURCE
    path, so a compose-launched instance cannot honour a served-tree override. Refuse rather than
    report a tree that is not served."""
    sandbox.toml.write_text(
        sandbox.toml.read_text(encoding="utf-8").replace(
            'run_mode = "source"', 'run_mode = "docker"'
        ),
        encoding="utf-8",
    )
    token = _acquire(sandbox, "--addons-path-override", str(worktree_addons))
    res = _apply_exclusive(sandbox, "--alloc-token", token)
    out = res.stdout + res.stderr
    assert res.returncode != 0, f"docker + a served-tree override must be refused\n{out}"
    assert "BLOCKED" in out, f"expected the file's BLOCKED refusal idiom\n{out}"
    assert "docker" in out, f"the refusal must name the run mode that cannot honour it\n{out}"
    assert not sandbox.launch_log.exists(), f"nothing may launch on a refusal\n{out}"


# ---------------------------------------------------------------------------
# MUST-NOT-CATCH - the cases where the catalog row is the RIGHT answer
# ---------------------------------------------------------------------------


@requires_bash
def test_with_no_lease_the_catalog_row_is_still_served(sandbox):
    """MUST-NOT-CATCH - no lease, no argument: the declared/shared spin-up is unchanged. A guard
    that turned this red would have broken every existing caller."""
    res = sandbox.apply()
    out = res.stdout + res.stderr
    assert res.returncode == 0, f"the plain declared spin-up must still work\n{out}"
    conf = _conf_text(res)
    assert _conf_value(conf, "addons_path") == str(sandbox.addons), (
        f"with no lease the catalog row IS the tree to serve\n{conf}"
    )
    assert _facts(res).get("SERVED_ADDONS_SOURCE") == "catalog", (
        f"the reported source must name the catalog rung\n{out}"
    )


@requires_bash
def test_a_lease_matching_the_catalog_row_is_not_a_conflict(sandbox):
    """MUST-NOT-CATCH - a lease acquired with NO override records the catalog row itself. Nothing
    differs, so nothing may be refused and the served tree is the catalog row."""
    _use_array_form_addons_path(sandbox)
    token = _acquire(sandbox)
    res = _apply_exclusive(sandbox, "--alloc-token", token)
    out = res.stdout + res.stderr
    assert res.returncode == 0, f"a lease that agrees with the catalog must not be refused\n{out}"
    conf = _conf_text(res)
    assert _conf_value(conf, "addons_path") == str(sandbox.addons), (
        f"the served tree must be the (identical) catalog row\n{conf}"
    )
    assert _facts(res).get("SERVED_ADDONS_PATH") == str(sandbox.addons), (
        "the reported served tree must name the catalog row the lease agrees with. Got: "
        f"{_facts(res)!r}\n{out}"
    )


# ---------------------------------------------------------------------------
# Separator SSOT - the served value is canonicalized, not re-spelled
# ---------------------------------------------------------------------------


@requires_bash
def test_a_colon_joined_override_reaches_the_conf_comma_joined(sandbox, tmp_path):
    """The conf key Odoo parses is COMMA-separated on every indexed series. A caller (or a legacy
    producer) handing over a colon-joined list must still reach the conf comma-joined - via the
    same splitter every other consumer uses, never a second hand-rolled conversion."""
    second = tmp_path / "second-checkout" / "addons"
    second.mkdir(parents=True, exist_ok=True)
    res = sandbox.apply("--addons-path", f"{sandbox.addons}:{second}")
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    conf = _conf_text(res)
    assert _conf_value(conf, "addons_path") == f"{sandbox.addons},{second}", (
        f"the conf must carry a comma-joined addons_path\n{conf}"
    )


# ---------------------------------------------------------------------------
# Probe corpus - the guard's own MUST-CATCH / MUST-NOT-CATCH shapes, asserted on text so the
# resolution CONTRACT cannot be quietly reverted to a catalog-only re-derivation.
# ---------------------------------------------------------------------------


def test_cmd_apply_has_exactly_one_addons_path_writer():
    """SSOT - the conf's `addons_path` line must be written in exactly ONE place, from the
    resolved value. A second writer is how the catalog row crept back in.
    """
    text = (PLUGIN / "scripts" / "setup-steps" / "50-instance-spinup.sh").read_text(
        encoding="utf-8"
    )
    writers = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith('echo "addons_path = ')
    ]
    assert len(writers) == 1, (
        "exactly one conf writer for addons_path is expected, found "
        f"{len(writers)}: {writers}"
    )
    assert writers[0] == 'echo "addons_path = ${INST_ADDONS_PATH:-}"', (
        "the single writer must emit the RESOLVED value (INST_ADDONS_PATH is reassigned by the "
        f"served-tree resolution), got: {writers[0]!r}"
    )
