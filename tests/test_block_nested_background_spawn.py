"""Behavioral guard for hooks/block-nested-background-spawn.sh (PreToolUse hard DENY).

The mistake this hook makes impossible to express: a SUBAGENT launching a child in the
BACKGROUND and then ending its turn. Measured, not assumed - only the ROOT conversation is ever
resumed when a background child finishes; a child holds no address for its launcher; and a
child's fallback send to `main` is ACCEPTED and delivered to the ROOT while the launcher that
was actually waiting stays parked forever. `snippets/spawner-completion-contract.md` R0/R1
forbids the move in prose; this hook is the first mechanism that REFUSES it.

Business rules protected, NOT the implementation:

  - **DENY iff all three hold**: (a) the call is a subagent spawn (`Agent`, or the historical
    `Task`), AND (b) the CALLER is itself a subagent (any of agent_id / agentId / agent_type /
    agentType populated - the same identity signal `remind-delegate.sh` already relies on), AND
    (c) the launch would be backgrounded.
  - **Backgrounded means `true` OR ABSENT.** Background is the spawn tool's DEFAULT
    (`run_in_background` documents "Agents run in the background by default ... Set to false to
    run this agent synchronously"), so a guard keyed on an explicit `true` alone would miss the
    majority of real calls, which omit the flag entirely. This is the single assertion most
    likely to be silently regressed into a `== true` check, hence its own test.
  - **The ROOT is NEVER denied.** No agent-identity field means the root, and the root is
    allowed to background freely - every drive-to-done fan-out in this plugin depends on it.
  - **The deny reason is ACTIONABLE**: it must name the blocking alternative (re-issue with
    `run_in_background: false`, whose result returns inside the caller's own turn), state that
    concurrency survives it (several blocking launches in ONE message still run concurrently),
    and state the consequence being prevented (nothing wakes you / the result goes to the root
    / the run stalls with no error).
  - **The deny uses the documented PreToolUse schema** - `hookSpecificOutput.permissionDecision
    == "deny"` with `permissionDecisionReason` - NOT the SubagentStop `{"decision": "block"}`
    shape `enforce-teardown.sh` uses. Different event, different schema; conflating them
    produces a hook whose refusal is silently ignored.
  - **Fails OPEN on every uncertainty**: no jq, unparseable stdin, empty stdin, a tool name
    outside the spawn set, a non-object `tool_input`, or a `run_in_background` value that is
    neither boolean nor absent -> silent pass (exit 0, no stdout). A guardrail that breaks a
    working run is worse than the stall it prevents.
  - **Never blocks a non-spawn tool.** In particular `Bash` with `run_in_background: true` is
    how `odoo-instance-ops` launches every long Odoo build; denying it would break the
    active-wait contract outright.
  - **Exit code is ALWAYS 0** - a PreToolUse hook that hard-fails is itself an outage.

Run with: python3 -m pytest tests/test_block_nested_background_spawn.py -v
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
HOOK = PLUGIN_ROOT / "hooks" / "block-nested-background-spawn.sh"
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"

_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or _BASH is None,
    reason="hook needs jq + bash; absent here (the hook itself degrades to a silent pass)",
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
_ABSENT = object()


def _payload(
    tool_name="Agent",
    *,
    background=_ABSENT,
    agent_id="agent-under-test",
    agent_type="odoo-ai-agents:odoo-coder",
    id_key="agent_id",
    type_key="agent_type",
    tool_input=_ABSENT,
):
    """A PreToolUse stdin payload in the shape the harness actually sends.

    Field set mirrors the established fixture in tests/test_git_delegation_boundary.py:
    hook_event_name / tool_name / tool_input / agent_id / agent_type / cwd.
    """
    if tool_input is _ABSENT:
        tool_input = {"subagent_type": "odoo-ai-agents:odoo-backend-coder", "prompt": "do it"}
        if background is not _ABSENT:
            tool_input["run_in_background"] = background
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "cwd": str(ROOT),
    }
    if agent_id is not None:
        payload[id_key] = agent_id
    if agent_type is not None:
        payload[type_key] = agent_type
    return payload


def _run(payload, env_overrides=None, raw=None):
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    if env_overrides:
        env.update(env_overrides)
    stdin = raw if raw is not None else json.dumps(payload)
    return subprocess.run(
        [_BASH, str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )


def _assert_denied(proc):
    assert proc.returncode == 0, (
        f"a PreToolUse hook must always exit 0 (the DENY travels in stdout JSON, never in the "
        f"exit code); got rc={proc.returncode}, stderr={proc.stderr!r}"
    )
    assert proc.stdout.strip(), "expected a deny JSON on stdout, got nothing"
    out = json.loads(proc.stdout)
    hso = out.get("hookSpecificOutput", {})
    assert hso.get("hookEventName") == "PreToolUse", (
        f"deny must be emitted under the PreToolUse schema, got {out!r}"
    )
    assert hso.get("permissionDecision") == "deny", (
        f"expected permissionDecision 'deny', got {hso.get('permissionDecision')!r} - full: {out!r}"
    )
    reason = hso.get("permissionDecisionReason") or ""
    assert reason.strip(), "a deny with no permissionDecisionReason tells the caller nothing"
    assert "decision" not in out, (
        "the SubagentStop `{'decision': 'block'}` shape is a DIFFERENT event's schema; emitting "
        f"it on PreToolUse produces a refusal the harness ignores. Full output: {out!r}"
    )
    return reason


def _assert_passed(proc):
    assert proc.returncode == 0, f"must exit 0; got rc={proc.returncode}, stderr={proc.stderr!r}"
    assert proc.stdout.strip() == "", (
        f"expected a SILENT pass (no stdout at all), got {proc.stdout!r}"
    )


# --------------------------------------------------------------------------- #
# DENY side - the three conditions all hold
# --------------------------------------------------------------------------- #
def test_subagent_spawning_with_explicit_background_true_is_denied():
    """The literal case the contract forbids: a subagent launches a child with
    run_in_background: true, then has no way to ever be woken by it."""
    _assert_denied(_run(_payload(background=True)))


def test_subagent_spawning_with_run_in_background_absent_is_denied():
    """THE load-bearing case. Background is the spawn tool's DEFAULT, so omitting the flag IS
    backgrounding it - and omitting it is the common shape, not the rare one. A guard that only
    catches an explicit `true` would wave through the majority of the very calls it exists to
    stop, and would look green in every test that only ever sets the flag explicitly."""
    _assert_denied(_run(_payload(background=_ABSENT)))


def test_subagent_spawning_with_explicit_null_background_is_denied():
    """JSON `null` is "not specified", which the tool resolves to its background default - it
    must be treated exactly like an absent key, never as a third state that slips through."""
    _assert_denied(_run(_payload(background=None)))


@pytest.mark.parametrize(
    "id_key,type_key", [("agent_id", "agent_type"), ("agentId", "agentType")]
)
def test_either_casing_of_the_agent_identity_field_marks_a_subagent(id_key, type_key):
    """The identity signal is read in both snake_case and camelCase (the same defensive pair
    remind-delegate.sh reads) - a payload that used only one casing must not read as the root."""
    _assert_denied(_run(_payload(background=True, id_key=id_key, type_key=type_key)))


@pytest.mark.parametrize("present", ["id_only", "type_only"])
def test_any_single_populated_identity_field_is_enough_to_mean_subagent(present):
    """ANY populated agent identity means "in a subagent" - the V-52 rule remind-delegate.sh
    records as a production bug fix. Requiring BOTH fields would re-open that hole."""
    kwargs = {"agent_id": None} if present == "type_only" else {"agent_type": None}
    _assert_denied(_run(_payload(background=True, **kwargs)))


@pytest.mark.parametrize("tool", ["Agent", "Task"])
def test_both_spawn_tool_names_are_covered(tool):
    """`Agent` is the spawn tool this harness emits (verified against the local transcript
    corpus: every recorded spawn is `Agent`); `Task` is the historical name the same call
    carried in earlier CLI versions. Matching the set costs nothing and survives a rename."""
    _assert_denied(_run(_payload(tool_name=tool, background=True)))


# --------------------------------------------------------------------------- #
# The deny must be ACTIONABLE
# --------------------------------------------------------------------------- #
def test_deny_reason_names_the_blocking_alternative():
    """A refusal that only scolds leaves the caller stuck. The reason must name the exact
    remedy - re-issue with run_in_background: false - and say that its result comes back inside
    the caller's own turn, which is the whole reason blocking is safe where backgrounding is
    not."""
    reason = _assert_denied(_run(_payload(background=True)))
    assert "run_in_background" in reason, "the reason must name the flag to change"
    assert "false" in reason, "the reason must name the value to set it to"
    lowered = reason.lower()
    assert "turn" in lowered, (
        "the reason must say the blocking launch returns the child's result inside the caller's "
        f"OWN turn - otherwise 'block instead' reads as 'give up'. Reason: {reason!r}"
    )


def test_deny_reason_states_that_concurrency_survives_the_refusal():
    """Denying background must not read as "you may no longer fan out". Concurrency comes from
    emitting several spawn calls in ONE message, each of which can still block."""
    reason = _assert_denied(_run(_payload(background=True))).lower()
    assert "one message" in reason or "same message" in reason or "single message" in reason, (
        f"the reason must point at the one-message fan-out as the way to keep concurrency: {reason!r}"
    )
    assert "concurrent" in reason or "parallel" in reason, (
        f"the reason must say those launches still run concurrently: {reason!r}"
    )


def test_deny_reason_states_the_consequence_being_prevented():
    """The caller has to understand this is not a style preference: nothing can wake it, the
    child's result lands on the root, and the run stops with no error to notice."""
    reason = _assert_denied(_run(_payload(background=True))).lower()
    assert "root" in reason, f"must say where the result actually goes: {reason!r}"
    assert "wake" in reason or "resume" in reason, (
        f"must say nothing wakes/resumes the launcher: {reason!r}"
    )


def test_deny_reason_is_short_enough_to_be_read():
    """An actionable refusal that runs to a page is an unread refusal."""
    reason = _assert_denied(_run(_payload(background=True)))
    assert len(reason) <= 1200, f"deny reason is {len(reason)} chars - trim it to stay readable"


# --------------------------------------------------------------------------- #
# PASS side - any one condition missing
# --------------------------------------------------------------------------- #
def test_subagent_spawning_with_explicit_background_false_passes():
    """The prescribed shape must never be obstructed - this is the call the deny tells callers
    to make, so denying it would leave no legal move at all."""
    _assert_passed(_run(_payload(background=False)))


@pytest.mark.parametrize("background", [True, _ABSENT, False])
def test_the_root_is_never_denied(background):
    """THE regression that would break the human's own workflow. No agent-identity field means
    the ROOT conversation, which is the one context that IS resumed when a background child
    finishes - backgrounding there is correct and this plugin's drive-to-done fan-out depends
    on it. Denying the root would convert the fix into an outage."""
    _assert_passed(_run(_payload(background=background, agent_id=None, agent_type=None)))


def test_empty_string_identity_fields_read_as_root():
    """Present-but-empty is not "populated" - the harness sends the key on the root too in some
    versions, and treating "" as a subagent would deny every root launch."""
    _assert_passed(_run(_payload(background=True, agent_id="", agent_type="")))


@pytest.mark.parametrize("tool", ["Bash", "Write", "Edit", "Skill", "TaskUpdate", "SendMessage"])
def test_non_spawn_tools_are_never_denied(tool):
    """Scope discipline. `Bash` with run_in_background: true is exactly how odoo-instance-ops
    launches every long Odoo build before its foreground wait-log call - a hook that keyed on
    the flag rather than on the TOOL would break the active-wait contract outright. TaskUpdate
    is included because a loose `Task` matcher would over-match it."""
    _assert_passed(
        _run(
            _payload(
                tool_name=tool,
                tool_input={"command": "odoo-bin -u base", "run_in_background": True},
            )
        )
    )


# --------------------------------------------------------------------------- #
# FAIL-OPEN paths
# --------------------------------------------------------------------------- #
def test_malformed_json_passes_silently():
    _assert_passed(_run(None, raw="{not json at all"))


def test_empty_stdin_passes_silently():
    _assert_passed(_run(None, raw=""))


def test_missing_jq_passes_silently(tmp_path):
    """The hook's very first check is `command -v jq`; with jq unresolvable it must fail open
    rather than crash - a guardrail that breaks a working run is worse than the stall."""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    _assert_passed(_run(_payload(background=True), env_overrides={"PATH": str(empty)}))


def test_missing_tool_input_passes_silently():
    """No tool_input at all is an unrecognized payload shape, not a background launch."""
    _assert_passed(_run(_payload(background=True, tool_input=None)))


def test_non_object_tool_input_passes_silently():
    _assert_passed(_run(_payload(background=True, tool_input="a string, somehow")))


@pytest.mark.parametrize("weird", [1, 0, {"nested": True}, ["true"]])
def test_uninterpretable_background_value_passes_silently(weird):
    """A `run_in_background` that is neither boolean nor a boolean-ish string is a shape this
    hook does not understand - it must not guess a denial out of it."""
    _assert_passed(
        _run(
            _payload(
                tool_input={"subagent_type": "x", "run_in_background": weird},
            )
        )
    )


def test_missing_tool_name_passes_silently():
    _assert_passed(_run(_payload(tool_name=None, background=True)))


def test_no_plugin_root_still_decides_correctly():
    """This hook reads NOTHING off disk - no SSOT lookup, no state root, no run file. It must
    therefore keep working with CLAUDE_PLUGIN_ROOT unset, unlike its remind-delegate sibling."""
    env = {"CLAUDE_PLUGIN_ROOT": ""}
    _assert_denied(_run(_payload(background=True), env_overrides=env))


# --------------------------------------------------------------------------- #
# hooks.json registration
# --------------------------------------------------------------------------- #
def _pretooluse_groups():
    return json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]


def test_hooks_json_registers_the_hook_under_pretooluse():
    """An unregistered hook is a mechanism described but never reached."""
    cmds = [h.get("command", "") for g in _pretooluse_groups() for h in g.get("hooks", [])]
    assert any("block-nested-background-spawn.sh" in c for c in cmds), (
        "hooks.json must register block-nested-background-spawn.sh under PreToolUse; "
        f"found: {cmds!r}"
    )


def test_hooks_json_scopes_the_hook_to_the_spawn_tool_and_matches_it():
    """The matcher is the gate BEFORE the script's own guard runs - if it does not accept the
    real spawn tool name, the hook never executes at all (the V-19 failure mode). It must also
    be SCOPED: an unmatched PreToolUse entry would run this script on every tool call."""
    import re

    matchers = [
        g.get("matcher")
        for g in _pretooluse_groups()
        if any("block-nested-background-spawn.sh" in h.get("command", "") for h in g.get("hooks", []))
    ]
    assert matchers, "the hook's PreToolUse group was not found"
    for matcher in matchers:
        assert matcher, (
            "the group registering block-nested-background-spawn.sh must carry a matcher scoped "
            "to the spawn tool - an absent matcher runs it on every tool call in the session"
        )
        assert re.match(matcher, "Agent"), (
            f"matcher {matcher!r} must accept the real spawn tool name 'Agent', or the hook "
            "never runs (it is gated out before the script is even invoked)"
        )


def test_hooks_json_timeout_matches_the_other_pretooluse_entry():
    """Consistency with the sibling PreToolUse hook - a divergent timeout here is drift, and a
    long one delays every spawn in the session."""
    timeouts = {
        h.get("timeout")
        for g in _pretooluse_groups()
        for h in g.get("hooks", [])
    }
    assert timeouts == {5}, f"PreToolUse hooks should share the 5s timeout; found {timeouts!r}"
