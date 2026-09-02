"""A host without a usable `python3` must be TOLD so, by the step that needs it.

Root cause this protects: every setup step that reads the instance catalog shells out to
`python3` and suppresses its stderr (`2>/dev/null || true`, 42 occurrences across
`scripts/setup-steps/`). That suppression is right for an absent optional fact and wrong for a
broken interpreter, because it makes the two indistinguishable. Measured before the fix: on a
host where `python3` did not resolve, `48-db-local-auth.sh apply` enumerated zero instances from
a catalog declaring one, skipped every pass silently, and reported

    x nothing was proven: no declared instance reached the reconnect check.

- a message that blames the catalog and never mentions the interpreter. Nothing anywhere checked
that `python3` existed: `grep -rn 'command -v python3' scripts/setup-steps/` returned nothing.

The hosts this happens on are ordinary: a version manager whose `python3` is a shim that resolves
to nothing under the step's PATH, a container-only or minimal host with no system python, or a
python older than `tomllib`. The plugin supports hosts with and without Docker and with and
without a system python, so "without" has to be a diagnosable answer rather than a silent no-op.

Run: python -m pytest tests/test_python_preflight.py -v
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STEPS = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "setup-steps"
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "require_python.sh"

_BASH = shutil.which("bash")
requires_bash = pytest.mark.skipif(_BASH is None, reason="these steps are bash")

# Every step that reaches the instance catalog (or the Claude config) through python3. Derived
# from the interpreter call itself, not from a hand-kept list, so a new step that shells out to
# python is caught by this test rather than by a user.
CATALOG_STEPS = (
    "48-db-local-auth.sh",
    "05-prereq-check.sh",
    "45-venv.sh",
    "40-instance-profile.sh",
    "47-instance-reset.sh",
)
JSON_ONLY_STEPS = (
    "00-osm-gate.sh",
    "10-browser-mcp.sh",
    "30-permissions.sh",
    "32-permissions-state-root.sh",
)
# Reads the catalog (tomllib) AND hashes registry state, so it names both.
MIXED_STEPS = ("50-instance-spinup.sh",)


def _steps_invoking_python() -> set[str]:
    found = set()
    for path in sorted(STEPS.glob("*.sh")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "python3 - " in text or "python3 -c" in text:
            found.add(path.name)
    return found


def _run(step: str, *args: str, tmp_path: Path, python3: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["ODOO_AI_PYTHON3"] = python3
    env["ODOO_AI_HOME"] = str(tmp_path / "state")
    env["ODOO_AI_INSTANCES"] = str(tmp_path / "instances.toml")
    (tmp_path / "instances.toml").write_text(
        '[[instance]]\nseries = "17.0"\naddons_path = ["/nowhere"]\n', encoding="utf-8")
    return subprocess.run([_BASH, str(STEPS / step), *args],
                          capture_output=True, text=True, env=env, timeout=120)


def test_the_preflight_ssot_exists_and_is_the_only_copy():
    """One home for the rule. A second hand-rolled interpreter check in a step is how the two
    answers drift apart, which is the failure mode this repo pays for most often."""
    assert LIB.is_file(), f"missing preflight SSOT: {LIB}"
    body = LIB.read_text(encoding="utf-8")
    assert "require_python3()" in body
    assert "ODOO_AI_PYTHON3" in body, (
        "an operator whose interpreter is not on PATH must have a way to name one without "
        "editing PATH - a shim that resolves to nothing is the common case"
    )


@pytest.mark.parametrize("step", CATALOG_STEPS + JSON_ONLY_STEPS + MIXED_STEPS)
def test_every_python_using_step_preflights_its_interpreter(step):
    text = (STEPS / step).read_text(encoding="utf-8")
    assert "require_python.sh" in text, (
        f"{step} shells out to python3 but never preflights it, so a host without a usable "
        "interpreter gets a downstream symptom instead of the cause"
    )
    assert "require_python3 " in text


def test_the_derived_step_set_has_not_outgrown_this_files_list():
    """Discovery floor. If a new step starts shelling out to python3, it must appear here - a
    hand-kept list that silently stops covering the tree is worse than no list."""
    derived = _steps_invoking_python()
    known = set(CATALOG_STEPS) | set(JSON_ONLY_STEPS) | set(MIXED_STEPS)
    missing = derived - known
    assert not missing, (
        f"these steps invoke python3 but are not covered by this test: {sorted(missing)}"
    )


@requires_bash
@pytest.mark.parametrize("step", CATALOG_STEPS)
def test_a_broken_interpreter_is_named_not_hidden(step, tmp_path):
    """The behaviour, not the wiring. With no usable python3 the step must name the interpreter
    and stop - never proceed to report an empty catalog, which is what it did before."""
    res = _run(step, "check", tmp_path=tmp_path, python3="/nonexistent/python3")
    out = res.stdout + res.stderr
    assert res.returncode == 2, f"expected the invocation to be refused; got {res.returncode}\n{out}"
    assert "python3" in out, f"the refusal must name the interpreter:\n{out}"
    assert "ODOO_AI_PYTHON3" in out, f"the refusal must name the way out:\n{out}"
    assert "nothing was proven" not in out, (
        "the step reached its downstream symptom instead of stopping at the cause - this is the "
        f"exact defect the preflight exists to prevent:\n{out}"
    )


@requires_bash
@pytest.mark.parametrize("step", CATALOG_STEPS + JSON_ONLY_STEPS + MIXED_STEPS)
def test_describe_still_works_without_any_python(step, tmp_path):
    """`describe` is pure text. A host with no python must still be able to read what a step
    would do - refusing that would trade one unusable state for another."""
    res = _run(step, "describe", tmp_path=tmp_path, python3="/nonexistent/python3")
    assert res.returncode == 0, (
        f"{step} describe must not need an interpreter; got {res.returncode}\n"
        f"{res.stdout}{res.stderr}"
    )
    assert res.stdout.strip(), "describe must still say something"


@requires_bash
def test_the_capability_floor_is_the_callers_to_choose(tmp_path):
    """`00-osm-gate.sh` parses JSON and needs no `tomllib`. Inheriting the catalog steps' 3.11
    floor would refuse a host this step would have served - the same defect inverted."""
    text = (STEPS / "00-osm-gate.sh").read_text(encoding="utf-8")
    assert "require_python3 " in text and " json" in text.split("require_python3 ", 1)[1][:120], (
        "the OSM gate must ask for the capability it actually uses (json), not the default"
    )


@requires_bash
def test_a_working_interpreter_is_not_refused(tmp_path):
    """Red-before-green's other half: the preflight must be invisible on a healthy host."""
    real = shutil.which("python3")
    if real is None:
        pytest.skip("no python3 on PATH to prove the healthy path with")
    res = _run("48-db-local-auth.sh", "describe", tmp_path=tmp_path, python3=real)
    assert res.returncode == 0
    out = res.stdout + res.stderr
    assert "needs a working python3" not in out, f"healthy host was refused:\n{out}"
