"""Behavioral guard for hooks/block-unowned-lease-mutation.sh (PreToolUse hard DENY).

THE INCIDENT: a dispatched agent was given a purely documentary brief - read three requirement
docs, rule on one oracle scenario. No instance was named, no lease token was handed to it, no
execution was asked for. It ended its turn by running `allocator.py release <token>` on the LIVE
acceptance lease of the run that had dispatched it; `drop_on_release: true` fired and a database
built minutes earlier was destroyed. Its reasoning was that the lease "looked orphaned" - no
owner.pid, no parked_at. The question it never asked was DID I ACQUIRE THIS.

The agent's own definition already called it read-only and a HARD LEAF that "does not write, run, or
adjudicate tests". That prohibition was PROSE with no gate under it - the same shape as the
coordinator-authoring breach hooks/block-coordinator-code-write.sh was written for.

Business rules protected, NOT the implementation:

  - **A release must NAME its owner.** A SUBAGENT's `allocator.py release` carrying no `--run-id`
    (nor its `--session` alias) is DENIED. An absent run id is not "the owner forgot a flag"; it is
    ownership not established, and the call drops a database.
  - **A dispatched agent may not override the ownership decision.** `--force` / `--force-forget` on
    `release`, and `--yes` on `reap-orphans`, are DENIED for a subagent. Without this, the
    allocator's own refusal (which names `--force`) is one flag away from the same data loss, by
    the same "it looked orphaned" reasoning.
  - **The rightful owner is never blocked.** The identical command WITH a run id passes, for every
    agent. This is the red-before-green half: a gate that over-applies stalls every instance
    pipeline on the host, which is worse than the breach it prevents.
  - **Identity-free by design.** No per-agent allow-list: `role` in the agent SSOT has two live
    values and the agents that legitimately drive the allocator sit on both sides of that line, so
    a role table cannot separate the classes, and a 26-agent hand classification would be 26
    chances to brick a real pipeline. The gate asserts the one property every legitimate caller can
    satisfy. It therefore also covers agents that do not exist yet.
  - **Non-destructive and janitor verbs are never refused**: acquire, bind, park, resume,
    heartbeat, gc, list, and a list-only reap-orphans. `gc` / `reap-orphans` judge "provably
    abandoned" / "no lease references this database at all", never "not mine", so neither needs an
    ownership check.
  - **The ROOT is never denied** (the rule its two sibling PreToolUse hooks follow): a human is
    present in the main context to read the allocator's own refusal. The allocator refuses a
    foreign or un-named release for EVERY caller regardless - this hook is the earlier,
    explanatory layer, and the layer that still holds if that predicate is loosened again.
  - **Fails OPEN on every uncertainty** and always exits 0.

REMAINING FALSE NEGATIVES - stated here and in the hook's own header, and PINNED below as passing
so each hole is a measured fact rather than a surprise:
  1. `park` / `resume` / `heartbeat` / `bind` on a lease the caller does not own. Those verbs accept
     no `--run-id`, so there is nothing to require - and `park` is one of the THREE EXITS the
     SubagentStop teardown gate accepts, so making it refusable could deadlock a subagent between a
     refused release and a refused park. Separate scope, deliberately not half-fixed here.
  2. A run id that is present but WRONG or empty (`--run-id ""`). This arm is lexical; the
     allocator's comparison under flock is what catches those (tests/test_allocator.py).
  3. A verb or flag COMPUTED at runtime, or assembled inside a script the command only invokes.
  4. A release through any tool outside the `Bash` matcher.
  5. These tests prove the hook DECIDES correctly on a payload. They cannot prove the harness
     delivers that payload for every shell path in every CLI build - that is what `hooks.json`
     registration (asserted below) keeps wired.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / "plugins" / "odoo-ai-agents"
HOOK = PLUGIN_ROOT / "hooks" / "block-unowned-lease-mutation.sh"
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"

_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or _BASH is None,
    reason="hook needs jq + bash; absent here (the hook itself degrades to a silent pass)",
)

ALLOC = 'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py"'


def _run(command, *, agent_type="odoo-qa-planner", agent_id="a1", tool="Bash", raw=None):
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool,
               "tool_input": {"command": command}}
    if agent_id is not None:
        payload["agent_id"] = agent_id
    if agent_type is not None:
        payload["agent_type"] = agent_type
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    return subprocess.run(
        [_BASH, str(HOOK)],
        input=raw if raw is not None else json.dumps(payload),
        capture_output=True, text=True, env=env, timeout=30, check=False,
    )


def _denied(proc):
    assert proc.returncode == 0, f"must exit 0; rc={proc.returncode} stderr={proc.stderr!r}"
    assert proc.stdout.strip(), "expected a deny JSON on stdout, got nothing"
    out = json.loads(proc.stdout)
    hso = out.get("hookSpecificOutput", {})
    assert hso.get("hookEventName") == "PreToolUse"
    assert hso.get("permissionDecision") == "deny", f"expected deny, got {out!r}"
    assert "decision" not in out, (
        "the SubagentStop {'decision':'block'} shape is a different event's schema and is silently "
        f"ignored on PreToolUse: {out!r}"
    )
    reason = hso.get("permissionDecisionReason") or ""
    assert reason.strip(), "a deny with no reason strands the caller"
    return reason


def _passed(proc):
    assert proc.returncode == 0, f"must exit 0; rc={proc.returncode} stderr={proc.stderr!r}"
    assert not proc.stdout.strip(), (
        f"expected a silent pass, got a decision: {proc.stdout!r}"
    )


# --------------------------------------------------------------------------- #
# The incident, and the remedy it must name
# --------------------------------------------------------------------------- #
def test_a_subagent_release_that_names_no_owner_is_denied():
    """The exact command that destroyed the database."""
    reason = _denied(_run(f"{ALLOC} release abababababababababababababababab"))
    assert "--run-id" in reason, "the deny must name the flag a rightful owner threads"
    for expected in ("ALLOC_RUN_ID", "LEAVE IT ALONE", "park"):
        assert expected in reason, (
            f"the deny must tell the caller what to do instead; missing {expected!r}: {reason!r}"
        )


def test_the_deny_reason_refutes_the_reasoning_that_caused_the_incident():
    """A refusal that only says "no" leaves the caller's WRONG premises intact, and the next
    dispatch reaches the same conclusion. The premises were: an absent owner.pid means abandoned;
    same-run provenance means stale; holding the token means ownership."""
    reason = _denied(_run(f"{ALLOC} release tok"))
    assert "owner.pid" in reason and "abandoned" in reason, (
        f"the deny must refute 'no pid means abandoned': {reason!r}"
    )
    assert "SAME run" in reason, f"the deny must refute same-run-provenance staleness: {reason!r}"
    assert "not ownership" in reason, f"the deny must refute token-as-ownership: {reason!r}"


@pytest.mark.parametrize("command", [
    f'{ALLOC} release "$ALLOC_TOKEN" --run-id "$ALLOC_RUN_ID"',
    f"{ALLOC} release tok --run-id acceptance-run-a",
    f"{ALLOC} release tok --run-id=acceptance-run-a",
    f"{ALLOC} release tok --session legacy-run",
    f"{ALLOC} release tok --instances /srv/x/instances.toml --run-id r1",
])
def test_the_rightful_owner_is_never_blocked(command):
    """Every legitimate release shape passes untouched, for a subagent. A gate that stalled these
    would trade one data-loss hole for a fleet of stalled pipelines."""
    _passed(_run(command, agent_type="odoo-instance-ops"))


def test_a_run_id_cannot_be_borrowed_from_a_neighbouring_command():
    """Segment-scoped, or `release $T && echo --run-id x` would launder the incident straight
    through the lexical check."""
    _denied(_run(f"{ALLOC} release tok && echo --run-id x"))


# --------------------------------------------------------------------------- #
# Overrides are a human's call
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("command", [
    f"{ALLOC} release tok --run-id mine --force",
    f"{ALLOC} release tok --run-id mine --force-forget",
    f"{ALLOC} release tok --force",
    f"{ALLOC} reap-orphans --yes",
    f"{ALLOC} reap-orphans --min-age-s 60 --yes",
])
def test_a_subagent_may_not_override_the_ownership_decision(command):
    reason = _denied(_run(command, agent_type="odoo-coder"))
    assert "BLOCKED" in reason, (
        f"the deny must name the reporting exit, not just refuse: {reason!r}"
    )


def test_threading_a_run_id_does_not_buy_a_force():
    """Order matters: the override arm is evaluated first, so a well-formed release cannot smuggle
    an override past the gate by also naming an owner."""
    _denied(_run(f"{ALLOC} release tok --run-id mine --force", agent_type="odoo-instance-ops"))


# --------------------------------------------------------------------------- #
# Everything the gate must NOT touch
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("command", [
    f"{ALLOC} acquire --series 17.0 --mode ephemeral --ports 0 --run-id r1",
    f"{ALLOC} bind tok --pid 4242",
    f"{ALLOC} park tok",
    f"{ALLOC} park tok --park-ttl 7200",
    f"{ALLOC} resume tok --pid 4242",
    f"{ALLOC} heartbeat tok",
    f"{ALLOC} gc",
    f"{ALLOC} reap-orphans",
    f"{ALLOC} list --show-tokens",
    f"{ALLOC} query --series 17.0 --state parked",
    f"{ALLOC} assert-droppable --db-name odoo_17_0 --run-id r1",
    f"{ALLOC} --help",
])
def test_non_destructive_and_janitor_verbs_pass(command):
    """gc and reap-orphans judge "provably abandoned" / "no lease references this database at all",
    never "not mine", so neither needs an ownership check; the rest reserve, observe, or suspend.
    park in particular MUST pass - it is one of the three exits the SubagentStop teardown gate
    accepts, so refusing it could deadlock a subagent between a refused release and a refused
    park."""
    _passed(_run(command, agent_type="odoo-qa-planner"))


@pytest.mark.parametrize("command", [
    "grep -rn 'allocator.py release' scripts/",
    'grep -rn "allocator.py release tok" .',
    "sed -n '/allocator.py release/p' snippets/instance-resolution.md",
    'echo "then run: allocator.py release $TOKEN"',
    'python3 -c \'print("allocator.py release tok")\'',
    "cat scripts/lib/allocator.py",
])
def test_reading_or_quoting_the_command_is_not_running_it(command):
    """Found by this file, not by review: the first detector matched `allocator.py` + a verb
    anywhere in the text, so `grep -rn 'allocator.py release' scripts/` was DENIED. A gate that
    blocks reading the code it guards is an outage, not a safeguard - and it would have blocked the
    very investigation that diagnoses an incident. The verb must sit in an EXECUTION position: the
    script token is the segment's first token, or is preceded by a python interpreter."""
    _passed(_run(command))


def test_the_root_context_is_never_denied():
    """Same command as the incident, from main. A human is there to read the allocator's own
    refusal - and the allocator refuses it regardless of who calls."""
    _passed(_run(f"{ALLOC} release tok", agent_type=None, agent_id=None))


def test_a_non_bash_tool_is_never_denied():
    _passed(_run("irrelevant", tool="Write"))


@pytest.mark.parametrize("raw", ["", "not json", "{}", '{"tool_name":"Bash"}'])
def test_fails_open_on_an_unusable_payload(raw):
    _passed(_run("unused", raw=raw))


# --------------------------------------------------------------------------- #
# The documented residuals, pinned as PASSING so they stay measured facts
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("command", [
    'python3 "$ALLOC_PY" $VERB "$TOK"',                 # verb computed at runtime
    "bash teardown.sh",                                  # release lives inside the script
    f'{ALLOC} release tok --run-id ""',                  # present but empty
    f"{ALLOC} release tok --run-id $UNSET_VAR",          # present but unresolved
])
def test_documented_residual_is_really_a_residual(command):
    """Each of these SHOULD pass this hook. Two of them are still refused one layer down, by the
    allocator's own comparison under flock (tests/test_allocator.py); the first two are not caught
    anywhere and are named in the hook header. Pinning them keeps the hole reviewable instead of
    letting a future reader assume coverage the gate does not have."""
    _passed(_run(command))


# --------------------------------------------------------------------------- #
# Registration - the plugin's dominant defect is a correct mechanism nothing calls
# --------------------------------------------------------------------------- #
def _pretooluse_groups():
    return json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]


def test_hooks_json_registers_the_gate_and_its_matcher_reaches_bash():
    """The matcher is evaluated BEFORE the script runs, so a matcher that missed `Bash` would leave
    every case in this file testing a script the harness never invokes."""
    groups = [
        g for g in _pretooluse_groups()
        if any("block-unowned-lease-mutation.sh" in h.get("command", "")
               for h in g.get("hooks", []))
    ]
    assert groups, "hooks.json must register block-unowned-lease-mutation.sh under PreToolUse"
    for g in groups:
        matcher = g.get("matcher")
        assert matcher, "the gate must be matcher-scoped, not run on every tool call"
        assert re.match(matcher, "Bash"), (
            f"matcher {matcher!r} must accept 'Bash' - the shell is the only surface an allocator "
            "verb travels on, so omitting it disarms the gate entirely"
        )
        for tool in ("Read", "Write", "Edit", "Agent", "Skill"):
            assert not re.match(matcher, tool), (
                f"matcher {matcher!r} must not over-match {tool!r}"
            )


def test_the_hooks_json_description_does_not_undercount_the_denies():
    """A stale restatement is how a rule gets reverted: the description used to assert "exactly ONE
    PreToolUse hard deny", which this gate makes false. Whoever changes the count must change the
    sentence in the same commit."""
    desc = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["description"]
    denies = sum(
        1 for g in _pretooluse_groups() for h in g.get("hooks", [])
        if "block-" in h.get("command", "")
    )
    assert denies == 2, f"the deny set changed ({denies}) - update the description below too"
    assert "exactly TWO PreToolUse hard denies" in desc, (
        "the description must state the ACTUAL number of PreToolUse hard denies; a stale count is "
        f"the restatement that outlives its definition: {desc[:400]!r}"
    )
    assert "block-unowned-lease-mutation.sh" in desc, (
        "the description must name this gate, or a reader auditing the hook set will miss it"
    )
