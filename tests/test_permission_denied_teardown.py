"""Behavioral guard for hooks/permission-denied-teardown.sh (PermissionDenied ADVISORY).

THE INCIDENT: a dispatched `odoo-instance-ops` had `allocator.py park` refused by the harness
permission classifier, and later `allocator.py release <token> --run-id <id>` refused the same
way. Neither command ever executed. The agent behaved correctly at every step it knew about - it
did not retry, did not reword, reported the refusal verbatim - and then ended on a bare `BLOCKED`,
which the SubagentStop teardown gate let past unconditionally at the time. A live ephemeral
database and its lease outlived the run, and a human reclaimed them by hand.

Nothing in the plugin told that agent the one thing that was still available to it: it could not
RELEASE, but it could still NAME A CATCHER. This hook says exactly that, at the moment of refusal.

Business rules protected, NOT the implementation:

  - **A refused give-back gets advice, at the moment it is refused.** `release` and `park` are the
    two verbs that hand a lease back; a refusal on either is the leak's starting gun.
  - **The advice is the OPPOSITE of a bypass.** The hook must tell the agent to stop trying and to
    hand the lease over by name. It must never set `retry`, and never suggest rewording the
    command - re-issuing a refused destructive call under a new spelling is itself a blocked
    action, and a hook that nudged toward it would be teaching the breach.
  - **It must name the exit that is always reachable.** Forwarding INSTANCE_HANDLE needs no tool,
    no permission and no live process, so it is the one exit a permission denial cannot take away.
  - **Read-only verbs are not give-backs.** `list` / `query` / `heartbeat` leak nothing when
    refused; advising on them would train agents to ignore the message that matters.
  - **A hook failure must never be louder than the denial it annotates.** Any malformed, empty, or
    unexpected payload exits 0 silently.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / "plugins" / "odoo-ai-agents"
HOOK = PLUGIN_ROOT / "hooks" / "permission-denied-teardown.sh"
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"

ALLOC = "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py"
TOKEN = "7273055907184f0a90c9514bcf10040b"


def _run(command, *, tool="Bash", raw=None):
    """Drive the hook exactly as Claude Code does: JSON on stdin, output on stdout."""
    if raw is None:
        payload = json.dumps({
            "hook_event_name": "PermissionDenied",
            "tool_name": tool,
            "tool_input": {"command": command},
            "denial_reason": "Blocked by classifier",
            "has_classifier_verdict": True,
        })
    else:
        payload = raw
    proc = subprocess.run(
        ["bash", str(HOOK)], input=payload, capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, (
        f"a PermissionDenied hook must ALWAYS exit 0 (got {proc.returncode}); "
        "the denial already happened and the hook must not add a second failure"
    )
    return proc.stdout


def _advised(stdout):
    assert stdout.strip(), "expected the hook to emit advisory JSON, got silence"
    doc = json.loads(stdout)
    assert doc.get("systemMessage"), "advisory must carry a systemMessage"
    return doc


def _silent(stdout):
    assert not stdout.strip(), f"expected silence, got: {stdout[:200]!r}"


# --------------------------------------------------------------------------- #
# The give-back verbs
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("command", [
    f"{ALLOC} release {TOKEN} --run-id fp-16-to-17-20260821",
    f"{ALLOC} park {TOKEN}",
    f"{ALLOC} release {TOKEN}",
    f"cd /tmp && {ALLOC} park {TOKEN} --run-id r1",
])
def test_a_refused_give_back_is_advised(command):
    """Both verbs that hand a lease back, with and without a run id, bare or in a compound
    command. This is the moment the leak starts, and the only moment the agent is still holding
    every fact it needs to hand the lease over."""
    _advised(_run(command))


@pytest.mark.parametrize("command", [
    f"{ALLOC} list --show-tokens",
    f"{ALLOC} heartbeat {TOKEN}",
    f"{ALLOC} query --series 17.0 --state parked",
    f"{ALLOC} acquire --series 17.0",
    "rm -rf /tmp/build",
    "git push --force",
])
def test_non_give_back_denials_stay_silent(command):
    """A refusal that leaks no lease gets no lecture. Advising on `list` would train agents to
    skim past the one message that means a database is about to outlive the run."""
    _silent(_run(command))


def test_a_non_bash_tool_is_ignored():
    """The matcher is Bash; a same-looking command arriving on another tool is not a give-back."""
    _silent(_run(f"{ALLOC} release {TOKEN}", tool="Edit"))


@pytest.mark.parametrize("raw", ["", "not json at all", "{}", '{"tool_name":"Bash"}',
                                 '{"tool_name":"Bash","tool_input":{}}', "null"])
def test_unparseable_payloads_fail_open_silently(raw):
    """Fail-open is the whole contract for an advisory hook: the tool call is already denied, and
    a parse error must not add noise or a second failure on top of it."""
    _silent(_run(None, raw=raw))


# --------------------------------------------------------------------------- #
# What the advice must and must not say
# --------------------------------------------------------------------------- #

def test_the_advice_never_sets_retry():
    """`retry: true` would tell the model to re-issue a destructive call the harness just refused.
    The correct move is to STOP and hand the lease over - so this key must be absent entirely,
    not merely false."""
    doc = _advised(_run(f"{ALLOC} release {TOKEN} --run-id r1"))
    hso = doc.get("hookSpecificOutput") or {}
    assert "retry" not in hso and "retry" not in doc, (
        "the hook must never advise retrying a refused give-back"
    )


def test_the_advice_names_the_always_available_exit():
    """The single load-bearing sentence: forwarding INSTANCE_HANDLE is the exit a permission
    denial cannot take away. Without it the agent has been told what NOT to do and nothing else,
    which is exactly the state that produced the leak."""
    msg = _advised(_run(f"{ALLOC} release {TOKEN} --run-id r1"))["systemMessage"]
    assert "INSTANCE_HANDLE" in msg, "must name the handle to forward"
    assert "lease_token" in msg and "run_id" in msg, "must name the fields the catcher needs"
    assert "next.inputs" in msg, "must name WHERE the handle goes"
    assert "caller" in msg.lower(), "must name the dispatching caller as the catcher"


def test_the_advice_forbids_working_around_the_refusal():
    """A hook that annotated a denial without this line would be one prompt away from teaching
    the bypass it exists to prevent."""
    msg = _advised(_run(f"{ALLOC} park {TOKEN}"))["systemMessage"].lower()
    assert "do not re-issue" in msg, "must forbid re-issuing the refused command"
    assert "reword" in msg, "must forbid rewording it past the refusal"


def test_the_advice_warns_that_a_bare_stop_report_will_not_pass():
    """The behavioural link to enforce-teardown.sh: the agent must learn here that the gate is
    status-blind, or it will do exactly what the incident agent did and end on a bare BLOCKED."""
    msg = _advised(_run(f"{ALLOC} release {TOKEN} --run-id r1"))["systemMessage"]
    assert "BLOCKED" in msg, "must name the status the incident agent used"
    assert "status-blind" in msg.lower(), "must state that the gate ignores the status value"


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #

def test_the_hook_is_registered_and_executable():
    """A hook nobody runs protects nothing - the plugin's dominant historical defect. Assert the
    script is executable AND that hooks.json actually wires it to the PermissionDenied event with
    a Bash matcher."""
    assert HOOK.exists(), f"missing hook script: {HOOK}"
    import os
    assert os.access(HOOK, os.X_OK), "hook script must be executable"

    manifest = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    entries = manifest.get("hooks", {}).get("PermissionDenied")
    assert entries, "hooks.json must register a PermissionDenied hook"
    commands = [
        c.get("command", "")
        for entry in entries
        for c in entry.get("hooks", [])
    ]
    assert any(HOOK.name in c for c in commands), (
        f"{HOOK.name} is not wired into the PermissionDenied event"
    )
    assert any(entry.get("matcher") == "Bash" for entry in entries), (
        "the PermissionDenied registration must be matcher-scoped to Bash"
    )


def test_the_manifest_description_documents_the_new_hook():
    """hooks.json's description is the map a debugging agent reads first; a hook missing from it
    is a hook nobody knows fired."""
    manifest = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    desc = " ".join(manifest.get("description", "").split())
    assert HOOK.name in desc, "the manifest description must name the new hook"
