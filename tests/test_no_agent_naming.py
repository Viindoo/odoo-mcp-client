"""Whole-tree guard: nothing assumes an agent can be NAMED at launch, or can derive a name for
itself.

Behavior protected: a launch call has no name parameter, so "spawn each worker ONCE with a stable
name" and "self-generate `coder-<module-slug>`" both describe a primitive that does not exist. A
resume founded on such a name resolves nothing; a per-module cap founded on one is unenforceable.
The only address any agent ever holds is the id its OWN launch call returned for a child it
launched, so every resume identity in this repo must be that id.

Scans the WHOLE tree of agent-facing prose (plugins/ + repo-root docs/) with normalized whitespace
and no filename allowlist. Absence assertions are paired with presence assertions on the
replacement, so deleting the mechanism outright cannot pass.

Run: python -m pytest tests/test_no_agent_naming.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS = REPO_ROOT / "plugins"
ODOO_PLUGIN = PLUGINS / "odoo-ai-agents"
# docs/authoring-skills-and-agents.md is the file every NEW agent is authored from.
ROOT_DOCS = REPO_ROOT / "docs"

CODING_SKILL = ODOO_PLUGIN / "skills" / "odoo-coding" / "SKILL.md"
FP_SKILL = ODOO_PLUGIN / "skills" / "odoo-forward-port" / "SKILL.md"
FP_PHASE_DETAIL = (
    ODOO_PLUGIN / "skills" / "odoo-forward-port" / "references" / "fp-phase-detail.md"
)
CHP = ODOO_PLUGIN / "snippets" / "context-handoff-protocol.md"

SCAN_ROOTS = (PLUGINS, ROOT_DOCS)
_SCANNED_SUFFIXES = (".md", ".yaml", ".yml", ".json", ".py", ".sh")


def _scan_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        for suffix in _SCANNED_SUFFIXES:
            files.extend(root.rglob(f"*{suffix}"))
    return sorted(p for p in files if ".venv" not in p.parts)


SCANNED = _scan_files()
NORMALIZED: dict[Path, str] = {
    p: " ".join(p.read_text(encoding="utf-8", errors="replace").split()) for p in SCANNED
}


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def test_scan_corpus_discovered():
    assert len(SCANNED) >= 200, (
        f"expected >=200 scanned files under plugins/, found {len(SCANNED)}"
    )


# ---------------------------------------------------------------------------
# 1. No file assumes a name can be assigned at launch or derived by the agent.
# ---------------------------------------------------------------------------

# An AGENT noun, so "name the module" / "look the tool up by name" cannot false-positive.
_AGENT_NOUN = (
    r"(?:agent|subagent|worker|teammate|coordinator|child|children|leaf|leaves|spawn|"
    r"coder|reviewer|architect|scout|surveyor|operator|writer|planner)s?"
)
# SHAPES for "this agent has a name I chose", not a phrase list: minting one, assigning one,
# launching under one, or resuming by one. Any of them founds work on a primitive the launch call
# does not expose.
_NAMING_ASSUMPTION_RE = re.compile(
    r"(stable (?:spawn )?name\b|spawn(?:ed)? (?:it |them |each \w+ )?(?:with|under) a name\b|"
    r"self-generate|named once|under that name\b|under this name\b|under the name\b|"
    r"by the names you launched|a NAME, never an agentId|named teammate|spawn name\b|"
    # launch/spawn/dispatch <the agent> as/under <a literal or template name>
    rf"(?:launch|spawn|dispatch)\w*\s+(?:it|them|each|the|your|every)\s*(?:{_AGENT_NOUN}\s+)?"
    r"(?:as|under)\s+[`\"'<]|"
    # give / assign / mint / choose a name-or-identifier FOR AN AGENT (never for a field or label)
    rf"(?:give|assign|mint|choose|pick|invent|derive|set)\s+(?:it|them|each|the|your|every|a|an)?"
    rf"\s*(?:{_AGENT_NOUN}|it|them)\s+(?:a|the|its|their)\s+(?:own\s+|stable\s+|fixed\s+)?"
    r"(?:name|identifier|label|handle)\b|"
    # name the agent (imperative), as opposed to naming a module/tool/file
    rf"\bname\s+(?:it|them|each|the|your|every)\s+{_AGENT_NOUN}\b|"
    # resume/address/target it BY a name rather than by the id a launch returned
    rf"(?:launch|spawn|dispatch|resume|address|target|reach)\w*\s+[^.]{{0,60}}?\bby\s+"
    r"(?:that |its |the |a )?name\b)",
    re.I,
)
# Stating that the primitive does NOT exist is the rule, not an instance of it.
_IMPOSSIBILITY_RE = re.compile(
    r"(never|cannot|can not|must not|do not|does not|is not|no launch|impossible|"
    r"unimplementable|retired)",
    re.I,
)


def _naming_offenders(text: str) -> list[str]:
    return [
        m.group(0)
        for m in _NAMING_ASSUMPTION_RE.finditer(text)
        if not _IMPOSSIBILITY_RE.search(text[max(0, m.start() - 80): m.start()])
    ]


# Every phrasing below previously slipped. Asserted as executable probes so the shape cannot
# quietly shrink back to a phrase list.
_MUST_CATCH = (
    "Spawn each worker ONCE with a stable name.",
    "Launch it as `fp-adapt-<slug>-<module>` so you can resume it.",
    "Give the agent the identifier `coder-<module-slug>`.",
    "Self-generate `coder-<module-slug>` and reuse it.",
    "Name each coordinator at launch so it can be resumed.",
    "Assign the worker a stable identifier and resume it later.",
    "Resume the worker by the name you gave it.",
    "Launch the three teammate agents by name.",
)
_MUST_NOT_CATCH = (
    # Selecting WHICH agent type to launch is not naming the instance it starts.
    "Launch the agent by TYPE; if a short type fails to resolve, retry with the "
    "plugin-qualified form.",
    # Non-agent lookups by name are ordinary.
    "Inspect a TestClass or TestHelper by name.",
    "Exclude the sibling directories by name.",
    # The replacement mechanism itself.
    "Resume the child by the id that child's own launch call returned to you.",
)


def test_no_file_assumes_an_agent_can_be_named_at_launch():
    offenders = [
        f"{_rel(path)}: {hit!r}"
        for path, text in NORMALIZED.items()
        for hit in _naming_offenders(text)
    ]
    assert not offenders, (
        "a naming assumption survives. A launch call cannot assign a name and an agent cannot "
        "derive one for itself, so anything founded on a name is unimplementable - use the id "
        "the launch call returned:\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize("phrasing", _MUST_CATCH)
def test_naming_guard_catches_every_known_phrasing(phrasing):
    assert _naming_offenders(" ".join(phrasing.split())), (
        f"the naming guard does not catch {phrasing!r} - it is a phrase list again, not a shape"
    )


@pytest.mark.parametrize("phrasing", _MUST_NOT_CATCH)
def test_naming_guard_allows_type_selection_and_id_resume(phrasing):
    assert not _naming_offenders(" ".join(phrasing.split())), (
        f"the naming guard flags {phrasing!r}. Choosing an agent TYPE, looking a non-agent thing "
        "up by name, and resuming by a captured id are all legal - only minting an instance name "
        "is the defect"
    )


def test_chp_states_the_replacement_positively():
    """Paired presence assertion: the absence guard above must not be satisfiable by deleting
    the resume mechanism entirely."""
    low = NORMALIZED[CHP].lower()
    assert re.search(r"cannot name a child at launch", low), (
        "context-handoff-protocol.md must state the impossibility explicitly, or the next "
        "author re-derives naming from first principles"
    )
    assert re.search(r"the id that child's own launch call returned", low), (
        "context-handoff-protocol.md Tier A must name the ONE address source positively"
    )


# ---------------------------------------------------------------------------
# 2. The cross-invocation resume field is an id, defined by its provenance.
# ---------------------------------------------------------------------------


def test_worker_name_field_is_gone_and_the_id_field_replaces_it():
    offenders = [
        _rel(path) for path, text in NORMALIZED.items() if "WORKER NAME" in text
    ]
    assert not offenders, (
        f"the retired name-shaped resume field survives in: {offenders}"
    )
    for path in (CODING_SKILL, FP_SKILL, FP_PHASE_DETAIL):
        assert "WORKER_AGENT_ID" in NORMALIZED[path], (
            f"{_rel(path)}: the cross-invocation resume field must be WORKER_AGENT_ID"
        )
    receiving = NORMALIZED[CODING_SKILL]
    assert "captured from ITS OWN earlier launch" in receiving, (
        "odoo-coding/SKILL.md must define WORKER_AGENT_ID by PROVENANCE (an id the caller "
        "captured from its own launch), not merely by name - provenance is what makes it "
        "unforgeable"
    )
    assert "never a string anyone invented" in receiving, (
        "odoo-coding/SKILL.md must forbid an invented value for WORKER_AGENT_ID"
    )


def test_per_module_agent_cap_rests_on_the_id_registry():
    """R2b (at most one agent per module across a forward-port run) must be founded on ids the
    skill captured, recorded per module - the only thing that can actually enforce it."""
    text = NORMALIZED[FP_SKILL]
    assert "Per-module agent-id registry" in text, (
        "odoo-forward-port/SKILL.md must declare the id registry R2b rests on"
    )
    assert "one id per module for the WHOLE run" in text, (
        "the registry must be stated as one id per module for the whole run - that IS R2b"
    )


# ---------------------------------------------------------------------------
# 3. No environment flag gates any dispatch tier.
# ---------------------------------------------------------------------------


def test_no_env_flag_gate_survives():
    offenders = [
        _rel(path)
        for path, text in NORMALIZED.items()
        if "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS" in text
    ]
    assert not offenders, (
        "a dispatch tier is still gated on an experimental environment flag. The plugin's own "
        f"setup docs say the flag is not needed, so the gate can only ever be wrong: {offenders}"
    )
