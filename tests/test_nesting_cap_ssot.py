"""Guard: the platform nesting cap is stated in ONE place, and that place states what was measured.

The defect this protects against: `docs/setup.md` and `05-prereq-check.sh` said the platform depth
cap is 5 while R0 move 1 and the README said `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` defaults to 3.
Two copies of one number drifted apart, and a reader of either could not tell which was true.

What was measured (Claude Code 2.1.288, 2026-10-03), from the installed binary and a live nested
probe (`claude -p`, one recursive agent that logs whether it holds the `Agent` tool):

  * the cap is `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` when set, else a remote-config value whose
    fallback is 3 (and the cached remote value on the measuring account was 3);
  * the main conversation is depth 0, and every launched agent - a `context: fork` skill included -
    is its launcher's depth + 1; an inline skill adds none;
  * the launch tool is filtered out of an agent's toolset unless its depth is below the cap, with no
    error: the probe logged depth 1 and 2 holding it, depth 3 not; with the variable set to 2, depth
    2 no longer held it.

So the SSOT (R0 move 1 of `snippets/spawner-completion-contract.md`) must state the default, how
depth is counted, and that the tool goes silently - and no other file may restate a number for the
cap, because a restated number is the copy that rots. History (`CHANGELOG.md`) is exempt: it records
what an earlier release said.

Run: python -m pytest tests/test_nesting_cap_ssot.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
SSOT = PLUGIN / "snippets" / "spawner-completion-contract.md"

_SCANNED_SUFFIXES = {".md", ".sh", ".py", ".yaml", ".yml", ".json", ".txt"}
_SKIP_DIRS = {".git", ".venv", "node_modules", "tests", "__pycache__"}
_EXEMPT = {SSOT.resolve(), (REPO_ROOT / "CHANGELOG.md").resolve()}

# Any phrasing that names the cap: "depth cap", "nesting cap", "nesting limit", "depth-cap",
# "max depth", "spawn depth", or the variable itself. Matched case-insensitively on
# whitespace-normalized text, so a line break inside the phrase does not hide it.
_ANCHOR_RE = re.compile(
    r"depth[ -]cap|nesting[ -](?:cap|limit)|max(?:imum)?[ -](?:subagent[ -])?(?:spawn[ -])?depth|"
    r"spawn[ -]depth|SPAWN_DEPTH",
    re.I,
)
# Numbers near an anchor that are NOT a cap value: a section pointer ("R0 move 1"), a dotted
# version ("2.1.172").
_NOT_A_CAP_RE = re.compile(r"\bmove\s*\d+\b|\bR\d+\b|\b\d+(?:\.\d+)+\b", re.I)
_WINDOW = 40


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _scanned_files() -> list[Path]:
    out = []
    for p in REPO_ROOT.rglob("*"):
        if not p.is_file() or p.suffix not in _SCANNED_SUFFIXES:
            continue
        if any(part in _SKIP_DIRS for part in p.relative_to(REPO_ROOT).parts):
            continue
        if p.resolve() in _EXEMPT:
            continue
        out.append(p)
    return out


def test_scan_corpus_is_not_empty_and_reaches_the_files_that_drifted():
    """A walk that silently skipped the plugin tree would make the restatement check vacuous."""
    files = {p.relative_to(REPO_ROOT).as_posix() for p in _scanned_files()}
    for must in (
        "plugins/odoo-ai-agents/docs/setup.md",
        "plugins/odoo-ai-agents/scripts/setup-steps/05-prereq-check.sh",
        "plugins/odoo-ai-agents/README.md",
        "plugins/odoo-ai-agents/snippets/context-handoff-protocol.md",
        "plugins/odoo-ai-agents/docs/reference/workflow-harness.md",
    ):
        assert must in files, f"the restatement scan no longer reaches {must}"


def test_r0_move_1_states_the_measured_cap_and_how_depth_is_counted():
    text = _norm(SSOT.read_text(encoding="utf-8"))
    start = text.index("**Move 1 - NO agent-launch capability**")
    move1 = text[start : text.index("**Move 2", start)]
    low = move1.lower()
    assert "`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`" in move1, "R0 move 1 must name the variable"
    assert "default 3" in low, "R0 move 1 must state the measured default of 3"
    assert "depth 0" in low and "one deeper than its launcher" in low, (
        "R0 move 1 must say how depth is counted - main is 0, each launch adds one - or a reader "
        "cannot tell whether a chain of three agents is inside a cap of 3"
    )
    assert "below the cap" in low and "depth-3 agent holds none" in low, (
        "R0 move 1 must say an agent holds the launch tool only below the cap, so at the default "
        "the depth-3 agent is the one without it"
    )
    assert "removed silently" in low, "the tool goes without an error - an agent must look, not wait"
    assert "your toolset, not the number, is the truth" in low, (
        "the default is remotely configurable, so the number must never replace looking at the tool"
    )


def test_no_file_but_the_ssot_restates_a_number_for_the_nesting_cap():
    offenders = []
    for path in _scanned_files():
        text = _norm(path.read_text(encoding="utf-8", errors="replace"))
        for m in _ANCHOR_RE.finditer(text):
            window = _NOT_A_CAP_RE.sub(" ", text[m.end() : m.end() + _WINDOW])
            if re.search(r"\b\d+\b", window):
                rel = path.relative_to(REPO_ROOT).as_posix()
                offenders.append(f"{rel}: ...{text[m.start() : m.end() + _WINDOW]}...")
    assert not offenders, (
        "the nesting cap's value lives only in R0 move 1 of snippets/spawner-completion-contract.md; "
        "point there instead of restating it:\n  " + "\n  ".join(offenders)
    )


def test_the_guard_catches_the_phrasings_that_drifted():
    """Red-before-green for the scan itself: each spelling that once carried a wrong or duplicated
    number must be flagged, and each pointer form the fix uses must not."""
    def flagged(s: str) -> bool:
        s = _norm(s)
        for m in _ANCHOR_RE.finditer(s):
            if re.search(r"\b\d+\b", _NOT_A_CAP_RE.sub(" ", s[m.end() : m.end() + _WINDOW])):
                return True
        return False

    for bad in (
        "Claude Code 2.1.172+ (the platform depth cap is 5).",
        "below odoo-coding; the platform enforces a depth cap of 5).",
        "(`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, default 3) - at the cap",
        "skill dispatch (depth-cap-3; non-fork interior agents",
        "may spawn its own subagents (depth cap 3, capability-branching",
        "the nesting\ncap is 5",
    ):
        assert flagged(bad), f"the guard must flag: {bad!r}"
    for good in (
        "(`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`; default and depth counting: §R0 move 1)",
        "inside the depth cap - SSOT `snippets/spawner-completion-contract.md` §R0",
        "the platform nesting cap and how depth is counted are stated once, in R0 move 1.",
    ):
        assert not flagged(good), f"the guard must not flag a pointer: {good!r}"
