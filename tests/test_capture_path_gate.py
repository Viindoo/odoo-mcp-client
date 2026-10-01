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
PATHS_PY = PLUGIN / "scripts" / "lib" / "paths.py"

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
def _project(world):
    """A non-git project directory (its .odoo-ai-root marker keys the ISOLATE dir)."""
    proj = world["tmp"] / "proj"
    proj.mkdir(exist_ok=True)
    (proj / ".odoo-ai-root").write_text("", encoding="utf-8")
    return proj


def _isolate_of(world, proj, **env_over):
    """The ISOLATE dir the plugin's own resolver gives `proj` (paths.py CLI)."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("ODOO_AI_PROJECT_DIR", "ODOO_AI_WORKTREE_DIR")}
    env.update(ODOO_AI_HOME=str(world["state"]), **env_over)
    out = subprocess.run(["python3", str(PATHS_PY), "--root", str(proj), "isolate"], env=env,
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _reason(out):
    return out["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_relative_screenshot_path_is_denied_with_a_concrete_destination(world):
    """The refusal names WHERE to write: a fresh adhoc run dir under the session's own ISOLATE
    dir (slug <intent>-<YYYYMMDD>-<4hex>), computed without creating anything."""
    proj = _project(world)
    before = sorted(world["tmp"].rglob("*"))
    out = _run(world, BUNDLED + "take_screenshot", {"pageId": 1, "filePath": "shot.png"},
               cwd=str(proj))
    assert sorted(world["tmp"].rglob("*")) == before, "naming the destination must create nothing"
    assert _denied(out), out
    reason = _reason(out)
    assert "filePath='shot.png' is a relative path" in reason
    assert "Never retry with a relative path" in reason and "mv" in reason
    assert "ISOLATE_DIR from its brief" in reason
    assert "<" not in reason and ">" not in reason, f"unresolved placeholder: {reason}"
    assert reason.isascii(), reason
    m = re.search(r"Write it under (\S+?)/? \(", reason)
    assert m, reason
    target = Path(m.group(1))
    assert re.fullmatch(r"[a-z0-9-]+-\d{8}-[0-9a-f]{4}", target.name), target.name
    assert target.parent == Path(_isolate_of(world, proj)) / "visual" / "adhoc"


def test_the_suggested_destination_passes_the_gate(world):
    proj = _project(world)
    reason = _reason(_run(world, BUNDLED + "take_screenshot", {"filePath": "a.png"},
                          cwd=str(proj)))
    target = re.search(r"Write it under (\S+?)/? \(", reason).group(1)
    assert _run(world, BUNDLED + "take_screenshot", {"filePath": target + "/a.png"},
                cwd=str(proj)) is None


def test_the_destination_follows_a_worktree_dir_override(world):
    proj = _project(world)
    override = world["tmp"] / "custom-isolate"
    reason = _reason(_run(world, BUNDLED + "take_screenshot", {"filePath": "a.png"},
                          cwd=str(proj), ODOO_AI_WORKTREE_DIR=str(override)))
    assert f"Write it under {override / 'visual' / 'adhoc'}/" in reason, reason
    assert not override.exists(), "naming the destination must not create it"


@pytest.mark.parametrize("tool,key,remedy", [
    (BUNDLED + "take_screenshot", "filePath", "omit filePath to get the image inline"),
    ("mcp__playwright__browser_take_screenshot", "filename",
     "BLOCKED(state root unresolvable - cannot place evidence)"),
    ("mcp__pagecast__convert_to_gif", "webmPath",
     "BLOCKED(state root unresolvable - cannot place evidence)"),
])
def test_without_a_resolvable_run_dir_the_remedy_is_the_familys_way_out(world, tool, key, remedy):
    """No git repo and no project marker above the session's directory: there is no ISOLATE dir
    to name, so the refusal says what to do instead - never a path with a placeholder in it."""
    _register(world, "playwright", ["-y", "@playwright/mcp@0.0.83",
                                    f"--output-dir={world['state'] / 'projects'}"])
    _register(world, "pagecast", ["-y", "@mcpware/pagecast@0.2.1"],
              env={"RECORDING_OUTPUT_DIR": str(world["state"] / "scratch" / "pagecast")})
    bare = world["tmp"] / "no-project"
    bare.mkdir()
    out = _run(world, tool, {key: "x.png"}, cwd=str(bare))
    assert _denied(out), out
    reason = _reason(out)
    assert remedy in reason and "Write it under" not in reason, reason
    assert "<" not in reason and reason.isascii(), reason


@pytest.mark.parametrize("tool,key", [
    (BUNDLED + "take_screenshot", "filePath"),
    ("mcp__playwright__browser_take_screenshot", "filename"),
    ("mcp__pagecast__convert_to_gif", "webmPath"),
])
def test_a_capture_may_never_overwrite_the_lease_registry(world, tool, key):
    """The state root also holds runtime/leases.json, the catalog and the logs: only its
    projects/ tree is a capture destination, for every family."""
    _register(world, "playwright", ["-y", "@playwright/mcp@0.0.83",
                                    f"--output-dir={world['state'] / 'projects'}"])
    _register(world, "pagecast", ["-y", "@mcpware/pagecast@0.2.1"],
              env={"RECORDING_OUTPUT_DIR": str(world["state"] / "scratch" / "pagecast")})
    for target in (world["state"] / "runtime" / "leases.json", world["state"] / "visual" / "x.png"):
        out = _run(world, tool, {key: str(target)})
        assert _denied(out), (target, out)
        assert "is outside " + str(world["state"] / "projects") in _reason(out)


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
    assert "is outside " + str(world["state"] / "projects") in _reason(out)


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


def _register_playwright(world):
    _register(world, "playwright", ["-y", "@playwright/mcp@0.0.83",
                                    f"--output-dir={world['state'] / 'projects'}"])


def test_playwright_may_not_write_an_override_dir_outside_the_capture_area(world):
    """playwright takes ONE --output-dir (the capture area): an override outside it passes no
    server check, so the gate must not let it through either - while chrome-devtools, launched
    with a --workspace per override, may write there."""
    _register_playwright(world)
    override = world["tmp"] / "custom-isolate"
    target = str(override / "visual" / "a.png")
    out = _run(world, "mcp__playwright__browser_take_screenshot", {"filename": target},
               ODOO_AI_WORKTREE_DIR=str(override))
    assert _denied(out), out
    assert _run(world, BUNDLED + "take_screenshot", {"filePath": target},
                ODOO_AI_WORKTREE_DIR=str(override)) is None


def test_playwright_is_sent_to_chrome_devtools_when_the_run_dir_is_unwritable_for_it(world):
    """The run dir sits under an override playwright cannot write: naming it would send the
    agent to a second refusal, so the remedy names another way out."""
    _register_playwright(world)
    proj = _project(world)
    override = world["tmp"] / "custom-isolate"
    out = _run(world, "mcp__playwright__browser_take_screenshot", {"filename": "a.png"},
               cwd=str(proj), ODOO_AI_WORKTREE_DIR=str(override))
    assert _denied(out), out
    reason = _reason(out)
    assert "Write it under" not in reason, reason
    assert "make this capture with chrome-devtools" in reason
    assert "BLOCKED(state root unresolvable - cannot place evidence)" in reason
    assert reason.isascii() and "<" not in reason, reason


def test_playwright_gets_a_concrete_dir_when_its_run_dir_is_in_the_capture_area(world):
    _register_playwright(world)
    proj = _project(world)
    reason = _reason(_run(world, "mcp__playwright__browser_take_screenshot",
                          {"filename": "a.png"}, cwd=str(proj)))
    target = re.search(r"Write it under (\S+?)/? \(", reason).group(1)
    assert target.startswith(str(world["state"] / "projects")), reason
    assert _run(world, "mcp__playwright__browser_take_screenshot",
                {"filename": target + "/a.png"}, cwd=str(proj)) is None


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


def test_a_bare_chrome_devtools_server_is_the_users_own_and_never_touched(world):
    """This plugin bundles chrome-devtools in its own namespace and its setup never registers a
    bare one: a bare mcp__chrome-devtools__ is the user's server - no deny, and no permanent
    'run setup' advisory setup could never clear."""
    for inp in ({"filePath": "x.png"}, {"filePath": str(world["tmp"] / "repo" / "a.png")}):
        assert _run(world, "mcp__chrome-devtools__take_screenshot", inp) is None


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


def _flagged(world):
    return {"command": "npx", "args": ["-y", "chrome-devtools-mcp@1.10.1",
                                       f"--workspace={world['state'] / 'projects'}"]}


UNFLAGGED = {"command": "npx", "args": ["-y", "chrome-devtools-mcp@1.10.1", "--isolated"]}


def _scopes(world, *, local=None, user=None, project=None, proj_dir=None):
    data = {}
    if user is not None:
        data["mcpServers"] = {"chrome-devtools-headed": user}
    if local is not None:
        data["projects"] = {str(proj_dir): {"mcpServers": {"chrome-devtools-headed": local}}}
    (world["cfg"] / ".claude.json").write_text(json.dumps(data), encoding="utf-8")
    if project is not None:
        (proj_dir / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"chrome-devtools-headed": project}}), encoding="utf-8")


def test_a_local_scope_registration_for_this_project_counts(world):
    proj = _project(world)
    _scopes(world, local=_flagged(world), proj_dir=proj)
    out = _run(world, "mcp__chrome-devtools-headed__take_screenshot", {"filePath": "a.png"},
               cwd=str(proj))
    assert _denied(out), out


@pytest.mark.parametrize("scopes,decision", [
    # local beats project and user
    ({"local": "unflagged", "user": "flagged"}, "advise"),
    ({"local": "flagged", "user": "unflagged"}, "deny"),
    ({"local": "unflagged", "project": "flagged"}, "advise"),
    # project beats user
    ({"project": "flagged", "user": "unflagged"}, "deny"),
    ({"project": "unflagged", "user": "flagged"}, "advise"),
    # user alone
    ({"user": "flagged"}, "deny"),
], ids=lambda v: "-".join(f"{k}={x}" for k, x in v.items()) if isinstance(v, dict) else v)
def test_the_answering_registration_follows_claudes_scope_precedence(world, scopes, decision):
    """Claude answers a name from local scope, else the project's .mcp.json, else user scope: the
    gate judges THAT registration, not whichever scope happens to carry the flag."""
    proj = _project(world)
    pick = {"flagged": _flagged(world), "unflagged": UNFLAGGED}
    _scopes(world, proj_dir=proj, **{k: pick[v] for k, v in scopes.items()})
    out = _run(world, "mcp__chrome-devtools-headed__take_screenshot", {"filePath": "a.png"},
               cwd=str(proj))
    assert (_denied(out) if decision == "deny" else _advised(out)), out


def test_the_bundled_server_below_the_launcher_python_floor_is_not_flagged(world, monkeypatch):
    """Below the floor the launcher starts the base launch without flags; the gate must then
    advise, not refuse every capture the server could no longer write."""
    cap = _load_capture()
    ssot, _ = cap._lib()
    monkeypatch.setattr(ssot, "LAUNCH_MIN_PYTHON", (99, 0))
    env = dict(os.environ, ODOO_AI_HOME=str(world["state"]), CLAUDE_CONFIG_DIR=str(world["cfg"]))
    decision, _msg = cap.check(BUNDLED + "take_screenshot", {"filePath": "a.png"}, "/repo", env)
    assert decision == "advise"
    monkeypatch.setattr(ssot, "LAUNCH_MIN_PYTHON", (3, 0))
    decision, _msg = cap.check(BUNDLED + "take_screenshot", {"filePath": "a.png"}, "/repo", env)
    assert decision == "deny"


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
