"""Behaviour tests for the compaction pair: steer-compaction.sh (PreCompact) records what the
next window needs, recover-after-compaction.sh (SessionStart, source compact) emits the notice.

Facts come from the per-session state file, else from the transcript, else the notice is the
static sentences alone. Both hooks exit 0 on any input and speak only when they should.
"""
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
HOOKS = PLUGIN / "hooks"
RECOVER = HOOKS / "recover-after-compaction.sh"
STEER = HOOKS / "steer-compaction.sh"
HOOKS_JSON = HOOKS / "hooks.json"
HARNESS_CUT = 10000

needs_jq = pytest.mark.skipif(shutil.which("jq") is None, reason="the state and the notice facts need jq")


def _env(tmp_path, **extra):
    e = dict(os.environ)
    for var in ("ODOO_AI_HOME", "ODOO_AI_PROJECT_DIR", "ODOO_AI_WORKTREE_DIR"):
        e.pop(var, None)
    e.update({"HOME": str(tmp_path / "home"), "ODOO_AI_HOME": str(tmp_path / "state"),
              "CLAUDE_PLUGIN_ROOT": str(PLUGIN)})
    e.update(extra)
    return e


def _run(hook, stdin_text, env=None):
    return subprocess.run(["bash", str(hook)], input=stdin_text, capture_output=True, text=True,
                          timeout=30, env=env)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _skill_call(name, tid):
    return json.dumps({"type": "assistant", "timestamp": _now(), "message": {
        "role": "assistant", "content": [
            {"type": "tool_use", "id": tid, "name": "Skill", "input": {"skill": name}}]}})


def _command_record(name):
    return json.dumps({"type": "user", "message": {
        "role": "user", "content": f"<command-message>x</command-message><command-name>/{name}</command-name>"}})


def _transcript(tmp_path, lines, name="t.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _payload(source="compact", **extra):
    return json.dumps({"hook_event_name": "SessionStart", "source": source, **extra})


def _notice(proc):
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.strip().splitlines()
    assert len(lines) == 1
    out = json.loads(lines[0])["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    assert len(proc.stdout) < HARNESS_CUT
    return out["additionalContext"]


def _owned_run(tmp_path, run_id="r42", cursor="n2", approach="odoo-test-writing", kind="skill"):
    """A run record this session wrote last: a tool call naming it, stamped around the write."""
    isolate = tmp_path / "isolate"
    isolate.mkdir(exist_ok=True)
    rf = isolate / f"run-{run_id}.json"
    call = {"type": "assistant", "timestamp": _now(), "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "toolu_w", "name": "Bash", "input": {"command": f"echo > {rf}"}}]}}
    rf.write_text(json.dumps({
        "run_id": run_id, "status": "NEEDS_NEXT", "cursor": cursor,
        "nodes": [{"id": "n1", "approach": "odoo-coding", "approach_kind": "skill"},
                  {"id": cursor, "approach": approach, "approach_kind": kind}]}), encoding="utf-8")
    time.sleep(0.05)
    result = {"type": "user", "timestamp": _now(), "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_w", "content": "ok"}]}}
    return rf, [json.dumps(call), json.dumps(result)]


# --------------------------------------------------------------------------- registration

def test_recovery_is_registered_for_the_compact_source_only_and_steering_for_pre_compact():
    hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
    start = hooks["SessionStart"]
    mine = [e for e in start if any("recover-after-compaction.sh" in h["command"] for h in e["hooks"])]
    assert len(mine) == 1 and mine[0].get("matcher") == "compact"
    assert [e for e in start if "matcher" in e] == mine
    pre = [h["command"] for e in hooks["PreCompact"] for h in e["hooks"]]
    assert len(pre) == 1 and "steer-compaction.sh" in pre[0]


# --------------------------------------------------------------------------- recovery notice

def test_a_session_with_no_facts_gets_the_static_notice(tmp_path):
    ctx = _notice(_run(RECOVER, _payload(), _env(tmp_path)))
    assert "Skill in progress" not in ctx
    assert "Other plugin skills" not in ctx
    assert "Run in progress" not in ctx
    assert "SKILL.md" not in ctx
    assert ctx.startswith("[odoo-ai-agents]")


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "fork"])
def test_other_session_sources_get_no_notice(source, tmp_path):
    r = _run(RECOVER, _payload(source), _env(tmp_path))
    assert r.returncode == 0 and r.stdout == ""


@pytest.mark.parametrize("stdin_text", ["", "{not json", "not json at all"])
def test_empty_or_malformed_input_never_blocks_the_session(stdin_text, tmp_path):
    for hook in (RECOVER, STEER):
        r = _run(hook, stdin_text, _env(tmp_path))
        assert r.returncode == 0
    assert _run(RECOVER, stdin_text, _env(tmp_path)).stdout == ""


@needs_jq
def test_the_transcript_names_the_skills_used_and_the_latest_is_in_progress(tmp_path):
    t = _transcript(tmp_path, [
        _skill_call("odoo-ai-agents:odoo-instance", "a"),
        _command_record("git-toolkit:git-ops"),
        _skill_call("vault-capture", "b"),
        _skill_call("odoo-ai-agents:odoo-instance", "c"),
        _skill_call("odoo-ai-agents:odoo-coding", "d"),
    ])
    ctx = _notice(_run(RECOVER, _payload(session_id="s-none", transcript_path=str(t)), _env(tmp_path)))
    assert "Skill in progress: odoo-ai-agents:odoo-coding " in ctx
    others = ctx.split("Other plugin skills used earlier: ")[1].split(" - ")[0]
    assert others == "git-toolkit:git-ops, odoo-ai-agents:odoo-instance"
    assert "vault-capture" not in ctx
    assert "SKILL.md" not in ctx


@needs_jq
def test_the_other_skills_list_is_capped_and_the_notice_stays_under_the_cut(tmp_path):
    lines = [_skill_call(f"odoo-ai-agents:odoo-skill-{i}", f"id{i}") for i in range(300)]
    t = _transcript(tmp_path, lines)
    ctx = _notice(_run(RECOVER, _payload(session_id="s-big", transcript_path=str(t)), _env(tmp_path)))
    assert "odoo-skill-299" in ctx and "odoo-skill-0," not in ctx
    assert len(ctx) < 2000


@needs_jq
def test_the_run_this_session_owns_is_named_and_its_node_skill_is_in_progress(tmp_path):
    rf, run_lines = _owned_run(tmp_path)
    t = _transcript(tmp_path, [_skill_call("odoo-ai-agents:odoo-instance", "a"), *run_lines])
    env = _env(tmp_path, ODOO_AI_WORKTREE_DIR=str(tmp_path / "isolate"))
    ctx = _notice(_run(RECOVER, _payload(session_id="s-run", transcript_path=str(t), cwd=str(tmp_path)), env))
    assert f"Run in progress: r42 at {rf}, node n2 (odoo-test-writing)" in ctx
    assert "Skill in progress: odoo-ai-agents:odoo-test-writing " in ctx
    assert "Other plugin skills used earlier: odoo-ai-agents:odoo-instance " in ctx


@needs_jq
def test_a_run_node_that_is_not_a_skill_leaves_the_latest_skill_in_progress(tmp_path):
    _, run_lines = _owned_run(tmp_path, cursor="n2", approach="odoo-code-reviewer", kind="agent")
    t = _transcript(tmp_path, [_skill_call("odoo-ai-agents:odoo-coding", "a"), *run_lines])
    env = _env(tmp_path, ODOO_AI_WORKTREE_DIR=str(tmp_path / "isolate"))
    ctx = _notice(_run(RECOVER, _payload(session_id="s-agent", transcript_path=str(t), cwd=str(tmp_path)), env))
    assert "Skill in progress: odoo-ai-agents:odoo-coding " in ctx
    assert "node n2 (odoo-code-reviewer)" in ctx


@needs_jq
def test_a_run_another_session_wrote_is_not_named(tmp_path):
    _, _ = _owned_run(tmp_path)
    t = _transcript(tmp_path, [_skill_call("odoo-ai-agents:odoo-coding", "a")])
    env = _env(tmp_path, ODOO_AI_WORKTREE_DIR=str(tmp_path / "isolate"))
    ctx = _notice(_run(RECOVER, _payload(session_id="s-other", transcript_path=str(t), cwd=str(tmp_path)), env))
    assert "Run in progress" not in ctx


# --------------------------------------------------------------------------- steering + state file

@needs_jq
def test_steering_prints_the_instruction_and_records_what_recovery_reads(tmp_path):
    rf, run_lines = _owned_run(tmp_path)
    t = _transcript(tmp_path, [_skill_call("odoo-ai-agents:odoo-instance", "a"), *run_lines])
    env = _env(tmp_path, ODOO_AI_WORKTREE_DIR=str(tmp_path / "isolate"))
    pre = json.dumps({"hook_event_name": "PreCompact", "trigger": "auto", "custom_instructions": "",
                      "session_id": "s-steer", "transcript_path": str(t), "cwd": str(tmp_path)})
    r = _run(STEER, pre, env)
    assert r.returncode == 0
    assert r.stdout.startswith("[odoo-ai-agents] Keep in the summary:")
    assert len(r.stdout) < HARNESS_CUT
    state = json.loads((tmp_path / "state" / "compaction" / "s-steer.json").read_text(encoding="utf-8"))
    assert state["skills"] == ["odoo-ai-agents:odoo-instance"]
    assert state["run"]["id"] == "r42" and state["run"]["path"] == str(rf)
    assert state["run"]["cursor"] == "n2"

    # The transcript is gone by the time recovery runs: the state file alone carries the facts.
    t.unlink()
    ctx = _notice(_run(RECOVER, _payload(session_id="s-steer", transcript_path=str(t), cwd=str(tmp_path)), env))
    assert "Run in progress: r42" in ctx
    assert "Skill in progress: odoo-ai-agents:odoo-test-writing " in ctx


@needs_jq
def test_a_corrupt_state_file_falls_back_to_the_transcript(tmp_path):
    d = tmp_path / "state" / "compaction"
    d.mkdir(parents=True)
    (d / "s-bad.json").write_text("{broken", encoding="utf-8")
    t = _transcript(tmp_path, [_skill_call("odoo-ai-agents:odoo-debug", "a")])
    ctx = _notice(_run(RECOVER, _payload(session_id="s-bad", transcript_path=str(t)), _env(tmp_path)))
    assert "Skill in progress: odoo-ai-agents:odoo-debug " in ctx


@pytest.mark.parametrize("pre", [
    json.dumps({"hook_event_name": "PreCompact", "trigger": "manual"}),
    json.dumps({"session_id": "../escape", "transcript_path": "/nonexistent", "cwd": "/nonexistent"}),
    json.dumps({"session_id": "s-nt", "transcript_path": "/nonexistent"}),
])
def test_steering_never_fails_and_always_prints_the_instruction(pre, tmp_path):
    r = _run(STEER, pre, _env(tmp_path))
    assert r.returncode == 0
    assert r.stdout.startswith("[odoo-ai-agents] Keep in the summary:")
    assert not (tmp_path / "escape.json").exists()


def test_steering_survives_an_unwritable_state_root(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    env = _env(tmp_path, ODOO_AI_HOME=str(blocker / "sub"))
    r = _run(STEER, json.dumps({"session_id": "s-ro"}), env)
    assert r.returncode == 0 and r.stdout.startswith("[odoo-ai-agents] Keep in the summary:")


# --------------------------------------------------------------------------- without jq

def _path_without_jq(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("bash", "cat", "dirname", "grep", "awk", "mktemp", "mv", "rm", "mkdir", "find", "stat"):
        src = shutil.which(tool)
        if src:
            (bin_dir / tool).symlink_to(src)
    return str(bin_dir)


def test_without_jq_the_notice_is_the_static_text_and_steering_still_prints(tmp_path):
    env = _env(tmp_path, PATH=_path_without_jq(tmp_path))
    r = _run(RECOVER, _payload(session_id="s1"), env)
    assert r.returncode == 0
    assert r.stdout.startswith("[odoo-ai-agents] The context was just compacted.")
    assert "Skill in progress" not in r.stdout and not r.stdout.lstrip().startswith("{")
    assert _run(RECOVER, _payload("startup"), env).stdout == ""
    s = _run(STEER, json.dumps({"session_id": "s1"}), env)
    assert s.returncode == 0 and s.stdout.startswith("[odoo-ai-agents] Keep in the summary:")
    assert not (tmp_path / "state").exists()
