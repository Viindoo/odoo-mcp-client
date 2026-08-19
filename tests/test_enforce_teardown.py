"""Behavioral guard for hooks/enforce-teardown.sh + hooks/session-end-gc.sh (L1.6 + L1.3).

These protect the BEHAVIOR contract of the resource-teardown enforcement (ETHOS#11) for its
consumer - an AI subagent that provisions browser pages and/or Odoo instances. Each test states
the business rule it locks in and fails for exactly one reason: that rule changed.

The NAMED DESIGN RULE under test (a future contributor must not invert it):
- INSTANCES (detached OS processes that outlive the session) = HARD BLOCK, and only on the
  PROVABLE ledger lie: a live, non-shared allocator lease owned by this run, still held at a turn
  end that neither reported a stopped run (`status: BLOCKED` / `NEEDS_CONTEXT`) nor forwarded
  INSTANCE_HANDLE inside its continuation fence (the named-catcher handoff exception). The gate is
  NOT keyed on the literal `DONE`: every other status, an out-of-enum value, and a turn carrying no
  machine-readable status at all are gated too. SubagentStop only.
- BROWSERS (pages/recordings that die WITH the session's MCP server) = ADVISORY ONLY, keyed on the
  fuzzy transcript open/close count, on BOTH SubagentStop and Stop. NEVER `decision: block`.

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


def _tu(name, file_path=None, command=None):
    inp = {}
    if file_path:
        inp["file_path"] = file_path
    if command:
        inp["command"] = command
    return {"type": "tool_use", "name": name, "input": inp}


def _text(s):
    return {"type": "text", "text": s}


def _cont(status, forward_handle=False):
    """A ```continuation fenced block with the given status; optionally forwarding INSTANCE_HANDLE."""
    body = f"```continuation\nstatus: {status}\n"
    if forward_handle:
        body += (
            "next:\n"
            "  - skill: odoo-coding\n"
            "    inputs: {INSTANCE_HANDLE: {db_name: x, lease_token: t, run_id: run-abc}}\n"
        )
    else:
        body += "produced: []\nnext: []\n"
    body += "```"
    return _text(body)


def _acquire(run_id="run-abc"):
    """An assistant Bash tool_use that self-provisions a lease under run_id (the provisioner proof)."""
    return _tu(
        "Bash",
        command=(
            f"python3 ${{CLAUDE_PLUGIN_ROOT}}/scripts/lib/allocator.py acquire "
            f"--series 17.0 --mode ephemeral --ports 1 --run-id {run_id}"
        ),
    )


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


def _run(tmp_path, lines, stop_hook_active=False, event="SubagentStop", leases=None):
    """Invoke enforce-teardown.sh with a crafted transcript + a seeded ledger; return (rc, parsed)."""
    home = tmp_path / "home"
    _seed_ledger(home, leases or [])  # empty ledger by default -> no instance ever matches
    tpath = tmp_path / "transcript.jsonl"
    tpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    stdin = json.dumps(
        {"transcript_path": str(tpath), "stop_hook_active": stop_hook_active,
         "hook_event_name": event}
    )
    import os
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    env["ODOO_AI_HOME"] = str(home)
    env["HOME"] = str(home)  # isolate any ~/.odoo-ai fallback
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
def test_navigate_only_plus_one_close_is_no_finding(tmp_path):
    """One-page-reuse discipline: navigate (reuse) + close, zero new_page -> nothing to nudge."""
    lines = [
        _line(content=[_tu("mcp__chrome-devtools__navigate_page")]),
        _line(content=[_tu("mcp__chrome-devtools__navigate_page")]),
        _line(content=[_tu("mcp__chrome-devtools__close_page")]),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is None, "navigate_page/close only (no new_page) must pass clean - no false nudge"


def test_two_new_pages_one_close_is_advisory_never_block(tmp_path):
    """2 new_page vs 1 close_page -> ADVISORY nudge naming the counts, never a block."""
    lines = [
        _line(content=[_tu("mcp__chrome-devtools__new_page")]),
        _line(content=[_tu("mcp__chrome-devtools__new_page")]),
        _line(content=[_tu("mcp__chrome-devtools__close_page")]),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is not None and out.get("continue") is True and "systemMessage" in out
    assert "decision" not in out, "a browser finding must NEVER hard-block"
    assert "2 new_page vs 1 close_page" in out["systemMessage"], (
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
    assert out is not None and out.get("continue") is True and "decision" not in out
    assert "2 new_page vs 1 close_page" in out["systemMessage"], (
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
    assert out is not None and out.get("continue") is True and "decision" not in out
    assert "record_page" in out["systemMessage"] and "stop_recording" in out["systemMessage"]


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
    assert out is not None and out.get("continue") is True and "decision" not in out
    assert "browser_close" in out["systemMessage"], "the nudge must name browser_close"


def test_playwright_video_pair_unbalanced_is_advisory(tmp_path):
    lines = [
        _line(content=[_tu("mcp__playwright__browser_navigate")]),
        _line(content=[_tu("mcp__playwright__browser_start_video")]),
        _line(content=[_tu("mcp__playwright__browser_close")]),  # closes page, but video not stopped
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines)
    assert out is not None and out.get("continue") is True and "decision" not in out
    assert "browser_start_video" in out["systemMessage"], (
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
    """Browser findings are advisory on BOTH SubagentStop and Stop."""
    lines = [
        _line(content=[_tu("mcp__chrome-devtools__new_page")]),
        _line(content=[_cont("DONE")]),
    ]
    _, out = _run(tmp_path, lines, event="Stop")
    assert out is not None and out.get("continue") is True and "decision" not in out


# --------------------------------------------------------------------------- #
# Instance check - BLOCKING, ledger-grounded, SubagentStop only. Fires at EVERY turn end except a
# BLOCKED / NEEDS_CONTEXT stop-report or a forwarded INSTANCE_HANDLE - never keyed on `DONE`.
# --------------------------------------------------------------------------- #
def test_live_owned_lease_at_done_without_handle_is_blocked(tmp_path):
    """The one hard block: a live non-shared lease owned by this run + DONE + no handoff -> BLOCK."""
    lines = [_line(content=[_acquire("run-abc")]), _line(content=[_cont("DONE")])]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc", token="ab" * 16)])
    assert out is not None and out.get("decision") == "block", (
        "a live owned instance lease at a DONE claim is a provable leak -> must block"
    )
    reason = out.get("reason", "")
    assert "ab" * 16 in reason, "the block reason must name the exact lease token"
    assert "release" in reason and "--run-id run-abc" in reason, (
        "the reason must give the deterministic release command so the agent can self-correct"
    )


def test_acquire_with_addons_override_still_correlates_a_run_id(tmp_path):
    """CS-C2's --addons-path-override flag must not break the teardown gate's
    run-id correlation. HARD CONSTRAINT 1: the hook derives the run-id by
    grepping the transcript for a literal `allocator.py` + `acquire` CALL line
    (enforce-teardown.sh :149-151); adding a flag to `acquire` is safe, but
    wrapping the call in a helper or renaming the verb is not - this test is
    the fence that makes that constraint testable."""
    acquire_with_override = _tu(
        "Bash",
        command=(
            "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py acquire "
            "--series 17.0 --mode ephemeral --ports 1 --run-id run-abc "
            "--addons-path-override /tmp/wt"
        ),
    )
    lines = [_line(content=[acquire_with_override]), _line(content=[_cont("DONE")])]
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
    """A run holding MORE THAN ONE live lease must get every token + release command, not just one."""
    lines = [_line(content=[_acquire("run-abc")]), _line(content=[_cont("DONE")])]
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
        _line(content=[_acquire("run-abc")]),
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
    lines = [_line(content=[_acquire("run-abc")]),
             _line(content=[_cont("DONE", forward_handle=True)])]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
    assert out is None, "a forwarded INSTANCE_HANDLE is a legitimate handoff - never block it"


def test_shared_lease_is_never_dropped_pass(tmp_path):
    """A shared lease is a many-reader render target, never a single-consumer drop -> pass."""
    lines = [_line(content=[_acquire("run-abc")]), _line(content=[_cont("DONE")])]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc", mode="shared")])
    assert out is None, "a shared lease must never be blocked as a leak"


def test_instance_block_is_subagentstop_only_not_stop(tmp_path):
    """Instance leaks hard-block only on SubagentStop; the main-agent Stop must never be trapped."""
    lines = [_line(content=[_acquire("run-abc")]), _line(content=[_cont("DONE")])]
    _, out = _run(tmp_path, lines, event="Stop", leases=[_lease(run_id="run-abc")])
    assert out is None or out.get("decision") != "block", (
        "the instance gate must not block the main agent on Stop (only browsers are advised there)"
    )


def test_foreign_run_lease_is_not_correlated_pass(tmp_path):
    """A live lease owned by a DIFFERENT run than this transcript's run_id must not block."""
    lines = [_line(content=[_acquire("run-abc")]), _line(content=[_cont("DONE")])]
    _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-OTHER")])
    assert out is None or out.get("decision") != "block", (
        "run_id correlation must be precise - a foreign run's lease is not this subagent's leak"
    )


def test_pure_consumer_echoing_forwarded_run_id_is_not_blocked(tmp_path):
    """BLOCKER regression: a subagent that RECEIVES a forwarded handle, runs NO allocator command,
    and merely quotes the forwarded run_id in its own report (exactly as agents/odoo-qa-tester.md
    instructs - 'this was forwarded to me, I am NOT releasing it') must NOT be hard-blocked. run_id
    is correlated ONLY from this subagent's own owning-action allocator commands (acquire/bind/
    heartbeat), never from free report text - so quoting a forwarded run_id can never trigger the
    one blocking gate in the system."""
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
    lines = [_line(content=[_acquire("run-abc")]), _line(content=[_cont("DONE")])]
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

    lines = [_line(content=[_acquire("run-abc")]), _line(content=[_cont("DONE")])]
    alive_but_ttl_expired = _lease(
        run_id="run-abc", pid=os.getpid(), host=socket.gethostname(), fresh=False,
    )
    _, out = _run(tmp_path, lines, leases=[alive_but_ttl_expired])
    assert out is not None and out.get("decision") == "block", (
        "a same-host lease whose owner pid is PROVABLY alive must block the DONE "
        "claim even when its heartbeat is far past ttl_s - liveness, not ttl, "
        "governs a same-host recorded pid"
    )


# The gate partitions the closed status enum into exactly two tiers, and every value must land in
# one of them:
#   STOP_REPORT      - a stopped run the contract itself permits to report a live lease. T4's last
#                      bullet makes BLOCKED the sanctioned outcome when teardown ITSELF failed
#                      ("report the lease token ... so the caller or allocator GC can reap it"), so
#                      hard-blocking these would trap the one path the contract gives that failure.
#   HANDOFF_OR_RELEASE - a turn that must have released the lease or forwarded it BY NAME (T4's
#                      only exception). A bare one of these with a live lease is an unforwarded
#                      lease, which is T4's definition of the leak.
STOP_REPORT = {"BLOCKED", "NEEDS_CONTEXT"}
HANDOFF_OR_RELEASE = {"DONE", "NEEDS_NEXT"}


def test_status_tiers_partition_the_closed_enum():
    """Structural guard, not a restatement: every value of the vocabulary SSOT's closed enum must
    be assigned to exactly one tier above. Adding a fifth status cannot silently inherit a pass -
    this test goes red until someone decides which tier it belongs to."""
    enum = set(_vocab("continuation_status"))
    assert STOP_REPORT | HANDOFF_OR_RELEASE == enum, (
        f"unassigned status value(s): {enum ^ (STOP_REPORT | HANDOFF_OR_RELEASE)!r}"
    )
    assert not (STOP_REPORT & HANDOFF_OR_RELEASE), "the two tiers must be disjoint"
    assert set(_declared_non_completion_statuses()) == enum - {"DONE"}


def test_non_done_status_never_blocks(tmp_path):
    """A STOP_REPORT status is a stopped run reporting honestly, not a completion claim - the gate
    must not fire. A BLOCKED agent that preserved its log path is behaving correctly, and one that
    is BLOCKED *because* its own release failed must be able to say so."""
    for status in sorted(STOP_REPORT):
        lines = [_line(content=[_acquire("run-abc")]), _line(content=[_cont(status)])]
        _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
        assert out is None or out.get("decision") != "block", (
            f"status={status} reports a stopped run - the instance gate must not block"
        )


def test_needs_next_without_a_forwarded_handle_blocks(tmp_path):
    """T4 gives a live lease exactly ONE exception: `status: NEEDS_NEXT` WITH `INSTANCE_HANDLE`
    forwarded to a named catcher. A bare NEEDS_NEXT is the "unnamed forward the token for later
    release" T4 names as the leak this contract exists to close - nobody has been handed the
    lease, so nobody releases it.
    MUST FAIL on the pre-fix hook (measured: NEEDS_NEXT was an unconditional pass)."""
    lines = [_line(content=[_acquire("run-abc")]), _line(content=[_cont("NEEDS_NEXT")])]
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
    lines = [_line(content=[_acquire("run-abc")]),
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
    lines = [_line(content=[_acquire("run-abc")]),
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
    lines = [_line(content=[_acquire("run-abc")]),
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
        lines = [_line(content=[_acquire("run-abc")]), _line(content=[_cont(status)])]
        _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
        assert out is not None and out.get("decision") == "block", (
            f"status={status} is not a declared non-completion value - it must not buy a pass "
            f"the literal DONE would not have got"
        )


def test_cosmetic_spelling_never_moves_a_status_out_of_its_tier(tmp_path):
    """False-positive fence for the complement predicate: the gate blocks everything that is
    neither a stop report nor a named handoff, so a cosmetic spelling - backticks, lowercase, a
    trailing comma, bold markers - must not cost a status the tier it declared. Both passing
    tiers are covered: the stop report alone, and NEEDS_NEXT with its handle forwarded."""
    for raw in ("`BLOCKED`", "blocked", "NEEDS_CONTEXT,", "**needs_context**"):
        lines = [_line(content=[_acquire("run-abc")]), _line(content=[_cont(raw)])]
        _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
        assert out is None or out.get("decision") != "block", (
            f"status={raw!r} reports a stopped run - decoration must not hard-block it"
        )
    for raw in ("`NEEDS_NEXT`", "needs_next", "**NEEDS_NEXT**"):
        lines = [_line(content=[_acquire("run-abc")]),
                 _line(content=[_cont(raw, forward_handle=True)])]
        _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
        assert out is None or out.get("decision") != "block", (
            f"status={raw!r} with a forwarded handle is the T4 handoff - decoration must not block"
        )


def test_no_status_on_main_agent_stop_never_blocks(tmp_path):
    """A main agent ends nearly every turn with no continuation block at all - that is normal,
    not a leak claim. The instance block stays SubagentStop-only; widening the status predicate
    must not leak the hard block onto Stop."""
    lines = [_line(content=[_acquire("run-abc")]),
             _line(content=[_text("Waiting for the background run to complete...")])]
    _, out = _run(tmp_path, lines, event="Stop", leases=[_lease(run_id="run-abc")])
    assert out is None or out.get("decision") != "block", (
        "the main agent's Stop must never be trapped by the no-status case"
    )


def test_no_status_without_a_live_lease_is_not_a_block(tmp_path):
    """The LEDGER is the trigger, the status only decides whether to consult it: a no-status
    turn whose run holds nothing live must pass silently (no ledger lie, nothing to release)."""
    lines = [_line(content=[_acquire("run-abc")]),
             _line(content=[_text("Waiting for the background run to complete...")])]
    _, out = _run(tmp_path, lines, leases=[])
    assert out is None, "no live owned lease means there is nothing to gate on"


def test_stop_hook_active_never_re_blocks(tmp_path):
    """stop_hook_active=true means we already forced one continue -> loop-safe silent pass."""
    lines = [_line(content=[_acquire("run-abc")]), _line(content=[_cont("DONE")])]
    _, out = _run(tmp_path, lines, stop_hook_active=True, leases=[_lease(run_id="run-abc")])
    assert out is None, "with stop_hook_active=true the hook must stay out of the way (no loop)"


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
    lines = [_line(content=[_acquire("run-abc")]), _line(content=[_cont("DONE")])]
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
    lines = [_line(content=[_acquire("run-abc")]), _line(content=[_cont("DONE")])]
    resumed = _lease(run_id="run-abc", token="ef" * 16)
    resumed.pop("parked_at", None)
    _, out = _run(tmp_path, lines, leases=[resumed])
    assert out is not None and out.get("decision") == "block", (
        "once the park keys are gone the lease is an ordinary live lease again and "
        "must be gated again"
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
    lines = [_line(content=[_acquire("run-abc")]), _line(content=[_cont("DONE")])]
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
def _run_gc(plugin_root: Path):
    import os
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    return subprocess.run(
        ["bash", str(GC_HOOK)], input="{}", capture_output=True, text=True, timeout=20, env=env
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


def test_session_end_gc_invokes_allocator_gc_when_present(tmp_path):
    """A present allocator.py must be invoked with the `gc` subcommand."""
    libdir = tmp_path / "scripts" / "lib"
    libdir.mkdir(parents=True)
    (libdir / "allocator.py").write_text(
        "import sys, pathlib\n"
        "pathlib.Path(pathlib.Path(__file__).parent / 'gc-called.txt')"
        ".write_text(' '.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    proc = _run_gc(tmp_path)
    assert proc.returncode == 0, f"stderr={proc.stderr!r}"
    marker = libdir / "gc-called.txt"
    assert _wait_for_file(marker), "session-end-gc.sh must invoke the allocator"
    assert marker.read_text(encoding="utf-8").strip() == "gc", (
        "the allocator must be called with exactly the `gc` subcommand"
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
    assert gc_marker.read_text(encoding="utf-8").strip() == "gc"

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
    assert any("parse-continuation.sh" in c for c in subagent)


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
    own header - must each name the pass-set (a BLOCKED / NEEDS_CONTEXT stop-report, or a forwarded
    INSTANCE_HANDLE) and must not present DONE as the key."""
    manifest = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    for label, text in (
        ("hooks/hooks.json description", manifest.get("description", "")),
        ("hooks/enforce-teardown.sh header", HOOK.read_text(encoding="utf-8")),
    ):
        norm = " ".join(text.split())
        assert "BLOCKED" in norm and "NEEDS_CONTEXT" in norm, (
            f"{label}: must name BOTH stop-report statuses that pass the gate"
        )
        assert "INSTANCE_HANDLE" in norm, (
            f"{label}: must name the forwarded-handle handoff as the gate's other exception"
        )
        assert re.search(r"\bNOT keyed|NEVER on the literal|not keyed\b", norm), (
            f"{label}: must state explicitly that the gate is NOT keyed on the literal DONE - "
            "without it, the DONE-only reading comes straight back"
        )
