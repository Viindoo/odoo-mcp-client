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


def test_live_mcp_json_ships_only_the_eager_browser_server():
    """Guard the premise: five browser families really did leave .mcp.json, and the only OTHER
    key present is a LOCAL (non-browser) server, never a second browser family. LOCAL_SERVERS is
    the SSOT for what counts as "not a browser family" here (scripts/lib/plugin_mcp_servers.py)."""
    data = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
    servers = set(data.get("mcpServers", {}))
    assert servers - bp.plugin_mcp_servers.LOCAL_SERVERS == {"chrome-devtools"}


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


# --- V-19: bare (non-plugin-namespaced) tool names -------------------------------------
# The 5 opt-in browser families are registered STAND-ALONE by odoo-setup, so their tool
# names carry NO `plugin_<name>_` prefix at all (e.g. `mcp__playwright__browser_click`,
# verbatim in a deferred-tool listing). Before the fix, `_matches` only recognized the
# plugin-namespaced form, so these tools showed a manual permission prompt on first use in
# the very session they were just wired (durable settings.json allowlist self-healed only
# NEXT session). `_matches` must cover the IDENTICAL name set `browser_prefixes()` emits.
@pytest.mark.parametrize("server", ALL_SIX)
def test_matches_accepts_bare_form_for_every_family(server):
    tool = f"mcp__{server}__navigate_page"
    assert bp._matches(tool, PLUGIN) is True, (
        f"bare-form tool for family {server!r} must match - browser_prefixes() emits a bare "
        f"allow-prefix for it, so _matches must accept the same name set (V-19)"
    )


def test_matches_bare_form_rejects_foreign_server():
    """A bare tool from an unrelated MCP server must still be rejected."""
    assert bp._matches("mcp__odoo-semantic__model_inspect", PLUGIN) is False
    assert bp._matches("mcp__github__get_me", PLUGIN) is False


# --- V-19: hooks.json PermissionRequest matcher (the gate BEFORE _matches even runs) ----
# Claude Code only invokes auto-approve-browser.sh at all when the tool name satisfies this
# regex - so `_matches` alone is not sufficient; the matcher itself must also accept the
# bare form, or the hook never runs for the 5 opt-in families in the first place.
def _permission_request_matcher():
    """The BROWSER PermissionRequest entry - i.e. the one that dispatches
    auto-approve-browser.sh. hooks.json registers a SECOND, separate PermissionRequest
    entry for auto-approve-local.sh (odoo-local's own tools) - identified by its command,
    not by position, so this helper stays correct regardless of entry order."""
    hooks_json = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    entries = hooks_json["hooks"]["PermissionRequest"]
    for entry in entries:
        commands = [h.get("command", "") for h in entry.get("hooks", [])]
        if any("auto-approve-browser.sh" in c for c in commands):
            return entry["matcher"]
    raise AssertionError("no PermissionRequest entry dispatches auto-approve-browser.sh")


@pytest.mark.parametrize("server", ALL_SIX)
def test_hooks_json_permission_matcher_accepts_bare_form_for_every_family(server):
    import re

    pattern = _permission_request_matcher()
    tool = f"mcp__{server}__navigate_page"
    assert re.match(pattern, tool), (
        f"hooks.json PermissionRequest matcher {pattern!r} must match the bare-form tool "
        f"{tool!r} - otherwise auto-approve-browser.sh never even runs for this family (V-19)"
    )


def test_hooks_json_permission_matcher_still_accepts_namespaced_form():
    import re

    pattern = _permission_request_matcher()
    tool = "mcp__plugin_odoo-ai-agents_chrome-devtools__navigate_page"
    assert re.match(pattern, tool)


def test_hooks_json_permission_matcher_rejects_foreign_server():
    import re

    pattern = _permission_request_matcher()
    assert re.match(pattern, "mcp__odoo-semantic__model_inspect") is None
    assert re.match(pattern, "Bash") is None


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


# --- LOCAL (non-browser) servers must never leak into the browser permission surface -----
# odoo-local is bundled in the SAME .mcp.json as chrome-devtools, but it is not a browser
# family (scripts/lib/plugin_mcp_servers.py LOCAL_SERVERS): some of its tools are destructive
# (lease_release, an applied lease_gc), so a blanket browser-style auto-allow would be a
# category error. These are the negative-case counterparts to the ALL_SIX tests above.

def test_local_server_gets_no_browser_prefix():
    """odoo-local must be subtracted from the union even though it lives in .mcp.json - it
    must never gain either the plugin-namespaced or the bare browser allow-prefix."""
    prefixes = set(bp.browser_prefixes(PLUGIN))
    assert "mcp__plugin_odoo-ai-agents_odoo-local" not in prefixes
    assert "mcp__odoo-local" not in prefixes


def test_matches_rejects_local_server_tool():
    """A tool namespaced to odoo-local must not satisfy the browser-permission SSOT's
    _matches() - approving it is auto-approve-local.sh's job, a category apart."""
    assert bp._matches("mcp__plugin_odoo-ai-agents_odoo-local__lease_release", PLUGIN) is False
    assert bp._matches("mcp__plugin_odoo-ai-agents_odoo-local__lease_gc", PLUGIN) is False


def test_all_servers_excludes_local_even_when_only_in_live_mcp_json(tmp_path):
    """The subtraction must apply to a LIVE .mcp.json entry too, not just the static list -
    a local server declared only in a test fixture's .mcp.json (never in STATIC_SERVERS)
    must still be excluded from the union, exactly like a real odoo-local entry is."""
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "odoo-ai-agents"}), encoding="utf-8"
    )
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"odoo-local": {"command": "python3"}}}), encoding="utf-8"
    )
    prefixes = set(bp.browser_prefixes(tmp_path))
    assert "mcp__plugin_odoo-ai-agents_odoo-local" not in prefixes
    assert "mcp__odoo-local" not in prefixes
