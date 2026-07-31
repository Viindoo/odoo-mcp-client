"""Behavior gate for the SSOT Spawner Completion Contract (R1 barrier / R2 no-early-DONE /
R3 report-up-one-level) and the reconciliation of every `main`-hardcode it replaces.

Root cause this protects: a spawner (an agent/skill that launches another agent) could
previously (a) compose its own result or claim `status: DONE` while a launched child was still
running (no mechanical barrier tied to the Agent-tool background/foreground lever), and (b) a
worker's completion report was hardcoded to `to: "main"` in `agent-team-protocol.md` (Ask 1's
literal template, Ask 2's brief-injection template, the "authoritative delivery channel" claim,
and the Addressing header) even when a NESTED spawner - not the main context - was its actual
launcher. A report sent to `main` when the real launcher is a nested coordinator (e.g.
`odoo-coder`) is delivered to the wrong context and strands the coordinator that is blocking on
it (R1) - a silent misdelivery, not a loud error.

These assertions protect the CONTRACT'S BEHAVIOR (the barrier is mechanical and counted on the
always-on task list; DONE is illegal while a child runs; every report addresses the launcher-
supplied `REPLY_TO`, `main` only when main is that launcher) - not a wording snapshot. Each can
fail for a real reason: drop the barrier language, allow an early DONE, or reintroduce an
unconditional `main` default, and the corresponding assertion goes red.

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
AGENT_TEAM_PROTOCOL_MD = SNIPPETS / "agent-team-protocol.md"
CONTINUATION_CONTRACT_MD = SNIPPETS / "continuation-contract.md"
WORKER_BRIEF_MD = SNIPPETS / "worker-brief.md"

# Wave-1 consumers: the snippet-level files reconciled alongside the new SSOT. Agent bodies
# and skill files are wired in a later wave - not asserted here.
WAVE1_CONSUMERS = [AGENT_TEAM_PROTOCOL_MD, CONTINUATION_CONTRACT_MD, WORKER_BRIEF_MD]

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


_EXACTLY_ONE_LEVEL_RE = re.compile(r"(?i)exactly\s+one\s+level")
# A bare `"one level" in low` is satisfied by policy-INVERTING text such as "the report may skip
# more than one level" - "one level" is a literal substring of "more than one level" too. Reject
# that inversion explicitly rather than trust the bare substring alone.
_MORE_THAN_ONE_LEVEL_INVERSION_RE = re.compile(r"(?i)more\s+than\s+one\s+level")


def test_r3_pins_reply_to_as_the_launcher_never_a_guess():
    """R3 must pin REPLY_TO as the launcher-supplied address, gate the literal `main` on main
    being the actual launcher, and forbid skipping a level (reporting past a nested spawner)."""
    text = _norm(CONTRACT_MD)
    low = text.lower()
    assert "r3" in low, "must have an R3 section"
    assert "reply_to" in low, "R3 must name the REPLY_TO field"
    assert _EXACTLY_ONE_LEVEL_RE.search(low), "R3 must state the report goes up EXACTLY one level"
    assert not _MORE_THAN_ONE_LEVEL_INVERSION_RE.search(low), (
        "R3 text asserts the report may skip MORE THAN ONE level, which INVERTS the "
        "exactly-one-level rule"
    )
    assert "main` only when" in low, (
        "R3 must gate the literal `main` on main being the actual launcher, never a default"
    )
    assert "never guesses" in low or "never guess" in low, (
        "R3 must forbid a worker guessing its own address or a grand-parent's"
    )
    assert "strands it" in low or "strand" in low, (
        "R3 must name the failure mode of skipping a level: stranding the blocking coordinator"
    )


# ---------------------------------------------------------------------------
# 5. Applies to Tier-C cold-spawn too (always-on, not CHP-gated)
# ---------------------------------------------------------------------------


def test_contract_is_always_on_not_chp_gated():
    """The barrier/no-early-DONE/report-up-one-level discipline must hold identically whether
    or not the CHP capability probe is positive - unlike the SendMessage transport it rides on
    when Agent Team mode is on."""
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
# 8. agent-team-protocol.md Ask 1 - no unconditional `to: "main"`
# ---------------------------------------------------------------------------


def test_ask1_no_longer_hardcodes_main_as_the_send_target():
    """Ask 1's completion-report template must address REPLY_TO (the launcher), never an
    unconditional literal `main`."""
    text = _read(AGENT_TEAM_PROTOCOL_MD)
    assert 'to: "main"' not in text, (
        "Ask 1 must not hardcode SendMessage({to: \"main\", ...}) unconditionally"
    )
    norm = _norm(AGENT_TEAM_PROTOCOL_MD)
    assert "reply_to" in norm.lower(), "Ask 1 must address <REPLY_TO>, not a literal main"


# ---------------------------------------------------------------------------
# 9. agent-team-protocol.md Ask 2 - lead injects its OWN address, never a literal main
# ---------------------------------------------------------------------------


def test_ask2_injects_leads_own_address_not_a_literal_main():
    """Ask 2's brief-injection template must have the lead inject its OWN address as
    REPLY_TO, gated on main being the actual lead - never an unconditional `REPLY_TO: main`."""
    text = _read(AGENT_TEAM_PROTOCOL_MD)
    assert "REPLY_TO: main`," not in text, (
        "Ask 2 must not inject an unconditional literal `REPLY_TO: main` into every brief"
    )
    norm = _norm(AGENT_TEAM_PROTOCOL_MD)
    low = norm.lower()
    assert "this lead's own address" in low, (
        "Ask 2 must state the lead injects its OWN address as REPLY_TO"
    )
    assert "never a hardcoded literal" in low, (
        "Ask 2 must forbid a hardcoded literal main when a nested spawner is the lead"
    )


# ---------------------------------------------------------------------------
# 10. agent-team-protocol.md - REPLY_TO, not main, is the authoritative channel
# ---------------------------------------------------------------------------


def test_authoritative_delivery_channel_is_reply_to_not_unconditionally_main():
    """The 'authoritative delivery channel' claim must attribute authority to REPLY_TO (the
    launcher), qualifying `main` as one case of it - never state `main` is authoritative
    unconditionally."""
    text = _read(AGENT_TEAM_PROTOCOL_MD)
    assert "So `main` is the authoritative delivery channel" not in text, (
        "must not claim `main` is unconditionally the authoritative delivery channel"
    )
    norm = _norm(AGENT_TEAM_PROTOCOL_MD)
    assert (
        "reply_to` (the launcher named in the brief) is the authoritative delivery channel"
        in norm.lower()
    ), "must attribute authoritative delivery to REPLY_TO (the launcher), not a bare main default"


# ---------------------------------------------------------------------------
# 11. agent-team-protocol.md Addressing header - lead need not be main
# ---------------------------------------------------------------------------


def test_addressing_header_allows_a_nested_spawner_as_lead():
    """The Addressing section must state the lead can be a nested spawner coordinator (not only
    the main context), so a worker's REPLY_TO is not implied to always be `main`."""
    norm = _norm(AGENT_TEAM_PROTOCOL_MD)
    low = norm.lower()
    assert "address authority, not necessarily `main`" in low or (
        "the address authority" in low and "not necessarily" in low
    ), "the Addressing header must not imply the lead is always `main`"
    assert "nested spawner coordinator" in low, (
        "the Addressing section must name the nested-spawner-as-lead case explicitly"
    )
    assert "spawner-completion-contract.md" in norm, (
        "the Addressing section must cross-reference the R3 SSOT"
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
# 13. worker-brief.md - REPLY_TO always the launcher, never "often main"
# ---------------------------------------------------------------------------


def test_worker_brief_reply_to_never_defaults_to_main():
    """worker-brief.md's REPLY_TO field must be defined as ALWAYS the launcher, with `main`
    only a special case, and must explicitly forbid hardcoding `main` in the worker's own body."""
    text = _read(WORKER_BRIEF_MD)
    assert "often `main`" not in text, (
        "must not describe REPLY_TO as merely 'often main' - that is the advisory hedge "
        "this edit removes"
    )
    norm = _norm(WORKER_BRIEF_MD)
    low = norm.lower()
    assert "always the agent that launched you" in low, (
        "REPLY_TO must be defined as ALWAYS the launcher"
    )
    assert "do not hardcode `main`" in low or "do not hardcode main" in low, (
        "must explicitly forbid hardcoding `main` in the worker's own body"
    )
    assert "spawner-completion-contract.md" in norm, (
        "must defer to the spawner-completion-contract.md R3 SSOT"
    )
