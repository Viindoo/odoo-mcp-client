"""Behavioral guard for hooks/report-terminal-status.sh (SubagentStop strand telemetry - M2).

This hook is the ONLY mechanical evidence in the plugin that a stranded subagent (one that
ends its turn without a terminal status, or fires a tool_use it never gets a result for) is
actually happening at runtime - every other guard in the remediation only proves the PROSE
changed. It proves a RATE, not a cause: it is a pure side-effecting observer that appends
ONE line to a rolling counter file under the machine-global state root when either strand
signature is present, and otherwise stays completely silent.

Business rules protected, NOT the implementation:

  - **S1 (strand).** The transcript's FINAL assistant turn carries no `status:` from
    DONE|NEEDS_NEXT|BLOCKED|NEEDS_CONTEXT inside a fenced ```continuation block -> one line
    appended, tagged `signature=S1`.
  - **S2 (unexecuted tool_use).** A `tool_use` id in that same final assistant turn with no
    matching `tool_use_id` in any `tool_result` anywhere in the transcript -> one line
    appended, tagged `signature=S2` (or `signature=S1,S2` when both fire together).
  - **A clean stop (terminal status present, every tool_use resolved) writes NOTHING.**
  - **Never blocks, never emits stdout JSON.** This hook is an observer only - unlike its
    SubagentStop siblings (enforce-grounding.sh, parse-continuation.sh) it never returns
    `{decision: ...}` or `{continue: ...}`; stdout is always empty and the exit code is
    always 0.
  - **Fails open on every uncertainty**: missing jq, an unresolvable state root (no
    CLAUDE_PLUGIN_ROOT, or the resolved root is not writable), or a loop re-entry
    (stop_hook_active=true) all degrade to a silent no-write, never a crash and never a
    guessed write location.

Hermetic: every test points ODOO_AI_HOME/HOME at a throwaway tmp_path - never the real
$HOME, never this repo's own state.

Run with: python3 -m pytest tests/test_report_terminal_status.py -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / "plugins" / "odoo-ai-agents"
HOOK = PLUGIN_ROOT / "hooks" / "report-terminal-status.sh"
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"

_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or _BASH is None,
    reason="report-terminal-status.sh needs jq + bash; absent here (the hook itself degrades to pass)",
)


# --------------------------------------------------------------------------- #
# helpers - transcript line builders (mirror the real Claude Code JSONL shape:
# {"type": "assistant"|"user", "message": {"role": ..., "content": [...]}})
# --------------------------------------------------------------------------- #
def _assistant(*content_blocks) -> str:
    return json.dumps({"type": "assistant", "message": {"role": "assistant", "content": list(content_blocks)}})


def _user(*content_blocks) -> str:
    return json.dumps({"type": "user", "message": {"role": "user", "content": list(content_blocks)}})


def _text(s: str) -> dict:
    return {"type": "text", "text": s}


def _tool_use(tool_id: str, name: str = "Bash") -> dict:
    return {"type": "tool_use", "id": tool_id, "name": name, "input": {}}


def _tool_result(tool_id: str) -> dict:
    return {"type": "tool_result", "tool_use_id": tool_id, "content": "ok", "is_error": False}


def _continuation(status: str) -> str:
    return f"done.\n```continuation\nstatus: {status}\nproduced: []\nnext: []\n```"


def _env(home: Path, **extra) -> dict:
    """A clean subprocess env: throwaway $ODOO_AI_HOME/$HOME, no override vars leaking in
    from the invoking shell, plugin root pinned - fully hermetic."""
    e = dict(os.environ)
    for var in ("ODOO_AI_HOME", "ODOO_AI_INSTANCES", "ODOO_AI_PROJECT_DIR", "ODOO_AI_WORKTREE_DIR"):
        e.pop(var, None)
    e["ODOO_AI_HOME"] = str(home)
    e["HOME"] = str(home)
    e["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    e.update(extra)
    return e


def _write_transcript(tmp_path: Path, lines: list[str]) -> Path:
    tpath = tmp_path / "transcript.jsonl"
    tpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tpath


def _run_hook(env: dict, transcript_path: Path | None = None, stop_hook_active: bool = False):
    payload = {"stop_hook_active": stop_hook_active}
    if transcript_path is not None:
        payload["transcript_path"] = str(transcript_path)
    proc = subprocess.run(
        [_BASH, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
        timeout=30, env=env,
    )
    return proc


def _counter_file(home: Path) -> Path:
    return home / "telemetry" / "strand-events.log"


# --------------------------------------------------------------------------- #
# Existence / static sanity
# --------------------------------------------------------------------------- #
def test_hook_exists_and_parses():
    assert HOOK.exists(), f"hook not found at {HOOK}"
    r = subprocess.run([_BASH, "-n", str(HOOK)], capture_output=True, text=True)
    assert r.returncode == 0, f"report-terminal-status.sh failed bash -n: {r.stderr}"


# --------------------------------------------------------------------------- #
# The business rule: clean stop writes nothing
# --------------------------------------------------------------------------- #
def test_clean_stop_with_terminal_status_and_resolved_tool_writes_nothing(tmp_path):
    """A subagent that resolved its tool_use and closed with a terminal status must leave the
    counter file untouched - the hook must not fire on honest work."""
    home = tmp_path / "home"
    env = _env(home)
    transcript = _write_transcript(tmp_path, [
        _assistant(_text("Working on it."), _tool_use("toolu_1")),
        _user(_tool_result("toolu_1")),
        _assistant(_text(_continuation("DONE"))),
    ])

    proc = _run_hook(env, transcript)

    assert proc.returncode == 0
    assert proc.stdout.strip() == "", "this hook must never emit stdout JSON - it only observes"
    assert not _counter_file(home).exists(), "a clean terminal stop must not append a counter line"


@pytest.mark.parametrize("status", ["NEEDS_NEXT", "BLOCKED", "NEEDS_CONTEXT"])
def test_clean_stop_accepts_every_terminal_status(tmp_path, status):
    home = tmp_path / "home"
    env = _env(home)
    transcript = _write_transcript(tmp_path, [_assistant(_text(_continuation(status)))])

    proc = _run_hook(env, transcript)

    assert proc.returncode == 0
    assert not _counter_file(home).exists(), f"status={status} is terminal - must not be counted"


# --------------------------------------------------------------------------- #
# S1 - strand: final assistant turn carries no terminal status
# --------------------------------------------------------------------------- #
def test_s1_no_continuation_block_appends_one_line(tmp_path):
    home = tmp_path / "home"
    env = _env(home)
    transcript = _write_transcript(tmp_path, [
        _assistant(_text("I'm done here, waiting for the child agent to report back.")),
    ])

    proc = _run_hook(env, transcript)

    assert proc.returncode == 0
    assert proc.stdout.strip() == ""
    counter = _counter_file(home)
    assert counter.exists(), "S1 (no terminal status) must append a counter line"
    lines = counter.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "signature=S1" in lines[0]
    assert "S2" not in lines[0].split("signature=")[1]


def test_s1_status_outside_the_four_terminal_values_still_counts(tmp_path):
    """A `status:` line present but NOT one of DONE|NEEDS_NEXT|BLOCKED|NEEDS_CONTEXT (e.g. a
    freeform 'waiting') is exactly the state the contract forbids - must still count as S1."""
    home = tmp_path / "home"
    env = _env(home)
    transcript = _write_transcript(tmp_path, [_assistant(_text(_continuation("WAITING")))])

    proc = _run_hook(env, transcript)

    assert proc.returncode == 0
    counter = _counter_file(home)
    assert counter.exists()
    assert "signature=S1" in counter.read_text(encoding="utf-8")


def test_s1_counter_rolls_across_multiple_stops(tmp_path):
    """'Rolling counter' means it accumulates - a second stranded stop appends a SECOND line,
    it does not overwrite the first."""
    home = tmp_path / "home"
    env = _env(home)
    transcript = _write_transcript(tmp_path, [_assistant(_text("still going"))])

    _run_hook(env, transcript)
    _run_hook(env, transcript)

    lines = _counter_file(home).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2, "two independent stranded stops must append two lines, not one"


# --------------------------------------------------------------------------- #
# S2 - unexecuted tool_use: final turn's tool_use id never gets a tool_result
# --------------------------------------------------------------------------- #
def test_s2_unresolved_tool_use_in_final_turn_appends_one_line(tmp_path):
    """A terminal status IS present (so this is not also S1) but the SAME final turn also
    fired a tool_use that never got a tool_result anywhere in the transcript - the
    stranding fingerprint - isolated from S1 to prove the two signatures are detected
    independently."""
    home = tmp_path / "home"
    env = _env(home)
    transcript = _write_transcript(tmp_path, [
        _assistant(_text(_continuation("DONE")), _tool_use("toolu_bg1", name="Agent")),
    ])

    proc = _run_hook(env, transcript)

    assert proc.returncode == 0
    assert proc.stdout.strip() == ""
    counter = _counter_file(home)
    assert counter.exists(), "S2 (unexecuted tool_use) must append a counter line"
    line = counter.read_text(encoding="utf-8").splitlines()[0]
    assert "signature=S2" in line
    assert "S1" not in line.split("signature=")[1]


def test_s2_tool_use_resolved_by_a_later_result_does_not_count(tmp_path):
    """The mirror image of the S2 test: the SAME shape, but a tool_result for that id DOES
    appear later in the transcript - a real Claude Code run interleaves tool_use with its own
    tool_result before the NEXT assistant turn - so this must not be misdetected as a strand
    just because it isn't wrapped as the model helper expects."""
    home = tmp_path / "home"
    env = _env(home)
    transcript = _write_transcript(tmp_path, [
        _assistant(_tool_use("toolu_2")),
        _user(_tool_result("toolu_2")),
        _assistant(_text(_continuation("DONE"))),
    ])

    proc = _run_hook(env, transcript)

    assert proc.returncode == 0
    assert not _counter_file(home).exists()


def test_both_signatures_combine_into_one_comma_joined_line(tmp_path):
    """Final turn has neither a terminal status NOR a resolved tool_use -> both signatures
    fire on the SAME stop and must produce exactly ONE line naming both, not two lines."""
    home = tmp_path / "home"
    env = _env(home)
    transcript = _write_transcript(tmp_path, [
        _assistant(_text("dispatching now"), _tool_use("toolu_3", name="Agent")),
    ])

    proc = _run_hook(env, transcript)

    assert proc.returncode == 0
    lines = _counter_file(home).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, "one stop, both signatures -> exactly one appended line"
    assert "S1" in lines[0] and "S2" in lines[0]


# --------------------------------------------------------------------------- #
# Resilience - never blocks, never crashes, never writes to a guessed location
# --------------------------------------------------------------------------- #
def test_loop_guard_stop_hook_active_suppresses_write(tmp_path):
    """stop_hook_active=true means we already forced one continue - the hook must not double
    count the same stop."""
    home = tmp_path / "home"
    env = _env(home)
    transcript = _write_transcript(tmp_path, [_assistant(_text("still going"))])

    proc = _run_hook(env, transcript, stop_hook_active=True)

    assert proc.returncode == 0
    assert not _counter_file(home).exists()


def test_missing_transcript_degrades_silently(tmp_path):
    home = tmp_path / "home"
    env = _env(home)

    proc = _run_hook(env, transcript_path=None)

    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_empty_stdin_degrades_silently(tmp_path):
    home = tmp_path / "home"
    env = _env(home)
    proc = subprocess.run([_BASH, str(HOOK)], input="", capture_output=True, text=True,
                           timeout=30, env=env)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_missing_jq_degrades_silently_without_writing(tmp_path):
    """The hook's very first check is `command -v jq`. With jq unresolvable on PATH, it must
    fail open (exit 0, no write) rather than crash or hang."""
    home = tmp_path / "home"
    empty_path_dir = tmp_path / "empty-path"
    empty_path_dir.mkdir()
    env = _env(home, PATH=str(empty_path_dir))
    transcript = _write_transcript(tmp_path, [_assistant(_text("still going"))])

    proc = _run_hook(env, transcript)

    assert proc.returncode == 0
    assert proc.stdout.strip() == ""
    assert not _counter_file(home).exists()


def test_missing_plugin_root_degrades_without_writing(tmp_path):
    """CLAUDE_PLUGIN_ROOT unset means the resolver script can't be located - the hook must not
    fall back to a guessed path (unlike the read-only parse-continuation.sh advisory-glob
    exception, this is a WRITE call site: snippets/state-root-resolution.md forbids a silent
    wrong-location write) - it must simply skip the write."""
    home = tmp_path / "home"
    env = _env(home)
    del env["CLAUDE_PLUGIN_ROOT"]
    transcript = _write_transcript(tmp_path, [_assistant(_text("still going"))])

    proc = _run_hook(env, transcript)

    assert proc.returncode == 0
    assert proc.stdout.strip() == ""
    assert not (home / "telemetry").exists(), "must not create telemetry/ anywhere when unresolvable"


def test_unwritable_state_root_degrades_without_crashing(tmp_path):
    """$ODOO_AI_HOME resolves to a path whose PARENT COMPONENT is a regular file (mkdir -p
    must fail) - the hook must degrade to a silent no-write, not crash or hard-fail."""
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    home = blocker / "home"  # can never be created - "not-a-directory" is a file
    env = _env(home)
    transcript = _write_transcript(tmp_path, [_assistant(_text("still going"))])

    proc = _run_hook(env, transcript)

    assert proc.returncode == 0, "an unwritable state root must never crash or non-zero-exit the hook"
    assert proc.stdout.strip() == ""


def test_malformed_transcript_degrades_silently(tmp_path):
    """A transcript with no parseable assistant JSON at all - never assume a strand when the
    evidence itself is uncertain."""
    home = tmp_path / "home"
    env = _env(home)
    tpath = tmp_path / "transcript.jsonl"
    tpath.write_text("not json\n{also not json\n", encoding="utf-8")

    proc = _run_hook(env, tpath)

    assert proc.returncode == 0
    assert not _counter_file(home).exists()


# --------------------------------------------------------------------------- #
# hooks.json registration
# --------------------------------------------------------------------------- #
def _commands_for(event):
    reg = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    cmds = []
    for group in reg["hooks"].get(event, []):
        for h in group.get("hooks", []):
            cmds.append(h.get("command", ""))
    return cmds


def test_hooks_json_registers_report_terminal_status_on_subagent_stop():
    subagent = _commands_for("SubagentStop")
    assert any("report-terminal-status.sh" in c for c in subagent), (
        "hooks.json must register report-terminal-status.sh under SubagentStop"
    )


def test_hooks_json_still_wires_the_other_three_subagent_stop_hooks():
    """Additive sibling - must not displace enforce-grounding.sh / enforce-teardown.sh /
    parse-continuation.sh."""
    subagent = _commands_for("SubagentStop")
    assert any("enforce-grounding.sh" in c for c in subagent)
    assert any("enforce-teardown.sh" in c for c in subagent)
    assert any("parse-continuation.sh" in c for c in subagent)
