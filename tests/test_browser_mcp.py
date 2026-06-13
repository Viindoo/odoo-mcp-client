"""Structural validation for the bundled browser MCP servers.

The odoo-ai-agents plugin ships a `.mcp.json` declaring six stdio/npx browser
servers that give the visual-UI skills their "eyes". Each of the three browser
backends (chrome-devtools, playwright, pagecast) ships TWO variants:

  - a headless DEFAULT (`<name>`): no UI, safe on no-display/CI hosts and for
    concurrent sessions — passes `--headless`;
  - a HEADED variant (`<name>-headed`): visible UI the AI selects only when the
    human asks to watch the browser — omits `--headless`.

These servers MUST stay local stdio-npx so the same declaration is portable
across Claude Code, Codex CLI, and Gemini CLI (Codex only accepts local servers
— the narrowest common denominator). Browser mode is fixed at launch, so the
headless/headed choice is server-selection, NOT an env var / on-disk flag.

Stdlib-only so it runs anywhere `python3 -m pytest` works.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS_PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
BROWSER_MCP = SKILLS_PLUGIN / ".mcp.json"
SKILLS_MANIFEST = SKILLS_PLUGIN / ".claude-plugin" / "plugin.json"

# Three backends x two variants (headless default + headed).
HEADLESS_DEFAULT = {"chrome-devtools", "playwright", "pagecast"}
HEADED_VARIANTS = {"chrome-devtools-headed", "playwright-headed", "pagecast-headed"}
EXPECTED_SERVERS = HEADLESS_DEFAULT | HEADED_VARIANTS

# chrome-devtools + playwright support --isolated (private profile per launch ->
# multiple concurrent sessions don't collide). pagecast isolates per-session
# internally and has no --isolated flag.
ISOLATED_SERVERS = {
    "chrome-devtools", "chrome-devtools-headed",
    "playwright", "playwright-headed",
}


@pytest.fixture(scope="module")
def mcp():
    assert BROWSER_MCP.is_file(), f"missing browser MCP config: {BROWSER_MCP}"
    with BROWSER_MCP.open(encoding="utf-8") as fh:
        return json.load(fh)  # raises if invalid JSON


def test_declares_all_browser_servers(mcp):
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


@pytest.mark.parametrize("name", sorted(HEADLESS_DEFAULT))
def test_headless_default_servers_pass_headless(mcp, name):
    """The default variant must run headless so it works on a no-display host."""
    args = mcp["mcpServers"][name]["args"]
    assert "--headless" in args, (
        f"{name} is the headless default and must pass --headless (got {args})"
    )


@pytest.mark.parametrize("name", sorted(HEADED_VARIANTS))
def test_headed_variants_omit_headless(mcp, name):
    """The -headed variant must NOT pass --headless (it shows a visible browser)."""
    args = mcp["mcpServers"][name]["args"]
    assert "--headless" not in args, (
        f"{name} is the headed variant and must NOT pass --headless (got {args})"
    )


@pytest.mark.parametrize("name", sorted(ISOLATED_SERVERS))
def test_isolated_servers_pass_isolated(mcp, name):
    """chrome-devtools/playwright must pass --isolated for concurrent-session safety."""
    args = mcp["mcpServers"][name]["args"]
    assert "--isolated" in args, (
        f"{name} must pass --isolated so concurrent sessions get a private profile (got {args})"
    )


@pytest.mark.parametrize("name", ["pagecast", "pagecast-headed"])
def test_pagecast_variants_omit_isolated(mcp, name):
    """pagecast has no --isolated flag (it isolates per-session internally)."""
    args = mcp["mcpServers"][name]["args"]
    assert "--isolated" not in args, (
        f"{name} must not pass --isolated (unsupported by @mcpware/pagecast) (got {args})"
    )


@pytest.mark.parametrize("backend", sorted(HEADLESS_DEFAULT))
def test_headed_variant_shares_package_with_default(mcp, backend):
    """A -headed variant must launch the same npm package as its headless default
    (it differs only by dropping --headless)."""
    headed = f"{backend}-headed"
    default_pkgs = [a for a in mcp["mcpServers"][backend]["args"] if "@" in a]
    headed_pkgs = [a for a in mcp["mcpServers"][headed]["args"] if "@" in a]
    assert default_pkgs == headed_pkgs, (
        f"{headed} must launch the same package as {backend} "
        f"(default {default_pkgs} vs headed {headed_pkgs})"
    )


def test_manifest_points_at_browser_mcp():
    with SKILLS_MANIFEST.open(encoding="utf-8") as fh:
        manifest = json.load(fh)
    assert manifest.get("mcpServers") == "./.mcp.json", (
        "skills manifest must reference ./.mcp.json so the browser servers load"
    )
