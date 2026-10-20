"""A lease a child handed back UP to a subagent is that subagent's to give back.

A coder-like subagent launches `odoo-instance-ops`; the child's report names the lease it
provisioned. From then on the coder holds that lease like one it acquired itself: it may not end
its turn or hand its report back while the lease is live and unforwarded, and it clears the gate
by releasing, parking or forwarding the lease in its own closed continuation fence. The main
session and a pure consumer of a forwarded handle stay ungated.

Run with: python3 -m pytest tests/test_handed_up_lease_teardown.py -v
"""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_handback_gate import (  # noqa: E402,F401
    GATE, TEARDOWN, _brief, _denied, _passed, _report, _result, _run_gate, _run_stop, _use,
    ledger,
)

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("bash") is None,
    reason="the hooks need jq + bash; absent here (each hook itself degrades to pass)",
)


def _child_hands_up(tok, run_id="run-R"):
    """The coder launched `odoo-instance-ops`; its synchronous report names the lease it took."""
    tid, use = _use("Agent", {"description": "provision", "prompt": "build the node's database"})
    block = ("Built.\n```instance-ops\nop: create-instance\nseries: 17.0\n"
             f"lease_token: {tok}\nrun_id: {run_id}\nstatus: created\n```")
    return [use, _result(tid, [{"type": "text", "text": block}])]


def _stop_blocked(tmp_path, ledger, lines, report):
    _, out = _run_stop(tmp_path, TEARDOWN, lines, ledger=ledger, last_message=report)
    return out


def test_a_coder_that_ends_holding_a_lease_its_child_handed_up_is_blocked(tmp_path, ledger):
    tok = ledger.acquire("run-R")
    lines = [_brief("build the node"), *_child_hands_up(tok)]
    report = _report("DONE")
    out = _stop_blocked(tmp_path, ledger, lines, report)
    assert out and out.get("decision") == "block", "a handed-up live lease is the coder's leak"
    assert tok in out["reason"]
    reason = _denied(_run_gate(tmp_path, lines, report, ledger=ledger))
    assert tok in reason, "the handback must be refused too, before the report reaches the caller"


def test_a_coder_that_released_the_handed_up_lease_may_end_and_hand_back(tmp_path, ledger):
    tok = ledger.acquire("run-R")
    p = ledger.alloc("release", tok, "--run-id", "run-R")
    assert p.returncode == 0, f"test setup: release failed: {p.stderr}"
    lines = [_brief("build the node"), *_child_hands_up(tok)]
    report = _report("DONE")
    out = _stop_blocked(tmp_path, ledger, lines, report)
    assert out is None or out.get("decision") != "block"
    _passed(_run_gate(tmp_path, lines, report, ledger=ledger))


def test_a_coder_that_forwards_the_handed_up_lease_to_its_caller_may_end_and_hand_back(
        tmp_path, ledger):
    tok = ledger.acquire("run-R")
    lines = [_brief("build the node"), *_child_hands_up(tok)]
    report = _report("NEEDS_NEXT", handle_tok=tok)
    out = _stop_blocked(tmp_path, ledger, lines, report)
    assert out is None or out.get("decision") != "block"
    _passed(_run_gate(tmp_path, lines, report, ledger=ledger))


def test_a_child_echoing_a_handle_the_coder_was_given_does_not_make_it_the_coders(
        tmp_path, ledger):
    """The lease arrived DOWN in the coder's brief; the child reports it unchanged. Holding the
    coder to a lease it may not release would deadlock it."""
    tok = ledger.acquire("run-R")
    lines = [_brief(f"Build on INSTANCE_HANDLE lease_token: {tok} run_id: run-R"),
             *_child_hands_up(tok)]
    report = _report("DONE")
    out = _stop_blocked(tmp_path, ledger, lines, report)
    assert out is None or out.get("decision") != "block"
    _passed(_run_gate(tmp_path, lines, report, ledger=ledger))


def test_the_main_session_is_never_held_to_a_handed_up_lease(tmp_path, ledger):
    tok = ledger.acquire("run-R")
    lines = [_brief("build the node"), *_child_hands_up(tok)]
    _passed(_run_gate(tmp_path, lines, _report("DONE"), ledger=ledger, agent=False))
