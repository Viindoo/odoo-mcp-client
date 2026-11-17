"""Behaviour tests: the public-address tool set of scripts/lib/plugin_mcp_servers.py.

The set is exactly `instance_expose` and `instance_unexpose` of the `odoo-local` server, printed by
the `expose` subcommand as full tool-call names; it never overlaps the lease give-back set, and
the coverage test that judges a settings file's allow list is the same for both.
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


def test_the_public_address_set_is_exactly_the_two_expose_tools():
    r = _cli("expose")
    assert r.returncode == 0
    assert r.stdout.split() == [
        f"mcp__plugin_{NAME}_odoo-local__instance_expose",
        f"mcp__plugin_{NAME}_odoo-local__instance_unexpose",
    ]


def test_every_public_address_tool_is_a_local_tool_and_none_is_a_give_back_tool():
    give_back = _cli("give-back").stdout.split()
    for tool in _cli("expose").stdout.split():
        assert _cli("match", tool).returncode == 0
        assert tool not in give_back


def test_a_public_address_tool_is_covered_by_its_exact_name_or_the_odoo_local_server_rule(tmp_path):
    tool = f"mcp__plugin_{NAME}_odoo-local__instance_expose"
    server = f"mcp__plugin_{NAME}_odoo-local"
    for allow in ([tool], [server], [server + "__*"]):
        assert _cli("give-back-covered", str(_settings(tmp_path, allow)), tool).returncode == 0, allow


def test_a_public_address_tool_is_not_covered_by_the_give_back_rules_or_another_server(tmp_path):
    tool = f"mcp__plugin_{NAME}_odoo-local__instance_expose"
    for allow in ([], [f"mcp__plugin_{NAME}_odoo-local__lease_release"],
                  [f"mcp__plugin_{NAME}_odoo-local__instance_unexpose"],
                  [f"mcp__plugin_{NAME}_odoo-media"], ["mcp__plugin_other_odoo-local__instance_expose"]):
        assert _cli("give-back-covered", str(_settings(tmp_path, allow)), tool).returncode == 1, allow
