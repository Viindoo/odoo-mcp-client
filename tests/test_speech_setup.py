"""Behaviour tests for `scripts/setup-steps/70-speech.sh` and `speech_config.py`.

The configuration names an OpenAI-compatible speech endpoint, a voice per narration language and
the speech-to-text check; the key never enters a file (only the NAME of its environment variable).
Everything runs on a throwaway state root (ODOO_AI_HOME); no network.
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
                "api_key_env": "OPENAI_API_KEY", "response_format": "wav",
                "voices": {"vi_VN": "voice-vi", "en_US": "voice-en"}},
        "stt": {"base_url": "https://api.openai.com/v1", "model": "whisper-1",
                "api_key_env": "OPENAI_API_KEY"}}


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


def test_propose_names_provider_shapes_and_key_variables_by_name_only(home):
    proc = _step(home, "propose", env={"OPENAI_API_KEY": "sk-not-a-real-key-1234567890"})
    assert proc.returncode == 0, proc.stderr
    assert "PROVIDER_1=" in proc.stdout and "localai" in proc.stdout and "DECLARED='0'" in proc.stdout
    assert "OPENAI_API_KEY" in proc.stdout
    assert "sk-not-a-real-key" not in proc.stdout + proc.stderr


def test_record_show_check_round_trip_and_the_key_stays_out_of_the_file(home):
    assert _record(home, GOOD).returncode == 0
    text = (home / "speech.toml").read_text(encoding="utf-8")
    assert 'api_key_env = "OPENAI_API_KEY"' in text and "sk-" not in text
    assert 'vi_VN = "voice-vi"' in text
    shown = json.loads(_step(home, "show").stdout)
    assert shown["tts"]["voices"] == {"vi_VN": "voice-vi", "en_US": "voice-en"}
    missing = _step(home, "check")
    assert missing.returncode == 1 and "OPENAI_API_KEY is not set" in missing.stderr
    ok = _step(home, "check", env={"OPENAI_API_KEY": "x"})
    assert ok.returncode == 0, ok.stderr


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
    (_bad(**{"tts.api_key_env": "sk-abcdefghijklmnopqrstuvwxyz0123456789"}), "never the key"),
    (_bad(**{"tts.voices": {"vi_VN": "same", "en_US": "same"}}), "native to one language"),
    (_bad(**{"tts.voices": {"vietnamese": "voice-vi"}}), "locale"),
    (_bad(**{"tts.voices": {}}), "at least one"),
    (_bad(**{"tts.base_url": "api.openai.com"}), "base_url"),
    (_bad(**{"stt.model": None}), "model"),
    (_bad(**{"tts.key": "sk-123"}), "unknown key"),
])
def test_record_refuses_a_key_in_the_file_a_shared_voice_and_every_other_invalid_shape(home, cfg, word):
    proc = _record(home, cfg)
    assert proc.returncode == 1, proc.stdout
    assert word in proc.stderr
    assert not (home / "speech.toml").exists()


def test_a_keyless_self_hosted_endpoint_is_valid(home):
    cfg = json.loads(json.dumps(GOOD))
    cfg["tts"].update({"provider": "kokoro-fastapi", "base_url": "http://localhost:8880/v1",
                       "api_key_env": ""})
    cfg["stt"].update({"base_url": "http://localhost:8000/v1", "api_key_env": ""})
    assert _record(home, cfg).returncode == 0
    assert _step(home, "check").returncode == 0
