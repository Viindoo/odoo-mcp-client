"""Setup steps 10 (Codex/Gemini) and 12 (Claude user scope) register each browser family with the
launch spec resolved on THIS machine (exact pin + state-root flags), report a registration that
differs as drift, and REPLACE it - never merge, because a merged args list keeps the stale flag
next to its replacement (Gemini's JSON merge used to union the args).

Everything runs against temp configs, a temp $ODOO_AI_HOME and a stub `claude` CLI.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
STEP10 = PLUGIN / "scripts" / "setup-steps" / "10-browser-mcp.sh"
STEP12 = PLUGIN / "scripts" / "setup-steps" / "12-browser-mcp-optin.sh"
SSOT_PY = PLUGIN / "scripts" / "lib" / "browser_mcp_servers.py"
CONFIG_MERGE = PLUGIN / "scripts" / "lib" / "config_merge.py"

ALL = ["chrome-devtools", "chrome-devtools-headed", "playwright", "playwright-headed",
       "pagecast", "pagecast-headed"]
OPTIN = ALL[1:]


@pytest.fixture
def world(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    cfg = tmp_path / "claude-config"
    cfg.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "claude-calls.jsonl"
    stub = bin_dir / "claude"
    stub.write_text(f"#!{sys.executable}\nimport json, sys\n"
                    f"open({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n",
                    encoding="utf-8")
    stub.chmod(0o755)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("BROWSER_MCP_") and k not in ("ODOO_AI_PROJECT_DIR",
                                                              "ODOO_AI_WORKTREE_DIR")}
    env.update(HOME=str(home), ODOO_AI_HOME=str(tmp_path / "state"),
               CLAUDE_CONFIG_DIR=str(cfg), CLAUDE_BIN=str(stub),
               CODEX_CONFIG=str(tmp_path / "codex" / "config.toml"),
               GEMINI_SETTINGS=str(tmp_path / "gemini" / "settings.json"))
    return {"tmp": tmp_path, "env": env, "cfg": cfg, "log": log,
            "codex": tmp_path / "codex" / "config.toml",
            "gemini": tmp_path / "gemini" / "settings.json"}


def _spec(world, server):
    out = subprocess.run([sys.executable, str(SSOT_PY), "spec", server], env=world["env"],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _step(world, step, verb):
    return subprocess.run(["bash", str(step), verb], env=world["env"], capture_output=True,
                          text=True, timeout=120)


def _claude_calls(world):
    if not world["log"].exists():
        return []
    return [json.loads(line) for line in world["log"].read_text().splitlines()]


def _write_claude_config(world, servers):
    (world["cfg"] / ".claude.json").write_text(json.dumps({"mcpServers": servers}),
                                               encoding="utf-8")


# --------------------------------------------------------------------------- #
# step 12 - Claude user scope
# --------------------------------------------------------------------------- #
def test_the_resolved_spec_carries_the_state_root(world):
    state = str(world["tmp"] / "state")
    assert f"--workspace={state}" in _spec(world, "chrome-devtools-headed")["args"]
    assert f"--output-dir={state}/projects" in _spec(world, "playwright")["args"]
    assert _spec(world, "pagecast")["env"] == {"RECORDING_OUTPUT_DIR": f"{state}/scratch/pagecast"}


def test_check_reports_missing_families(world):
    assert _step(world, STEP12, "check").returncode == 1


def test_check_passes_when_every_family_is_registered_as_specified(world):
    _write_claude_config(world, {s: dict(_spec(world, s), type="stdio") for s in OPTIN})
    res = _step(world, STEP12, "check")
    assert res.returncode == 0, res.stdout + res.stderr


def test_check_reports_a_registration_from_before_the_state_root_flags(world):
    servers = {s: dict(_spec(world, s), type="stdio") for s in OPTIN}
    servers["playwright"] = {"type": "stdio", "command": "npx",
                             "args": ["-y", "@playwright/mcp@0", "--caps=devtools", "--headless",
                                      "--isolated"], "env": {}}
    _write_claude_config(world, servers)
    assert _step(world, STEP12, "check").returncode == 1


def test_check_reports_a_moved_state_root(world):
    _write_claude_config(world, {s: dict(_spec(world, s), type="stdio") for s in OPTIN})
    world["env"]["ODOO_AI_HOME"] = str(world["tmp"] / "moved")
    assert _step(world, STEP12, "check").returncode == 1


def test_apply_removes_then_re_adds_only_the_drifted_family(world):
    servers = {s: dict(_spec(world, s), type="stdio") for s in OPTIN}
    servers["chrome-devtools-headed"] = {"type": "stdio", "command": "npx",
                                         "args": ["-y", "chrome-devtools-mcp@1", "--isolated"]}
    _write_claude_config(world, servers)
    res = _step(world, STEP12, "apply")
    assert res.returncode == 0, res.stdout + res.stderr
    want = _spec(world, "chrome-devtools-headed")
    assert _claude_calls(world) == [
        ["mcp", "remove", "--scope", "user", "chrome-devtools-headed"],
        ["mcp", "add", "--scope", "user", "chrome-devtools-headed", "--", "npx", *want["args"]],
    ]


def test_apply_adds_a_missing_family_with_its_env_and_without_a_remove(world):
    servers = {s: dict(_spec(world, s), type="stdio") for s in OPTIN if s != "pagecast"}
    _write_claude_config(world, servers)
    res = _step(world, STEP12, "apply")
    assert res.returncode == 0, res.stdout + res.stderr
    want = _spec(world, "pagecast")
    # The name precedes -e: --env takes several KEY=VALUE pairs and would swallow a later name.
    assert _claude_calls(world) == [[
        "mcp", "add", "--scope", "user", "pagecast",
        "-e", f"RECORDING_OUTPUT_DIR={want['env']['RECORDING_OUTPUT_DIR']}",
        "--", "npx", *want["args"]]]


def test_no_claude_cli_means_nothing_to_do(world):
    world["env"]["CLAUDE_BIN"] = "claude-not-installed-here"
    assert _step(world, STEP12, "check").returncode == 0
    res = _step(world, STEP12, "apply")
    assert res.returncode == 0 and _claude_calls(world) == []


# --------------------------------------------------------------------------- #
# step 10 - Codex / Gemini
# --------------------------------------------------------------------------- #
def test_without_codex_or_gemini_there_is_nothing_to_do_and_nothing_is_created(world):
    assert _step(world, STEP10, "check").returncode == 0
    assert _step(world, STEP10, "apply").returncode == 0
    assert not world["codex"].exists() and not world["gemini"].exists()


def test_codex_drift_is_replaced_not_duplicated(world):
    world["codex"].parent.mkdir(parents=True)
    world["codex"].write_text(
        '[profile]\nmodel = "x"\n\n'
        '[mcp_servers.playwright]\ncommand = "npx"\nargs = ["-y", "@playwright/mcp@0"]\n\n'
        '[mcp_servers.playwright.env]\nOLD = "1"\n\n'
        '[tail]\nkeep = true\n', encoding="utf-8")
    assert _step(world, STEP10, "check").returncode == 1
    res = _step(world, STEP10, "apply")
    assert res.returncode == 0, res.stdout + res.stderr
    text = world["codex"].read_text(encoding="utf-8")
    assert text.count("[mcp_servers.playwright]") == 1
    assert "@playwright/mcp@0\"" not in text and "OLD" not in text
    assert '[profile]\nmodel = "x"' in text and "[tail]\nkeep = true" in text
    for s in ALL:
        assert text.count(f"[mcp_servers.{s}]") == 1, s
    assert _step(world, STEP10, "check").returncode == 0


def test_codex_without_tomllib_compares_the_table_text(world):
    """3.8-3.10 hosts have no tomllib: the comparison falls back to the rendered table text."""
    world["codex"].parent.mkdir(parents=True)
    world["codex"].write_text("", encoding="utf-8")
    assert _step(world, STEP10, "apply").returncode == 0
    spec = json.dumps(_spec(world, "pagecast"))
    code = ("import sys; sys.modules['tomllib'] = None; sys.argv = ['config_merge.py', "
            "'mcp-server-matches', 'toml', %r, 'pagecast']; "
            "exec(open(%r).read())" % (str(world["codex"]), str(CONFIG_MERGE)))
    ok = subprocess.run([sys.executable, "-c", code], input=spec, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    stale = json.dumps(dict(_spec(world, "pagecast"), args=["-y", "@mcpware/pagecast@0"]))
    bad = subprocess.run([sys.executable, "-c", code], input=stale, capture_output=True, text=True)
    assert bad.returncode == 1


def test_gemini_drift_replaces_the_args_instead_of_unioning_them(world):
    world["gemini"].parent.mkdir(parents=True)
    world["gemini"].write_text(json.dumps({"theme": "dark", "mcpServers": {"pagecast": {
        "command": "npx", "args": ["-y", "@mcpware/pagecast@0", "--headless"], "trust": True}}}),
        encoding="utf-8")
    assert _step(world, STEP10, "check").returncode == 1
    res = _step(world, STEP10, "apply")
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads(world["gemini"].read_text(encoding="utf-8"))
    want = _spec(world, "pagecast")
    assert data["mcpServers"]["pagecast"] == dict(want, trust=True)
    assert data["theme"] == "dark"
    assert set(data["mcpServers"]) == set(ALL)
    assert _step(world, STEP10, "check").returncode == 0


# --------------------------------------------------------------------------- #
# the SessionStart hint
# --------------------------------------------------------------------------- #
def test_the_session_start_probe_names_drift_and_the_remedy(world):
    _write_claude_config(world, {"playwright": {"command": "npx",
                                                "args": ["-y", "@playwright/mcp@0"]}})
    hook = PLUGIN / "hooks" / "check-setup-deps.sh"
    res = subprocess.run(["bash", str(hook)], input="{}", env=world["env"], capture_output=True,
                         text=True, timeout=60)
    assert res.returncode == 0
    assert "browser MCP flags outdated" in res.stderr
    assert "claude playwright" in res.stderr
    assert "/odoo-ai-agents:odoo-setup browser, then restart the session" in res.stderr


def test_the_session_start_probe_is_silent_about_flags_when_registrations_match(world):
    _write_claude_config(world, {s: _spec(world, s) for s in OPTIN})
    hook = PLUGIN / "hooks" / "check-setup-deps.sh"
    res = subprocess.run(["bash", str(hook)], input="{}", env=world["env"], capture_output=True,
                         text=True, timeout=60)
    assert "browser MCP flags outdated" not in res.stderr
