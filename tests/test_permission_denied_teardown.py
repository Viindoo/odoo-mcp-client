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
import re
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


# --------------------------------------------------------------------------- #
# The quoted-path form: "${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py" park <token>
# --------------------------------------------------------------------------- #
# The harness reports tool_input.command AFTER shell variable expansion, so
# ${CLAUDE_PLUGIN_ROOT} arrives as a concrete absolute path, double-quoted (the plugin quotes
# every ${CLAUDE_PLUGIN_ROOT} reference so a path containing a space still runs). Before the
# fix, the closing quote right after "allocator.py" defeated the
# 'allocator\.py[[:space:]]+(park|release)' regex, which required WHITESPACE immediately after
# ".py" - a quote character is not whitespace, so this exact real-world shape was silently
# missed.
QUOTED_ALLOC = '"/home/user/.claude/plugins/cache/marketplace/odoo-ai-agents/7.0.2/scripts/lib/allocator.py"'


@pytest.mark.parametrize("command", [
    f"{QUOTED_ALLOC} park {TOKEN}",
    f"{QUOTED_ALLOC} release {TOKEN} --run-id r1",
])
def test_a_refused_quoted_path_give_back_is_advised(command):
    """The exact real-world shape the harness reports: allocator.py invoked as a quoted,
    already-expanded absolute path, not the bare 'python3 allocator.py' form."""
    _advised(_run(command))


def test_a_refused_quoted_path_non_give_back_stays_silent():
    """The quoted-path fix must not overshoot into matching a quoted-path READ-ONLY verb."""
    _silent(_run(f"{QUOTED_ALLOC} list --show-tokens"))


# --------------------------------------------------------------------------- #
# The MCP odoo-local tool_name form: no command string, tool_name alone is the signal.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("tool_name", [
    "mcp__plugin_odoo-ai-agents_odoo-local__lease_release",
    "mcp__plugin_odoo-ai-agents_odoo-local__lease_park",
])
def test_a_refused_mcp_lease_give_back_is_advised(tool_name):
    """The odoo-local MCP path: tool_input carries no "command" string (it carries structured
    args like {token, run_id}), so the hook must recognize the give-back from tool_name alone."""
    payload = json.dumps({
        "hook_event_name": "PermissionDenied",
        "tool_name": tool_name,
        "tool_input": {"token": TOKEN, "run_id": "r1"},
        "denial_reason": "Blocked by classifier",
        "has_classifier_verdict": True,
    })
    proc = subprocess.run(
        ["bash", str(HOOK)], input=payload, capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0
    _advised(proc.stdout)


@pytest.mark.parametrize("tool_name", [
    "mcp__plugin_odoo-ai-agents_odoo-local__lease_acquire",
    "mcp__plugin_odoo-ai-agents_odoo-local__lease_list",
    "mcp__plugin_odoo-ai-agents_odoo-local__lease_gc",
    "mcp__plugin_odoo-ai-agents_chrome-devtools__navigate_page",
    "mcp__odoo-semantic__model_inspect",
])
def test_non_give_back_mcp_tools_stay_silent(tool_name):
    """A read-only or non-give-back odoo-local tool, a browser tool, and a foreign MCP server's
    tool must all stay silent - only lease_release/lease_park on odoo-local are give-backs."""
    payload = json.dumps({
        "hook_event_name": "PermissionDenied",
        "tool_name": tool_name,
        "tool_input": {},
        "denial_reason": "Blocked by classifier",
        "has_classifier_verdict": True,
    })
    proc = subprocess.run(
        ["bash", str(HOOK)], input=payload, capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0
    _silent(proc.stdout)


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


def test_the_hook_is_also_registered_for_the_mcp_lease_give_back():
    """A SECOND PermissionDenied entry, matcher-scoped to the odoo-local lease_release/lease_park
    tool names, must dispatch this SAME script - the MCP give-back gets identical advice to the
    Bash CLI one, and it never replaces the original Bash-matcher entry (tested above)."""
    manifest = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    entries = manifest.get("hooks", {}).get("PermissionDenied")
    mcp_entries = [
        entry for entry in entries
        if entry.get("matcher") not in (None, "Bash")
    ]
    assert mcp_entries, "expected a second PermissionDenied entry beyond the Bash one"
    matcher = mcp_entries[0]["matcher"]
    assert re.match(matcher, "mcp__plugin_odoo-ai-agents_odoo-local__lease_release")
    assert re.match(matcher, "mcp__plugin_odoo-ai-agents_odoo-local__lease_park")
    assert re.match(matcher, "mcp__plugin_odoo-ai-agents_odoo-local__lease_acquire") is None
    commands = [c.get("command", "") for e in mcp_entries for c in e.get("hooks", [])]
    assert any(HOOK.name in c for c in commands), (
        f"the odoo-local PermissionDenied entry must also dispatch {HOOK.name}"
    )


def test_the_manifest_description_documents_the_new_hook():
    """hooks.json's description is the map a debugging agent reads first; a hook missing from it
    is a hook nobody knows fired."""
    manifest = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    desc = " ".join(manifest.get("description", "").split())
    assert HOOK.name in desc, "the manifest description must name the new hook"
