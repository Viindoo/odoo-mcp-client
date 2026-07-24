"""Guard the agent-body convention: an agent `.md` body is the agent's SYSTEM
PROMPT, not a routing surface.

Per Anthropic's subagent contract (https://code.claude.com/docs/en/sub-agents)
the frontmatter `description` is routing metadata - read by the orchestrator when
it decides whether to delegate - and the Markdown body is the system prompt the
running agent reads at startup. A `## When to invoke` heading in the body
re-states the `description`'s routing text and pollutes the system prompt with
content the running agent cannot act on, so it is banned in every plugin agent
file. See CONTRIBUTING.md "Agent format".

The ban is not limited to that one literal heading (V-36): a `## Out of Scope`
or `## Routing` section whose bullets are DOMINATED by `-> use X` redirects is
the same banned routing content under a different name - it evaded the
heading-only regex while still being unactionable-by-the-running-agent routing
prose. A section is "redirect-dominated" when at least half of its bullet
lines redirect elsewhere (`-> use X`); a genuine boundary note kept as prose
(no majority of bullets redirecting) is not flagged, so a legitimate
non-routing "Out of Scope" note elsewhere would not trip this guard. (Audited
at broadening time via `grep -rniE "^#{2} *(out.of.scope|routing)"
plugins/*/agents/*.md`: only `odoo-ui-debugger.md` carried either heading, and
that section was removed as part of this same fix - re-run the grep before
tightening this guard further.)
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_FILES = sorted(REPO_ROOT.glob("plugins/*/agents/*.md"))

# A Markdown H2 heading whose title starts with "When to invoke". The `^`
# anchor (with no leading indentation) only matches body headings: inside YAML
# frontmatter the phrase can only appear indented under a block scalar
# (`description: |`), so frontmatter prose mentions are intentionally not caught.
_WHEN_TO_INVOKE_HEADING = re.compile(r"^##\s+When to invoke", re.IGNORECASE)

# Generic routing-section headings (V-36). These are banned ONLY when the
# section is redirect-dominated (see `_is_redirect_dominated`) - unlike the
# unconditional `## When to invoke` ban above.
_REDIRECT_SECTION_HEADING = re.compile(
    r"^##\s+(Out[\s-]of[\s-]Scope|Routing)\b", re.IGNORECASE
)

_ANY_H2_HEADING = re.compile(r"^##\s+")
_BULLET_LINE = re.compile(r"^\s*[-*]\s+")
_REDIRECT_BULLET = re.compile(r"->\s*use\b", re.IGNORECASE)


def _section_body(lines: list[str], heading_idx: int) -> list[str]:
    """Lines strictly after the heading at `heading_idx`, up to (not including)
    the next top-level `## ` heading or end of file."""
    body = []
    for line in lines[heading_idx + 1 :]:
        if _ANY_H2_HEADING.match(line):
            break
        body.append(line)
    return body


def _is_redirect_dominated(section_lines: list[str]) -> bool:
    """True when at least half the bullet lines in the section redirect
    elsewhere (`-> use X`) - i.e. the section is functionally a routing table
    in prose clothing, not a boundary explanation. A section with no bullets
    at all (pure prose) is never dominated."""
    bullets = [line for line in section_lines if _BULLET_LINE.match(line)]
    if not bullets:
        return False
    redirects = [line for line in bullets if _REDIRECT_BULLET.search(line)]
    return len(redirects) / len(bullets) >= 0.5


def test_agent_files_discovered():
    # Floor: the glob must resolve real files, else the guard passes vacuously.
    assert AGENT_FILES, "no plugins/*/agents/*.md files found - glob is wrong"


# --- unit-level proof each predicate can fail (crafted strings, not just real files) ---
def test_redirect_dominated_predicate_can_fail():
    dominated = [
        "- **Rating a working screen** (aesthetics, a11y) -> use `odoo-ui-reviewer`",
        "- **Comparing two builds for drift** -> use `odoo-visual-regression`",
        "- **Writing the fix** -> use `odoo-coding`",
    ]
    assert _is_redirect_dominated(dominated)
    prose_boundary_note = [
        "- This agent never modifies application code or the running instance;",
        "  it only names the root cause and the file/method to change.",
    ]
    assert not _is_redirect_dominated(prose_boundary_note)
    assert not _is_redirect_dominated([])


def test_section_body_stops_at_next_h2():
    lines = ["## Out of Scope", "- a -> use `x`", "## Next Section", "- b -> use `y`"]
    assert _section_body(lines, 0) == ["- a -> use `x`"]


@pytest.mark.parametrize(
    "agent", AGENT_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_no_when_to_invoke_routing_heading_in_body(agent):
    rel = agent.relative_to(REPO_ROOT)
    offenders = [
        f"line {n}: {line.strip()}"
        for n, line in enumerate(agent.read_text(encoding="utf-8").splitlines(), 1)
        if _WHEN_TO_INVOKE_HEADING.match(line)
    ]
    assert not offenders, (
        f"{rel} has a `## When to invoke` body heading. Agent routing ('when to "
        "delegate') belongs in the `description` frontmatter, not the body - the "
        "body is the agent's system prompt (Anthropic subagent contract). Move "
        "triggers/examples to `description`; keep only runtime constraints in the "
        "body. See CONTRIBUTING.md 'Agent format'. Offending:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(
    "agent", AGENT_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_no_redirect_dominated_routing_section_in_body(agent):
    """Broadens the ban past the literal `## When to invoke` heading (V-36): a
    `## Out of Scope` / `## Routing` section is the same banned routing content
    under a different name once its bullets are dominated by `-> use X`
    redirects - it just evades a heading-only regex. A section kept for a
    genuine non-routing reason (prose boundary note, no bullet majority
    redirecting elsewhere) is NOT flagged."""
    rel = agent.relative_to(REPO_ROOT)
    lines = agent.read_text(encoding="utf-8").splitlines()
    offenders = []
    for n, line in enumerate(lines):
        if not _REDIRECT_SECTION_HEADING.match(line):
            continue
        if _is_redirect_dominated(_section_body(lines, n)):
            offenders.append(f"line {n + 1}: {line.strip()}")
    assert not offenders, (
        f"{rel} has a routing section (`## Out of Scope`/`## Routing`) whose "
        "bullets are dominated by `-> use X` redirects - this is the banned "
        "routing content from a different heading (V-36); routing belongs in "
        "the `description` frontmatter, not the body. Remove the section (moving "
        "any missing redirect into `description`) or rewrite it as prose that is "
        "not a majority of skill/agent redirects. See CONTRIBUTING.md 'Agent "
        "format'. Offending:\n  " + "\n  ".join(offenders)
    )
