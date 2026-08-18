"""Guard: `db_name` is validated BEFORE it keys any Tier-1 artifact filename.

Business rule protected: `db_name` (resolved at `50-instance-spinup.sh` from a CLI arg,
`instances.toml`, or the literal default `"odoo"` - operator-supplied config, never
attacker-controlled input) keys THREE artifact-filename families that `state_reclaim.sh` owns:
`<db>-<UTC-ts>.log`, `<db>-<UTC-ts>.findings.md`, `<db>-<port>.conf`. Nothing downstream ever
validated it. Two concrete failure modes this closes:

  FM1 - a `/` in db_name makes the generated conf's path escape `$ODOO_AI_HOME/conf/` (a nested
        or `..`-relative path). The sweep only ever looks `-maxdepth 1` inside that dir, so an
        artifact that lands outside it is invisible to the sweep FOREVER - permanently and
        unreclaimably leaked, the exact class of leak `state_reclaim.sh` exists to close.
  FM2 - a newline in db_name breaks the sweep's own lease guard: `prune_stale_run_artifacts`
        recovers the db name from a real filename and checks it with a LINE-oriented
        `grep -Fxq`. A db_name carrying an embedded newline splits that fixed-string pattern into
        multiple OR'd whole-line alternatives, so the comparison is against a FRAGMENT of the
        name rather than the whole name - it can miss a name that IS leased and let the sweep
        delete a LIVE instance's open conf.

The fix REJECTS an unusable name outright rather than sanitizing/slugging it: slugging would make
the artifact filename diverge from the real database name, and two distinct database names could
slug to the SAME filename - trading an unreclaimable leak for a silent cross-instance collision,
which is a regression, not a fix.

Accepted shape: Odoo's OWN database-manager pattern, MIRRORED rather than near-copied -
`addons/web/controllers/database.py` `DBNAME_PATTERN`, verified unchanged v9-v19 against the real
v9-v19 Odoo sources: `^[a-zA-Z0-9][a-zA-Z0-9_.-]+$`. So the first character must be alphanumeric,
every later character may also be underscore, hyphen or dot, and a name under two characters is
refused. A hyphen and an underscore are unconditionally safe in the interior
(`state_reclaim.sh`'s discriminator split is on the LAST hyphen in the basename, so any number of
internal hyphens/underscores round-trips) - a guard that caught either would break every existing
instance. Two consequences of mirroring instead of inventing: the dot is accepted, because Odoo
accepts it and it is never the sweep's split character; and a leading `-`/`.`/`_` or a
one-character name is REFUSED, because Odoo refuses it too - a name that cleared our gate and
then failed at database creation would be a gate that only moved the failure later.

SSOT for the class: `_DB_NAME_RE` in `state_reclaim.sh`, read by BOTH `validate_db_name` (the
pre-write gate) and `prune_stale_run_artifacts` (the sweep-side guard against a pre-existing bad
filename from before this validator existed - see the sweep tests below).

Offline: no PostgreSQL, no real Odoo, no network.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from shutil import which

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
STEP50 = PLUGIN / "scripts" / "setup-steps" / "50-instance-spinup.sh"
STATE_RECLAIM = PLUGIN / "scripts" / "lib" / "state_reclaim.sh"

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

# Reused, not re-implemented: test_conf_lifecycle.py's Sandbox already drives the REAL
# `50-instance-spinup.sh apply` far enough to reach the conf-write line (stubs odoo-bin, the
# python preflight AND the actual launch) - exactly the depth needed to prove a parent-directory
# escape BEHAVIOURALLY rather than by regex alone. See
# test_apply_prevents_a_genuine_parent_directory_escape_end_to_end below.
from test_conf_lifecycle import Sandbox  # noqa: E402

requires_bash = pytest.mark.skipif(which("bash") is None, reason="bash not available")

# The literal accepted-class spelling the refusal message must name. Kept as one constant here
# too (test-side SSOT) so a future re-wording of the message is a single edit, not a hunt.
ACCEPTED_CLASS_TEXT = "[A-Za-z0-9_.-]"


# ---------------------------------------------------------------------------
# Unit level: `validate_db_name` called directly (bash function, no script around it).
# ---------------------------------------------------------------------------


def _validate_db_name(name: str) -> subprocess.CompletedProcess:
    """Invoke `validate_db_name "$name"` in isolation, passing `name` through an env var so no
    shell ever re-parses it - a newline/space/glob probe must reach the function byte-for-byte,
    not get mangled by quoting."""
    env = dict(os.environ)
    env["DB_NAME_UNDER_TEST"] = name
    script = f'source "{STATE_RECLAIM}"; validate_db_name "$DB_NAME_UNDER_TEST"'
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=env, timeout=10,
    )


# MUST-CATCH: at least the five probes the task specifies, by shape.
_MUST_CATCH = [
    ("path escape", "db/x"),
    ("embedded newline", "foo\nbar"),
    ("embedded space", "foo bar"),
    ("empty name", ""),
    ("shell-glob character", "foo*bar"),
    # Extra rigor beyond the required minimum: a genuine parent-directory escape, and a
    # couple more glob/control characters that a narrower guard might miss.
    ("parent-directory escape", "../evil"),
    ("bracket glob character", "foo[bar]"),
    ("question-mark glob character", "foo?bar"),
    ("tab character", "foo\tbar"),
    # Mirroring Odoo's `DBNAME_PATTERN` rather than near-copying it means our gate refuses exactly
    # what Odoo refuses. These four were ACCEPTED by the earlier `^[A-Za-z0-9_.-]+$` spelling and
    # would each have failed later, at database creation, inside Odoo's own manager.
    ("leading hyphen", "-foo"),
    ("leading dot", ".foo"),
    ("leading underscore", "_foo"),
    ("dot-dot only", ".."),
    ("single character", "a"),
]


@requires_bash
@pytest.mark.parametrize("shape,name", _MUST_CATCH, ids=[s for s, _ in _MUST_CATCH])
def test_validate_db_name_refuses_every_must_catch_shape(shape, name):
    """Every shape Odoo's own `DBNAME_PATTERN` refuses, plus the shapes that break this file's
    artifact-filename families.

    `single character` MOVED here from MUST-NOT-CATCH when `_DB_NAME_RE` stopped being a near-copy
    of Odoo's pattern and became a mirror of it: `^[a-zA-Z0-9][a-zA-Z0-9_.-]+$` needs a first
    alphanumeric character AND at least one more after it, so Odoo itself rejects `"a"`. Accepting
    it here would only let the name clear our gate and then fail at database creation - the same
    reason `-foo`, `.foo`, `_foo` and `..` sit here rather than below.
    """
    res = _validate_db_name(name)
    assert res.returncode != 0, (
        f"validate_db_name must REFUSE a {shape} ({name!r}), returned 0 instead\n{res.stderr}"
    )
    assert "BLOCKED" in res.stderr, (
        f"a refusal must be loud (contain 'BLOCKED'), got:\n{res.stderr}"
    )


@requires_bash
def test_validate_db_name_refusal_names_both_character_classes():
    """The refusal message must name the OFFENDING class it saw and the ACCEPTED class - a bare
    'invalid' with no actionable detail is not enough to fix the name."""
    res = _validate_db_name("db/x")
    assert res.returncode != 0
    assert ACCEPTED_CLASS_TEXT in res.stderr, (
        f"the refusal must name the accepted class {ACCEPTED_CLASS_TEXT!r} verbatim:\n{res.stderr}"
    )
    assert "db/x" in res.stderr, (
        f"the refusal must echo the offending name back so the caller can see what was rejected:"
        f"\n{res.stderr}"
    )


# MUST-NOT-CATCH: plain names, and - explicitly - a hyphen AND an underscore together, since a
# guard that rejected either would break every existing instance.
_MUST_NOT_CATCH = [
    ("plain alnum", "odoo"),
    ("hyphen and underscore together", "foo-bar_baz"),
    ("existing fixture shape", "odoo_test"),
    ("widened: a dot, matching Odoo's own DBNAME_PATTERN", "foo.bar"),
    # A leading DIGIT stays accepted: Odoo's first-character class is `[a-zA-Z0-9]`, digits
    # included, so `17odoo` is a name Odoo itself creates.
    ("leading digit", "17odoo"),
    ("two characters, the floor Odoo's pattern sets", "ab"),
    ("interior dots and hyphens together", "v17.0-qa_db"),
]


@requires_bash
@pytest.mark.parametrize("shape,name", _MUST_NOT_CATCH, ids=[s for s, _ in _MUST_NOT_CATCH])
def test_validate_db_name_accepts_every_must_not_catch_shape(shape, name):
    res = _validate_db_name(name)
    assert res.returncode == 0, (
        f"validate_db_name must ACCEPT a {shape} ({name!r}) - refusing it would break an "
        f"existing instance. stderr:\n{res.stderr}"
    )
    assert res.stderr == "", f"an accepted name must print nothing to stderr:\n{res.stderr}"


# ---------------------------------------------------------------------------
# Wiring: the gate must actually be REACHED from 50-instance-spinup.sh's db_name resolution -
# this plugin's dominant defect class is correct code nothing calls.
# ---------------------------------------------------------------------------


def test_step50_calls_validate_db_name_right_after_resolving_db_name():
    text = STEP50.read_text(encoding="utf-8")
    anchor = 'local db_name="${ARG_DB_NAME:-${INST_DB_NAME:-odoo}}"'
    assert anchor in text, "db_name resolution line moved - update this test's anchor"
    after = text.split(anchor, 1)[1]
    # The call must be the NEXT non-comment statement, before any of the later gates
    # (--exclusive, --gevent-port pairing) or file/lease/DB side effects.
    next_stmt = next(
        (ln.strip() for ln in after.splitlines() if ln.strip() and not ln.strip().startswith("#")),
        "",
    )
    assert next_stmt == 'validate_db_name "$db_name" || return 1', (
        f"validate_db_name must be the very next statement after db_name is resolved - it must "
        f"run before any file is written, lease acquired, or database created. Found: "
        f"{next_stmt!r}"
    )


# ---------------------------------------------------------------------------
# Integration / behavioral: through the real `50-instance-spinup.sh apply`.
# ---------------------------------------------------------------------------


def _make_instances_toml(tmp_path: Path) -> Path:
    fake_addons = tmp_path / "fake-core" / "addons"
    fake_addons.mkdir(parents=True, exist_ok=True)
    toml = tmp_path / "instances.toml"
    toml.write_text(
        textwrap.dedent(f"""\
            [[instance]]
            series = "17.0"
            python = "/usr/bin/python3"
            http_port = 18069
            db_name = "odoo_test"
            db_host = "localhost"
            db_user = "odoo"
            run_mode = "source"
            addons_path = "{fake_addons}"
        """),
        encoding="utf-8",
    )
    return toml


def _base_env(tmp_path: Path) -> dict:
    env = dict(os.environ)
    env["ODOO_AI_INSTANCES"] = str(_make_instances_toml(tmp_path))
    env["ODOO_AI_HOME"] = str(tmp_path / "odoo-ai-home")
    env["SPINUP_TIMEOUT"] = "2"
    env["ODOO_AI_ALLOCATOR"] = ""  # not under test here; skip lease registration entirely
    env.pop("ODOO_PG_PASSWORD", None)
    return env


@requires_bash
@pytest.mark.parametrize(
    "shape,name",
    [
        ("path escape", "db/x"),
        ("parent-directory escape", "../evil"),
        ("embedded newline", "foo\nbar"),
    ],
    ids=["path_escape", "parent_dir_escape", "embedded_newline"],
)
def test_apply_refuses_a_bad_db_name_before_touching_the_filesystem(tmp_path, shape, name):
    """The behavioral proof: a bad `--db-name` is refused so early that `$ODOO_AI_HOME` is never
    even created - no conf, no log, nothing lands ANYWHERE, inside the conf dir or outside it."""
    env = _base_env(tmp_path)
    home = Path(env["ODOO_AI_HOME"])
    res = subprocess.run(
        ["bash", str(STEP50), "apply", "--version", "17.0", "--db-name", name],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert res.returncode != 0, (
        f"apply must refuse a {shape} db_name ({name!r})\n{res.stdout}\n{res.stderr}"
    )
    assert "BLOCKED" in res.stdout + res.stderr, (
        f"apply must refuse loudly for a {shape} db_name\n{res.stdout}\n{res.stderr}"
    )
    assert not home.exists(), (
        f"the gate must fire BEFORE anything under $ODOO_AI_HOME is created (no conf dir, no "
        f"log dir, no lease dir) for a {shape} db_name - found: "
        f"{sorted(str(p) for p in home.rglob('*')) if home.exists() else '<home never created>'}"
    )
    # A stronger, path-specific check for the two escape shapes: the exact file the unguarded
    # code would have attempted to write must not exist anywhere under tmp_path (inside OR
    # outside the intended conf dir).
    escaped_names = list(tmp_path.rglob("x-18069.conf")) + list(tmp_path.rglob("evil-18069.conf"))
    assert escaped_names == [], (
        f"no file the escaped path would have named may land ANYWHERE under {tmp_path}: "
        f"{escaped_names}"
    )


@requires_bash
def test_apply_prevents_a_genuine_parent_directory_escape_end_to_end(tmp_path):
    """The deepest behavioral proof: reuse `test_conf_lifecycle.Sandbox` (which drives the REAL
    script far enough to reach the actual conf-write line - stubbed odoo-bin, python preflight,
    AND the launch itself) with a declared `db_name = "../evil"`.

    `"../evil"` is deliberately a PARENT-relative escape, not a bare `db/x`: `..` always resolves
    (every directory has one), so this reproduces a genuine filesystem escape independent of
    whatever subdirectories happen to pre-exist under the conf dir - unlike `db/x`, which merely
    fails to open (ENOENT) when no `db/` subdirectory already exists. This is the strongest
    version of FM1 this suite can force deterministically.

    Without the gate, `$_conf_dir/../evil-<port>.conf` resolves to a path ONE LEVEL ABOVE the
    conf dir (directly under `$ODOO_AI_HOME`) - outside the `-maxdepth 1` scope the sweep ever
    looks at, i.e. leaked permanently. With the gate, `apply` must refuse before ANY of that path
    arithmetic runs, so no such file may exist anywhere.
    """
    sandbox = Sandbox(tmp_path, db="../evil")
    try:
        res = sandbox.apply()
        out = res.stdout + res.stderr
        assert res.returncode != 0, f"a parent-directory-escaping db_name must be refused\n{out}"
        assert "BLOCKED" in out, f"the refusal must be loud\n{out}"
        escaped = list(tmp_path.rglob("evil-*.conf"))
        assert escaped == [], (
            f"no conf named after the escaping db_name may land ANYWHERE under {tmp_path} - "
            f"found: {escaped}\n{out}"
        )
        assert sandbox.confs() == [], f"the conf dir itself must stay empty\n{out}"
    finally:
        sandbox.reap()


@requires_bash
@pytest.mark.parametrize(
    "shape,name",
    [
        ("hyphen and underscore", "foo-bar_baz"),
        ("widened dot class", "foo.bar"),
    ],
    ids=["hyphen_underscore", "dot"],
)
def test_apply_accepts_a_good_db_name_and_proceeds_past_the_gate(tmp_path, shape, name):
    """MUST-NOT-CATCH at the integration level: a legitimate name must reach past the gate (here,
    all the way to the 'already up' short-circuit, which needs only curl - not a real Odoo)."""
    env = _base_env(tmp_path)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    curl_stub = bindir / "curl"
    curl_stub.write_text("#!/usr/bin/env bash\necho 200\n", encoding="utf-8")
    curl_stub.chmod(0o755)
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"

    res = subprocess.run(
        ["bash", str(STEP50), "apply", "--version", "17.0", "--db-name", name],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert res.returncode == 0, (
        f"apply must ACCEPT a {shape} db_name ({name!r}) and proceed\n{res.stdout}\n{res.stderr}"
    )
    assert "BLOCKED" not in (res.stdout + res.stderr), (
        f"a legitimate {shape} db_name must never be refused\n{res.stdout}\n{res.stderr}"
    )


# ---------------------------------------------------------------------------
# Sweep-side guard: a PRE-EXISTING bad filename (from before this validator existed, or from any
# other write path) must be left alone, not misjudged by the lease check.
# ---------------------------------------------------------------------------


def _run_sweep(conf_dir: Path, home: Path) -> subprocess.CompletedProcess:
    script = (
        f'source "{STATE_RECLAIM}"; '
        f'export ODOO_AI_HOME="{home}"; '
        f'prune_stale_run_artifacts "{conf_dir}" "*.conf"'
    )
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=10)


@requires_bash
def test_sweep_leaves_a_pre_existing_newline_named_conf_alone(tmp_path):
    """A conf whose basename embeds a real newline (legal on Linux, and exactly the shape that
    breaks `grep -Fxq`'s line-oriented lease match) must survive the sweep rather than risk being
    misjudged as unleased and deleted. This is the residual this validator's own gate cannot
    reach retroactively - the sweep must defend itself."""
    conf_dir = tmp_path / "state-root" / "conf"
    conf_dir.mkdir(parents=True)
    bad = conf_dir / "foo\nbar-18069.conf"
    bad.write_text("[options]\nseeded = 1\n", encoding="utf-8")
    old = time.time() - 20 * 86400
    os.utime(bad, (old, old))
    # No lease registry at all -> "nothing was ever leased" is a legitimate host state that must
    # NOT, by itself, disable this guard's own skip.
    res = _run_sweep(conf_dir, tmp_path / "state-root")
    assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
    assert bad.exists(), (
        "a pre-existing conf whose recovered db name fails the accepted character class must be "
        "left alone (skip, not delete) - the sweep cannot trust a line-oriented lease compare "
        f"against a name that itself contains a newline. stderr:\n{res.stderr}"
    )


@requires_bash
def test_sweep_still_reclaims_a_normal_stale_unleased_conf(tmp_path):
    """Control: the new guard must not swallow the sweep's ordinary job for a well-formed name."""
    conf_dir = tmp_path / "state-root" / "conf"
    conf_dir.mkdir(parents=True)
    fine = conf_dir / "retired_db-18069.conf"
    fine.write_text("[options]\nseeded = 1\n", encoding="utf-8")
    old = time.time() - 20 * 86400
    os.utime(fine, (old, old))
    res = _run_sweep(conf_dir, tmp_path / "state-root")
    assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
    assert not fine.exists(), (
        "a stale, unleased, well-formed conf must still be reclaimed - the new guard must be "
        "scoped to unparseable names only"
    )
