"""hooks/block-capture-outside-state-root.sh (+ scripts/lib/capture_paths.py): a browser capture
must land under the state root.

The failure this exists for: a capture tool given a RELATIVE destination writes it under the
session's working directory - the user's repository - and the servers accept that, because the
client's roots include the cwd. The launch flags only make an absolute path under the state root
succeed. So the gate refuses a relative or out-of-root destination, but only where the answering
server provably runs with its state-root flag; elsewhere (a user who has not re-run setup) it
allows with an advisory, never strands them.

Each case runs the real hook script with a temporary $ODOO_AI_HOME and a temporary Claude config.
"""
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
HOOK = PLUGIN / "hooks" / "block-capture-outside-state-root.sh"
HOOKS_JSON = PLUGIN / "hooks" / "hooks.json"
CAPTURE_PY = PLUGIN / "scripts" / "lib" / "capture_paths.py"

BUNDLED = "mcp__plugin_odoo-ai-agents_chrome-devtools__"
FAMILIES = ["chrome-devtools", "chrome-devtools-headed", "playwright", "playwright-headed",
            "pagecast", "pagecast-headed"]


def _load_capture():
    spec = importlib.util.spec_from_file_location("capture_paths_under_test", CAPTURE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def world(tmp_path):
    state = tmp_path / "state"
    isolate = state / "projects" / "0123456789ab" / "worktrees" / "ba9876543210"
    isolate.mkdir(parents=True)
    cfg = tmp_path / "claude-config"
    cfg.mkdir()
    return {"tmp": tmp_path, "state": state, "isolate": isolate, "cfg": cfg}


def _register(world, family, args, env=None):
    """Write a user-scope registration for an opt-in family into the temporary Claude config."""
    path = world["cfg"] / ".claude.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data.setdefault("mcpServers", {})[family] = {
        "type": "stdio", "command": "npx", "args": args, "env": env or {}}
    path.write_text(json.dumps(data), encoding="utf-8")


def _run(world, tool, tool_input, *, cwd="/repo", **env_over):
    env = {k: v for k, v in os.environ.items()
           if k not in ("ODOO_AI_PROJECT_DIR", "ODOO_AI_WORKTREE_DIR")}
    env.update(ODOO_AI_HOME=str(world["state"]), CLAUDE_CONFIG_DIR=str(world["cfg"]))
    env.update(env_over)
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool,
                          "tool_input": tool_input, "cwd": cwd})
    proc = subprocess.run(["bash", str(HOOK)], input=payload, env=env,
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def _denied(out):
    return bool(out) and out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def _advised(out):
    return bool(out) and "odoo-setup browser" in out.get("systemMessage", "") \
        and out["hookSpecificOutput"].get("permissionDecision") is None


# --------------------------------------------------------------------------- #
# deny: the bundled chrome-devtools always runs with the flag
# --------------------------------------------------------------------------- #
def test_a_relative_screenshot_path_is_denied_with_the_remedy(world):
    out = _run(world, BUNDLED + "take_screenshot", {"pageId": 1, "filePath": "shot.png"})
    assert _denied(out), out
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "filePath='shot.png' is a relative path" in reason
    assert str(world["state"]) in reason and "never retry with a relative path" in reason
    assert "mv" in reason


def test_a_relative_path_is_denied_even_when_the_hook_runs_inside_the_state_root(world):
    """The server resolves a relative path against the SESSION cwd, not the hook's; a relative
    destination is refused on its own, never judged by where the hook process happens to run."""
    env = dict(os.environ, ODOO_AI_HOME=str(world["state"]), CLAUDE_CONFIG_DIR=str(world["cfg"]))
    payload = json.dumps({"tool_name": BUNDLED + "take_screenshot",
                          "tool_input": {"filePath": "visual/a.png"}, "cwd": str(world["isolate"])})
    proc = subprocess.run(["bash", str(HOOK)], input=payload, env=env, cwd=str(world["isolate"]),
                          capture_output=True, text=True, timeout=30)
    out = json.loads(proc.stdout)
    assert _denied(out), out


def test_an_absolute_path_outside_the_state_root_is_denied(world):
    out = _run(world, BUNDLED + "take_screenshot", {"filePath": str(world["tmp"] / "repo" / "a.png")})
    assert _denied(out), out
    assert "is outside " + str(world["state"]) in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_traversal_out_of_the_state_root_is_denied(world):
    sneaky = str(world["isolate"]) + "/../../../../../escaped.png"
    out = _run(world, BUNDLED + "take_screenshot", {"filePath": sneaky})
    assert _denied(out), out


@pytest.mark.parametrize("key", ["filePath", "outputDirPath", "requestFilePath", "responseFilePath"])
def test_every_write_key_is_checked(world, key):
    out = _run(world, BUNDLED + "lighthouse_audit", {key: "out"})
    assert _denied(out), (key, out)


# --------------------------------------------------------------------------- #
# allow
# --------------------------------------------------------------------------- #
def test_an_isolate_path_is_allowed_silently(world):
    out = _run(world, BUNDLED + "take_screenshot",
               {"filePath": str(world["isolate"] / "visual" / "run-1" / "a.png")})
    assert out is None, out


def test_a_share_path_is_allowed_silently(world):
    out = _run(world, BUNDLED + "take_snapshot",
               {"filePath": str(world["state"] / "projects" / "0123456789ab" / "doc" / "s.txt")})
    assert out is None, out


def test_an_override_worktree_dir_outside_the_root_is_allowed(world):
    override = world["tmp"] / "custom-isolate"
    out = _run(world, BUNDLED + "take_screenshot", {"filePath": str(override / "v" / "a.png")},
               ODOO_AI_WORKTREE_DIR=str(override))
    assert out is None, out


def test_a_call_with_no_destination_is_allowed(world):
    assert _run(world, BUNDLED + "take_screenshot", {"pageId": 1}) is None
    assert _run(world, BUNDLED + "navigate_page", {"url": "about:blank"}) is None


@pytest.mark.parametrize("tool,inp", [
    (BUNDLED + "upload_file", {"uid": "1_2", "filePath": "fixtures/invoice.pdf"}),
    (BUNDLED + "get_heapsnapshot_summary", {"filePath": "snap.heapsnapshot"}),
    ("mcp__playwright__browser_file_upload", {"paths": ["a.pdf"], "filename": "a.pdf"}),
    ("mcp__playwright__browser_run_code_unsafe", {"filename": "script.js"}),
    ("mcp__playwright__browser_set_storage_state", {"filename": "state.json"}),
])
def test_tools_that_only_read_a_path_are_allowed(world, tool, inp):
    assert _run(world, tool, inp) is None


def test_another_plugins_browser_namespace_is_never_touched(world):
    out = _run(world, "mcp__plugin_chrome-devtools-mcp_chrome-devtools__take_screenshot",
               {"filePath": "x.png"})
    assert out is None


@pytest.mark.parametrize("tool", ["mcp__plugin_odoo-ai-agents_odoo-local__lease_list", "Bash", "Write"])
def test_non_browser_tools_are_never_touched(world, tool):
    assert _run(world, tool, {"filePath": "x.png", "file_path": "x.png"}) is None


# --------------------------------------------------------------------------- #
# opt-in families: deny only when their registration carries the flag
# --------------------------------------------------------------------------- #
def test_playwright_registered_with_the_output_dir_denies_a_relative_filename(world):
    _register(world, "playwright", ["-y", "@playwright/mcp@0.0.83", "--headless",
                                    f"--output-dir={world['state'] / 'projects'}"])
    out = _run(world, "mcp__playwright__browser_take_screenshot", {"filename": "page.png"})
    assert _denied(out), out
    ok = _run(world, "mcp__playwright__browser_take_screenshot",
              {"filename": str(world["isolate"] / "visual" / "p.png")})
    assert ok is None, ok


def test_playwright_refuses_a_path_under_the_root_but_outside_its_output_dir(world):
    _register(world, "playwright", ["-y", "@playwright/mcp@0.0.83",
                                    f"--output-dir={world['state'] / 'projects'}"])
    out = _run(world, "mcp__playwright__browser_take_screenshot",
               {"filename": str(world["state"] / "scratch" / "p.png")})
    assert _denied(out), out


def test_pagecast_registered_with_its_output_dir_denies_a_relative_webm_path(world):
    _register(world, "pagecast", ["-y", "@mcpware/pagecast@0.2.1", "--headless"],
              env={"RECORDING_OUTPUT_DIR": str(world["state"] / "scratch" / "pagecast")})
    out = _run(world, "mcp__pagecast__convert_to_gif", {"webmPath": "recordings/recording-1.webm"})
    assert _denied(out), out


def test_an_opt_in_family_without_the_flag_is_allowed_with_a_setup_advisory(world):
    """Drift safety: a user who has not re-run setup since the flags existed keeps working."""
    _register(world, "chrome-devtools-headed", ["-y", "chrome-devtools-mcp@1", "--isolated"])
    out = _run(world, "mcp__chrome-devtools-headed__take_screenshot", {"filePath": "a.png"})
    assert _advised(out), out
    assert "relative" in out["systemMessage"]
    assert out["hookSpecificOutput"]["additionalContext"] == out["systemMessage"]


def test_an_unregistered_opt_in_family_is_allowed_with_a_setup_advisory(world):
    out = _run(world, "mcp__playwright-headed__browser_take_screenshot",
               {"filename": str(world["isolate"] / "a.png")})
    assert _advised(out), out


def test_a_registration_for_another_state_root_is_drift(world):
    _register(world, "chrome-devtools-headed",
              ["-y", "chrome-devtools-mcp@1.10.1", "--workspace=/somewhere/else"])
    out = _run(world, "mcp__chrome-devtools-headed__take_screenshot", {"filePath": "a.png"})
    assert _advised(out), out


def test_a_local_scope_registration_for_this_project_counts(world):
    path = world["cfg"] / ".claude.json"
    path.write_text(json.dumps({"projects": {"/repo": {"mcpServers": {"chrome-devtools-headed": {
        "command": "npx",
        "args": ["-y", "chrome-devtools-mcp@1.10.1", f"--workspace={world['state']}"]}}}}}))
    out = _run(world, "mcp__chrome-devtools-headed__take_screenshot", {"filePath": "a.png"})
    assert _denied(out), out


# --------------------------------------------------------------------------- #
# path comparison
# --------------------------------------------------------------------------- #
def test_a_symlinked_state_root_compares_by_realpath(world):
    """macOS: /tmp is /private/tmp. A root named through a symlink and a capture path named
    through the real directory (or the reverse) are the same place."""
    real = world["tmp"] / "private" / "state"
    real.mkdir(parents=True)
    link = world["tmp"] / "linked-state"
    link.symlink_to(real)
    out = _run(world, BUNDLED + "take_screenshot", {"filePath": str(real / "projects" / "a.png")},
               ODOO_AI_HOME=str(link))
    assert out is None, out
    out = _run(world, BUNDLED + "take_screenshot", {"filePath": str(link / "projects" / "a.png")},
               ODOO_AI_HOME=str(real))
    assert out is None, out


def test_a_git_bash_drive_path_is_read_as_a_windows_path(monkeypatch):
    cap = _load_capture()
    monkeypatch.setattr(cap.os, "name", "nt")
    assert cap.native_path("/c/Users/user/.odoo-ai/x.png") == "C:\\Users\\user\\.odoo-ai\\x.png"
    assert cap.native_path("/d") == "D:\\"
    monkeypatch.setattr(cap.os, "name", "posix")
    assert cap.native_path("/c/Users/user/x.png") == "/c/Users/user/x.png"


# --------------------------------------------------------------------------- #
# fail open
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("payload", ["", "not json", "[]", '{"tool_name": 5}',
                                     json.dumps({"tool_name": BUNDLED + "take_screenshot",
                                                 "tool_input": "filePath=x.png"})])
def test_an_unreadable_payload_fails_open(world, payload):
    env = dict(os.environ, ODOO_AI_HOME=str(world["state"]), CLAUDE_CONFIG_DIR=str(world["cfg"]))
    proc = subprocess.run(["bash", str(HOOK)], input=payload, env=env,
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0 and proc.stdout.strip() == ""


def test_an_internal_error_fails_open(world):
    """A path the OS cannot even resolve (an embedded NUL) raises inside the check; the hook
    must allow, never deny on its own error."""
    cap = _load_capture()
    payload = {"tool_name": BUNDLED + "take_screenshot",
               "tool_input": {"filePath": str(world["tmp"]) + "/a\x00b.png"}}
    env = dict(os.environ, ODOO_AI_HOME=str(world["state"]), CLAUDE_CONFIG_DIR=str(world["cfg"]))
    with pytest.raises(ValueError):
        cap.check(payload["tool_name"], payload["tool_input"], "/repo", env)
    proc = subprocess.run(["bash", str(HOOK)], input=json.dumps(payload), env=env,
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0 and proc.stdout.strip() == ""


# --------------------------------------------------------------------------- #
# registration
# --------------------------------------------------------------------------- #
def _gate_matchers():
    groups = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    return [g["matcher"] for g in groups
            if any(HOOK.name in h.get("command", "") for h in g.get("hooks", []))]


def test_hooks_json_registers_the_gate_once_and_the_script_is_executable():
    assert len(_gate_matchers()) == 1
    assert HOOK.is_file() and os.access(HOOK, os.X_OK)


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("prefix", ["mcp__plugin_odoo-ai-agents_", "mcp__"])
def test_the_matcher_reaches_every_family_in_both_namespaces(family, prefix):
    (matcher,) = _gate_matchers()
    assert re.fullmatch(matcher, f"{prefix}{family}__take_screenshot")


@pytest.mark.parametrize("tool", [
    "mcp__plugin_odoo-ai-agents_odoo-local__lease_release", "Bash", "Write", "Edit",
    "mcp__plugin_chrome-devtools-mcp_chrome-devtools__take_screenshot",
    "mcp__chrome-devtools-extra__take_screenshot",
])
def test_the_matcher_does_not_reach_other_tools(tool):
    (matcher,) = _gate_matchers()
    assert not re.fullmatch(matcher, tool)


def test_the_matcher_mirrors_the_family_ssot():
    """JSON cannot import the family list; the alternation is a literal mirror of it."""
    spec = importlib.util.spec_from_file_location(
        "bms_for_matcher", PLUGIN / "scripts" / "lib" / "browser_mcp_servers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (matcher,) = _gate_matchers()
    reached = {f for f in mod.ALL_SERVERS if re.fullmatch(matcher, f"mcp__{f}__x")}
    assert reached == set(mod.ALL_SERVERS)
