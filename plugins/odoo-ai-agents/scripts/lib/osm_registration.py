#!/usr/bin/env python3
"""osm_registration.py - where the Odoo Semantic MCP server is registered, if anywhere.

    osm_registration.py [--cwd DIR]
        prints OSM_URL=<base url, no trailing /mcp> and OSM_SOURCE=hand-registered|plugin,
        exit 0; exit 1 with nothing on stdout when no server is registered.

A hand-registered `odoo-semantic` server (the Claude Code user configuration file, top level or
the project of the working directory) comes first because Claude Code lets it shadow the
plugin's server. Otherwise the `odoo-semantic-mcp` plugin counts when it is enabled and holds an
`mcp_url` in `pluginConfigs` of the highest-precedence settings file that sets one. The API key
is never read. A file that is not valid JSON counts as absent. Stdlib only, Python 3.6 syntax:
the setup gate runs it on whatever python3 the host has.
"""
import json
import os
import sys

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from claude_settings import config_dir_path, settings_files  # noqa: E402

SERVER = "odoo-semantic"
PLUGIN = "odoo-semantic-mcp"


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _base(url):
    url = str(url or "").strip().rstrip("/")
    return url[:-4] if url.endswith("/mcp") else url


def _hand_registered_path():
    override = os.environ.get("CLAUDE_CONFIG")
    if override:
        return override
    base = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    return os.path.join(base, ".claude.json") if base else os.path.expanduser("~/.claude.json")


def _hand_registered(cwd):
    data = _read(_hand_registered_path())
    entry = (data.get("mcpServers") or {}).get(SERVER)
    if not isinstance(entry, dict):
        project = (data.get("projects") or {}).get(cwd) or {}
        entry = (project.get("mcpServers") or {}).get(SERVER)
    if isinstance(entry, dict):
        return _base(entry.get("url") or entry.get("serverUrl"))
    return ""


def _plugin(cwd):
    files = [_read(path) for _scope, path in settings_files(config_dir_path(), cwd)]
    enabled = set()
    for data in reversed(files):  # lowest precedence first; a higher file overrides
        flags = data.get("enabledPlugins")
        for pid, on in (flags.items() if isinstance(flags, dict) else ()):
            if pid.split("@")[0] == PLUGIN:
                (enabled.add if on is True else enabled.discard)(pid)
    for data in files:
        configs = data.get("pluginConfigs")
        for pid in sorted(configs if isinstance(configs, dict) else ()):
            if pid in enabled:
                opts = configs[pid].get("options") if isinstance(configs[pid], dict) else None
                url = _base((opts or {}).get("mcp_url") if isinstance(opts, dict) else "")
                if url:
                    return url
    return ""


def server(cwd=None):
    """(base_url, source), or ("", "") when no server is registered."""
    cwd = cwd or os.getcwd()
    url = _hand_registered(cwd)
    if url:
        return url, "hand-registered"
    url = _plugin(cwd)
    if url:
        return url, "plugin"
    return "", ""


def main(argv):
    cwd = None
    if len(argv) == 2 and argv[0] == "--cwd":
        cwd = argv[1]
    url, source = server(cwd)
    if not url:
        return 1
    print("OSM_URL=" + url)
    print("OSM_SOURCE=" + source)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
