"""Behaviour tests for the post-compaction recovery SessionStart hook.

After a compaction only the five most recently read files come back, so the hook tells the
agent which reading map to re-read from. It must speak on the `compact` source only and must
never block a session.
"""
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
HOOK = PLUGIN / "hooks" / "recover-after-compaction.sh"
HOOKS_JSON = PLUGIN / "hooks" / "hooks.json"
MAP = PLUGIN / "snippets" / "read-before-act.md"
ETHOS = PLUGIN / "ODOO-AI-ETHOS.md"


def _run(stdin_text):
    return subprocess.run(
        ["bash", str(HOOK)],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _payload(source):
    return json.dumps({"hook_event_name": "SessionStart", "source": source})


def test_compaction_notice_names_the_reading_map_and_the_five_file_limit():
    r = _run(_payload("compact"))
    assert r.returncode == 0
    lines = r.stdout.strip().splitlines()
    assert len(lines) == 1
    out = json.loads(lines[0])["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    ctx = out["additionalContext"]
    assert "five" in ctx
    assert str(MAP) in ctx and MAP.is_file()


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "fork"])
def test_other_session_sources_get_no_notice(source):
    r = _run(_payload(source))
    assert r.returncode == 0
    assert r.stdout == ""


@pytest.mark.parametrize("stdin_text", ["", "{not json", "not json at all"])
def test_empty_or_malformed_input_never_blocks_the_session(stdin_text):
    r = _run(stdin_text)
    assert r.returncode == 0
    assert r.stdout == ""


def test_hook_is_registered_for_the_compact_source_only():
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    entries = data["hooks"]["SessionStart"]
    mine = [
        e for e in entries
        if any("recover-after-compaction.sh" in h["command"] for h in e["hooks"])
    ]
    assert len(mine) == 1
    assert mine[0].get("matcher") == "compact"
    assert [e for e in entries if "matcher" in e] == mine
    assert "recovery notice" in data["description"]


@pytest.mark.parametrize("path", [ETHOS, MAP], ids=["ethos", "read-before-act"])
def test_re_read_condition_is_the_observable_compaction_notice(path):
    text = " ".join(path.read_text(encoding="utf-8").split())
    assert "compaction notice" in text
    assert "Re-read only after a context compaction" not in text
