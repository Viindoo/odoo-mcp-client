"""Behavioral guard for hooks/enforce-teardown.sh + hooks/session-end-gc.sh (L1.6 + L1.3).

These protect the BEHAVIOR contract of the resource-teardown enforcement (ETHOS#11) for its
consumer - an AI subagent that provisions browser pages and/or Odoo instances. Each test states
the business rule it locks in and fails for exactly one reason: that rule changed.

The NAMED DESIGN RULE under test (a future contributor must not invert it):
- INSTANCES (detached OS processes that outlive the session) = HARD BLOCK, and only on the
  PROVABLE ledger lie: a lease THIS subagent obtained itself (its token, read from its OWN
  transcript - `agent_transcript_path` - never correlated by the run id it shares with its parent
  and siblings) that the allocator's verdict still reports live and non-shared, at a turn end that
  does not forward INSTANCE_HANDLE inside its continuation fence (the named-catcher handoff
  exception). The gate is STATUS-BLIND: DONE, NEEDS_NEXT, BLOCKED, NEEDS_CONTEXT, an out-of-enum
  value, and a turn carrying no machine-readable status at all are gated alike. SubagentStop only.
- BROWSERS (pages/recordings that die WITH the session's MCP server) = ADVISORY ONLY, keyed on the
  fuzzy transcript open/close count, on BOTH SubagentStop and Stop. NEVER `decision: block`. On
  SubagentStop the finding rides additionalContext - the channel the subagent that drove the pages
  reads (a systemMessage reaches no model); on the main session's Stop it is a systemMessage for
  the user, because the main session often keeps a page open on purpose for the user.
- Every SubagentStop text addressed to the subagent - a block reason as much as a note - ends by
  telling it what its caller receives: the extra turn's last message replaces its report, so it
  repeats its complete report; a coordinator that only waits for its teammate keeps waiting; after
  a SubagentHandback nothing more reaches the caller.

Everything degrades to a silent pass on uncertainty (this is the one hard gate; a false block halts
real work, so it prefers a false-negative over a false-positive).

Run with: python3 -m pytest tests/test_enforce_teardown.py -v
"""
import io
import json
import re
import shutil
import socket
import subprocess
import time
import tokenize
from pathlib import Path

import pytest

from conftest import block_feedback_record, brief_record, model_context, resume_record

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / "plugins" / "odoo-ai-agents"
HOOK = PLUGIN_ROOT / "hooks" / "enforce-teardown.sh"
GC_HOOK = PLUGIN_ROOT / "hooks" / "session-end-gc.sh"
ALLOC = PLUGIN_ROOT / "scripts" / "lib" / "allocator.py"
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"
VOCAB_JSON = PLUGIN_ROOT / "generator" / "skill_tool_deps.json"


def _vocab(key):
    """A vocabulary list from the machine SSOT (generator/skill_tool_deps.json), so the
    status cases below track the enum instead of restating a hand-copied copy of it."""
    return json.loads(VOCAB_JSON.read_text(encoding="utf-8"))["vocabulary"][key]


def _declared_non_completion_statuses():
    """The continuation `status` values that are NOT a completion claim - the closed enum
    minus DONE. A subset of these (the STOP_REPORT tier below) is what the instance gate lets
    past; the rest are gated exactly like DONE."""
    return [s for s in _vocab("continuation_status") if s != "DONE"]

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or shutil.which("bash") is None,
    reason="enforce-teardown.sh needs jq + bash; absent here (the hook itself degrades to pass)",
)


# --------------------------------------------------------------------------- #
# Transcript builders (mirror test_enforce_grounding.py)
# --------------------------------------------------------------------------- #
def _line(role="assistant", content=None):
    return json.dumps({"role": role, "content": content or []})


def _tu(name, file_path=None, command=None, url=None):
    inp = {}
    if file_path:
        inp["file_path"] = file_path
    if command:
        inp["command"] = command
    if url:
        inp["url"] = url
    return {"type": "tool_use", "name": name, "input": inp}


def _text(s):
    return {"type": "text", "text": s}


def _cont(status, forward_handle=False):
    """A ```continuation fenced block with the given status; optionally forwarding INSTANCE_HANDLE.

    `forward_handle` is True (forward DEFAULT_TOKEN's lease) or the lease token to forward. The
    handoff clears only the lease whose OWN lease_token the handle carries, so the handle must name
    the real token - a placeholder forwards nobody's lease."""
    body = f"```continuation\nstatus: {status}\n"
    if forward_handle:
        tok = DEFAULT_TOKEN if forward_handle is True else forward_handle
        body += (
            "next:\n"
            "  - skill: odoo-coding\n"
            f"    inputs: {{INSTANCE_HANDLE: {{db_name: x, lease_token: {tok}, run_id: run-abc}}}}\n"
        )
    else:
        body += "produced: []\nnext: []\n"
    body += "```"
    return _text(body)


DEFAULT_TOKEN = "de" * 16
_TU_SEQ = iter(range(1, 10**9))


def _tool_use_line(name, inp, *, ts=None):
    """(line, tool_use_id): one assistant record carrying one tool_use with a unique id."""
    tid = f"toolu_{next(_TU_SEQ):06d}"
    rec = {"type": "assistant",
           "message": {"role": "assistant",
                       "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}}
    if ts:
        rec["timestamp"] = ts
    return json.dumps(rec), tid


def _tool_result_line(tid, content, *, is_error=False, ts=None, tool_use_result=None):
    """The harness-authored `user` record answering tool_use `tid`."""
    block = {"type": "tool_result", "tool_use_id": tid, "content": content}
    if is_error:
        block["is_error"] = True
    rec = {"type": "user", "message": {"role": "user", "content": [block]}}
    if ts:
        rec["timestamp"] = ts
    if tool_use_result is not None:
        rec["toolUseResult"] = tool_use_result
    return json.dumps(rec)


def _acquired(run_id="run-abc", token=DEFAULT_TOKEN, *, command=None, is_error=False):
    """A Bash `allocator.py acquire` the subagent ran ITSELF, plus the tool_result that handed it
    the token - the two lines that prove "this dispatch obtained lease <token>"."""
    cmd = command or (
        f"python3 ${{CLAUDE_PLUGIN_ROOT}}/scripts/lib/allocator.py acquire "
        f"--series 17.0 --mode ephemeral --ports 1 --run-id {run_id}"
    )
    use, tid = _tool_use_line("Bash", {"command": cmd})
    out = "Error: Exit code 10" if is_error else f"ALLOC_TOKEN={token}\nALLOC_RUN_ID={run_id}\n"
    return [use, _tool_result_line(tid, out, is_error=is_error)]


def _mcp_acquired(token, run_id="run-abc", prefix="mcp__plugin_odoo-ai-agents_odoo-local__"):
    """The same proof through the odoo-local MCP tool: the result text is the tool's JSON."""
    use, tid = _tool_use_line(prefix + "lease_acquire",
                              {"series": "17.0", "mode": "ephemeral", "run_id": run_id,
                               "cwd": "/w"})
    payload = {"lease": {"token": token, "run_id": run_id, "db_name": "odoo_17_0_t_x"}}
    return [use, _tool_result_line(tid, [{"type": "text", "text": json.dumps(payload)}],
                                   tool_use_result={"structuredContent": payload})]


def _seed_ledger(home: Path, leases):
    runtime = home / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "leases.json").write_text(
        json.dumps({"schema_version": 2, "leases": leases}), encoding="utf-8"
    )


def _lease(run_id="run-abc", mode="exclusive", pid=None, host=None, fresh=True, token=None):
    now = int(time.time())
    hb = now if fresh else now - 100000
    return {
        "token": token or ("de" * 16),
        "mode": mode,
        "series": "17.0",
        "db_name": "odoo_17_0",
        "drop_on_release": mode != "shared",
        "ports": [8170],
        "owner": {
            "host": host if host is not None else socket.gethostname(),
            "pid": pid,
            "run_id": run_id,
            "started_at": hb,
        },
        "ttl_s": 7200,
        "heartbeat_at": hb,
        "_pg": {"host": "localhost", "user": "odoo"},
    }


def _advisory(out) -> str:
    """The SubagentStop browser advisory's text: it must reach the subagent that drove the pages."""
    assert out is not None, "expected a browser advisory"
    ctx = model_context(out, "SubagentStop")
    assert ctx, out
    return ctx


def _run(tmp_path, lines, stop_hook_active=False, event="SubagentStop", leases=None,
         session_lines=None, home=None, with_agent_path=True, extra_env=None, payload_extra=None):
    """Invoke enforce-teardown.sh with a crafted transcript + a ledger; return (rc, parsed).

    On SubagentStop `lines` is the SUBAGENT's own transcript (`agent_transcript_path`) and
    `session_lines` the whole session's (`transcript_path`, parent + siblings) - the two files the
    real payload carries. On Stop `lines` is the session transcript. `home` reuses a ledger a test
    built with the real allocator; otherwise `leases` are seeded into a fresh one."""
    import os
    if home is None:
        home = tmp_path / "home"
        _seed_ledger(home, leases or [])  # empty ledger by default -> no instance ever matches
    tpath = tmp_path / "transcript.jsonl"
    tpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {"stop_hook_active": stop_hook_active, "hook_event_name": event}
    if event == "SubagentStop":
        spath = tmp_path / "session-transcript.jsonl"
        spath.write_text("\n".join(session_lines or []) + "\n", encoding="utf-8")
        payload["transcript_path"] = str(spath)
        if with_agent_path:
            payload["agent_transcript_path"] = str(tpath)
    else:
        payload["transcript_path"] = str(tpath)
    payload.update(payload_extra or {})
    stdin = json.dumps(payload)
    env = dict(os.environ)
    env.pop("CLAUDE_PID", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    env["ODOO_AI_HOME"] = str(home)
    env["HOME"] = str(home)  # isolate any ~/.odoo-ai fallback
    # The hook's allocator read must not discover the REAL session running this suite.
    env.setdefault("ODOO_AI_SESSION_ANCHOR", "none")
    env.update(extra_env or {})
    proc = subprocess.run(
        ["bash", str(HOOK)], input=stdin, capture_output=True, text=True, timeout=30, env=env
    )
    out = proc.stdout.strip()
    parsed = json.loads(out) if out else None
    return proc.returncode, parsed


# --------------------------------------------------------------------------- #
# Existence
# --------------------------------------------------------------------------- #
def test_hooks_exist_and_are_shell_scripts():
    for h in (HOOK, GC_HOOK):
        assert h.exists(), f"hook not found at {h}"
        assert h.read_text(encoding="utf-8").startswith("#!"), f"{h.name} must be a shell script"


# --------------------------------------------------------------------------- #
# Browser matcher - ADVISORY only, suffix-keyed, never a block
# --------------------------------------------------------------------------- #
def test_a_reused_page_returned_to_about_blank_is_no_finding(tmp_path):
    """One-page-reuse discipline: the reused page is driven, then navigated to about:blank (the
    server refuses to close its last page) -> nothing to nudge."""
    lines = [
        _line(content=[_tu("mcp__chrome-devtools__navigate_page", url="http://127.0.0.1:8069/odoo")]),
        _line(content=[_tu("mcp__chrome-devtools__navigate_page", url="http://127.0.0.1:8069/odoo/sales")]),
        _line(content=[_tu("mcp__chrome-devtools__navigate_page", url="about:blank")]),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is None, "a reused page ending on about:blank must pass clean - no false nudge"


def test_a_reused_page_left_on_a_url_is_nudged_to_about_blank(tmp_path):
    """A page reused by navigate_page is DRIVEN even though this agent never opened it; leaving
    it on the app keeps its session, timers and memory alive -> advisory, never a block."""
    lines = [
        _line(content=[_tu("mcp__chrome-devtools__navigate_page", url="http://127.0.0.1:8069/odoo")]),
        _line(content=[_tu("mcp__chrome-devtools__close_page")]),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    msg = _advisory(out)
    assert "about:blank" in msg and "http://127.0.0.1:8069/odoo" in msg, msg


def test_driving_again_after_blanking_is_nudged(tmp_path):
    """The LAST navigation decides: a blank followed by more driving leaves a live page."""
    lines = [
        _line(content=[_tu("mcp__chrome-devtools__navigate_page", url="about:blank")]),
        _line(content=[_tu("mcp__chrome-devtools__new_page", url="http://127.0.0.1:8069/web")]),
        _line(content=[_tu("mcp__chrome-devtools__close_page")]),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert "about:blank" in _advisory(out), out


def test_a_navigation_without_url_is_not_a_blank(tmp_path):
    """navigate_page back / reload carries no url and leaves the page on a real URL."""
    lines = [
        _line(content=[_tu("mcp__chrome-devtools__navigate_page", url="about:blank")]),
        _line(content=[_tu("mcp__chrome-devtools__navigate_page")]),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert "about:blank" in _advisory(out), out


def _page(op, page_id=None, url=None):
    """A chrome-devtools page call as chrome-devtools-mcp 1.10 issues it: page-scoped tools carry
    the pageId they act on (page-id routing is on by default); new_page never carries one."""
    inp = {}
    if page_id is not None:
        inp["pageId"] = page_id
    if url is not None:
        inp["url"] = url
    return _line(content=[{"type": "tool_use", "name": f"mcp__plugin_odoo-ai-agents_chrome-devtools__{op}",
                           "input": inp}])


def test_every_page_left_on_a_url_is_named_even_when_the_last_navigation_was_blank(tmp_path):
    """With pageIds, the LAST navigation no longer decides: page 2 still shows the app although
    page 1 ended on about:blank, and page 2 was never closed."""
    lines = [
        _page("navigate_page", 1, "http://127.0.0.1:8069/odoo"),
        _page("navigate_page", 2, "http://127.0.0.1:8069/odoo/sales"),
        _page("navigate_page", 1, "about:blank"),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    msg = _advisory(out)
    assert "page(s) 2 (http://127.0.0.1:8069/odoo/sales)" in msg, msg
    assert "1 (" not in msg, "page 1 ended on about:blank and must not be named"


def test_a_page_closed_after_driving_is_not_named(tmp_path):
    """Closing page 2 after it drove the app is its teardown, even though the last navigation
    on record (page 2's) was not about:blank."""
    lines = [
        _page("navigate_page", 1, "about:blank"),
        _page("navigate_page", 2, "http://127.0.0.1:8069/odoo/sales"),
        _page("close_page", 2),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is None, out


def test_a_keyed_reload_is_not_a_blank(tmp_path):
    lines = [
        _page("navigate_page", 3, "about:blank"),
        _page("navigate_page", 3),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert "page(s) 3 (back/forward/reload)" in _advisory(out), out


def test_every_keyed_page_on_about_blank_or_closed_passes_clean(tmp_path):
    lines = [
        _page("new_page", url="http://127.0.0.1:8069/odoo"),
        _page("navigate_page", 2, "http://127.0.0.1:8069/odoo/inventory"),
        _page("close_page", 2),
        _page("navigate_page", 1, "http://127.0.0.1:8069/odoo"),
        _page("navigate_page", 1, "about:blank"),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is None, out


def test_two_new_pages_one_close_is_advisory_never_block(tmp_path):
    """2 new_page vs 1 close_page -> ADVISORY nudge naming the counts, never a block."""
    lines = [
        _line(content=[_tu("mcp__chrome-devtools__new_page")]),
        _line(content=[_tu("mcp__chrome-devtools__new_page")]),
        _line(content=[_tu("mcp__chrome-devtools__close_page")]),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert "2 new_page vs 1 close_page" in _advisory(out), (
        "the advisory must name the concrete unmatched counts"
    )


def test_suffix_matching_across_headed_and_plugin_prefixes(tmp_path):
    """new_page/close_page are keyed on the trailing __name across ALL prefix namespaces."""
    lines = [
        _line(content=[_tu("mcp__chrome-devtools-headed__new_page")]),
        _line(content=[_tu("mcp__plugin_odoo-ai-agents_chrome-devtools__new_page")]),
        _line(content=[_tu("mcp__plugin_odoo-ai-agents_chrome-devtools__close_page")]),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert "2 new_page vs 1 close_page" in _advisory(out), (
        "headed + plugin_* prefixed names must count the same as the bare prefix (suffix match)"
    )


def test_record_and_gif_is_self_contained_no_finding(tmp_path):
    """record_and_gif opens+closes its own page - it must never be counted as an unmatched open."""
    lines = [
        _line(content=[_tu("mcp__pagecast__record_and_gif")]),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is None, "record_and_gif is self-contained -> no finding"


def test_pagecast_record_without_stop_is_advisory(tmp_path):
    lines = [
        _line(content=[_tu("mcp__pagecast-headed__record_page")]),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert "record_page" in _advisory(out) and "stop_recording" in _advisory(out)


def test_playwright_drive_with_close_is_no_finding(tmp_path):
    """One browser_close closes everything driven -> no leak."""
    lines = [
        _line(content=[_tu("mcp__playwright__browser_navigate")]),
        _line(content=[_tu("mcp__playwright__browser_click")]),
        _line(content=[_tu("mcp__playwright__browser_close")]),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is None, "playwright drive + one browser_close must pass clean"


def test_playwright_drive_without_close_is_advisory(tmp_path):
    lines = [
        _line(content=[_tu("mcp__playwright-headed__browser_navigate")]),
        _line(content=[_tu("mcp__playwright-headed__browser_fill_form")]),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert "browser_close" in _advisory(out), "the nudge must name browser_close"


def test_playwright_video_pair_unbalanced_is_advisory(tmp_path):
    lines = [
        _line(content=[_tu("mcp__playwright__browser_navigate")]),
        _line(content=[_tu("mcp__playwright__browser_start_video")]),
        _line(content=[_tu("mcp__playwright__browser_close")]),  # closes page, but video not stopped
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert "browser_start_video" in _advisory(out), (
        "an unbalanced start_video/stop_video pair must be nudged even when the page was closed"
    )


def test_browser_tabs_is_credited_as_a_close_signal(tmp_path):
    """A per-tab browser_tabs {action: close} is a legit close - it must not raise a false nudge."""
    lines = [
        _line(content=[_tu("mcp__playwright__browser_navigate")]),
        _line(content=[_tu("mcp__playwright__browser_click")]),
        _line(content=[_tu("mcp__playwright__browser_tabs")]),  # per-tab close (action not in NORM)
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is None, "browser_tabs must satisfy the close signal - no false playwright nudge"


def test_browser_advisory_fires_on_stop_event_too(tmp_path):
    """Browser findings are advisory on BOTH SubagentStop and Stop - on Stop for the user only."""
    lines = [
        _line(content=[_tu("mcp__chrome-devtools__new_page")]),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines, event="Stop")
    # On the main session's Stop the finding is for the USER: the main session often keeps a page
    # open on purpose for the user, so it is not handed to the model as a reason for another turn.
    assert out is not None and "decision" not in out, out
    assert "hookSpecificOutput" not in out, f"the main-session advisory reached the model: {out!r}"
    assert "new_page" in out.get("systemMessage", ""), out


def test_a_subagent_browser_advisory_says_what_its_caller_receives(tmp_path):
    """The advisory buys the subagent one more turn. Its caller then receives the message that turn
    ends on in place of the report, so the advisory says so - unless the report was already
    delivered through SubagentHandback, when it says that nothing written now reaches the caller."""
    page = _line(content=[_tu("mcp__chrome-devtools__new_page")])
    _, out = _run(tmp_path, [page, _line(content=[_cont("DONE")])])
    assert out["hookSpecificOutput"]["hookEventName"] == "SubagentStop", out
    assert "repeating your complete report" in _advisory(out), out
    use, tid = _tool_use_line("SubagentHandback", {"message": "DONE"})
    _, out = _run(tmp_path, [page, use, _tool_result_line(tid, "Delivered to your caller.")])
    msg = _advisory(out)
    assert "already delivered through SubagentHandback" in msg, msg
    assert "repeating your complete report" not in msg, msg


# --------------------------------------------------------------------------- #
# Instance check - BLOCKING, ledger-grounded, SubagentStop only. Fires at EVERY turn end except a
# BLOCKED / NEEDS_CONTEXT stop-report or a forwarded INSTANCE_HANDLE - never keyed on `DONE`.
# --------------------------------------------------------------------------- #
def test_live_owned_lease_at_done_without_handle_is_blocked(tmp_path):
    """The one hard block: a live non-shared lease THIS subagent acquired + DONE + no handoff."""
    lines = [*_acquired("run-abc", "ab" * 16), _line(content=[_cont("DONE")])]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc", token="ab" * 16)])
    assert out is not None and out.get("decision") == "block", (
        "a live owned instance lease at a DONE claim is a provable leak -> must block"
    )
    reason = out.get("reason", "")
    assert "ab" * 16 in reason, "the block reason must name the exact lease token"
    assert "release" in reason and "--run-id run-abc" in reason, (
        "the reason must give the deterministic release command so the agent can self-correct"
    )


# --------------------------------------------------------------------------- #
# A stop that WAITS for a teammate is not the end of the dispatch (R0 move 3)
# --------------------------------------------------------------------------- #
_COORD_ID = "a-coord-1"
_TEAMMATE_ID = "a5f0teammate01"
_INTERACTIVE = {"CLAUDE_CODE_ENTRYPOINT": "cli", "CLAUDE_CODE_SESSION_ATTENDED": "1"}
_UNATTENDED = {"CLAUDE_CODE_ENTRYPOINT": "sdk-cli", "CLAUDE_CODE_SESSION_ATTENDED": "0"}


def _launched_teammate(aid=_TEAMMATE_ID):
    """The coordinator's own async Agent launch and the receipt naming the teammate it started."""
    use, tid = _tool_use_line("Agent", {"subagent_type": "odoo-ai-agents:odoo-test-writer",
                                        "prompt": "write the RED test", "description": "test-first"})
    receipt = ("Async agent launched successfully.\nagentId: %s (internal ID - do not mention to "
               "user.)\nThe agent is working in the background. You will be notified "
               "automatically when it completes." % aid)
    return [use, _tool_result_line(tid, [{"type": "text", "text": receipt}])]


def _teammate_task(aid=_TEAMMATE_ID, status="running"):
    return {"id": aid, "type": "subagent", "status": status, "description": "test-first",
            "agent_type": "odoo-ai-agents:odoo-test-writer"}


def _waiting_stop(tmp_path, *, env, tasks, launched=True, extra_lines=()):
    tok = "c0" * 16
    lines = [*_acquired("run-w", tok), *(_launched_teammate() if launched else []),
             *extra_lines, _line(content=[_text("Waiting for the test-writer to finish.")])]
    payload = {"agent_id": _COORD_ID, "agent_type": "odoo-ai-agents:odoo-coder",
               "background_tasks": [{"id": _COORD_ID, "type": "subagent", "status": "running",
                                     "description": "node 1"}, *tasks]}
    return _run(tmp_path, lines, leases=[_lease(run_id="run-w", token=tok)], extra_env=env,
                payload_extra=payload)


def test_a_coordinator_waiting_for_its_own_running_teammate_keeps_its_node_lease(tmp_path):
    """Interactive R0 move 3: a coordinator ends its turn to WAIT for the teammate it launched and
    is woken when the teammate finishes - its node lease is still in use. Ordering a release at
    that stop destroys the instance the coordinator is about to build on."""
    _, out = _waiting_stop(tmp_path, env=_INTERACTIVE, tasks=[_teammate_task()])
    assert out is None or out.get("decision") != "block", out


def test_on_an_unattended_surface_a_waiting_stop_is_still_the_end_of_the_dispatch(tmp_path):
    """Unattended, nothing wakes a stopped subagent: the stop IS the end, the lease must be given
    back or handed off."""
    _, out = _waiting_stop(tmp_path, env=_UNATTENDED, tasks=[_teammate_task()])
    assert out is not None and out.get("decision") == "block", out


def test_a_teammate_that_already_finished_is_nothing_to_wait_for(tmp_path):
    _, out = _waiting_stop(tmp_path, env=_INTERACTIVE, tasks=[])
    assert out is not None and out.get("decision") == "block", out


def test_a_running_agent_this_subagent_did_not_launch_is_not_its_wait(tmp_path):
    """`background_tasks` is session-wide: a sibling's or the root's running agent proves nothing
    about this subagent waiting, so the lease is still gated."""
    _, out = _waiting_stop(tmp_path, env=_INTERACTIVE, tasks=[_teammate_task()], launched=False)
    assert out is not None and out.get("decision") == "block", out


def test_a_delivered_handback_is_final_even_with_a_teammate_running(tmp_path):
    """A report handed back through SubagentHandback is the real final report: the lease is gated
    as always, whatever is still running."""
    use, tid = _tool_use_line("SubagentHandback", {"message": "DONE"})
    _, out = _waiting_stop(tmp_path, env=_INTERACTIVE, tasks=[_teammate_task()],
                           extra_lines=[use, _tool_result_line(tid, "Delivered to your caller.")])
    assert out is not None and out.get("decision") == "block", out


REPEAT_REPORT = "repeating your complete report, its continuation block included"


def test_the_instance_block_tells_the_subagent_to_repeat_its_whole_report(tmp_path):
    """The block buys the subagent one more turn, and its caller receives the message that turn
    ends on in place of the report - so the reason says to repeat the complete report."""
    lines = [*_acquired("run-abc", "ab" * 16), _line(content=[_cont("DONE")])]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc", token="ab" * 16)])
    assert out is not None and out.get("decision") == "block", out
    assert REPEAT_REPORT in out["reason"], out["reason"]


def test_an_instance_block_after_a_handback_does_not_ask_for_a_new_report(tmp_path):
    """A report delivered through SubagentHandback is final: the reason must not send the agent
    after a report its caller will never receive."""
    use, tid = _tool_use_line("SubagentHandback", {"message": "DONE"})
    lines = [*_acquired("run-abc", "ab" * 16), use, _tool_result_line(tid, "Delivered.")]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc", token="ab" * 16)])
    assert out is not None and out.get("decision") == "block", out
    assert REPEAT_REPORT not in out["reason"], out["reason"]


def test_a_coordinator_waiting_for_its_teammate_is_told_to_keep_waiting(tmp_path):
    """A coordinator that stopped only to WAIT for the teammate it launched has not written its
    report yet: a browser note at that stop tells it to keep waiting and put the outcome in its
    report - never to repeat a report it has not written (which would end its dispatch early)."""
    page = _line(content=[_tu("mcp__chrome-devtools__new_page")])
    _, out = _waiting_stop(tmp_path, env=_INTERACTIVE, tasks=[_teammate_task()],
                           extra_lines=[page])
    msg = _advisory(out)
    assert "keep waiting" in msg and REPEAT_REPORT not in msg, msg
    # The same stop on the unattended surface is not a wait (nothing wakes the subagent there).
    _, out = _waiting_stop(tmp_path, env=_UNATTENDED, tasks=[_teammate_task()],
                           extra_lines=[page])
    assert out is not None and out.get("decision") == "block", out
    assert "keep waiting" not in out["reason"], out["reason"]


def test_acquire_with_addons_override_still_correlates_its_token(tmp_path):
    """CS-C2's --addons-path-override flag must not break the teardown gate's token
    correlation: the hook pairs the subagent's own Bash `allocator.py acquire` call with the
    `ALLOC_TOKEN=` its tool_result carried, so adding a flag to `acquire` is safe, while
    wrapping the call in a helper or renaming the verb is not - this test is the fence that
    makes that constraint testable."""
    lines = [
        *_acquired("run-abc", "cd" * 16, command=(
            "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py acquire "
            "--series 17.0 --mode ephemeral --ports 1 --run-id run-abc "
            "--addons-path-override /tmp/wt"
        )),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc", token="cd" * 16)])
    assert out is not None and out.get("decision") == "block", (
        "a live owned lease at a DONE claim must still block even when the "
        "acquire command carried --addons-path-override - the flag must not "
        "hide the call from the correlation grep"
    )
    reason = out.get("reason", "")
    assert "cd" * 16 in reason, "the block reason must still name the exact lease token"
    assert "release" in reason and "--run-id run-abc" in reason


def test_all_matching_leases_are_listed_in_the_block_reason(tmp_path):
    """A subagent holding MORE THAN ONE live lease must get every token + release command."""
    lines = [*_acquired("run-abc", "aa" * 16), *_acquired("run-abc", "bb" * 16),
             _line(content=[_cont("DONE")])]
    leases = [
        _lease(run_id="run-abc", token="aa" * 16),
        _lease(run_id="run-abc", token="bb" * 16),
    ]
    _, out = _run(tmp_path, lines, leases=leases)
    assert out is not None and out.get("decision") == "block"
    reason = out["reason"]
    assert "aa" * 16 in reason and "bb" * 16 in reason, (
        "every live owned lease must be named in the reason, each with its release command"
    )
    assert reason.count("--run-id run-abc") >= 2, "each lease needs its own release command"


def test_block_reason_also_carries_browser_advisory(tmp_path):
    """When a subagent both leaks an instance AND left a page open, the block surfaces both."""
    lines = [
        *_acquired("run-abc"),
        _line(content=[_tu("mcp__chrome-devtools__new_page")]),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
    assert out is not None and out.get("decision") == "block"
    assert "release" in out["reason"] and "1 new_page vs 0 close_page" in out["reason"], (
        "the block must name the release cmd AND fold in the open-page nudge"
    )


def test_forwarded_handle_is_a_legitimate_handoff_pass(tmp_path):
    """Same live lease, but INSTANCE_HANDLE forwarded in next.inputs -> named-catcher handoff -> pass."""
    lines = [*_acquired("run-abc"),
             _line(content=[_cont("DONE", forward_handle=True)])]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
    assert out is None, "a forwarded INSTANCE_HANDLE is a legitimate handoff - never block it"


def test_shared_lease_is_never_dropped_pass(tmp_path):
    """A shared lease is a many-reader render target, never a single-consumer drop -> pass."""
    lines = [*_acquired("run-abc"), _line(content=[_cont("DONE")])]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc", mode="shared")])
    assert out is None, "a shared lease must never be blocked as a leak"


def test_instance_block_is_subagentstop_only_not_stop(tmp_path):
    """Instance leaks hard-block only on SubagentStop; the main-agent Stop must never be trapped."""
    lines = [*_acquired("run-abc"), _line(content=[_cont("DONE")])]
    _, out = _run(tmp_path, lines, event="Stop", leases=[_lease(run_id="run-abc")])
    assert out is None or out.get("decision") != "block", (
        "the instance gate must not block the main agent on Stop (only browsers are advised there)"
    )


def test_a_lease_this_subagent_did_not_obtain_is_not_correlated_pass(tmp_path):
    """A live lease whose token this subagent never obtained must not block - whatever its run.
    The subagent's own lease is already released (gone from the ledger); a lease of another run,
    and one of the SAME run minted by someone else, are both still live and both not its leak."""
    lines = [*_acquired("run-abc", DEFAULT_TOKEN), _line(content=[_cont("DONE")])]
    leases = [_lease(run_id="run-OTHER", token="0f" * 16),
              _lease(run_id="run-abc", token="1f" * 16)]
    # The session transcript carries the same acquire (the pre-fix hook read that file): a
    # run-id correlation would reach the `1f` lease from it; a token correlation never does.
    _, out = _run(tmp_path, lines, leases=leases, session_lines=lines)
    assert out is None or out.get("decision") != "block", (
        "correlation is by token - a lease this dispatch did not obtain is not its leak"
    )


def test_pure_consumer_echoing_forwarded_run_id_is_not_blocked(tmp_path):
    """BLOCKER regression: a subagent that RECEIVES a forwarded handle, runs NO allocator command,
    and merely quotes the forwarded run_id in its own report (exactly as agents/odoo-qa-tester.md
    instructs - 'this was forwarded to me, I am NOT releasing it') must NOT be hard-blocked. The
    gate correlates only the TOKENS this subagent's own acquire/adopt/serve calls obtained, never
    free report text - so quoting a forwarded run_id can never trigger the one blocking gate in
    the system."""
    report = (
        "INSTANCE_HANDLE was forwarded to me by the orchestrator "
        "(run_id: run-abc, lease_token: t). I ran the acceptance scenarios against it and I am "
        "NOT releasing it, since I did not provision it - the orchestrator owns teardown."
    )
    lines = [_line(content=[_text(report)]), _line(content=[_cont("DONE")])]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
    assert out is None or out.get("decision") != "block", (
        "a pure consumer that only quotes the forwarded run_id must never be hard-blocked"
    )


def test_dead_pid_same_host_lease_is_stale_pass(tmp_path):
    """A recorded pid on THIS host that is dead means the process exited (no RAM leak) -> pass."""
    lines = [*_acquired("run-abc"), _line(content=[_cont("DONE")])]
    dead = _lease(run_id="run-abc", pid=2147480000, host=socket.gethostname())
    _, out = _run(tmp_path, lines, leases=[dead])
    assert out is None or out.get("decision") != "block", (
        "a dead-pid lease on this host is stale (gc reaps it) - do not block (prefer false-negative)"
    )


def test_g4_alive_pid_past_ttl_still_blocks(tmp_path):
    """G4 regression at the hook level: before this fix, the hook mirrored the
    allocator's OLD `_is_stale` (ttl-fresh is the ONLY gate) by pre-filtering
    `matches` on `(now - heartbeat_at) <= ttl_s` - so a lease whose owner pid was
    verifiably ALIVE on this host, but simply had not heartbeated within
    `ttl_s`, silently fell out of the block set. That is exactly the "a live
    instance's DONE claim slips through ungated" shape this hook exists to
    catch: a subagent claiming DONE while its own still-running server would
    have been reclaimed (RAM leak) had gc run instead of this hook firing.
    MUST FAIL on the pre-fix hook (measured: no block was emitted here)."""
    import os

    lines = [*_acquired("run-abc"), _line(content=[_cont("DONE")])]
    alive_but_ttl_expired = _lease(
        run_id="run-abc", pid=os.getpid(), host=socket.gethostname(), fresh=False,
    )
    _, out = _run(tmp_path, lines, leases=[alive_but_ttl_expired])
    assert out is not None and out.get("decision") == "block", (
        "a same-host lease whose owner pid is PROVABLY alive must block the DONE "
        "claim even when its heartbeat is far past ttl_s - liveness, not ttl, "
        "governs a same-host recorded pid"
    )


# The gate is STATUS-BLIND: it reads the LEDGER and the forwarded handle, never the status value.
# There is no passing tier of statuses. `BLOCKED` / `NEEDS_CONTEXT` used to be an unconditional
# pass, on the reading that T4 makes BLOCKED the sanctioned outcome when teardown ITSELF failed, so
# hard-blocking it would trap the one path the contract gives that failure. That conflated being
# unable to RELEASE with being unable to NAME A CATCHER: the second is always possible (it is text
# in the dispatch's own continuation fence - no tool, no permission, no live process), so requiring
# it traps nobody, while the old pass turned every denied teardown into a silent UNOWNED leak.
STATUS_ENUM_EXPECTED = {"DONE", "NEEDS_NEXT", "BLOCKED", "NEEDS_CONTEXT"}


def test_closed_status_enum_is_fully_enumerated():
    """Structural guard: the vocabulary SSOT's closed enum must be exactly the set this file
    exercises below. A fifth status cannot silently appear untested - this goes red until someone
    adds it to the status-blind sweeps."""
    enum = set(_vocab("continuation_status"))
    assert enum == STATUS_ENUM_EXPECTED, f"closed enum changed: {enum!r}"
    assert set(_declared_non_completion_statuses()) == enum - {"DONE"}


def test_every_status_blocks_when_a_live_lease_is_unforwarded(tmp_path):
    """The invariant this gate exists for, swept across the WHOLE closed enum plus the two
    off-enum shapes. A dispatch holding a live lease it acquired itself, naming nobody to take it,
    must be blocked no matter how it labels its own ending - a stopped run reports honestly AND
    names its catcher, it does not get to skip the second half.

    MUST FAIL on the pre-fix hook for BLOCKED / NEEDS_CONTEXT (measured: both were an
    unconditional pass, which is the door the leaked lease escaped through)."""
    for status in sorted(STATUS_ENUM_EXPECTED) + ["WEDGED"]:
        lines = [*_acquired("run-abc"), _line(content=[_cont(status)])]
        _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
        assert out is not None and out.get("decision") == "block", (
            f"status={status} holds a live unforwarded lease - the gate must block it"
        )


def test_every_status_passes_when_the_handle_is_forwarded(tmp_path):
    """The complement, and the reason the tightening above traps nobody: forwarding
    INSTANCE_HANDLE clears the gate on EVERY status, including the stopped-run reports. An agent
    whose teardown was denied is never stuck - it names its dispatching caller and ends."""
    for status in sorted(STATUS_ENUM_EXPECTED):
        lines = [*_acquired("run-abc"),
                 _line(content=[_cont(status, forward_handle=True)])]
        _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
        assert out is None or out.get("decision") != "block", (
            f"status={status} forwarded INSTANCE_HANDLE - the T4 handoff must pass"
        )


def test_stop_report_still_passes_when_no_lease_is_live(tmp_path):
    """The tightening is scoped to an actually-live owned lease. A BLOCKED dispatch that released
    (or never held) one is reporting a stopped run with nothing outstanding - it must sail
    through, or every unrelated failure would be trapped by a resource gate."""
    for status in ("BLOCKED", "NEEDS_CONTEXT"):
        lines = [*_acquired("run-abc"), _line(content=[_cont(status)])]
        _, out = _run(tmp_path, lines, leases=[])
        assert out is None or out.get("decision") != "block", (
            f"status={status} with no live lease must not be blocked by the instance gate"
        )


def test_needs_next_without_a_forwarded_handle_blocks(tmp_path):
    """T4 gives a live lease exactly ONE exception: `status: NEEDS_NEXT` WITH `INSTANCE_HANDLE`
    forwarded to a named catcher. A bare NEEDS_NEXT is the "unnamed forward the token for later
    release" T4 names as the leak this contract exists to close - nobody has been handed the
    lease, so nobody releases it.
    MUST FAIL on the pre-fix hook (measured: NEEDS_NEXT was an unconditional pass)."""
    lines = [*_acquired("run-abc", "9a" * 16), _line(content=[_cont("NEEDS_NEXT")])]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc", token="9a" * 16)])
    assert out is not None and out.get("decision") == "block", (
        "NEEDS_NEXT with a live lease and no forwarded handle is an unforwarded lease -> block"
    )
    reason = out.get("reason", "")
    assert "9a" * 16 in reason and "--run-id run-abc" in reason
    assert "INSTANCE_HANDLE" in reason, (
        "the reason must name the handoff alternative, not only the release command"
    )


def test_needs_next_with_a_forwarded_handle_passes(tmp_path):
    """The legitimate T4 handoff: NEEDS_NEXT forwarding INSTANCE_HANDLE to a named catcher in
    next.inputs keeps the lease alive on purpose - it must never be blocked."""
    lines = [*_acquired("run-abc"),
             _line(content=[_cont("NEEDS_NEXT", forward_handle=True)])]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
    assert out is None, "a forwarded INSTANCE_HANDLE under NEEDS_NEXT is the sanctioned handoff"


def test_handle_named_only_in_prose_is_not_a_handoff(tmp_path):
    """Shape, not substring: the handoff is read ONLY from inside the closed ```continuation
    fence, because that is the only channel a downstream consumer can act on. Promising a handoff
    in prose forwards nothing, so it must not buy the exception - even though the transcript
    contains the literal token INSTANCE_HANDLE.
    MUST FAIL on the pre-fix hook (measured: any NEEDS_NEXT passed regardless of the handle)."""
    promise = _text(
        "The instance stays up for the next step - INSTANCE_HANDLE (lease_token, run_id) is in "
        "my summary above and odoo-qa-tester can pick it up from there."
    )
    lines = [*_acquired("run-abc"),
             _line(content=[promise]),
             _line(content=[_cont("NEEDS_NEXT")])]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
    assert out is not None and out.get("decision") == "block", (
        "a handle promised in prose is not forwarded in next.inputs - it must not pass the gate"
    )


# "No status" = the subagent's own transcript carries no machine-readable `status:` inside a
# CLOSED ```continuation fence. Each shape below writes something a human might read as an
# ending, and two of them even contain the literal text `status: BLOCKED` - none of them puts a
# status where any consumer in this plugin reads one, so the lease has no declared owner.
NO_STATUS_SHAPES = {
    "plain-prose-turn-end": _text("Waiting for the background run to complete..."),
    "fence-without-a-status-key": _text("```continuation\nproduced: []\nnext: []\n```"),
    "status-in-prose-outside-any-fence": _text("Report: status: BLOCKED on the background run."),
    "fence-that-never-closes": _text("```continuation\nstatus: BLOCKED"),
}


@pytest.mark.parametrize("shape", sorted(NO_STATUS_SHAPES), ids=lambda s: s)
def test_turn_end_with_no_declared_status_blocks_a_live_lease(tmp_path, shape):
    """THE MISSING FOURTH CASE (live-run defect): a subagent ended its dispatch holding a live
    lease and declared NO terminal status at all - it just wrote a sentence. A SubagentStop IS
    the end of that dispatch, so nothing runs later to release the lease, and no
    INSTANCE_HANDLE was forwarded to name a catcher: the leak is permanent until TTL plus a
    later allocator call. The pre-fix gate keyed on the literal `DONE`, so this - the worst of
    the four cases - was the only one that passed silently.
    MUST FAIL on the pre-fix hook (measured: no block emitted for any of the four shapes)."""
    lines = [*_acquired("run-abc", "ef" * 16),
             _line(content=[NO_STATUS_SHAPES[shape]])]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc", token="ef" * 16)])
    assert out is not None and out.get("decision") == "block", (
        f"{shape}: a turn that ends with a live owned lease and no declared status must be "
        f"gated, not passed - a warning cannot fix a dispatch that has already ended"
    )
    reason = out.get("reason", "")
    assert "ef" * 16 in reason and "--run-id run-abc" in reason, (
        "the block must still name the exact lease token + its release command"
    )
    assert "continuation" in reason, (
        "the reason must tell the agent what it failed to emit, not only what to release"
    )


def test_out_of_enum_completion_claim_is_gated_too(tmp_path):
    """A guard bound to ONE spelling of "I am finished" misses every other spelling. The
    continuation enum is closed and lists DONE_WITH_CONCERNS under reserved_tokens - a
    subagent ending on it has still ENDED, so its live lease must be gated exactly like DONE."""
    reserved = _vocab("reserved_tokens")
    assert reserved, "the vocabulary SSOT lost its reserved_tokens list"
    for status in reserved:
        lines = [*_acquired("run-abc"), _line(content=[_cont(status)])]
        _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
        assert out is not None and out.get("decision") == "block", (
            f"status={status} is not a declared non-completion value - it must not buy a pass "
            f"the literal DONE would not have got"
        )


def test_cosmetic_spelling_never_moves_a_status_out_of_its_tier(tmp_path):
    """Decoration fence, now that the gate is status-blind. Cosmetic spelling - backticks,
    lowercase, a trailing comma, bold markers - must change NOTHING in either direction: a
    decorated stop report with a live unforwarded lease still blocks (no spelling buys back the
    old unconditional pass), and a decorated status with its handle forwarded still passes."""
    for raw in ("`BLOCKED`", "blocked", "NEEDS_CONTEXT,", "**needs_context**"):
        lines = [*_acquired("run-abc"), _line(content=[_cont(raw)])]
        _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
        assert out is not None and out.get("decision") == "block", (
            f"status={raw!r} holds a live unforwarded lease - decoration must not buy a pass"
        )
    for raw in ("`NEEDS_NEXT`", "needs_next", "**NEEDS_NEXT**"):
        lines = [*_acquired("run-abc"),
                 _line(content=[_cont(raw, forward_handle=True)])]
        _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
        assert out is None or out.get("decision") != "block", (
            f"status={raw!r} with a forwarded handle is the T4 handoff - decoration must not block"
        )


def test_no_status_on_main_agent_stop_never_blocks(tmp_path):
    """A main agent ends nearly every turn with no continuation block at all - that is normal,
    not a leak claim. The instance block stays SubagentStop-only; widening the status predicate
    must not leak the hard block onto Stop."""
    lines = [*_acquired("run-abc"),
             _line(content=[_text("Waiting for the background run to complete...")])]
    _, out = _run(tmp_path, lines, event="Stop", leases=[_lease(run_id="run-abc")])
    assert out is None or out.get("decision") != "block", (
        "the main agent's Stop must never be trapped by the no-status case"
    )


def test_no_status_without_a_live_lease_is_not_a_block(tmp_path):
    """The LEDGER is the trigger, the status only decides whether to consult it: a no-status
    turn whose run holds nothing live must pass silently (no ledger lie, nothing to release)."""
    lines = [*_acquired("run-abc"),
             _line(content=[_text("Waiting for the background run to complete...")])]
    _, out = _run(tmp_path, lines, leases=[])
    assert out is None, "no live owned lease means there is nothing to gate on"


def test_a_note_continued_stop_that_drops_the_handle_is_still_blocked(tmp_path):
    """A browser advisory buys the subagent one more turn; the report it ends that turn on is the
    one its caller receives. If that repeated report drops the INSTANCE_HANDLE the first one forwarded,
    the lease is unowned - the continued stop (stop_hook_active=true) must still be gated."""
    page = _line(content=[_tu("mcp__chrome-devtools__new_page")])
    first = [*_acquired("run-abc"), page, _line(content=[_cont("DONE", forward_handle=True)])]
    _, out = _run(tmp_path, first, leases=[_lease(run_id="run-abc")])
    note = _advisory(out)
    continued = first + [
        json.dumps({"type": "attachment", "attachment": {
            "type": "hook_additional_context", "content": [note], "hookName": "SubagentStop",
            "hookEvent": "SubagentStop", "toolUseID": "x"}}),
        _line(content=[_cont("DONE")])]
    _, out = _run(tmp_path, continued, stop_hook_active=True, leases=[_lease(run_id="run-abc")])
    assert out is not None and out.get("decision") == "block", (
        "a report rewritten in a hook-continued turn dropped the handle and nobody gated it"
    )


def test_the_same_teardown_block_is_given_once_per_continued_chain(tmp_path):
    """The loop guard: once refused with this exact reason, the continued stop of that chain with
    the same live lease passes (the SessionEnd backstop reclaims it) - a block that repeats forever
    traps the dispatch."""
    lines = [brief_record(), *_acquired("run-abc"), _line(content=[_cont("DONE")])]
    _, first = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
    assert first is not None and first.get("decision") == "block", first
    _, again = _run(tmp_path, lines + [block_feedback_record(first["reason"]),
                                       _line(content=[_cont("DONE")])],
                    stop_hook_active=True, leases=[_lease(run_id="run-abc")])
    assert again is None, f"the same block was given twice: {again!r}"


def test_a_resumed_dispatch_that_drops_the_handle_is_blocked_again(tmp_path):
    """Round 1: refused for not forwarding the lease, then forwarded it and passed. The caller later
    resumes the subagent, and its new final report drops the INSTANCE_HANDLE: that fresh stop must be
    gated again, or the lease stays unowned until the SessionEnd backstop."""
    lease = [_lease(run_id="run-abc")]
    lines = [*_acquired("run-abc"), _line(content=[_cont("DONE")])]
    _, first = _run(tmp_path, lines, leases=lease)
    assert first is not None and first.get("decision") == "block", first
    round_two = lines + [block_feedback_record(first["reason"]),
                         _line(content=[_cont("DONE", forward_handle=True)]),
                         resume_record("Re-run the check and report."),
                         _line(content=[_cont("DONE")])]
    _, out = _run(tmp_path, round_two, leases=lease)
    assert out is not None and out.get("decision") == "block", (
        "a resumed dispatch dropped the handle and passed on an earlier round's refusal"
    )


def test_non_teardown_subagent_self_gates_to_pass(tmp_path):
    """No browser tokens, no run-id signal -> not a teardown-shaped subagent -> silent pass."""
    lines = [
        _line(content=[_tu("Write", file_path="README.md")]),
        _line(content=[_text("Updated the docs.")]),
    ]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
    assert out is None, "a non-teardown subagent must be approved silently even if a lease exists"


def test_no_resource_tokens_passes(tmp_path):
    """A DONE claim with no browser and no instance activity at all -> nothing to enforce."""
    lines = [_line(content=[_text("All good.")]), _line(content=[_cont("DONE")])]
    _, out = _run(tmp_path, lines)
    assert out is None


def test_a_parked_lease_never_blocks_the_subagent_that_parked_it(tmp_path):
    """G4/G6 - the make-or-break case. A PARKED lease is pid-less with a fresh
    heartbeat, which is byte-for-byte the shape this gate reads as "live but
    unprovable" and hard-blocks. Before the exemption, parking an instance
    produced a block telling the agent to RELEASE the instance it had just
    deliberately preserved - the gate refusing the exit it exists to permit, and
    the whole park/resume feature stillborn at the hook.

    The exemption is safe only because `resume` DELETES `parked_at`; the sibling
    below is the half that proves it does not outlive the park."""
    lines = [*_acquired("run-abc", "ef" * 16), _line(content=[_cont("DONE")])]
    parked = _lease(run_id="run-abc", token="ef" * 16)
    parked["parked_at"] = int(time.time())
    parked["park_ttl_s"] = 86400
    _, out = _run(tmp_path, lines, leases=[parked])
    assert out is None or out.get("decision") != "block", (
        "a parked lease has no server process at all - park already did the RAM half "
        "of teardown, so the gate must let that turn end"
    )


def test_the_parked_exemption_dies_with_the_park_not_with_the_lease(tmp_path):
    """The other direction, and the one that would silently reopen the RAM leak:
    the SAME lease WITHOUT `parked_at` - i.e. after a resume - blocks again. If
    the exemption keyed on anything more durable than the park keys (a mode, a
    flag, the token), a resumed live server would be exempt forever."""
    lines = [*_acquired("run-abc", "ef" * 16), _line(content=[_cont("DONE")])]
    resumed = _lease(run_id="run-abc", token="ef" * 16)
    resumed.pop("parked_at", None)
    _, out = _run(tmp_path, lines, leases=[resumed])
    assert out is not None and out.get("decision") == "block", (
        "once the park keys are gone the lease is an ordinary live lease again and "
        "must be gated again"
    )


# --------------------------------------------------------------------------- #
# WHOSE lease - the subagent's own tokens, never its run id (real allocator, real verdict)
#
# A run id is shared by the parent and every sibling of one run BY DESIGN. The gate used to read
# the payload's `transcript_path` (the WHOLE session's transcript) and then block on every live
# lease carrying the run id it found there, so a child was ordered to release its parent's and its
# siblings' live instances. Every test below builds its ledger with the REAL allocator, anchored
# to a live stand-in session process, so "live" is the allocator's own verdict, not a fixture's.
# --------------------------------------------------------------------------- #
_CATALOG = """\
[[instance]]
series = "17.0"
addons_path = ["/srv/odoo/addons"]
run_mode = "source"
http_port = 8069
http_port_base = 8170
port_pool_size = 10
db_name = "odoo_17_0"
db_name_prefix = "odoo_17_0"
db_host = "localhost"
db_user = "odoo"
python = "/nonexistent/python"
"""


class _Ledger:
    """A temp ODOO_AI_HOME whose leases are written by the real allocator, anchored to a live
    `sleep` standing in for the Claude Code session (ODOO_AI_SESSION_ANCHOR)."""

    def __init__(self, tmp_path):
        import os
        import sys
        self.home = tmp_path / "ledger-home"
        self.home.mkdir()
        self.toml = tmp_path / "instances.toml"
        self.toml.write_text(_CATALOG, encoding="utf-8")
        self.session = subprocess.Popen(["sleep", "600"], start_new_session=True)
        self.py = sys.executable
        self._os = os

    def env(self, anchor=None):
        e = dict(self._os.environ)
        e.pop("CLAUDE_PID", None)
        e.pop("CLAUDE_CODE_SESSION_ID", None)
        e["ODOO_AI_HOME"] = str(self.home)
        e["ODOO_AI_INSTANCES"] = str(self.toml)
        e["HOME"] = str(self.home)
        e["ODOO_AI_SESSION_ANCHOR"] = anchor or str(self.session.pid)
        return e

    def alloc(self, *args, anchor=None):
        return subprocess.run([self.py, str(ALLOC), *args], capture_output=True, text=True,
                              env=self.env(anchor), timeout=60)

    def acquire(self, run_id="run-abc", mode="ephemeral", anchor=None, extra=()):
        p = self.alloc("acquire", "--series", "17.0", "--mode", mode, "--no-create",
                       "--ports", "1", "--run-id", run_id, *extra, anchor=anchor)
        assert p.returncode == 0, f"test setup: acquire failed: {p.stderr}"
        return re.search(r"^ALLOC_TOKEN=(\S+)$", p.stdout, re.M).group(1)

    def tokens(self):
        reg = json.loads((self.home / "runtime" / "leases.json").read_text(encoding="utf-8"))
        return {lz["token"] for lz in reg["leases"]}

    def close(self):
        if self.session.poll() is None:
            self.session.kill()
        self.session.wait(timeout=10)


@pytest.fixture
def ledger(tmp_path):
    led = _Ledger(tmp_path)
    try:
        yield led
    finally:
        led.close()


def _run_live(tmp_path, ledger, lines, **kw):
    """Run the hook against the real-allocator ledger. The hook itself is given the stand-in
    session's anchor, as it would inherit the live session's identity in production."""
    kw.setdefault("extra_env", {"ODOO_AI_SESSION_ANCHOR": str(ledger.session.pid)})
    return _run(tmp_path, lines, home=ledger.home, **kw)


def test_the_child_is_blocked_only_on_its_own_lease_never_its_parents(tmp_path, ledger):
    """THE DEFECT, reproduced whole. The parent acquired lease P under run R and dispatched a
    child; the child acquired lease C under the SAME run R and ended without teardown. The
    session transcript (`transcript_path`) carries the parent's acquire; the child's own
    transcript (`agent_transcript_path`) carries only its own. Both leases are live.
    The block must name C, and must never name P - the parent's instance is not the child's to
    release. MUST FAIL on the pre-fix hook (measured: it read the session transcript, correlated
    by run id, and ordered the child to release P as well)."""
    parent_tok = ledger.acquire("run-R")
    child_tok = ledger.acquire("run-R")
    session_lines = [*_acquired("run-R", parent_tok), _line(content=[_text("dispatching child")])]
    child_lines = [*_acquired("run-R", child_tok), _line(content=[_cont("DONE")])]
    _, out = _run_live(tmp_path, ledger, child_lines, session_lines=session_lines)
    assert out is not None and out.get("decision") == "block", (
        "the child's own live lease at a DONE claim is its leak - it must be blocked"
    )
    reason = out["reason"]
    assert child_tok in reason, "the block must name the lease the child acquired"
    assert parent_tok not in reason, (
        "the parent's lease shares the run id but was never the child's - naming it orders the "
        "child to destroy an instance its parent is still using"
    )


def test_the_child_is_blocked_only_on_its_own_mcp_acquired_lease(tmp_path, ledger):
    """Same rule through the odoo-local MCP tool: the child's lease_acquire result carries the
    token, and that token - not the run id - is what the gate correlates."""
    parent_tok = ledger.acquire("run-R")
    child_tok = ledger.acquire("run-R")
    session_lines = [*_mcp_acquired(parent_tok, "run-R")]
    child_lines = [*_mcp_acquired(child_tok, "run-R"), _line(content=[_cont("NEEDS_NEXT")])]
    _, out = _run_live(tmp_path, ledger, child_lines, session_lines=session_lines)
    assert out is not None and out.get("decision") == "block"
    assert child_tok in out["reason"] and parent_tok not in out["reason"]


def test_a_child_that_only_consumed_a_forwarded_handle_is_never_blocked(tmp_path, ledger):
    """The consumer case, against a LIVE lease of the child's own run: the parent acquired P and
    forwarded its INSTANCE_HANDLE; the child built on it and quoted it, but obtained nothing
    itself. Nothing it did makes P its lease, so its turn end must pass untouched."""
    parent_tok = ledger.acquire("run-R")
    use, tid = _tool_use_line("mcp__plugin_odoo-ai-agents_odoo-local__instance_build",
                              {"lease_token": parent_tok, "op": "test", "modules": ["sale"]})
    child_lines = [
        use, _tool_result_line(tid, [{"type": "text", "text": '{"job_id": "j1"}'}]),
        _line(content=[_text(f"Ran the tests on the forwarded instance (lease_token: "
                             f"{parent_tok}, run_id: run-R). I did not provision it and I am "
                             f"NOT releasing it.")]),
        _line(content=[_cont("DONE")]),
    ]
    session_lines = [*_acquired("run-R", parent_tok)]
    _, out = _run_live(tmp_path, ledger, child_lines, session_lines=session_lines)
    assert out is None, "a pure consumer of a forwarded handle obtained no lease - never block it"


def test_a_child_that_adopted_a_lease_owns_its_teardown(tmp_path, ledger):
    """Adopting a lease is a deliberate take-over (it re-anchors onto the caller): the dispatch
    that did it holds a live process nobody else is told about, so it must release, park or
    forward it."""
    tok = ledger.acquire("run-R")
    use, tid = _tool_use_line("mcp__plugin_odoo-ai-agents_odoo-local__lease_adopt",
                              {"lease_token": tok, "run_id": "run-R"})
    lines = [use, _tool_result_line(tid, [{"type": "text", "text": '{"ok": true}'}]),
             _line(content=[_cont("DONE")])]
    _, out = _run_live(tmp_path, ledger, lines)
    assert out is not None and out.get("decision") == "block", f"lease_adopt obtained {tok}"
    assert tok in out["reason"]


def test_serving_a_forwarded_handle_is_consumption_not_obtainment(tmp_path, ledger):
    """THE CONSUMER DEFECT, reproduced whole. The parent acquired P under run R and forwarded its
    INSTANCE_HANDLE; the child, as the instance-handle contract tells it to, ensured the instance
    was up with `instance_serve {lease_token: P}` and ended DONE. It obtained nothing: P is the
    parent's, and since the child shares run R a release it was told to run would SUCCEED and
    destroy the parent's instance. The turn end must pass, and P must never be named.
    MUST FAIL on the pre-fix hook (measured: it counted the serve's input lease_token as the
    child's own and blocked, ordering lease_release of P)."""
    parent_tok = ledger.acquire("run-R")
    use, tid = _tool_use_line("mcp__plugin_odoo-ai-agents_odoo-local__instance_serve",
                              {"lease_token": parent_tok, "run_id": "run-R", "cwd": "/w"})
    result = {"state": "running", "url": "http://localhost:8170", "lease_token": parent_tok,
              "instance_handle": {"lease_token": parent_tok, "run_id": "run-R"}}
    child_lines = [use,
                   _tool_result_line(tid, [{"type": "text", "text": json.dumps(result)}],
                                     tool_use_result={"structuredContent": result}),
                   _line(content=[_cont("DONE")])]
    _, out = _run_live(tmp_path, ledger, child_lines, session_lines=[*_acquired("run-R", parent_tok)])
    assert out is None or parent_tok not in json.dumps(out), (
        "serving a forwarded lease_token is consumption - the parent's lease must never be named"
    )
    assert out is None, "a consumer that only served its forwarded handle obtained nothing"


def test_bash_resume_of_a_forwarded_token_is_consumption_not_obtainment(tmp_path, ledger):
    """The CLI spelling of the same consumption: `allocator.py resume <P>` on a handed-over token
    moves no lease into this dispatch's hands."""
    parent_tok = ledger.acquire("run-R")
    use, tid = _tool_use_line("Bash", {"command": (
        f'python3 "${{CLAUDE_PLUGIN_ROOT}}/scripts/lib/allocator.py" resume {parent_tok} '
        f'--run-id run-R')})
    lines = [use, _tool_result_line(tid, "ok"), _line(content=[_cont("DONE")])]
    _, out = _run_live(tmp_path, ledger, lines)
    assert out is None, "resuming a forwarded token obtained nothing"


def test_a_launching_series_serve_is_never_ordered_to_tear_down_its_shared_server(tmp_path, ledger):
    """A series-mode `instance_serve` that LAUNCHED the server registers a SHARED lease for it (the
    only kind series mode registers). That lease is a multi-reader render server - no single
    consumer's teardown, its launcher included (resource-teardown-contract.md, shared row) - so the
    turn end must pass even though the correlation counts the token (it does, for arm A4 of
    block-unowned-lease-mutation.sh, so the launcher may stop it on an explicit user request). The
    ledger row is live, so only the shared-mode exemption can keep this gate quiet."""
    tok = ledger.acquire("run-R", mode="shared")
    use, tid = _tool_use_line("mcp__plugin_odoo-ai-agents_odoo-local__instance_serve",
                              {"series": "17.0", "run_id": "run-R", "cwd": "/w"})
    result = {"state": "launched", "lease_token": tok}
    lines = [use, _tool_result_line(tid, [{"type": "text", "text": json.dumps(result)}]),
             _line(content=[_cont("DONE")])]
    _, out = _run_live(tmp_path, ledger, lines)
    assert out is None or tok not in json.dumps(out), (
        "a shared render server is never one dispatch's to release - not even its launcher's"
    )


def test_the_block_message_names_only_obtainment_paths_that_can_be_listed(tmp_path, ledger):
    """The gate lists only non-shared leases, and a launching series-mode serve only ever registers
    a shared one - so the block message must not tell an agent a serve it LAUNCHED is among the
    leases it has to clear (that clause sent agents hunting for a server the gate never lists)."""
    tok = ledger.acquire("run-R")
    use, tid = _tool_use_line("mcp__plugin_odoo-ai-agents_odoo-local__lease_acquire",
                              {"series": "17.0", "run_id": "run-R"})
    result = {"lease": {"token": tok}}
    lines = [use, _tool_result_line(tid, [{"type": "text", "text": json.dumps(result)}]),
             _line(content=[_cont("DONE")])]
    _, out = _run_live(tmp_path, ledger, lines)
    assert out is not None and out.get("decision") == "block" and tok in out["reason"]
    assert "instance_serve that LAUNCHED" not in out["reason"]


def test_attaching_to_a_running_shared_server_is_not_obtainment(tmp_path, ledger):
    """A series-mode serve that ATTACHED joined a server another run started. Counting the token
    its result reports made that run's server this dispatch's to release - and a release stops it
    under everyone still using it. The ledger row here is deliberately exclusive + live, so the
    only thing that can keep the gate quiet is the attach not being counted. MUST FAIL on the
    pre-fix correlation (it counted every series-mode serve result's lease_token)."""
    tok = ledger.acquire("run-OTHER")
    use, tid = _tool_use_line("mcp__plugin_odoo-ai-agents_odoo-local__instance_serve",
                              {"series": "17.0", "run_id": "run-R", "cwd": "/w"})
    result = {"state": "attached", "lease_token": tok, "url": "http://localhost:8170"}
    lines = [use, _tool_result_line(tid, [{"type": "text", "text": json.dumps(result)}],
                                    tool_use_result={"structuredContent": result}),
             _line(content=[_cont("DONE")])]
    _, out = _run_live(tmp_path, ledger, lines)
    assert out is None, "attaching to someone else's server obtained nothing - never order its release"


def _resume_lines(tok, *, adopt=True):
    """The resume path of a parked lease of the caller's own run: lease_find(parked) ->
    [lease_adopt] -> instance_serve(lease_token)."""
    mcp = "mcp__plugin_odoo-ai-agents_odoo-local__"
    find, fid = _tool_use_line(mcp + "lease_find", {"series": "17.0", "state": "parked", "run_id": "run-R"})
    found = {"found": True, "state": "parked", "lease": {"token": tok, "run_id": "run-R", "yours": True}}
    lines = [find, _tool_result_line(fid, [{"type": "text", "text": json.dumps(found)}],
                                     tool_use_result={"structuredContent": found})]
    if adopt:
        ad, aid = _tool_use_line(mcp + "lease_adopt", {"lease_token": tok, "run_id": "run-R"})
        adopted = {"lease": {"token": tok, "run_id": "run-R"}, "anchor": "123"}
        lines += [ad, _tool_result_line(aid, [{"type": "text", "text": json.dumps(adopted)}],
                                        tool_use_result={"structuredContent": adopted})]
    serve, sid = _tool_use_line(mcp + "instance_serve", {"lease_token": tok, "cwd": "/w"})
    served = {"state": "launched", "resumed": True, "lease_token": tok, "url": "http://localhost:8170"}
    lines += [serve, _tool_result_line(sid, [{"type": "text", "text": json.dumps(served)}],
                                       tool_use_result={"structuredContent": served})]
    return lines


def test_a_resumed_parked_lease_is_held_by_the_dispatch_that_adopted_it(tmp_path, ledger):
    """lease_find(parked) -> lease_adopt -> instance_serve leaves a RUNNING server. The adopt is the
    take-over, so the resumer must park, release or hand it off - otherwise the resumed server runs
    on with no gate holding anyone to stopping it."""
    tok = ledger.acquire("run-R")
    _, out = _run_live(tmp_path, ledger, [*_resume_lines(tok), _line(content=[_cont("DONE")])])
    assert out is not None and out.get("decision") == "block", "the resumer owns the resumed server"
    assert tok in out["reason"]


def test_a_failed_acquire_obtained_nothing(tmp_path, ledger):
    """An error result handed the caller no lease. Correlating it anyway would pin whatever the
    ledger holds under that token on a dispatch that never got it."""
    tok = ledger.acquire("run-R")
    use, tid = _tool_use_line("mcp__plugin_odoo-ai-agents_odoo-local__lease_acquire",
                              {"series": "17.0", "run_id": "run-R"})
    lines = [use,
             _tool_result_line(tid, [{"type": "text", "text": json.dumps({"lease": {"token": tok}})}],
                               is_error=True),
             _line(content=[_cont("DONE")])]
    _, out = _run_live(tmp_path, ledger, lines)
    assert out is None, "an is_error result obtained nothing"


_EVAL_ACQUIRE = ('eval "$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py" acquire '
                 '--series 17.0 --mode ephemeral --ports 1 --run-id run-R)"')


def _eval_acquired(token, run_id="run-R"):
    """The eval shape: stdout is consumed by the shell, so the tool_result carries ONLY the
    allocator's stderr receipt line - the contract the allocator emits on every acquire."""
    use, tid = _tool_use_line("Bash", {"command": _EVAL_ACQUIRE})
    receipt = f"allocator: acquired lease {token} run_id={run_id}\n"
    return [use, _tool_result_line(tid, receipt,
                                   tool_use_result={"stdout": "", "stderr": receipt})]


def test_the_eval_shape_acquire_is_correlated_by_its_stderr_receipt(tmp_path, ledger):
    """`eval "$(allocator.py acquire ...)"` prints nothing to stdout - the token lands in a shell
    variable - but the allocator's stderr receipt names the token that very call obtained. The
    child's lease is named; the parent's lease of the same run is not."""
    parent_tok = ledger.acquire("run-R")
    child_tok = ledger.acquire("run-R")
    lines = [*_eval_acquired(child_tok), _line(content=[_cont("DONE")])]
    _, out = _run_live(tmp_path, ledger, lines, session_lines=[*_acquired("run-R", parent_tok)])
    assert out is not None and out.get("decision") == "block"
    assert child_tok in out["reason"] and parent_tok not in out["reason"]


def test_parallel_siblings_acquiring_in_the_same_second_each_own_only_their_lease(tmp_path, ledger):
    """Two siblings of ONE run acquire through the eval shape within the same second. Each child
    must be named only on its own lease. MUST FAIL on the pre-fix hook (measured: its +/-5 s
    acquisition-time window over the run's leases attributed BOTH leases to each sibling)."""
    tok_a = ledger.acquire("run-R")
    tok_b = ledger.acquire("run-R")
    for mine, theirs in ((tok_a, tok_b), (tok_b, tok_a)):
        lines = [*_eval_acquired(mine), _line(content=[_cont("DONE")])]
        _, out = _run_live(tmp_path, ledger, lines)
        assert out is not None and out.get("decision") == "block"
        assert mine in out["reason"], "each sibling is blocked on the lease its own call obtained"
        assert theirs not in out["reason"], "a parallel sibling's lease is never this child's"


def test_an_eval_acquire_without_a_receipt_correlates_nothing(tmp_path, ledger):
    """No receipt, no proof: an eval-shape acquire whose result carries no token (an allocator
    that predates the receipt) is a false negative, never a guess over the run's leases."""
    ledger.acquire("run-R")
    use, tid = _tool_use_line("Bash", {"command": _EVAL_ACQUIRE})
    lines = [use, _tool_result_line(tid, ""), _line(content=[_cont("DONE")])]
    _, out = _run_live(tmp_path, ledger, lines)
    assert out is None, "the time-window heuristic is gone - nothing is attributed by timing"


def test_a_receipt_quoted_by_an_unrelated_command_proves_nothing(tmp_path, ledger):
    """A receipt line is read only from an allocator acquire/adopt call's own result: a `cat` of
    a log that contains another dispatch's receipt is not this dispatch obtaining that lease."""
    tok = ledger.acquire("run-R")
    use, tid = _tool_use_line("Bash", {"command": "cat /tmp/some-run.log"})
    lines = [use, _tool_result_line(tid, f"allocator: acquired lease {tok} run_id=run-R\n"),
             _line(content=[_cont("DONE")])]
    _, out = _run_live(tmp_path, ledger, lines)
    assert out is None


def test_a_bash_adopt_receipt_is_correlated(tmp_path, ledger):
    """`allocator.py adopt` is a deliberate take-over; its token (argument and receipt) is owned."""
    tok = ledger.acquire("run-R")
    use, tid = _tool_use_line("Bash", {"command": (
        f'python3 "${{CLAUDE_PLUGIN_ROOT}}/scripts/lib/allocator.py" adopt {tok} --run-id run-R')})
    lines = [use, _tool_result_line(tid, f"allocator: adopted lease {tok} run_id=run-R\n"),
             _line(content=[_cont("DONE")])]
    _, out = _run_live(tmp_path, ledger, lines)
    assert out is not None and out.get("decision") == "block"
    assert tok in out["reason"]


def test_subagentstop_never_reads_the_session_transcript(tmp_path, ledger):
    """The session transcript is the parent's and the siblings' record. A SubagentStop whose own
    transcript obtained nothing passes, whatever the session transcript shows - and one whose
    payload carries no `agent_transcript_path` at all passes too (uncertainty), rather than
    falling back onto the session transcript, which IS the defect."""
    parent_tok = ledger.acquire("run-R")
    session_lines = [*_acquired("run-R", parent_tok), _line(content=[_cont("DONE")])]
    _, out = _run_live(tmp_path, ledger, [_line(content=[_cont("DONE")])],
                       session_lines=session_lines)
    assert out is None, "the child obtained nothing in its own transcript"
    _, out = _run_live(tmp_path, ledger, session_lines, session_lines=session_lines,
                       with_agent_path=False)
    assert out is None, "no agent_transcript_path -> pass, never a fallback to transcript_path"


def test_liveness_is_the_allocators_verdict_not_a_copy(tmp_path, ledger):
    """The session anchor, not a server pid or a TTL, is what keeps an anchored lease alive - and
    only the allocator knows that. A lease whose anchoring session is alive blocks even though no
    server pid was ever recorded; the SAME lease shape whose session has ended is reclaimable and
    does not. The pre-fix hook carried its own jq copy of the liveness rule, which knew nothing of
    session anchors."""
    live_tok = ledger.acquire("run-R")
    ended = subprocess.Popen(["sleep", "600"], start_new_session=True)
    ended_tok = ledger.acquire("run-R", anchor=str(ended.pid))
    ended.kill()
    ended.wait(timeout=10)
    # Past the automatic grace window, so the allocator's automatic reclaim WOULD take it.
    path = ledger.home / "runtime" / "leases.json"
    reg = json.loads(path.read_text(encoding="utf-8"))
    for lz in reg["leases"]:
        if lz["token"] == ended_tok:
            lz["heartbeat_at"] = lz["owner"]["started_at"] = int(time.time()) - 7 * 86400
            lz["owner"]["session"]["seen_at"] = int(time.time()) - 7 * 86400
    path.write_text(json.dumps(reg), encoding="utf-8")

    lines = [*_acquired("run-R", live_tok), *_acquired("run-R", ended_tok),
             _line(content=[_cont("DONE")])]
    _, out = _run_live(tmp_path, ledger, lines)
    assert out is not None and out.get("decision") == "block"
    assert live_tok in out["reason"], "a lease its live session protects is live"
    assert ended_tok not in out["reason"], (
        "a lease whose session ended long ago is the allocator's to reclaim, not a leak this "
        "dispatch can fix"
    )


def test_the_block_offers_the_mcp_tool_first_and_the_cli_as_fallback(tmp_path, ledger):
    """The odoo-local tools are the primary surface; the CLI is the fallback. The block must name
    the MCP give-back calls with the exact token and run id, BEFORE the CLI spelling."""
    tok = ledger.acquire("run-R")
    _, out = _run_live(tmp_path, ledger, [*_acquired("run-R", tok), _line(content=[_cont("DONE")])])
    reason = out["reason"]
    mcp = reason.index("odoo-local__lease_release")
    assert "odoo-local__lease_park" in reason
    assert f'lease_release {{lease_token: "{tok}", run_id: "run-R"}}' in reason, (
        "the MCP remedy must spell the argument the tool requires (lease_token); a bare `token` "
        "is refused with INVALID_ARGUMENTS, so the remedy would fail when followed"
    )
    assert f'lease_park {{lease_token: "{tok}", run_id: "run-R"}}' in reason
    assert "{token:" not in reason
    cli = reason.index(f"allocator.py\" release {tok} --run-id run-R")
    assert mcp < cli, "the MCP tool must be offered first, the CLI only as its fallback"
    assert f"allocator.py\" park {tok} --run-id run-R" in reason, (
        "the CLI park fallback must name the owner exactly as release does - the allocator refuses "
        "an un-named park of an owned lease (NOT_OWNER), so a bare `park <token>` fails when followed"
    )


# --------------------------------------------------------------------------- #
# G6 - the gate's EXIT SET is declared once and copied once, in lockstep.
#
# The hook cannot parse markdown at SubagentStop time, so the three exits are
# written out in the hook AND in snippets/resource-teardown-contract.md T1. That
# is a deliberate SECOND COPY, following the precedent the hook already sets for
# `DEFAULT_TTL_S` ("keep them in lockstep") - and a second copy is only safe while
# something asserts the two agree. This is that something: it compares the SET the
# contract declares against the set the hook actually EMITS to a blocked agent
# (the rendered message, not the source), so a contract that grows a fourth exit
# nobody wired into the hook fails here instead of in production.
# --------------------------------------------------------------------------- #
TEARDOWN_CONTRACT = PLUGIN_ROOT / "snippets" / "resource-teardown-contract.md"
_EXIT_BULLET_RE = re.compile(r"^-\s+\*\*`([a-z-]+)`\*\*", re.M)


def _contract_exit_set():
    """The exits declared under T1's `### The three exits` heading."""
    text = TEARDOWN_CONTRACT.read_text(encoding="utf-8")
    start = text.index("### The three exits")
    end = text.find("\n## ", start)
    section = text[start:] if end == -1 else text[start:end]
    return {m.group(1) for m in _EXIT_BULLET_RE.finditer(section)}


def test_the_contract_declares_exactly_three_exits():
    """Discovery floor: a renamed heading or a reflowed list would make the
    lockstep check below compare the empty set against the empty set and pass
    forever."""
    exits = _contract_exit_set()
    assert exits == {"release", "park", "handoff"}, (
        f"T1 must declare exactly the three exits; found {sorted(exits)} - if the set "
        "legitimately changed, change the hook's message in the same commit"
    )


def test_the_hook_block_names_every_exit_the_contract_declares(tmp_path):
    """Lockstep, asserted on the RENDERED block a blocked agent actually reads.

    An agent that is told only about `release` concludes that preserving a
    just-built database is impossible and destroys it - which is the behavior this
    whole feature exists to end. Naming the exits in the contract while the hook
    stays silent about them is therefore not a documentation gap; it is the defect
    with a document in front of it."""
    lines = [*_acquired("run-abc", "12" * 16), _line(content=[_cont("DONE")])]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc", token="12" * 16)])
    assert out is not None and out.get("decision") == "block", (
        "test setup: this scenario must produce a block, or there is no message to check"
    )
    reason = out["reason"]
    missing = sorted(name for name in _contract_exit_set() if name not in reason)
    assert not missing, (
        f"the block message does not name {missing} - the hook's exit set and "
        f"{TEARDOWN_CONTRACT.name} T1's have drifted apart"
    )
    assert "allocator.py\" park" in reason or "allocator.py park" in reason, (
        "naming `park` in prose is not enough - the block must give the runnable "
        "command, exactly as it does for release"
    )


# --------------------------------------------------------------------------- #
# session-end-gc.sh - crash backstop (L1.3)
# --------------------------------------------------------------------------- #
def _run_gc(plugin_root: Path, stdin="{}", extra_env=None):
    """Run the SessionEnd hook. The session identity is neutralised by default so the hook never
    discovers the REAL session running this suite as the one that is ending."""
    import os
    env = dict(os.environ)
    for name in ("CLAUDE_PID", "CLAUDE_CODE_SESSION_ID"):
        env.pop(name, None)
    env["ODOO_AI_SESSION_ANCHOR"] = "none"
    env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", str(GC_HOOK)], input=stdin, capture_output=True, text=True, timeout=20, env=env
    )


def _wait_for_file(path: Path, timeout_s: float = 30.0):
    """Wait for the DETACHED worker to produce `path`. The hook itself returns in
    milliseconds (it only spawns), so every assertion about the reaping is an
    assertion about the worker, and must be made after it, not after the hook."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.is_file():
            return True
        time.sleep(0.05)
    return path.is_file()


def test_session_end_gc_exits_zero_with_no_allocator(tmp_path):
    """No allocator.py present -> best-effort self-gate to a silent exit 0 (never errors)."""
    proc = _run_gc(tmp_path)  # empty plugin root
    assert proc.returncode == 0, f"must exit 0 with no allocator; stderr={proc.stderr!r}"
    assert proc.stdout.strip() == "", "SessionEnd gc must be silent"


def test_session_end_gc_never_runs_the_unscoped_machine_wide_gc(tmp_path):
    """The registry is MACHINE-GLOBAL: every concurrent session on this host writes the same
    leases.json. A bare `gc` (scope all, TTL arm included) at the end of ONE session is a sweep
    over every other session's work in progress, so the hook may only run the automatic scope
    (`dead-sessions`) and the ending session's own (`anchor`) - never a bare `gc`.
    MUST FAIL on the pre-fix hook (measured: it ran exactly `gc`, scope all)."""
    libdir = tmp_path / "scripts" / "lib"
    libdir.mkdir(parents=True)
    marker = libdir / "calls.txt"
    (libdir / "allocator.py").write_text(
        "import sys, pathlib\n"
        "with (pathlib.Path(__file__).parent / 'calls.txt').open('a') as fh:\n"
        "    fh.write(' '.join(sys.argv[1:]) + '\\n')\n",
        encoding="utf-8",
    )
    proc = _run_gc(tmp_path)
    assert proc.returncode == 0, f"stderr={proc.stderr!r}"
    deadline = time.monotonic() + 30.0
    calls = []
    while time.monotonic() < deadline and not any(c.startswith("gc") for c in calls):
        if marker.is_file():
            calls = [ln for ln in marker.read_text(encoding="utf-8").splitlines() if ln.strip()]
        time.sleep(0.05)
    gc_calls = [c for c in calls if c.split()[0] == "gc"]
    assert "gc --scope dead-sessions" in gc_calls, f"the automatic sweep must run; calls={calls!r}"
    for call in gc_calls:
        assert "--scope dead-sessions" in call or "--scope anchor" in call, (
            f"an unscoped gc reaches every session's leases on this host: {call!r}"
        )


def test_session_end_gc_wires_reap_orphans_list_only_and_persists_the_log(tmp_path):
    """#185: `reap-orphans` existed but had ZERO caller anywhere in the plugin -
    the mechanism was built and unreachable. This hook is now the discovery-half
    caller: it must invoke `reap-orphans` in its DEFAULT list-only mode (never
    `--yes` - that stays a human's explicit, separate action) and PERSIST the
    output so the candidate list is actually reviewable by someone. (`gc` above no
    longer discards its own account either: its stderr is appended to
    `logs/allocator-stderr.log` - see the hook's ALLOC_DIAG_BASENAME and
    tests/test_allocator_stderr_survives.py.)"""
    libdir = tmp_path / "scripts" / "lib"
    libdir.mkdir(parents=True)
    runtime_dir = tmp_path / "odoo-ai-home" / "runtime"
    (libdir / "allocator.py").write_text(
        "import sys, pathlib\n"
        "argv = sys.argv[1:]\n"
        "marker = pathlib.Path(__file__).parent / (argv[0] + '-called.txt')\n"
        "marker.write_text(' '.join(argv))\n"
        "if argv[0] == 'reap-orphans':\n"
        "    print('REAP_CANDIDATE fake_db_t_deadbeef age_h=30.0 size_mb=1.0')\n"
        "    print('# 1 orphan candidate(s) found (list-only - pass --yes to drop)')\n",
        encoding="utf-8",
    )
    (libdir / "resolve_instances.sh").write_text(
        "_odoo_ai_runtime_dir() { printf '%s\\n' " + repr(str(runtime_dir)) + "; }\n",
        encoding="utf-8",
    )

    proc = _run_gc(tmp_path)
    assert proc.returncode == 0, f"stderr={proc.stderr!r}"
    assert proc.stdout.strip() == "", "SessionEnd gc must stay silent on its own stdout"

    gc_marker = libdir / "gc-called.txt"
    assert _wait_for_file(gc_marker), "gc must still be invoked (unchanged L1.3 behavior)"
    assert gc_marker.read_text(encoding="utf-8").strip() == "gc --scope dead-sessions"

    reap_marker = libdir / "reap-orphans-called.txt"
    assert _wait_for_file(reap_marker), "session-end-gc.sh must now invoke reap-orphans (#185)"
    reap_argv = reap_marker.read_text(encoding="utf-8").strip()
    assert reap_argv == "reap-orphans", (
        f"reap-orphans must be called with NO extra flags - list-only default, "
        f"never --yes from this unattended hook; got argv={reap_argv!r}"
    )

    log_path = runtime_dir / "reap-orphans-candidates.log"
    # The redirect CREATES the file before reap-orphans emits a byte, so existence is
    # not the property under test - a truncated, empty candidate log is exactly the
    # failure the detach exists to prevent. Wait for actual CONTENT.
    deadline = time.monotonic() + 30.0
    log_text = ""
    while time.monotonic() < deadline:
        if log_path.is_file():
            log_text = log_path.read_text(encoding="utf-8")
            if "list-only" in log_text:
                break
        time.sleep(0.05)
    assert log_path.is_file(), (
        "the reap-orphans discovery output must be PERSISTED to its own candidate "
        "log so a human can actually review the candidate list later"
    )
    assert "REAP_CANDIDATE" in log_text and "list-only" in log_text, (
        f"the candidate log must carry the FULL discovery output, not a truncated "
        f"prefix left behind by a killed reaper; got {log_text!r}"
    )


def test_session_end_gc_returns_at_once_and_reaps_from_a_detached_session(tmp_path):
    """A SessionEnd hook does NOT get the budget its registration declares: measured on
    Claude Code 2.1.233, this hook (declared 25s, real runtime ~2.2s) was ABORTED ~1s after
    the batch's only other SessionEnd hook finished, 3 runs of 3 - and the abort KILLED the
    child mid-write (the candidate log was left 0 bytes). The rule this locks in: the hook
    must hand the reaping to a process the dying CLI does not own, and return at once.

    Two observable consequences, both asserted here:
      1. the hook returns long before the reaping could have finished (it only spawns);
      2. the reaping still completes afterwards, from its OWN session id - i.e. it is not
         in the CLI's process group, which is what lets it outlive the CLI's death."""
    import os

    libdir = tmp_path / "scripts" / "lib"
    libdir.mkdir(parents=True)
    # gc sleeps far longer than the hook may take, so a synchronous hook cannot hide here.
    (libdir / "allocator.py").write_text(
        "import os, sys, pathlib, time\n"
        "argv = sys.argv[1:]\n"
        "if argv[0] == 'gc':\n"
        "    time.sleep(3)\n"
        "marker = pathlib.Path(__file__).parent / (argv[0] + '-done.txt')\n"
        "marker.write_text(str(os.getsid(0)))\n",
        encoding="utf-8",
    )

    started = time.monotonic()
    proc = _run_gc(tmp_path)
    elapsed = time.monotonic() - started

    assert proc.returncode == 0, f"stderr={proc.stderr!r}"
    assert elapsed < 2.0, (
        f"the SessionEnd hook must return immediately (spawn only) - it took {elapsed:.2f}s, "
        f"which means the reaping is running UNDER the hook again and will be truncated by "
        f"the CLI's abort exactly as it was before the detach"
    )

    marker = libdir / "gc-done.txt"
    assert not marker.is_file(), (
        "gc must still be running when the hook returns - if it already finished, the hook "
        "waited for it and the detach is not real"
    )
    assert _wait_for_file(marker), (
        "the detached worker must still complete the gc after the hook returned - a fire-and-"
        "forget that never runs is worse than the synchronous version it replaced"
    )

    worker_sid = int(marker.read_text(encoding="utf-8").strip())
    assert worker_sid != os.getsid(0), (
        "the worker must run in its OWN session (start_new_session/setsid); sharing this "
        "caller's session is what lets the dying CLI kill it mid-reap"
    )


def test_session_end_gc_reaping_bounds_are_not_squeezed_under_the_hook_timeout():
    """The pre-detach defect, in one line of arithmetic: the script's own inner bounds
    (gc 25s + reap 15s = 40s) already exceeded the 25s its registration granted the WHOLE
    script, so a gc that actually used its bound guaranteed the rest was cut off - and gc
    NEEDS that room (up to 10s of SIGTERM grace PER orphan). Now that the reaping is
    detached, its bounds are sized for the work instead of for a hook budget. Lock that in:
    the worker's own gc bound must be LARGER than the hook timeout, which is only possible
    if the reaping no longer runs under it."""
    text = GC_HOOK.read_text(encoding="utf-8")
    bounds = {
        name: int(re.search(rf"^{name}=(\d+)", text, re.MULTILINE).group(1))
        for name in ("GC_TIMEOUT_S", "REAP_TIMEOUT_S")
    }

    reg = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    hook_timeouts = [
        h.get("timeout")
        for group in reg["hooks"]["SessionEnd"]
        for h in group.get("hooks", [])
        if "session-end-gc.sh" in h.get("command", "")
    ]
    assert hook_timeouts, "session-end-gc.sh must stay registered under SessionEnd"
    hook_timeout = hook_timeouts[0]

    assert bounds["GC_TIMEOUT_S"] > hook_timeout, (
        f"the gc bound ({bounds['GC_TIMEOUT_S']}s) must exceed the hook timeout "
        f"({hook_timeout}s) - if it fits under it, the reaping has been moved back under a "
        f"budget the CLI does not honour anyway"
    )
    assert bounds["GC_TIMEOUT_S"] >= 60, (
        f"gc spends up to 10s of SIGTERM grace per orphan; {bounds['GC_TIMEOUT_S']}s leaves "
        f"no room for a real multi-orphan crash, the case this backstop exists for"
    )
    assert bounds["REAP_TIMEOUT_S"] <= bounds["GC_TIMEOUT_S"], (
        "reap-orphans is the read-only half and must never outrank gc's bound"
    )


# --------------------------------------------------------------------------- #
# session-end-gc.sh - WHAT it reclaims (real hook, real allocator, real ledger)
#
# The registry is machine-global. The contract: at a session's end, reclaim that session's own
# running/reserved leases once its anchor process is provably gone, plus leases whose owner is
# provably dead (the automatic `dead-sessions` scope) - and nothing a live session, a park, or a
# merely-unprovable lease still holds.
# --------------------------------------------------------------------------- #
def _session_end(ledger, tmp_path, *, reason="prompt_input_exit", anchor_pid=None,
                 session_id="", extra_env=None):
    """Run the REAL SessionEnd hook as the session anchored at `anchor_pid` would."""
    empty = tmp_path / "empty-instances.toml"
    empty.write_text("# no [[instance]] declared\n", encoding="utf-8")
    env = {
        "ODOO_AI_HOME": str(ledger.home),
        "HOME": str(ledger.home),
        # gc of these no-drop leases needs no catalog, and an empty one keeps the list-only
        # reap-orphans away from any real cluster.
        "ODOO_AI_INSTANCES": str(empty),
        "ODOO_AI_SESSION_ANCHOR": str(anchor_pid or ledger.session.pid),
    }
    env.update(extra_env or {})
    stdin = json.dumps({"hook_event_name": "SessionEnd", "reason": reason,
                        "session_id": session_id})
    proc = _run_gc(PLUGIN_ROOT, stdin=stdin, extra_env=env)
    assert proc.returncode == 0 and proc.stdout.strip() == "", proc.stderr
    return ledger.home / "runtime" / "reap-orphans-candidates.log"


def _wait_worker_done(candidates_log, timeout_s=90.0):
    """The worker's LAST step writes the list-only reap-orphans log; its content means every
    gc step before it has finished."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if candidates_log.is_file() and "nothing to reap" in candidates_log.read_text(
                encoding="utf-8", errors="replace"):
            return True
        time.sleep(0.1)
    return False


def _age_lease(ledger, token, seconds, **fields):
    path = ledger.home / "runtime" / "leases.json"
    reg = json.loads(path.read_text(encoding="utf-8"))
    for lz in reg["leases"]:
        if lz["token"] == token:
            past = int(time.time()) - seconds
            lz["heartbeat_at"] = lz["owner"]["started_at"] = past
            if lz["owner"].get("session"):
                lz["owner"]["session"]["seen_at"] = past
            lz.update(fields)
    path.write_text(json.dumps(reg), encoding="utf-8")


def test_session_end_reclaims_only_the_ending_sessions_own_running_leases(tmp_path, ledger):
    """THE CONTRACT. The ending session A holds a running lease and a PARKED one; a concurrent
    live session B holds a lease; an unanchored, pid-less lease is days past its TTL (liveness
    unprovable, NOT provably dead). A's process exits after the hook fires, as `claude` does.
    Only A's running lease may go. MUST FAIL on the pre-fix hook (measured: it ran a bare `gc`
    over the machine-global registry, whose TTL arm reclaimed the unprovable lease too)."""
    other = subprocess.Popen(["sleep", "600"], start_new_session=True)
    try:
        a_run = ledger.acquire("run-A", mode="exclusive")
        a_parked = ledger.acquire("run-A", mode="exclusive", extra=("--db-name", "odoo_a_parked"))
        _age_lease(ledger, a_parked, 0, parked_at=int(time.time()), park_ttl_s=172800)
        b_run = ledger.acquire("run-B", mode="exclusive", anchor=str(other.pid),
                               extra=("--db-name", "odoo_b"))
        unprovable = ledger.acquire("run-U", mode="exclusive", anchor="none",
                                    extra=("--db-name", "odoo_u"))
        _age_lease(ledger, unprovable, 3 * 86400)

        log = _session_end(ledger, tmp_path)
        ledger.close()  # the ending session's process exits, after the hook fired
        assert _wait_worker_done(log), "the detached worker never finished"
        remaining = ledger.tokens()
        assert a_run not in remaining, "the ended session's own running lease must be reclaimed"
        assert remaining == {a_parked, b_run, unprovable}, (
            "only the ended session's RUNNING lease may go: its park survives by design, a live "
            "session's lease is work in progress, and an unprovable lease is a human's call"
        )
    finally:
        other.kill()
        other.wait(timeout=10)


def test_session_end_destroys_nothing_while_the_anchor_is_still_alive(tmp_path, ledger):
    """A session whose process outlives the wait (a SessionEnd that did not end the process) keeps
    every lease: the hook asks without --force and the allocator refuses a live anchor."""
    a_run = ledger.acquire("run-A", mode="exclusive")
    log = _session_end(ledger, tmp_path, extra_env={"ODOO_AI_SESSION_END_ANCHOR_WAIT_S": "1"})
    assert _wait_worker_done(log), "the detached worker never finished"
    assert a_run in ledger.tokens(), "a live session's lease must survive its SessionEnd"
    diag = (ledger.home / "logs" / "allocator-stderr.log")
    assert diag.is_file() and "still ALIVE" in diag.read_text(encoding="utf-8"), (
        "the anchor step must have ASKED and been refused - not silently skipped"
    )


@pytest.mark.parametrize("case", ["clear", "foreign-session-id"])
def test_session_end_leaves_a_session_it_cannot_prove_ended_alone(tmp_path, ledger, case):
    """`/clear` ends a session inside a process that keeps running; and an anchor that reports a
    DIFFERENT session id than the payload is not provably the ending session's. Neither may
    reclaim that anchor's leases, even once the process is gone (the automatic `dead-sessions`
    grace window still protects a freshly-ended session)."""
    a_run = ledger.acquire("run-A", mode="exclusive")
    kw = {"reason": "clear"} if case == "clear" else {
        "session_id": "the-ending-session",
        "extra_env": {"CLAUDE_CODE_SESSION_ID": "some-other-session"}}
    log = _session_end(ledger, tmp_path, **kw)
    ledger.close()
    assert _wait_worker_done(log), "the detached worker never finished"
    assert a_run in ledger.tokens(), f"{case}: not provably this session's end - keep its leases"



def test_session_end_gc_never_passes_yes_to_reap_orphans():
    """Static guard: the destructive `--yes` flag must never appear anywhere on
    this hook's reap-orphans invocation line - the drop half is a deliberate,
    separate, human-reviewed action (see the hook's own header rationale)."""
    text = GC_HOOK.read_text(encoding="utf-8")
    for line in text.splitlines():
        if "reap-orphans" in line and not line.strip().startswith("#"):
            assert "--yes" not in line, (
                f"session-end-gc.sh must never pass --yes to reap-orphans: {line!r}"
            )


# --------------------------------------------------------------------------- #
# hooks.json registration (JSON-parse assertions)
# --------------------------------------------------------------------------- #
def _commands_for(event):
    reg = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    cmds = []
    for group in reg["hooks"].get(event, []):
        for h in group.get("hooks", []):
            cmds.append(h.get("command", ""))
    return cmds


def test_hooks_json_registers_session_end_gc():
    assert any("session-end-gc.sh" in c for c in _commands_for("SessionEnd")), (
        "hooks.json must register session-end-gc.sh under a SessionEnd event"
    )


def test_hooks_json_registers_enforce_teardown_on_both_stop_events():
    assert any("enforce-teardown.sh" in c for c in _commands_for("SubagentStop")), (
        "enforce-teardown.sh must be registered under SubagentStop (the instance block)"
    )
    assert any("enforce-teardown.sh" in c for c in _commands_for("Stop")), (
        "enforce-teardown.sh must be registered under Stop (the browser advisory)"
    )


def test_hooks_json_still_wires_enforce_grounding_alongside_teardown():
    """The new hook is ADDITIVE - it must not displace the existing SubagentStop grounding gate."""
    subagent = _commands_for("SubagentStop")
    assert any("enforce-grounding.sh" in c for c in subagent)


# --------------------------------------------------------------------------- #
# The gate's TRIGGER is described identically everywhere, or nowhere
#
# The gate no longer keys on a literal `status: DONE`; it blocks EVERY subagent turn end except a
# BLOCKED / NEEDS_CONTEXT stop-report or a forwarded INSTANCE_HANDLE. A file that still calls the
# trigger "DONE-only" tells an agent debugging a hard block that the block is a bug - and the most
# authoritative-looking artifacts (hooks.json, the hook's own header) are exactly where that stale
# claim survived. The scan universe therefore includes the artifacts the whole-tree prose guards
# historically skipped: hooks/*.json, hooks/*.sh, and the repo's own tests/*.py.
# --------------------------------------------------------------------------- #
_HOOKS_DIR = PLUGIN_ROOT / "hooks"

# The gate itself - a DONE token only matters in a sentence that is talking about THIS gate.
# `hard block` is deliberately NOT here: it is generic enough to drag in unrelated degraded-path
# prose that merely happens to mention `status: DONE`.
_GATE_VOCAB = re.compile(
    r"enforce-teardown|teardown gate|resource-teardown|instance-teardown|SubagentStop",
    re.IGNORECASE,
)
# The sentence binds the gate to an outcome (this is a TRIGGER description, not a passing mention).
_TRIGGER_BINDING = re.compile(
    r"\b(?:fires?|firing|keyed|gated|self-passes|blocks?|blocked|blocking|triggers?|leak)\b",
    re.IGNORECASE,
)
# What makes the sentence NOT a DONE-only claim: it names another status the gate treats
# differently, names the no-status / out-of-enum shapes, denies the DONE keying outright, or labels
# itself as history. Naming DONE and nothing else is precisely the false claim.
_TRIGGER_QUALIFIER = re.compile(
    r"BLOCKED|NEEDS_CONTEXT|NEEDS_NEXT|no (?:machine-readable )?status|out-of-enum|"
    r"outside the enum|not keyed|never on the literal|pre-fix|no longer|used to|retired|"
    r"superseded|every turn end|any turn end",
    re.IGNORECASE,
)
_DONE_TOKEN = re.compile(r"\bDONE\b")


def _prose_of(path: Path) -> str:
    """The human-readable prose of a file, so a code line is never read as a claim.

    For `.py` the prose is its COMMENTS and DOCSTRINGS (a `_cont("DONE")` fixture argument is
    code, not a description of the gate); for `.sh` it is the comment lines; everything else is
    scanned whole."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        chunks = []
        try:
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type == tokenize.COMMENT:
                    chunks.append(tok.string.lstrip("#").strip())
                elif tok.type == tokenize.STRING and tok.string.lstrip("rbuRBUf")[:3] in (
                    '"""', "'''",
                ):
                    chunks.append(tok.string)
        except (tokenize.TokenError, IndentationError, SyntaxError):
            return text  # unparseable: scan it whole rather than skip it
        return "\n".join(chunks)
    if path.suffix == ".sh":
        return "\n".join(
            line.lstrip("#").strip()
            for line in text.splitlines()
            if line.lstrip().startswith("#")
        )
    return text


def _sentences(text: str):
    """Whitespace-normalized sentences. Joining the wrapped lines first is the whole point - every
    stale claim in this area spanned two or three source lines. Split on `.!?` only: a `:` or `;`
    routinely separates a claim from the gate name that governs it (`... at DONE is a leak (SSOT:
    resource-teardown-contract.md)`), and splitting there is what let one survive."""
    return [s for s in re.split(r"(?<=[.!?])\s+", " ".join(text.split())) if s]


def _trigger_scan_corpus():
    """Every agent-facing / machine-readable file that could describe the gate's trigger.

    Deliberately wider than `plugins/**/*.md`: `hooks/*.json` is the registration a debugging agent
    reads first, `hooks/*.sh` carries the headers that justify each hook, and `tests/*.py` carries
    the section banners a maintainer reads as the contract - all three were unscanned, and all
    three are where the stale DONE-only claims survived. This file is excluded because it must be
    allowed to NAME the shapes it bans."""
    self_path = Path(__file__).resolve()
    files = set((ROOT / "plugins").rglob("*.md"))
    files |= set(_HOOKS_DIR.glob("*.json")) | set(_HOOKS_DIR.glob("*.sh"))
    files |= set((ROOT / "tests").glob("*.py"))
    return sorted(p for p in files if p.resolve() != self_path)


def _done_only_offenders(paths):
    """Every sentence in `paths` that presents DONE as the teardown gate's trigger."""
    offenders = []
    for path in paths:
        try:
            prose = _prose_of(path)
        except (UnicodeDecodeError, OSError):
            continue
        for sentence in _sentences(prose):
            if not (_DONE_TOKEN.search(sentence) and _GATE_VOCAB.search(sentence)):
                continue
            if not _TRIGGER_BINDING.search(sentence):
                continue
            if _TRIGGER_QUALIFIER.search(sentence):
                continue
            offenders.append(f"{path}: {sentence[:220]}")
    return offenders


def test_trigger_scan_corpus_covers_the_historical_blind_spots():
    """Discovery floor: a corpus that silently stopped covering hooks/ or tests/ would make the
    guard below vacuous, which is how every stale claim in this area survived in the first place."""
    corpus = _trigger_scan_corpus()
    assert HOOKS_JSON in corpus, "hooks/hooks.json must be in the trigger-description scan"
    assert HOOK in corpus, "hooks/enforce-teardown.sh must be in the trigger-description scan"
    assert GC_HOOK in corpus, "hooks/session-end-gc.sh must be in the trigger-description scan"
    assert any(p.suffix == ".py" and p.parent.name == "tests" for p in corpus), (
        "the repo's own tests/*.py must be in the trigger-description scan"
    )
    assert any(p.suffix == ".md" for p in corpus), "plugin markdown must still be scanned"


def test_the_done_only_detector_can_actually_fire():
    """Red-before-green, in-repo: the detector must flag every phrasing the real stale survivors
    used, and clear the corrected wording - otherwise the whole-tree scan below is a guard that can
    only ever say "clean"."""
    must_flag = (
        # the five real survivors this guard was written for, verbatim in shape
        "the instance-teardown gate, which fires only on a live, non-shared lease that the "
        "SUBAGENT ITSELF provisioned at a DONE claim",
        "a -9 / OOM / abort runs no teardown prose and emits no DONE claim, so the DONE-gated "
        "SubagentStop teardown gate self-passes and never fires.",
        "prose release (graceful) -> SubagentStop block (a lying DONE) -> SessionEnd gc.",
        "an unforwarded live lease at DONE is a leak (SSOT: resource-teardown-contract.md T4)",
        "Instance check - BLOCKING, ledger-grounded, SubagentStop only, DONE only",
        # other spellings of the same claim - one phrasing must never be the whole guard
        "the resource-teardown gate is DONE-gated",
        "enforce-teardown.sh blocks a DONE claim",
        "the SubagentStop teardown gate fires when a subagent claims DONE",
        "the teardown gate triggers on DONE and nothing else",
        "SubagentStop teardown gate: it only ever fires at DONE",
    )
    for claim in must_flag:
        assert _done_only_offenders([_Synthetic(claim)]), (
            f"the DONE-only detector failed to flag: {claim!r}"
        )
    must_clear = (
        "the instance-teardown gate fires at a turn end that neither reports a stopped run "
        "(BLOCKED or NEEDS_CONTEXT) nor forwards INSTANCE_HANDLE - it is NOT keyed on DONE.",
        "an unforwarded live lease at any turn end but BLOCKED/NEEDS_CONTEXT is a leak the "
        "SubagentStop gate hard-blocks (SSOT: resource-teardown-contract.md T4)",
        "The pre-fix SubagentStop teardown gate keyed on the literal DONE.",
        "Degraded paths (never hard-block the whole run): the writer reports status: DONE with "
        "concerns.",
    )
    for ok in must_clear:
        assert not _done_only_offenders([_Synthetic(ok)]), (
            f"the DONE-only detector false-flagged correct prose: {ok!r}"
        )


class _Synthetic:
    """A one-sentence stand-in for a real file, so the detector's own red/green proof needs no
    fixture tree and no write into the repo."""

    suffix = ".md"

    def __init__(self, text):
        self._text = text

    def read_text(self, encoding="utf-8"):
        return self._text

    def __str__(self):
        return "<synthetic>"


def test_no_file_describes_the_teardown_gate_trigger_as_done_only():
    """No file anywhere may describe the teardown gate's trigger as DONE-only, in any phrasing.

    Whitespace-normalized and shape-based, so a reflow or a reworded sentence cannot smuggle the
    claim back in. An agent that believes the gate is DONE-gated concludes a block on a no-status
    turn end is a bug, and disables the only hard-enforcement mechanism in the system."""
    offenders = _done_only_offenders(_trigger_scan_corpus())
    assert not offenders, (
        "the teardown gate's trigger is still described as DONE-only:\n  " + "\n  ".join(offenders)
    )


def test_the_authoritative_artifacts_state_the_real_trigger():
    """The other half of the rule above: deleting the description must NOT pass as 'no stale claim
    found'. The two artifacts a debugging agent actually reads - the hook manifest and the hook's
    own header - must each state the REAL trigger: the gate is status-blind, its one exception is
    a forwarded INSTANCE_HANDLE, and the stop-report statuses are named as GATED rather than sold
    as a free pass. A reader who believes `BLOCKED` still walks through will re-open the leak."""
    manifest = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    for label, text in (
        ("hooks/hooks.json description", manifest.get("description", "")),
        ("hooks/enforce-teardown.sh header", HOOK.read_text(encoding="utf-8")),
    ):
        norm = " ".join(text.split())
        assert "BLOCKED" in norm and "NEEDS_CONTEXT" in norm, (
            f"{label}: must name BOTH stop-report statuses the gate now covers"
        )
        assert "INSTANCE_HANDLE" in norm, (
            f"{label}: must name the forwarded-handle handoff as the gate's only exception"
        )
        assert re.search(r"status-blind|STATUS-BLIND", norm), (
            f"{label}: must say the gate is STATUS-BLIND - without it, the "
            "'BLOCKED is a sanctioned pass' reading comes straight back and the leak with it"
        )
        assert not re.search(
            r"Only a stopped-run report|stop-report\) or a T4 named handoff passes", norm
        ), (
            f"{label}: still advertises the retired unconditional stop-report pass"
        )


# --------------------------------------------------------------------------- #
# The gate decides inside its timeout on a long dispatch
# --------------------------------------------------------------------------- #
def _declared_subagentstop_timeout() -> float:
    manifest = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    for group in manifest["hooks"]["SubagentStop"]:
        for h in group["hooks"]:
            if h["command"].endswith('/hooks/enforce-teardown.sh"'):
                return float(h["timeout"])
    raise AssertionError("enforce-teardown.sh is not registered under SubagentStop")


def test_a_live_lease_on_a_long_transcript_is_blocked_well_inside_the_timeout(tmp_path):
    """A long dispatch (thousands of calls, tens of MB of transcript) that holds a live lease at
    DONE is still blocked - and in a fraction of the timeout hooks.json gives the gate. A gate the
    harness cancels for running too long decides nothing, so the lease leaks unblocked: this gate
    must never fail toward allow by being slow."""
    filler = []
    for i in range(12000):            # ~75 MB: the size of a real long dispatch's transcript
        use, tid = _tool_use_line("Bash", {"command": f"echo step {i}"})
        filler += [use, _tool_result_line(tid, f"step {i} " + "x" * 6000)]
    tok = "f1" * 16
    lines = [*filler, *_acquired("run-long", tok), _line(content=[_cont("DONE")])]
    budget = _declared_subagentstop_timeout()
    t0 = time.monotonic()
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-long", token=tok)])
    elapsed = time.monotonic() - t0
    assert out is not None and out.get("decision") == "block", out
    assert tok in out.get("reason", "")
    assert elapsed < budget / 4, (
        f"the teardown gate took {elapsed:.1f}s on a long dispatch; hooks.json gives it "
        f"{budget:.0f}s and a cancelled gate never blocks")
