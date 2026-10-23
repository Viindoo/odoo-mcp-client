"""Behaviour tests for `scripts/setup-steps/75-youtube.sh`, `youtube_config.py` and the request
plan of `youtube_upload.py`. No network: the upload is exercised with --dry-run only.
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
STEP = PLUGIN / "scripts" / "setup-steps" / "75-youtube.sh"
UPLOAD = PLUGIN / "scripts" / "lib" / "youtube_upload.py"
ENV = {"YOUTUBE_CLIENT_ID": "id.apps", "YOUTUBE_CLIENT_SECRET": "GOCSPX-fake-secret-value-0001",
       "YOUTUBE_REFRESH_TOKEN": "1//fake-refresh-token-value-0001"}
GOOD = {"youtube": {"channel": "Acme docs", "client_id_env": "YOUTUBE_CLIENT_ID",
                    "client_secret_env": "YOUTUBE_CLIENT_SECRET",
                    "refresh_token_env": "YOUTUBE_REFRESH_TOKEN", "privacy": "unlisted"}}


@pytest.fixture()
def home(tmp_path):
    (tmp_path / "state").mkdir()
    return tmp_path / "state"


def _env(home, extra=None):
    base = {k: v for k, v in os.environ.items() if not k.startswith("YOUTUBE_")}
    base["ODOO_AI_HOME"] = str(home)
    base.update(extra or {})
    return base


def _step(home, *args, extra=None):
    return subprocess.run(["bash", str(STEP), *args], capture_output=True, text=True, timeout=60,
                          env=_env(home, extra))


def _record(home, cfg):
    f = home / "y.json"
    f.write_text(json.dumps(cfg), encoding="utf-8")
    return _step(home, "record", "--from-json", str(f))


def test_describe_check_apply_follow_the_step_contract(home):
    assert "YouTube channel" in _step(home, "describe").stdout
    assert _step(home, "check").returncode == 1
    apply = _step(home, "apply")
    assert apply.returncode == 1 and "propose" in apply.stdout
    assert not (home / "youtube.toml").exists()


def test_propose_names_the_force_ssl_scope_and_set_variables_by_name_only(home):
    proc = _step(home, "propose", extra=ENV)
    assert proc.returncode == 0, proc.stderr
    assert "youtube.force-ssl" in proc.stdout and "YOUTUBE_REFRESH_TOKEN" in proc.stdout
    assert "fake-refresh-token" not in proc.stdout + proc.stderr


def test_record_show_check_round_trip_keeps_secrets_out_of_the_file(home):
    assert _record(home, GOOD).returncode == 0
    text = (home / "youtube.toml").read_text(encoding="utf-8")
    assert 'refresh_token_env = "YOUTUBE_REFRESH_TOKEN"' in text and "fake" not in text
    assert json.loads(_step(home, "show").stdout)["youtube"]["privacy"] == "unlisted"
    assert _step(home, "check").returncode == 1  # variables unset
    assert _step(home, "check", extra=ENV).returncode == 0


@pytest.mark.parametrize("change, word", [
    ({"refresh_token_env": "1//0g-a-real-looking-token-value-abcdef"}, "never the value"),
    ({"privacy": "hidden"}, "privacy"),
    ({"channel": ""}, "channel"),
    ({"api_key": "x"}, "unknown key"),
])
def test_record_refuses_a_secret_value_and_every_other_invalid_shape(home, change, word):
    cfg = json.loads(json.dumps(GOOD))
    cfg["youtube"].update(change)
    proc = _record(home, cfg)
    assert proc.returncode == 1 and word in proc.stderr
    assert not (home / "youtube.toml").exists()


def test_upload_dry_run_prints_the_request_plan_and_no_secret(home, tmp_path):
    assert _record(home, GOOD).returncode == 0
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"\x00" * 1024)
    desc = tmp_path / "d.txt"
    desc.write_text("Mô tả video.\n\nCHAPTERS:\n0:00 Mở đầu\n", encoding="utf-8")
    srt = tmp_path / "vi_VN.srt"
    srt.write_text("1\n00:00:00,500 --> 00:00:03,000\nXin chào.\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(UPLOAD), "upload", "--video", str(video), "--title", "Demo",
                           "--description-file", str(desc), "--captions", "vi_VN=%s" % srt, "--dry-run"],
                          capture_output=True, text=True, env=_env(home, ENV), timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "PLAN=dry-run" in proc.stdout and "uploadType=resumable" in proc.stdout
    assert "PRIVACY=unlisted" in proc.stdout and "CAPTION_vi_VN=" in proc.stdout
    assert "fake" not in proc.stdout and "GOCSPX" not in proc.stdout


def test_upload_without_the_variables_is_refused_before_any_network(home, tmp_path):
    assert _record(home, GOOD).returncode == 0
    video = tmp_path / "demo.mp4"; video.write_bytes(b"\x00")
    desc = tmp_path / "d.txt"; desc.write_text("x", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(UPLOAD), "upload", "--video", str(video), "--title", "Demo",
                           "--description-file", str(desc)], capture_output=True, text=True,
                          env=_env(home), timeout=60)
    assert proc.returncode == 2 and "not set" in proc.stderr
