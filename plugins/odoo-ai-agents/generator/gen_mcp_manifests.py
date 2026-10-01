#!/usr/bin/env python3
"""
gen_mcp_manifests.py - SSOT generator for Codex CLI and Gemini CLI MCP manifests.

Reads:
  - plugins/odoo-ai-agents/.mcp.json          (WHICH servers the plugin bundles)
  - scripts/lib/browser_mcp_servers.py        (HOW each browser family launches: pin + flags)
  - plugins/odoo-ai-agents/.claude-plugin/plugin.json  (name/version/description)

Emits:
  - plugins/odoo-ai-agents/gemini-extension.json
  - plugins/odoo-ai-agents/.codex-plugin/mcp.json

Claude starts the bundled browser family through scripts/mcp/browser_mcp_launch.py with
``${CLAUDE_PLUGIN_ROOT}``, which only Claude Code expands. So the derived entries are built from
the launch SSOT, never copied from .mcp.json:
  - Gemini expands ``${extensionPath}`` and ``${/}`` in gemini-extension.json, so its entry runs
    the same launcher (state-root flags resolved at every start).
  - Codex expands neither, so its entry is the plain ``npx -y <pin> <base flags>``; the setup
    step 10-browser-mcp.sh writes the state-root flags into the user's own Codex config.

LOCAL servers (scripts/lib/plugin_mcp_servers.py LOCAL_SERVERS, e.g. ``odoo-local``) are
Claude-only and EXCLUDED from both derived manifests; Codex/Gemini use the Bash CLI for that
surface.

Usage:
  python3 generator/gen_mcp_manifests.py          # write mode (idempotent)
  python3 generator/gen_mcp_manifests.py check    # check mode: diff in-memory vs on-disk; exit 1 on drift

Run from the repo root (or the plugin root - paths are resolved relative to this file).
"""

import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.resolve()
SSOT_MCP = PLUGIN_ROOT / ".mcp.json"
CLAUDE_PLUGIN = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"

GEMINI_OUT = PLUGIN_ROOT / "gemini-extension.json"
CODEX_MCP_OUT = PLUGIN_ROOT / ".codex-plugin" / "mcp.json"

# Sibling-lib import (scripts/lib/plugin_mcp_servers.py is the SSOT for which
# bundled MCP servers are LOCAL/Claude-only - see module docstring above).
_LIB_DIR = str(PLUGIN_ROOT / "scripts" / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import plugin_mcp_servers  # noqa: E402  (sibling lib; resolves via the path insert above)
import browser_mcp_servers  # noqa: E402  (sibling lib; the browser launch SSOT)

# Gemini expands these in gemini-extension.json (extension directory, path separator).
GEMINI_LAUNCHER_ARG = "${extensionPath}${/}scripts${/}mcp${/}browser_mcp_launch.py"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _dump(data: dict) -> str:
    """Serialize to JSON with 2-space indent and a trailing newline (stable git diff)."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _codex_entry(server: str) -> dict:
    """Plain npx launch with the default pin (no env override: generation is deterministic)."""
    return {"command": "npx", "args": ["-y"] + browser_mcp_servers.npx_args(server, {})}


def _gemini_entry(server: str) -> dict:
    """The bundled launcher, which adds the state-root flags at every start."""
    return {"command": "python3", "args": [GEMINI_LAUNCHER_ARG, server]}


def build_gemini_extension(servers: list, plugin_meta: dict) -> dict:
    """
    Build gemini-extension.json content.

    Note: no 'trust' field (forbidden in Gemini extension manifests).
    Note: no 'type' field per server (Gemini infers transport from command).
    """
    return {
        "name": plugin_meta["name"],
        "version": plugin_meta["version"],
        "description": plugin_meta["description"],
        "mcpServers": {name: _gemini_entry(name) for name in servers},
    }


def build_codex_mcp(servers: list) -> dict:
    """
    Build .codex-plugin/mcp.json content: flat (no 'mcpServers' wrapper, no 'type').
    """
    return {name: _codex_entry(name) for name in servers}


def bundled_browser_servers() -> list:
    """The browser families .mcp.json bundles (LOCAL servers excluded), in file order."""
    ssot = _load_json(SSOT_MCP)
    names = [n for n in ssot.get("mcpServers", ssot) if n not in plugin_mcp_servers.LOCAL_SERVERS]
    unknown = [n for n in names if n not in browser_mcp_servers.ALL_SERVERS]
    if unknown:
        raise SystemExit(
            f"gen_mcp_manifests.py: .mcp.json bundles {unknown}, which is neither a LOCAL server "
            "(plugin_mcp_servers.LOCAL_SERVERS) nor a browser family "
            "(browser_mcp_servers.ALL_SERVERS) - add it to one of them."
        )
    return names


def generate() -> dict[str, str]:
    """Return a mapping of output_path -> serialized content (write mode helper)."""
    servers = bundled_browser_servers()
    plugin_meta = _load_json(CLAUDE_PLUGIN)

    return {
        str(GEMINI_OUT): _dump(build_gemini_extension(servers, plugin_meta)),
        str(CODEX_MCP_OUT): _dump(build_codex_mcp(servers)),
    }


def write_mode() -> int:
    """Generate and write output files. Returns 0 on success."""
    outputs = generate()
    changed: list[str] = []
    for path_str, content in outputs.items():
        p = Path(path_str)
        p.parent.mkdir(parents=True, exist_ok=True)
        existing = p.read_text(encoding="utf-8") if p.exists() else None
        if existing != content:
            p.write_text(content, encoding="utf-8")
            changed.append(path_str)

    if changed:
        print(f"gen_mcp_manifests.py: wrote {len(changed)} file(s):")
        for f in changed:
            p = Path(f)
            try:
                rel = p.relative_to(PLUGIN_ROOT.parent.parent)
            except ValueError:
                rel = p
            print(f"  {rel}")
    else:
        print("gen_mcp_manifests.py: all files already up-to-date (idempotent).")
    return 0


def check_mode() -> int:
    """
    Regenerate in-memory, diff against on-disk. Exit 1 with a clear message on drift.
    Mirrors the intent of gen_surface.py's check mode (used in CI).
    """
    outputs = generate()
    drifted: list[str] = []
    for path_str, expected in outputs.items():
        p = Path(path_str)
        if not p.exists():
            drifted.append(f"  MISSING: {path_str}")
            continue
        actual = p.read_text(encoding="utf-8")
        if actual != expected:
            drifted.append(f"  DRIFT:   {path_str}")

    if drifted:
        print(
            "ERROR: gen_mcp_manifests.py check failed - the following generated files are "
            "out of sync with plugins/odoo-ai-agents/.mcp.json + scripts/lib/browser_mcp_servers.py.\n"
            "Run: python3 plugins/odoo-ai-agents/generator/gen_mcp_manifests.py",
            file=sys.stderr,
        )
        for line in drifted:
            print(line, file=sys.stderr)
        return 1

    print("gen_mcp_manifests.py check: all generated manifests are in sync with SSOT.")
    return 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "write"
    if mode == "check":
        return check_mode()
    return write_mode()


if __name__ == "__main__":
    sys.exit(main())
