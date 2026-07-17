"""Behavioral tests for scripts/lib/resource_limits.sh (Problem 1 hardening).

Business rule protected: "a big install fails cleanly / is capped, on EVERY
Odoo version, and the caller can override or uncap it." This file protects the
VALUE-RESOLUTION contract (env override wins; the default formula; the
uncapped escape hatch) - the odoo-bin COMMAND-CONSTRUCTION contract (ulimit
wrap + --limit-memory-hard placement) is protected separately in
test_instance_ops_hardening.py.

All tests source the real resource_limits.sh in a throwaway bash -c and call
its public functions directly - no network, no real /proc/meminfo dependency
(a synthetic meminfo-shaped file is supplied via the test-only
_RESOURCE_LIMIT_MEMINFO_PATH override), no real odoo-bin. Offline and
deterministic.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "resource_limits.sh"

requires_bash = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash not available"
)

# The 4 GiB floor and its KiB form, mirrored here as PLAIN test-oracle
# constants (not imported from the script) so a change to the script's
# internal variable name can never silently make this test agree with itself.
FLOOR_BYTES = 4294967296
FLOOR_KIB = FLOOR_BYTES // 1024


def _clean_env(overrides: dict | None = None) -> dict:
    env = dict(os.environ)
    for var in (
        "ODOO_AI_LIMIT_MEMORY_HARD",
        "ODOO_AI_LIMIT_MEMORY_SOFT",
        "ODOO_AI_LIMIT_TIME_REAL",
        "_RESOURCE_LIMIT_MEMINFO_PATH",
    ):
        env.pop(var, None)
    if overrides:
        env.update(overrides)
    return env


def _write_meminfo(tmp_path: Path, memtotal_kib: int) -> Path:
    p = tmp_path / "meminfo"
    p.write_text(f"MemTotal:       {memtotal_kib} kB\nMemFree:        123 kB\n", encoding="utf-8")
    return p


def _call(func_expr: str, env: dict) -> subprocess.CompletedProcess:
    """Source the lib and evaluate func_expr (a single bash expression/statement)."""
    script = f'set -euo pipefail\nsource "{LIB}"\n{func_expr}\n'
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=env, timeout=15
    )


# ---------------------------------------------------------------------------
# env override wins
# ---------------------------------------------------------------------------

@requires_bash
def test_env_override_wins_for_hard_bytes():
    """An explicit ODOO_AI_LIMIT_MEMORY_HARD must be used VERBATIM, not the formula."""
    env = _clean_env({"ODOO_AI_LIMIT_MEMORY_HARD": "9876543210"})
    res = _call("resource_limit_hard_bytes", env)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "9876543210"


@requires_bash
def test_env_override_wins_over_a_large_memtotal(tmp_path):
    """Even when MemTotal would compute a LARGER default, an explicit override wins."""
    meminfo = _write_meminfo(tmp_path, memtotal_kib=64 * 1024 * 1024)  # 64 GiB
    env = _clean_env({
        "ODOO_AI_LIMIT_MEMORY_HARD": "5000000000",
        "_RESOURCE_LIMIT_MEMINFO_PATH": str(meminfo),
    })
    res = _call("resource_limit_hard_bytes", env)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "5000000000"


@requires_bash
def test_env_override_wins_for_soft_and_time_real():
    env = _clean_env({
        "ODOO_AI_LIMIT_MEMORY_SOFT": "1234567",
        "ODOO_AI_LIMIT_TIME_REAL": "999",
    })
    res_soft = _call("resource_limit_soft_bytes", env)
    res_time = _call("resource_limit_time_real", env)
    assert res_soft.stdout.strip() == "1234567", res_soft.stderr
    assert res_time.stdout.strip() == "999", res_time.stderr


# ---------------------------------------------------------------------------
# default formula: floor(MemTotal * 0.5), floored at 4 GiB
# ---------------------------------------------------------------------------

@requires_bash
def test_default_floors_at_4gib_when_memtotal_small(tmp_path):
    """A small MemTotal (half would be well under 4 GiB) must still floor at 4 GiB -
    never a cap so tight it recreates the OOM the fix exists to prevent."""
    meminfo = _write_meminfo(tmp_path, memtotal_kib=1 * 1024 * 1024)  # 1 GiB total
    env = _clean_env({"_RESOURCE_LIMIT_MEMINFO_PATH": str(meminfo)})
    res = _call("resource_limit_hard_bytes", env)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == str(FLOOR_BYTES)


@requires_bash
def test_default_uses_half_memtotal_when_above_floor(tmp_path):
    """Above the floor, the default is exactly half of MemTotal (in bytes)."""
    memtotal_kib = 20 * 1024 * 1024  # 20 GiB
    meminfo = _write_meminfo(tmp_path, memtotal_kib=memtotal_kib)
    env = _clean_env({"_RESOURCE_LIMIT_MEMINFO_PATH": str(meminfo)})
    res = _call("resource_limit_hard_bytes", env)
    assert res.returncode == 0, res.stderr
    expected = (memtotal_kib * 1024) // 2
    assert expected > FLOOR_BYTES, "test fixture must exercise the above-floor branch"
    assert res.stdout.strip() == str(expected)


@requires_bash
def test_default_falls_back_to_floor_when_meminfo_unreadable():
    """An unreadable/missing meminfo source (e.g. macOS, no /proc) must fall back to
    the 4 GiB floor, never crash and never silently uncap."""
    env = _clean_env({"_RESOURCE_LIMIT_MEMINFO_PATH": "/nonexistent/meminfo/path"})
    res = _call("resource_limit_hard_bytes", env)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == str(FLOOR_BYTES)


@requires_bash
def test_hard_kib_is_hard_bytes_divided_by_1024(tmp_path):
    """resource_limit_hard_kib must be the floor(bytes/1024) form of the SAME
    resolved value ulimit -Sv expects."""
    memtotal_kib = 20 * 1024 * 1024
    meminfo = _write_meminfo(tmp_path, memtotal_kib=memtotal_kib)
    env = _clean_env({"_RESOURCE_LIMIT_MEMINFO_PATH": str(meminfo)})
    bytes_res = _call("resource_limit_hard_bytes", env)
    kib_res = _call("resource_limit_hard_kib", env)
    assert bytes_res.returncode == 0 and kib_res.returncode == 0
    expected_kib = int(bytes_res.stdout.strip()) // 1024
    assert kib_res.stdout.strip() == str(expected_kib)


# ---------------------------------------------------------------------------
# uncapped escape hatch
# ---------------------------------------------------------------------------

@requires_bash
def test_zero_override_is_uncapped():
    """ODOO_AI_LIMIT_MEMORY_HARD=0 must resolve resource_limit_is_uncapped to TRUE
    (exit 0) and resource_limit_hard_bytes to '0' - the caller then skips ulimit
    AND still emits --limit-memory-hard=0."""
    env = _clean_env({"ODOO_AI_LIMIT_MEMORY_HARD": "0"})
    flag = _call(
        "if resource_limit_is_uncapped; then echo UNCAPPED; else echo CAPPED; fi", env
    )
    bytes_res = _call("resource_limit_hard_bytes", env)
    assert flag.stdout.strip() == "UNCAPPED", flag.stderr
    assert bytes_res.stdout.strip() == "0"


@requires_bash
def test_explicit_empty_override_is_uncapped():
    """An explicitly-set-but-EMPTY override ('empty-by-explicit-override') must also
    resolve to uncapped - distinct from leaving the var unset entirely, which
    resolves the default formula instead."""
    env = _clean_env({"ODOO_AI_LIMIT_MEMORY_HARD": ""})
    flag = _call(
        "if resource_limit_is_uncapped; then echo UNCAPPED; else echo CAPPED; fi", env
    )
    assert flag.stdout.strip() == "UNCAPPED", flag.stderr


@requires_bash
def test_unset_is_never_uncapped():
    """Leaving ODOO_AI_LIMIT_MEMORY_HARD unset must resolve the default formula
    (always > 0), never the uncapped escape hatch - only an EXPLICIT 0/empty opts
    into uncapped."""
    env = _clean_env()
    flag = _call(
        "if resource_limit_is_uncapped; then echo UNCAPPED; else echo CAPPED; fi", env
    )
    assert flag.stdout.strip() == "CAPPED", flag.stderr


@requires_bash
def test_non_numeric_override_is_treated_as_uncapped_not_a_crash():
    """A garbage override value must fail SAFE (uncapped, no crash) rather than
    being fed verbatim into arithmetic (which would abort the whole odoo-bin
    launch under `set -e`)."""
    env = _clean_env({"ODOO_AI_LIMIT_MEMORY_HARD": "not-a-number"})
    res = _call("resource_limit_hard_bytes", env)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "0"


# ---------------------------------------------------------------------------
# soft / time-real defaults (A2 long-running listener conf only)
# ---------------------------------------------------------------------------

@requires_bash
def test_soft_default_is_75pct_of_hard_floored():
    env = _clean_env({"ODOO_AI_LIMIT_MEMORY_HARD": "1000000000"})
    res = _call("resource_limit_soft_bytes", env)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == str(1000000000 * 3 // 4)


@requires_bash
def test_soft_default_is_zero_when_hard_is_uncapped():
    """No soft ceiling makes sense without a hard one - uncapped hard -> soft 0."""
    env = _clean_env({"ODOO_AI_LIMIT_MEMORY_HARD": "0"})
    res = _call("resource_limit_soft_bytes", env)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "0"


@requires_bash
def test_time_real_default_is_14000():
    env = _clean_env()
    res = _call("resource_limit_time_real", env)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "14000"
