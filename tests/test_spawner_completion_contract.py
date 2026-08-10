"""Behavior gate for the SSOT Spawner Completion Contract (R1 barrier / R2 no-early-DONE /
R3 the return path).

Root cause this protects: a spawner (an agent/skill that launches another agent) could
previously (a) compose its own result or claim `status: DONE` while a launched child was still
running (no mechanical barrier tied to the background/foreground lever of its own launch call),
and (b) every dispatched agent was told to PUSH its completion report to a reply address the
runtime never provides - a launch call cannot name the agent it starts, and the roster an agent
is shown contains neither itself nor its launcher. An agent that goes looking for that address
either guesses (silent misdelivery) or stalls.

These assertions protect the CONTRACT'S BEHAVIOR: the barrier is mechanical and counted on the
always-on task list; DONE is illegal while a child runs; the report is the final message and the
only address anyone holds points DOWN at a child they launched. Each can fail for a real reason:
drop the barrier language, allow an early DONE, or reintroduce a reply-address field, and the
corresponding assertion goes red.

Where a marker IS asserted verbatim it is a deliberate load-bearing TOKEN - a rule id (`R0 move
2`), a parameter name (`run_in_background`), a cross-referenced filename, or the declaring
sentence other guards count to prove a single home - never a stylistic sentence. Rewording those
tokens IS the change the assertion is meant to catch.

Run: python -m pytest tests/test_spawner_completion_contract.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
SNIPPETS = PLUGIN / "snippets"

CONTRACT_MD = SNIPPETS / "spawner-completion-contract.md"
CONTINUATION_CONTRACT_MD = SNIPPETS / "continuation-contract.md"
WORKER_BRIEF_MD = SNIPPETS / "worker-brief.md"

# Wave-1 consumers: the snippet-level files reconciled alongside the new SSOT. Agent bodies
# and skill files are wired in a later wave - not asserted here.
WAVE1_CONSUMERS = [CONTINUATION_CONTRACT_MD, WORKER_BRIEF_MD]

_BANNED_DASHES = {
    0x2012: "figure-dash",
    0x2013: "en-dash",
    0x2014: "em-dash",
    0x2015: "horizontal-bar",
}


def _norm(path: Path) -> str:
    """Whitespace-normalized file text so phrase checks survive line wrapping."""
    return " ".join(path.read_text(encoding="utf-8").split())


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Existence
# ---------------------------------------------------------------------------


def test_contract_file_exists():
    """The spawner completion contract must exist as its own SSOT snippet."""
    assert CONTRACT_MD.is_file(), (
        "snippets/spawner-completion-contract.md must exist as the SSOT for the "
        "spawner completion barrier / no-early-DONE / report-up-one-level discipline"
    )


# ---------------------------------------------------------------------------
# 2. R1 - completion barrier is mechanical, not a passive "wait"
# ---------------------------------------------------------------------------


def test_r1_barrier_is_mechanical_and_topology_aware():
    """R1 must tie the barrier to the real Agent-tool lever (run_in_background) and cover both
    dependent (sequential-blocking) and independent (parallel-batch) topologies, counted on the
    always-on task list - never a passive hope."""
    text = _norm(CONTRACT_MD)
    low = text.lower()
    assert "r1" in low, "must have an R1 section"
    assert "run_in_background" in text, (
        "R1 must anchor the barrier to the real run_in_background lever"
    )
    assert "dependent" in low and "independent" in low, (
        "R1 must cover both dependent (sequential) and independent (parallel batch) child "
        "topologies"
    )
    assert "execution-tasklist-contract.md" in text, (
        "R1 must anchor the launched-vs-returned counter to the always-on execution task list"
    )
    assert "never a passive" in low or "never rely on turn memory" in low, (
        "R1 must forbid a passive/memory-based wait in favor of the mechanical barrier"
    )


# ---------------------------------------------------------------------------
# 3. R2 - no early DONE
# ---------------------------------------------------------------------------


def test_r2_forbids_done_while_a_child_is_running():
    """R2 must make status DONE conditional on every launched child having returned
    DONE/BLOCKED, and must explicitly distinguish itself from continuation-contract.md's
    no-self-dispatch rule so the two are never conflated."""
    text = _norm(CONTRACT_MD)
    low = text.lower()
    assert "r2" in low, "must have an R2 section"
    assert "done" in low and "blocked" in low, "R2 must name the DONE/BLOCKED child outcomes"
    assert "not done" in low or "never done" in low or "not be done" in low or (
        "you are not done" in low
    ), "R2 must state the spawner is NOT done while a launched child still runs"
    assert "distinct" in low, (
        "R2 must explicitly distinguish itself from continuation-contract.md's "
        "no-self-dispatch rule"
    )


# ---------------------------------------------------------------------------
# 4. R3 - report up exactly one level
# ---------------------------------------------------------------------------


def test_r3_makes_the_final_message_the_only_return_path():
    """R3 must state, in the SSOT itself, that the completion report IS the final message, that
    it is never sent to anyone, and that a brief carrying a reply address is malformed. Weaken or
    delete any of those and an agent is back to hunting for an address that cannot exist."""
    text = _norm(CONTRACT_MD)
    low = text.lower()
    assert "r3" in low, "must have an R3 section"
    for marker in (
        "your completion report is the final text of your turn",
        "never send your report",
        "final message",
        "is malformed",
        "at any depth",
        "the one decidable action",
        "does not know its own",
    ):
        assert marker in low, f"R3 must state {marker!r}"
    assert "r0 move 2" in low, (
        "R3 must cross-reference R0 move 2 - the blocking launch's own return value IS the "
        "delivery mechanism, so the two rules must be visibly the same rule"
    )


def test_r3_names_the_only_address_any_agent_holds():
    """The single legal send target - a child you launched yourself, addressed by the id that
    child's own launch call returned - must be stated positively, alongside the enumeration of
    what does NOT resolve. Stating only the prohibition leaves a spawner with no legal move."""
    low = _norm(CONTRACT_MD).lower()
    assert "the only message you may ever send is down" in low, (
        "R3 must state the channel direction positively (DOWN, to a child you launched)"
    )
    assert "id that child's own launch call returned" in low, (
        "R3 must name the ONE address source: the id the child's own launch call returned"
    )
    for non_target in ("a name you invented", "a sibling"):
        assert non_target in low, (
            f"R3 must name {non_target!r} among the targets that do not resolve"
        )


def test_r3_confines_the_literal_main_to_the_background_exception():
    """`main` is a legal target ONLY from an agent `main` itself launched in the background, and
    only mid-run - never for a completion report. Without the second half, a background child
    re-invents the report push."""
    low = _norm(CONTRACT_MD).lower()
    idx = low.find("sole legal use of the literal `main`")
    assert idx != -1, "R3 must carve out the single legal use of the literal `main`"
    window = low[idx:idx + 400]
    assert "background" in window and "launched" in window, (
        "the `main` carve-out must require that `main` itself launched the agent, in the background"
    )
    assert "never sends its completion report" in window, (
        "the `main` carve-out must exclude the completion report - that is delivered for it"
    )


# ---------------------------------------------------------------------------
# 5. Applies to Tier-C cold-spawn too (always-on, not CHP-gated)
# ---------------------------------------------------------------------------


def test_contract_is_always_on_not_chp_gated():
    """The barrier / no-early-DONE / return-path discipline must hold identically at every
    dispatch tier - a Tier-C cold spawn is not a weaker contract than a Tier-A resume."""
    text = _norm(CONTRACT_MD)
    low = text.lower()
    assert "tier-c" in low, "must state the contract holds in Tier-C cold-spawn"
    assert "always-on" in low or "always on" in low, (
        "must state the discipline is always-on, not gated on an experimental probe"
    )


# ---------------------------------------------------------------------------
# 6. ASCII hyphen only (ETHOS output rule)
# ---------------------------------------------------------------------------


def test_contract_ascii_hyphen_only():
    """The new snippet must contain no typographic dash characters."""
    body = _read(CONTRACT_MD)
    offenders = [
        f"  spawner-completion-contract.md: contains {label} (U+{cp:04X})"
        for cp, label in _BANNED_DASHES.items()
        if chr(cp) in body
    ]
    assert not offenders, "typographic dashes found:\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# 7. Non-orphan - referenced by the Wave-1 snippet-level consumers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("consumer", WAVE1_CONSUMERS, ids=lambda p: p.name)
def test_contract_is_referenced_by_wave1_consumers(consumer):
    """Each Wave-1 consumer snippet must cross-reference the new SSOT by filename - a snippet
    nobody references is dead weight."""
    text = _read(consumer)
    assert "spawner-completion-contract.md" in text, (
        f"{consumer.name}: must reference spawner-completion-contract.md"
    )


# ---------------------------------------------------------------------------
# 12. continuation-contract.md - distinct barrier bullet, not merged with no-self-dispatch
# ---------------------------------------------------------------------------


def test_continuation_contract_has_a_distinct_barrier_bullet():
    """continuation-contract.md must carry a barrier bullet that is explicitly separated from
    the pre-existing 'never self-dispatch the next step' rule - two different guarantees, both
    must hold, neither replaces the other."""
    norm = _norm(CONTINUATION_CONTRACT_MD)
    low = norm.lower()
    assert "never dispatch the next step yourself" in low, (
        "the pre-existing no-self-dispatch rule must remain"
    )
    assert "spawner completion barrier" in low, (
        "must add a distinctly-labeled spawner completion barrier bullet"
    )
    assert "distinct from the no-self-dispatch rule above" in low, (
        "the new bullet must explicitly call out that it is distinct from the "
        "no-self-dispatch rule, not a restatement of it"
    )
    assert "spawner-completion-contract.md" in norm, (
        "the new bullet must cross-reference the R1/R2 SSOT"
    )


# ---------------------------------------------------------------------------
# 13. R3 malformed-input fallback - decidable at ANY depth, no undecidable clause
# ---------------------------------------------------------------------------


def test_r3_malformed_input_fallback_is_decidable_at_any_depth():
    """A brief that names a recipient is malformed, and R3 must answer it with ONE
    unconditional, decidable action. The two-step 'treat the context that dispatched you as the
    recipient ... if determinable' framing is undecidable at every depth - no agent can derive an
    address from 'the context' alone - so R3 must state the rule holds at ANY depth explicitly,
    leaving a depth-3 worker nothing to improvise."""
    text = _read(CONTRACT_MD)
    assert "treat the context that dispatched you" not in text, (
        "R3 must no longer instruct a worker to 'treat the context that dispatched you' as the "
        "recipient - that framing is never actually actionable (a worker cannot derive a send "
        "address from context alone) and reads as a genuine two-step decision when it is not"
    )
    norm = _norm(CONTRACT_MD)
    low = norm.lower()
    assert "at any depth" in low, (
        "R3's malformed-input fallback must explicitly state it holds at ANY depth - the "
        "decidability gap the charter named was specific to depth 3+ (a nested coordinator's own "
        "worker), so the fix must name that it is depth-independent, not just depth-1-safe"
    )
    assert "the one decidable action" in low or "one decidable action" in low, (
        "the fallback must state there is exactly ONE decidable action, not a two-branch "
        "determinable-or-not judgment call"
    )
    assert "does not know its own" in low or "does not know its own `agentid`" in low, (
        "the fallback must ground WHY inference is impossible: a worker does not know its own "
        "id and cannot derive its launcher's address from the brief alone"
    )


# ---------------------------------------------------------------------------
# 15. Whole-tree restatement guards (never write these against an allowlist)
# ---------------------------------------------------------------------------

# The old, undecidable R3 malformed-brief phrasing. Any file OTHER than the SSOT itself that
# contains either marker has restated R3 instead of pointing at it - exactly the failure mode
# worker-brief.md:79 exhibited (it cited "spawner-completion-contract.md R3" while restating R3's
# PRE-FIX content inline, so the citation and the restated text silently disagreed once R3 was
# corrected here without a companion edit there).
_R3_RESTATEMENT_MARKERS = (
    "if determinable",
    "treat the context that dispatched you",
)

# The old two-state barrier-release gate ("is `completed`/`blocked`" or "is `completed` or
# `blocked`"). Deliberately narrow to the "is <label>" release-condition SHAPE, not a bare
# co-occurrence of the words "completed" and "blocked" - a task-list tool's own lifecycle labels
# are legitimately named elsewhere for a different, correctly-scoped purpose (a coarse status
# mirror, not a barrier release condition) and must NOT false-positive here.
_RELEASE_VOCAB_RESTATEMENT_RE = re.compile(
    r"is `completed`\s*/\s*`blocked`|is `completed`\s+or\s+`blocked`"
)


def test_no_tree_wide_restatement_of_r3_malformed_input_fallback():
    """Whole-tree guard (no allowlist): no file anywhere under plugins/ may restate R3's
    malformed-brief fallback instead of pointing at it. A restatement drifts silently the next
    time R3's own wording changes - which is exactly what happened to worker-brief.md:79 this
    round. Any file needing this rule cites spawner-completion-contract.md R3 by path; it never
    reproduces the fallback's own decision language inline."""
    plugins_root = REPO_ROOT / "plugins"
    offenders = []
    for path in plugins_root.rglob("*.md"):
        if path == CONTRACT_MD:
            continue  # the SSOT is what every other file must point at, not restate
        low = path.read_text(encoding="utf-8").lower()
        for marker in _R3_RESTATEMENT_MARKERS:
            if marker in low:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: contains {marker!r}")
    assert not offenders, (
        "R3's malformed-brief fallback is restated outside its SSOT - replace with a pointer "
        "to spawner-completion-contract.md R3 instead:\n" + "\n".join(offenders)
    )


def test_no_tree_wide_restatement_of_the_two_state_barrier_release_gate():
    """Whole-tree guard (no allowlist): no file anywhere under plugins/ may gate a spawner's
    completion barrier on the bare tool-native `completed`/`blocked` label pair - the release
    vocabulary is owned once by R1 (the four Continuation Contract terminal statuses) and every
    consumer must reference it, never restate a narrower two-state version that silently
    excludes NEEDS_NEXT/NEEDS_CONTEXT (the exact C2 defect shape)."""
    plugins_root = REPO_ROOT / "plugins"
    offenders = []
    for path in plugins_root.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if _RELEASE_VOCAB_RESTATEMENT_RE.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "Found a barrier release condition gated on the bare `completed`/`blocked` label pair "
        "instead of the four-status Continuation Contract vocabulary (spawner-completion-contract.md "
        "R1):\n" + "\n".join(offenders)
    )


def test_worker_brief_states_a_leaf_holds_no_send_target():
    """worker-brief.md must tell a leaf, positively, that it holds NO legal send target (it
    launches nothing) and that a messaging tool in its toolset is not an instruction - then defer
    to R3. Reintroducing a reply address here is what made the leaf hunt for one."""
    text = _read(WORKER_BRIEF_MD)
    for banned in ("REPLY_TO", "CALLER_ID", "TASK_ID", "NOTIFY"):
        assert banned not in text, (
            f"worker-brief.md must not name {banned} - no brief carries a reply address"
        )
    norm = _norm(WORKER_BRIEF_MD)
    low = norm.lower()
    assert "your completion report is the final text of your turn" in low, (
        "worker-brief.md must state the report IS the final text of the turn"
    )
    assert "you hold no legal send target" in low, (
        "worker-brief.md must state POSITIVELY that a leaf holds no legal send target - a bare "
        "omission lets the next author re-add a reply field"
    )
    assert "never treat a messaging tool's presence in your toolset as an instruction" in low, (
        "worker-brief.md must kill the tool-presence-implies-mode inference explicitly"
    )
    assert "spawner-completion-contract.md" in norm, (
        "must defer to the spawner-completion-contract.md R3 SSOT"
    )


# ---------------------------------------------------------------------------
# 16. run_in_background is named only as the Agent tool's OWN blocking-launch lever (corrected)
# ---------------------------------------------------------------------------

# A prior version of this test asserted the FALSE premise that `run_in_background` may only appear
# inside framings that warn it away from an agent launch (treating it as an unrelated Bash
# subprocess flag). The corrected R0 (spawner-completion-contract.md) establishes the opposite:
# the Agent tool ITSELF exposes `run_in_background`, and `run_in_background: false` IS the
# sanctioned blocking-launch mechanism (R0 move 2) - a subagent well inside the nesting cap uses it
# to launch a child and block on the result. This test now asserts the ROLE every occurrence must
# play - the Agent tool's own capability-probe / blocking-launch lever - never a bare mention and
# never paired with a poll/sleep loop (which would misuse it as something to wait ON rather than
# the parameter that makes the launch itself synchronous).
_RUN_IN_BACKGROUND_ROLE_MARKERS = (
    # R0 move 2's capability probe: the Agent tool HAS the parameter -> a blocking launch exists.
    "a blocking launch is available",
    # R0 move 3's capability probe: the Agent tool has NO parameter -> every launch is async.
    "every launch is asynchronous",
    # R1's synchronous-launch framing.
    "launches it synchronously",
    # R1's dependent-topology framing: the launch itself blocks.
    "so the launch itself blocks",
)


def test_run_in_background_named_only_as_the_agent_tools_own_blocking_launch_lever():
    """Every occurrence of `run_in_background` in the contract must sit inside a window that
    frames it as the Agent tool's OWN parameter controlling whether a launch blocks - present means
    a blocking launch is available (R0 move 2, `run_in_background: false`), absent means every
    launch is asynchronous (R0 move 3) - never as an unrelated Bash flag, and never paired with an
    instruction to poll or sleep against it (which would misuse it as a thing you wait ON rather
    than the parameter that makes the launch call itself return synchronously).

    What this proves: the text names the token only in its correct role everywhere it appears.
    What it does NOT prove: that any agent actually reads or obeys it, or that the repo-wide
    [wait-mechanism] lint (generator/check_orchestration.py, warn-only) is clean elsewhere - this
    test is scoped to this one SSOT file only."""
    text = _norm(CONTRACT_MD)
    low = text.lower()
    occurrences = [m.start() for m in re.finditer(r"run_in_background", low)]
    assert occurrences, (
        "sanity: run_in_background must appear in R0/R1 as the Agent tool's blocking-launch lever "
        "- R0 move 2 REQUIRES it as the mechanism a spawner blocks a child launch with"
    )
    # A wide window (e.g. 150 chars) can accidentally "borrow" a role marker that legitimately
    # belongs to a DIFFERENT, nearby occurrence (e.g. R0 move 3's marker sitting just past a
    # gutted move-2 paragraph) - a bare, unexplained mention would then falsely read as
    # role-attributed. The real SSOT text's max token-to-marker span is ~63 chars (the marker
    # phrase itself must fit fully inside the window); 70 gives a little headroom for prose
    # rewording while staying well short of the ~100-char borrowed-marker leak a proven mutation
    # exposed at radius 150.
    for pos in occurrences:
        window = low[max(0, pos - 70):pos + 70]
        assert any(marker in window for marker in _RUN_IN_BACKGROUND_ROLE_MARKERS), (
            "an occurrence of 'run_in_background' does not sit inside a window framing it as the "
            f"Agent tool's own blocking-launch lever: ...{window}..."
        )
        assert "poll" not in window and "sleep" not in window, (
            "run_in_background must never be framed as something you poll or sleep against - it "
            f"is the Agent tool's own synchronous-launch parameter: ...{window}..."
        )
