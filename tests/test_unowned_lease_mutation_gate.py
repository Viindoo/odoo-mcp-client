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
  - **Adopting or parking a lease names its owner too.** `adopt` re-anchors a live lease onto the
    caller's session - it changes who vouches for an instance - and `park` stops the lease's server
    process group under the allocator's same ownership rule as `release`. A subagent's `adopt` or
    `park` without `--run-id` is DENIED exactly like a release without one, and `park --force` is
    an override like `release --force`.
  - **A dispatched agent may not APPLY a machine-wide reclaim.** The registry is shared by every
    session on the host, and an applying `gc` stops process groups and drops databases across all
    of them; a subagent's `gc` without `--dry-run` is DENIED. The dry run changes nothing and passes.
  - **An invocation inside a command substitution is still an invocation.** `eval "$(python3
    .../allocator.py acquire ...)"` is the allocator's own documented acquire shape, and `$(...)` /
    backticks EXECUTE their body even inside double quotes - every arm applies there too. A
    substitution inside SINGLE quotes is inert text and passes.
  - **Non-destructive verbs are never refused**: acquire, bind, resume, heartbeat, list, query,
    `gc --dry-run` and a list-only reap-orphans; a park that names its owner passes.
  - **The ROOT is never denied** (the rule its two sibling PreToolUse hooks follow): a human is
    present in the main context to read the allocator's own refusal. The allocator refuses a
    foreign or un-named release for EVERY caller regardless - this hook is the earlier,
    explanatory layer, and the layer that still holds if that predicate is loosened again.
  - **Fails OPEN on every uncertainty** and always exits 0.

REMAINING FALSE NEGATIVES - stated here and in the hook's own header, and PINNED below as passing
so each hole is a measured fact rather than a surprise:
  1. `resume` / `heartbeat` / `bind` on a lease the caller does not own. Those verbs accept no
     `--run-id`, so there is nothing to require.
  2. A run id that is present but WRONG or empty (`--run-id ""`). This arm is lexical; the
     allocator's comparison under flock is what catches those (tests/test_allocator.py).
  3. A verb or flag COMPUTED at runtime, or assembled inside a script the command only invokes.
  4. A release through any tool outside the `Bash` + odoo-local lease_release / lease_park
     matcher, or (arm A4) with a non-literal token or no readable agent transcript.
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


def test_every_park_remedy_the_gate_offers_names_its_owner():
    """The allocator refuses an un-named park of an owned lease (NOT_OWNER), and A1 refuses it here.
    A remedy line that spells `park <token>` bare is therefore a command that fails when followed -
    the refusal would send the caller straight into the next refusal."""
    for command, agent in ((f"{ALLOC} release tok", "odoo-qa-planner"),
                           (f"{ALLOC} gc --scope all", "odoo-instance-ops")):
        reason = _denied(_run(command, agent_type=agent))
        parks = re.findall(r"allocator\.py park [^`]*`", reason)
        assert parks, f"the deny must offer park as the keep-the-database exit: {reason!r}"
        for spelled in parks:
            assert "--run-id" in spelled, (
                f"a park remedy without --run-id is refused when followed: {spelled!r}"
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
    # A command written across two physical lines is ONE command. Splitting before joining put the
    # verb and its owner flag in different segments, so this exact shape - the owner releasing its
    # own lease - was refused, twice in real runs. Once it cost a leaked ephemeral database; once
    # the agent rejoined the line and the release went through, which means the guard's own
    # remediation text was a working bypass.
    f"{ALLOC} release tok \\\n    --run-id r1",
    f"{ALLOC} release \\\n    tok --run-id r1",
    # A separator INSIDE quotes is part of an argument, not a command boundary. Splitting there
    # cut the command before its owner flag and refused the rightful owner - the same lexical
    # mistake that, in the source-write gate, let a real write through instead.
    f'{ALLOC} release tok --reason "cleanup a && b" --run-id r1',
    f"{ALLOC} release tok --reason 'phase 1; phase 2' --run-id r1",
    # park is one of the three exits the SubagentStop teardown gate accepts: the owner parking its
    # own lease must pass, or a subagent is trapped between that gate and this one.
    f'{ALLOC} park "$ALLOC_TOKEN" --run-id "$ALLOC_RUN_ID"',
    f"{ALLOC} park tok --run-id r1 --park-ttl 7200",
    f"{ALLOC} park tok \\\n    --run-id r1",
])
def test_the_rightful_owner_is_never_blocked(command):
    """Every legitimate release shape passes untouched, for a subagent. A gate that stalled these
    would trade one data-loss hole for a fleet of stalled pipelines."""
    _passed(_run(command, agent_type="odoo-instance-ops"))


@pytest.mark.parametrize("command", [
    f"{ALLOC} adopt tok",
    f"{ALLOC} adopt tok --reason handover",
    f"{ALLOC} park tok",
    f"{ALLOC} park tok --park-ttl 7200",
    f'eval "$({ALLOC} park tok)"',
    f'TOK=$({ALLOC} release tok)',
    f'eval "$({ALLOC} release tok)"',
    f"eval {ALLOC} release tok",
    f'echo "released: $(echo $({ALLOC} release tok))"',
])
def test_an_owner_naming_verb_without_an_owner_is_denied_in_every_executed_shape(command):
    """A1 covers `adopt` (it moves who vouches for a live lease) and `park` (it stops the lease's
    server process group - the allocator refuses an un-named park of an owned lease as NOT_OWNER),
    and applies inside every shape the shell EXECUTES - a command substitution, a nested one, an
    `eval` - not only a bare line."""
    reason = _denied(_run(command))
    assert "--run-id" in reason, f"the deny must name the missing owner flag: {reason!r}"


@pytest.mark.parametrize("command", [
    f"{ALLOC} gc",
    f"{ALLOC} gc --scope all",
    f"{ALLOC} gc --scope dead-sessions",
    f"{ALLOC} gc --scope anchor --anchor mine --force",
    f'OUT="$({ALLOC} gc --scope dead-sessions)"',
])
def test_a_subagent_may_not_apply_a_machine_wide_gc(command):
    """The registry is shared by every session on this host; an applying gc stops process groups
    and DROPS databases across all of them. From a dispatch that is never the right call: free
    what you obtained by token, report what a janitor would reclaim. MUST FAIL on the pre-fix hook
    (measured: every one of these passed as a "janitor verb")."""
    reason = _denied(_run(command, agent_type="odoo-instance-ops"))
    assert "--dry-run" in reason and "lease_release" in reason, (
        f"the deny must name the dry run and the by-token give-back instead: {reason!r}"
    )


def test_the_main_context_may_still_apply_a_gc():
    """A human is present in the main context to read what gc would reclaim - the arm is scoped to
    subagents like every other arm of this gate."""
    _passed(_run(f"{ALLOC} gc --scope all", agent_type=None, agent_id=None))


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
    f"{ALLOC} park tok --run-id mine --force",
    f"{ALLOC} park tok --force",
    f"{ALLOC} reap-orphans --yes",
    f"{ALLOC} reap-orphans --min-age-s 60 --yes",
    # The SAME split, in the direction that loses data rather than stalling a pipeline: an override
    # flag on the continuation line landed in a segment carrying no allocator token at all, so arm
    # A2 never looked at it and a subagent was one newline away from --force-forget on a live
    # lease. hooks.json claims this arm refuses "any --force / --force-forget / reap-orphans --yes
    # override from a subagent"; before the join that sentence was false.
    f"{ALLOC} release tok --run-id mine \\\n    --force",
    f"{ALLOC} release tok \\\n    --force-forget",
    f"{ALLOC} reap-orphans \\\n    --yes",
    # `acquire --allow-unowned` is the allocator's deliberate opt-out from naming an owner. For a
    # HUMAN or a fixture that is a legitimate declaration; for a dispatched agent it is the wrong
    # answer to the only question the refusal asks - it reached for the flag because it holds no
    # run id, and an ownerless lease is invisible to the run that would have to reap it.
    f"{ALLOC} acquire --series 17.0 --mode ephemeral --allow-unowned",
    # The documented eval shape, which the verb parser used to read as a MENTION: `eval` was not a
    # wrapper and `"$(python3` is not an interpreter token, so no arm ever looked inside it.
    f'eval "$({ALLOC} acquire --series 17.0 --mode ephemeral --allow-unowned)"',
    f"X=$({ALLOC} release tok --run-id mine --force)",
    f'echo "`{ALLOC} reap-orphans --yes`"',
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
    f"{ALLOC} resume tok --pid 4242",
    f"{ALLOC} heartbeat tok",
    f"{ALLOC} adopt tok --run-id r1",
    f"{ALLOC} gc --dry-run",
    f"{ALLOC} gc --scope all --dry-run",
    f'eval "$({ALLOC} acquire --series 17.0 --mode ephemeral --ports 1 --run-id r1)"',
    f"TOK=$({ALLOC} release tok --run-id r1)",
    f"{ALLOC} reap-orphans",
    f"{ALLOC} list --show-tokens",
    f"{ALLOC} query --series 17.0 --state parked",
    f"{ALLOC} assert-droppable --db-name odoo_17_0 --run-id r1",
    f"{ALLOC} --help",
])
def test_non_destructive_verbs_pass(command):
    """A dry-run gc and a list-only reap-orphans change nothing; the rest reserve, observe, suspend,
    or name their owner - including inside the documented eval / command-substitution shapes."""
    _passed(_run(command, agent_type="odoo-qa-planner"))


@pytest.mark.parametrize("command", [
    f"{ALLOC} release --help",
    f"{ALLOC} release -h",
    f"{ALLOC} park --help",
    f"{ALLOC} adopt --help",
    f"{ALLOC} gc --help",
    f"{ALLOC} release tok --help",
    f"{ALLOC} release '--help'",
])
def test_asking_a_verb_for_its_usage_is_not_running_it(command):
    """Observed live: an agent read `allocator.py release --help` to learn the flags, and was
    refused for naming no owner. The allocator answers `-h`/`--help` anywhere in a verb's own
    arguments with usage text and exits before touching a lease, so there is nothing to own."""
    _passed(_run(command, agent_type="odoo-qa-planner"))


@pytest.mark.parametrize("command", [
    f'{ALLOC} release tok --reason "see --help"',
    f"{ALLOC} release tok --reason 'a -h b'",
])
def test_a_help_word_inside_a_quoted_value_buys_no_pass(command):
    """A `--help` spelled inside a quoted value reaches the allocator as part of that value, so the
    release really runs - it still has to name its owner."""
    _denied(_run(command, agent_type="odoo-qa-planner"))


@pytest.mark.parametrize("command", [
    "grep -rn 'allocator.py release' scripts/",
    'grep -rn "allocator.py release tok" .',
    "sed -n '/allocator.py release/p' snippets/instance-resolution.md",
    'echo "then run: allocator.py release $TOKEN"',
    'python3 -c \'print("allocator.py release tok")\'',
    "cat scripts/lib/allocator.py",
    # The interpreter spelled INSIDE the quoted sentence. The old test was adjacency - the script
    # token preceded by a python token anywhere in the segment - so the moment a remediation line
    # quoted the interpreter too, the mention read as an invocation. This gate refused a read-only
    # analysis command twice while its own sibling defect was being investigated.
    'echo "then run: python3 scripts/lib/allocator.py release $TOKEN"',
    "grep -rn 'python3 scripts/lib/allocator.py release' docs/",
    # A worklog entry describing the refusal. The body of a DATA heredoc is prose, not a command.
    ("cat >> /w/.odoo-ai/worklog/run-1/odoo-coder.md <<'EOF'\n"
     "BLOCKED: python3 scripts/lib/allocator.py release tok was refused; no owner to cite.\n"
     "EOF"),
    # A substitution inside SINGLE quotes is inert text - the shell never runs it.
    "echo 'the incident ran: $(python3 scripts/lib/allocator.py release tok)'",
    "grep -n '`python3 scripts/lib/allocator.py gc`' docs/x.md",
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
    PreToolUse hard deny", then "exactly TWO", then "exactly THREE" - each made false by the next
    gate (this one, block-handback-with-live-lease.sh, block-capture-outside-state-root.sh).
    Whoever changes the count must change the sentence in the same commit."""
    desc = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["description"]
    denies = sum(
        1 for g in _pretooluse_groups() for h in g.get("hooks", [])
        if "block-" in h.get("command", "")
    )
    assert denies == 4, f"the deny set changed ({denies}) - update the description below too"
    assert "exactly FOUR PreToolUse hard denies" in desc, (
        "the description must state the ACTUAL number of PreToolUse hard denies; a stale count is "
        f"the restatement that outlives its definition: {desc[:400]!r}"
    )
    assert "block-unowned-lease-mutation.sh" in desc, (
        "the description must name this gate, or a reader auditing the hook set will miss it"
    )


def test_the_hooks_json_description_attributes_command_segmenting_to_the_right_denies():
    """Review finding 3: next to the "exactly N PreToolUse hard denies" count the description said "Both
    PreToolUse denies segment the command" - a count word left over from when there were two. Only
    the denies that SOURCE hooks/command-segments.sh segment anything (the SubagentHandback gate
    parses a report, not a command). Read that set from the scripts, not from this test."""
    desc = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["description"]
    hooks_dir = HOOKS_JSON.parent
    denies = sorted({
        Path(h["command"].split()[-1].strip('"')).name
        for g in _pretooluse_groups() for h in g.get("hooks", [])
        if "block-" in h.get("command", "")
    })
    segmenters = [d for d in denies
                  if "command-segments.sh" in (hooks_dir / d).read_text(encoding="utf-8")]
    assert segmenters and len(segmenters) < len(denies), (
        f"test premise changed: segmenters={segmenters} denies={denies}"
    )
    sentences = [s for s in re.split(r"(?<=[.])\s+", desc) if "command-segments.sh" in s]
    assert len(sentences) == 1, f"expected one sentence naming command-segments.sh: {sentences}"
    sentence = sentences[0]
    assert not re.search(r"\b(both|all|every|each)\b[^.]*\bdenies\b", sentence, re.I), (
        f"a blanket count word over the denies is false while only {segmenters} segment: "
        f"{sentence!r}"
    )
    for d in denies:
        if d in segmenters:
            assert d in sentence, f"{d} segments commands but the sentence does not name it"
        else:
            assert d not in sentence, f"{d} does not segment commands yet the sentence claims it"


# --------------------------------------------------------------------------- #
# Arm A4 - release/park only a lease THIS agent holds.
#
# Ownership is RUN-scoped in the allocator, and an INSTANCE_HANDLE forwarded DOWN carries the
# provider's run_id - so a consumer that copies it names a real owner, passes arm A1, and the
# allocator ACCEPTS the release, destroying the instance its provider still uses. The contract
# (snippets/resource-teardown-contract.md T1) is narrower than the run: release/park only a lease
# you obtained, or one a child you dispatched handed back UP. Read from the caller's OWN transcript.
# --------------------------------------------------------------------------- #
MCP = "mcp__plugin_odoo-ai-agents_odoo-local__"
P_TOK = "a1" * 16   # the provider's (parent's) lease
C_TOK = "c3" * 16   # a lease the calling agent obtained itself
_SEQ = iter(range(1, 10**6))


def _use(name, inp):
    tid = f"toolu_a4_{next(_SEQ):05d}"
    return tid, json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tid, "name": name, "input": inp}]}})


def _result(tid, content, tool_use_result=None, **extra):
    rec = {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": content}]}}
    if tool_use_result is not None:
        rec["toolUseResult"] = tool_use_result
    rec.update(extra)
    return json.dumps(rec)


def _brief(text):
    return json.dumps({"type": "user", "message": {"role": "user", "content": text}})


def _forwarded_brief():
    return _brief(f"Run the tests on the forwarded instance. INSTANCE_HANDLE: lease_token: {P_TOK}, "
                  f"run_id: run-R, url: http://localhost:8170")


def _mcp_acquire(tok=C_TOK):
    tid, use = _use(MCP + "lease_acquire", {"series": "17.0", "run_id": "run-R"})
    payload = {"lease": {"token": tok, "run_id": "run-R"}}
    return [use, _result(tid, [{"type": "text", "text": json.dumps(payload)}],
                         tool_use_result={"structuredContent": payload})]


def _eval_acquire(tok=C_TOK):
    tid, use = _use("Bash", {"command": f'eval "$({ALLOC} acquire --series 17.0 --run-id run-R)"'})
    return [use, _result(tid, f"allocator: acquired lease {tok} run_id=run-R\n")]


def _serve_forwarded():
    tid, use = _use(MCP + "instance_serve", {"lease_token": P_TOK, "run_id": "run-R"})
    res = {"state": "running", "lease_token": P_TOK}
    return [use, _result(tid, [{"type": "text", "text": json.dumps(res)}],
                         tool_use_result={"structuredContent": res})]


def _run_a4(tmp_path, lines, *, tool, tool_input, agent=True, layout="agent_path"):
    """Invoke the gate with the caller's OWN transcript. `layout` picks how the payload points at
    it: `agent_path` (agent_transcript_path), `derived` (only transcript_path + agent_id, resolved
    through the harness's `<session>/subagents/agent-<id>.jsonl` layout), or `none`."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    session = tmp_path / "sess.jsonl"
    session.write_text("", encoding="utf-8")
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input,
               "transcript_path": str(session)}
    if agent:
        payload["agent_id"] = "a4agent"
        payload["agent_type"] = "odoo-ai-agents:odoo-qa-tester"
    if layout == "agent_path":
        tpath = tmp_path / "agent.jsonl"
        payload["agent_transcript_path"] = str(tpath)
    elif layout == "derived":
        tpath = tmp_path / "sess" / "subagents" / "agent-a4agent.jsonl"
        tpath.parent.mkdir(parents=True)
    else:
        tpath = tmp_path / "unused.jsonl"
    if layout != "none":
        tpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    return subprocess.run([_BASH, str(HOOK)], input=json.dumps(payload), capture_output=True,
                          text=True, env=env, timeout=30, check=False)


@pytest.mark.parametrize("tool", ["lease_release", "lease_park"])
@pytest.mark.parametrize("key", ["token", "lease_token"])
def test_a_consumer_may_not_release_or_park_a_handle_forwarded_down(tmp_path, tool, key):
    """THE BLOCKER, reproduced: the consumer received P in its brief, served it (consumption), and
    then tries to give it back with the run_id copied from the handle. The allocator would accept
    that - the gate must not. Both token argument spellings are covered."""
    lines = [_forwarded_brief(), *_serve_forwarded()]
    reason = _denied(_run_a4(tmp_path, lines, tool=MCP + tool,
                             tool_input={key: P_TOK, "run_id": "run-R"}))
    assert "forwarded to you" in reason and "hand it back UP" in reason
    assert P_TOK in reason


@pytest.mark.parametrize("verb", ["release", "park"])
def test_a_consumer_may_not_release_a_forwarded_handle_through_bash_either(tmp_path, verb):
    lines = [_forwarded_brief(), *_serve_forwarded()]
    reason = _denied(_run_a4(tmp_path, lines, tool="Bash",
                             tool_input={"command": f"{ALLOC} {verb} {P_TOK} --run-id run-R"}))
    assert "forwarded to you" in reason


@pytest.mark.parametrize("key", ["token", "lease_token"])
@pytest.mark.parametrize("tool", ["lease_release", "lease_park"])
def test_the_agent_that_acquired_the_lease_may_release_or_park_it(tmp_path, key, tool):
    """Red-before-green's other half: the rightful owner is never blocked."""
    lines = [_brief("build and test sale"), *_mcp_acquire()]
    _passed(_run_a4(tmp_path, lines, tool=MCP + tool, tool_input={key: C_TOK, "run_id": "run-R"}))


@pytest.mark.parametrize("command", [
    f"{ALLOC} release {C_TOK} --run-id run-R",
    f"{ALLOC} release --run-id run-R {C_TOK}",
    f'{ALLOC} park "{C_TOK}" --run-id run-R',
])
def test_an_eval_acquirer_may_give_back_its_own_lease_through_bash(tmp_path, command):
    lines = [_brief("build and test sale"), *_eval_acquire()]
    _passed(_run_a4(tmp_path, lines, tool="Bash", tool_input={"command": command}))


def test_an_acquirer_that_trimmed_its_acquire_output_may_still_release_its_own_lease(tmp_path):
    """Observed live: an agent ran `allocator.py acquire ... 2>&1 | tail -5`, and its own release
    of that lease was refused as unowned - the trim had cut every line naming the token. The
    allocator now writes its receipt as the LAST line of the merged stream
    (tests/test_allocator_lease_contracts.py pins that), so the tail the agent saw names the lease
    and the release passes. What a tail cannot leave is anything naming another lease."""
    tid, use = _use("Bash", {"command": f"{ALLOC} acquire --series 17.0 --mode exclusive "
                                        f"--no-create --run-id run-R 2>&1 | tail -5"})
    tail = ("ALLOC_DB_USER=odoo\nALLOC_DB_PORT=5437\nALLOC_SERIES=17.0\n"
            "ALLOC_SERVER_WIDE_MODULES=''\n"
            f"allocator: acquired lease {C_TOK} run_id=run-R\n")
    lines = [_brief("build"), use, _result(tid, tail)]
    _passed(_run_a4(tmp_path, lines, tool="Bash",
                    tool_input={"command": f"{ALLOC} release {C_TOK} --run-id run-R"}))


def test_an_orchestrator_may_release_a_lease_a_child_handed_up(tmp_path):
    """The orchestrator dispatched a child that provisioned C for the run and handed it back UP in
    its report (an async task-notification); the orchestrator now owns its teardown."""
    tid, use = _use("Agent", {"description": "provision", "prompt": "provision an instance"})
    launched = _result(tid, [{"type": "text", "text": "Async agent launched successfully."}],
                       tool_use_result={"isAsync": True, "status": "async_launched",
                                        "prompt": "provision an instance"})
    note = json.dumps({"type": "user", "origin": {"kind": "task-notification"},
                       "message": {"role": "user", "content": (
                           f"<task-notification>\n<tool-use-id>{tid}</tool-use-id>\n"
                           f"<status>completed</status>\n<result>```continuation\nstatus: NEEDS_NEXT\n"
                           f"next:\n  inputs:\n    INSTANCE_HANDLE: {{lease_token: {C_TOK}, run_id: run-R}}\n"
                           f"```</result>\n</task-notification>")}})
    lines = [_brief("run the pipeline"), use, launched, note]
    _passed(_run_a4(tmp_path, lines, tool=MCP + "lease_release",
                    tool_input={"token": C_TOK, "run_id": "run-R"}))


def test_a_synchronous_child_report_is_a_hand_up_too(tmp_path):
    tid, use = _use("Task", {"description": "provision", "prompt": "provision"})
    lines = [_brief("run"), use,
             _result(tid, [{"type": "text", "text": f"INSTANCE_HANDLE lease_token: {C_TOK}"}])]
    _passed(_run_a4(tmp_path, lines, tool=MCP + "lease_park",
                    tool_input={"lease_token": C_TOK, "run_id": "run-R"}))


# A child that delivers its report through the SubagentHandback tool reaches its caller ONLY as a
# PEER message - the Agent result and the task-notification then just point at it ("This agent's
# report was delivered to you as a message from ..."). The record shapes below are the ones the
# harness writes (observed in real transcripts): a `user` record carrying `origin` when the caller
# is idle (async child), and an `attachment` record of type `queued_command` carrying
# `attachment.origin` while the caller is blocked on a synchronous Agent call.
_KID = "a7c1d2e3f4a5b6c7d"
_POINTER = (f"This agent's report was delivered to you as a message from \"{_KID}\" "
            "(its SubagentHandback call). Read it there; it is not repeated here.")


def _handback_body(tok):
    return ("[Subagent hand-back] The text below is the final report of a subagent this session "
            "delegated to. The report follows:\n  Provisioned the instance.\n  ```continuation\n"
            "  status: NEEDS_NEXT\n  next:\n    inputs:\n"
            f"      INSTANCE_HANDLE: {{lease_token: {tok}, run_id: run-R}}\n  ```")


def _peer_user_record(sender, body, handback=True):
    origin = {"kind": "peer", "from": sender, "senderTaskId": sender, "body": body}
    if handback:
        origin["handback"] = True
    return json.dumps({"type": "user", "isMeta": True, "origin": origin,
                       "message": {"role": "user", "content": (
                           f"Another Claude session sent a message:\n<agent-message from=\"{sender}\">\n"
                           f"{body}\n</agent-message>")}})


def _peer_queued_attachment(sender, body):
    return json.dumps({"type": "attachment", "attachment": {
        "type": "queued_command", "commandMode": "prompt", "isMeta": True,
        "prompt": f"<agent-message from=\"{sender}\">\n{body}\n</agent-message>",
        "origin": {"kind": "peer", "from": sender, "senderTaskId": sender, "body": body,
                   "handback": True}}})


def _async_launch(agent_id=_KID):
    tid, use = _use("Agent", {"description": "provision", "prompt": "provision an instance"})
    launched = _result(tid, [{"type": "text", "text": (
        f"Async agent launched successfully.\nagentId: {agent_id} (internal ID)")}],
        tool_use_result={"isAsync": True, "status": "async_launched", "agentId": agent_id,
                         "prompt": "provision an instance"})
    note = json.dumps({"type": "user", "origin": {"kind": "task-notification"},
                       "message": {"role": "user", "content": (
                           f"<task-notification>\n<task-id>{agent_id}</task-id>\n"
                           f"<tool-use-id>{tid}</tool-use-id>\n<status>completed</status>\n"
                           f"<result>{_POINTER}\n</result>\n</task-notification>")}})
    return use, launched, note


@pytest.mark.parametrize("tool", ["lease_release", "lease_park"])
def test_a_caller_may_release_a_lease_its_async_child_handed_back_through_subagenthandback(
        tmp_path, tool):
    """The child provisioned C and handed it UP through SubagentHandback; the report reached the
    caller as a peer message from the child's agentId. The caller now owns C's teardown - refusing
    it (as "forwarded to you") strands a lease nobody may give back."""
    use, launched, note = _async_launch()
    lines = [_brief("run the pipeline"), use, launched, note,
             _peer_user_record(_KID, _handback_body(C_TOK))]
    _passed(_run_a4(tmp_path, lines, tool=MCP + tool,
                    tool_input={"lease_token": C_TOK, "run_id": "run-R"}))


def test_a_caller_may_release_a_lease_its_synchronous_child_handed_back_through_subagenthandback(
        tmp_path):
    """Synchronous child: the Agent result is only a pointer, and the report arrives as a
    queued_command attachment while the caller is blocked on the call."""
    tid, use = _use("Agent", {"description": "provision", "prompt": "provision an instance"})
    done = _result(tid, [{"type": "text", "text": _POINTER}],
                   tool_use_result={"status": "completed", "agentId": _KID,
                                    "agentType": "general-purpose", "handback": "send"})
    lines = [_brief("run the pipeline"), use, _peer_queued_attachment(_KID, _handback_body(C_TOK)),
             done]
    _passed(_run_a4(tmp_path, lines, tool=MCP + "lease_release",
                    tool_input={"lease_token": C_TOK, "run_id": "run-R"}))


def test_a_later_message_from_the_child_is_a_hand_up_too(tmp_path):
    """A child's message after its handback arrives as a peer message WITHOUT the handback flag;
    it still comes from a child this caller launched, so a token in it was handed UP."""
    use, launched, note = _async_launch()
    lines = [_brief("run the pipeline"), use, launched, note,
             _peer_user_record(_KID, "Report delivered.", handback=True),
             _peer_user_record(_KID, _handback_body(C_TOK), handback=False)]
    _passed(_run_a4(tmp_path, lines, tool=MCP + "lease_release",
                    tool_input={"lease_token": C_TOK, "run_id": "run-R"}))


def test_a_peer_message_from_an_agent_this_caller_never_launched_is_not_a_hand_up(tmp_path):
    """Only an agentId one of THIS agent's own Agent/Task calls launched is its child. A peer
    message from anyone else - here its own caller, messaging it mid-flight - forwards the token
    DOWN, and the refusal must say so."""
    use, launched, note = _async_launch()
    lines = [_brief("run the pipeline"), use, launched, note,
             _peer_user_record("a0000000000stranger", _handback_body(P_TOK), handback=False)]
    reason = _denied(_run_a4(tmp_path, lines, tool=MCP + "lease_release",
                             tool_input={"lease_token": P_TOK, "run_id": "run-R"}))
    assert "forwarded to you" in reason, (
        "a peer message from a non-child is text this agent was GIVEN - word it as forwarded"
    )


def test_a_hand_up_is_never_worded_as_a_forwarded_brief(tmp_path):
    """The child's handback carries the token it handed UP. Even when the caller's own brief ALSO
    names that token, the hand-up wins; and a hand-up record alone is never brief text."""
    use, launched, note = _async_launch()
    lines = [_brief("run the pipeline"), use, launched, note,
             _peer_user_record(_KID, _handback_body(C_TOK))]
    tpath = tmp_path / "caller.jsonl"
    tpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script = (f'. "{PLUGIN_ROOT}/hooks/lease-correlation.sh"; '
              f'printf "UP<<%s>>\\n" "$(_lease_handed_up_text "{tpath}")"; '
              f'printf "BRIEF<<%s>>\\n" "$(_lease_brief_text "{tpath}")"')
    out = subprocess.run([_BASH, "-c", script], capture_output=True, text=True, timeout=30).stdout
    up = out.split("UP<<", 1)[1].split(">>", 1)[0]
    brief = out.split("BRIEF<<", 1)[1].split(">>", 1)[0]
    assert C_TOK in up, "the child's handback is text handed UP"
    assert C_TOK not in brief, "a child's handback must never be read as the caller's brief"


def test_forwarding_a_token_further_down_is_not_a_hand_up(tmp_path):
    """An async launch result echoes the PROMPT this agent sent DOWN. Passing P on to a grandchild
    does not make P this agent's - and a notification for a tool_use it never made is not its
    child's report either."""
    tid, use = _use("Agent", {"description": "test", "prompt": f"use lease_token {P_TOK}"})
    launched = _result(tid, [{"type": "text", "text": f"Async agent launched. prompt: {P_TOK}"}],
                       tool_use_result={"isAsync": True, "status": "async_launched",
                                        "prompt": f"use lease_token {P_TOK}"})
    stray = json.dumps({"type": "user", "origin": {"kind": "task-notification"},
                        "message": {"role": "user", "content": (
                            f"<task-notification><tool-use-id>toolu_not_mine</tool-use-id>"
                            f"<result>lease_token: {P_TOK}</result></task-notification>")}})
    lines = [_forwarded_brief(), use, launched, stray]
    _denied(_run_a4(tmp_path, lines, tool=MCP + "lease_release",
                    tool_input={"token": P_TOK, "run_id": "run-R"}))


def test_a_token_found_rather_than_obtained_is_refused(tmp_path):
    """The original incident's shape on the MCP surface: a token seen in a listing is not owned."""
    tid, use = _use(MCP + "lease_list", {})
    lines = [_brief("read the docs"), use,
             _result(tid, [{"type": "text", "text": json.dumps({"leases": [{"token": P_TOK}]})}])]
    reason = _denied(_run_a4(tmp_path, lines, tool=MCP + "lease_release",
                             tool_input={"token": P_TOK, "run_id": "run-R"}))
    assert "nothing in your own transcript shows you obtaining" in reason


def test_the_transcript_is_found_through_the_harness_layout_too(tmp_path):
    """PreToolUse may carry only transcript_path + agent_id; the agent's own transcript is then
    `<session>/subagents/agent-<agent_id>.jsonl`."""
    lines = [_forwarded_brief()]
    _denied(_run_a4(tmp_path, lines, tool=MCP + "lease_release",
                    tool_input={"token": P_TOK, "run_id": "run-R"}, layout="derived"))


def test_the_main_context_is_never_denied_by_the_ownership_arm(tmp_path):
    lines = [_forwarded_brief()]
    _passed(_run_a4(tmp_path, lines, tool=MCP + "lease_release",
                    tool_input={"token": P_TOK, "run_id": "run-R"}, agent=False))


def test_an_unreadable_transcript_fails_open_and_says_so(tmp_path):
    proc = _run_a4(tmp_path, [], tool=MCP + "lease_release",
                   tool_input={"token": P_TOK, "run_id": "run-R"}, layout="none")
    _passed(proc)
    assert "fail open" in proc.stderr


def test_the_ownership_arm_matcher_reaches_the_mcp_give_back_tools():
    groups = [g for g in _pretooluse_groups()
              if any("block-unowned-lease-mutation.sh" in h.get("command", "")
                     for h in g.get("hooks", []))]
    for tool in ("lease_release", "lease_park", "lease_adopt"):
        assert any(re.fullmatch(g["matcher"], MCP + tool) for g in groups), (
            f"{tool} must reach the gate - a matcher that misses it disarms arm A4 on the primary "
            "give-back surface"
        )
    for tool in ("lease_acquire", "instance_serve", "lease_list"):
        assert not any(re.fullmatch(g["matcher"], MCP + tool) for g in groups)


def test_every_lease_the_teardown_gate_orders_released_passes_this_gate(tmp_path):
    """The two gates share ONE correlation (hooks/lease-correlation.sh). If they disagreed, the
    SubagentStop gate would order a release this gate refuses - a deadlock. For each obtaining
    shape the teardown gate correlates, the release it would order must pass here."""
    lib = PLUGIN_ROOT / "hooks" / "lease-correlation.sh"
    for lines in ([_brief("x"), *_mcp_acquire()], [_brief("x"), *_eval_acquire()]):
        t = tmp_path / f"t{next(_SEQ)}.jsonl"
        t.write_text("\n".join(lines) + "\n", encoding="utf-8")
        owned = subprocess.run([_BASH, "-c", f'. "{lib}"; _lease_owned_tokens "{t}"'],
                               capture_output=True, text=True, timeout=30).stdout.split()
        assert owned == [C_TOK]
        for tok in owned:
            _passed(_run_a4(tmp_path / f"d{next(_SEQ)}", lines, tool=MCP + "lease_release",
                            tool_input={"token": tok, "run_id": "run-R"}))


# --------------------------------------------------------------------------- #
# Arm A4 on ADOPT - a take-over of a lease is ownership moving, so it carries the same proof, plus
# one legitimate source release/park never gets: a parked lease of the caller's own run that its
# OWN lease_find returned (resume in a new session: lease_find(parked, run_id) -> lease_adopt).
# --------------------------------------------------------------------------- #
def _lease_find(tok):
    tid, use = _use(MCP + "lease_find", {"series": "17.0", "state": "parked", "run_id": "run-R"})
    res = {"found": True, "state": "parked", "lease": {"token": tok, "run_id": "run-R", "yours": True}}
    return [use, _result(tid, [{"type": "text", "text": json.dumps(res)}],
                         tool_use_result={"structuredContent": res})]


@pytest.mark.parametrize("key", ["token", "lease_token"])
def test_a_consumer_may_not_adopt_a_handle_forwarded_down(tmp_path, key):
    """Adopting re-anchors the provider's live lease onto the consumer - after which the consumer
    'owns' it and every later gate would let it release it. A forwarded handle is never yours."""
    lines = [_forwarded_brief(), *_serve_forwarded()]
    reason = _denied(_run_a4(tmp_path, lines, tool=MCP + "lease_adopt",
                             tool_input={key: P_TOK, "run_id": "run-R"}))
    assert "forwarded to you" in reason and "hand it back UP" in reason


def test_a_consumer_may_not_adopt_a_forwarded_handle_through_bash_either(tmp_path):
    lines = [_forwarded_brief()]
    reason = _denied(_run_a4(tmp_path, lines, tool="Bash",
                             tool_input={"command": f"{ALLOC} adopt {P_TOK} --run-id run-R"}))
    assert "forwarded to you" in reason


@pytest.mark.parametrize("via", ["mcp", "bash"])
def test_resuming_a_parked_lease_found_by_its_own_lease_find_may_adopt_it(tmp_path, via):
    """The legitimate new-session path: the agent's own lease_find(parked, run_id) returned the
    token, so it may adopt it - even when its brief also named the token."""
    lines = [_forwarded_brief(), *_lease_find(P_TOK)]
    if via == "mcp":
        proc = _run_a4(tmp_path, lines, tool=MCP + "lease_adopt",
                       tool_input={"lease_token": P_TOK, "run_id": "run-R"})
    else:
        proc = _run_a4(tmp_path, lines, tool="Bash",
                       tool_input={"command": f"{ALLOC} adopt {P_TOK} --run-id run-R"})
    _passed(proc)


def test_finding_a_lease_is_never_grounds_to_release_or_park_it(tmp_path):
    """lease_find is an ADOPT source only. Found is not owned for a destructive give-back."""
    lines = [_brief("resume the parked instance"), *_lease_find(P_TOK)]
    for tool in ("lease_release", "lease_park"):
        _denied(_run_a4(tmp_path / tool, lines, tool=MCP + tool,
                        tool_input={"token": P_TOK, "run_id": "run-R"}))


def test_an_adopt_of_a_token_found_elsewhere_is_refused_and_names_the_lease_find_path(tmp_path):
    tid, use = _use(MCP + "lease_list", {})
    lines = [_brief("x"), use,
             _result(tid, [{"type": "text", "text": json.dumps({"leases": [{"token": P_TOK}]})}])]
    reason = _denied(_run_a4(tmp_path, lines, tool=MCP + "lease_adopt",
                             tool_input={"token": P_TOK, "run_id": "run-R"}))
    assert "lease_find" in reason


def test_a_failed_lease_find_found_nothing(tmp_path):
    tid, use = _use(MCP + "lease_find", {"state": "parked", "run_id": "run-R"})
    rec = json.loads(_result(tid, [{"type": "text", "text": json.dumps({"lease": {"token": P_TOK}})}]))
    rec["message"]["content"][0]["is_error"] = True
    _denied(_run_a4(tmp_path, [_brief("x"), use, json.dumps(rec)], tool=MCP + "lease_adopt",
                    tool_input={"token": P_TOK, "run_id": "run-R"}))


@pytest.mark.parametrize("key", ["token", "lease_token"])
def test_an_agent_may_adopt_what_it_obtained_or_was_handed_up(tmp_path, key):
    _passed(_run_a4(tmp_path / "own", [_brief("x"), *_mcp_acquire()], tool=MCP + "lease_adopt",
                    tool_input={key: C_TOK, "run_id": "run-R"}))
    tid, use = _use("Task", {"description": "provision", "prompt": "provision"})
    lines = [_brief("x"), use, _result(tid, [{"type": "text", "text": f"lease_token: {C_TOK}"}])]
    _passed(_run_a4(tmp_path / "up", lines, tool=MCP + "lease_adopt",
                    tool_input={key: C_TOK, "run_id": "run-R"}))


def test_an_adopt_this_gate_allowed_is_then_a_lease_the_teardown_gate_holds_it_to(tmp_path):
    """Cross-gate: once a lease_find -> lease_adopt succeeds, the shared correlation counts the
    adopted token as obtained - so the teardown gate will order its release, and this gate must
    then let that release through (no deadlock between the two)."""
    tid, use = _use(MCP + "lease_adopt", {"lease_token": P_TOK, "run_id": "run-R"})
    lines = [_forwarded_brief(), *_lease_find(P_TOK), use,
             _result(tid, [{"type": "text", "text": json.dumps({"lease_token": P_TOK})}])]
    t = tmp_path / "t.jsonl"
    t.write_text("\n".join(lines) + "\n", encoding="utf-8")
    lib = PLUGIN_ROOT / "hooks" / "lease-correlation.sh"
    owned = subprocess.run([_BASH, "-c", f'. "{lib}"; _lease_owned_tokens "{t}"'],
                           capture_output=True, text=True, timeout=30).stdout.split()
    assert owned == [P_TOK], "a successful adopt is obtainment for the teardown gate"
    for tool in ("lease_release", "lease_park"):
        _passed(_run_a4(tmp_path / tool, lines, tool=MCP + tool,
                        tool_input={"token": P_TOK, "run_id": "run-R"}))


# --------------------------------------------------------------------------- #
# A series-mode instance_serve is obtainment only when it LAUNCHED the server. An attach joined a
# server another run started (the shared declared instance); releasing it stops that server under
# every run still using it.
# --------------------------------------------------------------------------- #
def _serve_series(tok, state):
    tid, use = _use(MCP + "instance_serve", {"series": "17.0", "run_id": "run-R"})
    res = {"state": state, "lease_token": tok, "url": "http://localhost:8170"}
    return [use, _result(tid, [{"type": "text", "text": json.dumps(res)}],
                         tool_use_result={"structuredContent": res})]


@pytest.mark.parametrize("tool", ["lease_release", "lease_park"])
def test_attaching_to_a_running_server_is_not_obtainment(tmp_path, tool):
    """MUST FAIL on the pre-fix correlation: it counted the attach result's lease_token as owned."""
    lines = [_brief("render the form"), *_serve_series(P_TOK, "attached")]
    reason = _denied(_run_a4(tmp_path, lines, tool=MCP + tool,
                             tool_input={"lease_token": P_TOK, "run_id": "run-R"}))
    assert "LAUNCHED" in reason


def test_a_series_serve_that_launched_its_server_may_give_it_back(tmp_path):
    lines = [_brief("render the form"), *_serve_series(C_TOK, "launched")]
    _passed(_run_a4(tmp_path, lines, tool=MCP + "lease_release",
                    tool_input={"lease_token": C_TOK, "run_id": "run-R"}))


# --------------------------------------------------------------------------- #
# Resuming a PARKED lease of your own run: lease_find(parked) -> lease_adopt -> instance_serve.
# The adopt is the explicit take-over; after it the resumer may park or release what it resumed
# (and the teardown gate holds it to that - tests/test_enforce_teardown.py). Without the adopt the
# token is only FOUND, and the refusal must name the adopt path so the agent is never stranded.
# --------------------------------------------------------------------------- #
def _resume(tok, *, adopt):
    lines = [*_lease_find(tok)]
    if adopt:
        tid, use = _use(MCP + "lease_adopt", {"lease_token": tok, "run_id": "run-R"})
        adopted = {"lease": {"token": tok, "run_id": "run-R"}, "anchor": "123"}
        lines += [use, _result(tid, [{"type": "text", "text": json.dumps(adopted)}],
                               tool_use_result={"structuredContent": adopted})]
    tid, use = _use(MCP + "instance_serve", {"lease_token": tok})
    served = {"state": "launched", "resumed": True, "lease_token": tok}
    lines += [use, _result(tid, [{"type": "text", "text": json.dumps(served)}],
                           tool_use_result={"structuredContent": served})]
    return lines


@pytest.mark.parametrize("tool", ["lease_park", "lease_release"])
def test_the_agent_that_adopted_and_resumed_a_parked_lease_may_park_or_release_it(tmp_path, tool):
    lines = [_brief("resume the parked 17.0 instance"), *_resume(P_TOK, adopt=True)]
    _passed(_run_a4(tmp_path, lines, tool=MCP + tool,
                    tool_input={"lease_token": P_TOK, "run_id": "run-R"}))
    lib = PLUGIN_ROOT / "hooks" / "lease-correlation.sh"
    t = tmp_path / "rt.jsonl"
    t.write_text("\n".join(lines) + "\n", encoding="utf-8")
    owned = subprocess.run([_BASH, "-c", f'. "{lib}"; _lease_owned_tokens "{t}"'],
                           capture_output=True, text=True, timeout=30).stdout.split()
    assert owned == [P_TOK], "the adopt made the resumed lease this agent's - the teardown gate holds it"


def test_a_resume_without_the_adopt_is_refused_and_the_refusal_names_the_adopt(tmp_path):
    lines = [_brief("resume the parked 17.0 instance"), *_resume(P_TOK, adopt=False)]
    reason = _denied(_run_a4(tmp_path, lines, tool=MCP + "lease_park",
                             tool_input={"lease_token": P_TOK, "run_id": "run-R"}))
    assert "your own lease_find returned this parked lease" in reason, (
        "a found-but-not-adopted token must get the resume-specific refusal, not the generic one"
    )
    assert "lease_adopt {lease_token, run_id}" in reason and "then instance_serve" in reason, (
        "the refusal must name the take-over path, or the resumer is stranded with a running server"
    )


# --------------------------------------------------------------------------- #
# Interpreter options do not move the script out of execution position. `python3 -u .../allocator.py
# release <tok>` runs the allocator exactly like the bare form; before the fix every arm required
# the script as the VERY NEXT token after python, so any option walked past all four arms.
# --------------------------------------------------------------------------- #
_PYOPTS = ["-u", "-I", "-X dev", "-Xdev -W error", "-uB", "-O -s -E"]
_ALLOC_PATH = '"${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py"'


@pytest.mark.parametrize("opts", _PYOPTS)
def test_a1_holds_with_interpreter_options(opts):
    reason = _denied(_run(f"python3 {opts} {_ALLOC_PATH} release tok"))
    assert "--run-id" in reason


@pytest.mark.parametrize("opts", _PYOPTS)
def test_a2_holds_with_interpreter_options(opts):
    _denied(_run(f"python3 {opts} {_ALLOC_PATH} release tok --run-id r1 --force"))


@pytest.mark.parametrize("opts", _PYOPTS)
def test_a3_holds_with_interpreter_options(opts):
    _denied(_run(f"python3 {opts} {_ALLOC_PATH} gc --scope all"))


@pytest.mark.parametrize("opts", _PYOPTS)
def test_a4_holds_with_interpreter_options(tmp_path, opts):
    lines = [_forwarded_brief()]
    reason = _denied(_run_a4(tmp_path, lines, tool="Bash", tool_input={
        "command": f"python3 {opts} {_ALLOC_PATH} release {P_TOK} --run-id run-R"}))
    assert "forwarded to you" in reason


@pytest.mark.parametrize("opts", _PYOPTS)
def test_the_owner_with_interpreter_options_still_passes(tmp_path, opts):
    lines = [_brief("build"), *_eval_acquire()]
    _passed(_run_a4(tmp_path, lines, tool="Bash", tool_input={
        "command": f"python3 {opts} {_ALLOC_PATH} release {C_TOK} --run-id run-R"}))


@pytest.mark.parametrize("command", [
    f"python3 -c 'print(1)' {_ALLOC_PATH} release tok",
    "python3 -m json.tool allocator.py release",
])
def test_code_or_module_instead_of_the_script_is_not_an_invocation(command):
    _passed(_run(command))


# --------------------------------------------------------------------------- #
# The gate decides inside its timeout on a long dispatch
# --------------------------------------------------------------------------- #
def _declared_pretooluse_timeout() -> float:
    manifest = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    for group in manifest["hooks"]["PreToolUse"]:
        for h in group["hooks"]:
            if h["command"].endswith('/hooks/block-unowned-lease-mutation.sh"'):
                return float(h["timeout"])
    raise AssertionError("block-unowned-lease-mutation.sh is not registered under PreToolUse")


def test_a_forwarded_lease_release_is_refused_well_inside_the_timeout_on_a_long_dispatch(
        tmp_path):
    """A consumer deep into a long dispatch (thousands of calls, tens of MB of transcript) tries to
    release the lease it was handed. The refusal still comes - and in a fraction of the timeout
    hooks.json gives the gate: a gate the harness cancels lets the release through, and the
    provider's database is dropped under it."""
    import time
    filler = []
    for i in range(12000):            # ~75 MB: the size of a real long dispatch's transcript
        tid, use = _use("Bash", {"command": f"echo step {i}"})
        filler += [use, _result(tid, f"step {i} " + "x" * 6000)]
    lines = [_forwarded_brief(), *_serve_forwarded(), *filler]
    budget = _declared_pretooluse_timeout()
    t0 = time.monotonic()
    proc = _run_a4(tmp_path, lines, tool=MCP + "lease_release",
                   tool_input={"lease_token": P_TOK, "run_id": "run-R"})
    elapsed = time.monotonic() - t0
    assert "forwarded to you" in _denied(proc)
    assert not proc.stderr.strip(), proc.stderr
    assert elapsed < budget / 4, (
        f"the lease-mutation gate took {elapsed:.1f}s on a long dispatch; hooks.json gives it "
        f"{budget:.0f}s and a cancelled gate lets the release through")
