"""Guard: the plugin's status and gate-reply vocabulary is declared ONCE and consumed
consistently - the M5 "One vocabulary, generator-owned" fix.

Background: this plugin used to carry THREE incompatible `status` enums (a 4-value
continuation status, a wider node status, and a stray `DONE_WITH_CONCERNS` value that
mechanical consumers never recognized) and THREE gate-reply-keyword vocabularies
(`approve/refine/cancel`, `yes/refine/cancel`, `approve/skip/cancel`) mixed within single
files. The fix: `generator/skill_tool_deps.json` -> `vocabulary` is the machine-owned SSOT;
`snippets/continuation-contract.md`, `snippets/planning-gate-contract.md`, and
`snippets/vocabulary.md` render it for a human/agent reader without restating the values
independently. `DONE_WITH_CONCERNS` is RESERVED - a caveat on completed work is now
`status: DONE` plus a `concerns:` list, never a fifth status value. This file is the
regression guard that keeps all of the above true.

Each test below is written to fail for a real reason - see the module docstring of each
test function for what mutation it catches.

Run: python -m pytest tests/test_status_vocabulary.py -v
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
DEPS_JSON = PLUGIN / "generator" / "skill_tool_deps.json"
CONTINUATION_CONTRACT = PLUGIN / "snippets" / "continuation-contract.md"
ETHOS = PLUGIN / "ODOO-AI-ETHOS.md"

EXPECTED_CONTINUATION_STATUS = ["DONE", "NEEDS_NEXT", "BLOCKED", "NEEDS_CONTEXT"]
EXPECTED_NODE_STATUS = [
    "PENDING", "READY", "RUNNING", "DONE", "FAILED", "SKIPPED", "BLOCKED", "NEEDS_CONTEXT",
]

# Files legitimately excluded from the reserved-token-in-status-position scan:
#   - ODOO-AI-ETHOS.md - a DIFFERENT field (human-facing self-report, ODOO-AI-ETHOS #10),
#     out of this plugin's ownership; its own Completion Status table row names
#     DONE_WITH_CONCERNS as ITS enum member, not a Continuation Contract `status:` value.
#   - review-severity-rubric.md - the reserved token was already migrated to a `concerns:`
#     sibling note there; the file is excluded from the SCAN (not the migration) because its
#     surrounding language is a review "verdict" word, not a `status:` field assignment - see
#     M5 design note ("neither is review-severity-rubric.md's verdict word").
_STATUS_POSITION_SCAN_EXCLUDES = {ETHOS}

# Scan every agent-facing prose root under the plugin.
_SCAN_ROOTS = [
    PLUGIN / "skills",
    PLUGIN / "agents",
    PLUGIN / "snippets",
    PLUGIN / "docs",
    PLUGIN / "workflows",
    PLUGIN / "commands",
]


def _load_vocab() -> dict:
    data = json.loads(DEPS_JSON.read_text(encoding="utf-8"))
    assert "vocabulary" in data, "generator/skill_tool_deps.json is missing its top-level 'vocabulary' block"
    return data["vocabulary"]


def _scan_files():
    for root in _SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path not in _STATUS_POSITION_SCAN_EXCLUDES:
                yield path


# ---------------------------------------------------------------------------
# test_enum_declared_once
# ---------------------------------------------------------------------------
# FAILS (for the right reason) if: the JSON SSOT and its prose rendering in
# continuation-contract.md disagree on the four continuation_status values, or if the JSON
# enum itself is edited to a different set of values/order. A prior version of this plugin
# had THREE different enums; this test proves there is exactly one for continuation_status,
# with the prose file agreeing verbatim.
def test_enum_declared_once():
    vocab = _load_vocab()
    assert vocab["continuation_status"] == EXPECTED_CONTINUATION_STATUS, (
        f"generator/skill_tool_deps.json vocabulary.continuation_status drifted: "
        f"{vocab['continuation_status']!r}"
    )
    assert vocab["node_status"] == EXPECTED_NODE_STATUS, (
        f"generator/skill_tool_deps.json vocabulary.node_status drifted: {vocab['node_status']!r}"
    )

    text = CONTINUATION_CONTRACT.read_text(encoding="utf-8")
    # The fenced schema line must declare exactly the JSON SSOT's four values, in order,
    # pipe-separated - the ONE prose rendering of the enum.
    m = re.search(r"^status:\s*(.+)$", text, re.MULTILINE)
    assert m, "snippets/continuation-contract.md no longer has a 'status: ...' schema line"
    rendered = [v.strip() for v in m.group(1).split("|")]
    assert rendered == EXPECTED_CONTINUATION_STATUS, (
        f"snippets/continuation-contract.md's rendered status enum {rendered!r} disagrees with "
        f"the JSON SSOT {EXPECTED_CONTINUATION_STATUS!r}"
    )


# ---------------------------------------------------------------------------
# test_no_reserved_token_in_status_position
# ---------------------------------------------------------------------------
# FAILS (for the right reason) if any agent-facing prose file assigns the reserved
# DONE_WITH_CONCERNS token in a `status:`-position context (a bare `status:` field, or a
# `status: DONE_WITH_CONCERNS(...)` narrative report) OUTSIDE the two sanctioned exceptions
# (ODOO-AI-ETHOS.md's OWN field, and the review-severity-rubric.md verdict word, which is not
# a status: field at all). This is the direct regression guard for the M5 migration: it would
# have failed loudly against the pre-fix tree (21 real hits across 14 files).
_RESERVED_IN_STATUS_RE = re.compile(
    r"status:\s*`?DONE_WITH_CONCERNS\b"  # `status: DONE_WITH_CONCERNS` / `status:` + literal
    r"|`status`\s*[:=]\s*.*DONE_WITH_CONCERNS"  # a schema-style enum listing it as a member
)


def test_no_reserved_token_in_status_position():
    hits = []
    for path in _scan_files():
        if path.name == "review-severity-rubric.md":
            continue  # verdict word, not a status: field - see module docstring
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for m in _RESERVED_IN_STATUS_RE.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            hits.append(f"{path.relative_to(ROOT)}:{line_no}")
        # A bare mention immediately after "status" prose language (not just the regex above)
        # also counts - e.g. `mark the run DONE_WITH_CONCERNS` or `return DONE_WITH_CONCERNS`.
        for m in re.finditer(r"\bDONE_WITH_CONCERNS\b", text):
            window_start = max(0, m.start() - 80)
            window = text[window_start:m.start()]
            if re.search(r"\b(status|run|return|report|emit)\b\s*[:`]*\s*$", window, re.IGNORECASE):
                line_no = text.count("\n", 0, m.start()) + 1
                hit = f"{path.relative_to(ROOT)}:{line_no}"
                if hit not in hits:
                    hits.append(hit)

    assert not hits, (
        "DONE_WITH_CONCERNS is reserved (not a status value - use `status: DONE` + `concerns:`); "
        f"found in a status-reporting position at: {hits}"
    )


# ---------------------------------------------------------------------------
# test_mechanical_consumers_cover_the_enum
# ---------------------------------------------------------------------------
# FAILS (for the right reason) if the observability hook that must recognize the FULL
# four-value enum (report-terminal-status.sh, which classifies a transcript's terminal status
# against exactly these four values to detect a "strand") stops naming all four, or if the
# run-record reader the unfinished-run reminder relies on (run-ownership.sh, sourced by
# drive-continuation.sh) stops selecting NEEDS_NEXT. Proves: at least one mechanical consumer
# recognizes every value in the declared enum (no value is dead weight that no script ever
# checks for).
def test_mechanical_consumers_cover_the_enum():
    hooks_dir = PLUGIN / "hooks"
    terminal = (hooks_dir / "report-terminal-status.sh").read_text(encoding="utf-8")
    combined = "|".join(EXPECTED_CONTINUATION_STATUS)
    assert combined in terminal or all(v in terminal for v in EXPECTED_CONTINUATION_STATUS), (
        "hooks/report-terminal-status.sh no longer names the full continuation_status enum "
        f"({EXPECTED_CONTINUATION_STATUS!r}) - a value could silently stop being observed"
    )

    run_records = (hooks_dir / "run-ownership.sh").read_text(encoding="utf-8")
    assert '"NEEDS_NEXT"' in run_records, (
        "hooks/run-ownership.sh no longer selects NEEDS_NEXT run records - the unfinished-run "
        "reminder would never fire"
    )
    # HARD CONTRACT: the reminder must never block the main agent (the plan runner's loop
    # depends on this). Guard the contract, not just the value.
    drive = (hooks_dir / "drive-continuation.sh").read_text(encoding="utf-8")
    emitted = re.findall(r"jq -cn[^\n]*'(\{[^']*\})'", drive)
    assert emitted and not any("decision" in obj for obj in emitted), (
        "hooks/drive-continuation.sh must never emit a block decision (HARD CONTRACT, see its "
        "own header) - a block would trap the main agent on a mere NEEDS_NEXT reminder"
    )


