"""Behaviour tests for `scripts/setup-steps/75-youtube.sh`, `youtube_config.py` (channels by
purpose), the request plan of `youtube_upload.py` and the consent flow's pieces that need no
Google. No network: uploads run with --dry-run, the consent URL is only built.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
LIB = PLUGIN / "scripts" / "lib"
STEP = PLUGIN / "scripts" / "setup-steps" / "75-youtube.sh"
UPLOAD = LIB / "youtube_upload.py"
sys.path.insert(0, str(LIB))
import youtube_config  # noqa: E402
import youtube_oauth  # noqa: E402

ENV = {"YOUTUBE_CLIENT_ID": "id.apps", "YOUTUBE_CLIENT_SECRET": "GOCSPX-fake-value-0001",
       "YOUTUBE_REFRESH_TOKEN_DOCS": "1//fake-refresh-value-0001"}
DOCS = {"slot": "docs", "channel": "Acme docs", "privacy": "unlisted", "default_language": "vi"}
MARKETING = {"slot": "marketing", "channel": "Acme"}


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


def _record(home, purpose, table):
    f = home / ("%s.json" % purpose)
    f.write_text(json.dumps(table), encoding="utf-8")
    return _step(home, "record", "--channel", purpose, "--from-json", str(f))


def test_describe_check_apply_follow_the_step_contract(home):
    assert "YouTube channels" in _step(home, "describe").stdout
    assert _step(home, "check").returncode == 1
    apply = _step(home, "apply")
    assert apply.returncode == 1 and "propose" in apply.stdout and "consent" in apply.stdout
    assert not (home / "youtube.toml").exists()


def test_propose_names_the_google_facts_the_slots_and_the_options(home):
    proc = _step(home, "propose")
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "youtube.force-ssl" in out and "In production" in out and "Branding" in out
    assert "SLOTS='docs marketing third'" in out and "youtube_refresh_token_docs" in out
    assert "RULE='at least one channel" in out and "DECLARED='0'" in out


def test_one_channel_is_enough_and_more_are_merged_one_at_a_time(home):
    assert _record(home, "docs", DOCS).returncode == 0
    text = (home / "youtube.toml").read_text(encoding="utf-8")
    assert "[channels.docs]" in text and 'slot = "docs"' in text and "fake" not in text
    assert _step(home, "check").returncode == 0
    assert _step(home, "check", "--channel", "marketing").returncode == 1
    assert _record(home, "marketing", MARKETING).returncode == 0
    shown = json.loads(_step(home, "show").stdout)["channels"]
    assert set(shown) == {"docs", "marketing"} and shown["docs"]["privacy"] == "unlisted"
    check = _step(home, "check", "--channel", "marketing")
    assert check.returncode == 0 and "CHANNEL_marketing=Acme slot=marketing" in check.stdout
    assert _step(home, "remove", "--channel", "marketing").returncode == 0
    assert set(json.loads(_step(home, "show").stdout)["channels"]) == {"docs"}


def test_a_purpose_defaults_its_slot_and_a_free_purpose_must_name_one(home):
    assert _record(home, "marketing", {"channel": "Acme"}).returncode == 0
    assert json.loads(_step(home, "show").stdout)["channels"]["marketing"]["slot"] == "marketing"
    proc = _record(home, "training", {"channel": "Acme Academy"})
    assert proc.returncode == 1 and "slot" in proc.stderr
    assert _record(home, "training", {"channel": "Acme Academy", "slot": "third"}).returncode == 0


@pytest.mark.parametrize("purpose, table, word", [
    ("docs", {"slot": "docs", "channel": "1//0g-a-real-looking-value-abcdef0123456789abcdef0123456789"}, "credential value"),
    ("docs", {"slot": "docs", "channel": "Acme", "privacy": "hidden"}, "privacy"),
    ("docs", {"slot": "docs", "channel": ""}, "channel"),
    ("docs", {"slot": "docs", "channel": "Acme", "refresh_token_env": "X"}, "unknown key"),
    ("Docs Channel", {"slot": "docs", "channel": "Acme"}, "purpose"),
    ("marketing", {"slot": "docs", "channel": "Acme"}, "one channel per slot"),
])
def test_record_refuses_a_value_in_the_file_and_every_other_invalid_shape(home, purpose, table, word):
    if word == "one channel per slot":
        assert _record(home, "docs", DOCS).returncode == 0
    before = (home / "youtube.toml").read_text(encoding="utf-8") if (home / "youtube.toml").exists() else None
    proc = _record(home, purpose, table)
    assert proc.returncode == 1 and word in proc.stderr
    after = (home / "youtube.toml").read_text(encoding="utf-8") if (home / "youtube.toml").exists() else None
    assert before == after


def test_a_single_table_file_from_an_older_plugin_is_read_as_the_docs_channel(home):
    (home / "youtube.toml").write_text(
        '[youtube]\nchannel = "Old docs"\nclient_id_env = "A"\nclient_secret_env = "B"\n'
        'refresh_token_env = "C"\nprivacy = "private"\n', encoding="utf-8")
    check = _step(home, "check")
    assert check.returncode == 0 and "NOTICE=" in check.stdout and "CHANNEL_docs=Old docs slot=docs privacy=private" in check.stdout
    assert _record(home, "marketing", MARKETING).returncode == 0
    text = (home / "youtube.toml").read_text(encoding="utf-8")
    assert "[youtube]" not in text and "[channels.docs]" in text and "[channels.marketing]" in text
    assert "client_id_env" not in text


def test_upload_dry_run_prints_the_request_plan_and_no_value(home, tmp_path):
    assert _record(home, "docs", DOCS).returncode == 0
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"\x00" * 1024)
    desc = tmp_path / "d.txt"
    desc.write_text("Mô tả video.\n\nCHAPTERS:\n0:00 Mở đầu\n", encoding="utf-8")
    srt = tmp_path / "vi_VN.srt"
    srt.write_text("1\n00:00:00,500 --> 00:00:03,000\nXin chào.\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(UPLOAD), "upload", "--channel", "docs", "--video", str(video),
                           "--title", "Demo", "--description-file", str(desc), "--captions", "vi_VN=%s" % srt,
                           "--dry-run"], capture_output=True, text=True, env=_env(home, ENV), timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "PLAN=dry-run" in proc.stdout and "uploadType=resumable" in proc.stdout
    assert "PRIVACY=unlisted" in proc.stdout and "CAPTION_vi_VN=" in proc.stdout and "CHANNEL=Acme docs (slot docs" in proc.stdout
    assert "fake" not in proc.stdout and "GOCSPX" not in proc.stdout


def test_upload_without_the_values_is_refused_before_any_network_and_names_the_slot_variable(home, tmp_path):
    assert _record(home, "docs", DOCS).returncode == 0
    video = tmp_path / "demo.mp4"; video.write_bytes(b"\x00")
    desc = tmp_path / "d.txt"; desc.write_text("x", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(UPLOAD), "upload", "--channel", "docs", "--video", str(video),
                           "--title", "Demo", "--description-file", str(desc)], capture_output=True, text=True,
                          env=_env(home), timeout=60)
    assert proc.returncode == 3 and "YOUTUBE_REFRESH_TOKEN_DOCS" in proc.stderr
    unknown = subprocess.run([sys.executable, str(UPLOAD), "check", "--channel", "marketing"],
                             capture_output=True, text=True, env=_env(home, ENV), timeout=60)
    assert unknown.returncode == 2 and "no channel for purpose 'marketing'" in unknown.stderr


def test_the_consent_url_carries_pkce_offline_access_and_the_force_ssl_scope(tmp_path):
    verifier, challenge = youtube_oauth.pkce_pair()
    assert 43 <= len(verifier) <= 128 and challenge and "=" not in challenge
    url = youtube_oauth.consent_url("id.apps", "http://127.0.0.1:4321/", challenge, "st4te")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["scope"] == [youtube_config.SCOPE] and q["access_type"] == ["offline"] and q["prompt"] == ["consent"]
    assert q["code_challenge"] == [challenge] and q["code_challenge_method"] == ["S256"] and q["state"] == ["st4te"]
    client = tmp_path / "client.json"
    client.write_text(json.dumps({"installed": {"client_id": "id.apps", "client_secret": "GOCSPX-fake-value-0001"}}))
    assert youtube_oauth.read_client_json(str(client)) == ("id.apps", "GOCSPX-fake-value-0001")
    client.write_text(json.dumps({"web": {"client_id": "x"}}))
    with pytest.raises(youtube_oauth.ConsentError):
        youtube_oauth.read_client_json(str(client))


def test_the_consent_out_json_is_private_to_the_operator(tmp_path):
    out = tmp_path / "values.json"
    youtube_oauth.write_out_json({"youtube_client_id": "a", "youtube_refresh_token_docs": "b"}, str(out))
    assert oct(out.stat().st_mode & 0o777) == "0o600"
    assert json.loads(out.read_text())["youtube_refresh_token_docs"] == "b"
    with pytest.raises(FileExistsError):
        youtube_oauth.write_out_json({}, str(out))
