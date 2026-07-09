#!/usr/bin/env python3
"""browser_prefixes.py - SSOT derivation of the browser MCP permission prefixes.

Claude Code namespaces a plugin-provided server's tools as
``mcp__plugin_<plugin>_<server>__<tool>`` and matches an allow rule
``mcp__<server>`` at the ``mcp__<server>__`` BOUNDARY (not as a raw string
prefix). So ``mcp__plugin_odoo-ai-agents_chrome-devtools`` does NOT cover the
distinct ``chrome-devtools-headed`` server - every family, headed variants
included, needs its own prefix.

PERMISSIONS ARE DECOUPLED FROM THE EAGER SET. Only ONE browser family
(``chrome-devtools``) is eager (bundled in ``<plugin_root>/.mcp.json``); the
other five are OPT-IN, wired on demand by odoo-setup (they are NOT in
.mcp.json). If the allow-prefixes were derived from .mcp.json alone, the five
opt-in families would be permission-blocked the moment a user wires one. So the
prefixes are derived from the STATIC full six-family server list
(``STATIC_SERVERS``) UNION whatever the live .mcp.json declares - never from
.mcp.json keys alone. Allowing a prefix for a family that is not (yet) running
is harmless; missing one for a family the user just opted into is a bug. This is
the single source of truth both hooks (auto-approve, ensure-permissions) and the
30-permissions setup step read.

stdlib-only (no jq, no 3rd-party). Two CLI modes used by callers:

    python3 browser_prefixes.py prefixes
        Print, one per line, for each family S: ``mcp__plugin_<name>_<S>`` then
        the bare ``mcp__<S>``.

    python3 browser_prefixes.py match <tool_name>
        Exit 0 if <tool_name> starts with ``mcp__plugin_<name>_<S>__`` for some
        family S, else exit 1.
"""
import json
import re
import sys
from pathlib import Path

# scripts/lib/browser_prefixes.py -> plugin_root is two dirs up (lib -> scripts -> root).
PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent

# The STATIC full six-family server list (three backends x headless+headed). This
# is the permission SSOT: every family gets an allow-prefix regardless of whether
# it is currently in .mcp.json, so an opt-in family wired later by odoo-setup is
# never permission-blocked. Kept in sync with scripts/lib/browser-mcp-servers.sh
# (the shell SSOT for the same six families' npx args).
FALLBACK_PLUGIN_NAME = "odoo-ai-agents"
STATIC_SERVERS = [
    "chrome-devtools", "chrome-devtools-headed",
    "playwright", "playwright-headed",
    "pagecast", "pagecast-headed",
]
# Back-compat alias: this list was historically the read-failure fallback; it is
# now the always-applied static base of the union.
FALLBACK_SERVERS = STATIC_SERVERS

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


def _all_servers(plugin_root: Path) -> list:
    """The static full six-family SSOT UNION the live .mcp.json keys.

    Static families come first (stable order); any live-only extra (a family
    added to .mcp.json but not yet in STATIC_SERVERS) is appended so it is still
    covered. Decoupling from the eager set is the whole point: the five opt-in
    families keep their allow-prefix even though only chrome-devtools is in
    .mcp.json today.
    """
    servers = list(STATIC_SERVERS)
    seen = set(servers)
    try:
        data = json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8"))
        for s in (data.get("mcpServers") or {}).keys():
            if s not in seen:
                seen.add(s)
                servers.append(s)
    except Exception:
        pass
    return servers


def browser_prefixes(plugin_root: Path = PLUGIN_ROOT) -> list:
    """Return the derived allow-list prefixes (importable for callers/tests)."""
    name = _normalize(_read_plugin_name(plugin_root))
    servers = [_normalize(s) for s in _all_servers(plugin_root)]
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
    servers = [_normalize(s) for s in _all_servers(plugin_root)]
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
