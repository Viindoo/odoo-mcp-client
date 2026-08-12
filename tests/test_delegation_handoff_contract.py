"""Guard the round-2 delegation-handoff hardening on top of `snippets/dispatch-brief.md`,
`worker-brief.md`, `continuation-contract.md`, and `spawner-completion-contract.md`.

Protects four behaviors, each previously a caller-side field/rule with no callee-side
enforcement (or, for the ETHOS citations, an existing plugin-shipped principle never bound
at the dispatch site it governs):

1. The caller-side dispatch-brief skeleton carries NO reply-address field, and says so, so a
   caller composing a brief from that file alone cannot invent one. A dispatched agent's report
   is its final message; the launch call's own return value delivers it.
2. Every `odoo-ai-agents` agent's `## Brief self-check` section confirms a prior-artifact
   pointer was supplied (`INPUTS` or a family-named equivalent such as `DESIGN_DOC`) before
   starting work - a caller-side field with a matching callee-side check, not caller-side
   advice with nothing on the receiving end.
3. `OBJECTIVE`/`CONSTRAINTS` compliance with the plugin's own auto-loaded ODOO-AI-ETHOS #4
   (Outcomes over Procedures) is bound (cited) at the one site it governs - the dispatch-brief
   field definitions and every agent's self-check - not left to float unbound while the
   plugin ships the rule.
4. `continuation-contract.md` binds ODOO-AI-ETHOS #10 (Completion Status - "a DONE claim
   must be accompanied by observable evidence") at the always-on baseline, and explicitly bans
   an unqualified "waiting" statement as a terminal state - a genuinely missing rule before
   this change.

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

# A sentence that DENIES the pointer is a key of this family, rather than requiring
# it. Without this distinction a bare substring search is satisfied by the very
# sentence that says the token is NOT part of the brief - the guard then passes on
# text asserting the opposite of what it checks for.
_ARTIFACT_POINTER_DENIAL = re.compile(
    r"not\s+(?:a\s+)?keys?\b|never\s+(?:be\s+)?required|are\s+never\s+required|"
    r"never\s+a\s+STOP|emitting\s+none|no\s+artifact[- ]path",
    re.IGNORECASE,
)
# What makes a denial a DECISION rather than an oversight: it states what happens
# when the field is absent.
_ARTIFACT_POINTER_DISPOSITION = re.compile(
    r"never\s+a\s+STOP|never\s+required|carry\s+that\s+substance|exhaustive\s+key\s+list",
    re.IGNORECASE,
)


def _self_check_sentences(normalized: str):
    """Whitespace-normalized sentences of a self-check section."""
    return [s for s in re.split(r"(?<=[.;!?])\s+", normalized) if s]


def _artifact_pointer_status(normalized: str):
    """(requires, denies) for one self-check section.

    `requires` - a prior-artifact pointer is named in a REQUIRING sentence.
    `denies`   - a sentence names the pointer only to state it is NOT a key of
                 this family's brief.
    Judged per sentence, so an explicit carve-out can never be counted as the
    requirement it removes.
    """
    requires = denies = False
    for sentence in _self_check_sentences(normalized):
        if not _ARTIFACT_POINTER_TOKENS.search(sentence):
            continue
        if _ARTIFACT_POINTER_DENIAL.search(sentence):
            denies = True
        else:
            requires = True
    return requires, denies

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
    """The Brief self-check SECTION, anchored at a line-start heading.

    `_section`'s plain `find` matched the first occurrence anywhere, so an inline cross-reference
    to `## Brief self-check` earlier in the body silently redefined the section this guard reads -
    and the guard then reported the real self-check as missing. Section identity is the heading at
    line start; a mention of its name in a sentence is a pointer, not the section."""
    text = _read(agent_path)
    m = re.search(r"^## Brief self-check\s*$", text, re.M)
    if not m:
        return ""
    return _section(text[m.start():], "## Brief self-check")


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
# 1. The caller-side SSOT carries NO reply-address field and says so, so a
#    caller reading only that file cannot invent one.
# ---------------------------------------------------------------------------


def test_dispatch_brief_skeleton_declares_no_reply_address_field():
    text = _read(DISPATCH_BRIEF)
    assert "REPLY_TO" not in text and "CALLER_ID" not in text, (
        "dispatch-brief.md - the file any spawner reads BY PATH while composing a dispatch "
        "prompt - must carry no reply-address field: a launch call cannot name the agent it "
        "starts and an agent's roster contains neither itself nor its launcher, so any such "
        "field can only ever be filled with a guess"
    )
    norm = _norm(DISPATCH_BRIEF).lower()
    assert "no reply-address field exists" in norm, (
        "dispatch-brief.md must state POSITIVELY that no reply-address field exists - a silent "
        "omission lets the next author re-add the row under a new name"
    )
    assert "spawner-completion-contract.md" in norm, (
        "the no-reply-address statement must point at the R3 SSOT for the return path"
    )


def test_dispatch_brief_skeleton_is_ten_fields_with_no_caller_id_row():
    norm = _norm(DISPATCH_BRIEF)
    assert "Universal skeleton (10 fields)" in norm, (
        "the skeleton heading must reflect the removed reply-address row - still 11 means the "
        "row is back in the table"
    )


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
    """Either the self-check REQUIRES a prior-artifact pointer, or it states -
    explicitly, with a disposition - that this family has none.

    A bare substring search for the token cannot tell those apart: a family whose
    brief legitimately carries no artifact path (one that operates live
    infrastructure) satisfies it with the single sentence declaring the token is
    NOT a key, i.e. the guard goes green on text asserting the opposite of what it
    checks for. Both arms are therefore judged per sentence, and a denial must say
    what the absence means so a reader can tell a deliberate carve-out from a
    forgotten check.
    """
    section = _self_check_section(agent)
    normalized = " ".join(section.split())
    requires, denies = _artifact_pointer_status(normalized)
    assert requires or denies, (
        f"{agent.relative_to(REPO_ROOT)}: '## Brief self-check' never checks for a prior-"
        "artifact pointer (INPUTS/DESIGN_DOC/ORACLE_PATH/GAP_MATRIX/CATALOG_PATH/"
        "SCENARIOS_PATH/diff_path/feature catalog/grounding source) - a caller that forgets to "
        "hand over the design/plan/recon paths would go completely unnoticed by this agent's "
        "own self-check"
    )
    if denies and not requires:
        assert _ARTIFACT_POINTER_DISPOSITION.search(normalized), (
            f"{agent.relative_to(REPO_ROOT)}: '## Brief self-check' declares a prior-artifact "
            "pointer is not a key of this family but never states what its absence MEANS. An "
            "exemption has to say the missing field is never a STOP (and where the exhaustive "
            "key list lives), or the sentence is indistinguishable from a check that was simply "
            "dropped"
        )


def test_the_artifact_pointer_check_distinguishes_a_requirement_from_a_carve_out():
    """Efficacy floor, driven on synthetic sections.

    Both arms above pass today, so nothing in the parametrized sweep proves the
    predicate can still tell them apart. These cases fail the moment it degrades
    back to a substring search.
    """
    requiring = "Confirm the brief carries INPUTS naming the prior artifact before starting."
    assert _artifact_pointer_status(requiring) == (True, False)

    carve_out = (
        "Confirm the brief carries this family's required fields (INSTANCE_HANDLE, series). "
        "`INPUTS` and any artifact-path field are NOT keys of this family's brief and are "
        "NEVER required here; their absence is NEVER a STOP."
    )
    requires, denies = _artifact_pointer_status(carve_out)
    assert (requires, denies) == (False, True), (
        "a sentence that DENIES the pointer is a key must not be counted as requiring it"
    )
    assert _ARTIFACT_POINTER_DISPOSITION.search(" ".join(carve_out.split())), (
        "a legitimate carve-out states the disposition of the absent field"
    )

    silent = "Confirm the brief carries INSTANCE_HANDLE and the target series."
    assert _artifact_pointer_status(silent) == (False, False), (
        "a self-check that never mentions a prior-artifact pointer at all must be a finding"
    )

    bare_denial = "`INPUTS` is not a key of this family."
    requires, denies = _artifact_pointer_status(bare_denial)
    assert (requires, denies) == (False, True)
    assert not _ARTIFACT_POINTER_DISPOSITION.search(bare_denial), (
        "a denial with no stated disposition must NOT satisfy the exemption arm - that is "
        "how a dropped check would slip through as a carve-out"
    )


# ---------------------------------------------------------------------------
# 4. No agent's self-check names a reply address or a messaging tool. The
#    branch it used to guard consulted a value that cannot exist, and keyed
#    behavior on a tool merely being present.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("agent", ODOO_AGENT_FILES, ids=lambda p: p.stem)
def test_agent_self_check_names_no_reply_address(agent):
    section = _self_check_section(agent)
    normalized = " ".join(section.split())
    for banned in ("REPLY_TO", "CALLER_ID", "SendMessage"):
        assert banned not in normalized, (
            f"{agent.relative_to(REPO_ROOT)}: '## Brief self-check' names {banned!r}. The "
            "self-check runs before any work and must consult only fields a caller can actually "
            "supply; a reply address is not one, and a messaging tool being in the toolset is "
            "not evidence of anything (spawner-completion-contract.md R3)."
        )


# ---------------------------------------------------------------------------
# 5. continuation-contract.md binds ODOO-AI-ETHOS #10 at the always-on
#    baseline, at every dispatch tier, and drops the old mis-numbered citation.
# ---------------------------------------------------------------------------


def test_continuation_contract_cites_ethos_10():
    text = _read(CONTINUATION_CONTRACT)
    assert _ETHOS_10 in text, (
        "continuation-contract.md must cite ODOO-AI-ETHOS #10 (Completion Status - 'a DONE "
        "claim must be accompanied by observable evidence') at the always-on baseline, not "
        "only inside a tier-gated transport rule"
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
    assert "always" in low, (
        "the three-part shape must be stated as ALWAYS-on, never scoped to one dispatch tier"
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
# 7. No dispatching skill wires a reply address into any brief it composes.
#    Denominator is COMPUTED (never a hardcoded file list), so a new
#    dispatching skill added later is caught automatically.
# ---------------------------------------------------------------------------


DISPATCHING_SKILLS = [f for f in ODOO_SKILL_MD_FILES if "dispatch-brief.md" in _read(f)]


def test_dispatching_skills_discovered():
    assert len(DISPATCHING_SKILLS) >= 1, (
        "expected at least 1 skill referencing dispatch-brief.md - the detector predicate is "
        "wrong if this is empty, since skills/odoo-forward-port/SKILL.md alone should match"
    )


@pytest.mark.parametrize("skill", DISPATCHING_SKILLS, ids=lambda p: p.parent.name)
def test_dispatching_skill_wires_no_reply_address(skill):
    text = _read(skill)
    for banned in ("REPLY_TO", "CALLER_ID"):
        assert banned not in text, (
            f"{skill.relative_to(REPO_ROOT)}: composes dispatch briefs (references "
            f"dispatch-brief.md) and still names {banned!r}. No brief carries a reply address: "
            "the dispatched agent's report is its final message and this skill reads it from "
            "its own launch call's return value (spawner-completion-contract.md R3)."
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
