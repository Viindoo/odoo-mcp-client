#!/usr/bin/env python3
"""browser_prefixes.py - SSOT derivation of the browser MCP permission prefixes.

The plugin ships its browser MCP servers in <plugin_root>/.mcp.json. Claude Code
namespaces a plugin-provided server's tools as
``mcp__plugin_<plugin>_<server>__<tool>`` and matches an allow rule
``mcp__<server>`` at the ``mcp__<server>__`` BOUNDARY (not as a raw string
prefix). So ``mcp__plugin_odoo-ai-agents_chrome-devtools`` does NOT cover the
distinct ``chrome-devtools-headed`` server - every server, headed variants
included, needs its own prefix. To prevent the two lists drifting apart, the
prefixes are DERIVED here from .mcp.json (the single source of truth for which
servers exist) rather than hand-maintained.

stdlib-only (no jq, no 3rd-party). Two CLI modes used by callers:

    python3 browser_prefixes.py prefixes
        Print, one per line, for each server S: ``mcp__plugin_<name>_<S>`` then
        the bare ``mcp__<S>``.

    python3 browser_prefixes.py match <tool_name>
        Exit 0 if <tool_name> starts with ``mcp__plugin_<name>_<S>__`` for some
        server S, else exit 1.

If .mcp.json / plugin.json cannot be read or yields no servers, fall back to the
static base list so a caller never receives an empty result.
"""
import json
import re
import sys
from pathlib import Path

# scripts/lib/browser_prefixes.py -> plugin_root is two dirs up (lib -> scripts -> root).
PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent

# Static fallback if .mcp.json can't be read. Lists all 6 shipped servers (both
# variants) so the fallback never silently re-drops the `-headed` coverage that is
# the whole point of deriving from .mcp.json.
FALLBACK_PLUGIN_NAME = "odoo-ai-agents"
FALLBACK_SERVERS = [
    "chrome-devtools", "chrome-devtools-headed",
    "playwright", "playwright-headed",
    "pagecast", "pagecast-headed",
]

_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def _normalize(name: str) -> str:
    """Normalize any char outside [A-Za-z0-9_-] to '_' (mirrors Claude Code)."""
    return _SAFE.sub("_", name)


def _read_plugin_name(plugin_root: Path) -> str:
    try:
        data = json.loads((plugin_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        name = data.get("name")
        if isinstance(name, str) and name.strip():
            return name
    except Exception:
        pass
    return FALLBACK_PLUGIN_NAME


def _read_servers(plugin_root: Path) -> list:
    try:
        data = json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8"))
        servers = list((data.get("mcpServers") or {}).keys())
        if servers:
            return servers
    except Exception:
        pass
    return list(FALLBACK_SERVERS)


def browser_prefixes(plugin_root: Path = PLUGIN_ROOT) -> list:
    """Return the derived allow-list prefixes (importable for callers/tests)."""
    name = _normalize(_read_plugin_name(plugin_root))
    servers = [_normalize(s) for s in _read_servers(plugin_root)]
    prefixes = []
    for s in servers:
        prefixes.append(f"mcp__plugin_{name}_{s}")
        prefixes.append(f"mcp__{s}")
    return prefixes


def _matches(tool_name: str, plugin_root: Path = PLUGIN_ROOT) -> bool:
    """True if tool_name is namespaced to one of this plugin's browser servers.

    Matches at the ``mcp__plugin_<name>_<server>__`` boundary - the same rule
    Claude Code uses - so e.g. ``...chrome-devtools__navigate_page`` matches but
    ``Bash`` or a foreign server does not.
    """
    name = _normalize(_read_plugin_name(plugin_root))
    servers = [_normalize(s) for s in _read_servers(plugin_root)]
    for s in servers:
        if tool_name.startswith(f"mcp__plugin_{name}_{s}__"):
            return True
    return False


def main(argv) -> int:
    if len(argv) >= 2 and argv[1] == "prefixes":
        for p in browser_prefixes():
            print(p)
        return 0
    if len(argv) >= 3 and argv[1] == "match":
        return 0 if _matches(argv[2]) else 1
    print("Usage: browser_prefixes.py {prefixes|match <tool_name>}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
