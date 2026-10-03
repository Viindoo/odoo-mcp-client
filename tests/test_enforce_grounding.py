"""Behavioral guard for hooks/enforce-grounding.sh (SubagentStop grounding enforcement).

These tests protect the BEHAVIOR contract of the hook (ETHOS#11) for its consumer - an
AI subagent (odoo-coder / odoo-frontend-coder / odoo-code-reviewer). Each test states the
business rule it locks in and fails for exactly one reason: that rule changed.

The contract under test:
- BLOCK only the provable lie: artifact claims `grounded: osm` with ZERO mcp__odoo-semantic__*
  calls.
- NOTE (non-blocking) the half-grounded case: backend .py written, OSM called, ORM validators
  skipped.
- NOTE (non-blocking) the SILENT-SKIPPER: backend .py written with zero OSM calls and no
  grounding label. (Deliberately a note, not a block - a block there only manufactures
  unverifiable `grounded: local-source` labels and false-blocks legit pure-python/standalone
  work. The hard quality gate is Odoo's test_lint/test_pylint CI module, not OSM-call-count.)
- PASS (stay out of the way): non-Odoo subagents (self-gate), honest local-source label,
  properly grounded work, and a lie block already given inside the same hook-continued chain
  (a continued stop is still checked; a fresh stop is blocked again).

Run with: python3.11 -m pytest tests/test_enforce_grounding.py -v
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import (block_feedback_record, brief_record, handback_records, model_context,
                      resume_record)

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "plugins" / "odoo-ai-agents" / "hooks" / "enforce-grounding.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("bash") is None,
    reason="enforce-grounding.sh needs jq + bash; absent here (the hook itself degrades to pass)",
)


def _line(role="assistant", content=None):
    return json.dumps({"role": role, "content": content or []})


def _tool_use(name, file_path=None):
    inp = {"file_path": file_path} if file_path else {}
    return {"type": "tool_use", "name": name, "input": inp}


def _text(s):
    return {"type": "text", "text": s}


def _run(tmp_path, transcript_lines, stop_hook_active=False):
    """Invoke the hook with a crafted transcript + stdin; return (rc, parsed_stdout_or_None)."""
    tpath = tmp_path / "transcript.jsonl"
    tpath.write_text("\n".join(transcript_lines) + "\n", encoding="utf-8")
    # The real SubagentStop payload: the subagent's OWN transcript is agent_transcript_path, and
    # transcript_path is the whole session's (an empty decoy here).
    session = tmp_path / "session-transcript.jsonl"
    session.write_text("", encoding="utf-8")
    stdin = json.dumps({"hook_event_name": "SubagentStop", "transcript_path": str(session),
                        "agent_transcript_path": str(tpath), "stop_hook_active": stop_hook_active})
    proc = subprocess.run(
        ["bash", str(HOOK)], input=stdin, capture_output=True, text=True, timeout=20
    )
    out = proc.stdout.strip()
    parsed = json.loads(out) if out else None
    return proc.returncode, parsed


def _note_text(out) -> str:
    """A grounding NOTE's text: it must reach the subagent, the one agent that can still act on it
    before its report reaches the caller (SubagentStop additionalContext)."""
    assert out is not None, "expected a grounding note"
    note = model_context(out, "SubagentStop")
    assert note, out
    return note


def test_hook_exists_and_is_executable_shell():
    assert HOOK.exists(), f"hook not found at {HOOK}"
    assert HOOK.read_text(encoding="utf-8").startswith("#!"), "hook must be a shell script"


def test_lie_is_blocked(tmp_path):
    """Claims `grounded: osm` but made ZERO OSM calls -> the one provable lie -> BLOCK."""
    lines = [
        _line(content=[_tool_use("Write", "models/sale.py")]),
        _line(content=[_text("Done. grounded: osm")]),
    ]
    rc, out = _run(tmp_path, lines)
    assert rc == 0  # hook signals via stdout JSON, not exit code
    assert out is not None and out.get("decision") == "block", (
        "claiming grounded:osm with zero mcp__odoo-semantic__* calls must be blocked"
    )


def test_silent_skipper_gets_a_note_not_a_pass(tmp_path):
    """THE tightening: backend .py + zero OSM + no label must no longer slip through silently."""
    lines = [_line(content=[_tool_use("Write", "models/sale.py")])]
    rc, out = _run(tmp_path, lines)
    assert rc == 0
    assert out is not None, "silent-skipper must produce a note, not a silent pass"
    note = _note_text(out)
    assert "ZERO mcp__odoo-semantic__" in note, note
    # The extra turn's last message is what the caller receives: the note must say so, or the
    # subagent ends on a one-line acknowledgement and the caller loses the report.
    assert "repeating your complete report" in note, note


def test_the_lie_block_tells_the_subagent_to_repeat_its_whole_report(tmp_path):
    """The block buys the subagent one more turn, and its caller receives the message that turn
    ends on in place of the report - so the reason says to repeat the complete report, with the
    relabelled grounding, instead of leaving the caller a one-line acknowledgement."""
    lines = [
        _line(content=[_tool_use("Write", "models/sale.py")]),
        _line(content=[_text("Done. grounded: osm")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is not None and out.get("decision") == "block", out
    assert "repeating your complete report, its continuation block included" in out["reason"], out


def test_silent_skipper_is_not_blocked_even_with_orm_looking_code(tmp_path):
    """A note, never a block - absence of an OSM call is not a provable lie."""
    lines = [_line(content=[_tool_use("Edit", "models/account_move.py")])]
    _, out = _run(tmp_path, lines)
    assert out is not None and out.get("decision") != "block"


def test_half_grounded_gets_a_note(tmp_path):
    """Backend .py written, OSM called, but ORM validators skipped -> non-blocking note."""
    lines = [
        _line(content=[_tool_use("mcp__odoo-semantic__model_inspect")]),
        _line(content=[_tool_use("Write", "models/sale.py")]),
    ]
    _, out = _run(tmp_path, lines)
    assert "ORM validators" in _note_text(out)


def test_a_note_after_a_delivered_handback_buys_no_turn(tmp_path):
    """A report already delivered through SubagentHandback is final - nothing the subagent writes
    now reaches its caller, and no SubagentStop channel reaches anyone else - so the note is not
    emitted at all: it must never buy the subagent another turn."""
    lines = [_line(content=[_tool_use("Write", "models/sale.py")]), *handback_records("DONE")]
    _, out = _run(tmp_path, lines)
    assert out is None, f"a note after a final report still produced output: {out!r}"


def test_honest_local_source_label_passes_clean(tmp_path):
    """Backend .py + zero OSM but an explicit `grounded: local-source` label -> pass, no note."""
    lines = [
        _line(content=[_tool_use("Write", "models/sale.py")]),
        _line(content=[_text("OSM not indexed here. grounded: local-source (not OSM-indexed)")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is None, "an honest local-source label must not be nagged"


def test_properly_grounded_passes_clean(tmp_path):
    """OSM calls made AND validators run AND claims osm -> fully grounded -> pass."""
    lines = [
        _line(content=[_tool_use("mcp__odoo-semantic__model_inspect")]),
        _line(content=[_tool_use("mcp__odoo-semantic__validate_depends")]),
        _line(content=[_tool_use("Write", "models/sale.py")]),
        _line(content=[_text("grounded: osm")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is None, "properly grounded work must pass with no note and no block"


def test_non_odoo_subagent_self_gates_to_pass(tmp_path):
    """No OSM, no .py, no grounding vocabulary -> not our concern -> silent pass."""
    lines = [
        _line(content=[_tool_use("Write", "README.md")]),
        _line(content=[_text("Updated the docs.")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is None, "a non-Odoo subagent must be approved silently"


LIE = [
    _line(content=[_tool_use("Write", "models/sale.py")]),
    _line(content=[_text("Done. grounded: osm")]),
]


def test_a_continued_stop_is_still_checked_for_the_lie(tmp_path):
    """A note or block from any SubagentStop hook buys the subagent one more turn, and the report it
    ends that turn on is the one its caller receives. stop_hook_active is true on that stop - the
    lie written there must still be blocked."""
    _, out = _run(tmp_path, LIE, stop_hook_active=True)
    assert out is not None and out.get("decision") == "block", (
        "a lie written in a hook-continued turn reached the caller unchecked"
    )


def test_the_same_lie_block_is_given_once_per_continued_chain(tmp_path):
    """The loop guard: once the subagent was refused with this exact reason, the continued stop of
    that chain with the same lie passes - a block that repeats forever traps the dispatch."""
    _, first = _run(tmp_path, [brief_record(), *LIE])
    assert first is not None and first.get("decision") == "block", first
    _, again = _run(tmp_path, [brief_record(), *LIE, block_feedback_record(first["reason"]),
                                     _line(content=[_text("Done. grounded: osm")])],
                    stop_hook_active=True)
    assert again is None, f"the same block was given twice: {again!r}"


def test_a_lie_in_a_resumed_dispatch_is_blocked_again(tmp_path):
    """Round 1 was refused and fixed. Later the caller resumes the subagent and its NEW report lies
    again: that is a fresh stop (no hook continued it) and a new report, so the same reason must be
    given again - a reason from an earlier round says nothing about this report."""
    _, first = _run(tmp_path, LIE)
    round_two = LIE + [block_feedback_record(first["reason"]),
                       _line(content=[_text("Done. grounded: local-source (not OSM-indexed)")]),
                       resume_record("Add the second field."),
                       _line(content=[_tool_use("Write", "models/sale_extra.py")]),
                       _line(content=[_text("Done. grounded: osm")])]
    _, out = _run(tmp_path, round_two)
    assert out is not None and out.get("decision") == "block", (
        "a lie in a resumed dispatch passed because an earlier round's refusal was in the window"
    )


def test_a_lie_first_met_in_a_note_continued_turn_of_a_later_round_is_blocked(tmp_path):
    """The same reason was given in round 1. In round 2 a note buys the subagent a turn and THAT
    turn lies: the continued stop is inside a chain where this refusal was never given, so it fires
    once."""
    _, first = _run(tmp_path, LIE)
    note = _note_attachment("Grounding note: round two.")
    round_two = LIE + [block_feedback_record(first["reason"]), resume_record("Go on."),
                       _line(content=[_tool_use("Write", "models/sale_extra.py")]),
                       _line(content=[_text("Done.")]), note,
                       _line(content=[_text("Done. grounded: osm")])]
    _, out = _run(tmp_path, round_two, stop_hook_active=True)
    assert out is not None and out.get("decision") == "block", out


def test_an_unreadable_transcript_never_reblocks_a_continued_stop(tmp_path):
    """An unreadable transcript holds no record of what was already said: a first stop is still
    checked (the claim is in the payload's final message), but a hook-continued stop is never
    blocked again - the missing record must not turn into a loop."""
    t = tmp_path / "agent.jsonl"
    t.write_text("\n".join(LIE) + "\n", encoding="utf-8")
    t.chmod(0)
    if os.access(t, os.R_OK):
        pytest.skip("running as a user that reads any file")

    def _stop(active):
        stdin = json.dumps({"hook_event_name": "SubagentStop", "stop_hook_active": active,
                            "transcript_path": str(t), "agent_transcript_path": str(t),
                            "last_assistant_message": "Done. grounded: osm"})
        proc = subprocess.run(["bash", str(HOOK)], input=stdin, capture_output=True, text=True,
                              timeout=20)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout.strip()

    assert '"block"' in _stop(False), "a first stop with the claim must still be checked"
    assert _stop(True) == "", "a continued stop was blocked again with no record to dedupe on"


def _note_attachment(text):
    """How the harness records a SubagentStop additionalContext in the subagent's own transcript."""
    return json.dumps({"type": "attachment", "attachment": {
        "type": "hook_additional_context", "content": [text], "hookName": "SubagentStop",
        "hookEvent": "SubagentStop", "toolUseID": "x"}}, ensure_ascii=False)


def test_a_grounding_note_already_in_the_context_is_not_repeated(tmp_path):
    """A subagent woken again after a stop already holds the note it got at the first stop: the
    same note is not injected again at the next stop - but a lie written in the turn the note
    bought is still blocked, on that continued stop."""
    work = [_line(content=[_tool_use("Write", "models/sale.py")])]
    _, first = _run(tmp_path, work)
    note = _note_text(first)
    _, again = _run(tmp_path, work + [_note_attachment(note), _line("user", [_text("go on")])])
    assert again is None, f"the same grounding note was repeated: {again!r}"
    lie = work + [_note_attachment(note), _line(content=[_text("Done. grounded: osm")])]
    _, out = _run(tmp_path, lie, stop_hook_active=True)
    assert out is not None and out.get("decision") == "block"
