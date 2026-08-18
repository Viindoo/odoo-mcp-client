"""Behavior guard: a catalog `addons_path` declared as a STRING resolves to the SAME tree a
LIST declares - all the way onto the lease row and into the conf a real spin-up serves.

The business rule: `instances.toml` accepts TWO declared shapes for `[[instance]].addons_path` -
a native TOML array (what `40-instance-profile.sh` records) and a bare flattened string (a
hand-typed override, e.g. `addons_path = "/a,/b"`). `instances_io.addons_path_list` is the SSOT
that normalizes both; a caller that skips it and hands the raw catalog value to
`instances_io.join_addons_path` - which comma-joins a LIST - iterates a STRING character by
character, so `"/a,/b"` becomes `/,a,/,b`.

That is a WRONG VALUE, not a crash, and it lands on the field that decides which source tree a
server serves: `allocator.py cmd_acquire` writes the resolved value onto the lease row, and
`50-instance-spinup.sh cmd_apply` reads that row to pick the tree it launches against. A run
measured against a garbage addons_path fails in the silent direction - the port answers, the
suite runs, and the green means nothing.

One site in `allocator.py` reads the catalog value - `_resolve_addons_csv`, the no-override
branch, which produces `ALLOC_ADDONS_PATH` and the lease row's `addons_path`. `_emit_instance_common`
used to carry an INDEPENDENT fallback read of its own (a second copy of the same catalog-shape
logic, taken whenever no resolved value was passed in); that branch was provably unreachable -
every real call site already resolves `addons_csv` up front and returns early on error before ever
reaching the emit call - so it was removed and `addons_csv` is now a required argument.
`_emit_instance_common` only ever emits the value its caller already resolved.

Every assertion here is on the resolved VALUE (and, end to end, on the generated conf and the
script's own machine output), never on prose: the defect always described itself as success.

Offline: no PostgreSQL, no real Odoo, no network. The end-to-end case reuses
`test_conf_lifecycle.Sandbox` (stub odoo-bin / python / curl / pg_isready) and the acquire+apply
helpers of `test_apply_serves_the_leased_tree`, rather than standing up a second harness.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from shutil import which

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
LIB = PLUGIN / "scripts" / "lib"
ALLOCATOR = LIB / "allocator.py"

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import instances_io  # noqa: E402

from test_conf_lifecycle import Sandbox  # noqa: E402
from test_apply_serves_the_leased_tree import (  # noqa: E402
    _acquire,
    _apply_exclusive,
    _conf_text,
    _conf_value,
    _facts,
)

requires_bash = pytest.mark.skipif(which("bash") is None, reason="bash not available")


def _allocator():
    """The allocator loaded as a module, so the two reading sites can be called directly."""
    spec = importlib.util.spec_from_file_location("allocator_catalog_shapes", ALLOCATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ALLOC = _allocator()


def _emitted_addons_path(inst) -> str:
    """`ALLOC_ADDONS_PATH` as `_emit_instance_common` actually prints it: resolve the catalog
    value through the ONE sanctioned reader (`_resolve_addons_csv`, exactly as every real
    `cmd_acquire` call site does) and hand the result in, then read back what landed on stdout.

    `_emit_instance_common` no longer accepts a call with no resolved value - its own former
    fallback read was provably unreachable and has been removed, so `addons_csv` is now a required
    argument (see the module docstring). This helper still verifies the emission is a faithful
    passthrough of whatever was resolved - the behavior worth protecting - through the same
    resolve-then-emit sequence `cmd_acquire` performs, rather than by exercising a branch that can
    no longer exist."""
    csv, err = ALLOC._resolve_addons_csv(inst, None)
    assert err is None, err
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ALLOC._emit_instance_common(inst, csv)
    values = [
        line.split("=", 1)[1]
        for line in buf.getvalue().splitlines()
        if line.startswith("ALLOC_ADDONS_PATH=")
    ]
    assert len(values) == 1, f"expected exactly one ALLOC_ADDONS_PATH line: {buf.getvalue()!r}"
    # _emit shell-quotes; strip the quoting the same way a caller's `eval` would.
    value = values[0]
    if value.startswith("'") and value.endswith("'"):
        value = value[1:-1]
    return value


# ---------------------------------------------------------------------------
# MUST-CATCH - the shapes the character-by-character join corrupted
# ---------------------------------------------------------------------------

MUST_CATCH = [
    pytest.param("/opt/odoo/addons,/opt/custom", "/opt/odoo/addons,/opt/custom", id="string-two"),
    pytest.param("/a", "/a", id="string-single-entry"),
    pytest.param("/a/b:/c/d", "/a/b,/c/d", id="string-legacy-colon"),
]

MUST_NOT_CATCH = [
    pytest.param(["/opt/odoo/addons", "/opt/custom"], "/opt/odoo/addons,/opt/custom", id="list-two"),
    pytest.param(["/a"], "/a", id="list-single-entry"),
    pytest.param([], "", id="list-empty"),
    pytest.param("", "", id="string-empty"),
]


@pytest.mark.parametrize("declared,expected", MUST_CATCH)
def test_a_string_form_catalog_addons_path_resolves_to_the_declared_tree(declared, expected):
    """MUST-CATCH - the acquire-time resolution of a STRING-shaped declaration.

    The `/,a,/,b` damage is asserted away twice over: once by pinning the exact value, and once
    by the shape check - a character-joined value is a run of single-character entries, which no
    real addons_path ever is.
    """
    csv, err = ALLOC._resolve_addons_csv({"addons_path": declared}, None)
    assert err is None, err
    assert csv == expected, f"declared {declared!r} resolved to {csv!r}, not {expected!r}"
    entries = [e for e in csv.split(",") if e]
    assert all(len(e) > 1 for e in entries), (
        f"{declared!r} was iterated character by character: {entries!r}"
    )


@pytest.mark.parametrize("declared,expected", MUST_CATCH)
def test_the_emitted_value_resolves_a_string_form_declaration_too(declared, expected):
    """MUST-CATCH - the SECOND observation site. `_emit_instance_common` emits exactly the value
    `_resolve_addons_csv` resolved for a STRING-shaped declaration, so a regression that broke
    only the emission (leaving resolution itself correct) would still be caught here."""
    assert _emitted_addons_path({"addons_path": declared}) == expected


@pytest.mark.parametrize("declared,expected", MUST_NOT_CATCH)
def test_the_list_and_empty_shapes_are_unchanged(declared, expected):
    """MUST-NOT-CATCH - the canonical array form, a one-entry array, and an empty/absent value
    must come out exactly as they did before. A fix that moved any of these is not a fix."""
    csv, err = ALLOC._resolve_addons_csv({"addons_path": declared}, None)
    assert err is None, err
    assert csv == expected
    assert _emitted_addons_path({"addons_path": declared}) == expected


def test_an_absent_addons_path_resolves_to_empty_at_both_sites():
    """MUST-NOT-CATCH - a catalog row that declares no addons_path at all (the pre-field
    catalogs are still legal) stays empty rather than becoming an error or a literal."""
    csv, err = ALLOC._resolve_addons_csv({}, None)
    assert err is None, err
    assert csv == ""
    assert _emitted_addons_path({}) == ""


@pytest.mark.parametrize("declared,expected", MUST_CATCH + MUST_NOT_CATCH)
def test_the_public_reader_normalizes_both_declared_shapes(declared, expected):
    """`instances_io.addons_path_list` is the ONE sanctioned reader of a declared addons_path,
    and it is public precisely so a caller outside the module can reach it instead of
    re-deriving the shape rule. Composed with `join_addons_path` it must reproduce the wire
    format both allocator sites emit."""
    entries = instances_io.addons_path_list({"addons_path": declared})
    assert isinstance(entries, list)
    assert instances_io.join_addons_path(entries) == expected


# ---------------------------------------------------------------------------
# End to end - the lease row and the tree the spin-up actually serves
# ---------------------------------------------------------------------------


def _lease_row(sandbox: Sandbox, token: str) -> dict:
    """The lease row as the allocator's OWN command surface reports it - the same
    `list --show-tokens` read `50-instance-spinup.sh::_lease_addons_path` performs."""
    res = subprocess.run(
        [sys.executable, str(ALLOCATOR), "list", "--show-tokens"],
        capture_output=True, text=True, env=sandbox.env(), timeout=60,
    )
    assert res.returncode == 0, f"list failed:\n{res.stdout}\n{res.stderr}"
    registry = json.loads(res.stdout)
    rows = [r for r in registry.get("leases") or [] if r.get("token") == token]
    assert rows, f"no lease row for {token!r}:\n{res.stdout}"
    return rows[0]


def _declare_string_form_addons_path(sandbox: Sandbox, *dirs: Path) -> str:
    """Rewrite the sandbox catalog to declare `addons_path` as a bare comma-separated STRING
    over `dirs`, and return the value a correct resolution must produce."""
    joined = ",".join(str(d) for d in dirs)
    text = sandbox.toml.read_text(encoding="utf-8")
    replaced = text.replace(
        f'addons_path = "{sandbox.addons}"', f'addons_path = "{joined}"'
    )
    assert replaced != text, "the sandbox catalog no longer declares a scalar addons_path"
    sandbox.toml.write_text(replaced, encoding="utf-8")
    return joined


@pytest.fixture
def sandbox(tmp_path):
    sb = Sandbox(tmp_path)
    try:
        yield sb
    finally:
        sb.reap()


@pytest.fixture
def second_addons(tmp_path) -> Path:
    """A second REAL addons dir, so the multi-entry string form is exercised against directories
    that exist - the served tree is asserted to be a real directory, not just a matching string."""
    path = tmp_path / "extra-checkout" / "addons"
    path.mkdir(parents=True, exist_ok=True)
    return path


@requires_bash
def test_a_string_form_catalog_reaches_the_lease_and_the_served_conf(sandbox, second_addons):
    """END TO END - the consequence that makes this worth fixing.

    With a two-entry STRING catalog, a REAL `allocator.py acquire` must record a usable path on
    the lease, and the tree `50-instance-spinup.sh apply` resolves FROM that lease must be those
    real directories. Before the fix the lease carried `/,t,m,p,...`, which `cmd_apply` could
    only reject as "not a directory list" - so it fell back to the catalog row and warned, and
    `SERVED_ADDONS_SOURCE` said `catalog`.
    """
    expected = _declare_string_form_addons_path(sandbox, sandbox.addons, second_addons)

    token = _acquire(sandbox)
    row = _lease_row(sandbox, token)
    assert row.get("addons_path") == expected, (
        f"the lease must record the declared tree, got {row.get('addons_path')!r}"
    )

    res = _apply_exclusive(sandbox, "--alloc-token", token)
    out = res.stdout + res.stderr
    assert res.returncode == 0, f"the spin-up must succeed on a string-form catalog\n{out}"

    facts = _facts(res)
    assert facts.get("SERVED_ADDONS_PATH") == expected, f"{facts!r}\n{out}"
    assert facts.get("SERVED_ADDONS_SOURCE") == "lease", (
        f"the lease's tree is usable now, so it - not the catalog fallback - is what was "
        f"served: {facts!r}\n{out}"
    )
    for entry in facts["SERVED_ADDONS_PATH"].split(","):
        assert os.path.isdir(entry), f"served a path that is not a directory: {entry!r}\n{out}"

    assert "not a directory list" not in res.stderr, (
        f"nothing is malformed any more, so nothing may warn about it\n{res.stderr}"
    )
    assert _conf_value(_conf_text(res), "addons_path") == expected, _conf_text(res)


@requires_bash
def test_the_array_form_catalog_produces_the_identical_lease_and_conf(sandbox, second_addons):
    """MUST-NOT-CATCH, end to end - the canonical ARRAY declaration of the SAME two directories
    must produce a byte-identical lease row, served path and conf. The two shapes are two
    spellings of one fact; a fix that made them disagree in the other direction would be the
    same defect wearing the opposite sign."""
    joined = ",".join(str(d) for d in (sandbox.addons, second_addons))
    text = sandbox.toml.read_text(encoding="utf-8")
    replaced = text.replace(
        f'addons_path = "{sandbox.addons}"',
        f'addons_path = ["{sandbox.addons}", "{second_addons}"]',
    )
    assert replaced != text
    sandbox.toml.write_text(replaced, encoding="utf-8")

    token = _acquire(sandbox)
    assert _lease_row(sandbox, token).get("addons_path") == joined

    res = _apply_exclusive(sandbox, "--alloc-token", token)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert _facts(res).get("SERVED_ADDONS_PATH") == joined, f"{_facts(res)!r}\n{out}"
    assert _conf_value(_conf_text(res), "addons_path") == joined, _conf_text(res)
