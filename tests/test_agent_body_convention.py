"""Guard the agent-body convention: an agent `.md` body is the agent's SYSTEM
PROMPT, not a routing surface.

Per Anthropic's subagent contract (https://code.claude.com/docs/en/sub-agents)
the frontmatter `description` is routing metadata - read by the orchestrator when
it decides whether to delegate - and the Markdown body is the system prompt the
running agent reads at startup. A `## When to invoke` heading in the body
re-states the `description`'s routing text and pollutes the system prompt with
content the running agent cannot act on, so it is banned in every plugin agent
file. See CONTRIBUTING.md "Agent format".
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


def test_agent_files_discovered():
    # Floor: the glob must resolve real files, else the guard passes vacuously.
    assert AGENT_FILES, "no plugins/*/agents/*.md files found - glob is wrong"


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
