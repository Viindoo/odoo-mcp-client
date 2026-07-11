"""Guard the caller-side dispatch-brief system introduced alongside
`snippets/dispatch-brief.md`.

Mirrors the grep-the-prose idiom of `tests/test_agent_body_convention.py`:
plain-text assertions over the Markdown body, no YAML/frontmatter parsing.

Protects:
  - The two new SSOT snippets exist and are ASCII-hyphen clean (ETHOS #0).
  - Every `odoo-ai-agents` agent carries a `## Brief self-check` heading that
    points back at `dispatch-brief.md` and uses the `NEEDS_CONTEXT`/`BLOCKED`
    status vocabulary (see `dispatch-brief.md`'s LEAF variant).
  - `odoo-coder` - the one per-module COORDINATOR/spawner in the plugin - uses
    the SPAWNER framing instead: it must NOT carry the leaf-only literal
    "STOP and return `NEEDS_CONTEXT`" wording, and must instruct re-briefing
    the leaves it dispatches.
  - Every `git-toolkit` agent carries its OWN `## Brief self-check` pointing at
    `git-nesting-protocol.md`, and NEVER references `dispatch-brief.md` - the
    two plugins are independent (`git-toolkit` cannot depend on
    `odoo-ai-agents`; see `tests/test_git_toolkit_independence.py`).
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

ODOO_AGENTS_DIR = REPO_ROOT / "plugins" / "odoo-ai-agents" / "agents"
GIT_TOOLKIT_AGENTS_DIR = REPO_ROOT / "plugins" / "git-toolkit" / "agents"

ODOO_AGENT_FILES = sorted(ODOO_AGENTS_DIR.glob("*.md"))
GIT_TOOLKIT_AGENT_FILES = sorted(GIT_TOOLKIT_AGENTS_DIR.glob("*.md"))

DISPATCH_BRIEF = (
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "snippets" / "dispatch-brief.md"
)
REVIEW_SEVERITY_RUBRIC = (
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "snippets" / "review-severity-rubric.md"
)

_BRIEF_SELF_CHECK_HEADING = re.compile(r"^##\s+Brief self-check\s*$", re.MULTILINE)
# figure dash U+2012, en dash U+2013, em dash U+2014, horizontal bar U+2015
_BANNED_UNICODE_DASH = re.compile(r"[‒–—―]")
_NEEDS_CONTEXT_OR_BLOCKED = re.compile(r"NEEDS_CONTEXT|BLOCKED")
# The leaf-only literal clause from dispatch-brief.md's LEAF variant, tolerant
# of the Markdown line-wrap between "STOP and" and "return `NEEDS_CONTEXT...`".
_LEAF_STOP_AND_RETURN_NEEDS_CONTEXT = re.compile(
    r"STOP and\s+return\s+`NEEDS_CONTEXT"
)
_RE_BRIEF = re.compile(r"re-brief", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Discovery floors - the same failure mode as a vacuous parametrize.
# ---------------------------------------------------------------------------


def test_odoo_agent_files_discovered():
    assert len(ODOO_AGENT_FILES) >= 26, (
        f"expected at least 26 plugins/odoo-ai-agents/agents/*.md files, "
        f"found {len(ODOO_AGENT_FILES)} - glob is wrong or agents went missing"
    )


def test_git_toolkit_agent_files_discovered():
    assert len(GIT_TOOLKIT_AGENT_FILES) >= 4, (
        f"expected at least 4 plugins/git-toolkit/agents/*.md files, "
        f"found {len(GIT_TOOLKIT_AGENT_FILES)} - glob is wrong or agents went missing"
    )


# ---------------------------------------------------------------------------
# The two new SSOT snippets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "snippet", [DISPATCH_BRIEF, REVIEW_SEVERITY_RUBRIC], ids=lambda p: p.name
)
def test_snippet_exists_and_non_empty(snippet):
    assert snippet.exists(), f"{snippet} does not exist"
    assert snippet.stat().st_size > 0, f"{snippet} is empty"


@pytest.mark.parametrize(
    "snippet", [DISPATCH_BRIEF, REVIEW_SEVERITY_RUBRIC], ids=lambda p: p.name
)
def test_snippet_is_ascii_hyphen_clean(snippet):
    text = snippet.read_text(encoding="utf-8")
    match = _BANNED_UNICODE_DASH.search(text)
    assert match is None, (
        f"{snippet.name}: banned Unicode dash {match.group()!r} found - use the "
        "ASCII hyphen '-' per ODOO-AI-ETHOS #0"
    )


# ---------------------------------------------------------------------------
# Every odoo-ai-agents agent carries the LEAF (or SPAWNER) brief self-check
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "agent", ODOO_AGENT_FILES, ids=lambda p: p.stem
)
def test_odoo_agent_has_brief_self_check_heading(agent):
    text = agent.read_text(encoding="utf-8")
    assert _BRIEF_SELF_CHECK_HEADING.search(text), (
        f"{agent.relative_to(REPO_ROOT)}: missing a `## Brief self-check` "
        "heading - every odoo-ai-agents agent must self-check its inbound "
        "dispatch brief per snippets/dispatch-brief.md"
    )


@pytest.mark.parametrize(
    "agent", ODOO_AGENT_FILES, ids=lambda p: p.stem
)
def test_odoo_agent_references_dispatch_brief(agent):
    text = agent.read_text(encoding="utf-8")
    assert "dispatch-brief.md" in text, (
        f"{agent.relative_to(REPO_ROOT)}: does not reference `dispatch-brief.md` "
        "- the caller-side schema it self-checks against"
    )


@pytest.mark.parametrize(
    "agent", ODOO_AGENT_FILES, ids=lambda p: p.stem
)
def test_odoo_agent_uses_needs_context_or_blocked_vocabulary(agent):
    text = agent.read_text(encoding="utf-8")
    assert _NEEDS_CONTEXT_OR_BLOCKED.search(text), (
        f"{agent.relative_to(REPO_ROOT)}: does not use `NEEDS_CONTEXT` or "
        "`BLOCKED` anywhere - a brief self-check with no escalation status is "
        "not enforceable"
    )


# ---------------------------------------------------------------------------
# odoo-coder is the one SPAWNER, not a leaf - it must use the spawner framing
# ---------------------------------------------------------------------------


def test_odoo_coder_uses_spawner_framing_not_leaf_stop_clause():
    odoo_coder = ODOO_AGENTS_DIR / "odoo-coder.md"
    assert odoo_coder.exists(), f"{odoo_coder} not found"
    text = odoo_coder.read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", text)
    assert not _LEAF_STOP_AND_RETURN_NEEDS_CONTEXT.search(normalized), (
        "odoo-coder.md is a per-module COORDINATOR/spawner (worker-brief.md "
        "exempts it from the hard-leaf contract) - it must NOT carry the "
        "leaf-only literal 'STOP and return `NEEDS_CONTEXT`' clause verbatim; "
        "that phrasing belongs to a leaf with no one left to re-brief"
    )


def test_odoo_coder_instructs_rebriefing_its_leaves():
    odoo_coder = ODOO_AGENTS_DIR / "odoo-coder.md"
    text = odoo_coder.read_text(encoding="utf-8")
    assert _RE_BRIEF.search(text), (
        "odoo-coder.md must instruct RE-BRIEFING each leaf it dispatches "
        "(odoo-test-writer, odoo-backend-coder, odoo-frontend-coder) by reading "
        "dispatch-brief.md BY PATH, per the SPAWNER variant in "
        "snippets/dispatch-brief.md - found no 're-brief' mention"
    )


# ---------------------------------------------------------------------------
# git-toolkit agents: own brief self-check, NEVER dispatch-brief.md
# (cross-plugin boundary: git-toolkit cannot depend on odoo-ai-agents)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "agent", GIT_TOOLKIT_AGENT_FILES, ids=lambda p: p.stem
)
def test_git_toolkit_agent_has_brief_self_check_heading(agent):
    text = agent.read_text(encoding="utf-8")
    assert _BRIEF_SELF_CHECK_HEADING.search(text), (
        f"{agent.relative_to(REPO_ROOT)}: missing a `## Brief self-check` "
        "heading"
    )


@pytest.mark.parametrize(
    "agent", GIT_TOOLKIT_AGENT_FILES, ids=lambda p: p.stem
)
def test_git_toolkit_agent_references_git_nesting_protocol(agent):
    text = agent.read_text(encoding="utf-8")
    assert "git-nesting-protocol.md" in text, (
        f"{agent.relative_to(REPO_ROOT)}: `## Brief self-check` must reference "
        "git-nesting-protocol.md (git-toolkit's own caller-side schema, "
        "independent of odoo-ai-agents' dispatch-brief.md)"
    )


@pytest.mark.parametrize(
    "agent", GIT_TOOLKIT_AGENT_FILES, ids=lambda p: p.stem
)
def test_git_toolkit_agent_never_references_dispatch_brief(agent):
    text = agent.read_text(encoding="utf-8")
    assert "dispatch-brief.md" not in text, (
        f"{agent.relative_to(REPO_ROOT)}: references `dispatch-brief.md`, an "
        "odoo-ai-agents-only snippet - git-toolkit is domain-agnostic and must "
        "not depend on odoo-ai-agents (see tests/test_git_toolkit_independence.py)"
    )
