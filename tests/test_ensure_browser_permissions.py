"""Behavioral tests for the SessionStart browser-permission self-apply hook.

`hooks/ensure-browser-permissions.sh` is the ONE machine-level bit that cannot
ship in the repo: it idempotently adds the browser MCP tool permission prefixes
to the user's settings.json so the visual-UI agents run without a per-tool
approval prompt. Contract under test (the behavior, not the implementation):

  - adds the plugin-namespaced own prefixes to permissions.allow[];
  - idempotent: a second run changes nothing;
  - honours the ODOO_AI_NO_AUTO_PERMS=1 opt-out (no write at all);
  - runs non-interactively (stdin closed) and always exits 0 (never blocks the
    session).

Drives a throwaway settings.json via CLAUDE_SETTINGS so the real
~/.claude/settings.json is never touched. Stdlib-only (needs bash + python3,
which the step script the hook delegates to also needs).
"""
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
HOOK = PLUGIN / "hooks" / "ensure-browser-permissions.sh"

_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def _normalize(name):
    return _SAFE.sub("_", name)


def _plugin_name():
    data = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return _normalize(data["name"])


def _servers():
    data = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
    return [_normalize(s) for s in data["mcpServers"]]


# Anti-drift: the own-prefixes set is DERIVED from .mcp.json (the SSOT for which
# browser servers ship), not hard-coded - so adding/renaming a server (e.g. a new
# `-headed` variant) is automatically covered, and a regression that stops adding
# one is caught here. With the current .mcp.json this is the 6 plugin-namespaced
# prefixes (chrome-devtools[-headed], playwright[-headed], pagecast[-headed]).
NAME = _plugin_name()
SERVERS = _servers()
OWN_PREFIXES = {f"mcp__plugin_{NAME}_{s}" for s in SERVERS}


def _run(settings_path, env_extra=None):
    env = dict(os.environ)
    env["CLAUDE_SETTINGS"] = str(settings_path)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(HOOK)],
        env=env,
        stdin=subprocess.DEVNULL,  # non-interactive: no TTY
        capture_output=True,
        text=True,
        timeout=60,
    )


def _allow(settings_path):
    data = json.loads(Path(settings_path).read_text(encoding="utf-8"))
    return set((data.get("permissions") or {}).get("allow") or [])


@pytest.fixture()
def settings(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{}", encoding="utf-8")
    return p


def test_hook_file_present():
    assert HOOK.is_file(), f"missing hook: {HOOK}"


def test_adds_own_prefixes(settings):
    r = _run(settings)
    assert r.returncode == 0, f"hook must exit 0; stderr={r.stderr}"
    missing = OWN_PREFIXES - _allow(settings)
    assert not missing, f"hook did not add own-prefixes {missing}; allow={_allow(settings)}"


def test_every_mcp_server_gets_a_prefix(settings):
    # Anti-drift, per-server: for EVERY browser MCP server declared in .mcp.json
    # - the `-headed` variants included (a different server name, NOT covered by
    # the base server's boundary-matched prefix) - the corresponding
    # `mcp__plugin_<name>_<server>` prefix must land in permissions.allow[].
    r = _run(settings)
    assert r.returncode == 0, f"hook must exit 0; stderr={r.stderr}"
    allow = _allow(settings)
    for server in SERVERS:
        prefix = f"mcp__plugin_{NAME}_{server}"
        assert prefix in allow, (
            f"server '{server}' from .mcp.json has no allow prefix '{prefix}'; allow={allow}"
        )


def test_idempotent(settings):
    _run(settings)
    first = _allow(settings)
    r = _run(settings)
    assert r.returncode == 0, f"second run must exit 0; stderr={r.stderr}"
    assert _allow(settings) == first, "second run changed the allow-list (not idempotent)"


def test_opt_out_writes_nothing(settings):
    before = settings.read_text(encoding="utf-8")
    r = _run(settings, {"ODOO_AI_NO_AUTO_PERMS": "1"})
    assert r.returncode == 0, f"opt-out must still exit 0; stderr={r.stderr}"
    assert settings.read_text(encoding="utf-8") == before, "opt-out must not modify settings"
    assert not (OWN_PREFIXES & _allow(settings)), "opt-out must add no prefixes"
