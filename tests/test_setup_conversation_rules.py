"""What the setup command asks a newcomer, and how - the rules a live run on 8.2.0 showed missing:
no fill-in template in the chat, the voice endpoint states its own models and voices, no playlist
id or default language asked at setup, reload wording that matches Claude Code, the install dialog
told to leave the plugin options empty, and the operator's own commands runnable with `!`.
Each test reads the prose a runtime agent reads (names and rules, never a sentence an LLM wrote).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SETUP = (PLUGIN / "commands" / "odoo-setup.md").read_text(encoding="utf-8")


def _note(step):
    start = SETUP.index("- **%s**" % step)
    end = SETUP.find("\n- **", start + 1)
    return " ".join(SETUP[start:end if end > 0 else None].split())


def test_the_command_bans_a_fill_in_template_and_limits_free_text_to_a_url_and_a_label():
    rules = " ".join(SETUP.split())
    assert "Never a fill-in template" in rules
    assert "the only free-text answers are a URL and a label" in rules


def test_the_voice_step_asks_where_the_voice_comes_from_and_derives_models_and_voices_from_the_endpoint():
    note = _note("70-speech")
    assert "ONE closed question" in note and "probe-endpoint" in note
    assert "never types a model id, a voice id or an auth mode" in note
    assert "speech_voices" in note and "speech_probe" in note
    for banned in ("the TTS `base_url`, `model`", "the STT `base_url`, `model` and `auth`"):
        assert banned not in note, banned


def test_the_youtube_step_never_asks_for_a_playlist_id_or_a_default_language():
    note = _note("75-youtube")
    assert "never asked at setup" in note and "playlist" in note
    assert "an optional playlist id and default language" not in note
    propose = subprocess.run([sys.executable, str(PLUGIN / "scripts" / "lib" / "youtube_config.py"), "propose"],
                             capture_output=True, text=True, env={**os.environ, "ODOO_AI_HOME": str(ROOT / "nowhere")})
    facts = [line for line in propose.stdout.splitlines() if line.startswith("FACTS_TO_CONFIRM=")][0]
    assert "playlist_id" not in facts and "default_language" not in facts and "privacy" not in facts
    assert any(line.startswith("OPTIONAL=") and "playlist_id" in line for line in propose.stdout.splitlines())


def test_the_operator_commands_may_be_typed_in_the_chat_with_a_leading_bang():
    assert "leading `!`" in _note("75-youtube") and "leading `!`" in _note("70-speech")
    connect = (ROOT / "plugins" / "odoo-semantic-mcp" / "commands" / "connect.md").read_text(encoding="utf-8")
    assert "leading `!`" in connect
    propose = subprocess.run([sys.executable, str(PLUGIN / "scripts" / "lib" / "youtube_config.py"), "propose"],
                             capture_output=True, text=True, env={**os.environ, "ODOO_AI_HOME": str(ROOT / "nowhere")})
    prepare = [line for line in propose.stdout.splitlines() if line.startswith("PREPARE_4=")][0]
    assert "'!'" in prepare and "consent" in prepare


def test_reload_wording_distinguishes_plugin_servers_from_hand_registrations():
    rules = " ".join(SETUP.split())
    assert "MCP servers do NOT hot-reload" not in rules and "MCP servers do not hot-reload" not in rules
    assert "`/reload-plugins` reloads the plugin's own servers" in rules
    for rel in ("plugins/odoo-ai-agents/README.md", "plugins/odoo-ai-agents/docs/setup.md",
                "plugins/odoo-semantic-mcp/README.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "(MCP does not hot-reload)" not in text and "not hot-reloaded" not in text, rel
        assert "/reload-plugins" in text, rel


def test_every_plugin_option_tells_the_install_dialog_to_leave_it_empty_and_names_what_fills_it():
    options = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["userConfig"]
    assert len(options) == 6
    for name, spec in options.items():
        assert spec.get("required") is False, name
        assert spec["description"].startswith("Leave empty when Claude Code asks at install"), name
        assert ("consent" in spec["description"]) or ("Configure" in spec["description"]), name


def test_the_setup_command_reviews_the_whole_registry_before_the_plan_and_the_venv_check_prints_the_findings():
    rules = " ".join(SETUP.split())
    assert "registry_review.py" in rules and "Review the whole registry" in rules
    assert "Never work around a finding in silence" in rules
    step45 = (PLUGIN / "scripts" / "setup-steps" / "45-venv.sh").read_text(encoding="utf-8")
    assert "registry_review.py" in step45
