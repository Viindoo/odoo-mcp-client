"""Guard: every skill description must stay under the per-entry hard cap.

Claude's skill listing truncates/drops descriptions over ~1024 chars, which
silently degrades triggering. This test locks in the description compaction so a
future edit cannot let a description re-bloat past the cap without failing CI.

Frontmatter is parsed line-by-line (stdlib only), mirroring test_skill_format.py.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_FILES = sorted((ROOT / "plugins" / "odoo-ai-agents" / "skills").glob("*/SKILL.md"))

# Hard limit at which Claude truncates a skill/command description (confirmed in
# skill-creator's improve_description.py). Stay at or under it for every skill.
HARD_CAP = 1024
# Soft target from the compaction pass; exceeding it is allowed but worth noticing.
SOFT_TARGET = 1024


def _description(text):
    """Return the flattened description string from YAML frontmatter."""
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "file must start with '---' frontmatter"
    i = 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            break
        if line and not line[0].isspace() and line.split(":", 1)[0] == "description":
            v = line.split(":", 1)[1].strip()
            if v in (">", "|", ">-", "|-", ">+", "|+", ""):
                body = []
                j = i + 1
                while j < len(lines) and lines[j].strip() != "---" and (
                    lines[j].strip() == "" or lines[j][:1].isspace()
                ):
                    body.append(lines[j].strip())
                    j += 1
                return " ".join(b for b in body if b).strip()
            return v
        i += 1
    raise AssertionError("description key not found in frontmatter")


def test_skill_files_discovered():
    assert len(SKILL_FILES) >= 26, f"expected >=26 skills, found {len(SKILL_FILES)}"


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_description_under_hard_cap(skill):
    desc = _description(skill.read_text(encoding="utf-8"))
    n = len(desc)
    assert n <= HARD_CAP, (
        f"{skill.parent.name}: description is {n} chars, over the {HARD_CAP}-char hard cap "
        f"— Claude will truncate it. Compact the description (trim duplicate trigger "
        f"phrases / examples; keep routing/disambiguation clauses)."
    )
