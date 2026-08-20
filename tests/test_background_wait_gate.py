"""Behavior gate for the unwakeable background-shell wait (hooks/enforce-background-wait.sh plus
the one prose home that declares the rule).

## The behavior protected

A dispatched agent that starts a shell command in the background and then ENDS ITS TURN loses that
command's result. The Bash tool answers a backgrounded command with "You will be notified when it
completes."; that receipt is written for the ROOT conversation, where it holds. A SubagentStop IS
the end of that dispatch - nothing resumes a dispatched agent for a background shell command - so
the caller receives whatever text the subagent wrote before stopping, and the command finishes with
nobody waiting.

The contrast that makes the narrow scope load-bearing: an AGENT child DOES wake the launcher that
stopped for it. So the gate must fire on a live `type: "shell"` background task and never on a
`type: "subagent"` one (which includes the stopping subagent's own entry), and never on the root.

Equally load-bearing: backgrounding itself is a WORKING pattern here. A subagent may start a long
command and drive it to a result with foreground calls INSIDE THE SAME TURN (that is how
`odoo-instance-ops` runs every long Odoo build). Nothing in this file may make that shape illegal -
only the TURN END with the command still live is refused.

## What the payload actually carries (measured, not assumed)

A real `SubagentStop` payload was captured by registering a stdin-dumping hook in a throwaway
`claude -p` session and reproducing the defect there. It carries: `session_id`, `transcript_path`
(the SESSION transcript), `cwd`, `prompt_id`, `permission_mode`, `hook_event_name`,
`stop_hook_active`, `last_assistant_message`, `agent_id`, `agent_type`, `agent_transcript_path`,
`session_crons`, and `background_tasks` - an array of
`{id, type: "subagent"|"shell", status, description, command?, agent_type?}` covering the WHOLE
session. A root `Stop` payload carries the same `background_tasks` but NONE of `agent_id` /
`agent_type` / `agent_transcript_path`. A background shell task that has FINISHED is removed from
the array outright, so "still listed with status running" is the liveness test.

## Red-before-green

`test_the_other_subagentstop_hooks_do_not_catch_this_shape` is the committed form of the pre-fix
measurement: the same defect payload is fed to every OTHER SubagentStop hook and none of them
returns a block. That was the tree's state before this gate existed, and it is what made the stall
silent. Every behavior test below then goes red for a real reason: delete the type filter and
`test_a_live_agent_child_is_never_gated` fails; delete the ownership correlation and
`test_a_live_shell_task_this_subagent_did_not_start_is_not_its_problem` fails; delete the
root guard and `test_a_root_shaped_stop_is_never_gated` fails.

## STATED RESIDUAL FALSE NEGATIVES

1. A command backgrounded OUTSIDE the Bash tool's background flag - a bare `&`, `setsid`, `nohup`,
   or a `disown` inside an ordinary foreground call - never becomes a task id and never appears in
   `background_tasks`. It is invisible to a task-id check and always will be.
2. Only `"status": "running"` counts as live. A live task carrying some other status label passes.
3. Ownership is proved from the subagent's own transcript text. A task the ROOT started and this
   subagent merely QUOTED would correlate; the refusal is still actionable, but the ownership claim
   would be wrong.
4. The prose half is a LEXICAL whole-tree scan over normalized whitespace. A promise phrased in
   wording neither vocabulary anticipates escapes it. It proves the harmful INSTRUCTION is absent
   from the prose an agent is handed; it can never prove an agent obeys the rule.

Run: python -m pytest tests/test_background_wait_gate.py -v
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS = REPO_ROOT / "plugins"
ODOO_PLUGIN = PLUGINS / "odoo-ai-agents"
HOOKS_DIR = ODOO_PLUGIN / "hooks"
HOOKS_JSON = HOOKS_DIR / "hooks.json"
GATE = HOOKS_DIR / "enforce-background-wait.sh"
SSOT = ODOO_PLUGIN / "snippets" / "spawner-completion-contract.md"
ROOT_DOCS = REPO_ROOT / "docs"

# The tool_result text the Bash tool hands back for a backgrounded command, verbatim in shape.
_RECEIPT = (
    "Command running in background with ID: {tid}. Output is being written to: {out}. "
    "You will be notified when it completes. To check interim output, use Read on that file path."
)


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #
def _transcript(tmp_path: Path, task_ids: list[str], name: str = "agent-x.jsonl") -> Path:
    """A subagent transcript whose Bash tool_results hand it each of `task_ids`."""
    path = tmp_path / name
    lines = [json.dumps({
        "type": "assistant",
        "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "Bash",
             "input": {"command": "sleep 90", "run_in_background": True}},
        ]},
    })]
    for tid in task_ids:
        lines.append(json.dumps({
            "type": "user",
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1",
                 "content": _RECEIPT.format(tid=tid, out=f"/srv/run/tasks/{tid}.output")},
            ]},
        }))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _shell_task(tid: str, status: str = "running", command: str = "make test") -> dict:
    return {"id": tid, "type": "shell", "status": status,
            "description": "long build", "command": command}


def _agent_task(tid: str, status: str = "running") -> dict:
    return {"id": tid, "type": "subagent", "status": status,
            "description": "child agent", "agent_type": "general-purpose"}


def _subagent_payload(transcript: Path | None, tasks: list[dict], **over) -> dict:
    payload = {
        "session_id": "s-1",
        "transcript_path": "/srv/run/session.jsonl",
        "cwd": "/repos/demo",
        "permission_mode": "default",
        "hook_event_name": "SubagentStop",
        "stop_hook_active": False,
        "agent_id": "a-child-1",
        "agent_type": "general-purpose",
        "last_assistant_message": "WAITING - I have NOT yet read its output.",
        "background_tasks": tasks,
        "session_crons": [],
    }
    if transcript is not None:
        payload["agent_transcript_path"] = str(transcript)
    payload.update(over)
    return payload


def _root_payload(tasks: list[dict], **over) -> dict:
    """A root `Stop` payload: same session-wide task list, no agent identity at all."""
    payload = {
        "session_id": "s-1",
        "transcript_path": "/srv/run/session.jsonl",
        "cwd": "/repos/demo",
        "permission_mode": "default",
        "hook_event_name": "Stop",
        "stop_hook_active": False,
        "last_assistant_message": "WAITING",
        "background_tasks": tasks,
        "session_crons": [],
    }
    payload.update(over)
    return payload


def _run(payload, script: Path = GATE) -> tuple[int, str]:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    proc = subprocess.run(
        ["bash", str(script)],
        input=raw, capture_output=True, text=True, timeout=30,
        cwd=str(REPO_ROOT), env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/tmp",
                                 "CLAUDE_PLUGIN_ROOT": str(ODOO_PLUGIN)},
    )
    return proc.returncode, proc.stdout


def _decision(stdout: str) -> str:
    if not stdout.strip():
        return ""
    return json.loads(stdout.strip().splitlines()[-1]).get("decision", "")


def _reason(stdout: str) -> str:
    return json.loads(stdout.strip().splitlines()[-1]).get("reason", "")


def test_gate_script_exists_and_is_wired_under_subagentstop_only():
    """Floor: without registration the script is inert, and wiring it under `Stop` would gate the
    root - the one context that IS woken when a background command finishes."""
    assert GATE.is_file(), f"{GATE} is missing - every behavior test below is vacuous"
    wiring = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]

    def _commands(event: str) -> list[str]:
        return [h["command"] for group in wiring.get(event, []) for h in group.get("hooks", [])]

    assert any(GATE.name in c for c in _commands("SubagentStop")), (
        "enforce-background-wait.sh must be registered under SubagentStop"
    )
    for event in ("Stop", "PreToolUse", "SessionEnd", "SessionStart", "UserPromptSubmit"):
        assert not any(GATE.name in c for c in _commands(event)), (
            f"enforce-background-wait.sh must NOT be wired under {event} - only a SUBAGENT's stop "
            "loses a background command's result"
        )


# --------------------------------------------------------------------------- #
# 1. The refusal - a subagent-shaped stop holding its own live background shell command
# --------------------------------------------------------------------------- #
def test_a_subagent_stopping_with_its_own_live_background_command_is_refused(tmp_path):
    """The measured defect, end to end."""
    t = _transcript(tmp_path, ["bvld2f72c"])
    rc, out = _run(_subagent_payload(t, [_agent_task("a-child-1"), _shell_task("bvld2f72c")]))
    assert rc == 0, "a hook must never exit non-zero - it speaks through stdout JSON"
    assert _decision(out) == "block", (
        "a subagent ending its turn with its own background shell command still running must be "
        "refused - stopping here delivers the result to nobody"
    )


def test_the_refusal_names_the_command_its_output_file_and_a_move_for_each(tmp_path):
    """A refusal an agent cannot act on is noise. It must carry: the fact that no wake is coming,
    the task's own output path (so 'read it now' is executable), and the three exits."""
    t = _transcript(tmp_path, ["bq1"])
    _, out = _run(_subagent_payload(t, [_shell_task("bq1", command="make test")]))
    reason = _reason(out)
    low = reason.lower()

    assert "/srv/run/tasks/bq1.output" in reason, (
        "the refusal must name the task's OWN output file, read back from the subagent's "
        "transcript - without it 'read it now' is not an executable instruction"
    )
    assert "make test" in reason, "the refusal must name the command that is still running"
    assert "nothing resumes a dispatched agent" in low, (
        "the refusal must state the fact that overrides the Bash receipt: no wake is coming"
    )
    assert "you will be notified when it completes" in low, (
        "the refusal must quote the receipt it is overriding, or the agent trusts the line it can "
        "see over the rule it cannot"
    )
    for move in ("read it now", "wait for it in this turn", "stop it"):
        assert move in low, f"the refusal must offer the {move!r} exit"
    assert "blocked" in low, (
        "the refusal must name the reporting exit for a result that cannot be had this turn"
    )


# --------------------------------------------------------------------------- #
# 2. The narrow scope - what must NEVER be gated
# --------------------------------------------------------------------------- #
def test_a_root_shaped_stop_is_never_gated(tmp_path):
    """The root IS woken when a background command completes. Gating it would refuse a stop that
    loses nothing. Same live task, root-shaped payload."""
    rc, out = _run(_root_payload([_agent_task("a-child-1"), _shell_task("bvld2f72c")]))
    assert rc == 0 and out.strip() == "", (
        "a root `Stop` payload must pass silently - the root is resumed when the command finishes"
    )


def test_the_root_guard_is_load_bearing_independently_of_the_transcript_check(tmp_path):
    """A real root `Stop` payload also lacks `agent_transcript_path`, so the ownership check would
    stop it too - defense in depth that would hide a deleted root guard. This probe isolates the
    guard by SYNTHESIZING a root-shaped payload that nonetheless carries an owning transcript:
    only `hook_event_name != SubagentStop` and the absent `agent_id` can refuse to gate it."""
    t = _transcript(tmp_path, ["bq1"])
    payload = _root_payload([_shell_task("bq1")])
    payload["agent_transcript_path"] = str(t)
    rc, out = _run(payload)
    assert rc == 0 and out.strip() == "", (
        "the root must never be gated on the event name and the missing agent identity alone - "
        "the root IS woken when a background command finishes"
    )


def test_a_subagentstop_payload_without_agent_identity_passes(tmp_path):
    """No caller identity is an unknown shape, not a subagent. Fail open."""
    t = _transcript(tmp_path, ["bq1"])
    rc, out = _run(_subagent_payload(t, [_shell_task("bq1")], agent_id=""))
    assert rc == 0 and out.strip() == ""


def test_a_live_agent_child_is_never_gated(tmp_path):
    """An agent child DOES deliver to a launcher that stopped for it - that is the sanctioned
    nested-dispatch shape. Only `type: shell` entries lose their result."""
    t = _transcript(tmp_path, ["bq1"])
    rc, out = _run(_subagent_payload(t, [_agent_task("a-child-1"), _agent_task("a-grandchild")]))
    assert rc == 0 and out.strip() == "", (
        "a stop holding only agent children must pass - including the stopping subagent's own "
        "entry, which the payload always lists as a running `subagent` task"
    )


def test_the_type_filter_is_load_bearing_independently_of_the_ownership_check(tmp_path):
    """Two independent guards keep an agent child out: `type != "shell"`, and the ownership
    correlation (an agent launch never produces a Bash background receipt, so a child's id is
    never in the transcript). Defense in depth hides a deletion - remove the type filter and the
    realistic test above still passes, because ownership catches it.

    So this probe isolates the filter: it SYNTHESIZES an id collision, putting the agent child's
    id into the subagent's transcript as though it had been handed back as a background task.
    Nothing but the type filter can refuse to gate this payload."""
    child = "a-grandchild"
    t = _transcript(tmp_path, [child])
    rc, out = _run(_subagent_payload(t, [_agent_task(child)]))
    assert rc == 0 and out.strip() == "", (
        "a `type: subagent` entry must be skipped on its type alone - an agent child DOES wake "
        "the launcher that stopped for it, at any depth"
    )


def test_a_live_shell_task_this_subagent_did_not_start_is_not_its_problem(tmp_path):
    """`background_tasks` is SESSION-wide: a command the ROOT started is listed here too. Refusing
    this subagent for it would demand a fix it cannot make."""
    t = _transcript(tmp_path, ["mine-1"])
    rc, out = _run(_subagent_payload(t, [_shell_task("someone-elses-task")]))
    assert rc == 0 and out.strip() == "", (
        "a live shell task absent from this subagent's own transcript must not gate it"
    )


def test_a_finished_background_command_passes(tmp_path):
    """The working pattern: background, then wait for it inside the same turn. A finished task is
    REMOVED from `background_tasks`, so the compliant subagent's payload lists no shell entry."""
    t = _transcript(tmp_path, ["bq1"])
    rc, out = _run(_subagent_payload(t, [_agent_task("a-child-1")]))
    assert rc == 0 and out.strip() == "", (
        "backgrounding then waiting in-turn must stay legal - this gate refuses the turn end, "
        "never the backgrounding"
    )


def test_a_shell_task_with_a_non_running_status_passes(tmp_path):
    t = _transcript(tmp_path, ["bq1"])
    rc, out = _run(_subagent_payload(t, [_shell_task("bq1", status="completed")]))
    assert rc == 0 and out.strip() == ""


# --------------------------------------------------------------------------- #
# 3. Fail open on every uncertainty
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("label,mutate", [
    ("loop-guard", lambda p: p.update({"stop_hook_active": True})),
    ("no background_tasks key", lambda p: p.pop("background_tasks", None)),
    ("background_tasks is null", lambda p: p.update({"background_tasks": None})),
    ("background_tasks is an object", lambda p: p.update({"background_tasks": {"a": 1}})),
    ("background_tasks is empty", lambda p: p.update({"background_tasks": []})),
    ("no hook_event_name", lambda p: p.pop("hook_event_name", None)),
    ("unknown hook_event_name", lambda p: p.update({"hook_event_name": "SomethingNew"})),
    ("task entries are not objects", lambda p: p.update({"background_tasks": ["x", 3]})),
    ("task has no type", lambda p: p.update({"background_tasks": [{"id": "bq1", "status": "running"}]})),
])
def test_every_uncertain_payload_passes(tmp_path, label, mutate):
    """A guard that breaks a working run is worse than the stall it prevents."""
    t = _transcript(tmp_path, ["bq1"])
    payload = _subagent_payload(t, [_shell_task("bq1")])
    mutate(payload)
    rc, out = _run(payload)
    assert rc == 0 and out.strip() == "", f"{label}: must fail open, got {out!r}"


@pytest.mark.parametrize("raw", ["", "   ", "not json at all", "[]", "null", '{"a":'])
def test_unparseable_stdin_passes(raw):
    rc, out = _run(raw)
    assert rc == 0 and out.strip() == "", f"unparseable stdin {raw!r} must pass, got {out!r}"


def test_a_missing_or_unreadable_agent_transcript_passes(tmp_path):
    """Ownership cannot be proved without the subagent's own transcript - so it is not claimed."""
    for label, payload in (
        ("absent field", _subagent_payload(None, [_shell_task("bq1")])),
        ("nonexistent path", _subagent_payload(tmp_path / "gone.jsonl", [_shell_task("bq1")])),
    ):
        rc, out = _run(payload)
        assert rc == 0 and out.strip() == "", f"{label}: must fail open, got {out!r}"


def test_the_session_transcript_is_never_used_for_ownership(tmp_path):
    """`transcript_path` on a SubagentStop is the SESSION's transcript. Correlating against it
    would attribute the ROOT's own background commands to whichever subagent stopped next."""
    session = _transcript(tmp_path, ["roots-task"], name="session.jsonl")
    payload = _subagent_payload(None, [_shell_task("roots-task")])
    payload["transcript_path"] = str(session)
    rc, out = _run(payload)
    assert rc == 0 and out.strip() == "", (
        "the session transcript must not stand in for the subagent's own"
    )


# --------------------------------------------------------------------------- #
# 4. Red-before-green: the pre-fix tree does not catch this shape
# --------------------------------------------------------------------------- #
def test_the_other_subagentstop_hooks_do_not_catch_this_shape(tmp_path):
    """The committed pre-fix measurement. Every other SubagentStop hook approves the defect
    payload, which is why the stall was silent. If a future change makes one of them catch it,
    this test goes red and the duplication must be resolved deliberately - not discovered."""
    t = _transcript(tmp_path, ["bvld2f72c"])
    payload = _subagent_payload(t, [_agent_task("a-child-1"), _shell_task("bvld2f72c")])
    siblings = ["enforce-grounding.sh", "enforce-teardown.sh", "parse-continuation.sh",
                "report-terminal-status.sh"]
    blocked = []
    for name in siblings:
        script = HOOKS_DIR / name
        if not script.is_file():
            continue
        _, out = _run(payload, script=script)
        if _decision(out) == "block":
            blocked.append(name)
    assert not blocked, (
        f"{blocked} now also block the background-wait shape. Exactly one gate should own it "
        "(enforce-background-wait.sh); two blocks on one turn end is a double refusal"
    )


# --------------------------------------------------------------------------- #
# 5. Prose - one home declares the rule, and nothing in the tree contradicts it
# --------------------------------------------------------------------------- #
_GENERATED_RE = re.compile(
    r"<!--\s*BEGIN GENERATED TOOLS\s*-->.*?<!--\s*END GENERATED TOOLS\s*-->", re.S
)


def _prose_files() -> list[Path]:
    files = [p for root in (PLUGINS, ROOT_DOCS) for p in root.rglob("*.md")]
    files += list(PLUGINS.rglob("hooks.json"))
    return sorted(p for p in files if ".venv" not in p.parts)


def _norm_text(text: str) -> str:
    return " ".join(_GENERATED_RE.sub(" ", text).split())


PROSE = {p: _norm_text(p.read_text(encoding="utf-8")) for p in _prose_files()}


def test_prose_corpus_discovered():
    assert len(PROSE) >= 200, (
        f"expected >=200 scanned prose files, found {len(PROSE)} - the glob is wrong, so the "
        "whole-tree assertion below would pass for the wrong reason"
    )


# A promise that a background command's completion will reach the reader on its own. Two
# vocabularies, paired inside one window over NORMALIZED text - never line adjacency, never a
# single phrasing.
_WAKE_RE = re.compile(
    r"(you will be notified|will be notified|be notified when|"
    r"you will be woken|be woken when|notification will (?:reach|resume|wake))",
    re.I,
)
_BACKGROUND_RE = re.compile(
    r"background(?:ed|ing)?\s+(?:shell\s+)?(?:task|command|run|process|job|build)|"
    r"\bin the background\b|\brun_in_background\b",
    re.I,
)
# What makes the pairing legal: the same window says the promise does not hold here.
_DENIAL_RE = re.compile(
    r"(does not hold|do(?:es)? not apply|never (?:holds|applies)|is not true for you|"
    r"no notification|never resumes|nothing resumes|overridden|overrides|"
    r"written for the root|only inside the turn)",
    re.I,
)
_PAIR_WINDOW = 240


def _wake_promise_offenders(text: str) -> list[str]:
    found = []
    for m in _WAKE_RE.finditer(text):
        window = text[max(0, m.start() - _PAIR_WINDOW): m.end() + _PAIR_WINDOW]
        if not _BACKGROUND_RE.search(window):
            continue
        if _DENIAL_RE.search(window):
            continue
        found.append(window.strip()[:280])
    return found


def test_no_file_promises_an_agent_a_wake_for_a_background_command():
    offenders = [
        f"{path.relative_to(REPO_ROOT)}: ...{w}..."
        for path, text in PROSE.items()
        for w in _wake_promise_offenders(text)
    ]
    assert not offenders, (
        "prose promises that a background command's completion will reach the reader on its own. "
        "That receipt is written for the ROOT conversation; a dispatched agent's turn end IS the "
        "end of its dispatch and nothing resumes it, so the result is reachable only inside the "
        "turn that started it (snippets/spawner-completion-contract.md R0 § A background shell "
        "command is a SAME-TURN result):\n" + "\n".join(offenders)
    )


_MUST_CATCH = (
    "If you are waiting for a background task you will be notified when it completes, so end "
    "your turn and consume the result when it arrives.",
    "Start the build in the background; you will be woken when the run finishes.",
    "Run it with run_in_background: true via Bash - a notification will reach you on completion.",
)
_MUST_NOT_CATCH = (
    "The Bash tool's generic guidance - \"if waiting for a background task you will be notified; "
    "do not poll\" - DOES NOT APPLY to a dispatched agent ANYWHERE.",
    "The receipt it hands back says you will be notified when the command completes. That "
    "sentence is written for the ROOT conversation, where it is true. It is not true for you.",
    "You will be notified when your teammate's review lands on the pull request.",
)


@pytest.mark.parametrize("phrasing", _MUST_CATCH)
def test_wake_promise_guard_catches_every_known_phrasing(phrasing):
    assert _wake_promise_offenders(_norm_text(phrasing)), (
        f"the wake-promise guard does not catch {phrasing!r} - it is bound to one spelling again"
    )


@pytest.mark.parametrize("phrasing", _MUST_NOT_CATCH)
def test_wake_promise_guard_allows_the_denial_and_unrelated_shapes(phrasing):
    assert not _wake_promise_offenders(_norm_text(phrasing)), (
        f"the wake-promise guard flags {phrasing!r}. Quoting the receipt in order to deny it is "
        "the corrected shape, and a notification unrelated to a background command is not this "
        "defect at all"
    )


def test_the_ssot_declares_the_rule_positively():
    """An absence guard alone passes on a tree that deleted the rule everywhere. The single home
    must state the fact, the consequence, and the legal shape."""
    low = PROSE[SSOT].lower()
    assert "a background shell command is a same-turn result" in low, (
        "the SSOT must carry the named section other files point at"
    )
    assert "written for the root conversation" in low, (
        "the SSOT must say WHO the Bash receipt is written for - a bare prohibition loses to the "
        "receipt the agent can see"
    )
    assert "nothing resumes you for a background shell command" in low, (
        "the SSOT must state the mechanical fact, not just the prohibition"
    )
    assert "only inside the turn that started it" in low, (
        "the SSOT must state where the result IS reachable, or the rule reads as a ban on "
        "backgrounding"
    )
    assert "foreground" in low, (
        "the SSOT must name the legal shape - drive it to a result with foreground calls in the "
        "same turn - or an agent reads the rule as 'never background anything'"
    )
    assert "an agent child does deliver to a launcher that stopped" in low, (
        "the SSOT must state the contrast with an agent child, which DOES wake its launcher - "
        "collapsing the two rules is how one gets generalized onto the other"
    )
    assert "enforce-background-wait.sh" in low, (
        "the SSOT must name the gate that enforces it, so the refusal an agent meets at runtime "
        "is traceable to the rule"
    )
