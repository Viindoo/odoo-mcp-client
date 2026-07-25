"""Guard: no plugin agent declares a frontmatter field the build silently discards.

Platform fact, recovered from the plugin-agent loader (build 2.1.218):

    for(let U of["permissionMode","hooks","mcpServers"]) if(c[U]!==void 0)
      w(`Plugin agent file ${e} sets ${U}, which is ignored for plugin agents.
         Use .claude/agents/ for this level of control.`,{level:"warn"});

`permissionMode`/`hooks`/`mcpServers` never reach the returned agent descriptor for a PLUGIN
agent (`plugins/*/agents/*.md`) - they are read only to emit the warning above, then discarded.
These fields take effect only for agents under user/project `.claude/agents/`, which is outside
any plugin and outside this repo's authority.

There is therefore NO frontmatter lever a plugin agent has to influence its own permission mode
(see docs/authoring-skills-and-agents.md § Agent authoring and
snippets/planning-gate-contract.md § Plan-Mode enter/exit for the behavioral fix this motivated -
P3: do not dispatch a state-root-writing agent while a Plan Mode window is open). This test
guards against a future author reintroducing one of these dead fields under the mistaken belief
it changes runtime enforcement.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AGENT_FILES = sorted(ROOT.glob("plugins/*/agents/*.md"))

IGNORED_FIELDS = ("permissionMode", "hooks", "mcpServers")

_WARN_STRING = "ignored for plugin agents"


def _frontmatter_lines(text: str) -> list[str]:
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "file must start with '---' frontmatter"
    out = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        out.append(line)
    return out


def test_at_least_one_agent_found():
    # Anti-drift: if the glob pattern stops matching (e.g. a plugin restructure),
    # this test must fail loudly rather than silently pass on zero files.
    assert len(AGENT_FILES) >= 3, f"expected >=3 plugin agents, found {len(AGENT_FILES)}"


@pytest.mark.parametrize("agent", AGENT_FILES, ids=lambda p: f"{p.parent.parent.name}/{p.stem}")
def test_agent_declares_no_ignored_field(agent):
    text = agent.read_text(encoding="utf-8")
    fm_lines = _frontmatter_lines(text)
    rel = agent.relative_to(ROOT)
    for field in IGNORED_FIELDS:
        offenders = [
            line for line in fm_lines
            if not line[:1].isspace() and line.strip().startswith(f"{field}:")
        ]
        assert not offenders, (
            f"{rel}: declares top-level `{field}:` in frontmatter, which is {_WARN_STRING} "
            f"(the build warns and discards it - see the platform fact in this test's module "
            f"docstring). Use user/project `.claude/agents/` for this level of control instead."
        )
