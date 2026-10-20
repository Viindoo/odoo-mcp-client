"""Every setup step script must be executable.

Unlike the hooks (always dispatched as `bash <path>`, see test_hooks_executable_consistency.py),
`/odoo-ai-agents:odoo-setup` runs each step directly as `"$s" describe|check|apply`, so a step
shipped without its executable bit fails with "Permission denied" at run time.
`47-instance-reset.sh` shipped as 100644 in 7.8.0 and made `odoo-setup --reset` unusable.
CI checks the tree out from git, so the on-disk mode here is the mode that ships.
"""
from __future__ import annotations

import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS_DIR = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "setup-steps"


def test_every_setup_step_the_command_runs_directly_is_executable():
    steps = sorted(STEPS_DIR.glob("*.sh"))
    assert steps, f"no setup step scripts found under {STEPS_DIR}"
    not_executable = [
        f"{p.name} (mode {oct(stat.S_IMODE(p.stat().st_mode))})"
        for p in steps
        if not p.stat().st_mode & stat.S_IXUSR
    ]
    assert not not_executable, (
        "setup step(s) odoo-setup cannot run (it invokes each step directly, not via bash): "
        + ", ".join(not_executable)
    )
