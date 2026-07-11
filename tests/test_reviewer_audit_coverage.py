"""Guard the reviewer <-> dedicated-audit coverage wiring introduced alongside
the diff-scope mode on the three audit skills.

Mirrors the grep-the-prose idiom of `tests/test_agent_body_convention.py`.

Protects:
  - `agents/odoo-code-reviewer.md` names all three dedicated audits, points at
    the shared `review-severity-rubric.md`, briefs them diff-scoped
    (`SCOPE_FILES`/`CHANGED_SET`), and documents the ownership-transfer /
    trigger-only degradation rule (so a dimension is never double-reported).
  - The stale, now-false blanket claim that every dispatched agent (including
    the reviewer itself) "does NOT invoke Skill tool" is gone from
    `skills/odoo-code-review/SKILL.md` and its `references/agent-prompts.md` -
    the reviewer MAY invoke the Skill tool inline for its own dedicated-audit
    escalation.
  - Each of the three audit `SKILL.md` files documents an optional diff-scope
    mode, still defaults to whole-module output when no scope is given
    (regression guard against the diff-scope mode silently becoming
    mandatory), and still routes general code-correctness review requests
    back to `odoo-code-review` in its `## Out of Scope` section.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "plugins" / "odoo-ai-agents" / "agents"
SKILLS_DIR = REPO_ROOT / "plugins" / "odoo-ai-agents" / "skills"

CODE_REVIEWER_AGENT = AGENTS_DIR / "odoo-code-reviewer.md"
CODE_REVIEW_SKILL = SKILLS_DIR / "odoo-code-review" / "SKILL.md"
AGENT_PROMPTS_REF = SKILLS_DIR / "odoo-code-review" / "references" / "agent-prompts.md"

AUDIT_SKILLS = {
    "odoo-perf-audit": SKILLS_DIR / "odoo-perf-audit" / "SKILL.md",
    "odoo-security-audit": SKILLS_DIR / "odoo-security-audit" / "SKILL.md",
    "odoo-deprecation-audit": SKILLS_DIR / "odoo-deprecation-audit" / "SKILL.md",
}

# The stale blanket claim: "...does NOT spawn subagents, does NOT invoke Skill
# tool." with no carve-out for the reviewer's own dedicated-audit escalation.
# The fixed wording splits this into two sentences with a MAY-invoke carve-out
# in between, so this adjacency (comma directly joining the two clauses) is a
# reliable fingerprint of the old, now-false claim.
_STALE_BLANKET_NO_SKILL_TOOL_CLAIM = re.compile(
    r"does not spawn subagents,\s*does not invoke (the )?skill tool",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# odoo-code-reviewer.md wires all three audits + the shared rubric
# ---------------------------------------------------------------------------


def _reviewer_text() -> str:
    assert CODE_REVIEWER_AGENT.exists(), f"{CODE_REVIEWER_AGENT} not found"
    return CODE_REVIEWER_AGENT.read_text(encoding="utf-8")


@pytest.mark.parametrize("audit_skill", sorted(AUDIT_SKILLS))
def test_reviewer_references_each_audit_skill(audit_skill):
    text = _reviewer_text()
    assert audit_skill in text, (
        f"agents/odoo-code-reviewer.md does not reference `{audit_skill}` - the "
        "reviewer must be able to escalate to all three dedicated audits"
    )


def test_reviewer_references_review_severity_rubric():
    text = _reviewer_text()
    assert "review-severity-rubric.md" in text, (
        "agents/odoo-code-reviewer.md does not reference "
        "review-severity-rubric.md - the shared severity scale SSOT"
    )


def test_reviewer_briefs_audits_diff_scoped():
    text = _reviewer_text()
    assert "SCOPE_FILES" in text or "CHANGED_SET" in text, (
        "agents/odoo-code-reviewer.md does not mention SCOPE_FILES or "
        "CHANGED_SET - it must brief each escalated audit diff-scoped, not as "
        "a whole-module re-sweep"
    )


def test_reviewer_documents_ownership_transfer_degradation():
    text = _reviewer_text().lower()
    assert "ownership-transfer" in text or "ownership transfer" in text, (
        "agents/odoo-code-reviewer.md does not mention the ownership-transfer "
        "rule from review-severity-rubric.md"
    )
    assert "trigger-only" in text or "trigger only" in text, (
        "agents/odoo-code-reviewer.md does not mention that its inline check "
        "DEGRADES TO TRIGGER-ONLY once a dimension escalates to its dedicated "
        "audit - required to prevent double-reporting a finding"
    )


# ---------------------------------------------------------------------------
# The stale "reviewer never invokes Skill tool" claim must be gone
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "doc", [CODE_REVIEW_SKILL, AGENT_PROMPTS_REF], ids=lambda p: p.name
)
def test_no_stale_reviewer_never_invokes_skill_tool_claim(doc):
    assert doc.exists(), f"{doc} not found"
    text = doc.read_text(encoding="utf-8")
    match = _STALE_BLANKET_NO_SKILL_TOOL_CLAIM.search(text)
    assert match is None, (
        f"{doc.relative_to(REPO_ROOT)} still contains the stale blanket claim "
        f"{match.group()!r} - odoo-code-reviewer MAY invoke the Skill tool "
        "inline for its own dedicated-audit escalation (see "
        "agents/odoo-code-reviewer.md); only the OTHER dispatched agents "
        "(scoper, ui-reviewer) never invoke it"
    )


def test_code_review_skill_documents_reviewer_may_invoke_skill_tool():
    text = CODE_REVIEW_SKILL.read_text(encoding="utf-8")
    assert "MAY invoke the Skill tool" in text, (
        "skills/odoo-code-review/SKILL.md must positively document that "
        "odoo-code-reviewer MAY invoke the Skill tool inline for its own "
        "dedicated-audit escalation"
    )


def test_agent_prompts_ref_documents_reviewer_may_invoke_skill_tool():
    text = AGENT_PROMPTS_REF.read_text(encoding="utf-8")
    assert "MAY invoke the Skill tool" in text, (
        "skills/odoo-code-review/references/agent-prompts.md must positively "
        "document that odoo-code-reviewer MAY invoke the Skill tool inline for "
        "its own dedicated-audit escalation"
    )


# ---------------------------------------------------------------------------
# Each of the three audit SKILL.md files: diff-scope mode + whole-module
# default (regression guard) + Out-of-Scope routing back to odoo-code-review
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(AUDIT_SKILLS), ids=lambda n: n)
def test_audit_skill_exists(name):
    assert AUDIT_SKILLS[name].exists(), f"{AUDIT_SKILLS[name]} not found"


@pytest.mark.parametrize("name", sorted(AUDIT_SKILLS), ids=lambda n: n)
def test_audit_skill_documents_diff_scope_mode(name):
    text = AUDIT_SKILLS[name].read_text(encoding="utf-8")
    assert "SCOPE_FILES" in text and "CHANGED_SET" in text, (
        f"skills/{name}/SKILL.md does not document a diff-scope mode "
        "(SCOPE_FILES/CHANGED_SET)"
    )


@pytest.mark.parametrize("name", sorted(AUDIT_SKILLS), ids=lambda n: n)
def test_audit_skill_still_defaults_to_whole_module_output(name):
    """Regression guard: diff-scope mode must stay OPTIONAL. A standalone
    invocation (no SCOPE_FILES/CHANGED_SET) must still produce whole-module
    output, exactly as it did before this diff-scope mode was added.
    """
    text = AUDIT_SKILLS[name].read_text(encoding="utf-8").lower()
    assert "default" in text and "whole-module" in text, (
        f"skills/{name}/SKILL.md no longer documents whole-module output as "
        "the default when no SCOPE_FILES/CHANGED_SET is supplied - a "
        "standalone invocation must be unaffected by the new diff-scope mode"
    )


@pytest.mark.parametrize("name", sorted(AUDIT_SKILLS), ids=lambda n: n)
def test_audit_skill_out_of_scope_routes_to_code_review(name):
    text = AUDIT_SKILLS[name].read_text(encoding="utf-8")
    out_of_scope_match = re.search(
        r"^##\s+Out of Scope\s*$(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL
    )
    assert out_of_scope_match, f"skills/{name}/SKILL.md has no `## Out of Scope` section"
    assert "odoo-code-review" in out_of_scope_match.group(1), (
        f"skills/{name}/SKILL.md's `## Out of Scope` section does not route "
        "general code-correctness review requests to `odoo-code-review`"
    )
