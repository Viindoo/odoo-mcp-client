"""Structural validation for the bundled (EAGER) browser MCP server.

The odoo-ai-agents plugin ships a `.mcp.json` that Claude Code auto-loads on
install. To keep a plain session from eager-launching six browser npx processes
it does not need, `.mcp.json` now declares EXACTLY ONE eager server: the
headless `chrome-devtools`. The other five families (chrome-devtools-headed,
playwright[-headed], pagecast[-headed]) are OPT-IN - wired on demand by the
odoo-setup steps and asserted in `test_setup_wiring.py`, NOT here.

Contract this file protects:
  - `.mcp.json` ships exactly ONE eager BROWSER server (LOCAL, non-browser servers -
    e.g. `odoo-local` - are a separate concern, tracked by scripts/lib/plugin_mcp_servers.py's
    LOCAL_SERVERS SSOT, and are excluded from this file's browser-only assertions);
  - it is `chrome-devtools`, headless, `--isolated`;
  - it is a local stdio-npx server (portable across Claude/Codex/Gemini);
  - its package is version-PINNED (never `@latest`, so a session is reproducible).

Stdlib-only so it runs anywhere `python3 -m pytest` works.
"""
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS_PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
BROWSER_MCP = SKILLS_PLUGIN / ".mcp.json"
SKILLS_MANIFEST = SKILLS_PLUGIN / ".claude-plugin" / "plugin.json"

# The single eager family. Everything else is opt-in (test_setup_wiring.py).
EAGER_SERVER = "chrome-devtools"


def _local_servers() -> frozenset:
    """scripts/lib/plugin_mcp_servers.py LOCAL_SERVERS - the SSOT for which bundled
    .mcp.json servers are LOCAL (non-browser), e.g. `odoo-local`. This file only
    asserts the BROWSER-family contract, so a local server must be subtracted
    before checking "exactly one eager server" - it is a different category
    entirely, not a second eager browser family."""
    spec = importlib.util.spec_from_file_location(
        "plugin_mcp_servers", SKILLS_PLUGIN / "scripts" / "lib" / "plugin_mcp_servers.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.LOCAL_SERVERS


@pytest.fixture(scope="module")
def mcp():
    assert BROWSER_MCP.is_file(), f"missing browser MCP config: {BROWSER_MCP}"
    with BROWSER_MCP.open(encoding="utf-8") as fh:
        return json.load(fh)  # raises if invalid JSON


def test_exactly_one_eager_server(mcp):
    servers = mcp.get("mcpServers", {})
    browser_servers = set(servers) - _local_servers()
    assert browser_servers == {EAGER_SERVER}, (
        f"expected exactly one eager BROWSER server {{{EAGER_SERVER!r}}}, got {browser_servers} "
        f"(all .mcp.json keys: {set(servers)}). The other five browser families are opt-in and "
        "must NOT be in .mcp.json; a LOCAL server (plugin_mcp_servers.LOCAL_SERVERS) is a "
        "different category and is subtracted here, not counted as a second eager browser family."
    )


def test_local_servers_are_not_counted_as_browser_servers(mcp):
    """Negative case: a LOCAL server (e.g. odoo-local) may coexist in .mcp.json, but it must
    never be mistaken for a browser family - it gets no browser allow-prefix (see
    test_browser_prefixes.py) and is not approved by auto-approve-browser.sh (see
    test_auto_approve_browser.py)."""
    local = _local_servers()
    servers = set(mcp.get("mcpServers", {}))
    assert local & servers, (
        f"premise failed: no local server from {sorted(local)} found in .mcp.json "
        f"(got {sorted(servers)}) - this test would otherwise pass vacuously"
    )
    assert not (local & {EAGER_SERVER}), "a local server must never equal the eager browser server"


def test_eager_server_is_local_stdio_npx(mcp):
    """Codex accepts only local servers -> the eager server must be stdio via npx."""
    spec = mcp["mcpServers"][EAGER_SERVER]
    assert spec.get("type") == "stdio", f"{EAGER_SERVER} must be stdio (cross-runtime portable)"
    assert spec.get("command") == "npx", f"{EAGER_SERVER} must launch via npx (auto-download)"
    args = spec.get("args", [])
    assert isinstance(args, list) and args, f"{EAGER_SERVER} must pass npx args"
    assert "-y" in args, f"{EAGER_SERVER} npx args should include -y for non-interactive install"


def test_eager_server_is_headless_and_isolated(mcp):
    """The eager server runs headless (safe on a no-display host) and isolated."""
    args = mcp["mcpServers"][EAGER_SERVER]["args"]
    assert "--headless" in args, f"eager {EAGER_SERVER} must pass --headless (got {args})"
    assert "--isolated" in args, f"eager {EAGER_SERVER} must pass --isolated (got {args})"


def test_eager_server_package_is_pinned_not_latest(mcp):
    """The npm package MUST be version-pinned (e.g. chrome-devtools-mcp@1), never @latest."""
    args = mcp["mcpServers"][EAGER_SERVER]["args"]
    pkgs = [a for a in args if "@" in a]
    assert pkgs, f"{EAGER_SERVER} must name a pinned npm package (got {args})"
    for pkg in pkgs:
        assert not pkg.endswith("@latest"), (
            f"{EAGER_SERVER} package must be pinned, not @latest (got {pkg!r})"
        )
        # A pin looks like <name>@<version-or-major>; require a concrete tail.
        assert re.search(r"@[0-9]", pkg), (
            f"{EAGER_SERVER} package must pin to a numeric version/major (got {pkg!r})"
        )


def test_manifest_points_at_browser_mcp():
    with SKILLS_MANIFEST.open(encoding="utf-8") as fh:
        manifest = json.load(fh)
    assert manifest.get("mcpServers") == "./.mcp.json", (
        "skills manifest must reference ./.mcp.json so the eager browser server loads"
    )
