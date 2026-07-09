"""Contract tests for browser_prefixes.py - permissions DECOUPLED from eager set.

Issue #156 dropped five of the six browser families out of `.mcp.json` (they are
now opt-in). The permission allow-prefixes MUST NOT follow the eager set: if they
were derived from `.mcp.json` alone, the five opt-in families would be
permission-blocked the moment a user wires one. This file protects the fix -
`browser_prefixes()` yields the plugin-namespaced AND bare allow-prefix for ALL
SIX families (static SSOT UNION the live .mcp.json keys), and `_matches` accepts
an opt-in `-headed` tool that is not in .mcp.json.

Stdlib-only; loads the module by file path (it lives outside the tests package).
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
MODULE_PATH = PLUGIN / "scripts" / "lib" / "browser_prefixes.py"


def _load():
    spec = importlib.util.spec_from_file_location("browser_prefixes", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bp = _load()

# The six families the permission SSOT must always cover, regardless of .mcp.json.
ALL_SIX = [
    "chrome-devtools", "chrome-devtools-headed",
    "playwright", "playwright-headed",
    "pagecast", "pagecast-headed",
]


def test_static_ssot_lists_all_six_families():
    assert set(bp.STATIC_SERVERS) == set(ALL_SIX), (
        f"STATIC_SERVERS must list all six families; got {bp.STATIC_SERVERS}"
    )


def test_live_mcp_json_ships_only_the_eager_server():
    """Guard the premise: five families really did leave .mcp.json."""
    data = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
    assert set(data.get("mcpServers", {})) == {"chrome-devtools"}


def test_prefixes_cover_all_six_families_after_five_leave_mcp_json():
    prefixes = set(bp.browser_prefixes(PLUGIN))
    name = "odoo-ai-agents"
    for server in ALL_SIX:
        assert f"mcp__plugin_{name}_{server}" in prefixes, (
            f"opt-in family {server!r} lost its plugin-namespaced allow-prefix "
            "(permissions must NOT be coupled to the eager .mcp.json set)"
        )
        assert f"mcp__{server}" in prefixes, f"family {server!r} lost its bare allow-prefix"


def test_matches_accepts_optin_headed_tool_not_in_mcp_json():
    """A chrome-devtools-headed tool (opt-in, NOT in .mcp.json) must still match."""
    tool = "mcp__plugin_odoo-ai-agents_chrome-devtools-headed__navigate_page"
    assert bp._matches(tool, PLUGIN) is True


def test_matches_rejects_foreign_tool():
    assert bp._matches("Bash", PLUGIN) is False
    assert bp._matches("mcp__odoo-semantic__model_inspect", PLUGIN) is False


def test_prefixes_union_includes_live_only_extra(tmp_path):
    """A family added to .mcp.json but not in STATIC_SERVERS is still covered (union)."""
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "odoo-ai-agents"}), encoding="utf-8"
    )
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"future-browser": {"command": "npx"}}}), encoding="utf-8"
    )
    prefixes = set(bp.browser_prefixes(tmp_path))
    # static six still present...
    assert "mcp__plugin_odoo-ai-agents_pagecast-headed" in prefixes
    # ...plus the live-only extra.
    assert "mcp__plugin_odoo-ai-agents_future-browser" in prefixes
