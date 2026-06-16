"""Tests for setup step 47 (47-instance-reset.sh).

Guards three contracts:
  - backup-before-overwrite: a .bak.<ts> file is created containing the
    ORIGINAL content before the new file is written.
  - filter-by-mode: default mode keeps instances whose every addons_path
    exists on disk and drops dead ones; --hard writes 0 instances.
  - check-always-0: `check` exits 0 regardless of file state.

Offline: no PostgreSQL, no Odoo, no network. Uses ODOO_AI_INSTANCES (tmp
path) and ODOO_AI_BACKUP_TS (deterministic timestamp) for full isolation.
"""

import os
import subprocess
import sys
from pathlib import Path
from shutil import which

import pytest

ROOT = Path(__file__).resolve().parent.parent
STEP47 = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "setup-steps" / "47-instance-reset.sh"

FIXED_TS = "1700000000"  # deterministic backup timestamp for all tests


def _run_step(subcommand, *extra_args, toml_path=None, env_extra=None):
    """Run 47-instance-reset.sh with the given subcommand under a controlled env."""
    env = {k: v for k, v in os.environ.items()}
    env.pop("ODOO_AI_INSTANCES", None)
    env.pop("ODOO_AI_HOME", None)
    env.pop("HOME", None)  # prevent accidental writes to real home
    if toml_path is not None:
        env["ODOO_AI_INSTANCES"] = str(toml_path)
    env["ODOO_AI_BACKUP_TS"] = FIXED_TS
    if env_extra:
        env.update(env_extra)

    cmd = ["bash", str(STEP47), subcommand] + list(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def _toml_with_instances(tmp_path, instances):
    """Write a simple instances.toml with the given list of dicts.

    Each dict must have 'series' and 'addons_path' (list of str) keys.
    Returns the Path.
    """
    toml = tmp_path / "instances.toml"
    lines = []
    for inst in instances:
        lines.append("")
        lines.append("[[instance]]")
        lines.append(f'series = "{inst["series"]}"')
        paths_str = ", ".join(f'"{p}"' for p in inst["addons_path"])
        lines.append(f"addons_path = [{paths_str}]")
        lines.append(f'http_port = {inst.get("http_port", 8069)}')
        lines.append(f'db_name = "odoo_{inst["series"].replace(".", "_")}"')
    toml.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return toml


@pytest.mark.skipif(which("bash") is None, reason="bash not available")
def test_step47_describe():
    """describe prints a non-empty one-line description."""
    proc = _run_step("describe")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() != ""


# ---------------------------------------------------------------------------
# Contract 1: backup-before-overwrite
# ---------------------------------------------------------------------------

@pytest.mark.skipif(which("bash") is None, reason="bash not available")
def test_step47_reset_backs_up_before_overwrite(tmp_path):
    """apply creates <path>.bak.<ts> with the ORIGINAL content before rewriting.

    Fails if the backup is missing, has wrong content, or is created AFTER the
    new file is written (atomicity: original must be preserved in the backup).
    """
    live_path = tmp_path / "instances.toml"
    original = (
        "[[instance]]\n"
        'series = "17.0"\n'
        f'addons_path = ["{tmp_path}"]\n'  # tmp_path always exists -> kept in default mode
        "http_port = 8069\n"
    )
    live_path.write_text(original, encoding="utf-8")

    proc = _run_step("apply", toml_path=live_path)
    assert proc.returncode == 0, f"apply failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"

    bak = Path(f"{live_path}.bak.{FIXED_TS}")
    assert bak.exists(), (
        f"backup not found at {bak}; step output:\n{proc.stdout}\n{proc.stderr}"
    )
    assert bak.read_text(encoding="utf-8") == original, (
        "backup does not match original content"
    )
    # The live file must also have been rewritten (not identical to original in all cases,
    # but at minimum the step ran without error and the backup predates the live write).
    assert live_path.exists()


# ---------------------------------------------------------------------------
# Contract 2: filter-by-mode
# ---------------------------------------------------------------------------

@pytest.mark.skipif(which("bash") is None, reason="bash not available")
def test_step47_reset_default_keeps_live_drops_dead(tmp_path):
    """Default apply keeps instances with existing addons_path, drops dead ones.

    Seeds a toml with:
      - instance A: addons_path points to a real tmp dir (live)
      - instance B: addons_path points to a non-existent path (dead)

    After `apply` (no --hard):
      - A's series is still in the file
      - B's series is gone
    """
    live_dir = tmp_path / "live_addon"
    live_dir.mkdir()
    dead_path = str(tmp_path / "nonexistent_addon_dir_xyz")

    toml = _toml_with_instances(tmp_path, [
        {"series": "17.0", "addons_path": [str(live_dir)]},
        {"series": "16.0", "addons_path": [dead_path]},
    ])
    original = toml.read_text(encoding="utf-8")

    proc = _run_step("apply", toml_path=toml)
    assert proc.returncode == 0, f"apply failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"

    result = toml.read_text(encoding="utf-8")

    # Backup must exist and match original.
    bak = Path(f"{toml}.bak.{FIXED_TS}")
    assert bak.exists(), "backup not created"
    assert bak.read_text(encoding="utf-8") == original

    # Live series kept, dead series dropped.
    assert "17.0" in result, f"live series 17.0 was dropped; file:\n{result}"
    assert "16.0" not in result, f"dead series 16.0 was kept; file:\n{result}"


@pytest.mark.skipif(which("bash") is None, reason="bash not available")
def test_step47_reset_hard_wipes_all_instances(tmp_path):
    """--hard writes a file with 0 [[instance]] entries.

    Seeds a toml with two instances (both with existing addons_path).
    After `apply --hard` the result has no [[instance]] tables.
    """
    live_dir_a = tmp_path / "addon_a"
    live_dir_a.mkdir()
    live_dir_b = tmp_path / "addon_b"
    live_dir_b.mkdir()

    toml = _toml_with_instances(tmp_path, [
        {"series": "17.0", "addons_path": [str(live_dir_a)]},
        {"series": "18.0", "addons_path": [str(live_dir_b)]},
    ])
    original = toml.read_text(encoding="utf-8")

    proc = _run_step("apply", "--hard", toml_path=toml)
    assert proc.returncode == 0, f"apply --hard failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"

    result = toml.read_text(encoding="utf-8")

    # Backup must exist and match original.
    bak = Path(f"{toml}.bak.{FIXED_TS}")
    assert bak.exists(), "backup not created for --hard"
    assert bak.read_text(encoding="utf-8") == original

    # Zero [[instance]] tables after --hard.
    import re
    instance_blocks = re.findall(r"^\[\[instance\]\]", result, re.MULTILINE)
    assert len(instance_blocks) == 0, (
        f"--hard left {len(instance_blocks)} [[instance]] block(s):\n{result}"
    )


# ---------------------------------------------------------------------------
# Contract 3: check always exits 0 (excluded from the `all` glob loop)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(which("bash") is None, reason="bash not available")
def test_step47_check_always_satisfied_when_file_missing(tmp_path):
    """check exits 0 even when instances.toml does not exist."""
    missing = tmp_path / "no-such-file.toml"
    assert not missing.exists()

    proc = _run_step("check", toml_path=missing)
    assert proc.returncode == 0, (
        f"check returned non-zero when file absent:\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )


@pytest.mark.skipif(which("bash") is None, reason="bash not available")
def test_step47_check_always_satisfied_when_file_exists(tmp_path):
    """check exits 0 even when instances.toml exists with valid instances."""
    live_dir = tmp_path / "addon"
    live_dir.mkdir()
    toml = _toml_with_instances(tmp_path, [
        {"series": "17.0", "addons_path": [str(live_dir)]},
    ])
    assert toml.exists()

    proc = _run_step("check", toml_path=toml)
    assert proc.returncode == 0, (
        f"check returned non-zero when file present:\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
