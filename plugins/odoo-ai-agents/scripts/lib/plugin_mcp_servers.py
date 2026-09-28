#!/usr/bin/env python3
"""plugin_mcp_servers.py - SSOT for this plugin's LOCAL (non-browser) MCP servers.

The plugin's bundled `.mcp.json` ships two DIFFERENT kinds of stdio MCP server, and
they must never be treated alike:

  - BROWSER families (chrome-devtools/playwright/pagecast, headless+headed) - pure
    UI-automation surfaces, safe to blanket-auto-allow. Their SSOT is
    `browser_prefixes.py`.
  - LOCAL servers - talk to THIS MACHINE's own on-disk state (allocator leases,
    instance lifecycle, catalog reads) via a `${CLAUDE_PLUGIN_ROOT}`-relative
    Python entry point. Some of their tools are destructive (a lease release or an
    applied gc can stop a process group and drop a database), so they are NOT a
    browser-style blanket-allow surface, and `${CLAUDE_PLUGIN_ROOT}` only resolves
    inside Claude Code - a local server can never be forwarded to a non-Claude
    runtime's MCP manifest.

This module is the single source of truth for the second set, `LOCAL_SERVERS`, and
is read by:
  - `browser_prefixes.py` - SUBTRACTS this set from its derived permission
    prefixes, so a local server is never seeded as a "browser" permission.
  - `generator/gen_mcp_manifests.py` - EXCLUDES this set from the Codex/Gemini
    manifests it derives from `.mcp.json` (those runtimes cannot resolve
    `${CLAUDE_PLUGIN_ROOT}`).
  - `hooks/auto-approve-local.sh` - the PermissionRequest hook that auto-allows
    a local server's tools (except an apply-mode `lease_gc`).

A local server is ALWAYS plugin-bundled (declared in this plugin's own
`.mcp.json`) - unlike the five opt-in browser families, it is never registered
stand-alone, so its tools carry ONLY the plugin-namespaced form
(`mcp__plugin_<plugin>_<server>__<tool>`), never a bare `mcp__<server>__<tool>`
form. Add a new local server here (and to `.mcp.json`) in lockstep - this is the
one place every consumer reads.

stdlib-only (no jq, no 3rd-party). Tiny CLI for shell hooks that cannot import
Python modules directly:

    python3 plugin_mcp_servers.py servers
        Print each local server name, one per line.

    python3 plugin_mcp_servers.py prefixes
        Print each local server's plugin-namespaced tool-call prefix
        (``mcp__plugin_<name>_<server>``), one per line.

    python3 plugin_mcp_servers.py match <tool_name>
        Exit 0 if <tool_name> is namespaced to one of these local servers, else
        exit 1.
"""
import json
import re
import sys
from pathlib import Path

# scripts/lib/plugin_mcp_servers.py -> plugin_root is two dirs up (lib -> scripts -> root).
PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent

FALLBACK_PLUGIN_NAME = "odoo-ai-agents"

# The plugin-bundled LOCAL stdio MCP servers. See module docstring for why these
# are kept separate from browser_prefixes.py's STATIC_SERVERS.
LOCAL_SERVERS = frozenset({"odoo-local"})

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


def is_local_server(name: str) -> bool:
    """True if `name` is one of this plugin's local (Claude-only) MCP servers."""
    return name in LOCAL_SERVERS


def local_tool_prefix(server: str, plugin_root: Path = PLUGIN_ROOT) -> str:
    """Return the plugin-namespaced tool-call prefix for a local server, e.g.
    'mcp__plugin_odoo-ai-agents_odoo-local'. A local server is always
    plugin-bundled, so - unlike a browser family - it has no bare stand-alone
    form; callers must not also probe a bare `mcp__<server>` prefix for it.
    """
    name = _normalize(_read_plugin_name(plugin_root))
    return f"mcp__plugin_{name}_{_normalize(server)}"


def split_local_tool(tool_name: str, plugin_root: Path = PLUGIN_ROOT):
    """If `tool_name` is namespaced to one of this plugin's local servers, return
    `(server, short_tool_name)`; otherwise return `(None, None)`.

    e.g. split_local_tool("mcp__plugin_odoo-ai-agents_odoo-local__lease_gc")
         -> ("odoo-local", "lease_gc")
    """
    for server in LOCAL_SERVERS:
        prefix = local_tool_prefix(server, plugin_root) + "__"
        if tool_name.startswith(prefix):
            return server, tool_name[len(prefix):]
    return None, None


def is_local_tool(tool_name: str, plugin_root: Path = PLUGIN_ROOT) -> bool:
    """True if tool_name belongs to one of this plugin's local MCP servers."""
    server, _short = split_local_tool(tool_name, plugin_root)
    return server is not None


def main(argv) -> int:
    if len(argv) >= 2 and argv[1] == "servers":
        for s in sorted(LOCAL_SERVERS):
            print(s)
        return 0
    if len(argv) >= 2 and argv[1] == "prefixes":
        for s in sorted(LOCAL_SERVERS):
            print(local_tool_prefix(s))
        return 0
    if len(argv) >= 3 and argv[1] == "match":
        return 0 if is_local_tool(argv[2]) else 1
    print("Usage: plugin_mcp_servers.py {servers|prefixes|match <tool_name>}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
