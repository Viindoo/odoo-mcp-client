"""Structural validation for the bundled browser MCP servers.

The odoo-ai-agents plugin ships a `.mcp.json` declaring three
stdio/npx browser servers (chrome-devtools, playwright, pagecast) that give
the visual-UI skills their "eyes". These servers MUST stay local stdio-npx so
the same declaration is portable across Claude Code, Codex CLI, and Gemini CLI
(Codex only accepts local servers — the narrowest common denominator).

Stdlib-only so it runs anywhere `python3 -m pytest` works.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS_PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
BROWSER_MCP = SKILLS_PLUGIN / ".mcp.json"
SKILLS_MANIFEST = SKILLS_PLUGIN / ".claude-plugin" / "plugin.json"

EXPECTED_SERVERS = {"chrome-devtools", "playwright", "pagecast"}


@pytest.fixture(scope="module")
def mcp():
    assert BROWSER_MCP.is_file(), f"missing browser MCP config: {BROWSER_MCP}"
    with BROWSER_MCP.open(encoding="utf-8") as fh:
        return json.load(fh)  # raises if invalid JSON


def test_declares_the_three_browser_servers(mcp):
    servers = mcp.get("mcpServers", {})
    assert set(servers) == EXPECTED_SERVERS, (
        f"expected exactly {EXPECTED_SERVERS}, got {set(servers)}"
    )


@pytest.mark.parametrize("name", sorted(EXPECTED_SERVERS))
def test_each_server_is_local_stdio_npx(mcp, name):
    """Codex accepts only local servers -> every server must be stdio via npx."""
    spec = mcp["mcpServers"][name]
    assert spec.get("type") == "stdio", f"{name} must be stdio (cross-runtime portable)"
    assert spec.get("command") == "npx", f"{name} must launch via npx (auto-download)"
    args = spec.get("args", [])
    assert isinstance(args, list) and args, f"{name} must pass npx args"
    assert "-y" in args, f"{name} npx args should include -y for non-interactive install"


def test_manifest_points_at_browser_mcp():
    with SKILLS_MANIFEST.open(encoding="utf-8") as fh:
        manifest = json.load(fh)
    assert manifest.get("mcpServers") == "./.mcp.json", (
        "skills manifest must reference ./.mcp.json so the browser servers load"
    )
