"""Behaviour tests: the lease give-back tool set of scripts/lib/plugin_mcp_servers.py.

The set is exactly `lease_release` and `lease_park` of the `odoo-local` server, printed by the
`give-back` subcommand as full tool-call names; no other tool of any local server is in it.
`give-back-covered` says whether a settings file's allow list already grants one of them.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
LIB = PLUGIN / "scripts" / "lib" / "plugin_mcp_servers.py"
NAME = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["name"]


def _cli(*args):
    return subprocess.run([sys.executable, str(LIB), *args], capture_output=True, text=True, timeout=30)


def _settings(tmp_path, allow):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"permissions": {"allow": allow}}), encoding="utf-8")
    return p


def test_give_back_set_is_exactly_the_two_lease_give_back_tools():
    r = _cli("give-back")
    assert r.returncode == 0
    assert r.stdout.split() == [
        f"mcp__plugin_{NAME}_odoo-local__lease_release",
        f"mcp__plugin_{NAME}_odoo-local__lease_park",
    ]


def test_every_give_back_tool_is_a_local_tool_of_the_odoo_local_server():
    for tool in _cli("give-back").stdout.split():
        assert _cli("match", tool).returncode == 0
        assert tool.startswith(f"mcp__plugin_{NAME}_odoo-local__")


def test_covered_by_the_exact_name_or_the_odoo_local_server_rule(tmp_path):
    tool = f"mcp__plugin_{NAME}_odoo-local__lease_release"
    server = f"mcp__plugin_{NAME}_odoo-local"
    for allow in ([tool], [server], [server + "__*"]):
        assert _cli("give-back-covered", str(_settings(tmp_path, allow)), tool).returncode == 0, allow


def test_not_covered_by_another_tool_server_or_plugin(tmp_path):
    tool = f"mcp__plugin_{NAME}_odoo-local__lease_release"
    for allow in ([], [f"mcp__plugin_{NAME}_odoo-local__lease_park"],
                  [f"mcp__plugin_{NAME}_odoo-media"], ["mcp__plugin_other_odoo-local"],
                  ["mcp__plugin_other_odoo-local__lease_release"]):
        assert _cli("give-back-covered", str(_settings(tmp_path, allow)), tool).returncode == 1, allow
