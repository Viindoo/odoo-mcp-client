"""Behavioral guard: a subagent's report delivered through the `SubagentHandback` tool.

A subagent may hand its report back with a TOOL CALL - `SubagentHandback({"message": "<report>"})`
- instead of as its last assistant text. Observed live (Claude Code, a throwaway plugin logging the
hook payloads):
  - The report reaches the caller the moment the call runs, BEFORE the subagent's turn ends - so
    before SubagentStop. A second call returns `success: false` ("already delivered ... Use
    SendMessage").
  - A PreToolUse `permissionDecision: deny` on SubagentHandback stops delivery: the call comes back
    as an error tool_result and the caller receives NO message; the next, allowed call delivers.
  - The PreToolUse payload carries `agent_id` / `agent_type` and the SESSION `transcript_path`, but
    no `agent_transcript_path`; the subagent's own transcript is
    `<session transcript minus .jsonl>/subagents/agent-<agent_id>.jsonl`.
  - The harness writes each content block of one assistant turn as its OWN record (a thinking
    record, then a text record), so the last assistant RECORD can hold no text at all.

The business rules protected here:
  1. The caller never receives a report while a lease the subagent obtained itself is still live,
     unless that report forwards INSTANCE_HANDLE to a named catcher
     (hooks/block-handback-with-live-lease.sh, PreToolUse).
  2. Every hook that reads a subagent's terminal status or forwarded handle reads the report the
     caller ACTUALLY received - the delivered handback message, else the final message - from the subagent's OWN transcript (hooks/final-report.sh).

Run with: python3 -m pytest tests/test_handback_gate.py -v
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import handback_records

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_enforce_teardown import _Ledger, _contract_exit_set  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / "plugins" / "odoo-ai-agents"
HOOKS = PLUGIN_ROOT / "hooks"
GATE = HOOKS / "block-handback-with-live-lease.sh"
TEARDOWN = HOOKS / "enforce-teardown.sh"
STATUS_HOOK = HOOKS / "report-terminal-status.sh"
GROUNDING = HOOKS / "enforce-grounding.sh"
HOOKS_JSON = HOOKS / "hooks.json"
VOCAB_JSON = PLUGIN_ROOT / "generator" / "skill_tool_deps.json"
MCP = "mcp__plugin_odoo-ai-agents_odoo-local__"
AGENT_ID = "a0c0ffee0handback"

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("bash") is None,
    reason="the hooks need jq + bash; absent here (each hook itself degrades to pass)",
)


# --------------------------------------------------------------------------- #
# Transcript records, in the shapes the harness writes
# --------------------------------------------------------------------------- #
_SEQ = iter(range(1, 10**9))


def _rec(role, block, **extra):
    rec = {"type": role, "message": {"role": role, "content": [block]}}
    rec.update(extra)
    return json.dumps(rec)


def _use(name, inp):
    tid = f"toolu_hb_{next(_SEQ):06d}"
    return tid, _rec("assistant", {"type": "tool_use", "id": tid, "name": name, "input": inp})


def _result(tid, content, *, is_error=False, tool_use_result=None):
    block = {"type": "tool_result", "tool_use_id": tid, "content": content}
    if is_error:
        block["is_error"] = True
    extra = {"toolUseResult": tool_use_result} if tool_use_result is not None else {}
    return _rec("user", block, **extra)


def _thinking():
    return _rec("assistant", {"type": "thinking", "thinking": "", "signature": "x"})


def _text(s):
    return _rec("assistant", {"type": "text", "text": s})


def _brief(s):
    return json.dumps({"type": "user", "message": {"role": "user", "content": s}})


def _reminder():
    return json.dumps({"type": "user", "isMeta": True, "message": {"role": "user", "content": (
        "<system-reminder>\nYour final report is delivered through SubagentHandback.\n"
        "</system-reminder>")}})


def _attachment():
    return json.dumps({"type": "attachment", "attachment": {"type": "skill_listing"}})


def _mcp_acquire(tok, run_id="run-R"):
    tid, use = _use(MCP + "lease_acquire", {"series": "17.0", "mode": "ephemeral",
                                            "run_id": run_id, "cwd": "/w"})
    payload = {"lease": {"token": tok, "run_id": run_id, "db_name": "odoo_17_0_t_x"}}
    return [use, _result(tid, [{"type": "text", "text": json.dumps(payload)}],
                         tool_use_result={"structuredContent": payload})]


def _cont(status=None, handle_tok=None):
    body = "```continuation\n"
    if status:
        body += f"status: {status}\n"
    if handle_tok:
        body += ("next:\n  - skill: odoo-coding\n"
                 f"    inputs: {{INSTANCE_HANDLE: {{lease_token: {handle_tok}, run_id: run-R}}}}\n")
    else:
        body += "produced: []\nnext: []\n"
    return body + "```"


def _report(status="DONE", handle_tok=None, prose=""):
    return f"Built the instance.\n{prose}\n{_cont(status, handle_tok)}"


_DELIVERED = {"success": True, "message": "Report delivered to your caller."}
_ALREADY = {"success": False, "message": (
    "Nothing was sent: your report was already delivered (SubagentHandback delivers one "
    "report). Use SendMessage for anything further, then stop.")}


def _handback(message, outcome=_DELIVERED, *, denied=False):
    """A SubagentHandback call and its harness answer: delivered, refused as a second call, or
    denied by a PreToolUse hook (an error tool_result - nothing was sent)."""
    return handback_records(message, tid=f"toolu_hb_{next(_SEQ):06d}", outcome=outcome,
                            denied=denied)


# --------------------------------------------------------------------------- #
# Runners
# --------------------------------------------------------------------------- #
@pytest.fixture
def ledger(tmp_path):
    led = _Ledger(tmp_path)
    try:
        yield led
    finally:
        led.close()


def _hook_env(ledger=None, home=None):
    env = dict(os.environ)
    env.pop("CLAUDE_PID", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    if ledger is not None:
        env.update(ledger.env())
    elif home is not None:
        env["ODOO_AI_HOME"] = str(home)
        env["HOME"] = str(home)
        env["ODOO_AI_SESSION_ANCHOR"] = "none"
    return env


def _run_gate(tmp_path, lines, message, *, ledger=None, agent=True, layout="derived",
              tool="SubagentHandback"):
    """The PreToolUse payload as observed live: agent_id/agent_type + the SESSION transcript_path,
    no agent_transcript_path - the agent's own transcript is found through the on-disk layout."""
    session = tmp_path / "sess.jsonl"
    session.write_text("", encoding="utf-8")
    payload = {"session_id": "s", "transcript_path": str(session), "cwd": str(tmp_path),
               "permission_mode": "auto", "hook_event_name": "PreToolUse", "tool_name": tool,
               "tool_input": {"message": message}, "tool_use_id": "toolu_gate"}
    if agent:
        payload.update({"agent_id": AGENT_ID, "agent_type": "general-purpose"})
    if layout == "derived":
        tpath = tmp_path / "sess" / "subagents" / f"agent-{AGENT_ID}.jsonl"
        tpath.parent.mkdir(parents=True, exist_ok=True)
        tpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    proc = subprocess.run(["bash", str(GATE)], input=json.dumps(payload), capture_output=True,
                          text=True, timeout=30, env=_hook_env(ledger, tmp_path / "home"))
    assert proc.returncode == 0, f"a PreToolUse gate must always exit 0: {proc.stderr}"
    return proc


def _denied(proc):
    out = json.loads(proc.stdout)
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse" and hso["permissionDecision"] == "deny"
    return hso["permissionDecisionReason"]


def _passed(proc):
    assert not proc.stdout.strip(), f"expected a silent pass, got: {proc.stdout!r}"


def _run_stop(tmp_path, hook, lines, *, session_lines=(), ledger=None, home=None,
              last_message=None):
    """A real SubagentStop payload: the subagent's own transcript is agent_transcript_path; the
    session's (parent plus siblings) is transcript_path; `last_assistant_message` is the text of
    the agent's final message."""
    agent = tmp_path / "agent.jsonl"
    agent.write_text("\n".join(lines) + "\n", encoding="utf-8")
    session = tmp_path / "session.jsonl"
    session.write_text("\n".join(session_lines) + "\n", encoding="utf-8")
    payload = {"hook_event_name": "SubagentStop", "stop_hook_active": False, "cwd": str(tmp_path),
               "transcript_path": str(session), "agent_transcript_path": str(agent),
               "agent_id": AGENT_ID, "agent_type": "general-purpose"}
    if last_message is not None:
        payload["last_assistant_message"] = last_message
    proc = subprocess.run(["bash", str(hook)], input=json.dumps(payload), capture_output=True,
                          text=True, timeout=30, env=_hook_env(ledger, home or tmp_path / "home"))
    out = proc.stdout.strip()
    return proc.returncode, (json.loads(out) if out else None)


def _statuses():
    return json.loads(VOCAB_JSON.read_text(encoding="utf-8"))["vocabulary"]["continuation_status"]


# --------------------------------------------------------------------------- #
# 1. The PreToolUse gate: no report leaves while a lease the subagent obtained is live
# --------------------------------------------------------------------------- #
def test_a_handback_while_holding_a_live_lease_is_denied_before_it_is_delivered(tmp_path, ledger):
    """THE DEFECT: the subagent acquired a lease and handed its report back without giving the
    lease back. Delivered, the caller holds a report while the instance leaks; the SubagentStop
    block then fires only after the fact. The handback itself must be refused."""
    tok = ledger.acquire("run-R")
    reason = _denied(_run_gate(tmp_path, [_brief("provision"), *_mcp_acquire(tok)],
                               _report("DONE"), ledger=ledger))
    assert tok in reason, "the refusal must name the live lease"
    assert "status: DONE" in reason, "the refusal must quote the status the report declared"
    assert "NOT delivered" in reason and "SubagentHandback again" in reason, (
        "the agent must learn that nothing reached its caller and that it hands back AGAIN after "
        "taking an exit - otherwise it assumes the report is lost and stops"
    )
    assert f'lease_release {{lease_token: "{tok}", run_id: "run-R"}}' in reason


def test_the_gate_names_every_exit_the_teardown_contract_declares(tmp_path, ledger):
    """Lockstep with snippets/resource-teardown-contract.md T1, asserted on the rendered deny: an
    agent told only about `release` destroys a database it could have parked or handed off."""
    tok = ledger.acquire("run-R")
    reason = _denied(_run_gate(tmp_path, [*_mcp_acquire(tok)], _report("DONE"), ledger=ledger))
    missing = sorted(e for e in _contract_exit_set() if e not in reason)
    assert not missing, f"the handback deny does not name {missing}"


@pytest.mark.parametrize("status", [*_statuses(), None])
def test_the_gate_is_status_blind(tmp_path, ledger, status):
    """Like the SubagentStop gate, the question is "is a live lease still held with nobody named to
    take it", never the status: a BLOCKED report still names its catcher, and a report with no
    status at all leaks worst."""
    tok = ledger.acquire("run-R")
    reason = _denied(_run_gate(tmp_path, [*_mcp_acquire(tok)], _report(status), ledger=ledger))
    if status is None:
        assert "NO `status`" in reason


def test_a_handback_that_forwards_instance_handle_in_its_fence_passes(tmp_path, ledger):
    """Exit 3: the report names a catcher for the live instance - it may go out."""
    tok = ledger.acquire("run-R")
    _passed(_run_gate(tmp_path, [*_mcp_acquire(tok)], _report("NEEDS_NEXT", handle_tok=tok),
                      ledger=ledger))


def test_an_instance_handle_mentioned_outside_the_fence_forwards_nothing(tmp_path, ledger):
    tok = ledger.acquire("run-R")
    prose = f"INSTANCE_HANDLE: lease_token {tok} - the caller can have it."
    _denied(_run_gate(tmp_path, [*_mcp_acquire(tok)], _report("DONE", prose=prose),
                      ledger=ledger))


def _mark_parked(ledger, tok):
    """The park keys a real `park` leaves on the row (its server pid is gone, parked_at set) - a
    ledger-only lease has no server process for the allocator's own `park` to stop."""
    reg_path = ledger.home / "runtime" / "leases.json"
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    for row in reg["leases"]:
        if row["token"] == tok:
            row["parked_at"] = int(time.time())
            row["park_ttl_s"] = 86400
            row["owner"]["pid"] = None
    reg_path.write_text(json.dumps(reg), encoding="utf-8")


@pytest.mark.parametrize("verb", ["release", "park"])
def test_a_handback_after_the_lease_was_given_back_passes(tmp_path, ledger, verb):
    """Exits 1 and 2: once the ledger no longer shows the lease live, the report goes out."""
    tok = ledger.acquire("run-R")
    if verb == "release":
        p = ledger.alloc("release", tok, "--run-id", "run-R")
        assert p.returncode == 0, f"test setup: release failed: {p.stderr}"
    else:
        _mark_parked(ledger, tok)
    _passed(_run_gate(tmp_path, [*_mcp_acquire(tok)], _report("DONE"), ledger=ledger))


def test_a_consumer_of_a_forwarded_lease_may_hand_back_freely(tmp_path, ledger):
    """A lease that arrived in the brief is its provider's; the consumer obtained nothing."""
    tok = ledger.acquire("run-R")
    lines = [_brief(f"Test on INSTANCE_HANDLE lease_token {tok} run_id run-R")]
    _passed(_run_gate(tmp_path, lines, _report("DONE"), ledger=ledger))


def test_the_main_context_and_other_tools_are_never_denied(tmp_path, ledger):
    tok = ledger.acquire("run-R")
    lines = [*_mcp_acquire(tok)]
    _passed(_run_gate(tmp_path, lines, _report("DONE"), ledger=ledger, agent=False))
    _passed(_run_gate(tmp_path, lines, _report("DONE"), ledger=ledger, tool="SendMessage"))


def test_an_unreadable_agent_transcript_fails_open_and_says_so(tmp_path, ledger):
    proc = _run_gate(tmp_path, [], _report("DONE"), ledger=ledger, layout="none")
    _passed(proc)
    assert "fail open" in proc.stderr


def test_the_gate_is_wired_to_subagenthandback_only():
    hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    groups = [g for g in hooks
              if any(GATE.name in h.get("command", "") for h in g.get("hooks", []))]
    assert groups, "hooks.json must register the handback gate under PreToolUse"
    for g in groups:
        assert re.fullmatch(g["matcher"], "SubagentHandback")
        for other in ("Bash", "Agent", "SendMessage", MCP + "lease_release"):
            assert not re.fullmatch(g["matcher"], other), f"the matcher must not reach {other}"


# --------------------------------------------------------------------------- #
# 2. The SubagentStop teardown gate reads the report the caller received
# --------------------------------------------------------------------------- #
def test_the_teardown_gate_reads_the_status_inside_a_delivered_handback(tmp_path, ledger):
    """The pre-fix gate read text blocks only: a report whose fence carried `status: DONE`, handed
    back through the tool, was reported as having NO status. The block must quote the real status
    and, since a second handback is refused, never send the agent to hand back again."""
    tok = ledger.acquire("run-R")
    lines = [_reminder(), _brief("provision"), *_mcp_acquire(tok), _thinking(),
             *_handback(_report("DONE")), _attachment(), _thinking(),
             _text("Handback delivered successfully.")]
    _, out = _run_stop(tmp_path, TEARDOWN, lines, ledger=ledger)
    assert out and out.get("decision") == "block"
    assert "status: DONE" in out["reason"] and "NO `status`" not in out["reason"]
    assert "ALREADY handed back" in out["reason"], (
        "a second handback is refused - the block must not send the agent to hand back again"
    )


def test_a_handback_that_forwarded_instance_handle_satisfies_the_teardown_gate(tmp_path, ledger):
    tok = ledger.acquire("run-R")
    lines = [*_mcp_acquire(tok), *_handback(_report("NEEDS_NEXT", handle_tok=tok)),
             _text("Handed back.")]
    _, out = _run_stop(tmp_path, TEARDOWN, lines, ledger=ledger)
    assert out is None or out.get("decision") != "block"


def test_a_lease_obtained_after_the_handback_is_blocked_with_release_or_park(tmp_path, ledger):
    """The report is already out and a second handback is refused, so its fence is final: the
    block must say so and point at release or park, not at handing back again."""
    tok = ledger.acquire("run-R")
    lines = [*_handback(_report("DONE")), *_mcp_acquire(tok), _text("Acquired after reporting.")]
    _, out = _run_stop(tmp_path, TEARDOWN, lines, ledger=ledger, last_message="Acquired after.")
    assert out and out.get("decision") == "block"
    assert "ALREADY handed back" in out["reason"] and "release or park" in out["reason"]
    assert "status: DONE" in out["reason"], "the fence read is the delivered report's"


@pytest.mark.parametrize("outcome", ["denied", "refused"])
def test_a_denied_or_refused_handback_is_not_the_report(tmp_path, ledger, outcome):
    """A handback the PreToolUse gate denied, or a second one the harness refused, never reached
    the caller - the handle inside it forwards nothing, and the final text is the report."""
    tok = ledger.acquire("run-R")
    message = _report("NEEDS_NEXT", handle_tok=tok)
    hb = _handback(message, denied=True) if outcome == "denied" else _handback(message, _ALREADY)
    lines = [*_mcp_acquire(tok), *hb, _text(_report("DONE"))]
    _, out = _run_stop(tmp_path, TEARDOWN, lines, ledger=ledger)
    assert out and out.get("decision") == "block", f"a {outcome} handback was taken as the report"
    assert "status: DONE" in out["reason"]


def test_a_handle_forwarded_in_an_earlier_turn_the_caller_never_received_forwards_nothing(
        tmp_path, ledger):
    """Without a handback the caller receives the FINAL turn's text only; a fence left in an
    earlier turn is not part of the report, so its INSTANCE_HANDLE names no catcher."""
    tok = ledger.acquire("run-R")
    lines = [*_mcp_acquire(tok), _text(_report("NEEDS_NEXT", handle_tok=tok)),
             *_use_and_result("Bash", {"command": "ls"}), _text("All done.")]
    _, out = _run_stop(tmp_path, TEARDOWN, lines, ledger=ledger)
    assert out and out.get("decision") == "block"
    assert "NO `status`" in out["reason"]


def _use_and_result(name, inp):
    tid, use = _use(name, inp)
    return [use, _result(tid, "ok")]


# Every way the refusal could still offer the handoff or a fresh report after the report is out.
# A delivered SubagentHandback is final (R3 in snippets/spawner-completion-contract.md): a second
# handback is refused, no fence can be amended, and no message may carry the report instead.
_POST_HANDBACK_DEAD_ENDS = {
    "the handoff exit": r"\bhandoff\b|\bexit 3\b|\bexits? 1 and 2\b",
    "forwarding INSTANCE_HANDLE now": r"\bforward\w*\s+(`)?INSTANCE_HANDLE",
    "reporting a (new) continuation block": r"report\s+a\s+`?continuation`?\s+block",
    "calling SubagentHandback again": r"SubagentHandback again",
}


@pytest.mark.parametrize("when", ["lease-before-handback", "lease-after-handback"])
def test_after_a_delivered_handback_the_block_offers_only_release_or_park(tmp_path, ledger, when):
    """THE DEFECT (review finding 1): once the report was delivered, the block's closing sentence
    said only release or park can clear the lease - but the shared text above it still offered
    exit 3 (forward INSTANCE_HANDLE) and "report a continuation block", neither of which can reach
    the caller any more. An agent obeying the incoherent text writes a second report nobody
    receives, or reaches for SendMessage, which R3 forbids."""
    tok = ledger.acquire("run-R")
    if when == "lease-before-handback":
        lines = [*_mcp_acquire(tok), *_handback(_report("DONE")), _text("Handed back.")]
    else:
        lines = [*_handback(_report("DONE")), *_mcp_acquire(tok), _text("Acquired after.")]
    _, out = _run_stop(tmp_path, TEARDOWN, lines, ledger=ledger)
    assert out and out.get("decision") == "block"
    reason = out["reason"]
    offered = sorted(name for name, pat in _POST_HANDBACK_DEAD_ENDS.items()
                     if re.search(pat, reason, re.I))
    assert not offered, f"a delivered report is final, yet the block still offers: {offered}"
    assert f'lease_release {{lease_token: "{tok}", run_id: "run-R"}}' in reason
    assert f'lease_park {{lease_token: "{tok}", run_id: "run-R"}}' in reason
    assert re.search(r"\bno other message may carry it\b", reason), (
        "the harness's own refusal of a second handback points at a messaging tool - the block "
        "must say that route is closed too, or the agent follows the harness into an R3 breach"
    )


def test_before_any_handback_the_block_still_offers_all_three_exits(tmp_path, ledger):
    """The complement: with no report delivered yet the handoff is still open and must be named -
    dropping it here would push a teardown-denied agent into a bare stopped-run report."""
    tok = ledger.acquire("run-R")
    _, out = _run_stop(tmp_path, TEARDOWN, [*_mcp_acquire(tok)], ledger=ledger,
                       last_message=_report("DONE"))
    assert out and out.get("decision") == "block"
    reason = out["reason"]
    assert not sorted(e for e in _contract_exit_set() if e not in reason)
    assert "Exit 3 is always available" in reason


# --------------------------------------------------------------------------- #
# Per-lease handoff (review finding 2): forwarding ONE handle clears ONE lease
# --------------------------------------------------------------------------- #
def _cont_forwarding(status, *toks, extra=""):
    body = f"```continuation\nstatus: {status}\n{extra}next:\n"
    for t in toks:
        body += ("  - skill: odoo-coding\n    reason: test on it\n"
                 f"    inputs: {{INSTANCE_HANDLE: {{lease_token: {t}, run_id: run-R}}}}\n")
    return body + "```"


def test_forwarding_one_handle_does_not_clear_a_second_live_lease_at_handback(tmp_path, ledger):
    """THE DEFECT: the forwarded-handle check was a plain grep for INSTANCE_HANDLE, so forwarding
    lease A cleared lease B as well - B then leaked with nobody named to take it."""
    a, b = ledger.acquire("run-R"), ledger.acquire("run-R")
    reason = _denied(_run_gate(tmp_path, [*_mcp_acquire(a), *_mcp_acquire(b)],
                               "Built two.\n" + _cont_forwarding("NEEDS_NEXT", a), ledger=ledger))
    assert b in reason, "the lease nobody was handed must be named"
    assert a not in reason, "the forwarded lease has a named catcher and is not this refusal's"


def test_forwarding_every_live_lease_passes_the_handback(tmp_path, ledger):
    a, b = ledger.acquire("run-R"), ledger.acquire("run-R")
    _passed(_run_gate(tmp_path, [*_mcp_acquire(a), *_mcp_acquire(b)],
                      "Built two.\n" + _cont_forwarding("NEEDS_NEXT", a, b), ledger=ledger))


def test_forwarding_a_handle_to_some_other_lease_clears_nothing(tmp_path, ledger):
    """An INSTANCE_HANDLE naming a lease this agent did not obtain (its parent's, a stale one)
    hands nobody the lease that is actually live."""
    tok = ledger.acquire("run-R")
    reason = _denied(_run_gate(tmp_path, [*_mcp_acquire(tok)],
                               "Done.\n" + _cont_forwarding("NEEDS_NEXT", "f0" * 16),
                               ledger=ledger))
    assert tok in reason


def test_a_token_quoted_in_the_fence_outside_next_is_not_forwarded(tmp_path, ledger):
    """The handoff lives in next.inputs - the one field a driver turns into the catcher's brief. A
    token quoted in blocked_reason (with a handle for some other lease in next) names no catcher."""
    tok = ledger.acquire("run-R")
    extra = f"blocked_reason: could not release {tok}\n"
    reason = _denied(_run_gate(tmp_path, [*_mcp_acquire(tok)],
                               "Stuck.\n" + _cont_forwarding("BLOCKED", "f0" * 16, extra=extra),
                               ledger=ledger))
    assert tok in reason


def test_forwarding_one_handle_does_not_clear_a_second_live_lease_at_subagent_stop(tmp_path,
                                                                                     ledger):
    a, b = ledger.acquire("run-R"), ledger.acquire("run-R")
    _, out = _run_stop(tmp_path, TEARDOWN, [*_mcp_acquire(a), *_mcp_acquire(b)], ledger=ledger,
                       last_message="Built two.\n" + _cont_forwarding("NEEDS_NEXT", a))
    assert out and out.get("decision") == "block"
    assert b in out["reason"] and a not in out["reason"]
    _, out = _run_stop(tmp_path, TEARDOWN, [*_mcp_acquire(a), *_mcp_acquire(b)], ledger=ledger,
                       last_message="Built two.\n" + _cont_forwarding("NEEDS_NEXT", a, b))
    assert out is None or out.get("decision") != "block"


# --------------------------------------------------------------------------- #
# 3. report-terminal-status.sh / enforce-grounding.sh
# --------------------------------------------------------------------------- #
def _strand_log(home):
    f = home / "telemetry" / "strand-events.log"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def test_a_status_handed_back_through_the_tool_is_not_a_strand(tmp_path):
    home = tmp_path / "home"
    lines = [*_handback(_report("DONE")), _thinking()]
    rc, _ = _run_stop(tmp_path, STATUS_HOOK, lines, home=home)
    assert rc == 0 and _strand_log(home) == ""


def test_a_final_turn_split_across_records_is_read_whole(tmp_path):
    """The harness writes a turn's text and thinking blocks as separate records; a trailing
    thinking-only record is not a final turn without a status."""
    home = tmp_path / "home"
    lines = [*_use_and_result("Bash", {"command": "ls"}), _thinking(), _text(_report("DONE")),
             _thinking()]
    _run_stop(tmp_path, STATUS_HOOK, lines, home=home)
    assert _strand_log(home) == ""


def test_the_strand_counter_judges_the_subagents_own_final_turn(tmp_path):
    home = tmp_path / "home"
    _run_stop(tmp_path, STATUS_HOOK, [_text("I will continue later.")],
              session_lines=[_text(_report("DONE"))], home=home)
    assert "signature=S1" in _strand_log(home)


def test_a_grounding_claim_inside_a_handback_is_checked(tmp_path):
    """`grounded: osm` asserted in the handed-back report with zero OSM calls is the same lie as
    in a text block - and a label is never only on a report's first line."""
    lines = [*_handback("Added the field.\nChecked it.\ngrounded: osm\n" + _cont("DONE"))]
    _, out = _run_stop(tmp_path, GROUNDING, lines)
    assert out and out.get("decision") == "block"


def test_a_grounding_claim_on_a_later_line_of_a_text_block_is_checked(tmp_path):
    _, out = _run_stop(tmp_path, GROUNDING, [_text("Added the field.\ngrounded: osm\n" + _cont("DONE"))])
    assert out and out.get("decision") == "block"


def test_grounding_never_credits_the_sessions_osm_calls_to_the_subagent(tmp_path):
    """The parent's OSM calls live in the session transcript; the subagent that claims OSM
    grounding with none of its own is still lying."""
    _, osm_use = _use("mcp__odoo-semantic__model_inspect", {"model": "sale.order"})
    _, out = _run_stop(tmp_path, GROUNDING, [_text("grounded: osm")], session_lines=[osm_use])
    assert out and out.get("decision") == "block"


# --------------------------------------------------------------------------- #
# 4. The final message the transcript file does not hold yet
#
# Observed live: when SubagentStop runs, the subagent's transcript file on disk ends at the record
# BEFORE its final assistant message (a snapshot taken by the hook held the last tool_result and
# an attachment, not the final text). The payload's `last_assistant_message` carries that text; a
# hook reading only the file never sees the report's fence.
# --------------------------------------------------------------------------- #
def _flushed_so_far(tok):
    return [_brief("provision"), *_mcp_acquire(tok), *_use_and_result("Bash", {"command": "ls"}),
            _attachment()]


def test_the_teardown_gate_reads_a_final_message_the_file_does_not_hold_yet(tmp_path, ledger):
    tok = ledger.acquire("run-R")
    _, out = _run_stop(tmp_path, TEARDOWN, _flushed_so_far(tok), ledger=ledger,
                       last_message=_report("NEEDS_NEXT", handle_tok=tok))
    assert out is None or out.get("decision") != "block", (
        "the final message forwards INSTANCE_HANDLE - blocking it is the false NO-status block"
    )


def test_the_teardown_gate_quotes_the_status_of_a_final_message_the_file_lacks(tmp_path, ledger):
    tok = ledger.acquire("run-R")
    _, out = _run_stop(tmp_path, TEARDOWN, _flushed_so_far(tok), ledger=ledger,
                       last_message=_report("BLOCKED"))
    assert out and out.get("decision") == "block"
    assert "status: BLOCKED" in out["reason"] and "NO `status`" not in out["reason"]


def test_a_final_message_the_file_lacks_is_not_a_strand(tmp_path):
    home = tmp_path / "home"
    _run_stop(tmp_path, STATUS_HOOK, [_brief("go"), *_use_and_result("Bash", {"command": "ls"})],
              home=home, last_message=_report("DONE"))
    assert _strand_log(home) == ""


def test_a_grounding_claim_in_a_final_message_the_file_lacks_is_checked(tmp_path):
    _, out = _run_stop(tmp_path, GROUNDING, [_brief("go")],
                       last_message="Added the field.\ngrounded: osm")
    assert out and out.get("decision") == "block"
