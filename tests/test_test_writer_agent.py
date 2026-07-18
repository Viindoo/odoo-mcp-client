"""Contract tests for the dedicated odoo-test-writer agent (v4.9.0).

Protects the BEHAVIOR of the reconciled test-authoring topology (not a wording snapshot):

- `odoo-test-writer` is a NEW agent that exists and is registered in plugin.json.
- It AUTHORS Odoo automation tests by invoking the `odoo-test-writing` skill INLINE (its capability
  SSOT) - it does not re-implement the authoring procedure.
- It is a HARD LEAF: it spawns no further agent (invokes the skill inline, +0 depth).
- Every named caller that needs a test authored LAUNCHES the odoo-test-writer agent (context
  isolation) - not the odoo-test-writing skill inline, and not a coder in a bespoke test-author mode.
- The `odoo-coder` COORDINATOR launches odoo-test-writer (test-first); the `odoo-coding` SKILL does
  NOT (the coordinator owns it), avoiding a skill<->agent cycle.
- The coder agents no longer author tests; the bespoke TEST-AUTHOR MODE wiring is gone.

Red-before-green: each assertion fails if its wiring is dropped or inverted.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
AGENTS = PLUGIN / "agents"
SKILLS = PLUGIN / "skills"
WRITER = AGENTS / "odoo-test-writer.md"
CLAUDE_MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"
DEPS = PLUGIN / "generator" / "skill_tool_deps.json"

# Skills whose body actively LAUNCHES the odoo-test-writer agent to have a test authored.
#
# odoo-qa-suite is intentionally NOT here: its Phase 1 produces a STATIC, non-executing
# release TEST-PLAN table (frontmatter, :24, :86), never a runnable test file, so it must
# never launch the agent - launching it was the outlier bug fixed by V-05 (deleted).
# Runnable tests route to the odoo-test-writing skill directly (see its frontmatter
# description), not through this skill.
CALLERS = {
    "odoo-acceptance": SKILLS / "odoo-acceptance" / "SKILL.md",
    "odoo-code-review": SKILLS / "odoo-code-review" / "SKILL.md",
    "odoo-forward-port": SKILLS / "odoo-forward-port" / "SKILL.md",
    "odoo-git-rebase": SKILLS / "odoo-git-rebase" / "SKILL.md",
}


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_test_writer_agent_exists_and_is_registered():
    """The odoo-test-writer agent file exists and is declared in plugin.json.agents."""
    assert WRITER.is_file(), "agents/odoo-test-writer.md must exist (the test-authoring executor)"
    declared = {Path(p).name for p in json.loads(_text(CLAUDE_MANIFEST)).get("agents", [])}
    assert "odoo-test-writer.md" in declared, (
        "odoo-test-writer.md must be declared in .claude-plugin/plugin.json agents"
    )


def test_test_writer_authors_by_invoking_the_skill_inline():
    """It AUTHORS by invoking the odoo-test-writing skill INLINE - its capability SSOT."""
    body = _text(WRITER)
    assert "odoo-test-writing" in body, (
        "odoo-test-writer must name the odoo-test-writing skill it invokes"
    )
    low = body.lower()
    assert "inline" in low, "odoo-test-writer must invoke the odoo-test-writing skill INLINE (+0 depth)"
    assert "Skill(odoo-test-writing)" in body or "skill `odoo-test-writing`" in low or (
        "invoke" in low and "odoo-test-writing" in body
    ), "odoo-test-writer must invoke the odoo-test-writing skill via the Skill tool"


def test_test_writer_is_a_hard_leaf():
    """It is a HARD LEAF: it spawns no further agent."""
    low = _text(WRITER).lower()
    assert "hard leaf" in low, "odoo-test-writer must declare it is a HARD LEAF"
    assert "never launch" in low or "launch no sub-agent" in low or "launches no" in low or (
        "spawns no" in low
    ), "odoo-test-writer must state it launches no sub-agent"


def test_test_writer_registered_in_orchestration_ssot():
    """The orchestration SSOT records odoo-test-writer as an agent tool-dep entry that mirrors the
    odoo-test-writing skill surface (it invokes it inline)."""
    deps = json.loads(_text(DEPS))
    assert "odoo-test-writer" in deps["agents"], (
        "skill_tool_deps.json agents must include odoo-test-writer (its tool deps)"
    )
    # A skill DIR must not be minted for the agent (orchestration keys are skill dirs only).
    assert "odoo-test-writer" not in deps["orchestration"], (
        "odoo-test-writer is an AGENT, not a skill dir - it must not have its own orchestration key "
        "(it appears in the spawns lists of the skills that launch it)"
    )


def test_named_callers_launch_the_test_writer_agent():
    """Every named caller launches the odoo-test-writer agent (context isolation) for authoring."""
    for name, path in CALLERS.items():
        assert "odoo-test-writer" in _text(path), (
            f"{name} must launch the odoo-test-writer agent to author tests (context isolation)"
        )


def test_qa_suite_does_not_launch_the_test_writer_agent():
    """Regression guard for V-05: odoo-qa-suite Phase 1 is a STATIC, non-executing release
    TEST-PLAN table - it must never launch odoo-test-writer (that launch contradicted its own
    frontmatter/:24/:86 static-orchestrator contract and was deleted)."""
    assert "odoo-test-writer" not in _text(SKILLS / "odoo-qa-suite" / "SKILL.md"), (
        "odoo-qa-suite must not launch the odoo-test-writer agent - Phase 1 is static/"
        "non-executing/inline; runnable tests route to odoo-test-writing directly"
    )


def test_coder_launches_writer_but_coding_skill_does_not():
    """The odoo-coder COORDINATOR launches odoo-test-writer (test-first); the odoo-coding SKILL does
    NOT - the coordinator owns it (no skill<->agent cycle)."""
    coder = _text(AGENTS / "odoo-coder.md")
    assert "odoo-test-writer" in coder, "the odoo-coder coordinator must launch odoo-test-writer"

    coding = _text(SKILLS / "odoo-coding" / "SKILL.md")
    low = coding.lower()
    assert "does not launch `odoo-test-writer`" in low or "does not launch odoo-test-writer" in low, (
        "odoo-coding must state it does NOT launch odoo-test-writer (the coordinator does)"
    )


def test_no_bespoke_coder_test_author_mode_remains():
    """The old 'TEST-AUTHOR MODE' coder-authors-tests wiring must be gone; coders write code only."""
    scan = [
        SKILLS / "odoo-coding" / "SKILL.md",
        AGENTS / "odoo-coder.md",
        AGENTS / "odoo-backend-coder.md",
        AGENTS / "odoo-frontend-coder.md",
    ]
    offenders = [p.relative_to(ROOT) for p in scan if "TEST-AUTHOR MODE" in _text(p)]
    assert not offenders, (
        "the bespoke TEST-AUTHOR MODE (coder-authors-tests) wiring must be removed; offenders: "
        + ", ".join(str(o) for o in offenders)
    )
    # The coders must explicitly disclaim test authoring.
    for agent in ("odoo-backend-coder", "odoo-frontend-coder"):
        low = _text(AGENTS / f"{agent}.md").lower()
        assert "do not author tests" in low or "does not author tests" in low, (
            f"{agent} must state it does NOT author tests (the odoo-test-writer teammate does)"
        )
