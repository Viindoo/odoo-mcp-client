"""Behavioral tests for the PermissionRequest auto-approve hook for LOCAL MCP tools.

`hooks/auto-approve-local.sh` closes the same in-session permission gap
`auto-approve-browser.sh` closes for browser tools, but for the odoo-local server
(scripts/mcp/odoo_local_server.py's lease/instance/catalog tools) - a DIFFERENT
category (scripts/lib/plugin_mcp_servers.py LOCAL_SERVERS): some of its tools are
destructive (a lease release, an applied lease_gc can stop a process group and
drop a database), so it is never approved as a "browser" tool, and it is not a
blanket-allow surface either.

Contract under test (behavior, not implementation):
  - any odoo-local tool other than lease_gc -> allow;
  - lease_gc with no dry_run / dry_run:true (the documented default) -> allow
    (read-only listing);
  - lease_gc with dry_run:false (an APPLY reclaim) -> pass-through (fall through
    to the normal human-approval prompt) - this is the one case that must NOT be
    auto-approved;
  - a non-local tool (browser, foreign MCP server, Bash) -> pass-through;
  - ODOO_AI_NO_AUTO_PERMS=1 -> pass-through even for an otherwise-allowed tool.

Stdlib + subprocess only.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
HOOK = PLUGIN / "hooks" / "auto-approve-local.sh"

_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def _normalize(name):
    return _SAFE.sub("_", name)


def _plugin_name():
    data = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return _normalize(data["name"])


NAME = _plugin_name()
LOCAL_SERVER = "odoo-local"
PREFIX = f"mcp__plugin_{NAME}_{_normalize(LOCAL_SERVER)}"


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


def _allowed(payload):
    r = _run(payload)
    assert r.returncode == 0, f"hook must exit 0; stderr={r.stderr}"
    out = json.loads(r.stdout)
    behavior = out["hookSpecificOutput"]["decision"]["behavior"]
    assert behavior == "allow", f"expected allow; got {out}"
    return r


def _silent(payload, env_extra=None):
    r = _run(payload, env_extra)
    assert r.returncode == 0, f"hook must exit 0; stderr={r.stderr}"
    assert r.stdout.strip() == "", f"expected pass-through (no decision); stdout={r.stdout!r}"
    return r


def test_hook_file_present_and_executable():
    assert HOOK.is_file(), f"missing hook: {HOOK}"
    import os
    assert os.access(HOOK, os.X_OK), "hook script must be executable"


@pytest.mark.parametrize("tool_short", [
    "lease_acquire", "lease_release", "lease_park", "lease_list", "lease_find",
    "db_preflight", "instance_build", "job_wait", "instance_serve", "instance_status",
    "catalog_read", "catalog_locate", "series_detect", "project_dir",
])
def test_every_non_gc_local_tool_is_allowed(tool_short):
    """Every odoo-local tool except lease_gc is auto-allowed unconditionally - including the
    give-back verbs (lease_release/lease_park): PERMISSION for the call and OWNERSHIP of the
    lease are different questions, and this hook only answers the first."""
    _allowed({"tool_name": f"{PREFIX}__{tool_short}", "tool_input": {}})


def test_lease_gc_with_no_tool_input_is_allowed():
    """No tool_input at all -> no dry_run key -> not the dry_run:false exception -> allow."""
    _allowed({"tool_name": f"{PREFIX}__lease_gc"})


def test_lease_gc_with_empty_tool_input_is_allowed():
    _allowed({"tool_name": f"{PREFIX}__lease_gc", "tool_input": {}})


def test_lease_gc_with_dry_run_true_is_allowed():
    _allowed({"tool_name": f"{PREFIX}__lease_gc", "tool_input": {"dry_run": True}})


def test_lease_gc_with_dry_run_false_falls_through_to_human_prompt():
    """The one exception: an APPLY-mode gc (dry_run:false) can actually stop process groups and
    drop databases. It must NOT be auto-approved - it falls through to the normal prompt."""
    _silent({"tool_name": f"{PREFIX}__lease_gc", "tool_input": {"dry_run": False}})


def test_lease_gc_with_dry_run_as_string_false_is_still_allowed():
    """Only the JSON boolean `false` triggers the exception - a truthy/non-bool value (a model
    mistake, or a future caller that passes a string) must not silently widen the exception into
    blocking calls it was never meant to block. Fails CLOSED only on the exact documented shape."""
    _allowed({"tool_name": f"{PREFIX}__lease_gc", "tool_input": {"dry_run": "false"}})


def test_non_local_browser_tool_passes_through():
    _silent({"tool_name": "mcp__plugin_odoo-ai-agents_chrome-devtools__navigate_page"})


def test_foreign_mcp_tool_passes_through():
    _silent({"tool_name": "mcp__odoo-semantic__model_inspect"})


def test_bash_tool_passes_through():
    _silent({"tool_name": "Bash", "tool_input": {"command": "ls"}})


def test_opt_out_passes_through_even_for_an_otherwise_allowed_tool():
    _silent(
        {"tool_name": f"{PREFIX}__lease_acquire", "tool_input": {}},
        {"ODOO_AI_NO_AUTO_PERMS": "1"},
    )


def test_opt_out_still_silent_for_the_gc_exception():
    _silent(
        {"tool_name": f"{PREFIX}__lease_gc", "tool_input": {"dry_run": False}},
        {"ODOO_AI_NO_AUTO_PERMS": "1"},
    )


@pytest.mark.parametrize("raw", ["", "not json at all", "null", '{"tool_input":{}}'])
def test_unparseable_or_toolless_payloads_stay_silent(raw):
    r = subprocess.run(
        ["bash", str(HOOK)], input=raw, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, f"hook must exit 0; stderr={r.stderr}"
    assert r.stdout.strip() == "", f"expected silence; stdout={r.stdout!r}"


# --- Wiring: hooks.json registers this hook on PermissionRequest, matcher-scoped to odoo-local --

def _permission_request_local_entry():
    hooks_json = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    entries = hooks_json["hooks"]["PermissionRequest"]
    for entry in entries:
        commands = [h.get("command", "") for h in entry.get("hooks", [])]
        if any("auto-approve-local.sh" in c for c in commands):
            return entry
    raise AssertionError("no PermissionRequest entry dispatches auto-approve-local.sh")


def test_hooks_json_registers_auto_approve_local():
    entry = _permission_request_local_entry()
    assert entry, "auto-approve-local.sh must be registered on PermissionRequest"


def test_hooks_json_local_matcher_accepts_odoo_local_tools():
    entry = _permission_request_local_entry()
    pattern = entry["matcher"]
    assert re.match(pattern, f"{PREFIX}__lease_acquire")
    assert re.match(pattern, f"{PREFIX}__lease_gc")


def test_hooks_json_local_matcher_rejects_browser_and_foreign_tools():
    entry = _permission_request_local_entry()
    pattern = entry["matcher"]
    assert re.match(pattern, "mcp__plugin_odoo-ai-agents_chrome-devtools__navigate_page") is None
    assert re.match(pattern, "mcp__odoo-semantic__model_inspect") is None
    assert re.match(pattern, "Bash") is None


def test_manifest_description_documents_the_new_hook():
    """hooks.json's description is the map a debugging agent reads first; a hook missing from it
    is a hook nobody knows fired (mirrors test_permission_denied_teardown.py's own check)."""
    manifest = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    desc = " ".join(manifest.get("description", "").split())
    assert HOOK.name in desc, "the manifest description must name auto-approve-local.sh"
