"""Behavioral guard: the plugin's ADVISORY hooks cost context only when they say something new, and
its Stop hooks finish inside their declared timeout on a long session.

Business rules locked in here (each test fails for exactly one of them):

- An advisory a hook injects into the model's context (UserPromptSubmit / PreToolUse
  `additionalContext`, Stop `systemMessage`) is said ONCE per context window. The harness records
  every injected text in the session transcript; when the same text already sits there after the
  last compaction, repeating it adds tokens and nothing else. After a compaction it is said again
  once - compaction drops it from the context. A changed text (a run on another node, another page
  left open) is new and is said.
- detect-intent.sh classifies the USER's prompt only. A prompt the harness submits on its own - a
  background task's <task-notification>, another agent's peer message - is a subagent's report,
  not user intent, and gets no hint at all.
- The Stop hooks finish well inside the timeout hooks.json declares for them on a session with
  thousands of tool calls. A Stop hook that outruns it is cancelled by the harness: the turn end
  stalls for the whole timeout and the hook's own advisory never runs.

Transcript records are written the way the harness writes them (compact JSON, raw UTF-8, one
record per line) - the hooks read the raw lines.

Run with: python3 -m pytest tests/test_advisory_hooks_context_cost.py -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / "plugins" / "odoo-ai-agents"
HOOKS = PLUGIN_ROOT / "hooks"
INTENT_HOOK = HOOKS / "detect-intent.sh"
DELEGATE_HOOK = HOOKS / "remind-delegate.sh"
DRIVE_HOOK = HOOKS / "drive-continuation.sh"
TEARDOWN_HOOK = HOOKS / "enforce-teardown.sh"
HOOKS_JSON = HOOKS / "hooks.json"

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("bash") is None,
    reason="the advisory hooks need jq + bash; without them they degrade to a silent pass",
)

# A prompt that, on its own, earns the OSM hints (engineering domain + an Odoo anchor) and the
# language reminder (not plain English). Odoo vocabulary + a non-English word.
ODOO_PROMPT = "thêm computed field vào odoo module sale"


# --------------------------------------------------------------------------- #
# Harness-shaped transcript records
# --------------------------------------------------------------------------- #
def _dump(rec: dict) -> str:
    return json.dumps(rec, separators=(",", ":"), ensure_ascii=False)


def _user(text: str) -> str:
    return _dump({"type": "user", "message": {"role": "user", "content": text}})


def _context_attachment(event: str, text: str) -> str:
    """How the harness records a hook's additionalContext."""
    return _dump({"type": "attachment", "attachment": {
        "type": "hook_additional_context", "content": [text], "hookName": event,
        "hookEvent": event, "toolUseID": "x"}})


def _system_message_attachment(event: str, text: str) -> str:
    """How the harness records a hook's systemMessage."""
    return _dump({"type": "attachment", "attachment": {
        "type": "hook_system_message", "content": text, "hookName": event, "hookEvent": event,
        "toolUseID": "x"}})


def _compact_boundary() -> str:
    return _dump({"type": "system", "subtype": "compact_boundary",
                  "content": "Conversation compacted", "level": "info"})


def _tool_use(tid: str, name: str, inp: dict) -> str:
    return _dump({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tid, "name": name, "input": inp}]}})


def _tool_result(tid: str, text: str) -> str:
    return _dump({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": text}]}})


def _write(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def _env(tmp_path: Path, **extra) -> dict:
    """Hermetic: throwaway HOME/state root, OSM declared wired (so the OSM hints can fire), no
    override variable leaking in from the invoking shell."""
    e = dict(os.environ)
    for var in ("ODOO_AI_HOME", "ODOO_AI_PROJECT_DIR", "ODOO_AI_WORKTREE_DIR", "ODOO_AI_INSTANCES"):
        e.pop(var, None)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    cfg = tmp_path / "claude.json"
    cfg.write_text(json.dumps({"mcpServers": {"odoo-semantic": {}}}), encoding="utf-8")
    e.update({"HOME": str(home), "ODOO_AI_HOME": str(home / ".odoo-ai"),
              "CLAUDE_CONFIG": str(cfg), "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT)})
    e.update(extra)
    return e


def _run(hook: Path, payload: dict, env: dict, timeout: float = 60) -> tuple[dict | None, float]:
    t0 = time.monotonic()
    proc = subprocess.run(["bash", str(hook)], input=json.dumps(payload), capture_output=True,
                          text=True, env=env, timeout=timeout)
    elapsed = time.monotonic() - t0
    assert proc.returncode == 0, f"{hook.name} must always exit 0: rc={proc.returncode} {proc.stderr}"
    out = proc.stdout.strip()
    return (json.loads(out) if out else None), elapsed


def _ctx(out: dict | None) -> str:
    return "" if out is None else out.get("hookSpecificOutput", {}).get("additionalContext", "")


def _intent(prompt: str, transcript: Path, env: dict) -> str:
    out, _ = _run(INTENT_HOOK, {"hook_event_name": "UserPromptSubmit", "prompt": prompt,
                                "transcript_path": str(transcript)}, env)
    return _ctx(out)


# --------------------------------------------------------------------------- #
# detect-intent.sh (UserPromptSubmit)
# --------------------------------------------------------------------------- #
def test_a_user_prompt_still_gets_its_hints_in_a_fresh_context(tmp_path):
    """Guard for the two rules below: they must not silence a real first prompt."""
    env = _env(tmp_path)
    ctx = _intent(ODOO_PROMPT, _write(tmp_path / "t.jsonl", [_user(ODOO_PROMPT)]), env)
    assert "[OSM]" in ctx and "[Language]" in ctx, ctx


@pytest.mark.parametrize("prompt", [
    "<task-notification>\n<task-id>a1</task-id>\n<status>completed</status>\n<result>Đã sửa odoo "
    "module sale: thêm computed field, test xanh trên v17.</result>\n</task-notification>",
    'Another Claude session sent a message: <agent-message from="a2"> [Subagent report] '
    "odoo module sale migrated to version 18, tests green </agent-message>",
], ids=["task-notification", "peer-agent-message"])
def test_a_prompt_the_harness_submits_gets_no_hint(tmp_path, prompt):
    """A subagent's report delivered as a prompt is not the user asking for Odoo work, and its
    language is the subagent's, not the user's - no Odoo hint and no language reminder."""
    env = _env(tmp_path)
    ctx = _intent(prompt, _write(tmp_path / "t.jsonl", [_user(prompt)]), env)
    assert ctx == "", f"a harness-submitted prompt was classified as user intent: {ctx!r}"


def test_a_hint_already_in_the_context_is_not_repeated(tmp_path):
    """The second Odoo prompt of a session gets nothing the first one already put in context."""
    env = _env(tmp_path)
    t = _write(tmp_path / "t.jsonl", [_user(ODOO_PROMPT)])
    first = _intent(ODOO_PROMPT, t, env)
    assert first
    _write(t, [_user(ODOO_PROMPT), _context_attachment("UserPromptSubmit", first),
               _user(ODOO_PROMPT)])
    again = _intent(ODOO_PROMPT, t, env)
    assert again == "", f"the same hints were injected a second time: {again!r}"


def test_only_the_blocks_not_yet_in_the_context_are_injected(tmp_path):
    """Per block: an English Odoo prompt put the OSM hints in context; a later non-English prompt
    adds the language reminder alone."""
    env = _env(tmp_path)
    english = "add a computed field to the odoo sale module"
    t = _write(tmp_path / "t.jsonl", [_user(english)])
    first = _intent(english, t, env)
    assert "[OSM]" in first and "[Language]" not in first, first
    _write(t, [_user(english), _context_attachment("UserPromptSubmit", first),
               _user(ODOO_PROMPT)])
    second = _intent(ODOO_PROMPT, t, env)
    assert "[Language]" in second, f"the new block was dropped: {second!r}"
    assert "[OSM]" not in second, f"a block already in context was repeated: {second!r}"


def test_a_hint_said_before_a_compaction_is_said_again(tmp_path):
    """Compaction drops earlier injections from the context, so the hint returns once."""
    env = _env(tmp_path)
    t = _write(tmp_path / "t.jsonl", [_user(ODOO_PROMPT)])
    first = _intent(ODOO_PROMPT, t, env)
    _write(t, [_user(ODOO_PROMPT), _context_attachment("UserPromptSubmit", first),
               _compact_boundary(), _user(ODOO_PROMPT)])
    assert _intent(ODOO_PROMPT, t, env) == first


# --------------------------------------------------------------------------- #
# remind-delegate.sh (PreToolUse)
# --------------------------------------------------------------------------- #
def _active_run_env(tmp_path: Path) -> dict:
    isolate = tmp_path / "isolate"
    isolate.mkdir(exist_ok=True)
    (isolate / "run-r1.json").write_text(json.dumps(
        {"run_id": "r1", "status": "NEEDS_NEXT", "cursor": "n1"}), encoding="utf-8")
    return _env(tmp_path, ODOO_AI_WORKTREE_DIR=str(isolate))


def _delegate(tool: str, transcript: Path, env: dict, **extra) -> str:
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(ROOT),
               "tool_input": {"command": "ls"} if tool == "Bash" else {"file_path": "/x.py"},
               "transcript_path": str(transcript), **extra}
    out, _ = _run(DELEGATE_HOOK, payload, env)
    if out is not None:
        assert out["hookSpecificOutput"]["permissionDecision"] == "defer"
    return _ctx(out)


def test_the_mid_run_delegate_reminder_is_said_once_per_context(tmp_path):
    """The main agent's next Bash/Edit/Write calls of the same run add nothing once the reminder is
    in context - whichever heavy tool it is."""
    env = _active_run_env(tmp_path)
    t = _write(tmp_path / "t.jsonl", [_user("go")])
    first = _delegate("Bash", t, env)
    assert "mid-run" in first, "the reminder must still fire on the first heavy call of a run"
    _write(t, [_user("go"), _context_attachment("PreToolUse", first)])
    for tool in ("Bash", "Edit", "Write"):
        assert _delegate(tool, t, env) == "", f"the reminder was repeated on {tool}"
    _write(t, [_user("go"), _context_attachment("PreToolUse", first), _compact_boundary()])
    assert _delegate("Edit", t, env) == first, "after a compaction the reminder returns once"


def test_the_leaf_reminder_is_said_once_per_subagent_context(tmp_path):
    """A role=leaf subagent is reminded once in ITS OWN context, not on every git call."""
    env = _env(tmp_path)
    session = _write(tmp_path / "session.jsonl", [])
    own = _write(tmp_path / "agent.jsonl", [_user("brief")])
    leaf = {"agent_id": "a1", "agent_type": "odoo-backend-coder",
            "agent_transcript_path": str(own),
            "tool_input": {"command": "git commit -am x"}}
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(ROOT),
               "transcript_path": str(session), **leaf}
    first = _ctx(_run(DELEGATE_HOOK, payload, env)[0])
    assert "role=leaf" in first
    _write(own, [_user("brief"), _context_attachment("PreToolUse", first)])
    again = _ctx(_run(DELEGATE_HOOK, payload, env)[0])
    assert again == "", f"the leaf reminder was repeated in the same context: {again!r}"


# --------------------------------------------------------------------------- #
# drive-continuation.sh (Stop)
# --------------------------------------------------------------------------- #
def _drive(transcript: Path, env: dict) -> str:
    out, _ = _run(DRIVE_HOOK, {"hook_event_name": "Stop", "cwd": str(ROOT),
                               "stop_hook_active": False, "transcript_path": str(transcript)}, env)
    return "" if out is None else out.get("systemMessage", "")


def test_the_unfinished_run_reminder_is_said_once_per_run_state(tmp_path):
    """Every later turn end with the run on the same node repeats nothing; the run moving to
    another node is news and is said."""
    isolate = tmp_path / "isolate"
    isolate.mkdir()
    run = isolate / "run-r1.json"
    run.write_text(json.dumps({"run_id": "r1", "status": "NEEDS_NEXT", "cursor": "n1"}),
                   encoding="utf-8")
    env = _env(tmp_path, ODOO_AI_WORKTREE_DIR=str(isolate))
    t = _write(tmp_path / "t.jsonl", [_user("go")])
    first = _drive(t, env)
    assert "'r1'" in first and "n1" in first
    _write(t, [_user("go"), _system_message_attachment("Stop", first), _user("more")])
    assert _drive(t, env) == "", "the same reminder was repeated at the next turn end"
    run.write_text(json.dumps({"run_id": "r1", "status": "NEEDS_NEXT", "cursor": "n2"}),
                   encoding="utf-8")
    moved = _drive(t, env)
    assert "n2" in moved, f"a run that moved on must be reminded again: {moved!r}"


def test_a_run_record_without_run_id_is_named_by_its_file(tmp_path):
    """The reminder names WHICH run is unfinished; a record without run_id is named by its file
    (run-<id>.json), never as '?'."""
    isolate = tmp_path / "isolate"
    isolate.mkdir()
    (isolate / "run-shopfloor-20260901-e822.json").write_text(
        json.dumps({"status": "NEEDS_NEXT", "cursor": "n1"}), encoding="utf-8")
    env = _env(tmp_path, ODOO_AI_WORKTREE_DIR=str(isolate))
    msg = _drive(_write(tmp_path / "t.jsonl", []), env)
    assert "'shopfloor-20260901-e822'" in msg, msg


# --------------------------------------------------------------------------- #
# enforce-teardown.sh (Stop) - browser advisory and run time
# --------------------------------------------------------------------------- #
def _declared_timeout(event: str, script: str) -> float:
    hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"][event]
    for group in hooks:
        for h in group["hooks"]:
            if h["command"].endswith(f'/hooks/{script}"'):
                return float(h["timeout"])
    raise AssertionError(f"{script} is not registered under {event}")


def _teardown(event: str, transcript: Path, env: dict, timeout: float = 120):
    payload = {"hook_event_name": event, "stop_hook_active": False, "cwd": str(ROOT),
               "transcript_path": str(transcript), "last_assistant_message": "done"}
    if event == "SubagentStop":
        payload.update({"agent_transcript_path": str(transcript), "agent_id": "a1"})
    return _run(TEARDOWN_HOOK, payload, env, timeout=timeout)


def test_the_browser_advisory_is_said_once_per_finding(tmp_path):
    """A page the main agent keeps open across turns is reported once, not at every turn end; a
    new finding (another page opened) is said."""
    env = _env(tmp_path)
    page = _tool_use("t1", "mcp__chrome-devtools__new_page", {"url": "http://x/odoo"})
    t = _write(tmp_path / "t.jsonl", [_user("look"), page, _tool_result("t1", "ok")])
    out, _ = _teardown("Stop", t, env)
    first = out["systemMessage"]
    assert "new_page" in first
    base = [_user("look"), page, _tool_result("t1", "ok"), _system_message_attachment("Stop", first)]
    _write(t, base + [_user("next")])
    out, _ = _teardown("Stop", t, env)
    assert out is None, f"the same browser finding was repeated: {out!r}"
    page2 = _tool_use("t2", "mcp__chrome-devtools__new_page", {"url": "http://x/b"})
    _write(t, base + [page2, _tool_result("t2", "ok")])
    out, _ = _teardown("Stop", t, env)
    assert out is not None and "2 new_page" in out["systemMessage"], out


def _long_session(path: Path, calls: int) -> Path:
    """A long main session: `calls` Bash calls with their results, then one chrome-devtools page
    left open (so the hook has an advisory to deliver)."""
    lines = [_user("start")]
    for i in range(calls):
        tid = f"toolu_{i:06d}"
        lines.append(_tool_use(tid, "Bash", {"command": f"echo step {i}"}))
        lines.append(_tool_result(tid, f"step {i} output " + "x" * 200))
    lines.append(_tool_use("toolu_page", "mcp__chrome-devtools__new_page", {"url": "http://x"}))
    lines.append(_tool_result("toolu_page", "ok"))
    return _write(path, lines)


@pytest.mark.parametrize("event", ["Stop", "SubagentStop"])
def test_teardown_finishes_well_inside_its_timeout_on_a_long_session(tmp_path, event):
    """With thousands of tool calls in the transcript, the teardown hook still delivers its
    advisory in a fraction of the timeout hooks.json gives it - a hook the harness cancels never
    delivers anything and stalls the turn end for the full timeout."""
    env = _env(tmp_path)
    t = _long_session(tmp_path / "t.jsonl", calls=6000)
    budget = _declared_timeout(event, "enforce-teardown.sh")
    out, elapsed = _teardown(event, t, env, timeout=budget * 10)
    assert out is not None and "new_page" in out.get("systemMessage", ""), out
    assert elapsed < budget / 2, (
        f"enforce-teardown.sh took {elapsed:.1f}s on {event} with 6000 tool calls; hooks.json "
        f"gives it {budget:.0f}s, and it must finish well inside that")
