"""The upgrade path for a stand-alone `odoo-semantic` registration made by an earlier connect
command: `migrate_connection.py` moves its URL and value into the plugin's configured options
through the Claude Code CLI (a stub `claude` here) and removes the registration that shadows the
plugin's server. The value itself must never appear on stdout, stderr or an argument.
"""
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "odoo-semantic-mcp" / "scripts" / "migrate_connection.py"
PID = "odoo-semantic-mcp@test-mkt"

STUB = r'''#!/usr/bin/env python3
import json, os, sys
state = os.environ["STUB_STATE"]
open(os.path.join(state, "calls.log"), "a").write(json.dumps(sys.argv[1:]) + "\n")
cfg_path = os.path.join(state, "configured.json")
configured = json.load(open(cfg_path)) if os.path.exists(cfg_path) else []
if sys.argv[1:3] == ["plugin", "configure"] and "--json" in sys.argv:
    print(json.dumps({"pluginId": sys.argv[3], "configured": configured}))
elif sys.argv[1:3] == ["plugin", "configure"] and "--values-stdin" in sys.argv:
    if os.environ.get("STUB_FAIL"):
        sys.stderr.write("stub: refused\n"); sys.exit(1)
    values = json.loads(sys.stdin.read())
    json.dump(values, open(os.path.join(state, "values.json"), "w"))
    json.dump(sorted(set(configured) | set(values)), open(cfg_path, "w"))
elif sys.argv[1:3] == ["mcp", "remove"]:
    path = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], ".claude.json")
    data = json.load(open(path))
    data.get("mcpServers", {}).pop(sys.argv[3], None)
    json.dump(data, open(path, "w"))
else:
    sys.stderr.write("stub: unexpected %r\n" % (sys.argv[1:],)); sys.exit(2)
'''

ENTRY = {"type": "http", "url": "https://osm.example.test/mcp", "headers": {"X-API-Key": "osm_value_77"},
         "timeout": 90000}


def _world(tmp_path, entry=ENTRY, other=True):
    state = tmp_path / "state"
    state.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "claude"
    stub.write_text(STUB, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    servers = {"playwright": {"type": "stdio", "command": "npx"}} if other else {}
    if entry is not None:
        servers["odoo-semantic"] = entry
    (cfg / ".claude.json").write_text(json.dumps({"mcpServers": servers, "projects": {}}), encoding="utf-8")
    return {"state": state, "bin": bindir, "cfg": cfg}


def _run(world, *args, env=None):
    base = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
    base.update({"PATH": "%s:%s" % (world["bin"], base.get("PATH", "")), "STUB_STATE": str(world["state"]),
                 "CLAUDE_CONFIG_DIR": str(world["cfg"])})
    base.update(env or {})
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=base)


def _calls(world):
    log = world["state"] / "calls.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def _servers(world):
    return json.loads((world["cfg"] / ".claude.json").read_text())["mcpServers"]


def test_plan_finds_the_user_scope_registration_without_printing_its_value(tmp_path):
    world = _world(tmp_path)
    proc = _run(world, "--plugin-id", PID, "plan")
    assert proc.returncode == 0, proc.stderr
    assert "FOUND=user URL=https://osm.example.test/mcp VALUE=present STATE=unset" in proc.stdout
    assert "osm_value_77" not in proc.stdout + proc.stderr


def test_apply_moves_url_and_value_then_removes_the_registration_after_a_backup(tmp_path):
    world = _world(tmp_path)
    proc = _run(world, "--plugin-id", PID, "apply")
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "MOVED=api_key" in out and "MOVED=mcp_url" in out and "REMOVED=user" in out and "NEXT=/reload-plugins" in out
    assert "osm_value_77" not in out + proc.stderr
    assert all("osm_value_77" not in arg for call in _calls(world) for arg in call)
    assert json.loads((world["state"] / "values.json").read_text()) == {
        "mcp_url": "https://osm.example.test/mcp", "api_key": "osm_value_77"}
    assert "odoo-semantic" not in _servers(world) and "playwright" in _servers(world)
    backups = list(world["cfg"].glob(".claude.json.bak.*"))
    assert len(backups) == 1 and "odoo-semantic" in json.loads(backups[0].read_text())["mcpServers"]
    assert ["mcp", "remove", "odoo-semantic", "--scope", "user"] in _calls(world)


def test_a_refused_configure_keeps_the_registration(tmp_path):
    world = _world(tmp_path)
    proc = _run(world, "--plugin-id", PID, "apply", env={"STUB_FAIL": "1"})
    assert proc.returncode == 1
    assert "FAILED=api_key" in proc.stdout
    assert "odoo-semantic" in _servers(world)
    assert not list(world["cfg"].glob(".claude.json.bak.*"))


def test_an_already_configured_plugin_only_loses_the_shadowing_registration(tmp_path):
    world = _world(tmp_path)
    (world["state"] / "configured.json").write_text(json.dumps(["api_key", "mcp_url"]))
    proc = _run(world, "--plugin-id", PID, "apply")
    assert proc.returncode == 0, proc.stderr
    assert "SKIPPED=api_key" in proc.stdout and "REMOVED=user" in proc.stdout
    assert not (world["state"] / "values.json").exists()
    assert "odoo-semantic" not in _servers(world)


def test_nothing_happens_without_a_stand_alone_registration(tmp_path):
    world = _world(tmp_path, entry=None)
    proc = _run(world, "--plugin-id", PID, "apply")
    assert proc.returncode == 0 and "FOUND=none" in proc.stdout
    assert _calls(world) == []


def test_without_a_plugin_id_nothing_is_changed(tmp_path):
    world = _world(tmp_path)
    proc = _run(world, "apply")
    assert proc.returncode == 1 and "plugin-id" in proc.stderr
    assert "odoo-semantic" in _servers(world) and _calls(world) == []


def test_the_connect_command_hands_the_migration_to_the_operator_instead_of_removing_by_itself():
    connect = (ROOT / "plugins" / "odoo-semantic-mcp" / "commands" / "connect.md").read_text(encoding="utf-8")
    assert "scripts/migrate_connection.py\" apply" in connect
    assert "never by you" in connect
    assert "claude mcp remove odoo-semantic --scope <that scope>" not in connect
