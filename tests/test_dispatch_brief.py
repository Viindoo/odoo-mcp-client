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


# ---------------------------------------------------------------------------
# B4 - SURVEY field reachability. Before this fix, the literal token `SURVEY`
# appeared 0 times in dispatch-brief.md: absent from field 4 INPUTS's
# canonical reuse-key list, absent from the Coder family delta, and absent
# from all 3 Coder-family `## Brief self-check` sections. A brief carrying
# `INPUTS: DESIGN_DOC=...` (every OTHER field present) passed every checked
# gate while silently dropping deep-survey findings a human handed over -
# the caller had no textual reason to know the field even existed.
# ---------------------------------------------------------------------------

_SURVEY_TOKEN = "SURVEY"


def test_dispatch_brief_inputs_row_names_survey():
    text = DISPATCH_BRIEF.read_text(encoding="utf-8")
    inputs_rows = [
        line for line in text.splitlines() if line.startswith("| 4 | `INPUTS`")
    ]
    assert inputs_rows, "dispatch-brief.md: field 4 `INPUTS` row not found"
    assert _SURVEY_TOKEN in inputs_rows[0], (
        "dispatch-brief.md field 4 (INPUTS) must reuse the literal `SURVEY` "
        "key name in its canonical key-name list - a caller reading only "
        "the universal skeleton must learn deep-survey findings have a "
        "named home, the same way DESIGN_DOC/GAP_MATRIX/ORACLE_PATH already do"
    )


def test_dispatch_brief_coder_family_declares_survey():
    text = DISPATCH_BRIEF.read_text(encoding="utf-8")
    coder_section = _section(text, "### Coder", "### Reviewer / auditor")
    assert _SURVEY_TOKEN in coder_section, (
        "dispatch-brief.md's Coder family delta must declare `SURVEY` as a "
        "required field carrying the same 'key must be present even at its "
        "safe value' rule as skeleton field 4 INPUTS - otherwise a "
        "Coder-family brief can silently drop the deep-survey pointer and "
        "pass every checked gate clean (the exact R4 symptom)"
    )


@pytest.mark.parametrize(
    "agent_name", ["odoo-coder.md", "odoo-backend-coder.md", "odoo-frontend-coder.md"]
)
def test_coder_family_brief_self_check_requires_survey(agent_name):
    agent = ODOO_AGENTS_DIR / agent_name
    text = agent.read_text(encoding="utf-8")
    self_check_section = _section(text, "## Brief self-check")
    assert _SURVEY_TOKEN in self_check_section, (
        f"{agent_name}: '## Brief self-check' must check for `SURVEY` (the "
        "deep-survey findings pointer) both in its required-field list and "
        "its missing-field STOP/NEEDS_CONTEXT clause - before this fix none "
        "of the Coder-family self-checks caught a brief that silently "
        "omitted the field entirely"
    )


# ---------------------------------------------------------------------------
# Cross-group registration - GATE_ROLE (pre-pr-lint-gate | per-module-verify)
# was wired into odoo-instance-ops.md's lint-union enforcement point and
# odoo-coder.md's dispatch branches by another fix group this round, but was
# never registered in dispatch-brief.md - a caller reading only the
# caller-side SSOT skeleton would not learn the obligation exists.
# ---------------------------------------------------------------------------


def test_dispatch_brief_instance_ops_family_declares_gate_role():
    text = DISPATCH_BRIEF.read_text(encoding="utf-8")
    instance_section = _section(text, "### Instance / ops", "### Survey / analyst")
    assert "GATE_ROLE" in instance_section, (
        "dispatch-brief.md's Instance/ops family delta must register "
        "`GATE_ROLE` (pre-pr-lint-gate | per-module-verify) - it is a "
        "load-bearing field with no safe default, enforced in "
        "odoo-instance-ops.md, but was never surfaced in the caller-side SSOT"
    )


# ---------------------------------------------------------------------------
# P4 - the worker brief carries no reply-address key at all. Earlier
# revisions argued about WHEN such a key applied; the key itself is what a
# leaf cannot use, since a leaf launches nothing and therefore holds no
# address of any kind.
# ---------------------------------------------------------------------------

WORKER_BRIEF = (
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "snippets" / "worker-brief.md"
)


def test_worker_brief_carries_no_reply_address_key():
    text = WORKER_BRIEF.read_text(encoding="utf-8")
    for banned in ("REPLY_TO", "CALLER_ID", "TASK_ID", "NOTIFY"):
        assert banned not in text, (
            f"worker-brief.md must not name {banned} - a leaf launches nothing, so it holds no "
            "send target and no reply address can be supplied to it"
        )
    low = " ".join(text.split()).lower()
    assert "you hold no legal send target at all" in low, (
        "worker-brief.md must state the absence POSITIVELY, or the next author re-adds the key"
    )


# ---------------------------------------------------------------------------
# P5 - Survey/analyst family must carry the Continuation Contract (ODOO-AI-
# ETHOS #10 always-on 3-part report + explicit "waiting" ban), same as the
# other 21 agents in the plugin. Before this fix, 5/26 agents (this family)
# used an ad hoc "Return..." format with neither the always-on report shape
# nor the generic banned-phrase enumeration.
# ---------------------------------------------------------------------------

SURVEY_ANALYST_FAMILY = [
    "odoo-backend-debugger.md",
    "odoo-ui-debugger.md",
    "odoo-review-scoper.md",
    "odoo-intent-extractor.md",
    "odoo-installable-prober.md",
    "odoo-gap-analyzer.md",
    "odoo-feature-cataloger.md",
    "odoo-doc-scoper.md",
]

# SHRINK-ONLY allowlist, now EMPTY: odoo-intent-extractor.md was initially
# excluded here (owned by another fix group this round, actively editing the
# same file for an unrelated SLUG defect at the time this test was first
# written) but was wired into the Continuation Contract once that other
# group's edit landed - see the F3 fix report. Stays empty: a future
# Survey/analyst-family agent that ships without continuation-contract.md
# must fail test_survey_analyst_family_carries_continuation_contract rather
# than being silently re-added here.
_MISSING_CONTINUATION_CONTRACT_ALLOWLIST = set()


@pytest.mark.parametrize("agent_name", SURVEY_ANALYST_FAMILY)
def test_survey_analyst_family_carries_continuation_contract(agent_name):
    agent = ODOO_AGENTS_DIR / agent_name
    assert agent.exists(), f"{agent} not found"
    if agent_name in _MISSING_CONTINUATION_CONTRACT_ALLOWLIST:
        pytest.skip(f"{agent_name}: known-red, owned by another fix group this round")
    text = agent.read_text(encoding="utf-8")
    assert "continuation-contract.md" in text, (
        f"{agent_name}: Survey/analyst family member must reference "
        "continuation-contract.md (the ALWAYS-ON 3-part report + explicit "
        "'waiting' ban) - the same contract the other 21 agents in the "
        "plugin already carry"
    )


# ---------------------------------------------------------------------------
# P4 residual - concrete agent-dispatch brief TEMPLATES (not just the generic
# "read dispatch-brief.md by path" instruction) must include the CALLER_ID
# (REPLY_TO) field literal, matching the established correct pattern in
# odoo-forward-port/references/fp-phase-detail.md. Before this fix, 5 of 6
# concrete agent-targeting templates across 4 skill files omitted it entirely
# even though their parent skill's generic dispatch instruction already
# points at dispatch-brief.md (field 11 is ALWAYS) - the gap was in the
# filled-in example a caller actually copies values into, not in the generic
# pointer sentence. Skill-to-skill (not skill-to-agent) templates are
# intentionally excluded: dispatch-brief.md's own skeleton is scoped to "a
# spawner ... dispatches a specialist agent", not a Skill-tool invocation of
# another skill (odoo-git-rebase's odoo-coding template, odoo-modules-
# upgrade's odoo-instance/odoo-i18n templates) - adding CALLER_ID there would
# be a scope-violating misapplication, not a genuine fix.
# ---------------------------------------------------------------------------

_AGENT_DISPATCH_TEMPLATE_FILES = [
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "skills" / "odoo-coding" / "SKILL.md",
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "skills" / "odoo-doc-illustration" / "SKILL.md",
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "skills" / "odoo-icon-design" / "SKILL.md",
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "skills" / "odoo-instance" / "SKILL.md",
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "skills" / "odoo-forward-port" / "references" / "fp-phase-detail.md",
]


@pytest.mark.parametrize("path", _AGENT_DISPATCH_TEMPLATE_FILES, ids=lambda p: p.name)
def test_agent_dispatch_template_carries_no_caller_id(path):
    """A filled-in template is what a caller actually copies, so a retired field surviving there
    re-seeds it even after the schema drops it. These five files carried the field literal."""
    assert path.exists(), f"{path} not found"
    text = path.read_text(encoding="utf-8")
    for banned in ("CALLER_ID", "REPLY_TO"):
        assert banned not in text, (
            f"{path.relative_to(REPO_ROOT)}: a concrete agent-dispatch brief template in this "
            f"file still carries {banned!r}. No brief carries a reply address - the dispatched "
            "agent's report is its final message (spawner-completion-contract.md R3)."
        )


def test_missing_continuation_contract_allowlist_is_shrink_only():
    for agent_name in sorted(_MISSING_CONTINUATION_CONTRACT_ALLOWLIST):
        agent = ODOO_AGENTS_DIR / agent_name
        assert agent.exists(), f"{agent_name} does not exist"
        text = agent.read_text(encoding="utf-8")
        assert "continuation-contract.md" not in text, (
            f"{agent_name} now references continuation-contract.md - remove "
            "it from _MISSING_CONTINUATION_CONTRACT_ALLOWLIST (shrink-only: "
            "an entry that gains the reference must be removed, never "
            "silently kept)"
        )


# ---------------------------------------------------------------------------
# M4 - Resolved-value dispatch. dispatch-brief.md field 11 (CALLER_ID/
# REPLY_TO) becomes an address grammar (an ADDRESS, never a name/pointer),
# and a new "Two rules that decide whether the brief works" section is added.
# Guards `12-design-final.md` § M4.
# ---------------------------------------------------------------------------


def test_dispatch_brief_skeleton_ends_at_field_10():
    """The skeleton table must stop at field 10. An eleventh row is, by construction, the retired
    reply-address field coming back under some name - there is no other candidate."""
    text = DISPATCH_BRIEF.read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if re.match(r"^\| 11 \|", line)]
    assert not rows, (
        f"dispatch-brief.md: the universal skeleton must stop at field 10, found: {rows}"
    )
    assert "| 10 | `RETURN_BUDGET`" in text, (
        "sanity: field 10 (RETURN_BUDGET) must still be the last skeleton row"
    )


def test_dispatch_brief_has_two_rules_section():
    text = DISPATCH_BRIEF.read_text(encoding="utf-8")
    assert "## Two rules that decide whether the brief works" in text, (
        "dispatch-brief.md must carry the '## Two rules that decide whether "
        "the brief works' section (resolved-value fields + one-dispatch-one-"
        "kind) - M4's mechanical companion to the field-11 address grammar"
    )
    two_rules = _section(
        text,
        "## Two rules that decide whether the brief works",
        "## Role-family deltas",
    )
    assert "Every field carries a resolved VALUE" in two_rules, (
        "dispatch-brief.md's two-rules section must state the resolved-value "
        "rule verbatim"
    )
    assert "One dispatch, one KIND of work" in two_rules, (
        "dispatch-brief.md's two-rules section must state the one-kind-per-"
        "dispatch rule verbatim"
    )
    assert "MUST NOT re-run the resolver" in two_rules, (
        "dispatch-brief.md's two-rules section must forbid a worker handed a "
        "resolved value from re-running the resolver itself"
    )


# ---------------------------------------------------------------------------
# M4 - odoo-instance/SKILL.md's brief block must carry only resolved values,
# never a "go read this document / call this procedure" field. Before this
# fix, `INSTANCE_RESOLUTION: follow instance-resolution.md` sent the
# dispatched odoo-instance-ops agent to re-derive a procedure its own body
# already fully implements (Steps A-D) - a hidden sub-task, and a duplicate
# SSOT. Guards `12-design-final.md` § M4 mechanical guard `[brief-values]`.
# ---------------------------------------------------------------------------

ODOO_INSTANCE_SKILL = (
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "skills" / "odoo-instance" / "SKILL.md"
)

_PROCEDURAL_FIELD_VALUE = re.compile(
    r"^([A-Z][A-Z0-9_ ]*)\s*(?:\([^)]*\))?\s*:\s*(follow|call|resolve|per)\s",
    re.IGNORECASE,
)


def _instance_brief_fence(text):
    marker = "The brief must include:\n\n```\n"
    start = text.index(marker) + len(marker)
    end = text.index("\n```", start)
    return text[start:end]


def test_odoo_instance_brief_fence_is_discovered():
    text = ODOO_INSTANCE_SKILL.read_text(encoding="utf-8")
    fence = _instance_brief_fence(text)
    assert "OPERATION:" in fence and "WORKTREE_PATH:" in fence, (
        "odoo-instance/SKILL.md: could not locate the dispatch-brief fenced "
        "field block (expected it to start at OPERATION: and include "
        "WORKTREE_PATH) - the extraction anchor drifted"
    )


def test_no_procedural_field_values_in_instance_brief():
    text = ODOO_INSTANCE_SKILL.read_text(encoding="utf-8")
    fence = _instance_brief_fence(text)
    hits = [
        line for line in fence.splitlines() if _PROCEDURAL_FIELD_VALUE.match(line)
    ]
    assert not hits, (
        "odoo-instance/SKILL.md's dispatch-brief field block hands the "
        "dispatched agent a field whose value begins 'follow '/'call '/"
        "'resolve '/'per ' - a hidden sub-task the worker must resolve "
        "itself instead of a resolved value the caller already supplied "
        f"(M4 two-rules section, dispatch-brief.md): {hits}"
    )


# ---------------------------------------------------------------------------
# M4 - INSTANCE_HANDLE field names. instance-handle-contract.md is the SSOT
# for the fields an INSTANCE_HANDLE carries; agents/odoo-instance-ops.md's
# canonical `instance-ops` output block is the actual PRODUCER. The contract
# must declare `db_name`/`venv_python`, matching the producer's actual field
# names - `db_name` because that is Odoo's own spelling (odoo.conf's
# `db_name =` key, the `--db_host`/`--db_port`/`--db_user` CLI flags; Odoo
# never spells this `dbname`) - and every producer field describing the ONE
# live instance must be documented in the contract, and vice versa.
# Data-driven both directions, scoped to the fields that describe the ONE
# live instance (never the per-operation-only fields: op, series,
# modules_installed, failed, errors, warnings, skipped, findings_path,
# status, notes - those are not part of the handle abstraction).
# ---------------------------------------------------------------------------

INSTANCE_HANDLE_CONTRACT = (
    REPO_ROOT / "plugins" / "odoo-ai-agents" / "snippets" / "instance-handle-contract.md"
)
ODOO_INSTANCE_OPS_AGENT = ODOO_AGENTS_DIR / "odoo-instance-ops.md"

_OPERATION_SCOPED_PRODUCER_FIELDS = {
    "op",
    "series",
    "modules_installed",
    "failed",
    "errors",
    "warnings",
    "skipped",
    "findings_path",
    "status",
    "notes",
}


def _contract_field_names(text):
    section = text[text.index("carries exactly:"): text.index("## Provision once, forward everywhere")]
    return set(re.findall(r"^-\s+`([a-z_]+)`", section, re.MULTILINE))


def _producer_canonical_field_names(text):
    match = re.search(r"```instance-ops\n(.*?)\n```", text, re.DOTALL)
    assert match, "agents/odoo-instance-ops.md: canonical `instance-ops` output block not found"
    return set(re.findall(r"^(\w+):", match.group(1), re.MULTILINE))


def test_instance_handle_field_names_match_producers():
    contract_fields = _contract_field_names(
        INSTANCE_HANDLE_CONTRACT.read_text(encoding="utf-8")
    )
    producer_fields = _producer_canonical_field_names(
        ODOO_INSTANCE_OPS_AGENT.read_text(encoding="utf-8")
    )
    handle_producer_fields = producer_fields - _OPERATION_SCOPED_PRODUCER_FIELDS

    missing_from_producer = contract_fields - producer_fields
    assert not missing_from_producer, (
        "instance-handle-contract.md promises field(s) the producer "
        f"(agents/odoo-instance-ops.md canonical output block) never emits: "
        f"{sorted(missing_from_producer)}"
    )

    undocumented_in_contract = handle_producer_fields - contract_fields
    assert not undocumented_in_contract, (
        "agents/odoo-instance-ops.md's canonical output block emits "
        "instance-describing field(s) instance-handle-contract.md never "
        f"documents: {sorted(undocumented_in_contract)}"
    )

    assert "db_name" in contract_fields and "dbname" not in contract_fields, (
        "instance-handle-contract.md must declare `db_name` (the producer's "
        "actual field name, and Odoo's own spelling), not the stale `dbname`"
    )
    assert "venv_python" in contract_fields and "venv" not in contract_fields, (
        "instance-handle-contract.md must declare `venv_python` (the "
        "producer's actual field name), not the stale `venv`"
    )


# ---------------------------------------------------------------------------
# M4 - "Isolation, not exclusivity" (X-16, stated not mechanically provable):
# instance-handle-contract.md must never instruct a worker to wait for a
# resource another session owns.
# ---------------------------------------------------------------------------


def test_instance_handle_contract_states_isolation_not_exclusivity():
    text = INSTANCE_HANDLE_CONTRACT.read_text(encoding="utf-8")
    normalized = " ".join(text.split())
    assert "Isolation, not exclusivity." in normalized, (
        "instance-handle-contract.md must carry the 'Isolation, not "
        "exclusivity' principle verbatim (M4, X-16)"
    )
    assert (
        "Never instruct a worker to wait for a resource another session owns"
        in normalized
    ), (
        "instance-handle-contract.md's 'Isolation, not exclusivity' principle "
        "must forbid instructing a worker to wait for a resource another "
        "session owns - give it a distinct port/database/config/log instead"
    )
