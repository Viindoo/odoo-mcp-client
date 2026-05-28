"""Validate that every skill ships well-formed YAML frontmatter.

Frontmatter is parsed line-by-line (stdlib only) so the suite has no third-party
dependency on PyYAML.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_FILES = sorted((ROOT / "skills").glob("*/SKILL.md"))


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
