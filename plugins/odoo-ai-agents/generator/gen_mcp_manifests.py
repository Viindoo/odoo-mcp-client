#!/usr/bin/env python3
"""
gen_mcp_manifests.py — SSOT generator for Codex CLI and Gemini CLI MCP manifests.

Reads:
  - plugins/odoo-ai-agents/.mcp.json          (browser MCP server SSOT)
  - plugins/odoo-ai-agents/.claude-plugin/plugin.json  (name/version/description)

Emits:
  - plugins/odoo-ai-agents/gemini-extension.json
  - plugins/odoo-ai-agents/.codex-plugin/mcp.json

Usage:
  python3 generator/gen_mcp_manifests.py          # write mode (idempotent)
  python3 generator/gen_mcp_manifests.py check    # check mode: diff in-memory vs on-disk; exit 1 on drift

Run from the repo root (or the plugin root — paths are resolved relative to this file).
"""

import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.resolve()
SSOT_MCP = PLUGIN_ROOT / ".mcp.json"
CLAUDE_PLUGIN = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"

GEMINI_OUT = PLUGIN_ROOT / "gemini-extension.json"
CODEX_MCP_OUT = PLUGIN_ROOT / ".codex-plugin" / "mcp.json"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _dump(data: dict) -> str:
    """Serialize to JSON with 2-space indent and a trailing newline (stable git diff)."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _strip_type(entry: dict) -> dict:
    """Return a copy of entry without the 'type' field (Codex/Gemini infer from command)."""
    return {k: v for k, v in entry.items() if k != "type"}


def build_gemini_extension(ssot_servers: dict, plugin_meta: dict) -> dict:
    """
    Build gemini-extension.json content.

    Shape:
      {
        "name": "...",
        "version": "...",
        "description": "...",
        "mcpServers": {
          "<server>": { "command": "npx", "args": [...] }
        }
      }

    Note: no 'trust' field (forbidden in Gemini extension manifests).
    Note: no 'type' field per server (Gemini infers transport from command).
    Note: 'cwd' omitted — not needed for npx invocations.
    """
    mcp_servers = {
        name: _strip_type(entry)
        for name, entry in ssot_servers.items()
    }
    return {
        "name": plugin_meta["name"],
        "version": plugin_meta["version"],
        "description": plugin_meta["description"],
        "mcpServers": mcp_servers,
    }


def build_codex_mcp(ssot_servers: dict) -> dict:
    """
    Build .codex-plugin/mcp.json content.

    Flat shape (no 'mcpServers' wrapper, no 'type'):
      {
        "<server>": { "command": "npx", "args": [...] }
      }
    """
    return {
        name: _strip_type(entry)
        for name, entry in ssot_servers.items()
    }


def generate() -> dict[str, str]:
    """Return a mapping of output_path -> serialized content (write mode helper)."""
    ssot = _load_json(SSOT_MCP)
    ssot_servers = ssot.get("mcpServers", ssot)  # handle both wrapped and flat SSOT
    plugin_meta = _load_json(CLAUDE_PLUGIN)

    return {
        str(GEMINI_OUT): _dump(build_gemini_extension(ssot_servers, plugin_meta)),
        str(CODEX_MCP_OUT): _dump(build_codex_mcp(ssot_servers)),
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
            "ERROR: gen_mcp_manifests.py check failed — the following generated files are "
            "out of sync with plugins/odoo-ai-agents/.mcp.json.\n"
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
