"""Structural validation for the bundled (EAGER) browser MCP server.

The odoo-ai-agents plugin ships a `.mcp.json` that Claude Code auto-loads on install. It declares
EXACTLY ONE eager browser server, the headless `chrome-devtools`; the other five families are
opt-in (test_setup_wiring.py). The eager server starts through
`scripts/mcp/browser_mcp_launch.py`, which adds the state-root flags a static manifest cannot
spell; the launcher's own behaviour is in test_browser_mcp_launcher.py.

Contract this file protects:
  - `.mcp.json` ships exactly ONE eager BROWSER server (LOCAL servers - e.g. `odoo-local`,
    scripts/lib/plugin_mcp_servers.py LOCAL_SERVERS - are a separate category);
  - it is `chrome-devtools`, a stdio server started by the bundled launcher with python3;
  - what the launcher resolves for it is headless, `--isolated`, and an EXACT package version.
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS_PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
BROWSER_MCP = SKILLS_PLUGIN / ".mcp.json"
SKILLS_MANIFEST = SKILLS_PLUGIN / ".claude-plugin" / "plugin.json"
LAUNCHER = SKILLS_PLUGIN / "scripts" / "mcp" / "browser_mcp_launch.py"

EAGER_SERVER = "chrome-devtools"
EXACT_PIN = re.compile(r"@\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def _local_servers() -> frozenset:
    spec = importlib.util.spec_from_file_location(
        "plugin_mcp_servers", SKILLS_PLUGIN / "scripts" / "lib" / "plugin_mcp_servers.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.LOCAL_SERVERS


@pytest.fixture(scope="module")
def mcp():
    assert BROWSER_MCP.is_file(), f"missing browser MCP config: {BROWSER_MCP}"
    with BROWSER_MCP.open(encoding="utf-8") as fh:
        return json.load(fh)  # raises if invalid JSON


def test_exactly_one_eager_server(mcp):
    servers = mcp.get("mcpServers", {})
    browser_servers = set(servers) - _local_servers()
    assert browser_servers == {EAGER_SERVER}, (
        f"expected exactly one eager BROWSER server {{{EAGER_SERVER!r}}}, got {browser_servers} "
        f"(all .mcp.json keys: {set(servers)}). The other five browser families are opt-in and "
        "must NOT be in .mcp.json."
    )


def test_local_servers_are_not_counted_as_browser_servers(mcp):
    local = _local_servers()
    servers = set(mcp.get("mcpServers", {}))
    assert local & servers, (
        f"premise failed: no local server from {sorted(local)} found in .mcp.json "
        f"(got {sorted(servers)}) - this test would otherwise pass vacuously"
    )
    assert EAGER_SERVER not in local, "the eager browser server must never be a LOCAL server"


def test_eager_server_starts_through_the_bundled_launcher(mcp):
    """A static manifest cannot spell the state root (default ~/.odoo-ai unless $ODOO_AI_HOME is
    set), so the eager server must start through the launcher that resolves it."""
    spec = mcp["mcpServers"][EAGER_SERVER]
    assert spec.get("type") == "stdio"
    assert spec.get("command") == "python3"
    assert spec.get("args") == [
        "${CLAUDE_PLUGIN_ROOT}/scripts/mcp/browser_mcp_launch.py", EAGER_SERVER
    ]
    assert LAUNCHER.is_file()


def _resolved_argv(tmp_path) -> list:
    """Run the launcher with a stub npx that records its argv - what the client really starts."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    record = tmp_path / "argv.json"
    stub = stub_dir / "npx"
    stub.write_text(
        f"#!{sys.executable}\nimport json, sys\n"
        f"open({str(record)!r}, 'w').write(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    env = dict(os.environ, PATH=f"{stub_dir}{os.pathsep}{os.environ.get('PATH', '')}",
               ODOO_AI_HOME=str(tmp_path / "state"))
    for var in ("BROWSER_MCP_CHROME_PIN", "ODOO_AI_PROJECT_DIR", "ODOO_AI_WORKTREE_DIR"):
        env.pop(var, None)
    proc = subprocess.run([sys.executable, str(LAUNCHER), EAGER_SERVER], env=env,
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(record.read_text(encoding="utf-8"))


def test_eager_server_runs_headless_and_isolated(tmp_path):
    argv = _resolved_argv(tmp_path)
    assert "--headless" in argv, argv
    assert "--isolated" in argv, argv


def test_eager_server_package_is_an_exact_version(tmp_path):
    """`npx -y pkg@1` reuses whatever 1.x a machine's npm cache holds, so file-write rules
    differed between machines. The launched package must be an exact version."""
    argv = _resolved_argv(tmp_path)
    assert argv[0] == "-y", argv
    pkg = argv[1]
    assert pkg.startswith("chrome-devtools-mcp@"), argv
    assert EXACT_PIN.search(pkg), f"package must pin an exact version, got {pkg!r}"


def test_manifest_points_at_browser_mcp():
    with SKILLS_MANIFEST.open(encoding="utf-8") as fh:
        manifest = json.load(fh)
    assert manifest.get("mcpServers") == "./.mcp.json", (
        "skills manifest must reference ./.mcp.json so the eager browser server loads"
    )
