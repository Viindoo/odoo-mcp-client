"""Behavioral guard for skills/wave/SKILL.md hard rules.

These tests protect the BEHAVIOR contracts of the wave skill (ETHOS#11):
- Each assertion fails for exactly one reason: the corresponding rule was removed.
- Tests protect the business contract ("no merge without human confirm",
  "never touch principal branch"), NOT the code structure.

Run with: python3.11 -m pytest tests/test_wave_hardrules.py -v
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WAVE_SKILL = ROOT / "plugins" / "odoo-semantic-skills" / "skills" / "wave" / "SKILL.md"


def _body(text: str) -> str:
    """Return the content after the closing --- of the frontmatter block."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if i > 0 and line.strip() == "---":
            return "\n".join(lines[i + 1:])
    return text


def _skill_body() -> str:
    assert WAVE_SKILL.exists(), f"skills/wave/SKILL.md not found at {WAVE_SKILL}"
    return _body(WAVE_SKILL.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Rule 1: Principal-branch-lock
# The skill body must explicitly prohibit checkout/commit on the principal branch.
# If this rule is deleted, multi-WI waves will silently modify the branch other
# sessions depend on, breaking the safety guarantee of the wave pattern.
# ---------------------------------------------------------------------------

_PRINCIPAL_LOCK_RE = re.compile(
    r"(?i)principal.{0,120}?(never|must\s+not|do\s+not).{0,80}?"
    r"(checkout|commit|switch|rebase|merge|push|reset)",
    re.DOTALL,
)


def test_principal_branch_lock_present():
    """Rule 1: skill body must prohibit git write-ops on the principal branch.

    Fails if: the principal-branch-lock hard rule is removed or rephrased to
    drop the prohibition keywords. This would allow subagents to commit directly
    to master/main, defeating the entire wave isolation model.
    """
    body = _skill_body()
    assert _PRINCIPAL_LOCK_RE.search(body), (
        "skills/wave/SKILL.md: principal-branch-lock rule missing. "
        "The body must contain text matching: principal...never/must not/do not...checkout/commit/switch/rebase/merge/push/reset. "
        "This rule prevents wave subagents from committing directly to the principal branch."
    )


# ---------------------------------------------------------------------------
# Rule 4: Human-confirm merge
# The skill body must explicitly prohibit auto-merge and require human confirmation.
# If this rule is deleted, waves could merge PRs automatically, bypassing the
# human safety gate that protects production branches.
# ---------------------------------------------------------------------------

_HUMAN_CONFIRM_RE = re.compile(
    r"(?i)(human.{0,20}confirm|no.{0,20}auto.{0,20}merg|never.{0,20}auto.{0,20}merg"
    r"|wait.{0,40}user.{0,40}confirm|explicit.{0,40}confirm)",
    re.DOTALL,
)


def test_human_confirm_merge_present():
    """Rule 4: skill body must require human confirmation before merge.

    Fails if: the human-confirm-merge hard rule is removed or softened to allow
    automatic merge. Without this, a wave could silently merge a PR while the
    human is away, landing unreviewed changes on the principal branch.
    """
    body = _skill_body()
    assert _HUMAN_CONFIRM_RE.search(body), (
        "skills/wave/SKILL.md: human-confirm-merge rule missing. "
        "The body must contain text matching one of: "
        "'human-confirm', 'no auto-merge', 'never auto-merge', "
        "'wait for user confirmation', 'explicit confirmation'. "
        "This rule ensures no merge happens without a human approval gate."
    )


# ---------------------------------------------------------------------------
# Phase-4 WI-brief nesting rule
# The WI brief skeleton in Phase 2 must state that leaf subagents (depth 2)
# MAY use non-spawning specialist skills but MUST NOT self-spawn or call
# self-spawning skills. This is the depth contract that prevents crash-inducing
# nested subagent chains (depth 3+).
# ---------------------------------------------------------------------------

_NESTING_SKILL_RE = re.compile(
    r"(?i)(may.{0,60}?(nl.?dispatch|specialist\s+skill|non.?spawn)"
    r"|dispatch.{0,60}?specialist.{0,60}?non.?spawn"
    r"|do\s+not.{0,40}?spawn.{0,40}?subagent"
    r"|must\s+not.{0,40}?spawn)",
    re.DOTALL,
)

_NESTING_SELF_SPAWN_RE = re.compile(
    r"(?i)(do\s+not.{0,60}?(self.?spawn|call.{0,30}?self.?spawn"
    r"|invoke.{0,30}?skill.{0,30}?spawn"
    r"|/code.?review.*?from.{0,40}?leaf"
    r"|skill.?creator.*?leaf"
    r"|wave.*?recursive)"
    r"|never.{0,60}?(spawn|self.?spawn))",
    re.DOTALL,
)


def test_wi_brief_nesting_rule_present():
    """Phase-4 WI brief must include the depth-2 nesting rule.

    The WI brief skeleton must state two things:
    (a) leaf subagents MAY NL-dispatch non-spawning specialist skills
    (b) leaf subagents MUST NOT spawn subagents themselves or call self-spawning skills

    Fails if: the nesting rule is removed from the WI brief template. Without it,
    leaf workers at depth 2 would not know they are prohibited from spawning further
    agents, which would create depth-3+ chains that crash the harness due to context
    exhaustion or tool conflicts.
    """
    body = _skill_body()
    assert _NESTING_SKILL_RE.search(body), (
        "skills/wave/SKILL.md: WI-brief nesting rule (a) missing. "
        "The body must state that leaf subagents may NL-dispatch non-spawning specialist skills. "
        "Matches: 'may...NL-dispatch/specialist skill/non-spawn', or similar. "
        "Without this, leaf workers don't know they can delegate to odoo-coder etc."
    )
    assert _NESTING_SELF_SPAWN_RE.search(body), (
        "skills/wave/SKILL.md: WI-brief nesting rule (b) missing. "
        "The body must prohibit leaf subagents from spawning further subagents or calling "
        "self-spawning skills (/code-review, skill-creator, wave). "
        "Without this guard, depth-3+ chains can form and crash the harness."
    )
