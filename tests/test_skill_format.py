"""Validate that every skill ships well-formed YAML frontmatter.

Frontmatter is parsed line-by-line (stdlib only) so the suite has no third-party
dependency on PyYAML.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_FILES = sorted((ROOT / "skills").glob("*/SKILL.md"))
AGENT_FILES = sorted((ROOT / "agents").glob("*.md"))


def _frontmatter(text):
    """Return the dict of top-level keys in the leading --- ... --- block.

    Handles both inline scalars (``key: value``) and YAML block scalars
    (``key: >`` / ``key: |`` followed by indented lines).
    """
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "file must start with '---' frontmatter"
    keys = {}
    i = 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            return keys
        # only capture top-level (unindented) "key: value" pairs
        if line and not line[0].isspace() and ":" in line:
            k, _, v = line.partition(":")
            v = v.strip()
            if v in (">", "|", ">-", "|-", ">+", "|+", ""):
                # block scalar (or empty): gather following indented lines
                body = []
                j = i + 1
                while j < len(lines) and lines[j].strip() != "---" and (
                    lines[j].strip() == "" or lines[j][:1].isspace()
                ):
                    body.append(lines[j].strip())
                    j += 1
                v = " ".join(b for b in body if b).strip()
                i = j
                keys[k.strip()] = v
                continue
            keys[k.strip()] = v
        i += 1
    raise AssertionError("frontmatter not closed with '---'")


def _body(text):
    """Return the content after the closing --- of frontmatter."""
    lines = text.splitlines()
    # Find the closing --- that marks end of frontmatter
    for i, line in enumerate(lines):
        if i > 0 and line.strip() == "---":
            # Everything after this line is the body
            return "\n".join(lines[i + 1 :])
    return ""


def _tools_list(text):
    """Return the list items under the top-level ``tools:`` frontmatter key.

    Handles the YAML block-sequence form::

        tools:
          - item_a
          - item_b
    """
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "file must start with '---' frontmatter"
    tools = []
    in_tools = False
    i = 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            break
        if not line[0:1].isspace() and line.strip().startswith("tools:"):
            in_tools = True
            i += 1
            continue
        if in_tools:
            if line and line[0:1].isspace() and line.strip().startswith("- "):
                tools.append(line.strip()[2:].strip())
            elif line and not line[0:1].isspace():
                # Another top-level key — stop collecting tools
                in_tools = False
        i += 1
    return tools


# ---------------------------------------------------------------------------
# Agent tests
# ---------------------------------------------------------------------------

_DEPTH_RULE_RE = re.compile(
    r"(?i)(do\s+not|must\s+not).{0,60}?(spawn|subagent|sub-?agent)"
)
_SKILL_GUARD_RE = re.compile(
    r"(?i)(do\s+not|must\s+not).{0,80}?(invoke|call).{0,40}?skill"
)


def test_at_least_3_agents():
    assert len(AGENT_FILES) >= 3, f"expected >=3 agents, found {len(AGENT_FILES)}"


@pytest.mark.parametrize("agent", AGENT_FILES, ids=lambda p: p.stem)
def test_agent_frontmatter(agent):
    text = agent.read_text(encoding="utf-8")
    fm = _frontmatter(text)
    assert fm.get("name"), f"{agent.stem}: missing 'name'"
    assert fm.get("description"), f"{agent.stem}: missing 'description'"
    assert fm.get("model"), f"{agent.stem}: missing 'model'"
    tools = _tools_list(text)
    assert tools, f"{agent.stem}: 'tools' key missing or empty (must have >=1 entry)"


@pytest.mark.parametrize("agent", AGENT_FILES, ids=lambda p: p.stem)
def test_agent_depth_rule_guard(agent):
    text = agent.read_text(encoding="utf-8")
    body = _body(text)
    assert _DEPTH_RULE_RE.search(body), (
        f"{agent.stem}: agent body must contain a depth-rule guard matching "
        r"(?i)(do not|must not).*(spawn|subagent|sub-?agent)"
    )


@pytest.mark.parametrize("agent", AGENT_FILES, ids=lambda p: p.stem)
def test_agent_skill_invocation_guard(agent):
    text = agent.read_text(encoding="utf-8")
    body = _body(text)
    assert _SKILL_GUARD_RE.search(body), (
        f"{agent.stem}: agent body must contain a skill-invocation guard matching "
        r"(?i)(do not|must not).*(invoke|call).*skill"
    )


# ---------------------------------------------------------------------------
# Skill tests
# ---------------------------------------------------------------------------


def test_at_least_15_skills():
    assert len(SKILL_FILES) >= 15, f"expected >=15 skills, found {len(SKILL_FILES)}"


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_frontmatter(skill):
    text = skill.read_text(encoding="utf-8")
    fm = _frontmatter(text)
    assert fm.get("name"), f"{skill.parent.name}: missing 'name'"
    assert fm.get("description"), f"{skill.parent.name}: missing 'description'"
    # directory name should match the declared skill name
    assert fm["name"] == skill.parent.name, (
        f"{skill.parent.name}: frontmatter name '{fm['name']}' "
        f"does not match directory"
    )
    # Check for required body sections
    body = _body(text)
    assert "## Persona" in body, f"{skill.parent.name} SKILL.md missing required ## Persona section"
    assert "## Out of Scope" in body, f"{skill.parent.name} SKILL.md missing required ## Out of Scope section"
