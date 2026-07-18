"""Behavioral tests for the PermissionRequest auto-approve hook.

`hooks/auto-approve-browser.sh` closes the in-session permission gap: Claude Code
finalizes permissions BEFORE SessionStart hooks run, so settings.json written by
the SessionStart self-apply only takes effect next session. This hook receives a
PermissionRequest payload on stdin and, for a tool namespaced to one of THIS
plugin's browser MCP servers, emits an `allow` decision; for anything else it
stays silent (pass-through to the normal prompt). Contract under test (behavior,
not implementation):

  - a plugin browser tool (incl. a `-headed` variant) -> stdout is JSON with
    hookSpecificOutput.decision.behavior == "allow", exit 0;
  - a non-plugin tool (e.g. Bash) -> no allow on stdout (pass-through), exit 0;
  - ODOO_AI_NO_AUTO_PERMS=1 even for a browser tool -> pass-through, exit 0.

The sample browser tool name is a `-headed` OPT-IN family (`chrome-devtools-headed`)
that is NOT in .mcp.json - the exact case #156 must not regress: an opt-in family
wired later must still be auto-approved because the hook's permission SSOT
(browser_prefixes.py) covers all six families statically, decoupled from the
eager .mcp.json set. Stdlib + subprocess only.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
HOOK = PLUGIN / "hooks" / "auto-approve-browser.sh"

_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def _normalize(name):
    return _SAFE.sub("_", name)


def _plugin_name():
    data = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return _normalize(data["name"])


NAME = _plugin_name()
# An OPT-IN `-headed` family, deliberately NOT in .mcp.json (only chrome-devtools
# is eager). The hook must still allow it - proving permissions are decoupled
# from the eager set.
OPTIN_HEADED_SERVER = "chrome-devtools-headed"
HEADED_TOOL = f"mcp__plugin_{NAME}_{_normalize(OPTIN_HEADED_SERVER)}__navigate_page"


def _run(payload, env_extra=None):
    env = None
    if env_extra:
        import os
        env = dict(os.environ)
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_hook_file_present_and_executable():
    assert HOOK.is_file(), f"missing hook: {HOOK}"


def test_browser_headed_tool_is_allowed():
    r = _run({"tool_name": HEADED_TOOL, "hook_event_name": "PermissionRequest"})
    assert r.returncode == 0, f"hook must exit 0; stderr={r.stderr}"
    out = json.loads(r.stdout)  # must be valid JSON
    behavior = out["hookSpecificOutput"]["decision"]["behavior"]
    assert behavior == "allow", f"expected allow for {HEADED_TOOL}; got {out}"


def test_non_plugin_tool_passes_through():
    r = _run({"tool_name": "Bash", "hook_event_name": "PermissionRequest"})
    assert r.returncode == 0, f"hook must exit 0; stderr={r.stderr}"
    assert r.stdout.strip() == "", f"non-plugin tool must produce no decision; stdout={r.stdout!r}"


def test_bare_form_optin_tool_is_allowed():
    """V-19: a bare (non-plugin-namespaced) opt-in tool must also be allowed.

    The 5 opt-in browser families are registered STAND-ALONE by odoo-setup, so their real
    tool names carry no `plugin_<name>_` prefix at all (e.g. `mcp__playwright__browser_click`).
    Before the fix these showed a manual permission prompt on first use in the session they
    were just wired, defeating the hook's stated purpose for them.
    """
    bare_tool = "mcp__playwright__browser_click"
    r = _run({"tool_name": bare_tool, "hook_event_name": "PermissionRequest"})
    assert r.returncode == 0, f"hook must exit 0; stderr={r.stderr}"
    out = json.loads(r.stdout)
    behavior = out["hookSpecificOutput"]["decision"]["behavior"]
    assert behavior == "allow", f"expected allow for {bare_tool}; got {out}"


def test_opt_out_passes_through_even_for_browser_tool():
    r = _run(
        {"tool_name": HEADED_TOOL, "hook_event_name": "PermissionRequest"},
        {"ODOO_AI_NO_AUTO_PERMS": "1"},
    )
    assert r.returncode == 0, f"opt-out must still exit 0; stderr={r.stderr}"
    assert r.stdout.strip() == "", f"opt-out must produce no decision; stdout={r.stdout!r}"
