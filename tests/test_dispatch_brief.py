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


# ---------------------------------------------------------------------------
# CS-C11a prerequisite 1/4: every odoo-ai-agents agent/skill that names a
# git-tracked write target (a .po/.pot/.py/.xml/.js/.scss/.rst file, or the
# static/description/ icon path) must carry WORKTREE_PATH (field 5 above) -
# otherwise a separate agent context that does not inherit the caller's cwd
# writes to whatever checkout happens to be ambient.
# ---------------------------------------------------------------------------

ODOO_SKILLS_DIR = REPO_ROOT / "plugins" / "odoo-ai-agents" / "skills"
ODOO_SKILL_MD_FILES = sorted(ODOO_SKILLS_DIR.glob("*/SKILL.md"))

# Small, declared extension set: a file "names a git-tracked write target" when
# its FRONTMATTER (the block between the two `---` delimiters - a section
# boundary, not a bare sentence) names one of these as something it writes.
_GIT_TRACKED_WRITE_EXT_PATTERN = re.compile(r"\.(?:pot|po|py|xml|js|scss|rst)\b")
_STATIC_DESCRIPTION_TARGET = "static/description/"


def _frontmatter_block(text: str) -> str:
    """Return the YAML frontmatter body (between the first two `---` lines)."""
    lines = text.splitlines()
    delims = [i for i, l in enumerate(lines) if l.strip() == "---"]
    if len(delims) >= 2:
        return "\n".join(lines[delims[0] + 1: delims[1]])
    return ""


def _names_git_tracked_write_target(path: Path) -> bool:
    fm = _frontmatter_block(path.read_text(encoding="utf-8"))
    return bool(_GIT_TRACKED_WRITE_EXT_PATTERN.search(fm)) or (_STATIC_DESCRIPTION_TARGET in fm)


def test_worktree_path_subject_files_discovered():
    assert len(ODOO_SKILL_MD_FILES) >= 40, (
        f"expected at least 40 plugins/odoo-ai-agents/skills/*/SKILL.md files, "
        f"found {len(ODOO_SKILL_MD_FILES)} - glob is wrong or skills went missing"
    )


# Known-red, SHRINK-ONLY. Each entry is a file whose frontmatter names a
# git-tracked write target (.po/.pot/.py/.xml/.js/.scss/.rst/static/description/)
# without carrying WORKTREE_PATH (snippets/dispatch-brief.md field 5). odoo-i18n +
# odoo-translator were fixed first because the i18n mandate required it; every
# remaining entry (the same violation in flows the mandate did not touch) has
# since been threaded through and closed - see each file's own WORKTREE_PATH
# wiring for the receiving dispatcher and, where a file merely NAMED a target in
# prose without writing one (a frontmatter false-positive), the citation
# explaining why no field applies. Stays EMPTY: a future git-tracked writer
# that ships without WORKTREE_PATH must fail test_git_tracked_writers_carry_worktree_path
# rather than being silently re-added here.
_MISSING_WORKTREE_PATH_ALLOWLIST = set()

_ODOO_AI_AGENTS_ROOT = REPO_ROOT / "plugins" / "odoo-ai-agents"


def test_git_tracked_writers_carry_worktree_path():
    """Every agent/skill whose frontmatter names a git-tracked write target must
    carry the literal `WORKTREE_PATH` token, unless it is in the shrink-only
    known-red allowlist below.

    Red today (pre-CS-C11a) on `skills/odoo-i18n/SKILL.md` and
    `agents/odoo-translator.md` - both verified at ZERO case-insensitive
    `worktree` occurrences: `.po`/`.pot` files are git-tracked and
    `odoo-translator` is a separate agent context that does not inherit the
    caller's cwd, so a translation write silently landed in whatever checkout
    was ambient.
    """
    subjects = ODOO_AGENT_FILES + ODOO_SKILL_MD_FILES
    failures = []
    for f in subjects:
        if not _names_git_tracked_write_target(f):
            continue
        rel = str(f.relative_to(_ODOO_AI_AGENTS_ROOT))
        if "WORKTREE_PATH" in f.read_text(encoding="utf-8"):
            continue
        if rel in _MISSING_WORKTREE_PATH_ALLOWLIST:
            continue
        failures.append(rel)

    assert not failures, (
        "these files name a git-tracked write target "
        "(.po/.pot/.py/.xml/.js/.scss/.rst/static/description/) in their frontmatter "
        "but do not carry WORKTREE_PATH, and are not in the known-red allowlist - either "
        "add WORKTREE_PATH per snippets/dispatch-brief.md field 5, or add the file to "
        f"_MISSING_WORKTREE_PATH_ALLOWLIST with a reason: {failures}"
    )

    # The allowlist is SHRINK-ONLY BY ASSERTION, not by comment: every entry must
    # still LACK WORKTREE_PATH. A file that gains the token must be removed from
    # the list or this reddens - the list can only shrink, never grow silently.
    for rel in sorted(_MISSING_WORKTREE_PATH_ALLOWLIST):
        f = _ODOO_AI_AGENTS_ROOT / rel
        assert f.exists(), f"_MISSING_WORKTREE_PATH_ALLOWLIST entry {rel!r} does not exist on disk"
        assert "WORKTREE_PATH" not in f.read_text(encoding="utf-8"), (
            f"{rel} now carries WORKTREE_PATH - remove it from "
            "_MISSING_WORKTREE_PATH_ALLOWLIST (shrink-only: an entry that gains the token "
            "must be removed, never silently kept)"
        )

    # The two files THIS commit fixes can never be quietly re-admitted.
    assert "skills/odoo-i18n/SKILL.md" not in _MISSING_WORKTREE_PATH_ALLOWLIST
    assert "agents/odoo-translator.md" not in _MISSING_WORKTREE_PATH_ALLOWLIST


# ---------------------------------------------------------------------------
# SELF_PROVISION: worktree-addons carve-out field.
#
# instance-handle-contract.md's Worktree-addons carve-out treats
# `SELF_PROVISION: worktree-addons` as load-bearing: a brief carrying it
# authorizes the per-module coordinator (odoo-coder) to self-provision even
# though it may look like it "received no handle"; a brief carrying BOTH
# `INSTANCE_HANDLE` and the token is explicitly "malformed" per that contract.
# dispatch-brief.md brands itself the SSOT for the CALLER-side brief - a
# caller reading only the SSOT must be told to emit this field, and
# odoo-coder's own self-check (copied from the SSOT's SPAWNER template) must
# validate it before dispatching a leaf on a brief whose SELF_PROVISION/
# INSTANCE_HANDLE combination is malformed - otherwise the coordinator
# silently takes the wrong branch instead of surfacing the gap.
# ---------------------------------------------------------------------------

_SELF_PROVISION_TOKEN = "SELF_PROVISION: worktree-addons"


def _section(text, start_heading, end_heading=None):
    """Return text from start_heading (inclusive) up to end_heading (exclusive),
    or to EOF when end_heading is None/not found after start_heading."""
    start = text.index(start_heading)
    if end_heading is not None:
        try:
            end = text.index(end_heading, start + len(start_heading))
            return text[start:end]
        except ValueError:
            pass
    return text[start:]


def test_dispatch_brief_coder_family_declares_self_provision():
    text = DISPATCH_BRIEF.read_text(encoding="utf-8")
    coder_section = _section(text, "### Coder", "### Reviewer / auditor")
    # Whitespace-normalize before the literal-presence check so a line-wrap
    # inside the token cannot produce a false pass/fail on either side.
    normalized = " ".join(coder_section.split())
    assert _SELF_PROVISION_TOKEN in normalized, (
        "dispatch-brief.md's Coder family delta (the file brands itself THE "
        f"SSOT for the caller-side brief) must declare the exact token "
        f"{_SELF_PROVISION_TOKEN!r} - a caller reading only the SSOT would "
        "not otherwise know to emit it (see instance-handle-contract.md "
        "§ Worktree-addons carve-out)"
    )


def test_dispatch_brief_spawner_self_check_validates_self_provision():
    text = DISPATCH_BRIEF.read_text(encoding="utf-8")
    spawner_section = _section(text, "### SPAWNER variant", "## How a caller uses it")
    normalized = " ".join(spawner_section.split())
    assert "SELF_PROVISION" in normalized, (
        "dispatch-brief.md's SPAWNER self-check template (copied verbatim into "
        "odoo-coder.md's own '## Brief self-check') must validate "
        "SELF_PROVISION alongside INSTANCE_HANDLE - otherwise a brief carrying "
        "BOTH fields (malformed per instance-handle-contract.md) is never "
        "caught by the template's own gate"
    )


def test_odoo_coder_brief_self_check_validates_self_provision():
    odoo_coder = ODOO_AGENTS_DIR / "odoo-coder.md"
    text = odoo_coder.read_text(encoding="utf-8")
    self_check_section = _section(text, "## Brief self-check")
    normalized = " ".join(self_check_section.split())
    assert _SELF_PROVISION_TOKEN in normalized, (
        "odoo-coder.md's OWN '## Brief self-check' section must validate the "
        f"exact token {_SELF_PROVISION_TOKEN!r} - its 'Own the integrated "
        "module verification' section a few lines earlier in the SAME file "
        "keys directly on this field as load-bearing logic, so a malformed "
        "brief must be caught by this self-check gate, not silently take the "
        "wrong branch"
    )
