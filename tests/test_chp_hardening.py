"""Contract tests for the Context-Handoff Protocol (CHP) snippet and its wiring.

These protect the BEHAVIOR the plugin promises when orchestrator skills dispatch
worker agents across three capability tiers (SendMessage-resume / fork / fresh
spawn). Each assertion guards one wiring that, if silently dropped, would break
the CHP contract: tier documentation, fallback conditions, confidentiality framing,
async park-and-resume semantics, Phase-1 skill wiring, handoff field validity, and
Tier-C fallback reachability from every non-fresh skill.

Red-before-green: deleting the corresponding reference or token makes exactly the
matching assertion fail. stdlib only.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SNIPPETS = PLUGIN / "snippets"
SKILLS = PLUGIN / "skills"
GENERATOR = PLUGIN / "generator"
DOCS_REF = PLUGIN / "docs" / "reference"

CHP_SNIPPET = SNIPPETS / "context-handoff-protocol.md"
AGENT_TEAM_PROTOCOL = SNIPPETS / "agent-team-protocol.md"
SKILL_TOOL_DEPS = GENERATOR / "skill_tool_deps.json"
ORCHESTRATION_MAP = DOCS_REF / "ORCHESTRATION-MAP.md"

VALID_HANDOFF_VALUES = {"send-message", "fork", "fresh"}

# Phase-1 skills that must reference the CHP snippet.
PHASE1_SKILLS = [
    SKILLS / "odoo-coding" / "SKILL.md",
    SKILLS / "odoo-code-review" / "SKILL.md",
]


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Snippet existence
# ---------------------------------------------------------------------------


def test_chp_snippet_exists():
    """The context-handoff-protocol.md SSOT snippet must exist."""
    assert CHP_SNIPPET.is_file(), f"missing SSOT snippet {CHP_SNIPPET}"


def test_agent_team_protocol_exists():
    """The agent-team-protocol.md SSOT snippet must exist and carry its anchor tokens.

    This is the worker->lead half of the Agent Team contract (CHP owns lead->worker). The
    anchors guard its two load-bearing asks (the teammate completion-report push 'Ask 1' and
    the low-context task board 'Ask 2') plus the two tool surfaces they ride on (`SendMessage`
    for the report push, `TaskCreate` for the board). Dropping any one silently breaks the
    protocol, so each is asserted here (mirrors test_chp_snippet_exists for the CHP SSOT).
    """
    assert AGENT_TEAM_PROTOCOL.is_file(), f"missing SSOT snippet {AGENT_TEAM_PROTOCOL}"
    body = _read(AGENT_TEAM_PROTOCOL)
    for token in ("Ask 1", "Ask 2", "SendMessage", "TaskCreate"):
        assert token in body, (
            f"agent-team-protocol.md: missing anchor token '{token}'"
        )


# ---------------------------------------------------------------------------
# 2. Three tiers documented
# ---------------------------------------------------------------------------


def test_chp_snippet_documents_three_tiers():
    """Snippet must document Tier A, Tier B, and Tier C (hyphen or space form)."""
    body = _read(CHP_SNIPPET)
    for tier in ("A", "B", "C"):
        pattern = re.compile(rf"Tier[- ]{tier}\b", re.IGNORECASE)
        assert pattern.search(body), (
            f"context-handoff-protocol.md: missing documentation for Tier {tier}"
        )


# ---------------------------------------------------------------------------
# 3. Fallback conditions documented
# ---------------------------------------------------------------------------


def test_chp_snippet_documents_fallback_conditions():
    """Snippet must name all key fallback-condition tokens."""
    body = _read(CHP_SNIPPET)
    required_tokens = [
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
        "SendMessage",
        "not addressable",
        "resume",
    ]
    for token in required_tokens:
        assert token in body, (
            f"context-handoff-protocol.md: missing fallback-condition token '{token}'"
        )
    # non-lead token: accept either form
    assert "non-lead" in body or "not the team lead" in body, (
        "context-handoff-protocol.md: missing non-lead orchestrator fallback token "
        "('non-lead' or 'not the team lead')"
    )


# ---------------------------------------------------------------------------
# 4. No secret framing
# ---------------------------------------------------------------------------


def test_chp_snippet_no_secret_framing():
    """Every line containing 'secret' must also be part of a prohibition.

    The confidentiality guard prohibits describing a handoff payload as 'secret'.
    Any line that mentions 'secret' must also contain a prohibition keyword (never,
    not, do NOT, refuse, guard) - a bare use of the word to describe a payload is
    a runtime correctness bug.
    """
    body = _read(CHP_SNIPPET)
    prohibition_re = re.compile(r"\b(never|not|do not|do NOT|refuse|guard)\b", re.IGNORECASE)
    violations = []
    for lineno, line in enumerate(body.splitlines(), start=1):
        if "secret" in line.lower():
            if not prohibition_re.search(line):
                violations.append(f"  line {lineno}: {line.strip()}")
    assert not violations, (
        "context-handoff-protocol.md: 'secret' appears without a prohibition keyword:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# 5. Park-and-resume semantics documented
# ---------------------------------------------------------------------------


def test_chp_snippet_documents_park_and_resume():
    """Snippet must document async park-and-be-resumed semantics."""
    body = _read(CHP_SNIPPET)
    assert "park" in body or "fire-and-forget" in body, (
        "context-handoff-protocol.md: missing async semantics token "
        "('park' or 'fire-and-forget')"
    )


# ---------------------------------------------------------------------------
# 6. Phase-1 skill wiring
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skill_path", PHASE1_SKILLS, ids=lambda p: p.parent.name)
def test_chp_wired_into_phase1_skills(skill_path):
    """Phase-1 skills must reference context-handoff-protocol.md."""
    body = _read(skill_path)
    assert "context-handoff-protocol.md" in body, (
        f"{skill_path.parent.name}/SKILL.md: missing reference to context-handoff-protocol.md"
    )


# ---------------------------------------------------------------------------
# 7. Handoff field values are valid
# ---------------------------------------------------------------------------


def test_handoff_field_values_valid():
    """Every orchestration entry's 'handoff' field (if present) must be a valid value."""
    data = json.loads(_read(SKILL_TOOL_DEPS))
    orch = data.get("orchestration", {})
    invalid = []
    for skill_name, entry in orch.items():
        if skill_name.startswith("_"):
            continue
        if not isinstance(entry, dict):
            continue
        handoff = entry.get("handoff")
        if handoff is not None and handoff not in VALID_HANDOFF_VALUES:
            invalid.append(f"  {skill_name}: handoff={handoff!r} (valid: {VALID_HANDOFF_VALUES})")
    assert not invalid, (
        "skill_tool_deps.json: invalid handoff values:\n" + "\n".join(invalid)
    )


# ---------------------------------------------------------------------------
# 8. Non-fresh handoff skills document Tier-C fallback
# ---------------------------------------------------------------------------


def test_nonfresh_handoff_skills_document_tier_c():
    """Skills whose orchestration handoff is 'send-message' or 'fork' must document
    a Tier-C fallback path in their SKILL.md - either via a case-insensitive 'Tier-C'
    reference, a 'fresh spawn' mention, or a reference to context-handoff-protocol.md.
    """
    data = json.loads(_read(SKILL_TOOL_DEPS))
    orch = data.get("orchestration", {})
    missing = []
    for skill_name, entry in orch.items():
        if skill_name.startswith("_"):
            continue
        if not isinstance(entry, dict):
            continue
        handoff = entry.get("handoff")
        if handoff not in {"send-message", "fork"}:
            continue
        skill_md = SKILLS / skill_name / "SKILL.md"
        if not skill_md.is_file():
            missing.append(f"  {skill_name}: SKILL.md not found at {skill_md}")
            continue
        body = _read(skill_md)
        has_tier_c = bool(re.search(r"tier-?c\b", body, re.IGNORECASE))
        has_fresh_spawn = "fresh spawn" in body
        has_chp_ref = "context-handoff-protocol.md" in body
        if not (has_tier_c or has_fresh_spawn or has_chp_ref):
            missing.append(
                f"  {skill_name}: handoff={handoff!r} but SKILL.md lacks Tier-C fallback "
                f"(need 'Tier-C', 'fresh spawn', or 'context-handoff-protocol.md')"
            )
    assert not missing, (
        "Non-fresh handoff skills missing Tier-C fallback documentation:\n"
        + "\n".join(missing)
    )


# ---------------------------------------------------------------------------
# 9. ASCII hyphen only
# ---------------------------------------------------------------------------


def test_chp_snippet_ascii_hyphen_only():
    """Snippet must contain no typographic dash characters (ETHOS rule)."""
    banned = {
        0x2012: "figure-dash",
        0x2013: "en-dash",
        0x2014: "em-dash",
        0x2015: "horizontal-bar",
    }
    body = _read(CHP_SNIPPET)
    offenders = []
    for cp, label in banned.items():
        if chr(cp) in body:
            offenders.append(f"  context-handoff-protocol.md: contains {label} (U+{cp:04X})")
    assert not offenders, "typographic dashes found:\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# 10. Orchestration map documents handoff column
# ---------------------------------------------------------------------------


def test_orchestration_map_documents_handoff():
    """ORCHESTRATION-MAP.md must contain a 'handoff' column header.

    This map is 100% generated by gen_surface.py (make gen). The column was added
    in WI-7 when make gen was run, so this is now a plain passing assertion.
    """
    assert ORCHESTRATION_MAP.is_file(), f"missing {ORCHESTRATION_MAP}"
    body = _read(ORCHESTRATION_MAP)
    assert "handoff" in body, (
        "ORCHESTRATION-MAP.md: missing 'handoff' column header "
        "(regenerate with 'make gen' after WI-7 updates gen_surface.py)"
    )
