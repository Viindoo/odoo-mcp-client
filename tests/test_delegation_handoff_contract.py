"""Guard the round-2 delegation-handoff hardening on top of `snippets/dispatch-brief.md`,
`worker-brief.md`, `continuation-contract.md`, `spawner-completion-contract.md`, and
`agent-team-protocol.md`.

Protects four behaviors, each previously a caller-side field/rule with no callee-side
enforcement (or, for the ETHOS citations, an existing plugin-shipped principle never bound
at the dispatch site it governs):

1. The caller-side dispatch-brief skeleton names the CALLER's own identity/return address
   (`REPLY_TO`, skeleton field 11) so a caller composing a brief from that file alone still
   learns the obligation exists - not only from a worker-side or transport-side file.
2. Every `odoo-ai-agents` agent's `## Brief self-check` section confirms a prior-artifact
   pointer was supplied (`INPUTS` or a family-named equivalent such as `DESIGN_DOC`) before
   starting work - a caller-side field with a matching callee-side check, not caller-side
   advice with nothing on the receiving end.
3. `OBJECTIVE`/`CONSTRAINTS` compliance with the plugin's own auto-loaded ODOO-AI-ETHOS #4
   (Outcomes over Procedures) is bound (cited) at the one site it governs - the dispatch-brief
   field definitions and every agent's self-check - not left to float unbound while the
   plugin ships the rule.
4. `continuation-contract.md` binds ODOO-AI-ETHOS #10 (Completion Status - "a DONE claim
   must be accompanied by observable evidence") at the always-on baseline (not only inside
   Agent Team mode's `SendMessage` push), and explicitly bans an unqualified "waiting"
   statement as a terminal state - a genuinely missing rule before this change.

Mirrors the grep-the-prose idiom of `tests/test_dispatch_brief.py`: plain-text assertions,
whitespace-normalized before matching, no allowlist, whole-tree glob (never a hardcoded file
list) so the denominator grows automatically as skills/agents are added.

Run: python -m pytest tests/test_delegation_handoff_contract.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
SNIPPETS = PLUGIN / "snippets"

DISPATCH_BRIEF = SNIPPETS / "dispatch-brief.md"
WORKER_BRIEF = SNIPPETS / "worker-brief.md"
CONTINUATION_CONTRACT = SNIPPETS / "continuation-contract.md"
SPAWNER_COMPLETION_CONTRACT = SNIPPETS / "spawner-completion-contract.md"
AGENT_TEAM_PROTOCOL = SNIPPETS / "agent-team-protocol.md"

ODOO_AGENTS_DIR = PLUGIN / "agents"
ODOO_AGENT_FILES = sorted(ODOO_AGENTS_DIR.glob("*.md"))

ODOO_SKILLS_DIR = PLUGIN / "skills"
ODOO_SKILL_MD_FILES = sorted(ODOO_SKILLS_DIR.glob("*/SKILL.md"))

_BRIEF_SELF_CHECK_HEADING = re.compile(r"^##\s+Brief self-check\s*$", re.MULTILINE)

_ARTIFACT_POINTER_TOKENS = re.compile(
    r"INPUTS|DESIGN_DOC|MASTER_DESIGN_DOC|ORACLE_PATH|GAP_MATRIX|CATALOG_PATH|SCENARIOS_PATH|"
    r"diff_path|feature.catalog|grounding source",
    re.IGNORECASE,
)

_ETHOS_4 = "ODOO-AI-ETHOS #4"
_ETHOS_10 = "ODOO-AI-ETHOS #10"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _norm(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _section(text: str, start_heading: str, end_heading_re: str | None = r"\n##\s") -> str:
    """Return text from start_heading (inclusive) up to the next `## ` heading, or EOF."""
    idx = text.find(start_heading)
    if idx == -1:
        return ""
    rest = text[idx + len(start_heading):]
    if end_heading_re is not None:
        m = re.search(end_heading_re, rest)
        if m:
            return rest[: m.start()]
    return rest


def _self_check_section(agent_path: Path) -> str:
    text = _read(agent_path)
    return _section(text, "## Brief self-check")


def _agent_roles() -> dict[str, str]:
    """agents.<name>.role from the SSOT registry (data-driven - never a hardcoded name list)."""
    import json

    deps = json.loads((PLUGIN / "generator" / "skill_tool_deps.json").read_text(encoding="utf-8"))
    return {name: entry.get("role") for name, entry in deps.get("agents", {}).items()}


_AGENT_ROLES = _agent_roles()


# ---------------------------------------------------------------------------
# Discovery floors - a broken glob must fail loudly, not silently pass vacuously.
# ---------------------------------------------------------------------------


def test_odoo_agent_files_discovered():
    assert len(ODOO_AGENT_FILES) >= 26, (
        f"expected at least 26 plugins/odoo-ai-agents/agents/*.md files, "
        f"found {len(ODOO_AGENT_FILES)} - glob is wrong or agents went missing"
    )


def test_odoo_skill_files_discovered():
    assert len(ODOO_SKILL_MD_FILES) >= 40, (
        f"expected at least 40 plugins/odoo-ai-agents/skills/*/SKILL.md files, "
        f"found {len(ODOO_SKILL_MD_FILES)} - glob is wrong or skills went missing"
    )


# ---------------------------------------------------------------------------
# 1. Caller-side identity field (REPLY_TO) lives on the caller-facing SSOT
#    itself, not only on a worker-side or transport-side file.
# ---------------------------------------------------------------------------


def test_dispatch_brief_skeleton_names_caller_identity_field():
    text = _read(DISPATCH_BRIEF)
    assert "REPLY_TO" in text, (
        "dispatch-brief.md - the file branded as the CALLER-side SSOT that any spawner reads "
        "BY PATH while composing a dispatch prompt - must name REPLY_TO (or an explicit pointer "
        "to it) in its own universal skeleton table, not only in worker-brief.md/"
        "agent-team-protocol.md; a caller following the prescribed authoring workflow (read "
        "this file, fill the skeleton) must be able to learn the obligation exists from here"
    )


def test_dispatch_brief_skeleton_is_eleven_fields_with_caller_id_row():
    norm = _norm(DISPATCH_BRIEF)
    assert "Universal skeleton (11 fields)" in norm, (
        "the skeleton heading must reflect the added CALLER_ID/REPLY_TO row - still 10 means "
        "the row was not actually added to the table"
    )
    assert "CALLER_ID" in norm, "the new field must be named CALLER_ID (REPLY_TO) in the table"


# ---------------------------------------------------------------------------
# 2. ODOO-AI-ETHOS #4 (Outcomes over Procedures) is BOUND (cited) at the two
#    field definitions it governs and at every agent's self-check - never
#    restated as a new paragraph (that would be a duplicate-SSOT defect).
# ---------------------------------------------------------------------------


def test_dispatch_brief_objective_row_cites_ethos_4():
    text = _read(DISPATCH_BRIEF)
    objective_row = _section(text, "| 1 | `OBJECTIVE`", end_heading_re=r"\n\|")
    assert _ETHOS_4 in objective_row, (
        "the OBJECTIVE skeleton row must cite ODOO-AI-ETHOS #4 (Outcomes over Procedures) - "
        "the plugin already ships this principle (auto-loaded every session); it must be bound "
        "here, not left uncited while a second, unbound copy of 'let the specialist decide' "
        "would be a duplicate-SSOT defect"
    )


def test_dispatch_brief_constraints_row_cites_ethos_4():
    text = _read(DISPATCH_BRIEF)
    constraints_row = _section(text, "| 8 | `CONSTRAINTS`", end_heading_re=r"\n\|")
    assert _ETHOS_4 in constraints_row, (
        "the CONSTRAINTS skeleton row must cite ODOO-AI-ETHOS #4 (Outcomes over Procedures) - "
        "same binding requirement as OBJECTIVE above"
    )


# NOTE on two expected-red cases: `agents/odoo-intent-extractor.md` and
# `agents/odoo-diff-comparator.md` are, at the time this test was written, owned and being
# edited by a different, concurrently-running work-group on this same tree (serialization:
# one writer per file). This test file carries NO allowlist/exclusion for them - per this
# round's rule, a guard is tightened by a structural marker, never by listing known files.
# They are therefore expected to show up as individually-named red parametrize cases below
# until that other work-group lands the same self-check text; that is the intended,
# self-documenting behavior of a full, unfiltered sweep, not a bug in this test.


@pytest.mark.parametrize("agent", ODOO_AGENT_FILES, ids=lambda p: p.stem)
def test_agent_self_check_cites_ethos_4(agent):
    section = _self_check_section(agent)
    normalized = " ".join(section.split())
    assert _ETHOS_4 in normalized, (
        f"{agent.relative_to(REPO_ROOT)}: '## Brief self-check' does not cite {_ETHOS_4} - "
        "a caller-dictated implementation method in OBJECTIVE/CONSTRAINTS must be flagged as "
        "non-binding per the plugin's own Outcomes-over-Procedures principle, bound here"
    )


# ---------------------------------------------------------------------------
# 3. Every agent's self-check confirms a prior-artifact pointer (INPUTS or a
#    family-named equivalent) was supplied - closes the caller-side-field/
#    no-callee-check gap.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("agent", ODOO_AGENT_FILES, ids=lambda p: p.stem)
def test_agent_self_check_confirms_prior_artifact_pointer(agent):
    section = _self_check_section(agent)
    normalized = " ".join(section.split())
    assert _ARTIFACT_POINTER_TOKENS.search(normalized), (
        f"{agent.relative_to(REPO_ROOT)}: '## Brief self-check' never checks for a prior-"
        "artifact pointer (INPUTS/DESIGN_DOC/ORACLE_PATH/GAP_MATRIX/CATALOG_PATH/"
        "SCENARIOS_PATH/diff_path/feature catalog/grounding source) - a caller that forgets to "
        "hand over the design/plan/recon paths would go completely unnoticed by this agent's "
        "own self-check"
    )


# ---------------------------------------------------------------------------
# 4. Every agent's self-check is aware of the REPLY_TO malformed-input
#    fallback (never an indefinite wait for want of a reply address).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("agent", ODOO_AGENT_FILES, ids=lambda p: p.stem)
def test_agent_self_check_handles_missing_reply_to(agent):
    section = _self_check_section(agent)
    normalized = " ".join(section.split())
    assert "REPLY_TO" in normalized, (
        f"{agent.relative_to(REPO_ROOT)}: '## Brief self-check' never mentions REPLY_TO - a "
        "caller that omits it under Agent Team mode would leave this agent with no rule "
        "telling it not to wait indefinitely for a reply address"
    )
    # M6 (12-design-final.md): a role=leaf agent body may not cite spawner-completion-contract.md
    # at all (spawner-tier contract) - R3's leaf-facing REPLY_TO fallback moved to
    # worker-brief.md under M1 (#204 AC4), so leaves point there instead. A role=spawner/
    # coordinator is exempt from that ban (it MUST still cite spawner-completion-contract.md
    # elsewhere in its body - see test_role_scoped_citation.py) and may keep pointing at it
    # directly here too. Either way the pointer must be non-restated, never bare-copied prose.
    role = _AGENT_ROLES.get(agent.stem)
    expected_pointer = "spawner-completion-contract.md" if role in ("spawner", "coordinator") else "worker-brief.md"
    assert expected_pointer in normalized, (
        f"{agent.relative_to(REPO_ROOT)}: the REPLY_TO check must point at "
        f"{expected_pointer}'s malformed-input fallback (role={role!r}) rather than restating it."
    )


# ---------------------------------------------------------------------------
# 5. continuation-contract.md binds ODOO-AI-ETHOS #10 at the always-on
#    baseline (not only inside Agent Team mode) and drops the old
#    mis-numbered citation.
# ---------------------------------------------------------------------------


def test_continuation_contract_cites_ethos_10():
    text = _read(CONTINUATION_CONTRACT)
    assert _ETHOS_10 in text, (
        "continuation-contract.md must cite ODOO-AI-ETHOS #10 (Completion Status - 'a DONE "
        "claim must be accompanied by observable evidence') at the always-on baseline, not "
        "only inside agent-team-protocol.md's Agent-Team-mode-gated Ask 1"
    )


def test_continuation_contract_drops_mis_numbered_ethos_citation():
    text = _read(CONTINUATION_CONTRACT)
    assert "Completion-status #8" not in text, (
        "the old citation named the wrong principle number - ODOO-AI-ETHOS 'Completion Status' "
        "is principle #10, not #8 (#8 is 'Test the Behavior, Not the Code'); a runtime agent "
        "that follows the citation to #8 lands on the wrong rule"
    )


def test_continuation_contract_states_three_part_report_always_on():
    norm = _norm(CONTINUATION_CONTRACT)
    low = norm.lower()
    assert "three parts" in low or "3-part" in low, (
        "continuation-contract.md must state the completion report is three parts (prose "
        "summary + produced paths + the continuation block)"
    )
    assert "not only in agent team mode" in low or "always" in low, (
        "the three-part shape must be stated as ALWAYS-on, not scoped to Agent Team mode"
    )


def test_agent_team_protocol_points_at_continuation_contract_for_report_shape():
    """Ask 1 must no longer independently enumerate the 3-part shape (that would duplicate the
    SSOT continuation-contract.md now owns) - it must point at continuation-contract.md
    instead."""
    text = _read(AGENT_TEAM_PROTOCOL)
    assert "1. your **Continuation Contract** block" not in text, (
        "agent-team-protocol.md Ask 1 must not independently re-enumerate the 3-part "
        "completion-report shape (duplicate SSOT) - it must point at "
        "continuation-contract.md, which now owns that shape"
    )
    norm = _norm(AGENT_TEAM_PROTOCOL)
    assert "continuation-contract.md" in norm and "3-part" in norm, (
        "Ask 1 must explicitly point at continuation-contract.md for the report shape"
    )


# ---------------------------------------------------------------------------
# 6. "Waiting" is never expressible as a bare/unqualified terminal outcome.
# ---------------------------------------------------------------------------


def test_continuation_contract_bans_unqualified_waiting():
    norm = _norm(CONTINUATION_CONTRACT)
    low = norm.lower()
    assert "waiting" in low, (
        "continuation-contract.md must explicitly address 'waiting' - silence on it is exactly "
        "the missing-rule gap this test protects"
    )
    for marker in ("what you are waiting on", "who or what can unblock", "what the caller should do next"):
        assert marker in low, (
            f"the waiting rule must name all three components of a qualified pause - missing: "
            f"{marker!r}"
        )
    assert "protocol violation" in low, (
        "an unqualified 'waiting' statement (missing the three components above) must be "
        "named as a protocol violation - a decidable ban, not encouragement"
    )


def test_continuation_status_enum_never_includes_waiting():
    text = _read(CONTINUATION_CONTRACT)
    m = re.search(r"status:\s*([A-Z_| ]+)", text)
    assert m, "could not locate the `status:` enum line in the fenced continuation block"
    assert "WAITING" not in m.group(1).upper(), (
        "'waiting' must never be added as a legal `status` enum value - a genuine pause is "
        "BLOCKED or NEEDS_CONTEXT with blocked_reason naming what/who/next, never its own status"
    )


# ---------------------------------------------------------------------------
# 7. Every CHP-aware dispatching skill wires REPLY_TO - a tighter, causally
#    precise measure than "every skill mentions REPLY_TO somewhere": this
#    denominator is COMPUTED dynamically (never a hardcoded file list), so a
#    new CHP-aware skill added later is caught automatically.
# ---------------------------------------------------------------------------


def _is_chp_aware_dispatcher(skill_path: Path) -> bool:
    """A skill needs to wire REPLY_TO only when it can actually reach Agent-Team-mode/Tier-A
    addressed dispatch - a bare `context-handoff-protocol.md` reference is NOT enough by
    itself, since that file also documents Tier B (fork) and Tier C (fresh spawn), neither of
    which is `SendMessage`-addressed and neither of which needs REPLY_TO. Tightened (structural
    marker, not a file list) after the first version of this predicate produced two false
    positives - `skills/odoo-brl/SKILL.md` and `skills/odoo-gap-analysis/SKILL.md` reference
    `context-handoff-protocol.md` for Tier B (`subagent_type: "fork"`) ONLY, with zero mentions
    of `SendMessage`/`TaskCreate`/`agent-team-protocol.md`/Tier A anywhere in either file - they
    genuinely have no REPLY_TO obligation to wire.
    """
    text = _read(skill_path)
    references_dispatch_brief = "dispatch-brief.md" in text
    reaches_team_mode_addressing = (
        "agent-team-protocol.md" in text
        or "SendMessage" in text
        or "TaskCreate" in text
        or "Tier A" in text
        or "Tier-A" in text
    )
    return references_dispatch_brief and reaches_team_mode_addressing


CHP_AWARE_SKILLS = [f for f in ODOO_SKILL_MD_FILES if _is_chp_aware_dispatcher(f)]

# NOTE on one expected-red case: `skills/odoo-deep-survey/**` is, at the time this test was
# written, owned and being edited by a different, concurrently-running work-group on this
# same tree (serialization: one writer per file). No allowlist/exclusion here either, for the
# same reason stated above - a full, unfiltered sweep that names the offender is the point.


def test_chp_aware_skills_discovered():
    assert len(CHP_AWARE_SKILLS) >= 1, (
        "expected at least 1 skill referencing both dispatch-brief.md and "
        "(context-handoff-protocol.md or agent-team-protocol.md) - the detector predicate is "
        "wrong if this is empty, since skills/odoo-forward-port/SKILL.md alone should match"
    )


@pytest.mark.parametrize("skill", CHP_AWARE_SKILLS, ids=lambda p: p.parent.name)
def test_chp_aware_skill_wires_reply_to(skill):
    text = _read(skill)
    assert "REPLY_TO" in text, (
        f"{skill.relative_to(REPO_ROOT)}: dispatches via a CHP-aware fan-out (references "
        "dispatch-brief.md and context-handoff-protocol.md/agent-team-protocol.md) but never "
        "mentions REPLY_TO - if Agent Team mode is ever active for this skill's run, its "
        "dispatched workers get no REPLY_TO and fall onto the malformed-input degraded path "
        "every time, never the intended addressed path. See skills/odoo-forward-port/SKILL.md "
        "for the reference implementation of the CHP-conditional REPLY_TO injection pattern."
    )


# ---------------------------------------------------------------------------
# 8. ASCII hyphen only (ETHOS output rule) on every file this test file touches.
# ---------------------------------------------------------------------------

_BANNED_DASHES = {
    0x2012: "figure-dash",
    0x2013: "en-dash",
    0x2014: "em-dash",
    0x2015: "horizontal-bar",
}

_TOUCHED_SNIPPETS = [
    DISPATCH_BRIEF,
    WORKER_BRIEF,
    CONTINUATION_CONTRACT,
    SPAWNER_COMPLETION_CONTRACT,
    AGENT_TEAM_PROTOCOL,
]


@pytest.mark.parametrize("snippet", _TOUCHED_SNIPPETS, ids=lambda p: p.name)
def test_touched_snippet_is_ascii_hyphen_clean(snippet):
    body = _read(snippet)
    offenders = [
        f"{snippet.name}: contains {label} (U+{cp:04X})"
        for cp, label in _BANNED_DASHES.items()
        if chr(cp) in body
    ]
    assert not offenders, "typographic dashes found:\n" + "\n".join(offenders)
