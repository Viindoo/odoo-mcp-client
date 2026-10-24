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


def test_propose_lists_the_gateway_first_then_local_services_that_answer_the_audio_shape(home, tmp_path):
    """A fake docker on PATH publishes one container port; a loopback HTTP stub answers /v1/models
    there; a second published port answers nothing."""
    import http.server, threading, socket
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            body = b'{"data": [{"id": "voice-tts"}]}'
            self.send_response(200 if self.path == "/v1/models" else 404); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); dead = s.getsockname()[1]
    bindir = tmp_path / "bin"; bindir.mkdir()
    fake = bindir / "docker"
    fake.write_text("#!/usr/bin/env bash\necho 'voice-kokoro 0.0.0.0:%d->8880/tcp'\necho 'db 127.0.0.1:%d->5432/tcp'\n" % (port, dead))
    fake.chmod(0o755)
    try:
        proc = _step(home, "propose", env={"PATH": "%s:%s" % (bindir, os.environ["PATH"]),
                                          "ODOO_AI_SPEECH_BASE_URL": "https://gateway.example.test/v1"})
    finally:
        srv.shutdown()
    assert proc.returncode == 0, proc.stderr
    assert "PROVIDER_1='gateway https://gateway.example.test/v1" in proc.stdout
    assert "PROVIDER_2='voice-kokoro http://127.0.0.1:%d/v1" % port in proc.stdout
    assert "127.0.0.1:%d" % dead not in proc.stdout
    if "FFMPEG_FILTERS_MISSING='none'" not in proc.stdout:
        assert "REMEDY_" in proc.stdout


def test_audition_candidates_and_the_rate_per_video_type_are_recorded_and_validated(home):
    cfg = json.loads(json.dumps(GOOD))
    cfg["tts"]["candidates"] = {"vi_VN": ["voice-vi", "voice-vi-2", "voice-vi-3"]}
    cfg["tts"]["rate"] = {"tutorial": "1.0", "marketing": "1.1"}
    assert _record(home, cfg).returncode == 0
    text = (home / "speech.toml").read_text(encoding="utf-8")
    assert "[tts.candidates]" in text and "[tts.rate]" in text and 'marketing = "1.1"' in text
    shown = json.loads(_step(home, "show").stdout)
    assert shown["tts"]["candidates"]["vi_VN"] == ["voice-vi", "voice-vi-2", "voice-vi-3"]
    bad = json.loads(json.dumps(GOOD)); bad["tts"]["rate"] = {"marketing": "9"}
    proc = _record(home, bad)
    assert proc.returncode == 1 and "tts.rate" in proc.stderr
    import sys as _sys
    _sys.path.insert(0, str(PLUGIN / "scripts" / "lib"))
    import speech_config as scfg
    assert scfg.rate_for(cfg, "marketing") == 1.1 and scfg.rate_for(GOOD, "tutorial") == 1.0
    assert scfg.candidates_for(cfg, "vi_VN")[0] == "voice-vi" and scfg.candidates_for(cfg, "en_US") == ["voice-en"]


def test_probe_endpoint_tells_open_from_required_and_lists_models_and_voices_without_a_value(home, tmp_path):
    """The voice conversation asks for a URL at most; everything else comes from the endpoint."""
    import http.server
    import threading

    class Open(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            body = {"/v1/models": {"data": [{"id": "voice-tts"}, {"id": "voice-stt"}]},
                    "/v1/audio/voices": {"voices": ["mai", "af_heart"]}}.get(self.path)
            if body is None:
                self.send_response(404); self.end_headers(); return
            data = json.dumps(body).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    class Gated(Open):
        def do_GET(self):
            self.send_response(401); self.end_headers()

    servers = []
    try:
        bases = {}
        for name, handler in (("open", Open), ("gated", Gated)):
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            servers.append(srv)
            bases[name] = "http://127.0.0.1:%d/v1" % srv.server_address[1]
        import shlex

        def facts(text):
            return dict(line.split("=", 1) for line in shlex.split(text) if "=" in line)

        proc = _step(home, "probe-endpoint", "--base-url", bases["open"])
        assert proc.returncode == 0, proc.stderr
        got = facts(proc.stdout)
        assert got["REACHABLE"] == "1" and got["AUTH"] == "open"
        assert got["MODELS"] == "voice-tts voice-stt" and got["VOICES"] == "mai af_heart"
        assert got["TTS_MODEL_GUESS"] == "voice-tts" and got["STT_MODEL_GUESS"] == "voice-stt"
        proc = _step(home, "probe-endpoint", "--base-url", bases["gated"])
        assert proc.returncode == 0, proc.stderr
        got = facts(proc.stdout)
        assert got["AUTH"] == "required" and "speech_voices" in got["NEXT"]
        proc = _step(home, "probe-endpoint", "--base-url", "http://127.0.0.1:9/v1")
        assert proc.returncode == 1 and facts(proc.stdout)["REACHABLE"] == "0"
    finally:
        for srv in servers:
            srv.shutdown()


def test_an_endpoint_only_record_is_accepted_and_check_says_what_is_still_missing(home, tmp_path):
    """The gated-endpoint path: the endpoint is recorded before the value exists, so the value can
    only ever travel there; the file is not a working configuration until models and voices are in."""
    spec = tmp_path / "endpoint.json"
    spec.write_text(json.dumps({"tts": {"base_url": "https://gateway.example.test/v1", "auth": "bearer"},
                                "stt": {"base_url": "https://gateway.example.test/v1", "auth": "bearer"}}))
    proc = _step(home, "record", "--from-json", str(spec), "--endpoint-only")
    assert proc.returncode == 0, proc.stderr
    text = (home / "speech.toml").read_text(encoding="utf-8")
    assert 'base_url = "https://gateway.example.test/v1"' in text and "[tts.voices]" not in text
    proc = _step(home, "check")
    assert proc.returncode == 1
    assert "INCOMPLETE=" in proc.stdout and "tts.model" in proc.stdout and "tts.voices" in proc.stdout
    assert "speech_voices" in proc.stdout
    proc = _step(home, "record", "--from-json", str(spec))          # a complete record refuses the same file
    assert proc.returncode == 1 and "model" in proc.stderr
