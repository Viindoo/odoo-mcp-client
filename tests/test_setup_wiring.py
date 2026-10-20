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
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
LIB = PLUGIN / "scripts" / "lib" / "browser-mcp-servers.sh"
STEP10 = PLUGIN / "scripts" / "setup-steps" / "10-browser-mcp.sh"
STEP12 = PLUGIN / "scripts" / "setup-steps" / "12-browser-mcp-optin.sh"
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
# Opt-in families that still run headless (must pass --headless) vs headed
# (must omit --headless).
HEADLESS_OPTIN = {"playwright", "pagecast"}
HEADED_OPTIN = {"chrome-devtools-headed", "playwright-headed", "pagecast-headed"}
# chrome-devtools/playwright pass --isolated; pagecast never does.
ISOLATED_OPTIN = {"chrome-devtools-headed", "playwright", "playwright-headed"}
NO_ISOLATED_OPTIN = {"pagecast", "pagecast-headed"}
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


def _npx_args(server: str) -> list[str]:
    """Return `browser_mcp_npx_args <server>` output (the SSOT the steps consume)."""
    assert LIB.is_file(), f"missing SSOT lib: {LIB}"
    res = subprocess.run(
        ["bash", "-c", f'. "{LIB}"; browser_mcp_npx_args "$1"', "_", server],
        capture_output=True, text=True, env=_clean_env(),
    )
    assert res.returncode == 0, f"browser_mcp_npx_args {server} failed: {res.stderr}"
    return [ln for ln in res.stdout.splitlines() if ln != ""]


@requires_bash
def test_lib_declares_five_optin_families():
    res = subprocess.run(
        ["bash", "-c", f'. "{LIB}"; printf "%s\\n" "${{BROWSER_MCP_OPTIN_SERVERS[@]}}"'],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    got = [ln for ln in res.stdout.splitlines() if ln]
    assert got == OPTIN_SERVERS, f"opt-in family list drifted: {got}"


@requires_bash
def test_eager_family_not_in_optin_list():
    res = subprocess.run(
        ["bash", "-c", f'. "{LIB}"; echo "$BROWSER_MCP_EAGER_SERVER"'],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "chrome-devtools"


@requires_bash
@pytest.mark.parametrize("server", OPTIN_SERVERS)
def test_optin_family_package_is_pinned_to_an_exact_version(server):
    """`npx -y pkg@1` reuses whatever 1.x the machine's npm cache holds; only an exact version
    makes the file-write rules the same on every machine."""
    args = _npx_args(server)
    first = args[1] if args[0] == "-p" else args[0]
    m = EXACT.match(first)
    assert m, f"{server} must launch an exactly pinned package first (got {args})"
    assert m.group(1) == EXPECTED_PKG[server], f"{server} launches the wrong package: {first}"
    for i, a in enumerate(args[:-1]):
        if a == "-p":
            assert EXACT.match(args[i + 1]), f"{server}: an unpinned package {args[i + 1]!r}"


@requires_bash
@pytest.mark.parametrize("server", sorted(HEADLESS_OPTIN))
def test_headless_optin_passes_headless(server):
    assert "--headless" in _npx_args(server), f"{server} is a headless family and must pass --headless"


@requires_bash
@pytest.mark.parametrize("server", sorted(HEADED_OPTIN))
def test_headed_optin_omits_headless(server):
    assert "--headless" not in _npx_args(server), f"{server} is headed and must NOT pass --headless"


@requires_bash
@pytest.mark.parametrize("server", sorted(ISOLATED_OPTIN))
def test_isolated_optin_passes_isolated(server):
    assert "--isolated" in _npx_args(server), f"{server} must pass --isolated (concurrent-session safety)"


@requires_bash
@pytest.mark.parametrize("server", sorted(NO_ISOLATED_OPTIN))
def test_pagecast_optin_omits_isolated(server):
    assert "--isolated" not in _npx_args(server), f"{server} must not pass --isolated (unsupported)"


@requires_bash
def test_headed_variant_shares_package_with_headless_default():
    """A -headed family must launch the same package as its headless sibling."""
    for backend in ("chrome-devtools", "playwright", "pagecast"):
        assert _npx_args(backend)[0] == _npx_args(f"{backend}-headed")[0], backend


def test_claude_optin_step_registers_the_resolved_spec_at_user_scope():
    """The Claude opt-in step registers each family with `claude mcp add --scope user`, from the
    resolved launch spec (state-root flags included), and replaces a drifted entry."""
    text = STEP12.read_text(encoding="utf-8")
    assert "mcp add --scope user" in text, "step 12 must wire families at user scope"
    assert "mcp remove --scope user" in text, "step 12 must remove a drifted entry before re-adding"
    assert "BROWSER_MCP_OPTIN_SERVERS" in text, "step 12 must iterate the opt-in family SSOT"
    assert "browser_mcp_spec" in text, "step 12 must register the SSOT's resolved launch spec"


def test_claude_optin_step_documents_disabled_optout():
    """The opt-out for a browser-free host is documented in the step."""
    text = STEP12.read_text(encoding="utf-8")
    assert "disabledMcpjsonServers" in text, "step 12 must document the disabledMcpjsonServers opt-out"


def test_both_steps_source_the_shared_ssot():
    """Codex/Gemini (step 10) and Claude (step 12) share ONE launch SSOT."""
    for step in (STEP10, STEP12):
        assert "browser-mcp-servers.sh" in step.read_text(encoding="utf-8"), (
            f"{step.name} must source the shared browser-mcp-servers.sh SSOT"
        )


# --------------------------------------------------------------------------- #
# P3: step 32 (state-root permissions) is wired into odoo-setup.md            #
# --------------------------------------------------------------------------- #

def test_step32_file_exists_and_executable():
    assert STEP32.is_file(), f"missing step script: {STEP32}"
    assert os.access(STEP32, os.X_OK), f"step script must be executable: {STEP32}"


# --------------------------------------------------------------------------- #
# Step 48 (local passwordless DB auth) is wired into odoo-setup.md             #
#                                                                             #
# Without this, the step's own 52 behaviour tests all stay green while the step #
# becomes unreachable dead code: nothing else asserts that the setup command    #
# runs it, or that it is executable at all. Modelled on step 32's pair above.   #
# --------------------------------------------------------------------------- #

def test_step48_file_exists_and_executable():
    assert STEP48.is_file(), f"missing step script: {STEP48}"
    assert os.access(STEP48, os.X_OK), f"step script must be executable: {STEP48}"


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
