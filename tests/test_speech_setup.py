"""Behaviour tests for `scripts/setup-steps/70-speech.sh` and `speech_config.py`.

The configuration names an OpenAI-compatible speech endpoint, a voice per narration language and
the speech-to-text check; no credential value enters the file (the bearer value is a plugin option
only the odoo-media server receives). Everything runs on a throwaway state root (ODOO_AI_HOME); no
network.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
STEP = PLUGIN / "scripts" / "setup-steps" / "70-speech.sh"

GOOD = {"tts": {"provider": "openai", "base_url": "https://api.openai.com/v1", "model": "tts-1",
                "auth": "bearer", "response_format": "wav",
                "voices": {"vi_VN": "voice-vi", "en_US": "voice-en"}},
        "stt": {"base_url": "https://api.openai.com/v1", "model": "whisper-1", "auth": "bearer"}}


@pytest.fixture()
def home(tmp_path):
    (tmp_path / "state").mkdir()
    return tmp_path / "state"


def _step(home, *args, env=None):
    base = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    base.update({"ODOO_AI_HOME": str(home)})
    base.update(env or {})
    return subprocess.run(["bash", str(STEP), *args], capture_output=True, text=True, timeout=60, env=base)


def _record(home, cfg):
    f = home / "s.json"
    f.write_text(json.dumps(cfg), encoding="utf-8")
    return _step(home, "record", "--from-json", str(f))


def test_describe_check_apply_follow_the_step_contract(home):
    assert "speech endpoint" in _step(home, "describe").stdout
    check = _step(home, "check")
    assert check.returncode == 1 and "odoo-setup voice" in check.stderr
    apply = _step(home, "apply")
    assert apply.returncode == 1 and "propose" in apply.stdout
    assert not (home / "speech.toml").exists()


def test_propose_names_provider_shapes_and_the_value_source_without_any_variable_name(home):
    proc = _step(home, "propose", env={"ODOO_AI_SPEECH_BASE_URL": "https://gateway.example.test/v1"})
    assert proc.returncode == 0, proc.stderr
    assert "PROVIDER_1=" in proc.stdout and "localai" in proc.stdout and "DECLARED='0'" in proc.stdout
    assert "GATEWAY='https://gateway.example.test/v1'" in proc.stdout
    assert "VALUE_SOURCE=" in proc.stdout and "_API_KEY" not in proc.stdout


def test_record_show_check_round_trip_and_no_value_in_the_file(home):
    assert _record(home, GOOD).returncode == 0
    text = (home / "speech.toml").read_text(encoding="utf-8")
    assert 'auth = "bearer"' in text and "sk-" not in text
    assert 'vi_VN = "voice-vi"' in text
    shown = json.loads(_step(home, "show").stdout)
    assert shown["tts"]["voices"] == {"vi_VN": "voice-vi", "en_US": "voice-en"}
    ok = _step(home, "check")
    assert ok.returncode == 0, ok.stderr
    assert "AUTH=bearer" in ok.stdout and "plugin configuration" in ok.stdout


def test_a_file_written_with_the_variable_name_scheme_is_read_as_auth(home):
    legacy = json.loads(json.dumps(GOOD))
    legacy["tts"].pop("auth"); legacy["tts"]["api_key_env"] = "SOME_NAME"
    legacy["stt"].pop("auth"); legacy["stt"]["api_key_env"] = ""
    (home / "speech.toml").write_text(
        "[tts]\nprovider = \"openai\"\nbase_url = \"https://api.openai.com/v1\"\nmodel = \"tts-1\"\n"
        "api_key_env = \"SOME_NAME\"\nresponse_format = \"wav\"\n[tts.voices]\nvi_VN = \"voice-vi\"\n"
        "[stt]\nbase_url = \"https://api.openai.com/v1\"\nmodel = \"whisper-1\"\napi_key_env = \"\"\n",
        encoding="utf-8")
    shown = json.loads(_step(home, "show").stdout)
    assert shown["tts"]["auth"] == "bearer" and shown["stt"]["auth"] == "none"
    assert "api_key_env" not in json.dumps(shown)
    assert _step(home, "check").returncode == 0


def _bad(**changes):
    cfg = json.loads(json.dumps(GOOD))
    for path, value in changes.items():
        table, key = path.split(".")
        if value is None:
            cfg[table].pop(key, None)
        else:
            cfg[table][key] = value
    return cfg


@pytest.mark.parametrize("cfg, word", [
    (_bad(**{"tts.auth": "sk-abcdefghijklmnopqrstuvwxyz0123456789"}), "auth"),
    (_bad(**{"tts.model": "sk-abcdefghijklmnopqrstuvwxyz0123456789/abc-def"}), "credential value"),
    (_bad(**{"tts.voices": {"vi_VN": "same", "en_US": "same"}}), "native to one language"),
    (_bad(**{"tts.voices": {"vietnamese": "voice-vi"}}), "locale"),
    (_bad(**{"tts.voices": {}}), "at least one"),
    (_bad(**{"tts.base_url": "api.openai.com"}), "base_url"),
    (_bad(**{"stt.model": None}), "model"),
    (_bad(**{"tts.key": "sk-123"}), "unknown key"),
])
def test_record_refuses_a_value_in_the_file_a_shared_voice_and_every_other_invalid_shape(home, cfg, word):
    proc = _record(home, cfg)
    assert proc.returncode == 1, proc.stdout
    assert word in proc.stderr
    assert not (home / "speech.toml").exists()


def test_a_keyless_self_hosted_endpoint_is_valid(home):
    cfg = json.loads(json.dumps(GOOD))
    cfg["tts"].update({"provider": "kokoro-fastapi", "base_url": "http://localhost:8880/v1", "auth": "none"})
    cfg["stt"].update({"base_url": "http://localhost:8000/v1", "auth": "none"})
    assert _record(home, cfg).returncode == 0
    check = _step(home, "check")
    assert check.returncode == 0 and "AUTH=none" in check.stdout
