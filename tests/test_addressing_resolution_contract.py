"""Guard the addressing-resolution facts established for `SendMessage` targets, plus the
self-contradiction they replace in `agent-team-protocol.md`'s nested-coordinator exception.

Root cause this protects: a message target resolves ONLY to a concrete address (the literal
`main`, a live spawn `name`, or a raw `agentId`) - never to a skill name or an agent TYPE name, both
of which are lookup keys with no runtime identity. `agent-team-protocol.md` previously asserted
`odoo-coder`'s `REPLY_TO` is the literal skill name `odoo-coding` - a claim that, taken literally,
prescribes an unroutable send, because a skill has no address of its own (it executes inline in
whatever context invoked it). These tests protect the BEHAVIOR each fact encodes - not a wording
snapshot - so a rewording that preserves the rule still passes; deleting or inverting the rule fails.

Run: python -m pytest tests/test_addressing_resolution_contract.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
SNIPPETS = PLUGIN / "snippets"

AGENT_TEAM_PROTOCOL_MD = SNIPPETS / "agent-team-protocol.md"
CHP_MD = SNIPPETS / "context-handoff-protocol.md"
DISPATCH_BRIEF_MD = SNIPPETS / "dispatch-brief.md"
SPAWNER_CONTRACT_MD = SNIPPETS / "spawner-completion-contract.md"

ALL_FOUR = [AGENT_TEAM_PROTOCOL_MD, CHP_MD, DISPATCH_BRIEF_MD, SPAWNER_CONTRACT_MD]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _norm(path: Path) -> str:
    """Whitespace-normalized text so a phrase check survives markdown line-wrapping."""
    return " ".join(_read(path).split())


# ---------------------------------------------------------------------------
# Task 1 - the nested-coordinator exception no longer claims a skill name is
# a REPLY_TO address.
# ---------------------------------------------------------------------------


def test_nested_coordinator_exception_does_not_address_a_skill_by_name():
    """`odoo-coder`'s completion report must NOT be described as going to the literal skill name
    `odoo-coding` - `odoo-coding` is a skill, never a message target. It must instead resolve to
    whichever concrete context invoked that skill, cross-referencing the skill-has-no-address
    fact instead of asserting a bare literal."""
    text = _read(AGENT_TEAM_PROTOCOL_MD)
    assert '`odoo-coding` (its `REPLY_TO`), never to `main`' not in text, (
        "the nested-coordinator exception must not claim REPLY_TO is the literal skill name "
        "`odoo-coding` - a skill has no address, so this claim describes an unroutable send"
    )
    norm = _norm(AGENT_TEAM_PROTOCOL_MD)
    low = norm.lower()
    assert "whichever concrete context invoked the `odoo-coding` skill" in low, (
        "the fix must resolve odoo-coder's REPLY_TO to whichever concrete context invoked the "
        "odoo-coding skill, not to the skill name itself"
    )
    assert "a skill has no address of its own" in low, (
        "the fix must cross-reference the 'a skill has no address of its own' fact, its owning "
        "home in context-handoff-protocol.md, rather than re-deriving the reasoning inline"
    )


def test_nested_coordinator_exception_still_grounds_the_earlier_correct_rule():
    """The general REPLY_TO rule ~90 lines earlier in the same file (Ask 1: REPLY_TO is the
    launcher named in your brief, never a hardcoded literal) must still hold - this guards
    against a fix that only patches the contradiction locally without preserving the rule it
    must now agree with."""
    norm = _norm(AGENT_TEAM_PROTOCOL_MD)
    low = norm.lower()
    assert "never a hardcoded literal" in low, (
        "Ask 1's general REPLY_TO rule (never a hardcoded literal) must still be present so the "
        "nested-coordinator exception has something correct to agree with"
    )


# ---------------------------------------------------------------------------
# Fact 1 - only a concrete address resolves; a skill/agent-type name never
# does, and the send fails.
# ---------------------------------------------------------------------------


def test_sendmessage_resolves_only_a_concrete_address():
    """agent-team-protocol.md (the SendMessage transport SSOT) must state that `to:` resolves
    only a concrete address and that a skill name or agent TYPE name never resolves."""
    norm = _norm(AGENT_TEAM_PROTOCOL_MD)
    low = norm.lower()
    assert "resolves only a concrete address" in low, (
        "must state SendMessage's `to:` resolves only a concrete address"
    )
    assert "skill name" in low and "agent type" in low, (
        "must name both failure inputs: a skill name and an agent TYPE name"
    )
    assert "never registered as a target" in low or "never resolves" in low, (
        "must state a skill/agent-type name is never a valid send target"
    )
    assert "sending to one fails" in low or "the send fails" in low, (
        "must state the concrete consequence: the send fails"
    )


def test_concrete_address_fact_points_at_dispatch_brief_grammar_not_restating_it():
    """The concrete-address fact must point at dispatch-brief.md field 11 for the address
    grammar (main / spawn name / agentId) rather than re-enumerating it a second time."""
    text = _read(AGENT_TEAM_PROTOCOL_MD)
    assert "dispatch-brief.md` field 11" in text, (
        "must cross-reference dispatch-brief.md field 11 as the address-grammar SSOT"
    )


# ---------------------------------------------------------------------------
# Fact 5 - reply to the runtime-stamped sender, never a guessed/remembered
# name.
# ---------------------------------------------------------------------------


def test_reply_addresses_the_runtime_stamped_sender():
    norm = _norm(AGENT_TEAM_PROTOCOL_MD)
    low = norm.lower()
    assert "stamped on that incoming message" in low or "stamped on the incoming message" in low, (
        "must state a reply addresses the sender the runtime stamped on the incoming message"
    )
    assert "never a name you recall" in low or "not a name" in low or "guess" in low, (
        "must forbid replying to a remembered or guessed name"
    )


# ---------------------------------------------------------------------------
# Fact 2 - a skill has no address of its own; it runs inline in whatever
# context invoked it; the fork exception.
# ---------------------------------------------------------------------------


def test_chp_owns_skill_has_no_address_fact():
    """context-handoff-protocol.md must own a dedicated 'a skill has no address of its own'
    section, stating the general inline-execution rule (not just the main-invoked special case)
    and the forked-context exception."""
    text = _read(CHP_MD)
    assert re.search(r"^## A skill has no address of its own\s*$", text, re.MULTILINE), (
        "context-handoff-protocol.md must carry a heading 'A skill has no address of its own'"
    )
    norm = _norm(CHP_MD)
    low = norm.lower()
    assert "execute inline in whatever context invoked it" in low, (
        "must state a skill's instructions execute inline in whatever context invoked it "
        "(general rule, not just the main-invoked case)"
    )
    assert "never the skill's own name" in low, (
        "must state a skill's dispatches never carry the skill's own name"
    )
    assert "forked" in low or "background subagent" in low, (
        "must state the exception: a skill whose frontmatter declares a forked/background "
        "subagent context runs as a real subagent"
    )
    assert "your caller" in low, (
        "must state what 'your caller' resolves to inside the forked-context exception"
    )


def test_dispatch_brief_points_at_chp_instead_of_restating_the_main_only_case():
    """dispatch-brief.md field 11 must generalize beyond the old main-only special case and
    point at context-handoff-protocol.md's owning section rather than re-deriving the rule."""
    text = _read(DISPATCH_BRIEF_MD)
    assert "A skill invoked from main runs IN main's context" not in text, (
        "field 11 must not restate the narrower main-only special case now that the general "
        "rule lives in context-handoff-protocol.md"
    )
    assert 'context-handoff-protocol.md` "A skill has no address of its own"' in text, (
        "field 11 must point at context-handoff-protocol.md's owning section for the general rule"
    )


# ---------------------------------------------------------------------------
# Fact 3 - no agent can read its own address; impossible except `main`; the
# only route is the launcher stating the child's own spawn name in its brief.
# ---------------------------------------------------------------------------


def test_no_agent_can_read_its_own_address():
    norm = _norm(CHP_MD)
    low = norm.lower()
    assert "no agent can read its own address" in low, (
        "must state the general rule: no agent can read its own address"
    )
    assert "executable only for `main`" in low or "only for `main`" in low, (
        "must state 'pass your own address to your child' is executable only for main"
    )
    assert "exactly one way" in low, (
        "must state there is exactly one way a non-main agent can supply an address for itself"
    )
    assert "never derives or introspects it" in low, (
        "must state the child's own spawn name is repeated from the launcher's brief, never "
        "derived or introspected"
    )


# ---------------------------------------------------------------------------
# Fact 4 - the default is not to send at all; a synchronous launch's return
# value already carries the result.
# ---------------------------------------------------------------------------


def test_synchronous_launch_return_is_the_default_no_send_needed():
    text = _read(SPAWNER_CONTRACT_MD)
    assert "R0 - Dispatch physics" in text, "sanity: R0 heading must still exist"
    norm = _norm(SPAWNER_CONTRACT_MD)
    low = norm.lower()
    assert "is your own launch call's return value" in low, (
        "R0 move 2 must state the child's result IS the launch call's own return value on the "
        "blocking path"
    )
    assert "no `reply_to`, no `sendmessage`, no reply field needed" in low, (
        "R0 move 2 must state no REPLY_TO / SendMessage / reply field is needed on that path"
    )
    assert "default" in low and "preferred" in low, (
        "R0 move 2 must state the synchronous-return path is the default, preferred shape"
    )
    assert "including when you yourself are a subagent" in low, (
        "must state the default holds even when the launcher itself is a subagent, not only main"
    )


# ---------------------------------------------------------------------------
# Fact 6 - a background child outlives a non-main launcher: its completion
# is re-addressed to main, never resumed on the (finished) launcher.
# ---------------------------------------------------------------------------


def test_background_grandchild_boundary_documented():
    norm = _norm(SPAWNER_CONTRACT_MD)
    low = norm.lower()
    assert "a background child outlives a non-`main` launcher" in low, (
        "must name the boundary condition: a background child outlives a non-main launcher"
    )
    assert "re-addressed to `main`" in low, (
        "must state the child's completion is re-addressed to main"
    )
    assert "never resumed on you" in low, (
        "must state the completion is never resumed on the (finished) launcher"
    )
    assert "do not rely on a background grandchild" in low, (
        "must state the actionable consequence: do not rely on a background grandchild's result "
        "coming back to you"
    )


# ---------------------------------------------------------------------------
# Cross-cutting - ASCII hyphen only, no runtime version number, no banned
# 'Agent tool' phrase (test_terminology_launch_agent.py already scans this
# tree, but the six facts are new prose so a targeted check here fails fast).
# ---------------------------------------------------------------------------

_BANNED_DASHES = {
    0x2012: "figure-dash",
    0x2013: "en-dash",
    0x2014: "em-dash",
    0x2015: "horizontal-bar",
}

# Guard against a literal Claude Code version number leaking into shipped prose (the facts were
# established by reverse-engineering runtime version 2.1.223; that number must never appear here).
_VERSION_RE = re.compile(r"\b2\.1\.223\b")


@pytest.mark.parametrize("path", ALL_FOUR, ids=lambda p: p.name)
def test_no_typographic_dashes(path):
    body = _read(path)
    offenders = [
        f"{path.name}: contains {label} (U+{cp:04X})"
        for cp, label in _BANNED_DASHES.items()
        if chr(cp) in body
    ]
    assert not offenders, "typographic dashes found:\n" + "\n".join(offenders)


@pytest.mark.parametrize("path", ALL_FOUR, ids=lambda p: p.name)
def test_no_runtime_version_number(path):
    body = _read(path)
    assert not _VERSION_RE.search(body), (
        f"{path.name}: must not name a Claude Code runtime version number in shipped prose"
    )


@pytest.mark.parametrize("path", ALL_FOUR, ids=lambda p: p.name)
def test_no_banned_agent_tool_phrase(path):
    body = _read(path)
    assert not re.search(r"\bAgent[ -]tools?\b", body, re.IGNORECASE), (
        f"{path.name}: must not use the literal phrase 'Agent tool(s)' in agent-facing prose"
    )


# ---------------------------------------------------------------------------
# Single-owner discipline - each fact's marker text must not be duplicated
# verbatim in a second file (restating is how this plugin's addressing prose
# drifted before).
# ---------------------------------------------------------------------------


def test_skill_has_no_address_heading_appears_exactly_once():
    """The owning heading for Fact 2 must exist in exactly one file across the whole plugin tree
    - every other consumer points at it by name, never duplicates the heading itself."""
    offenders = []
    for path in (PLUGIN / "snippets").rglob("*.md"):
        text = _read(path)
        if re.search(r"^## A skill has no address of its own\s*$", text, re.MULTILINE):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [str(CHP_MD.relative_to(REPO_ROOT))], (
        f"'A skill has no address of its own' heading must exist in exactly "
        f"context-handoff-protocol.md, found in: {offenders}"
    )
