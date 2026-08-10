"""Guard the two identity facts the dispatch model rests on, and the return path they imply.

Root cause this protects: no agent can read its own address and none is shown its launcher, so the
only address any agent ever holds is the id its OWN launch call returned for a child it launched
itself. Every earlier revision of this contract assumed a reply address the runtime never provides.

Each fact is asserted as a REGEX SHAPE over whitespace-normalized text, so synonyms and reordering
that preserve the rule still pass while deleting or inverting it fails. Where a phrase is asserted
literally it is a load-bearing TOKEN (a heading, a brief key, a tool name), not a sentence.

Run: python -m pytest tests/test_addressing_resolution_contract.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
SNIPPETS = PLUGIN / "snippets"

CHP_MD = SNIPPETS / "context-handoff-protocol.md"
DISPATCH_BRIEF_MD = SNIPPETS / "dispatch-brief.md"
SPAWNER_CONTRACT_MD = SNIPPETS / "spawner-completion-contract.md"

ALL_THREE = [CHP_MD, DISPATCH_BRIEF_MD, SPAWNER_CONTRACT_MD]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _norm(path: Path) -> str:
    """Whitespace-normalized text so a phrase check survives markdown line-wrapping."""
    return " ".join(_read(path).split())


# ---------------------------------------------------------------------------
# Fact 3 - no agent can read its own address; `main` is the one fixed literal;
# every other address is captured from a launch call's own return value.
# ---------------------------------------------------------------------------


def test_no_agent_can_read_its_own_address():
    low = _norm(CHP_MD).lower()
    for shape, why in (
        (r"no agent can (?:read|see|learn|derive|introspect) its own address",
         "must state the general rule: no agent can read its own address"),
        (r"(?:executable|possible|available|works) only for `main`",
         "must state 'pass your own address to your child' is executable only for main"),
        (r"exactly one way",
         "must state there is exactly one way any other agent comes to hold an address"),
        (r"never derives?[^.]{0,40}introspects? it",
         "must state that address is captured from a launch return, never derived or introspected"),
    ):
        assert re.search(shape, low), why


# ---------------------------------------------------------------------------
# Fact 2 - a skill has no address of its own. Its launches ARE the invoking
# context's launches, so the ids they return belong to that context.
# ---------------------------------------------------------------------------


def test_chp_owns_skill_has_no_address_fact():
    """context-handoff-protocol.md owns this fact. It must state the inline-execution rule, that
    a skill holds NO address (its own or its invoker's), that the ids its launches return belong
    to the invoking context, and the forked/background-subagent case - which changes only WHERE
    the skill runs, never that it holds an upward address."""
    text = _read(CHP_MD)
    assert re.search(r"^## A skill has no address of its own\s*$", text, re.MULTILINE), (
        "context-handoff-protocol.md must carry a heading 'A skill has no address of its own'"
    )
    low = _norm(CHP_MD).lower()
    for shape, why in (
        (r"execute inline in whatever context invoked it",
         "must state a skill's instructions execute inline in whatever context invoked it"),
        (r"holds no address, its own or its invoker",
         "must state a skill holds no address of its own AND none for its invoker"),
        (r"launches are that context's launches",
         "must state the skill's launches ARE the invoking context's launches, so the ids they "
         "return are captured and held by that context"),
        (r"(?:forked|background) subagent context",
         "must cover the skill that runs as a real subagent instead"),
        (r"still holds no address for its launcher",
         "the forked/background case must NOT reintroduce an upward address"),
    ):
        assert re.search(shape, low), why


def test_no_snippet_says_a_dispatch_carries_an_address():
    """Whole-snippets-tree guard: the retired model said a skill's dispatches 'carry the address
    of the context that ran it'. No brief carries an address at all - a dispatch that carries one
    is the reply-address field under another name."""
    shape = re.compile(
        r"(?:brief|dispatch(?:es)?|prompt)[^.]{0,80}carr(?:y|ies|ying)[^.]{0,40}address"
        r"|carr(?:y|ies|ying) the address of",
        re.I,
    )
    # The prohibition must BIND the claim - same sentence, ahead of it. A "not" floating anywhere
    # in the surrounding window is how "its dispatches carry the address of ..." survived a guard.
    prohibition = re.compile(
        r"(never|\bno\b|\bnot\b|cannot|must not|is malformed|is retired|retired)", re.I
    )
    sentence_split = re.compile(r"(?<=[.;:!?])\s+")
    offenders = []
    for path in sorted(SNIPPETS.rglob("*.md")):
        norm = _norm(path)
        for m in shape.finditer(norm):
            start = 0
            for s in sentence_split.finditer(norm, 0, m.start()):
                start = s.end()
            nxt = sentence_split.search(norm, m.end())
            end = nxt.start() if nxt else len(norm)
            ahead = norm[start:m.start()]
            behind = norm[m.end():min(end, m.end() + 80)]
            if prohibition.search(ahead) or prohibition.search(behind):
                continue
            window = norm[max(0, m.start() - 140): m.end() + 140]
            offenders.append(f"{path.relative_to(REPO_ROOT)}: ...{window.strip()[:200]}...")
    assert not offenders, (
        "a dispatch is described as carrying an address. No agent holds an upward address, so a "
        "brief has nothing to put in such a field:\n" + "\n".join(offenders)
    )


def test_dispatch_brief_declares_no_reply_address_field():
    """dispatch-brief.md is the caller-side schema; it must say POSITIVELY that no reply-address
    field exists (a bare omission lets the next author re-add one) and point at the R3 SSOT for
    where the report actually goes."""
    low = _norm(DISPATCH_BRIEF_MD).lower()
    assert re.search(r"no reply-address field exists", low), (
        "dispatch-brief.md must state that no reply-address field exists"
    )
    assert re.search(r"do not add one under any name", low), (
        "dispatch-brief.md must forbid re-adding the field under a new name - renaming is how "
        "REPLY_TO/CALLER_ID would come back"
    )
    assert "spawner-completion-contract.md" in low, (
        "dispatch-brief.md must point at the R3 SSOT for the return path instead of restating it"
    )


def test_r3_enumerates_the_targets_that_do_not_resolve():
    """A skill name and an agent TYPE name are lookup keys with no runtime identity; an invented
    name and a sibling have none either. R3 must enumerate them, or the next author assumes one
    of them is addressable and writes an unroutable send."""
    low = _norm(SPAWNER_CONTRACT_MD).lower()
    for target in ("a name you invented", "a skill name", "an agent type", "a sibling"):
        assert target in low, (
            f"spawner-completion-contract.md R3 must name {target!r} among the targets that do "
            "not resolve"
        )
    assert re.search(r"does not resolve and the send fails", low), (
        "R3 must state the concrete consequence: the send fails"
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


@pytest.mark.parametrize("path", ALL_THREE, ids=lambda p: p.name)
def test_no_typographic_dashes(path):
    body = _read(path)
    offenders = [
        f"{path.name}: contains {label} (U+{cp:04X})"
        for cp, label in _BANNED_DASHES.items()
        if chr(cp) in body
    ]
    assert not offenders, "typographic dashes found:\n" + "\n".join(offenders)


@pytest.mark.parametrize("path", ALL_THREE, ids=lambda p: p.name)
def test_no_runtime_version_number(path):
    body = _read(path)
    assert not _VERSION_RE.search(body), (
        f"{path.name}: must not name a Claude Code runtime version number in shipped prose"
    )


@pytest.mark.parametrize("path", ALL_THREE, ids=lambda p: p.name)
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
