"""The upgrade path for the values an earlier plugin version read from environment variables.

`upgrade_values.py` moves them into the plugin's configured options through the Claude Code CLI
(a stub `claude` here records what it was asked) and rewrites `speech.toml` / `youtube.toml` in
the current form. The value itself must never appear on stdout, stderr or an argument.
"""
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
SCRIPT = LIB / "upgrade_values.py"
PID = "odoo-ai-agents@test-mkt"

STUB = r'''#!/usr/bin/env python3
import json, os, sys
state = os.environ["STUB_STATE"]
log = open(os.path.join(state, "calls.log"), "a")
log.write(json.dumps(sys.argv[1:]) + "\n")
cfg_path = os.path.join(state, "configured.json")
configured = json.load(open(cfg_path)) if os.path.exists(cfg_path) else []
if sys.argv[1:3] == ["plugin", "configure"] and "--json" in sys.argv:
    print(json.dumps({"pluginId": sys.argv[3], "configured": configured, "unconfigured": []}))
elif sys.argv[1:3] == ["plugin", "configure"] and "--values-stdin" in sys.argv:
    if os.environ.get("STUB_FAIL"):
        sys.stderr.write("stub: refused\n"); sys.exit(1)
    values = json.loads(sys.stdin.read())
    json.dump(values, open(os.path.join(state, "values.json"), "w"))
    json.dump(sorted(set(configured) | set(values)), open(cfg_path, "w"))
    print("Saved. Restart Claude Code to apply it.")
else:
    sys.stderr.write("stub: unexpected %r\n" % (sys.argv[1:],)); sys.exit(2)
'''

SPEECH_OLD = '''[tts]
provider = "openai"
base_url = "http://127.0.0.1:8880/v1"
model = "tts-1"
api_key_env = "MY_SPEECH_VALUE"

[tts.voices]
vi_VN = "alloy"

[stt]
provider = "openai"
base_url = "http://127.0.0.1:8880/v1"
model = "whisper-1"
api_key_env = "MY_SPEECH_VALUE"
'''

YOUTUBE_OLD = '''[youtube]
channel = "Docs channel"
client_id_env = "MY_YT_ID"
client_secret_env = "MY_YT_SECRET"
privacy = "unlisted"
'''


def _world(tmp_path, speech=SPEECH_OLD, youtube=YOUTUBE_OLD):
    state = tmp_path / "state"
    state.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "claude"
    stub.write_text(STUB, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    home = tmp_path / "odoo-ai"
    home.mkdir()
    if speech is not None:
        (home / "speech.toml").write_text(speech, encoding="utf-8")
    if youtube is not None:
        (home / "youtube.toml").write_text(youtube, encoding="utf-8")
    return {"state": state, "bin": bindir, "home": home}


def _run(world, *args, env=None):
    base = {k: v for k, v in os.environ.items() if not k.startswith(("MY_", "CLAUDE_PLUGIN"))}
    base.update({"PATH": "%s:%s" % (world["bin"], base.get("PATH", "")), "STUB_STATE": str(world["state"]),
                 "ODOO_AI_HOME": str(world["home"]), "HOME": str(world["home"].parent)})
    base.update(env or {})
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=base)


def _calls(world):
    log = world["state"] / "calls.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_plan_names_every_option_an_earlier_file_points_at_and_whether_its_value_is_here(tmp_path):
    world = _world(tmp_path)
    proc = _run(world, "--plugin-id", PID, "plan", env={"MY_SPEECH_VALUE": "sk-value-1", "MY_YT_ID": "id.apps"})
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "OPTION=speech_api_key SOURCE=MY_SPEECH_VALUE VALUE=present STATE=unset" in out
    assert "OPTION=youtube_client_id SOURCE=MY_YT_ID VALUE=present STATE=unset" in out
    assert "OPTION=youtube_client_secret SOURCE=MY_YT_SECRET VALUE=absent" in out
    # the earlier default name applies when the key was never written
    assert "OPTION=youtube_refresh_token_docs SOURCE=YOUTUBE_REFRESH_TOKEN VALUE=absent" in out
    assert "sk-value-1" not in out + proc.stderr and "id.apps" not in out + proc.stderr


def test_apply_moves_present_values_through_stdin_rewrites_the_files_and_names_the_missing_ones(tmp_path):
    world = _world(tmp_path)
    proc = _run(world, "--plugin-id", PID, "apply",
                env={"MY_SPEECH_VALUE": "sk-value-1", "MY_YT_ID": "id.apps", "MY_YT_SECRET": "sec-2"})
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "MOVED=speech_api_key" in out and "MOVED=youtube_client_id" in out and "MOVED=youtube_client_secret" in out
    assert "MISSING=youtube_refresh_token_docs" in out
    assert "NEXT=/reload-plugins" in out
    for secret in ("sk-value-1", "id.apps", "sec-2"):
        assert secret not in out + proc.stderr
        assert all(secret not in arg for call in _calls(world) for arg in call)
    sent = json.loads((world["state"] / "values.json").read_text())
    assert sent == {"speech_api_key": "sk-value-1", "youtube_client_id": "id.apps", "youtube_client_secret": "sec-2"}
    assert [c[:3] for c in _calls(world)].count(["plugin", "configure", PID]) == 2  # one --json read, one write
    speech = (world["home"] / "speech.toml").read_text()
    assert "api_key_env" not in speech and 'auth = "bearer"' in speech
    youtube = (world["home"] / "youtube.toml").read_text()
    assert "[channels.docs]" in youtube and "_env" not in youtube and 'slot = "docs"' in youtube
    assert list(world["home"].glob("speech.toml.bak.*")) and list(world["home"].glob("youtube.toml.bak.*"))


def test_apply_never_overwrites_an_option_the_operator_already_configured(tmp_path):
    world = _world(tmp_path, youtube=None)
    (world["state"] / "configured.json").write_text(json.dumps(["speech_api_key"]))
    proc = _run(world, "--plugin-id", PID, "apply", env={"MY_SPEECH_VALUE": "sk-value-1"})
    assert proc.returncode == 0, proc.stderr
    assert "SKIPPED=speech_api_key" in proc.stdout and "MOVED=" not in proc.stdout
    assert not (world["state"] / "values.json").exists()
    assert "api_key_env" not in (world["home"] / "speech.toml").read_text()   # the file still moves on


def test_a_refused_configure_leaves_the_files_as_they_were(tmp_path):
    world = _world(tmp_path, youtube=None)
    proc = _run(world, "--plugin-id", PID, "apply", env={"MY_SPEECH_VALUE": "sk-value-1", "STUB_FAIL": "1"})
    assert proc.returncode == 1
    assert "FAILED=speech_api_key" in proc.stdout
    assert (world["home"] / "speech.toml").read_text() == SPEECH_OLD
    assert "sk-value-1" not in proc.stdout + proc.stderr


def test_without_a_plugin_id_apply_only_reports(tmp_path):
    world = _world(tmp_path, youtube=None)
    proc = _run(world, "apply", env={"MY_SPEECH_VALUE": "sk-value-1"})
    assert proc.returncode == 1
    assert "MISSING=speech_api_key" in proc.stdout and "plugin-id" in proc.stderr
    assert _calls(world) == []


def test_the_plugin_id_comes_from_the_marketplace_cache_path():
    sys.path.insert(0, str(LIB))
    import upgrade_values
    assert upgrade_values.plugin_id(root="/x/.claude/plugins/cache/viindoo-plugins/odoo-ai-agents/8.2.0") \
        == "odoo-ai-agents@viindoo-plugins"
    assert upgrade_values.plugin_id(root="/srv/checkouts/odoo-mcp-client/plugins/odoo-ai-agents") == ""
    assert upgrade_values.plugin_id(explicit="odoo-ai-agents@other", root="/x") == "odoo-ai-agents@other"


def test_nothing_to_do_when_the_files_are_already_in_the_current_form(tmp_path):
    world = _world(tmp_path, speech=SPEECH_OLD.replace('api_key_env = "MY_SPEECH_VALUE"', 'auth = "bearer"'),
                   youtube='[channels.docs]\nslot = "docs"\nchannel = "Docs"\n')
    proc = _run(world, "--plugin-id", PID, "apply")
    assert proc.returncode == 0 and "NOTHING=" in proc.stdout
    assert _calls(world) == []


def test_the_setup_command_hands_the_upgrade_command_to_the_operator_when_check_says_so():
    setup = (ROOT / "plugins" / "odoo-ai-agents" / "commands" / "odoo-setup.md").read_text(encoding="utf-8")
    assert setup.count("`UPGRADE=`") >= 2          # the speech note and the youtube note
    assert "never yours" in setup                   # the agent never materializes the value itself
    for lib in ("speech_config.py", "youtube_config.py"):
        assert "upgrade_values.py" in (LIB / lib).read_text(encoding="utf-8"), lib
