"""Behavioral guard for hooks/enforce-teardown.sh + hooks/session-end-gc.sh (L1.6 + L1.3).

These protect the BEHAVIOR contract of the resource-teardown enforcement (ETHOS#11) for its
consumer - an AI subagent that provisions browser pages and/or Odoo instances. Each test states
the business rule it locks in and fails for exactly one reason: that rule changed.

The NAMED DESIGN RULE under test (a future contributor must not invert it):
- INSTANCES (detached OS processes that outlive the session) = HARD BLOCK, and only on the
  PROVABLE ledger lie: a live, non-shared allocator lease owned by this run at a `status: DONE`
  claim, with no INSTANCE_HANDLE forwarded (the named-catcher handoff exception). SubagentStop only.
- BROWSERS (pages/recordings that die WITH the session's MCP server) = ADVISORY ONLY, keyed on the
  fuzzy transcript open/close count, on BOTH SubagentStop and Stop. NEVER `decision: block`.

Everything degrades to a silent pass on uncertainty (this is the one hard gate; a false block halts
real work, so it prefers a false-negative over a false-positive).

Run with: python3 -m pytest tests/test_enforce_teardown.py -v
"""
import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / "plugins" / "odoo-ai-agents"
HOOK = PLUGIN_ROOT / "hooks" / "enforce-teardown.sh"
GC_HOOK = PLUGIN_ROOT / "hooks" / "session-end-gc.sh"
ALLOC = PLUGIN_ROOT / "scripts" / "lib" / "allocator.py"
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"

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
# Instance check - BLOCKING, ledger-grounded, SubagentStop only, DONE only
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


def test_non_done_status_never_blocks(tmp_path):
    """BLOCKED / NEEDS_NEXT are not a completion claim - the DONE-gate must not fire."""
    for status in ("BLOCKED", "NEEDS_NEXT", "NEEDS_CONTEXT"):
        lines = [_line(content=[_acquire("run-abc")]), _line(content=[_cont(status)])]
        _, out = _run(tmp_path, lines, leases=[_lease(run_id="run-abc")])
        assert out is None or out.get("decision") != "block", (
            f"status={status} is not DONE - the instance gate must not block"
        )


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
    assert marker.is_file(), "session-end-gc.sh must invoke the allocator"
    assert marker.read_text(encoding="utf-8").strip() == "gc", (
        "the allocator must be called with exactly the `gc` subcommand"
    )


def test_session_end_gc_wires_reap_orphans_list_only_and_persists_the_log(tmp_path):
    """#185: `reap-orphans` existed but had ZERO caller anywhere in the plugin -
    the mechanism was built and unreachable. This hook is now the discovery-half
    caller: it must invoke `reap-orphans` in its DEFAULT list-only mode (never
    `--yes` - that stays a human's explicit, separate action) and PERSIST the
    output (unlike `gc` above, which is intentionally /dev/null'd) so the
    candidate list is actually reviewable by someone."""
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
    assert gc_marker.is_file(), "gc must still be invoked (unchanged L1.3 behavior)"
    assert gc_marker.read_text(encoding="utf-8").strip() == "gc"

    reap_marker = libdir / "reap-orphans-called.txt"
    assert reap_marker.is_file(), "session-end-gc.sh must now invoke reap-orphans (#185)"
    reap_argv = reap_marker.read_text(encoding="utf-8").strip()
    assert reap_argv == "reap-orphans", (
        f"reap-orphans must be called with NO extra flags - list-only default, "
        f"never --yes from this unattended hook; got argv={reap_argv!r}"
    )

    log_path = runtime_dir / "reap-orphans-candidates.log"
    assert log_path.is_file(), (
        "the reap-orphans discovery output must be PERSISTED (not /dev/null'd like gc) "
        "so a human can actually review the candidate list later"
    )
    log_text = log_path.read_text(encoding="utf-8")
    assert "REAP_CANDIDATE" in log_text and "list-only" in log_text


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
