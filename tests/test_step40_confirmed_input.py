"""Tests for step 40 confirmed-input contract.

Guards the new behaviour where `40 apply` MUST NOT write anything unless
ODOO_AI_PROFILE_SPEC is set to a confirmed JSON spec file.

CPU-only: no PostgreSQL, no Odoo, no network.
"""

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from shutil import which

import pytest

ROOT = Path(__file__).resolve().parent.parent
STEP40 = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "setup-steps" / "40-instance-profile.sh"


def _run_step40(subcommand, env_extra=None, cwd=None):
    """Run `bash STEP40 <subcommand>` and return CompletedProcess."""
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(STEP40), subcommand],
        capture_output=True, text=True,
        env=env, cwd=str(cwd) if cwd else None,
    )


@pytest.mark.skipif(which("bash") is None, reason="bash not available")
def test_step40_requires_confirmed_input_no_auto_write(tmp_path):
    """40 apply exits non-zero and writes nothing when ODOO_AI_PROFILE_SPEC is unset.

    Fails if the step auto-writes any [[instance]] to instances.toml without a
    confirmed spec - guards the contract that discovery-then-write is no longer
    automatic.
    """
    instances_toml = tmp_path / "instances.toml"

    # ODOO_AI_PROFILE_SPEC deliberately NOT set; ODOO_AI_INSTANCES redirects writes.
    proc = _run_step40(
        "apply",
        env_extra={
            "ODOO_AI_INSTANCES": str(instances_toml),
            # Ensure HOME does not point somewhere with a real instances.toml
            "HOME": str(tmp_path),
            # Unset spec explicitly (subprocess inherits parent env, so override)
            "ODOO_AI_PROFILE_SPEC": "",
        },
        cwd=tmp_path,
    )

    assert proc.returncode != 0, (
        f"Expected non-zero exit when ODOO_AI_PROFILE_SPEC unset; got 0.\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    # The file must NOT have been created with any [[instance]] block.
    if instances_toml.exists():
        content = instances_toml.read_text()
        assert "[[instance]]" not in content, (
            f"Step 40 wrote [[instance]] without a confirmed spec:\n{content}"
        )

    # Stderr must contain a helpful message pointing to ODOO_AI_PROFILE_SPEC.
    combined = proc.stdout + proc.stderr
    assert "ODOO_AI_PROFILE_SPEC" in combined, (
        "Expected a mention of ODOO_AI_PROFILE_SPEC in output but got:\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )


@pytest.mark.skipif(which("bash") is None, reason="bash not available")
def test_step40_writes_from_confirmed_spec(tmp_path):
    """40 apply writes the correct [[instance]] from a confirmed JSON spec.

    Verifies:
    - The instance has the given series and addons_path.
    - Running apply a second time is idempotent (no duplicate [[instance]]).
    - The http_port default allocation is used when not specified in spec.
    """
    instances_toml = tmp_path / "instances.toml"
    spec_file = tmp_path / "profile.json"

    addons = ["/abs/custom", "/abs/core"]
    spec = [
        {
            "series": "17.0",
            "addons_path": addons,
            "http_port": 8139,
            "db_name": "odoo_17_0",
            "db_host": "localhost",
            "db_user": "odoo",
            "python": "",
        }
    ]
    spec_file.write_text(json.dumps(spec), encoding="utf-8")

    env_extra = {
        "ODOO_AI_PROFILE_SPEC": str(spec_file),
        "ODOO_AI_INSTANCES": str(instances_toml),
        "HOME": str(tmp_path),
    }

    # First run: should write.
    proc = _run_step40("apply", env_extra=env_extra, cwd=tmp_path)
    assert proc.returncode == 0, (
        f"First apply failed.\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert instances_toml.exists(), "instances.toml was not created"

    data = tomllib.loads(instances_toml.read_text())
    assert isinstance(data.get("instance"), list), "Expected [[instance]] array-of-tables"
    instances = data["instance"]
    assert len(instances) == 1, f"Expected 1 instance, got {len(instances)}"
    inst = instances[0]
    assert inst["series"] == "17.0", f"Wrong series: {inst}"
    assert inst["addons_path"] == addons, f"Wrong addons_path: {inst}"

    # Second run: idempotent - still exactly 1 [[instance]].
    proc2 = _run_step40("apply", env_extra=env_extra, cwd=tmp_path)
    assert proc2.returncode == 0, (
        f"Second (idempotent) apply failed.\nstdout: {proc2.stdout}\nstderr: {proc2.stderr}"
    )
    data2 = tomllib.loads(instances_toml.read_text())
    assert len(data2["instance"]) == 1, (
        f"Idempotency failed: expected 1 instance after second apply, "
        f"got {len(data2['instance'])}"
    )


@pytest.mark.skipif(which("bash") is None, reason="bash not available")
def test_step40_rejects_malformed_spec_without_partial_write(tmp_path):
    """40 apply rejects a spec with an invalid item and writes NO partial output.

    Spec: [valid item (series+addons_path), invalid item (missing series)].
    Expected: exit non-zero AND instances.toml contains 0 [[instance]] blocks
    (the valid first item must NOT have been written before the error).
    This is the red-green guard for the upfront-validate-before-write fix.
    """
    instances_toml = tmp_path / "instances.toml"
    spec_file = tmp_path / "bad_profile.json"

    # Item 0: valid. Item 1: missing 'series' - should abort the whole apply.
    spec = [
        {"series": "17.0", "addons_path": ["/abs/custom", "/abs/core"]},
        {"addons_path": ["/abs/other"]},   # no 'series' key
    ]
    spec_file.write_text(json.dumps(spec), encoding="utf-8")

    proc = _run_step40(
        "apply",
        env_extra={
            "ODOO_AI_PROFILE_SPEC": str(spec_file),
            "ODOO_AI_INSTANCES": str(instances_toml),
            "HOME": str(tmp_path),
        },
        cwd=tmp_path,
    )

    assert proc.returncode != 0, (
        f"Expected non-zero exit for malformed spec; got 0.\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )

    # Critical: the valid first item must NOT have been partially written.
    if instances_toml.exists():
        content = instances_toml.read_text()
        instance_count = content.count("[[instance]]")
        assert instance_count == 0, (
            f"Partial write detected: {instance_count} [[instance]] block(s) found "
            f"after a spec with an invalid item.\nFile content:\n{content}"
        )


@pytest.mark.skipif(which("bash") is None, reason="bash not available")
def test_step40_spec_defaults_fill_missing_optional_fields(tmp_path):
    """40 apply fills defaults for optional fields (db_name, db_host, db_user, http_port).

    Only series + addons_path are required; other fields have sensible defaults.
    """
    instances_toml = tmp_path / "instances.toml"
    spec_file = tmp_path / "minimal.json"

    spec = [{"series": "18.0", "addons_path": ["/repos/core18"]}]
    spec_file.write_text(json.dumps(spec), encoding="utf-8")

    proc = _run_step40(
        "apply",
        env_extra={
            "ODOO_AI_PROFILE_SPEC": str(spec_file),
            "ODOO_AI_INSTANCES": str(instances_toml),
            "HOME": str(tmp_path),
        },
        cwd=tmp_path,
    )
    assert proc.returncode == 0, (
        f"apply with minimal spec failed.\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )

    data = tomllib.loads(instances_toml.read_text())
    inst = data["instance"][0]
    assert inst["series"] == "18.0"
    assert inst["addons_path"] == ["/repos/core18"]
    # Defaults must be filled in:
    assert inst.get("db_host") == "localhost"
    assert inst.get("db_user") == "odoo"
    assert inst.get("db_name") == "odoo_18_0"
    # Port: first instance gets base_port (8069) since file was empty.
    assert inst.get("http_port") == 8069
