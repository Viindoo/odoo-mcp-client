"""Behavioral guard for change-group P2 - browser evidence must never land in the working
directory (root-cause: `odoo-qa-tester`/`odoo-ui-debugger` ordered a capture with NO destination,
and where a destination WAS named, the parameter key was wrong - `path`/`filename` instead of the
chrome-devtools `filePath`, silently swallowed by the schema's `additionalProperties: true`).

This file protects the BEHAVIOR the fix establishes, not the exact wording of any one edit:
- both evidence-producing leaves (`odoo-qa-tester`, `odoo-ui-debugger`) name a citable ISOLATE
  subpath for every artifact they capture;
- every dispatcher that fans out to one of those leaves (or to `odoo-ui-reviewer`) threads
  `ISOLATE_DIR` so the leaf never re-resolves from a possibly-wrong cwd;
- every evidence-producing leaf carries an explicit never-no-destination ban;
- the SSOT (`state-root-resolution.md`) declares both new ISOLATE rows and the three-bucket
  "where a captured artifact goes" rule exactly once;
- the wrong parameter names (`take_screenshot path`, "the `path` or `filename` argument") are
  excised everywhere, replaced by the real `filePath` key;
- the committed-deliverable pipeline (icon/marketing/user-doc) is untouched by the fix - it is
  reached only via an explicit copy, per bucket 3.

Stdlib-only; reads the agent-facing Markdown as the contract surface.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

QA_TESTER = PLUGIN / "agents" / "odoo-qa-tester.md"
UI_DEBUGGER = PLUGIN / "agents" / "odoo-ui-debugger.md"
UI_REVIEWER = PLUGIN / "agents" / "odoo-ui-reviewer.md"
STATE_ROOT = PLUGIN / "snippets" / "state-root-resolution.md"
CAPTURE_MECHANICS = PLUGIN / "skills" / "odoo-doc-illustration" / "references" / "capture-mechanics.md"
USER_DOC_WRITER = PLUGIN / "agents" / "odoo-user-doc-writer.md"
MARKETING_WRITER = PLUGIN / "agents" / "odoo-marketing-writer.md"
ICON_DESIGNER = PLUGIN / "agents" / "odoo-icon-designer.md"

ACCEPTANCE_SKILL = PLUGIN / "skills" / "odoo-acceptance" / "SKILL.md"
DEBUG_SKILL = PLUGIN / "skills" / "odoo-debug" / "SKILL.md"
UPGRADE_SKILL = PLUGIN / "skills" / "odoo-modules-upgrade" / "SKILL.md"
UPGRADE_PHASE_DETAIL = PLUGIN / "skills" / "odoo-modules-upgrade" / "references" / "upg-phase-detail.md"
CODE_REVIEW_SKILL = PLUGIN / "skills" / "odoo-code-review" / "SKILL.md"
UI_REVIEW_SKILL = PLUGIN / "skills" / "odoo-ui-review" / "SKILL.md"

_WS = re.compile(r"\s+")


def _read(p: Path) -> str:
    assert p.is_file(), f"missing: {p}"
    return p.read_text(encoding="utf-8")


def _norm(text: str) -> str:
    return _WS.sub(" ", text)


def _section(text: str, start_heading: str, end_headings=("## ",)) -> str:
    """Return the slice of `text` from `start_heading` up to (excluding) the next heading."""
    start = text.index(start_heading)
    body = text[start + len(start_heading):]
    end = len(body)
    for h in end_headings:
        idx = body.find(h)
        if idx != -1:
            end = min(end, idx)
    return body[:end]


def _window_after(text: str, anchor: str, span: int = 500) -> str:
    idx = text.index(anchor)
    return text[idx: idx + len(anchor) + span]


def _count_repo(phrase: str, exts=(".md",)):
    """Return {relpath: count} for files under PLUGIN where the ws-normalized phrase occurs."""
    needle = _norm(phrase)
    hits = {}
    for p in PLUGIN.rglob("*"):
        if p.is_file() and p.suffix in exts:
            n = _norm(p.read_text(encoding="utf-8")).count(needle)
            if n:
                hits[str(p.relative_to(PLUGIN))] = n
    return hits


# ---------------------------------------------------------------------------
# Both leaves name their ISOLATE subpath
# ---------------------------------------------------------------------------

def test_qa_tester_names_its_isolate_subpath():
    text = _read(QA_TESTER)
    assert "<ISOLATE_DIR>/visual/qa/<slug>/<module>/" in text, (
        "odoo-qa-tester must write its captured evidence under "
        "<ISOLATE_DIR>/visual/qa/<slug>/<module>/"
    )


def test_ui_debugger_names_its_isolate_subpath():
    text = _read(UI_DEBUGGER)
    assert "<ISOLATE_DIR>/visual/debug/<slug>/" in text, (
        "odoo-ui-debugger must write its captured evidence under "
        "<ISOLATE_DIR>/visual/debug/<slug>/"
    )


# ---------------------------------------------------------------------------
# All five dispatchers thread ISOLATE_DIR
# ---------------------------------------------------------------------------

def test_acceptance_threads_isolate_dir_to_qa_tester():
    text = _read(ACCEPTANCE_SKILL)
    phase_2b = _section(text, "## Phase 2b", end_headings=("## Phase 3",))
    assert "odoo-qa-tester" in phase_2b
    assert "ISOLATE_DIR:" in phase_2b, (
        "odoo-acceptance Phase 2b must thread ISOLATE_DIR into both the deep and smoke "
        "odoo-qa-tester dispatches"
    )


def test_debug_threads_isolate_dir_to_ui_debugger():
    text = _read(DEBUG_SKILL)
    template = _window_after(text, "DISPATCH MODEL:", span=1200)
    assert "odoo-ui-debugger" in template
    assert "ISOLATE_DIR" in template, (
        "odoo-debug's agent dispatch template must carry an ISOLATE_DIR field for "
        "odoo-ui-debugger"
    )


def test_modules_upgrade_threads_isolate_dir_to_ui_debugger():
    skill_text = _read(UPGRADE_SKILL)
    skill_window = _window_after(skill_text, "dispatch `odoo-backend-debugger` or `odoo-ui-debugger`", span=400)
    assert "ISOLATE_DIR" in skill_window, (
        "odoo-modules-upgrade/SKILL.md's P5 failure-handling dispatch must thread ISOLATE_DIR"
    )

    detail_text = _read(UPGRADE_PHASE_DETAIL)
    detail_window = _window_after(
        detail_text, "dispatch `odoo-backend-debugger` or `odoo-ui-debugger` with the traceback", span=400
    )
    assert "ISOLATE_DIR" in detail_window, (
        "upg-phase-detail.md's P5 dependency-level failure dispatch must thread ISOLATE_DIR"
    )


def test_code_review_threads_isolate_dir_to_ui_reviewer():
    text = _read(CODE_REVIEW_SKILL)
    window = _window_after(text, "dispatch one `odoo-ui-reviewer`", span=600)
    assert "ISOLATE_DIR" in window
    # Distinguishing clause: ARTIFACT_DIR (report dir) is not the same field as ISOLATE_DIR
    # (evidence root).
    assert "ARTIFACT_DIR" in window and "ISOLATE_DIR" in window
    assert "never collapse into one field" in _norm(window) or "SEPARATE" in window, (
        "odoo-code-review must distinguish ARTIFACT_DIR (report dir) from ISOLATE_DIR "
        "(evidence root) at the ui-reviewer dispatch site"
    )


def test_ui_review_skill_threads_isolate_dir():
    text = _read(UI_REVIEW_SKILL)
    section = _section(text, "## Agent invocation", end_headings=("## Standalone-first fallback",))
    assert "ISOLATE_DIR" in section, (
        "odoo-ui-review's dedicated front door must resolve and thread ISOLATE_DIR to "
        "odoo-ui-reviewer"
    )


# ---------------------------------------------------------------------------
# Every evidence leaf carries the never-no-destination ban
# ---------------------------------------------------------------------------

def test_evidence_leaves_ban_destination_less_captures():
    for leaf in (QA_TESTER, UI_DEBUGGER, UI_REVIEWER):
        text = _norm(_read(leaf)).lower()
        assert "call a capture tool with no destination" in text, (
            f"{leaf.name} must explicitly ban calling a capture tool with no destination"
        )


# ---------------------------------------------------------------------------
# state-root-resolution.md is the SSOT for both new rows + the three-bucket rule
# ---------------------------------------------------------------------------

def test_state_root_resolution_lists_both_new_isolate_rows():
    text = _read(STATE_ROOT)
    isolate_section = _section(text, "## Tier-2 ISOLATE list", end_headings=("## Codemod guards",))
    assert "visual/qa/<slug>/<module>/" in isolate_section
    assert "visual/debug/<slug>/" in isolate_section


def test_three_bucket_section_exists():
    text = _read(STATE_ROOT)
    assert "## Where a captured artifact goes" in text
    section = _section(
        text, "## Where a captured artifact goes", end_headings=("## The resolve-capture-substitute protocol",)
    )
    assert "Reusable across runs" in section
    assert "Run-scoped" in section
    assert "committed module deliverable" in section
    # Family mechanics + refusal fallback must be present too (Decisions C/E), not just the
    # discriminator.
    assert "filePath" in section
    assert "BLOCKED(state root unresolvable" in section
    assert "inline (state root unresolvable)" in section


# ---------------------------------------------------------------------------
# Wrong parameter names excised; filePath present everywhere a capture is ordered
# ---------------------------------------------------------------------------

def test_capture_parameter_names():
    for bad_phrase in ("take_screenshot path", "the `path` or `filename` argument"):
        hits = _count_repo(bad_phrase)
        assert sum(hits.values()) == 0, (
            f"Wrong capture parameter name {bad_phrase!r} must appear ZERO times; found: {hits}"
        )

    for f in (QA_TESTER, UI_DEBUGGER, UI_REVIEWER, CAPTURE_MECHANICS, USER_DOC_WRITER, MARKETING_WRITER):
        text = _read(f)
        assert "filePath" in text, f"{f.name} must reference the real chrome-devtools key filePath"


# ---------------------------------------------------------------------------
# Committed deliverables (bucket 3) survive untouched
# ---------------------------------------------------------------------------

def test_committed_deliverables_survive():
    icon_text = _read(ICON_DESIGNER)
    assert "static/description/icon.png" in icon_text

    marketing_text = _read(MARKETING_WRITER)
    assert "static/description/index.html" in marketing_text

    user_doc_text = _read(USER_DOC_WRITER)
    assert "doc/index.rst" in user_doc_text

    state_root_text = _read(STATE_ROOT)
    bucket_section = _section(
        text=state_root_text,
        start_heading="## Where a captured artifact goes",
        end_headings=("## The resolve-capture-substitute protocol",),
    )
    assert "static/description" in bucket_section
    assert "doc/..." in bucket_section or "doc/" in bucket_section
    assert "NEVER a capture destination" in bucket_section
