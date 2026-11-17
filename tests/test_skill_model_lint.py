"""Rule 23 [skill-model]: a skill's frontmatter carries no `model:` key."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "odoo-ai-agents"))
from generator import check_orchestration as co  # noqa: E402


def _findings(tmp_path, frontmatter_line, body="body model: opus"):
    skill = tmp_path / "plugins" / "p" / "skills" / "s" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    extra = f"{frontmatter_line}\n" if frontmatter_line else ""
    skill.write_text(f"---\nname: s\ndescription: d\n{extra}---\n{body}\n", encoding="utf-8")
    return co.skill_model_findings([skill], tmp_path)


def test_a_skill_without_model_is_accepted_even_if_the_body_mentions_one(tmp_path):
    assert _findings(tmp_path, "") == []


@pytest.mark.parametrize("line", ["model: sonnet", "model:opus", "model: 'haiku'", "model:"])
def test_a_model_key_is_refused(tmp_path, line):
    found = _findings(tmp_path, line)
    assert len(found) == 1 and found[0].startswith("[skill-model] 'plugins/p/skills/s/SKILL.md'")


def test_a_key_that_only_starts_with_model_is_accepted(tmp_path):
    assert _findings(tmp_path, "models: x") == []


def test_the_shipped_skills_pass_the_rule():
    findings: list[str] = []
    co.check_skill_model(findings)
    assert findings == []
