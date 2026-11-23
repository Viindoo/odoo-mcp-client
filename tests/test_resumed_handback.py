"""Behavioral guard for the SubagentStop hooks of an agent its launcher RESUMES.

A subagent that reports through `SubagentHandback` delivers ONE report per dispatch. Its launcher
can resume it afterwards with a new request; the answer to that request reaches the launcher only
through a new `SubagentHandback` call (plain end-of-turn text reaches nobody). Two business rules:

  1. Every gate judges the report of the CURRENT dispatch - the work since the launcher's latest
     request. A report delivered for an earlier request is not this turn's report: it neither
     stands in for it (grounding, teardown, strand telemetry read the current one) nor excuses the
     turn (a resumed turn that has delivered nothing is still an undelivered one).
  2. A resumed agent cannot silently end the turn without its answer having travelled: the stop is
     refused once per request, with the way to deliver it (hooks/enforce-resumed-handback.sh). A
     peer request is answered by a message to its sender; only the stop of the turn the request
     started is judged: a message that reached the agent after it had stopped starts a later turn,
     one that reached it while it still worked (a queued_command attachment) does not end the turn.

A launcher request, as a transcript records it (measured on real subagent transcripts): a user
record with `origin.kind` `coordinator` (the main conversation) or `peer` without `handback` (a
nested launcher), unless the peer is an agent this agent launched. Not requests: a peer message
with `handback` (a child's delivered report), a `task-notification`, a hook's feedback.

These tests assert decisions and structured fields only, never the wording of a reason.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from conftest import block_feedback_record, brief_record, handback_records, model_context, resume_record

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / "plugins" / "odoo-ai-agents"
HOOKS = PLUGIN_ROOT / "hooks"
GATE = HOOKS / "enforce-resumed-handback.sh"
GROUNDING = HOOKS / "enforce-grounding.sh"
TEARDOWN = HOOKS / "enforce-teardown.sh"
STATUS = HOOKS / "report-terminal-status.sh"
BGWAIT = HOOKS / "enforce-background-wait.sh"
HOOKS_JSON = HOOKS / "hooks.json"

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("bash") is None,
    reason="the hooks need jq + bash; absent here they degrade to pass",
)

REFUSED = {"success": False, "message": "Nothing was sent: your report was already delivered "
           "(SubagentHandback delivers one report). Use SendMessage for anything further, then stop."}
LAUNCHER = "a0launcher000001"
CHILD = "a1child00000001"


# --------------------------------------------------------------------------- #
# Transcript builders - the record shapes the harness writes
# --------------------------------------------------------------------------- #
def _assistant(*blocks) -> str:
    return json.dumps({"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}})


def _text(s: str) -> str:
    return _assistant({"type": "text", "text": s})


def _call(name: str, inp: dict, tid: str) -> str:
    return _assistant({"type": "tool_use", "id": tid, "name": name, "input": inp})


def _result(tid: str, text: str, *, tur: dict | None = None) -> str:
    rec = {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": [{"type": "text", "text": text}]}]}}
    if tur is not None:
        rec["toolUseResult"] = tur
    return json.dumps(rec)


def _report(status: str = "DONE", extra: str = "") -> str:
    return f"{extra}\n```continuation\nstatus: {status}\nproduced: []\nnext: []\n```"


def _delivered(tid: str, message: str | None = None) -> list[str]:
    return handback_records(message if message is not None else _report(), tid=tid)


def _peer_request(sender: str = LAUNCHER, text: str = "One more thing: re-run the check.") -> str:
    """A message from another agent that is NOT a hand-back: a nested launcher's request."""
    origin = {"kind": "peer", "from": sender, "senderTaskId": sender, "name": "general-purpose",
              "body": text}
    return json.dumps({"type": "user", "isMeta": True, "origin": origin, "message": {
        "role": "user", "content": f"Another Claude session sent a message while you were "
        f"working:\n<agent-message from=\"{sender}\">\n{text}\n</agent-message>"}})


def _peer_handback(sender: str = CHILD) -> str:
    """A child's delivered report, as it reaches its launcher."""
    origin = {"kind": "peer", "from": sender, "senderTaskId": sender, "handback": True,
              "body": "[Subagent hand-back] ..."}
    return json.dumps({"type": "user", "isMeta": True, "origin": origin, "message": {
        "role": "user", "content": "Another Claude session sent a message while you were working: "
        "<agent-message> [Subagent hand-back] the child's report </agent-message>"}})


def _queued_request(sender: str = LAUNCHER) -> str:
    """The same nested-launcher request while the agent was blocked on a synchronous call: an
    attachment record of type queued_command that carries the origin."""
    return json.dumps({"type": "attachment", "attachment": {
        "type": "queued_command", "commandMode": "prompt", "isMeta": True,
        "prompt": "<agent-message>do it again</agent-message>",
        "origin": {"kind": "peer", "from": sender, "senderTaskId": sender}}})


def _notification() -> str:
    return json.dumps({"type": "user", "isMeta": True, "origin": {"kind": "task-notification"},
                       "message": {"role": "user", "content": "[SYSTEM NOTIFICATION - NOT USER "
                                   "INPUT] A background task finished."}})


def _human() -> str:
    """A message a human typed into the agent's transcript view: origin kind `human`."""
    return json.dumps({"type": "user", "origin": {"kind": "human"},
                       "message": {"role": "user", "content": "a question typed in the transcript view"}})


def _queued(origin: dict) -> str:
    """A message that reached an agent still working its turn: the harness records it as an
    attachment of type queued_command that carries the origin (the turn goes on). The same
    messages reaching an agent that had stopped are the user records above."""
    return json.dumps({"type": "attachment", "attachment": {
        "type": "queued_command", "commandMode": "prompt", "isMeta": True,
        "prompt": "<agent-message>queued</agent-message>", "origin": origin}})


def _queued_notification() -> str:
    return _queued({"kind": "task-notification"})


def _queued_handback(sender: str = CHILD) -> str:
    return _queued({"kind": "peer", "from": sender, "senderTaskId": sender, "handback": True})


def _work(tid: str = "toolu_work") -> list[str]:
    """A tool call and its result: the agent is mid-turn, working."""
    return [_call("Bash", {"command": "make test"}, tid), _result(tid, "ok")]


def _block_records(reason: str) -> list[list[str]]:
    """The two shapes a SubagentStop block leaves in the agent's own transcript: a meta user record
    "Stop hook feedback:" + the reason, and a hook_blocking_error attachment (hookEvent
    SubagentStop) carrying the reason. The harness writes either or both."""
    attachment = json.dumps({"type": "attachment", "attachment": {
        "type": "hook_blocking_error", "hookEvent": "SubagentStop", "hookName": "SubagentStop",
        "toolUseID": "toolu_hook", "blockingError": {"blockingError": reason, "command": "gate.sh"}}})
    return [[block_feedback_record(reason)], [attachment], [block_feedback_record(reason), attachment]]


def _gate_reason(tmp_path: Path, lines: list[str]) -> str:
    """The block reason the gate itself gives for a transcript (not asserted on - only recorded)."""
    rc, out, _ = _run(GATE, tmp_path, lines)
    assert rc == 0 and out and out["decision"] == "block"
    return out["reason"]


def _launched_child(child: str = CHILD, tid: str = "toolu_launch") -> list[str]:
    return [_call("Agent", {"prompt": "go", "description": "child"}, tid),
            _result(tid, f"Async agent launched successfully.\nagentId: {child} (internal ID)",
                    tur={"isAsync": True, "status": "async_launched", "agentId": child})]


def _sent(tid: str = "toolu_send") -> list[str]:
    return [_call("SendMessage", {"to": LAUNCHER, "message": "the answer"}, tid),
            _result(tid, "Message sent.")]


# --------------------------------------------------------------------------- #
# One runner for every hook
# --------------------------------------------------------------------------- #
def _seed_ledger(home: Path, leases) -> None:
    runtime = home / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "leases.json").write_text(json.dumps({"schema_version": 2, "leases": leases}),
                                         encoding="utf-8")


def _live_lease(token: str, run_id: str = "run-r") -> dict:
    now = int(time.time())
    return {"token": token, "mode": "exclusive", "series": "17.0", "db_name": "odoo_17_0",
            "drop_on_release": True, "ports": [8170],
            "owner": {"host": socket.gethostname(), "pid": None, "run_id": run_id,
                      "started_at": now},
            "ttl_s": 7200, "heartbeat_at": now, "_pg": {"host": "localhost", "user": "odoo"}}


def _acquired(token: str, run_id: str = "run-r") -> list[str]:
    cmd = ("python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py acquire --series 17.0 "
           f"--mode ephemeral --ports 1 --run-id {run_id}")
    return [_call("Bash", {"command": cmd}, "toolu_acq"),
            _result("toolu_acq", f"ALLOC_TOKEN={token}\nALLOC_RUN_ID={run_id}\n")]


def _run(script: Path, tmp_path: Path, lines: list[str], *, active: bool = False,
         leases=None, payload_extra: dict | None = None) -> tuple[int, dict | None, Path]:
    """Run one hook on the agent's own transcript; return (rc, parsed stdout or None, home)."""
    home = tmp_path / "home"
    _seed_ledger(home, leases or [])
    tpath = tmp_path / "agent.jsonl"
    tpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    session = tmp_path / "session.jsonl"
    session.write_text("", encoding="utf-8")
    payload = {"hook_event_name": "SubagentStop", "stop_hook_active": active,
               "transcript_path": str(session), "agent_transcript_path": str(tpath)}
    payload.update(payload_extra or {})
    env = dict(os.environ)
    for var in ("CLAUDE_PID", "CLAUDE_CODE_SESSION_ID", "ODOO_AI_INSTANCES", "ODOO_AI_PROJECT_DIR",
                "ODOO_AI_WORKTREE_DIR"):
        env.pop(var, None)
    env.update({"CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT), "ODOO_AI_HOME": str(home),
                "HOME": str(home), "ODOO_AI_SESSION_ANCHOR": "none"})
    proc = subprocess.run(["bash", str(script)], input=json.dumps(payload), capture_output=True,
                          text=True, timeout=30, env=env)
    out = proc.stdout.strip()
    return proc.returncode, (json.loads(out) if out else None), home


def _blocks(script, tmp_path, lines, **kw) -> bool:
    rc, out, _ = _run(script, tmp_path, lines, **kw)
    assert rc == 0
    return bool(out) and out.get("decision") == "block"


def _strands(home: Path) -> int:
    f = home / "telemetry" / "strand-events.log"
    return len(f.read_text(encoding="utf-8").splitlines()) if f.exists() else 0


# =========================================================================== #
# The gate: a resumed agent cannot end the turn without its answer delivered
# =========================================================================== #
def test_the_gate_is_registered_under_subagent_stop_only():
    reg = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
    cmds = {ev: [h["command"] for g in groups for h in g.get("hooks", [])] for ev, groups in reg.items()}
    assert any(GATE.name in c for c in cmds["SubagentStop"])
    assert not any(GATE.name in c for ev, cs in cmds.items() if ev != "SubagentStop" for c in cs)


def test_a_first_dispatch_is_never_stopped(tmp_path):
    """Nothing was resumed: a first dispatch ending in plain text, or after its hand-back, is
    left to the other gates."""
    assert not _blocks(GATE, tmp_path, [brief_record(), _text("all done")])
    assert not _blocks(GATE, tmp_path, [brief_record(), *_delivered("toolu_1")])


@pytest.mark.parametrize("request_record", [resume_record("Fix the second finding."),
                                            _peer_request(), _queued_request()],
                         ids=["coordinator", "nested-launcher-peer", "queued-command-attachment"])
def test_a_resumed_turn_that_ends_in_text_is_stopped(tmp_path, request_record):
    """The incident: the report was delivered, the launcher resumed the agent, and the agent ended
    the resumed turn in plain text - an answer that reaches nobody."""
    lines = [brief_record(), *_delivered("toolu_1"), request_record, _text("Here is the answer.")]
    assert _blocks(GATE, tmp_path, lines)


def test_a_resumed_turn_that_delivers_its_answer_passes(tmp_path):
    lines = [brief_record(), *_delivered("toolu_1"), resume_record(), *_delivered("toolu_2"),
             _text("done")]
    assert not _blocks(GATE, tmp_path, lines)


def test_a_denied_handback_is_not_a_delivery(tmp_path):
    """A hand-back a PreToolUse hook denied delivered nothing: the turn still ends without its
    answer having travelled."""
    denied = handback_records(_report(), tid="toolu_2", denied=True)
    lines = [brief_record(), *_delivered("toolu_1"), resume_record(), *denied, _text("ok")]
    assert _blocks(GATE, tmp_path, lines)


def test_a_handback_refused_as_delivered_then_a_message_sent_passes(tmp_path):
    """The refusal tells the agent to send the answer with the messaging tool: doing so after the
    refusal is the answer travelling."""
    refused = handback_records(_report(), tid="toolu_2", outcome=REFUSED)
    ok = [brief_record(), *_delivered("toolu_1"), resume_record(), *refused, *_sent(), _text("ok")]
    assert not _blocks(GATE, tmp_path, ok)


def test_a_refused_handback_without_a_message_after_it_is_stopped(tmp_path):
    refused = handback_records(_report(), tid="toolu_2", outcome=REFUSED)
    base = [brief_record(), *_delivered("toolu_1"), resume_record()]
    assert _blocks(GATE, tmp_path, [*base, *refused, _text("ok")])
    # A message sent BEFORE the refusal is not the answer the refusal asks for.
    assert _blocks(GATE, tmp_path, [*base, *_sent(), *refused, _text("ok")])


@pytest.mark.parametrize("wake", [_notification(), _peer_handback(),
                                  block_feedback_record("a hook said something")],
                         ids=["task-notification", "child-handback", "hook-feedback"])
def test_a_wake_that_is_not_a_launcher_request_is_left_alone(tmp_path, wake):
    """After the delivered report the agent is woken by its own background task, a late child
    hand-back or a hook: those end in a one-line acknowledgement and must not be forced into a
    second report."""
    lines = [brief_record(), *_delivered("toolu_1"), wake, _text("noted")]
    assert not _blocks(GATE, tmp_path, lines)


_PEER_ASKED = [brief_record(), *_delivered("toolu_1"), _peer_request()]
_PEER_ANSWERED = [*_PEER_ASKED, *_sent("toolu_s1"), _text("answered the peer")]


def test_a_peer_request_answered_by_a_message_to_its_sender_passes(tmp_path):
    """The answer to a nested launcher's request is a message to that launcher: it needs no refused
    hand-back first, and the stop that follows is not blocked."""
    assert not _blocks(GATE, tmp_path, _PEER_ANSWERED)


@pytest.mark.parametrize("wake", [_notification(), _human(), _peer_handback(LAUNCHER)],
                         ids=["task-notification", "human-message", "peer-handback"])
def test_a_wake_after_an_answered_peer_request_is_never_blocked(tmp_path, wake):
    """After the peer was answered the agent is woken by something that is not a request (its
    background task, a human, the peer's own hand-back): the one-line acknowledgement it ends in is
    not an unanswered request, so the two agents cannot resume each other forever."""
    assert not _blocks(GATE, tmp_path, [*_PEER_ANSWERED, wake, _text("noted")])
    # Answered more than once, then woken: still nothing to ask for.
    assert not _blocks(GATE, tmp_path, [*_PEER_ANSWERED, *_sent("toolu_s2"), wake, _text("noted")])


@pytest.mark.parametrize("request_record", [resume_record("Fix the second finding."), _peer_request()],
                         ids=["coordinator", "peer"])
@pytest.mark.parametrize("wake", [_notification(), _human(), _peer_handback(LAUNCHER)],
                         ids=["task-notification", "human-message", "peer-handback"])
def test_only_the_stop_of_the_requests_own_turn_is_judged(tmp_path, request_record, wake):
    """An unanswered request is judged where its turn ends; a message that reaches the agent after
    it had stopped (a user record with an origin) starts a later turn this gate never judges for
    the older request."""
    base = [brief_record(), *_delivered("toolu_1"), request_record]
    assert _blocks(GATE, tmp_path, [*base, _text("no answer")])
    assert not _blocks(GATE, tmp_path, [*base, _text("no answer"), wake, _text("noted")])


def test_a_peer_request_never_answered_is_stopped(tmp_path):
    assert _blocks(GATE, tmp_path, [*_PEER_ASKED, _text("no answer")])


def test_a_message_to_someone_other_than_the_requests_sender_is_not_the_answer(tmp_path):
    other = [_call("SendMessage", {"to": "a9stranger", "message": "fyi"}, "toolu_o"),
             _result("toolu_o", "Message sent.")]
    assert _blocks(GATE, tmp_path, [*_PEER_ASKED, *other, _text("done")])
    # A message sent BEFORE the request is not its answer either.
    assert _blocks(GATE, tmp_path, [brief_record(), *_delivered("toolu_1"), *_sent("toolu_s0"),
                                    _peer_request(), _text("done")])


@pytest.mark.parametrize("shape", [0, 1, 2], ids=["feedback-record", "blocking-error-attachment", "both"])
@pytest.mark.parametrize("request_record", [resume_record("Fix the second finding."), _peer_request()],
                         ids=["coordinator", "peer"])
def test_a_request_is_blocked_once_across_stops(tmp_path, request_record, shape):
    """The record this gate's own block leaves in the transcript (either shape the harness writes)
    marks the request as blocked: the next stop of the same request passes."""
    stopped = [brief_record(), *_delivered("toolu_1"), request_record, _text("no answer")]
    reason = _gate_reason(tmp_path, stopped)
    after_block = [*stopped, *_block_records(reason)[shape], _text("still no answer")]
    assert not _blocks(GATE, tmp_path, after_block)
    # A second stop after further work (a tool call in between) is the same request: still passes.
    assert not _blocks(GATE, tmp_path, [*after_block, *_work(), _text("again no answer")])


def test_another_gates_block_does_not_use_up_the_request(tmp_path):
    """Only this gate's own block counts: a different hook's feedback after the request leaves the
    unanswered request to be blocked once."""
    other = [block_feedback_record("a teardown gate said something"), *_block_records("another reason")[1]]
    lines = [brief_record(), *_delivered("toolu_1"), resume_record(), _text("no answer"), *other,
             _text("still no answer")]
    assert _blocks(GATE, tmp_path, lines)


def test_a_new_request_after_a_block_is_judged_again(tmp_path):
    """The once-only rule belongs to one request: a later request is a new one."""
    stopped = [*_PEER_ASKED, _text("no answer")]
    reason = _gate_reason(tmp_path, stopped)
    lines = [*stopped, *_block_records(reason)[0], _text("still no answer"), resume_record("and another"),
             _text("no answer")]
    assert _blocks(GATE, tmp_path, lines)


@pytest.mark.parametrize("request_record", [resume_record("Fix the second finding."), _peer_request()],
                         ids=["coordinator", "peer"])
@pytest.mark.parametrize("wake", [_queued_notification(), _queued_handback(), _queued_handback(LAUNCHER),
                                  _queued({"kind": "human"})],
                         ids=["task-notification", "child-handback", "peer-handback", "human-message"])
def test_a_message_delivered_mid_turn_does_not_excuse_an_unanswered_request(tmp_path, request_record, wake):
    """The agent works the request, a background task or a child reports while it is still working,
    and it then ends the turn in plain text: the launcher is still waiting for its answer."""
    lines = [brief_record(), *_launched_child(), *_delivered("toolu_1"), request_record, *_work(),
             wake, *_work("toolu_work2"), _text("no answer")]
    assert _blocks(GATE, tmp_path, lines)


@pytest.mark.parametrize("wake", [_queued_notification(), _queued_handback()],
                         ids=["task-notification", "child-handback"])
def test_a_request_answered_around_a_mid_turn_message_passes(tmp_path, wake):
    """The same mid-turn transcript, with the answer delivered (a hand-back for a coordinator
    request, a message to the sender for a peer request): nothing to ask for."""
    head = [brief_record(), *_launched_child(), *_delivered("toolu_1")]
    coordinator = [*head, resume_record(), *_work(), wake, *_delivered("toolu_2"), _text("done")]
    assert not _blocks(GATE, tmp_path, coordinator)
    peer = [*head, _peer_request(), *_work(), wake, *_sent("toolu_s1"), _text("done")]
    assert not _blocks(GATE, tmp_path, peer)


def test_a_mid_turn_message_then_a_stop_after_a_block_passes(tmp_path):
    """Blocked once for the request, then more mid-turn messages and another plain-text stop: the
    request has had its one block."""
    head = [brief_record(), *_delivered("toolu_1"), resume_record(), *_work(), _queued_notification(),
            _text("no answer")]
    reason = _gate_reason(tmp_path, head)
    lines = [*head, *_block_records(reason)[0], *_work("toolu_work2"), _queued_notification(),
             _text("still no answer")]
    assert not _blocks(GATE, tmp_path, lines)


def test_a_message_from_an_agent_it_launched_is_not_a_launcher_request(tmp_path):
    """A child that answers by message (not by hand-back) is not the launcher asking for more."""
    lines = [brief_record(), *_launched_child(), *_delivered("toolu_1"), _peer_request(CHILD),
             _text("noted")]
    assert not _blocks(GATE, tmp_path, lines)
    # The same message from an agent it did not launch is a request.
    other = [brief_record(), *_launched_child(), *_delivered("toolu_1"), _peer_request("a9stranger"),
             _text("noted")]
    assert _blocks(GATE, tmp_path, other)


def test_the_latest_request_decides_not_the_first(tmp_path):
    """Answered once, resumed again, text again: the second request is unanswered."""
    lines = [brief_record(), *_delivered("toolu_1"), resume_record("first"), *_delivered("toolu_2"),
             resume_record("second"), _text("answer in text")]
    assert _blocks(GATE, tmp_path, lines)


def test_a_request_with_no_report_before_it_is_not_a_resume(tmp_path):
    """A message that reaches the agent during its first dispatch, before it has reported, is part
    of that dispatch: the agent is not known to report through SubagentHandback."""
    lines = [brief_record(), resume_record("while you work"), _text("done in text")]
    assert not _blocks(GATE, tmp_path, lines)


def test_an_agent_that_reports_as_final_text_is_never_stopped(tmp_path):
    """No SubagentHandback anywhere in its transcript: its report travels as its final message,
    resumed or not."""
    lines = [brief_record(), _text("first report"), resume_record("again"), _text("second report")]
    assert not _blocks(GATE, tmp_path, lines)


def test_a_stop_a_hook_already_continued_passes(tmp_path):
    """Bounded: the stop that follows the block (or any hook's block) is never blocked again."""
    lines = [brief_record(), *_delivered("toolu_1"), resume_record(), _text("answer")]
    assert _blocks(GATE, tmp_path, lines)
    assert not _blocks(GATE, tmp_path, lines, active=True)


def test_a_hand_back_call_without_its_result_yet_is_not_judged(tmp_path):
    """The transcript snapshot at SubagentStop can end at the hand-back call: uncertainty passes."""
    call = _call("SubagentHandback", {"message": _report()}, "toolu_2")
    lines = [brief_record(), *_delivered("toolu_1"), resume_record(), call]
    assert not _blocks(GATE, tmp_path, lines)


def test_an_unreadable_transcript_passes(tmp_path):
    rc, out, _ = _run(GATE, tmp_path, ["not json", "{also not"], payload_extra={})
    assert rc == 0 and out is None
    rc, out, _ = _run(GATE, tmp_path, [], payload_extra={"agent_transcript_path": str(tmp_path / "nope")})
    assert rc == 0 and out is None


# =========================================================================== #
# The other gates judge the report of the CURRENT dispatch
# =========================================================================== #
OSM_LIE = _report(extra="grounded: osm")


def test_grounding_reads_the_report_of_the_current_dispatch(tmp_path):
    """The resumed turn's own report claims OSM grounding with no OSM call: blocked, although the
    report delivered for the first request carried no label."""
    lines = [brief_record(), *_delivered("toolu_1"), resume_record(),
             *_delivered("toolu_2", OSM_LIE)]
    assert _blocks(GROUNDING, tmp_path, lines)


def test_grounding_does_not_replay_a_stale_report_on_a_later_dispatch(tmp_path):
    """The first report's label line is not what the launcher receives for the second request."""
    lines = [brief_record(), *_delivered("toolu_1", OSM_LIE), resume_record(),
             *_delivered("toolu_2", _report(extra="grounded: ungrounded - nothing checked"))]
    assert not _blocks(GROUNDING, tmp_path, lines)
    # And with no report yet for the new request, the stale label is not re-read either.
    lines = [brief_record(), *_delivered("toolu_1", OSM_LIE), resume_record(), _text("Working.")]
    assert not _blocks(GROUNDING, tmp_path, lines)


_PY = _call("Write", {"file_path": "models/sale.py"}, "toolu_w")


def test_a_resumed_turn_without_a_delivered_report_still_gets_the_grounding_note(tmp_path):
    """The earlier delivery no longer exempts the turn: backend Python written in the resumed turn
    with no report delivered for it is noted; once the turn delivered its report, nothing."""
    base = [brief_record(), *_delivered("toolu_1"), resume_record(), _PY]
    _, out, _ = _run(GROUNDING, tmp_path, [*base, _text("Done.")])
    assert out and model_context(out, "SubagentStop")
    _, out, _ = _run(GROUNDING, tmp_path, [*base, *_delivered("toolu_2")])
    assert out is None


def test_a_resumed_turns_note_closes_like_a_first_dispatch_note(tmp_path):
    """What a note tells the agent about its caller depends on whether THIS dispatch's report was
    delivered. Before it is delivered the closing sentence is the one of any undelivered dispatch,
    whatever an earlier dispatch did."""
    _, first, _ = _run(GROUNDING, tmp_path, [brief_record(), _PY, _text("Done.")])
    _, resumed, _ = _run(GROUNDING, tmp_path, [brief_record(), *_delivered("toolu_1"),
                                               resume_record(), _PY, _text("Done.")])
    assert first and resumed
    assert model_context(resumed, "SubagentStop") == model_context(first, "SubagentStop")


TOKEN = "ab" * 16


def _lease_lines(report_1: str, report_2: str | None) -> list[str]:
    lines = [brief_record(), *_acquired(TOKEN), *_delivered("toolu_1", report_1), resume_record()]
    if report_2 is not None:
        lines += _delivered("toolu_2", report_2)
    return lines


def _forwarding(token: str) -> str:
    return (f"```continuation\nstatus: NEEDS_NEXT\nnext:\n  - skill: odoo-coding\n"
            f"    inputs: {{INSTANCE_HANDLE: {{lease_token: {token}, run_id: run-r}}}}\n```")


def test_teardown_judges_the_current_dispatchs_report_for_the_lease(tmp_path):
    """The first report forwarded the lease to a named catcher; the resumed turn's report does not:
    the lease is again nobody's, and the gate blocks."""
    lines = _lease_lines(_forwarding(TOKEN), _report("DONE"))
    assert _blocks(TEARDOWN, tmp_path, lines, leases=[_live_lease(TOKEN)])


def test_teardown_accepts_a_handoff_made_in_the_current_dispatch(tmp_path):
    """The first report forwarded nothing; the resumed turn's report forwards the lease: handed
    off, so passes."""
    lines = _lease_lines(_report("DONE"), _forwarding(TOKEN))
    assert not _blocks(TEARDOWN, tmp_path, lines, leases=[_live_lease(TOKEN)])


def test_teardown_before_the_resumed_turn_reports_does_not_read_the_stale_handoff(tmp_path):
    """No report yet for the new request: the first report's forward is not the handoff of this
    dispatch, so the live lease still blocks the stop."""
    lines = _lease_lines(_forwarding(TOKEN), None) + [_text("working on the new request")]
    assert _blocks(TEARDOWN, tmp_path, lines, leases=[_live_lease(TOKEN)])


def _strand_count(tmp_path: Path, name: str, lines: list[str]) -> int:
    d = tmp_path / name
    d.mkdir()
    _, _, home = _run(STATUS, d, lines)
    return _strands(home)


def test_terminal_status_is_judged_on_the_current_dispatchs_report(tmp_path):
    """The strand counter reads the report the launcher received for THIS request."""
    text_end = [brief_record(), *_delivered("toolu_1"), resume_record(), _text("no fence here")]
    assert _strand_count(tmp_path, "a", text_end) == 1, (
        "a resumed turn ending in plain text without a status is a strand")
    clean = [brief_record(), *_delivered("toolu_1", _report("BLOCKED")), resume_record(),
             *_delivered("toolu_2", _report("DONE"))]
    assert _strand_count(tmp_path, "b", clean) == 0
    stale_ok = [brief_record(), *_delivered("toolu_1", _report("DONE")), resume_record(),
                *_delivered("toolu_2", "finished, no fence")]
    assert _strand_count(tmp_path, "c", stale_ok) == 1, (
        "the first report's fence must not stand in for the second report")
    first_dispatch = [brief_record(), _text("no fence here")]
    assert _strand_count(tmp_path, "d", first_dispatch) == 1


_PAGE = _call("mcp__chrome-devtools__new_page", {"url": "http://127.0.0.1:8069/odoo"}, "toolu_pg")


def test_a_browser_advisory_in_a_resumed_turn_closes_like_a_first_dispatch_one(tmp_path):
    """The advisory's closing sentence tells the agent what its caller receives; before this
    dispatch's report is delivered it is the sentence of an undelivered dispatch."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _, first, _ = _run(TEARDOWN, tmp_path / "a", [brief_record(), _PAGE, _text("done")])
    _, resumed, _ = _run(TEARDOWN, tmp_path / "b", [brief_record(), *_delivered("toolu_1"),
                                                    resume_record(), _PAGE, _text("done")])
    assert first and resumed
    assert model_context(resumed, "SubagentStop") == model_context(first, "SubagentStop")


_BG = [_call("Bash", {"command": "sleep 90", "run_in_background": True}, "toolu_bg"),
       _result("toolu_bg", "Command running in background with ID: bg7k2x. Output is being "
               "written to: /srv/run/tasks/bg7k2x.output. You will be notified when it completes.")]


def test_the_background_wait_block_closes_like_a_first_dispatch_one(tmp_path):
    extra = {"agent_id": "a-me", "agent_type": "general-purpose", "background_tasks": [
        {"id": "bg7k2x", "type": "shell", "status": "running", "description": "build",
         "command": "sleep 90"}]}
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _, first, _ = _run(BGWAIT, tmp_path / "a", [brief_record(), *_BG, _text("waiting")],
                       payload_extra=extra)
    _, resumed, _ = _run(BGWAIT, tmp_path / "b", [brief_record(), *_delivered("toolu_1"),
                                                  resume_record(), *_BG, _text("waiting")],
                         payload_extra=extra)
    assert first and resumed and first.get("decision") == "block" == resumed.get("decision")
    assert resumed["reason"] == first["reason"]
