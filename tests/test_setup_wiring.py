"""Behavior/contract tests for the OPT-IN browser MCP wiring.

Only ONE browser family is eager (chrome-devtools, in .mcp.json - see test_browser_mcp.py). The
other five are OPT-IN, wired on demand by the odoo-setup steps from the SSOT
`scripts/lib/browser_mcp_servers.py`, read by the steps through `browser-mcp-servers.sh`.

The per-family invariants (exact pinned package, headed/headless flag, --isolated for
chrome/playwright but not pagecast, headed shares its default's package) are asserted against
`browser_mcp_npx_args` - what the wiring steps consume - and the step's registration through
`claude mcp add --scope user` with the RESOLVED launch spec. The drift behaviour (check reports a
stale registration, apply removes and re-adds it) is in test_setup_browser_drift.py.

Stdlib + bash only.
"""
import functools
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
LIB = PLUGIN / "scripts" / "lib" / "browser-mcp-servers.sh"
STEP32 = PLUGIN / "scripts" / "setup-steps" / "32-permissions-state-root.sh"
STEP48 = PLUGIN / "scripts" / "setup-steps" / "48-db-local-auth.sh"
ODOO_SETUP_CMD = PLUGIN / "commands" / "odoo-setup.md"

requires_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")

# The five OPT-IN families (everything except the eager headless chrome-devtools).
OPTIN_SERVERS = [
    "chrome-devtools-headed",
    "playwright", "playwright-headed",
    "pagecast", "pagecast-headed",
]
# Opt-in families that still run headless (must pass --headless); the headed ones omit it.
HEADLESS_OPTIN = {"playwright", "pagecast"}
# chrome-devtools/playwright pass --isolated; pagecast never does.
ISOLATED_OPTIN = {"chrome-devtools-headed", "playwright", "playwright-headed"}
# Expected package per family; the version is checked separately (exact, never a range).
EXPECTED_PKG = {
    "chrome-devtools-headed": "chrome-devtools-mcp",
    "playwright": "@playwright/mcp",
    "playwright-headed": "@playwright/mcp",
    "pagecast": "@mcpware/pagecast",
    "pagecast-headed": "@mcpware/pagecast",
}
EXACT = re.compile(r"^(@?[^@]+)@(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)$")


def _clean_env():
    return {k: v for k, v in os.environ.items() if not k.startswith("BROWSER_MCP_")}


@functools.lru_cache(maxsize=None)
def _npx_args(server: str) -> tuple[str, ...]:
    """Return `browser_mcp_npx_args <server>` output (the SSOT the steps consume). Cached: the
    answer is a pure function of the SSOT, and each call is a bash + python launch."""
    assert LIB.is_file(), f"missing SSOT lib: {LIB}"
    res = subprocess.run(
        ["bash", "-c", f'. "{LIB}"; browser_mcp_npx_args "$1"', "_", server],
        capture_output=True, text=True, env=_clean_env(),
    )
    assert res.returncode == 0, f"browser_mcp_npx_args {server} failed: {res.stderr}"
    return tuple(ln for ln in res.stdout.splitlines() if ln != "")


@requires_bash
def test_lib_declares_the_five_optin_families_and_the_eager_one_outside_them():
    res = subprocess.run(
        ["bash", "-c", f'. "{LIB}"; printf "%s\\n" "${{BROWSER_MCP_OPTIN_SERVERS[@]}}"; '
                       'echo "eager=$BROWSER_MCP_EAGER_SERVER"'],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    lines = [ln for ln in res.stdout.splitlines() if ln]
    assert lines[:-1] == OPTIN_SERVERS, f"opt-in family list drifted: {lines[:-1]}"
    assert lines[-1] == "eager=chrome-devtools"


@requires_bash
@pytest.mark.parametrize("server", OPTIN_SERVERS)
def test_optin_family_launches_an_exactly_pinned_package_with_its_headless_and_isolated_flags(server):
    """`npx -y pkg@1` reuses whatever 1.x the machine's npm cache holds; only an exact version
    makes the file-write rules the same on every machine. Headless families pass --headless and
    headed ones omit it; chrome-devtools/playwright pass --isolated (concurrent-session safety)
    and pagecast does not (unsupported)."""
    args = _npx_args(server)
    first = args[1] if args[0] == "-p" else args[0]
    m = EXACT.match(first)
    assert m, f"{server} must launch an exactly pinned package first (got {args})"
    assert m.group(1) == EXPECTED_PKG[server], f"{server} launches the wrong package: {first}"
    for i, a in enumerate(args[:-1]):
        if a == "-p":
            assert EXACT.match(args[i + 1]), f"{server}: an unpinned package {args[i + 1]!r}"
    assert ("--headless" in args) == (server in HEADLESS_OPTIN), f"{server}: wrong --headless"
    assert ("--isolated" in args) == (server in ISOLATED_OPTIN), f"{server}: wrong --isolated"


@requires_bash
def test_headed_variant_shares_package_with_headless_default():
    """A -headed family must launch the same package as its headless sibling."""
    for backend in ("chrome-devtools", "playwright", "pagecast"):
        assert _npx_args(backend)[0] == _npx_args(f"{backend}-headed")[0], backend


@pytest.mark.parametrize("step", [STEP32, STEP48], ids=lambda p: p.stem)
def test_a_setup_step_script_is_executable(step):
    assert step.is_file(), f"missing step script: {step}"
    assert os.access(step, os.X_OK), f"step script must be executable: {step}"


# --------------------------------------------------------------------------- #
# Every setup step is reachable from the setup command                        #
# --------------------------------------------------------------------------- #

# Scripts under setup-steps/ that are NOT setup steps: `55-instance-ops` is the on-demand
# execution layer the odoo-local `instance_build` tool (and the allocator CLI) drives; its `check`
# is always satisfied and the setup command never names it.
NOT_A_SETUP_STEP = {"55-instance-ops"}


def test_every_setup_step_script_is_named_in_the_setup_command():
    """A step script the setup command never names is dead code: nothing tells an agent to run it,
    and every behaviour test of the step stays green regardless."""
    command = ODOO_SETUP_CMD.read_text(encoding="utf-8")
    steps = sorted(
        p.stem for p in (PLUGIN / "scripts" / "setup-steps").glob("[0-9][0-9]-*.sh")
    )
    assert len(steps) > 10, f"step discovery is vacuous: {steps}"
    unnamed = [s for s in steps if s not in NOT_A_SETUP_STEP and s not in command]
    assert not unnamed, f"commands/odoo-setup.md never names these setup steps: {unnamed}"
