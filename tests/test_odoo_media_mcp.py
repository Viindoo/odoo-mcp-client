"""Behaviour tests for the odoo-media stdio MCP server: the values reach the tools only through
the server's environment, nothing secret leaves a tool result, and every speech / YouTube tool does
its job against fake loopback endpoints (no network, no Google, no vendor).

The real entry point is driven over pipes (tests/odoo_local_mcp_harness.py, MEDIA_SERVER). The fake
endpoints speak the OpenAI audio shape (speech + transcriptions), Google's token endpoint, the
channels.list read and the resumable-upload protocol, and record what they were sent.
"""
from __future__ import annotations

import http.server
import json
import os
import shutil
import struct
import threading
import wave
from pathlib import Path

import pytest

from odoo_local_mcp_harness import MEDIA_SERVER, PLUGIN, McpClient, hermetic_env, structured

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
PLUGIN_VERSION = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]

PROBE_VI = "Xin chào, đây là bản thử giọng đọc cho video giới thiệu."


def _wav_bytes(seconds=0.3, rate=24000):
    frames = int(seconds * rate)
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
        wf.writeframes(struct.pack("<%dh" % frames, *([2000, -2000] * (frames // 2) + [0] * (frames % 2))))
    return buf.getvalue()


class _Fake(http.server.BaseHTTPRequestHandler):
    """One handler for every endpoint; `calls` records (path, headers subset, body) per request."""
    calls = []
    transcript = PROBE_VI
    token_status = 200

    def log_message(self, *_):
        pass

    def _read(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _send(self, status, body, ctype="application/json", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.calls.append(("GET", self.path, self.headers.get("Authorization", ""), b""))
        if self.path.startswith("/v1/audio/voices"):
            return self._send(200, json.dumps({"voices": ["mai", "af_heart"]}).encode())
        if self.path.startswith("/v1/models"):
            return self._send(200, json.dumps({"data": [{"id": "voice-tts"}, {"id": "voice-stt"}]}).encode())
        if self.path.startswith("/youtube/v3/channels"):
            return self._send(200, json.dumps({"items": [{"id": "UCfake", "snippet": {"title": "Acme Docs"}}]}).encode())
        if self.path.startswith("/youtube/v3/videos"):
            return self._send(200, json.dumps({"items": [{"id": "vid123", "snippet": {"title": "Demo", "channelId": "UCfake", "channelTitle": "Acme Docs"},
                                                          "status": {"uploadStatus": "processed", "privacyStatus": "unlisted"},
                                                          "processingDetails": {"processingStatus": "succeeded"}}]}).encode())
        return self._send(404, b"{}")

    def do_POST(self):
        body = self._read()
        self.calls.append(("POST", self.path, self.headers.get("Authorization", ""), body))
        if self.path.startswith("/v1/audio/speech"):
            return self._send(200, _wav_bytes(), "audio/wav")
        if self.path.startswith("/v1/audio/transcriptions"):
            words = [{"word": w, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, w in enumerate(self.transcript.split())]
            return self._send(200, json.dumps({"text": self.transcript, "words": words}, ensure_ascii=False).encode())
        if self.path.startswith("/token"):
            if self.token_status != 200:
                return self._send(self.token_status, json.dumps({"error": "invalid_grant"}).encode())
            return self._send(200, json.dumps({"access_token": "ya29.fake-access", "expires_in": 3600}).encode())
        if self.path.startswith("/upload/youtube/v3/videos"):
            host = self.headers.get("Host")
            return self._send(200, b"", extra={"Location": "http://%s/upload/session/1" % host})
        if self.path.startswith("/upload/youtube/v3/captions"):
            return self._send(200, json.dumps({"id": "cap1"}).encode())
        if self.path.startswith("/upload/youtube/v3/thumbnails"):
            return self._send(200, json.dumps({"items": []}).encode())
        if self.path.startswith("/youtube/v3/playlistItems"):
            return self._send(200, json.dumps({"id": "pl1"}).encode())
        return self._send(404, b"{}")

    def do_PUT(self):
        body = self._read()
        self.calls.append(("PUT", self.path, self.headers.get("Content-Range", ""), body))
        if self.path.startswith("/youtube/v3/videos"):
            return self._send(200, json.dumps({"id": "vid123", "status": {"privacyStatus": json.loads(body)["status"]["privacyStatus"]}}).encode())
        return self._send(200, json.dumps({"id": "vid123", "status": {"privacyStatus": "unlisted"}}).encode())

    def do_DELETE(self):
        self.calls.append(("DELETE", self.path, "", b""))
        return self._send(204, b"")


@pytest.fixture()
def fake():
    _Fake.calls = []
    _Fake.transcript = PROBE_VI
    _Fake.token_status = 200
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % server.server_address[1]
    try:
        yield base
    finally:
        server.shutdown()


def _write_configs(home: Path, base: str, auth="bearer"):
    home.mkdir(parents=True, exist_ok=True)
    (home / "speech.toml").write_text(
        '[tts]\nprovider = "gateway"\nbase_url = "%s/v1"\nmodel = "voice-tts"\nauth = "%s"\nresponse_format = "wav"\n'
        '[tts.voices]\nvi_VN = "mai"\nen_US = "af_heart"\n[stt]\nbase_url = "%s/v1"\nmodel = "voice-stt"\nauth = "%s"\n'
        % (base, auth, base, auth), encoding="utf-8")
    (home / "youtube.toml").write_text(
        '[channels.docs]\nslot = "docs"\nchannel = "Acme Docs"\nprivacy = "unlisted"\nplaylist_id = "PLx"\n'
        '[channels.marketing]\nslot = "marketing"\nchannel = "Acme"\n', encoding="utf-8")


@pytest.fixture()
def media(tmp_path, fake, monkeypatch):
    home = tmp_path / "home"
    _write_configs(home, fake)
    env = hermetic_env(home, SPEECH_API_KEY="speech-value-0001", YOUTUBE_CLIENT_ID="id.apps",
                       YOUTUBE_CLIENT_SECRET="GOCSPX-fake-0001", YOUTUBE_REFRESH_TOKEN_DOCS="1//fake-docs",
                       YOUTUBE_REFRESH_TOKEN_MARKETING="${user_config.youtube_refresh_token_marketing}",
                       ODOO_AI_GOOGLE_BASE=fake)
    with McpClient(env, tmp_path, server=MEDIA_SERVER) as client:
        client.initialize()
        yield client, home, fake


def test_initialize_names_the_media_server_and_lists_its_tools(tmp_path):
    with McpClient(hermetic_env(tmp_path / "home"), tmp_path, server=MEDIA_SERVER) as client:
        result = client.initialize()["result"]
        assert result["serverInfo"] == {"name": "odoo-media", "version": PLUGIN_VERSION}
        assert "configured through the plugin's options" in result["instructions"]
        names = [t["name"] for t in client.request("tools/list")["result"]["tools"]]
        assert names == ["media_info", "speech_synthesize", "speech_transcribe", "speech_voices", "speech_probe",
                         "youtube_check", "youtube_upload", "youtube_describe", "youtube_set_privacy", "youtube_delete",
                         "youtube_status"]
        assert client.stdout_violations == []


def test_media_info_reports_presence_per_option_and_never_a_value(media):
    client, home, fake = media
    info = structured(client.call("media_info"))
    assert info["options"] == {"speech_api_key": True, "youtube_client_id": True, "youtube_client_secret": True,
                               "youtube_refresh_token_docs": True, "youtube_refresh_token_marketing": False,
                               "youtube_refresh_token_third": False}
    assert info["speech"]["configured"] and info["speech"]["languages"] == ["en_US", "vi_VN"]
    assert info["youtube"]["channels"]["docs"]["value_present"] is True
    assert info["youtube"]["channels"]["marketing"]["value_present"] is False
    assert "speech-value-0001" not in json.dumps(info) and "fake" not in json.dumps(info)


def test_a_missing_option_is_refused_by_name_before_any_network(tmp_path, fake):
    home = tmp_path / "home"
    _write_configs(home, fake)
    with McpClient(hermetic_env(home), tmp_path, server=MEDIA_SERVER) as client:
        client.initialize()
        err = structured(client.call("speech_voices"))["error"]
        assert err["code"] == "VALUE_NOT_CONFIGURED" and err["diagnostics"]["option"] == "speech_api_key"
        assert "/plugin" in err["remedy"] and "chat" in err["remedy"]
        err = structured(client.call("youtube_check", {"channel": "docs", "live": True}))["error"]
        assert err["code"] == "VALUE_NOT_CONFIGURED" and "youtube_refresh_token_docs" in err["diagnostics"]["options"]
        # the configuration alone is readable without the values
        ok = structured(client.call("youtube_check", {"channel": "docs"}))
        assert ok["values_present"] is False and set(ok["missing_options"]) == {"youtube_client_id", "youtube_client_secret", "youtube_refresh_token_docs"}
    assert _Fake.calls == []


def test_a_keyless_endpoint_needs_no_option(tmp_path, fake):
    home = tmp_path / "home"
    _write_configs(home, fake, auth="none")
    with McpClient(hermetic_env(home), tmp_path, server=MEDIA_SERVER) as client:
        client.initialize()
        assert structured(client.call("speech_voices"))["voices"] == {"voices": ["mai", "af_heart"]}
    assert _Fake.calls[-1][2] == ""  # no Authorization header was sent


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_synthesize_sends_the_bearer_value_and_the_respelled_text_and_writes_48k_wav(media, tmp_path):
    client, home, fake = media
    out = tmp_path / "clip.wav"
    res = structured(client.call("speech_synthesize", {
        "text": "Viindoo AI giúp bạn.", "lang": "vi_VN", "out": str(out),
        "pronunciation": {"vi_VN": [{"written": "Viindoo", "spoken": "Vinn đu"}, {"written": "AI", "spoken": "ây ai"}]}}))
    assert res["out"] == str(out) and res["duration_s"] > 0.2
    with wave.open(str(out), "rb") as wf:
        assert wf.getframerate() == 48000 and wf.getnchannels() == 1
    method, path, auth, body = _Fake.calls[-1]
    assert path == "/v1/audio/speech" and auth == "Bearer speech-value-0001"
    sent = json.loads(body.decode("utf-8"))
    assert sent["input"] == "Vinn đu, ây ai giúp bạn." and sent["voice"] == "mai" and sent["response_format"] == "wav"
    assert "speech-value-0001" not in json.dumps(res)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_transcribe_returns_the_text_and_words_on_request(media, tmp_path):
    client, home, fake = media
    clip = tmp_path / "in.wav"
    clip.write_bytes(_wav_bytes())
    plain = structured(client.call("speech_transcribe", {"audio": str(clip), "lang": "vi_VN"}))
    assert plain["text"] == PROBE_VI and plain["words"] == []
    rich = structured(client.call("speech_transcribe", {"audio": str(clip), "lang": "vi_VN", "words": True}))
    assert rich["words"][0]["word"] == "Xin" and rich["words"][1]["start"] == pytest.approx(0.4)
    body = _Fake.calls[-1][3]
    assert b'name="language"\r\n\r\nvi' in body and b"verbose_json" in body


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_the_probe_passes_when_the_engine_says_the_sentence_back_and_fails_on_a_mismatch(media):
    client, home, fake = media
    res = structured(client.call("speech_probe", {"lang": "vi_VN"}))
    assert res["ok"] is True and res["results"][0]["verdict"] == "pass" and res["results"][0]["wer"] == 0.0
    assert res["results"][0]["clip"].startswith(str(home / "scratch" / "speech-probe"))
    _Fake.transcript = "something completely different was heard here"
    res = structured(client.call("speech_probe", {"lang": "vi_VN"}))
    assert res["ok"] is False and res["results"][0]["verdict"] == "fail"


def test_youtube_check_live_refreshes_a_token_and_reads_the_channel_title(media):
    client, home, fake = media
    res = structured(client.call("youtube_check", {"channel": "docs", "live": True}))
    assert res["live"] and res["channel_title"] == "Acme Docs" and res["channel_id"] == "UCfake"
    assert res["values_present"] and res["slot"] == "docs"
    token_call = [c for c in _Fake.calls if c[1].startswith("/token")][0]
    assert b"grant_type=refresh_token" in token_call[3] and b"1%2F%2Ffake-docs" in token_call[3]
    assert "fake-docs" not in json.dumps(res) and "GOCSPX" not in json.dumps(res)


def test_youtube_check_on_a_purpose_without_a_channel_keeps_the_video_local(media):
    client, home, fake = media
    err = structured(client.call("youtube_check", {"channel": "training"}))["error"]
    assert err["code"] == "YOUTUBE_CHANNEL_UNKNOWN" and "keep the video local" in err["remedy"]


def test_youtube_upload_dry_run_plans_and_a_real_upload_runs_the_resumable_protocol(media, tmp_path):
    client, home, fake = media
    video = tmp_path / "final.mp4"; video.write_bytes(b"\x00" * 4096)
    srt = tmp_path / "vi_VN.srt"; srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nXin chào\n")
    thumb = tmp_path / "t.jpg"; thumb.write_bytes(b"\xff\xd8\xff\xd9")
    plan = structured(client.call("youtube_upload", {"channel": "docs", "video": str(video), "title": "Demo",
                                                     "description": "d", "dry_run": True}))
    assert plan["dry_run"] and plan["privacy"] == "unlisted" and any("uploadType=resumable" in l for l in plan["plan"])
    assert _Fake.calls == []
    res = structured(client.call("youtube_upload", {"channel": "docs", "video": str(video), "title": "Demo",
                                                    "description": "Mô tả", "language": "vi",
                                                    "captions": {"vi_VN": str(srt)}, "thumbnail": str(thumb)}))
    assert res["video_id"] == "vid123" and res["watch_url"] == "https://www.youtube.com/watch?v=vid123"
    assert res["embed_url"].endswith("/embed/vid123") and res["privacy"] == "unlisted"
    assert res["captions"] == {"vi_VN": "ok"} and res["thumbnail"] == "ok" and res["playlist"] == "ok"
    paths = [c[1].split("?")[0] for c in _Fake.calls]
    assert "/token" in paths[0] and "/upload/youtube/v3/videos" in paths and "/upload/session/1" in paths
    assert "/upload/youtube/v3/captions" in paths and "/upload/youtube/v3/thumbnails/set" in paths and "/youtube/v3/playlistItems" in paths
    init = [c for c in _Fake.calls if c[1].startswith("/upload/youtube/v3/videos")][0]
    assert json.loads(init[3])["snippet"]["defaultLanguage"] == "vi"
    assert "fake" not in json.dumps(res) and "GOCSPX" not in json.dumps(res)
    status = structured(client.call("youtube_status", {"channel": "docs", "video_id": "vid123"}))
    assert status == {"upload_status": "processed", "privacy": "unlisted", "processing": "succeeded"}


def test_a_revoked_refresh_token_is_reported_as_youtube_failed_with_the_consent_remedy(media):
    client, home, fake = media
    _Fake.token_status = 400
    err = structured(client.call("youtube_check", {"channel": "docs", "live": True}))["error"]
    assert err["code"] == "YOUTUBE_FAILED" and "invalid_grant" in err["message"] and "consent" in err["remedy"]


def test_a_video_is_described_made_public_and_deleted_only_with_its_title(media):
    client, home, fake = media
    d = structured(client.call("youtube_describe", {"channel": "docs", "video_id": "vid123"}))
    assert d["title"] == "Demo" and d["channel_title"] == "Acme Docs" and d["privacy"] == "unlisted"
    pub = structured(client.call("youtube_set_privacy", {"channel": "docs", "video_id": "vid123", "privacy": "public"}))
    assert pub["privacy"] == "public"
    put = [c for c in _Fake.calls if c[0] == "PUT" and c[1].startswith("/youtube/v3/videos")][0]
    assert json.loads(put[3])["status"]["privacyStatus"] == "public"
    wrong = structured(client.call("youtube_delete", {"channel": "docs", "video_id": "vid123", "title": "Other"}))
    assert wrong["error"]["code"] == "INVALID_ARGUMENTS" and not [c for c in _Fake.calls if c[0] == "DELETE"]
    gone = structured(client.call("youtube_delete", {"channel": "docs", "video_id": "vid123", "title": "Demo"}))
    assert gone["id"] == "vid123" and [c for c in _Fake.calls if c[0] == "DELETE"][0][1].endswith("id=vid123")


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")
def test_speed_and_an_audition_voice_reach_the_engine_and_the_probe_says_whether_speed_was_honoured(media, tmp_path):
    client, home, fake = media
    out = tmp_path / "fast.wav"
    res = structured(client.call("speech_synthesize", {"text": "Xin chào.", "lang": "vi_VN", "out": str(out), "speed": 1.2,
                                                        "voice": "mai-2"}))
    assert res["duration_s"] > 0
    sent = json.loads(_Fake.calls[-1][3].decode("utf-8"))
    assert sent["speed"] == 1.2 and sent["voice"] == "mai-2"
    probe = structured(client.call("speech_probe", {"lang": "vi_VN", "speed": 1.3}))
    entry = probe["results"][0]
    assert entry["speed"] == 1.3 and entry["speed_honoured"] is False   # the fake returns the same clip whatever the speed


# --- the one-time upgrade pass at server start ------------------------------------------------

_CLAUDE_STUB = r'''#!/usr/bin/env python3
import json, os, sys
state = os.environ["STUB_STATE"]
open(os.path.join(state, "calls.log"), "a").write(json.dumps(sys.argv[1:]) + "\n")
cfg_path = os.path.join(state, "configured.json")
configured = json.load(open(cfg_path)) if os.path.exists(cfg_path) else {}
pid = sys.argv[3] if len(sys.argv) > 3 else ""
if sys.argv[1:3] == ["plugin", "configure"] and "--json" in sys.argv:
    print(json.dumps({"pluginId": pid, "configured": configured.get(pid, [])}))
elif sys.argv[1:3] == ["plugin", "configure"] and "--values-stdin" in sys.argv:
    values = json.loads(sys.stdin.read())
    json.dump(values, open(os.path.join(state, "values-%s.json" % pid.split("@")[0]), "w"))
    configured[pid] = sorted(set(configured.get(pid, [])) | set(values))
    json.dump(configured, open(cfg_path, "w"))
elif sys.argv[1:3] == ["mcp", "remove"]:
    path = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], ".claude.json")
    data = json.load(open(path)); data["mcpServers"].pop(sys.argv[3], None); json.dump(data, open(path, "w"))
else:
    sys.exit(2)
'''


def _upgrade_world(tmp_path):
    import stat
    home = tmp_path / "home"
    home.mkdir()
    (home / "speech.toml").write_text(
        '[tts]\nprovider = "gateway"\nbase_url = "http://127.0.0.1:1/v1"\nmodel = "voice-tts"\napi_key_env = "OLD_SPEECH_NAME"\n'
        '[tts.voices]\nvi_VN = "mai"\n[stt]\nbase_url = "http://127.0.0.1:1/v1"\nmodel = "voice-stt"\napi_key_env = "OLD_SPEECH_NAME"\n',
        encoding="utf-8")
    (home / "youtube.toml").write_text('[youtube]\nchannel = "Acme Docs"\nprivacy = "unlisted"\n', encoding="utf-8")
    state = tmp_path / "stub-state"
    state.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "claude"
    stub.write_text(_CLAUDE_STUB, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    cfg = tmp_path / "claude-config"
    (cfg / "plugins").mkdir(parents=True)
    (cfg / ".claude.json").write_text(json.dumps({"mcpServers": {"odoo-semantic": {
        "type": "http", "url": "https://osm.example.test/mcp", "headers": {"X-API-Key": "osm_old_value"}}}}))
    (cfg / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        "odoo-semantic-mcp@test-mkt": [{"scope": "user", "installPath": str(PLUGIN.parent / "odoo-semantic-mcp")}]}}))
    env = hermetic_env(home, PATH="%s:%s" % (bindir, os.environ.get("PATH", "")), STUB_STATE=str(state),
                       CLAUDE_CONFIG_DIR=str(cfg), ODOO_MEDIA_PLUGIN_ID="odoo-ai-agents@test-mkt",
                       OLD_SPEECH_NAME="speech-value-moved-1", YOUTUBE_CLIENT_ID="id.apps.moved")
    env.pop("SPEECH_API_KEY", None)
    return home, state, cfg, env


def _wait_for(path: Path, seconds=10.0):
    import time
    end = time.time() + seconds
    while time.time() < end:
        if path.exists():
            return True
        time.sleep(0.05)
    return False


def test_a_new_plugin_version_moves_earlier_values_once_and_the_tools_work_in_the_same_session(tmp_path):
    home, state, cfg, env = _upgrade_world(tmp_path)
    stamp = home / "state" / "upgrade.json"
    with McpClient(env, tmp_path, server=MEDIA_SERVER) as client:
        client.initialize()
        assert _wait_for(stamp), "the upgrade pass did not finish: %s" % "".join(client.stderr_chunks)[-2000:]
        info = structured(client.call("media_info"))
        assert info["options"]["speech_api_key"] is True          # applied to this process, no reload needed
        assert info["options"]["youtube_client_id"] is True
        assert info["upgrade"]["version"] == PLUGIN_VERSION
        assert sorted(info["upgrade"]["moved"]) == ["speech_api_key", "youtube_client_id"]
        assert "youtube_client_secret" in info["upgrade"]["missing"]
        assert info["upgrade"]["connection"]["removed"] == "user"
        assert "speech-value-moved-1" not in json.dumps(info) and "osm_old_value" not in json.dumps(info)
    sent = json.loads((state / "values-odoo-ai-agents.json").read_text())
    assert sent == {"speech_api_key": "speech-value-moved-1", "youtube_client_id": "id.apps.moved"}
    conn = json.loads((state / "values-odoo-semantic-mcp.json").read_text())
    assert conn == {"mcp_url": "https://osm.example.test/mcp", "api_key": "osm_old_value"}
    assert "odoo-semantic" not in json.loads((cfg / ".claude.json").read_text())["mcpServers"]
    assert "api_key_env" not in (home / "speech.toml").read_text()
    assert "[channels.docs]" in (home / "youtube.toml").read_text()
    stderr = "".join(client.stderr_chunks)
    assert "speech-value-moved-1" not in stderr and "osm_old_value" not in stderr
    # the readiness hook shows the notice once, then it is gone
    import subprocess
    hook = PLUGIN / "hooks" / "check-setup-deps.sh"
    proc = subprocess.run(["bash", str(hook)], capture_output=True, text=True, env=env)
    assert "upgrade" in proc.stderr and "speech_api_key" in proc.stderr and "/reload-plugins" in proc.stderr
    assert not (home / "state" / "upgrade-notice.txt").exists()
    # a second start on the same version runs nothing
    calls_before = (state / "calls.log").read_text()
    with McpClient(env, tmp_path, server=MEDIA_SERVER) as client:
        client.initialize()
        structured(client.call("media_info"))
    assert (state / "calls.log").read_text() == calls_before


def test_a_checkout_loaded_with_plugin_dir_never_moves_anything(tmp_path):
    home, state, cfg, env = _upgrade_world(tmp_path)
    env.pop("ODOO_MEDIA_PLUGIN_ID")
    with McpClient(env, tmp_path, server=MEDIA_SERVER) as client:
        client.initialize()
        info = structured(client.call("media_info"))
        assert info["upgrade"] == {"version": None}
    assert not (home / "state" / "upgrade.json").exists()
    assert not (state / "calls.log").exists()
    assert "api_key_env" in (home / "speech.toml").read_text()


def test_the_connection_half_waits_for_the_sibling_plugin_and_runs_once_it_is_updated(tmp_path):
    """A machine that updates odoo-ai-agents before odoo-semantic-mcp keeps its stand-alone
    registration for now; the pass marks that half pending and finishes it at the first server
    start after the sibling plugin is installed - without redoing the values half."""
    home, state, cfg, env = _upgrade_world(tmp_path)
    installed = cfg / "plugins" / "installed_plugins.json"
    installed.write_text(json.dumps({"version": 2, "plugins": {}}))     # sibling not installed yet
    stamp = home / "state" / "upgrade.json"
    with McpClient(env, tmp_path, server=MEDIA_SERVER) as client:
        client.initialize()
        assert _wait_for(stamp)
        info = structured(client.call("media_info"))
        assert info["upgrade"]["connection"]["pending"] is True
    assert "odoo-semantic" in json.loads((cfg / ".claude.json").read_text())["mcpServers"]
    assert sorted(json.loads(stamp.read_text())["moved"]) == ["speech_api_key", "youtube_client_id"]
    calls_before = (state / "calls.log").read_text()
    installed.write_text(json.dumps({"version": 2, "plugins": {
        "odoo-semantic-mcp@test-mkt": [{"scope": "user", "installPath": str(PLUGIN.parent / "odoo-semantic-mcp")}]}}))
    (home / "state" / "upgrade-notice.txt").unlink()          # the hook consumed the first notice
    with McpClient(env, tmp_path, server=MEDIA_SERVER) as client:
        client.initialize()
        assert _wait_for(home / "state" / "upgrade-notice.txt"), "the pending half did not run again"
        info = structured(client.call("media_info"))
        assert info["upgrade"]["connection"]["removed"] == "user"
    assert "odoo-semantic" not in json.loads((cfg / ".claude.json").read_text())["mcpServers"]
    new_calls = (state / "calls.log").read_text()[len(calls_before):]
    assert "odoo-ai-agents@test-mkt" not in new_calls and '"--values-stdin"' in new_calls


def test_speech_voices_lists_models_too_and_works_on_an_endpoint_only_file_but_never_takes_a_url(media, tmp_path):
    """The setup conversation records the endpoint first, the operator configures the value, and
    the tool lists voices and models from THAT endpoint; a caller can never point it elsewhere."""
    client, home, fake = media
    out = structured(client.call("speech_voices"))
    assert out["voices"] == {"voices": ["mai", "af_heart"]} and out["models"] == ["voice-tts", "voice-stt"]
    assert out["tts_model_guess"] == "voice-tts" and out["stt_model_guess"] == "voice-stt"
    (home / "speech.toml").write_text('[tts]\nbase_url = "%s/v1"\nauth = "bearer"\n[stt]\nbase_url = "%s/v1"\nauth = "bearer"\n'
                                      % (fake, fake), encoding="utf-8")   # endpoint only: no model, no voices
    out = structured(client.call("speech_voices"))
    assert out["models"] == ["voice-tts", "voice-stt"] and out["voices"]["voices"] == ["mai", "af_heart"]
    sent = [c for c in _Fake.calls if c[1] in ("/v1/models", "/v1/audio/voices")]
    assert sent and all(c[2].startswith("Bearer ") for c in sent)      # the configured value went along
    assert "speech-value-0001" not in json.dumps(out)
    before = len(_Fake.calls)
    refused = client.call("speech_voices", {"base_url": "http://127.0.0.1:1/v1"})
    assert refused.get("error") or structured(refused).get("error")     # no caller-chosen destination
    assert len(_Fake.calls) == before
