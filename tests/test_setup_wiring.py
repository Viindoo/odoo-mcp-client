"""Behavior/contract tests for the OPT-IN browser MCP wiring.

Only ONE browser family is eager (chrome-devtools, in .mcp.json - see
test_browser_mcp.py). The other five are OPT-IN, wired on demand by the
odoo-setup steps from the SSOT `scripts/lib/browser-mcp-servers.sh`. The five
per-family invariants that used to live in test_browser_mcp.py (correct pinned
package, headed/headless flag, --isolated for chrome/playwright but not
pagecast, headed shares its default's package) are RELOCATED here - they now
protect the WIRING the setup steps emit, not the (now single-server) .mcp.json.

We assert the invariants against `browser_mcp_npx_args` (the shell SSOT the
wiring steps consume) so the args the step registers are exactly right, and we
assert the new Claude opt-in step (12-browser-mcp-optin.sh) uses
`claude mcp add --scope user` over the five opt-in families.

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
# Expected pinned package per family (data-driven; current published major).
EXPECTED_PKG = {
    "chrome-devtools-headed": "chrome-devtools-mcp@1",
    "playwright": "@playwright/mcp@0",
    "playwright-headed": "@playwright/mcp@0",
    "pagecast": "@mcpware/pagecast@0",
    "pagecast-headed": "@mcpware/pagecast@0",
}


def _npx_args(server: str) -> list[str]:
    """Return `browser_mcp_npx_args <server>` output (the SSOT the steps consume)."""
    assert LIB.is_file(), f"missing SSOT lib: {LIB}"
    res = subprocess.run(
        ["bash", "-c", f'. "{LIB}"; browser_mcp_npx_args "$1"', "_", server],
        capture_output=True, text=True,
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
def test_optin_family_package_is_pinned(server):
    """Each opt-in family must launch its expected pinned package, never @latest."""
    args = _npx_args(server)
    pkgs = [a for a in args if "@" in a]
    assert pkgs, f"{server} must name a pinned npm package (got {args})"
    assert EXPECTED_PKG[server] in pkgs, (
        f"{server} must pin {EXPECTED_PKG[server]!r} (got {pkgs})"
    )
    for pkg in pkgs:
        assert not pkg.endswith("@latest"), f"{server} must be pinned, not @latest ({pkg})"


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
    """A -headed opt-in family must launch the same package as its headless sibling."""
    for backend in ("playwright", "pagecast"):
        default_pkgs = [a for a in _npx_args(backend) if "@" in a]
        headed_pkgs = [a for a in _npx_args(f"{backend}-headed") if "@" in a]
        assert default_pkgs == headed_pkgs, (
            f"{backend}-headed must launch the same package as {backend} "
            f"({default_pkgs} vs {headed_pkgs})"
        )
    # chrome-devtools-headed shares the eager chrome-devtools package.
    assert [a for a in _npx_args("chrome-devtools-headed") if "@" in a] == ["chrome-devtools-mcp@1"]


def test_claude_optin_step_uses_user_scope_add():
    """The Claude opt-in step must register families with `claude mcp add --scope user`."""
    text = STEP12.read_text(encoding="utf-8")
    assert "mcp add --scope user" in text, "step 12 must wire families at user scope"
    assert "-- npx -y" in text, "step 12 must register a local npx stdio server"
    assert "BROWSER_MCP_OPTIN_SERVERS" in text, "step 12 must iterate the opt-in family SSOT"
    assert "browser_mcp_npx_args" in text, "step 12 must source args from the SSOT lib"


def test_claude_optin_step_documents_disabled_optout():
    """The opt-out for a browser-free host is documented in the step."""
    text = STEP12.read_text(encoding="utf-8")
    assert "disabledMcpjsonServers" in text, "step 12 must document the disabledMcpjsonServers opt-out"


def test_both_steps_source_the_shared_ssot():
    """Codex/Gemini (step 10) and Claude (step 12) share ONE npx-args SSOT."""
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


def test_odoo_setup_command_enumerates_step32_in_all_and_permissions_modes():
    text = ODOO_SETUP_CMD.read_text(encoding="utf-8")
    # The `all` loop row runs "every step in scripts/setup-steps/ EXCEPT 47-instance-reset" -
    # step 32 must NOT be separately excluded there (it must run under `all` by default).
    all_row = next((ln for ln in text.splitlines() if ln.strip().startswith("| `all`")), None)
    assert all_row is not None, "odoo-setup.md must have an `all` row in the argument-filter table"
    assert "47-instance-reset" in all_row, "the `all` row must still exclude only 47-instance-reset"
    assert "EXCEPT `32-permissions-state-root" not in all_row, (
        "the `all` row must NOT separately exclude 32-permissions-state-root - it runs under `all`"
    )
    # The `permissions` row must explicitly enumerate step 32 alongside step 30.
    permissions_row = next(
        (ln for ln in text.splitlines() if ln.strip().startswith("| `permissions`")), None
    )
    assert permissions_row is not None, (
        "odoo-setup.md must have a `permissions` row in the argument-filter table"
    )
    assert "32-permissions-state-root" in permissions_row, (
        f"the `permissions` mode row must enumerate 32-permissions-state-root; got: {permissions_row!r}"
    )
    assert "30-permissions" in permissions_row, (
        f"the `permissions` mode row must still enumerate 30-permissions; got: {permissions_row!r}"
    )
    # Step reference section must describe step 32 (not just the arg table row).
    assert "**32-permissions-state-root**" in text, (
        "odoo-setup.md must document 32-permissions-state-root in its step-reference section, "
        "not just the argument-filter table"
    )



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


def test_odoo_setup_command_enumerates_step48_in_the_instance_loop():
    text = ODOO_SETUP_CMD.read_text(encoding="utf-8")
    # The `instance` row is the loop that provisions a declared instance, and this
    # step must run inside it - between the venv step that records `python` and the
    # spin-up that needs the connection to work.
    instance_row = next(
        (ln for ln in text.splitlines() if ln.strip().startswith("| `instance`")), None
    )
    assert instance_row is not None, (
        "odoo-setup.md must have an `instance` row in the argument-filter table"
    )
    assert "48-db-local-auth" in instance_row, (
        f"the `instance` mode row must enumerate 48-db-local-auth; got: {instance_row!r}"
    )
    # The `all` loop runs every step except the reset-only one, so 48 must NOT be
    # excluded there either.
    all_row = next((ln for ln in text.splitlines() if ln.strip().startswith("| `all`")), None)
    assert all_row is not None, "odoo-setup.md must have an `all` row"
    assert "48-db-local-auth" not in all_row.replace("EXCEPT", "EXCEPT"), (
        f"the `all` row must not name 48-db-local-auth as an exclusion; got: {all_row!r}"
    )
    # And the step-reference section must describe it, not just the table row.
    assert "**48-db-local-auth**" in text, (
        "odoo-setup.md must document 48-db-local-auth in its step-reference section, "
        "not just the argument-filter table"
    )
    # Its two non-default verbs are the user's escape routes; naming them is what
    # makes the change reversible from the documentation alone.
    for verb in ("revert", "check"):
        # Matched loosely on purpose: the command file quotes the path in some
        # places ("$STEPS_DIR/48-db-local-auth.sh" check) and not in others, and
        # this guard is about the VERB being documented, not about its quoting.
        assert re.search(r'48-db-local-auth\.sh"?\s+' + verb, text), (
            "odoo-setup.md must name the {v!r} verb: this step edits a live "
            "pg_hba.conf, so the way back and the way it is offered both belong in "
            "the documented contract".format(v=verb)
        )
