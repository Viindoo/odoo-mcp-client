"""Terminology guard: the literal phrase "Agent tool" / "Agent-tool" must not appear (or
reappear) in agent-facing prose.

Why this matters: agent/skill/snippet prose that hardcodes "the Agent tool" by name prescribes one
specific runtime's launch mechanism. Not every harness this plugin set targets exposes a tool
literally named that (Codex/Gemini expose their own dispatch primitives) - and even within Claude
Code, prescribing the tool BY NAME couples prose to an implementation detail instead of describing
the OUTCOME (launch/dispatch/cold-spawn a subagent). A prior wave renamed every such occurrence in
agent-facing prose to a neutral verb; this test is the regression guard that keeps it renamed.

Scope: every file under the agent-facing prose directories -
`plugins/odoo-ai-agents/{skills,agents,snippets,docs,workflows,commands}` and
`plugins/git-toolkit/{skills,agents,snippets,docs}` - regardless of extension (.md prose, .json
evals, .yaml workflows all render into what an agent reads or a router matches against).

Deliberate exclusions (each is commented at its own line below, not just listed here):
  - `generator/` (both plugins) - this is BUILD-TIME source that emits the render surface; it is
    not itself agent-facing prose, and `generator/gen_surface.py` / `generator/check_orchestration.py`
    are Python, not prose a routing agent reads.
  - `generator/check_orchestration.py` specifically - even though it lives under generator/ (already
    excluded), called out explicitly because it is the DETECTOR whose own job is to find this exact
    phrase in OTHER prose; its regex/comment literals legitimately contain the phrase to recognize it
    and must keep it, not be mistaken for a violation if scope ever changes.
  - `tests/` (this whole directory, including this file) - test code narrates old/new wording as
    part of its own assertions and docstrings; it is not prose an agent reads at dispatch time.
  - `tests/test_git_delegation_boundary.py` specifically - already finalized in a separate wave and
    out of this task's edit scope; it legitimately narrates "Agent tool" as historical / detector
    vocabulary for its own git-delegation assertions.
  - `CHANGELOG.md` - a historical record of past releases; rewriting history to match current
    terminology would falsify what actually shipped in each past version.
  - `tests/smoke/runtime_parity.md` - deliberately keeps the literal phrase: it is a cross-runtime
    PARITY note that has to name the Claude-Code-native tool by its actual name to explain why an
    equivalent feature is or is not available on Codex/Gemini.

Run: python -m pytest tests/test_terminology_launch_agent.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Matches "Agent tool", "Agent-tool", "agent tools", "Agent-Tools", etc. but NOT "Agent toolset" /
# "Agent tooling" (the trailing \b requires a non-word character right after "tool[s]", so a
# continuation like "set"/"ing" fails to match).
_BANNED_PHRASE_RE = re.compile(r"\bAgent[ -]tools?\b", re.IGNORECASE)

# Each root is scanned recursively for ALL files (not just *.md) - evals.json, *.workflow.yaml, and
# reference *.txt all count as agent-facing surface under these directories.
_SCAN_ROOTS = [
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "skills",
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "agents",
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "snippets",
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "docs",
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "workflows",
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "commands",
    REPO_ROOT / "plugins" / "git-toolkit" / "skills",
    REPO_ROOT / "plugins" / "git-toolkit" / "agents",
    REPO_ROOT / "plugins" / "git-toolkit" / "snippets",
    REPO_ROOT / "plugins" / "git-toolkit" / "docs",
]

# generator/ (either plugin) is never in _SCAN_ROOTS above - it is build-time source, not the
# rendered agent-facing surface; generator/check_orchestration.py's own KEEP-comment/detector
# literal is covered by that same blanket exclusion, not by a separate carve-out.
#
# tests/ (this whole directory) is never scanned - test code, including
# tests/test_git_delegation_boundary.py (already finalized, out of scope) and
# tests/smoke/runtime_parity.md (deliberately keeps the phrase), narrates old/new wording for its
# own assertions rather than being agent-facing prose.
#
# CHANGELOG.md lives at the repo root, outside every root above, so it is excluded by construction.


def _iter_scanned_files():
    for root in _SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                yield path


def test_scan_roots_exist():
    """Sanity check: the directories this guard scans must actually exist, so a typo'd path can
    never silently make this test vacuously pass."""
    missing = [str(r.relative_to(REPO_ROOT)) for r in _SCAN_ROOTS if not r.exists()]
    assert not missing, f"expected agent-facing prose directories are missing: {missing}"


def test_no_literal_agent_tool_phrase_in_agent_facing_prose():
    """No skill / agent / snippet / doc / workflow / command file may contain the literal phrase
    "Agent tool" / "Agent-tool" (singular or plural, either separator) - prose must describe the
    OUTCOME (launch / dispatch / cold-spawn a subagent), not prescribe one runtime's tool name."""
    offenders = []
    for path in _iter_scanned_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        match = _BANNED_PHRASE_RE.search(text)
        if match:
            rel = path.relative_to(REPO_ROOT)
            offenders.append(f"{rel}: {match.group()!r}")
    assert not offenders, (
        "literal 'Agent tool' / 'Agent-tool' phrase found in agent-facing prose (describe the "
        "outcome - launch/dispatch/cold-spawn - instead of naming the tool): "
        + "; ".join(offenders)
    )


def test_banned_phrase_regex_does_not_false_positive_on_toolset():
    """Guard the guard: the regex must not flag legitimate uses like 'in your own toolset' /
    'Agent toolset' / 'tooling' - only the standalone 'Agent tool(s)' phrase is banned."""
    assert _BANNED_PHRASE_RE.search("the Agent toolset available this turn") is None
    assert _BANNED_PHRASE_RE.search("your own Agent tooling") is None
    assert _BANNED_PHRASE_RE.search("dispatched via the Agent tool") is not None
    assert _BANNED_PHRASE_RE.search("launched via Agent-tools") is not None
