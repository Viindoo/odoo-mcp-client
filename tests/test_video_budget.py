"""`scripts/lib/video_budget.py` - the AI spend of a demo video is estimated, ledgered and bounded."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "video_budget.py"
FAKE_KEY = "fake-demo-key-value-0123456789"


def _tool(*args, env=None):
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True,
                          timeout=60, env=env)


def _kv(stdout):
    return dict(line.split("=", 1) for line in stdout.splitlines() if "=" in line)


def _sb(tmp_path, ai):
    sb = {"languages": ["en_US", "vi_VN"], "scenes": [{"id": "s1"}, {"id": "s2"}]}
    if ai is not None:
        sb["ai"] = ai
    path = tmp_path / "sb.json"
    path.write_text(json.dumps(sb), encoding="utf-8")
    return str(path)


AI = {"requests_per_scene": 2, "tokens_per_request": 100, "takes": 2, "trials_k": 3,
      "key_env": "DEMO_AI_KEY", "key_scope": "dedicated", "quota_note": "n"}


def test_estimate_multiplies_scenes_requests_takes_languages_plus_trials(tmp_path):
    proc = _tool("estimate", "--storyboard", _sb(tmp_path, AI))
    out = _kv(proc.stdout)
    # 2 scenes x 2 req x 2 takes x 2 langs + 2 scenes x 3 trials x 2 langs = 16 + 12
    assert proc.returncode == 0 and out["ESTIMATE_REQUESTS"] == "28" and out["ESTIMATE_TOKENS"] == "2800"


def test_estimate_without_an_ai_block_is_none_with_zeros(tmp_path):
    proc = _tool("estimate", "--storyboard", _sb(tmp_path, None))
    out = _kv(proc.stdout)
    assert proc.returncode == 0 and out["AI"] == "none" and out["ESTIMATE_TOKENS"] == "0"


def _log(tmp_path, requests, tokens):
    return _tool("log", "--ledger", str(tmp_path / "l.jsonl"), "--kind", "take", "--scene", "s1",
                 "--lang", "en_US", "--requests", str(requests), "--tokens", str(tokens))


def test_log_appends_a_line_and_reports_running_totals(tmp_path):
    _log(tmp_path, 1, 10)
    out = _kv(_log(tmp_path, 2, 20).stdout)
    assert out["LOGGED"] == "1" and out["TOTAL_REQUESTS"] == "3" and out["TOTAL_TOKENS"] == "30"
    assert len((tmp_path / "l.jsonl").read_text().splitlines()) == 2


def test_check_passes_within_the_margin_and_exits_4_naming_what_is_over(tmp_path):
    sb = _sb(tmp_path, AI)
    ledger = str(tmp_path / "l.jsonl")
    assert _tool("check", "--ledger", ledger, "--storyboard", sb).returncode == 0
    _log(tmp_path, 28, 3500)  # 2800 x 1.25 = 3500 tokens: at the bound, not over
    assert _tool("check", "--ledger", ledger, "--storyboard", sb).returncode == 0
    _log(tmp_path, 0, 1)
    over = _tool("check", "--ledger", ledger, "--storyboard", sb)
    assert over.returncode == 4 and _kv(over.stdout)["OVER"] == "tokens"


def test_check_names_requests_when_only_requests_exceed(tmp_path):
    sb = _sb(tmp_path, AI)
    _log(tmp_path, 36, 10)  # 28 x 1.25 = 35
    proc = _tool("check", "--ledger", str(tmp_path / "l.jsonl"), "--storyboard", sb)
    assert proc.returncode == 4 and _kv(proc.stdout)["OVER"] == "requests"


def test_keys_refuses_a_shared_key(tmp_path):
    sb = _sb(tmp_path, dict(AI, key_scope="shared"))
    proc = _tool("keys", "--storyboard", sb, env={"DEMO_AI_KEY": FAKE_KEY})
    assert proc.returncode == 1 and "ERROR=shared key" in proc.stdout


def test_keys_refuses_an_unset_variable(tmp_path):
    proc = _tool("keys", "--storyboard", _sb(tmp_path, AI), env={})
    assert proc.returncode == 1 and "ERROR=key_env DEMO_AI_KEY unset" in proc.stdout


def test_keys_names_the_variable_and_never_prints_the_value(tmp_path):
    proc = _tool("keys", "--storyboard", _sb(tmp_path, AI), env={"DEMO_AI_KEY": FAKE_KEY})
    assert proc.returncode == 0 and _kv(proc.stdout)["KEY_ENV"] == "DEMO_AI_KEY"
    assert FAKE_KEY not in proc.stdout + proc.stderr and str(len(FAKE_KEY)) not in proc.stdout
    assert _tool("keys", "--storyboard", _sb(tmp_path, None)).stdout.strip() == "KEY=none"
