"""Behavioral guard: no hook of the plugin hands the harness more text than it keeps.

Claude Code replaces a hook output (`additionalContext`, `systemMessage`, a block `reason`, or
plain stdout as a whole) over 10,000 characters by a file path and a 2,000-character preview, so
the rule the hook carries never reaches the model. Every hook whose output grows with its input
(pages left open, leases held, background tasks, the size of a shipped file) is therefore bounded
well under that cut. Each test feeds the hook the largest realistic input and asserts the size
and that the rule is still there; the list of what a bound drops is counted ("+N more"), not lost.

Run with: python3 -m pytest tests/test_hook_output_bounds.py -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import test_background_wait_gate as bw
import test_enforce_teardown as et
import test_ensure_ethos_import as ee

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / "plugins" / "odoo-ai-agents"
HOOKS = PLUGIN_ROOT / "hooks"

# The harness cut is 10,000 characters; the bound leaves room for the framing around the text.
LIMIT = 8000

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("bash") is None,
    reason="the hooks need jq + bash; without them they degrade to a silent pass",
)


def _total(out: dict | None) -> int:
    """The characters the harness counts: the whole JSON the hook printed."""
    return 0 if out is None else len(json.dumps(out, ensure_ascii=False))


def test_many_live_leases_keep_the_teardown_block_inside_the_cut(tmp_path):
    """A dispatch that left 25 leases live is still told to clear every one, in a bounded text:
    the first ones in full, the rest as a count that the next refusal narrows."""
    n = 25
    tokens = [f"{i:02x}" * 16 for i in range(n)]
    lines, leases = [], []
    for tok in tokens:
        lines += et._acquired("run-abc", tok)
        leases.append(et._lease(run_id="run-abc", token=tok))
    lines.append(et._line(content=[et._cont("DONE")]))
    _, out = et._run(tmp_path, lines, leases=leases)
    assert out is not None and out.get("decision") == "block"
    reason = out["reason"]
    assert _total(out) < LIMIT, f"block reason is {_total(out)} characters"
    assert f"{n} LIVE" in reason, "the true number of live leases must still be stated"
    assert tokens[0] in reason and "lease_release" in reason, "the first lease keeps its release forms"
    assert "more live lease(s)" in reason, "the leases left out must be counted"
    assert "handoff" in reason, "the three exits must survive the bound"


def test_many_open_pages_keep_the_browser_advisory_inside_the_cut(tmp_path):
    lines = [et._page("navigate_page", i, "http://127.0.0.1:8069/odoo/" + "x" * 300)
             for i in range(1, 61)]
    lines.append(et._line(content=[et._cont("DONE")]))
    _, out = et._run(tmp_path, lines)
    msg = et._advisory(out)
    assert _total(out) < LIMIT, f"browser advisory is {_total(out)} characters"
    assert "close_page every page but one" in msg, "the instruction must survive the bound"
    assert "+55 more" in msg, "the pages left out must be counted"


def test_many_background_tasks_keep_the_wait_refusal_inside_the_cut(tmp_path):
    ids = [f"bg{i}" for i in range(40)]
    t = bw._transcript(tmp_path, ids)
    tasks = [bw._shell_task(i, command="make test " + "y" * 3000) for i in ids]
    rc, stdout = bw._run(bw._subagent_payload(t, tasks))
    assert rc == 0 and bw._decision(stdout) == "block"
    assert len(stdout) < LIMIT, f"wait refusal is {len(stdout)} characters"
    reason = bw._reason(stdout)
    assert "40 background shell command(s)" in reason, "the true count must still be stated"
    assert "+35 more" in reason, "the tasks left out must be counted"
    for move in ("read it now", "wait for it in this turn", "stop it"):
        assert move in reason.lower(), f"the {move!r} exit must survive the bound"


def test_the_shipped_ethos_is_bridged_inside_the_cut_on_first_add(tmp_path):
    """The first-add bridge carries the whole ETHOS file when it fits; the real file is longer
    than the cut, so it must arrive as outline + path, with every principle still named."""
    ethos = PLUGIN_ROOT / "ODOO-AI-ETHOS.md"
    hook = ee._make_temp_plugin(tmp_path, ethos_content=ethos.read_text(encoding="utf-8"))
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    proc = ee._run(hook, cfg)
    assert proc.returncode == 0
    assert len(proc.stdout) < LIMIT, f"ETHOS bridge is {len(proc.stdout)} characters"
    ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
    headings = [l for l in ethos.read_text(encoding="utf-8").splitlines() if l.startswith("## ")]
    assert headings and all(h in ctx for h in headings), "every principle heading must be named"
    assert "ODOO-AI-ETHOS.md" in ctx, "the path to the full text must be given"


def test_a_short_ethos_is_still_bridged_whole(tmp_path):
    hook = ee._make_temp_plugin(tmp_path, ethos_content="# ETHOS\n## 1. Boil the Ocean\nbody text\n")
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    proc = ee._run(hook, cfg)
    ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "body text" in ctx


def test_the_session_start_digest_leaves_room_under_the_cut():
    """The SessionStart hooks print the digest as it is; it must stay a fraction of the cut."""
    digest = (PLUGIN_ROOT / "docs" / "reference" / "orchestration-digest.txt").read_text(encoding="utf-8")
    assert len(digest) < 4000, f"digest is {len(digest)} characters"


def test_the_compaction_notice_stays_inside_the_cut(tmp_path):
    proc = subprocess.run(["bash", str(HOOKS / "recover-after-compaction.sh")],
                          input=json.dumps({"source": "compact"}), capture_output=True, text=True,
                          env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT)}, timeout=30)
    assert proc.stdout.strip() and len(proc.stdout) < LIMIT
