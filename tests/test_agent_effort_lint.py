"""Rule 22 [agent-effort]: an agent never declares `max` (or an unknown value) as its effort."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "odoo-ai-agents"))
from generator import check_orchestration as co  # noqa: E402


def _findings(tmp_path, frontmatter_line):
    agent = tmp_path / "plugins" / "p" / "agents" / "a.md"
    agent.parent.mkdir(parents=True)
    extra = f"{frontmatter_line}\n" if frontmatter_line else ""
    agent.write_text(f"---\nname: a\nmodel: sonnet\n{extra}---\nbody effort: max\n", encoding="utf-8")
    return co.agent_effort_findings([agent], tmp_path)


@pytest.mark.parametrize("value", ["low", "medium", "high", "xhigh", "'high'"])
def test_a_valid_effort_is_accepted(tmp_path, value):
    assert _findings(tmp_path, f"effort: {value}") == []


def test_no_effort_is_accepted(tmp_path):
    assert _findings(tmp_path, "") == []


@pytest.mark.parametrize("value", ["max", "turbo", ""])
def test_max_and_unknown_values_are_refused(tmp_path, value):
    found = _findings(tmp_path, f"effort: {value}")
    assert len(found) == 1 and found[0].startswith("[agent-effort] 'plugins/p/agents/a.md'")


def test_the_shipped_agents_pass_the_rule():
    findings: list[str] = []
    co.check_agent_effort(findings)
    assert findings == []
