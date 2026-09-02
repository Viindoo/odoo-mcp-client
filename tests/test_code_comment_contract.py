"""Guard: every agent that WRITES or REVIEWS Odoo code can reach the comment/docstring contract,
and nothing in the plugin pushes the opposite way.

The behavior under protection is not "a file exists". It is that a dispatched coder arrives at its
first code block already carrying three rules - default to no comment, state WHY not WHAT, never
address the reviewer - and that a reviewer grades a diff for comment SURPLUS, not only absence.

Why the plugin must carry this at all: the harness does not. Claude Code's full comment policy
("Default to writing no comments...", "Don't explain WHAT the code does...") ships in the MAIN
agent's task prompt and collapses to a single "match the surrounding comment density" line on
lean-prompt models; the base system prompt handed to a Task-tool subagent carries no comment policy
whatsoever. Every coder in this plugin IS such a subagent, so an unreachable contract is a silent
no-op - hence the reachability assertions below rather than a mere existence check.

The upstream coding-guidelines extractions are verbatim RST and carry "document your code (docstring
on methods, simple comments for tricky parts of code)". That line stays untouched; the contract
declares precedence over it, and `test_no_consumer_treats_a_missing_docstring_as_a_defect` is the
regression guard that no consumer reintroduces a docstring quota.

Run: python -m pytest tests/test_code_comment_contract.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
SNIPPETS = PLUGIN / "snippets"
AGENTS = PLUGIN / "agents"
SKILLS = PLUGIN / "skills"
GUIDELINES = SKILLS / "_shared" / "coding_guidelines"

CONTRACT = SNIPPETS / "code-comment-contract.md"
CONTRACT_BASENAME = CONTRACT.name

# Mirrors check_orchestration.CARD_BUDGET_DEFAULT_CAP: a snippet cited by >=3 skills+agents is a
# hot contract loaded into many cold contexts, so its size is a per-dispatch cost.
CARD_BUDGET_DEFAULT_CAP = 4096

# Agents whose job is to WRITE source. Each must carry the rule in its own body: a path reference
# alone is a tool call the agent may skip, and these are exactly the contexts the harness leaves
# without any comment policy.
CODE_WRITING_AGENTS = [
    "odoo-backend-coder.md",
    "odoo-frontend-coder.md",
    "odoo-test-writer.md",
]

# Agents that hand a fix specification to a coder. A proven root cause is the strongest pull toward
# a narrating comment, so the handoff must name the contract.
FIX_DISPATCHING_AGENTS = [
    "odoo-backend-debugger.md",
    "odoo-ui-debugger.md",
]

REVIEWER = AGENTS / "odoo-code-reviewer.md"

VERSION_INDEXES = sorted(GUIDELINES.glob("*/INDEX.md"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- The contract itself ------------------------------------------------------------------------

def test_contract_exists():
    assert CONTRACT.is_file(), f"{CONTRACT_BASENAME} is the SSOT for code comments - it must exist"


def test_contract_fits_the_hot_contract_budget():
    """It is cited by well over 3 consumers, so [card-budget] caps it at the default. Keeping it
    under the cap without a grandfather entry is what makes it cheap enough to read on every
    dispatch."""
    size = CONTRACT.stat().st_size
    assert size <= CARD_BUDGET_DEFAULT_CAP, (
        f"{CONTRACT_BASENAME} is {size}B, over the {CARD_BUDGET_DEFAULT_CAP}B default cap - "
        f"trim it rather than declaring a grandfather budget"
    )


@pytest.mark.parametrize(
    "rule",
    [
        # The three rules a coder must arrive carrying, and the two failure modes they answer.
        "default to no comment",
        "purpose, not the mechanics",
        "attribution / self-defense",
        "unshippable references",
        "volume ceiling",
    ],
)
def test_contract_states_each_load_bearing_rule(rule):
    assert rule in _read(CONTRACT).lower(), (
        f"{CONTRACT_BASENAME} must state the '{rule}' rule - it is one of the reasons the "
        f"contract exists"
    )


def test_contract_declares_precedence_over_the_upstream_docstring_line():
    """The verbatim upstream RST says "document your code (docstring on methods...)". Without an
    explicit precedence clause a coder reading both has a genuine conflict and will default to the
    permissive reading."""
    text = _read(CONTRACT).lower()
    assert "document your code" in text and "permission" in text, (
        f"{CONTRACT_BASENAME} must quote the upstream 'document your code' line and demote it to a "
        f"PERMISSION, not a quota - otherwise the two guidelines read as a conflict"
    )


def test_contract_grades_findings_in_both_directions():
    """A one-directional rule regrows the original defect: grading only absence is what produced
    comment surplus in the first place."""
    text = _read(CONTRACT)
    assert "## In review" in text, f"{CONTRACT_BASENAME} must tell a reviewer how to grade"
    review_block = text.split("## In review", 1)[1]
    assert "MED" in review_block and "LOW" in review_block, (
        f"{CONTRACT_BASENAME} § In review must carry graded severities for surplus AND absence"
    )


# --- Reachability -------------------------------------------------------------------------------

@pytest.mark.parametrize("agent", CODE_WRITING_AGENTS)
def test_code_writing_agent_cites_the_contract(agent):
    body = _read(AGENTS / agent)
    assert CONTRACT_BASENAME in body, (
        f"{agent} writes source but cannot reach {CONTRACT_BASENAME}. A Task-tool subagent gets no "
        f"comment policy from the harness, so an uncited contract is a no-op for this agent"
    )


@pytest.mark.parametrize("agent", CODE_WRITING_AGENTS)
def test_code_writing_agent_inlines_the_two_headline_rules(agent):
    """A bare path is a tool call the agent may skip under context pressure. The two rules that
    answer the reported failure modes must survive even if the snippet is never opened."""
    body = _read(AGENTS / agent).lower()
    assert "pre-existed" in body or "self-defense" in body or "attribution" in body, (
        f"{agent} must inline the ban on attribution/self-defense comments, not only link it"
    )
    assert "serves" in body or "why not what" in body or "never what it does" in body, (
        f"{agent} must inline the purpose-over-mechanics rule, not only link it"
    )


@pytest.mark.parametrize("agent", CODE_WRITING_AGENTS)
def test_code_writing_agent_inlines_the_unshippable_reference_ban(agent):
    """The vector is the brief itself: a coder is handed DESIGN_DOC, SURVEY, RED_TEST_PATH,
    WORKLOG, SHARE_DIR/ISOLATE_DIR and WORKTREE_PATH as authoritative inputs, so pointing a comment
    at one reads as helpful traceability. None of them exists in the repo the code ships in, and
    nothing else catches it: the repo's own confidentiality hook scans THIS repo's commits, while a
    coder writes into the customer's."""
    body = _read(AGENTS / agent).lower()
    assert "unshippable" in body, (
        f"{agent} must inline the ban on citing anything absent from the shipping repo"
    )
    assert "state dir" in body or "state-dir" in body or "design_doc" in body, (
        f"{agent} must name at least one concrete unshippable class (the run's state dir, or the "
        f"brief fields that carry those paths) - an abstract ban is not actionable"
    )


def test_reviewer_grades_the_unshippable_reference():
    body = _read(REVIEWER).lower()
    assert "unshippable" in body, (
        "odoo-code-reviewer.md must grade an unshippable reference - it is the only gate that sees "
        "the finished diff"
    )


@pytest.mark.parametrize("agent", FIX_DISPATCHING_AGENTS)
def test_fix_dispatching_agent_passes_the_contract_to_the_coder(agent):
    body = _read(AGENTS / agent)
    assert CONTRACT_BASENAME in body, (
        f"{agent} instructs a coder what to write; it must forward {CONTRACT_BASENAME} so a proven "
        f"root cause does not become a narrating comment in the fix"
    )


def test_reviewer_cites_the_contract():
    assert CONTRACT_BASENAME in _read(REVIEWER), (
        "odoo-code-reviewer.md must cite the contract - it is the gate that catches surplus"
    )


def test_guidelines_catalog_lists_the_contract():
    assert CONTRACT_BASENAME in _read(GUIDELINES / "INDEX.md"), (
        "coding_guidelines/INDEX.md § Snippets catalog is where an agent discovers shared rules; "
        "the contract must appear there"
    )


@pytest.mark.parametrize("index", VERSION_INDEXES, ids=lambda p: p.parent.name)
def test_every_version_by_task_table_routes_to_the_contract(index):
    """read-before-write sends every coder to its version's 'By task' table and forbids reading
    anything the table does not map. A contract absent from the table is unreachable by that
    mandated path."""
    assert CONTRACT_BASENAME in _read(index), (
        f"{index.parent.name}/INDEX.md 'By task' must map to {CONTRACT_BASENAME}; the "
        f"read-before-write mandate forbids reading files the table does not list"
    )


def test_version_indexes_were_actually_discovered():
    """A glob that silently matches nothing would make the parametrized test above vacuously green."""
    assert len(VERSION_INDEXES) >= 6, (
        f"expected the per-version guideline indexes, found {len(VERSION_INDEXES)}"
    )


# --- SSOT: exactly one owner --------------------------------------------------------------------

def test_artifact_voice_defers_to_the_contract_for_source():
    """Both files govern voice. artifact-voice must own prose artifacts only and hand source over,
    or the two drift into contradicting each other about docstrings."""
    text = _read(SNIPPETS / "artifact-voice.md")
    assert CONTRACT_BASENAME in text, (
        "artifact-voice.md must cross-reference the code-comment contract for source files"
    )
    contract_line = re.search(r"^Every ARTIFACT.*?voice:", text, re.S | re.M)
    assert contract_line is not None, "artifact-voice.md § The contract lost its scope sentence"
    assert "docstring" not in contract_line.group(0), (
        "artifact-voice.md must not claim docstrings in its own artifact list - "
        f"{CONTRACT_BASENAME} owns them, and two owners is how the rules drift apart"
    )


# --- Regression guard: no consumer may reintroduce a docstring quota ----------------------------

# "non-obvious logic without a docstring" as a review dimension is exactly the pressure that
# produced the surplus. Phrased as a DEFECT, never as the contract's own explicit refusal.
_DOCSTRING_QUOTA_RE = re.compile(
    r"(?:without|lacks?|lacking|missing|no)\s+(?:a\s+)?docstring", re.I
)
# The contract, and any consumer restating it, must be able to say the opposite out loud.
_EXPLICIT_REFUSAL_RE = re.compile(
    r"(?:not,?\s+on\s+its\s+own,?\s+a\s+finding|do\s+not\s+raise\s+a\s+finding|"
    r"is\s+a\s+permission|not\s+a\s+quota)",
    re.I,
)


def _agent_facing_files() -> list[Path]:
    files = sorted(AGENTS.rglob("*.md"))
    files += sorted(SKILLS.rglob("SKILL.md"))
    files += sorted(SNIPPETS.glob("*.md"))
    return files


@pytest.mark.parametrize("path", _agent_facing_files(), ids=lambda p: p.name)
def test_no_consumer_treats_a_missing_docstring_as_a_defect(path):
    """Every 'missing docstring' mention must sit in the same sentence as the refusal that defuses
    it. A bare one is a docstring quota, and a quota is what the contract exists to remove."""
    for line in _read(path).splitlines():
        if not _DOCSTRING_QUOTA_RE.search(line):
            continue
        assert _EXPLICIT_REFUSAL_RE.search(line), (
            f"{path.relative_to(REPO_ROOT)}: {line.strip()[:160]!r} reads as a docstring quota. "
            f"A missing docstring is not, on its own, a finding - say so on the same line or drop "
            f"the clause ({CONTRACT_BASENAME})"
        )


# --- Self-check: the guards above can actually go RED --------------------------------------------

def test_docstring_quota_detector_can_fire():
    """Red-before-green, committed as an executable check: the exact clause this change removed from
    the reviewer must still be caught if anyone puts it back."""
    removed_clause = "a method doing more than one thing, non-obvious logic without a docstring."
    assert _DOCSTRING_QUOTA_RE.search(removed_clause), "the detector no longer sees a bare quota"
    assert not _EXPLICIT_REFUSAL_RE.search(removed_clause), (
        "the refusal pattern must NOT match a bare quota, or the guard exempts everything"
    )


def test_docstring_quota_detector_accepts_the_defused_form():
    defused = (
        "Do NOT raise a finding merely because a method lacks a docstring - the upstream line "
        "is a permission, not a quota."
    )
    assert _DOCSTRING_QUOTA_RE.search(defused), "sanity: the defused line still mentions the topic"
    assert _EXPLICIT_REFUSAL_RE.search(defused), (
        "the guard must accept a mention that carries its own refusal, else it bans the contract"
    )
