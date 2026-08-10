"""Whole-tree guard: no instruction keys behavior on a tool merely being PRESENT in a toolset,
and the "Agent Team mode" vocabulary that rode that inference is gone.

Behavior protected: the retired self-check told every agent that a messaging tool in its own
toolset meant "Agent Team mode is active for this dispatch", then branched on a reply address that
mode was supposed to supply. The messaging tool is ambient in this runtime (the plugin's own setup
docs say so), so the branch fired on every dispatch, on every run - not as an edge case. The
replacement procedure consults ZERO inputs: emit the report as the final message, always. A
procedure that consults nothing cannot false-positive.

Scans the WHOLE tree of agent-facing prose (plugins/ + repo-root docs/) with normalized whitespace
and no filename allowlist.

Run: python -m pytest tests/test_no_team_mode_detection.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS = REPO_ROOT / "plugins"
ODOO_PLUGIN = PLUGINS / "odoo-ai-agents"
GIT_TOOLKIT = PLUGINS / "git-toolkit"
# docs/authoring-skills-and-agents.md is the file every NEW agent is authored from - a rule broken
# there propagates into everything written next, so it is scanned exactly like plugin prose.
ROOT_DOCS = REPO_ROOT / "docs"

R3_SSOT = ODOO_PLUGIN / "snippets" / "spawner-completion-contract.md"
WORKER_BRIEF = ODOO_PLUGIN / "snippets" / "worker-brief.md"

# Same deliberate set every whole-tree guard in this repo uses: prose, declarative config/registry,
# and the executable surface (generators, setup steps) that also carries agent-facing prose.
SCAN_ROOTS = (PLUGINS, ROOT_DOCS)
_SCANNED_SUFFIXES = (".md", ".yaml", ".yml", ".json", ".py", ".sh")


def _scan_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        for suffix in _SCANNED_SUFFIXES:
            files.extend(root.rglob(f"*{suffix}"))
    return sorted(p for p in files if ".venv" not in p.parts)


SCANNED = _scan_files()
NORMALIZED: dict[Path, str] = {
    p: " ".join(p.read_text(encoding="utf-8", errors="replace").split()) for p in SCANNED
}


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def test_scan_corpus_discovered():
    assert len(SCANNED) >= 200, (
        f"expected >=200 scanned files under plugins/, found {len(SCANNED)}"
    )


# ---------------------------------------------------------------------------
# 1. The direct G4 guard: no behavior keys on a tool being present.
# ---------------------------------------------------------------------------

_TOOL_TOKEN_RE = re.compile(
    r"(SendMessage|TaskUpdate|TaskCreate|messaging tool|message tool|send tool)", re.I
)
# A SHAPE for "this tool exists for me", not a phrase list: the defect is the INFERENCE, and it
# reads the same however possession is worded ("in your toolset" / "you have it" / "it was granted"
# / "your allowlist includes it"). A closed list of four spellings misses every natural rewrite.
_PRESENCE_PREDICATE_RE = re.compile(
    r"(in (?:your|its|the)(?: own| current)? (?:toolset|tool set|grant|allowlist|tool list)|"
    r"(?:toolset|grant|allowlist|tool list) (?:carries|includes|lists|grants|contains)|"
    r"you (?:have|hold|were granted|are granted|got|possess|can use|can call|can send|can message)|"
    r"(?:is|are|was|were) (?:present|absent|available|granted|exposed|listed|in scope)|"
    r"(?:available|granted|exposed|offered) to (?:you|it)|"
    r"(?:you |it )?(?:has|have) access to|"
    r"when (?:available|addressable|present|granted)|"
    r"if (?:you |it )?(?:can|hold|holds|have|has)\b|"
    r"if `?(?:SendMessage|TaskUpdate|TaskCreate)`? (?:is|exists)|"
    r"(?:SendMessage|TaskUpdate|TaskCreate) (?:is|are) (?:in|present|available|granted))",
    re.I,
)
# The DEFECT is not "check whether you can send" (a real capability question the resume tier
# legitimately asks) - it is concluding that a MODE, a ROSTER, or an ADDRESS exists because a tool
# does. Only the second shape is matched.
_MODE_CONCLUSION_RE = re.compile(
    r"(agent[- ]team mode|team mode|teammate|reply address|REPLY_TO|CALLER_ID|roster|"
    r"is active|named teammate|the lead\b)",
    re.I,
)
# A window that FORBIDS the inference is the rule, not an instance of it.
_INFERENCE_BAN_RE = re.compile(
    r"(never|not an instruction|is not evidence|not a signal|do not|must not|cannot|no legal|"
    r"is retired|is malformed)",
    re.I,
)


def test_no_behavior_keys_on_a_tool_being_present():
    """Kills every phrasing of the false-positive probe, not one sentence: a tool token inside a
    presence-predicate window that concludes a mode/roster/address exists is the defect, unless
    the same window explicitly forbids that inference."""
    offenders = []
    for path, text in NORMALIZED.items():
        for m in _PRESENCE_PREDICATE_RE.finditer(text):
            window = text[max(0, m.start() - 160): m.end() + 160]
            if not _TOOL_TOKEN_RE.search(window):
                continue
            if not _MODE_CONCLUSION_RE.search(window):
                continue
            if _INFERENCE_BAN_RE.search(window):
                continue
            offenders.append(f"{_rel(path)}: ...{window.strip()[:240]}...")
    assert not offenders, (
        "behavior is keyed on a tool merely being present in a toolset. The messaging tool is "
        "ambient in this runtime, so such a branch fires on every dispatch - it detects nothing:\n"
        + "\n".join(offenders)
    )


# Phrasings that previously slipped, asserted as executable probes so the predicate cannot quietly
# shrink back to a four-spelling list.
_MUST_CATCH = (
    "If `SendMessage` is in your toolset, Agent Team mode is active.",
    "When you have the SendMessage tool, you hold a teammate roster.",
    "A messaging tool available to you means a reply address was supplied.",
    "If you hold `TaskUpdate`, the lead is tracking you.",
    "Your toolset includes SendMessage, so REPLY_TO is set.",
    "A messaging tool was granted to you, so this dispatch is team mode.",
)
_MUST_NOT_CATCH = (
    # CHP Tier A asks the real capability question and concludes nothing about a mode or address.
    "You hold the id that child's own launch call returned, and a messaging tool is in your "
    "current toolset: send the new instructions to that id.",
    # R3 states the ban.
    "Never read the presence of a messaging tool in your toolset as a signal that a reply "
    "address exists.",
)


def _tool_presence_offenders(text: str) -> list[str]:
    found = []
    for m in _PRESENCE_PREDICATE_RE.finditer(text):
        window = text[max(0, m.start() - 160): m.end() + 160]
        if not _TOOL_TOKEN_RE.search(window):
            continue
        if not _MODE_CONCLUSION_RE.search(window):
            continue
        if _INFERENCE_BAN_RE.search(window):
            continue
        found.append(window.strip()[:240])
    return found


@pytest.mark.parametrize("phrasing", _MUST_CATCH)
def test_presence_predicate_catches_every_known_rephrasing(phrasing):
    assert _tool_presence_offenders(" ".join(phrasing.split())), (
        f"the tool-presence guard does not catch {phrasing!r} - it is back to matching a fixed "
        "set of spellings instead of the inference"
    )


@pytest.mark.parametrize("phrasing", _MUST_NOT_CATCH)
def test_presence_predicate_allows_the_real_capability_question(phrasing):
    assert not _tool_presence_offenders(" ".join(phrasing.split())), (
        f"the tool-presence guard flags {phrasing!r}. Asking whether you CAN send is legitimate "
        "(Tier A needs it); concluding a mode/roster/address exists is the defect"
    )


def test_the_tool_presence_inference_is_banned_positively():
    """Paired presence assertion: deleting every mention would satisfy the absence guard above.
    Both SSOTs must actively forbid the inference."""
    assert (
        "never read the presence of a messaging tool in your toolset"
        in NORMALIZED[R3_SSOT].lower()
    ), "spawner-completion-contract.md R3 must forbid the tool-presence inference explicitly"
    assert (
        "never treat a messaging tool's presence in your toolset as an instruction"
        in NORMALIZED[WORKER_BRIEF].lower()
    ), "worker-brief.md must forbid the tool-presence inference explicitly for a leaf"


# ---------------------------------------------------------------------------
# 2. The vocabulary of the mode that never existed is gone.
# ---------------------------------------------------------------------------

_MODE_VOCAB_RE = re.compile(
    r"(agent[- ]team mode|team[- ]lead(?:er)?s?\b|teammate roster|\bAsk[- ][12]\b|"
    r"task[- ]board)",
    re.I,
)


def test_no_agent_team_mode_vocabulary_survives():
    offenders = [
        f"{_rel(path)}: {m.group(0)!r}"
        for path, text in NORMALIZED.items()
        for m in _MODE_VOCAB_RE.finditer(text)
    ]
    assert not offenders, (
        "vocabulary for a mode this plugin cannot enter survives. It cannot name an agent, so it "
        "cannot create a teammate, so there is no roster, no lead, and no board:\n"
        + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# 3. The task-board tools are not referenced in agent-facing prose.
# ---------------------------------------------------------------------------

_BOARD_TOOL_RE = re.compile(r"\b(TaskCreate|TaskList|TaskGet|TaskUpdate)\b")


def test_task_board_tools_are_not_referenced():
    """The executor's own progress list is tool-agnostic by design
    (`execution-tasklist-contract.md`); naming a specific board tool re-couples it to a surface
    that may not exist."""
    offenders = [
        f"{_rel(path)}: {m.group(0)}"
        for path, text in NORMALIZED.items()
        for m in _BOARD_TOOL_RE.finditer(text)
    ]
    assert not offenders, (
        "a concrete task-board tool name survives:\n" + "\n".join(offenders)
    )
    contract = ODOO_PLUGIN / "snippets" / "execution-tasklist-contract.md"
    assert "does not hardcode a tool name" in NORMALIZED[contract], (
        "execution-tasklist-contract.md must keep its tool-agnostic clause - that clause is why "
        "no consumer needs to name a board tool"
    )


# ---------------------------------------------------------------------------
# 4. A hard leaf's tools: allowlist grants no messaging tool.
# ---------------------------------------------------------------------------

_TOOLS_LINE_RE = re.compile(r"^tools:\s*\[(.*?)\]\s*$", re.MULTILINE | re.DOTALL)
_HARD_LEAF_MARKER_RE = re.compile(
    r"(never spawn|does not spawn|never launch|do NOT spawn|HARD LEAF|cannot spawn|"
    r"no subagent-spawning)",
    re.I,
)


def test_hard_leaf_allowlists_grant_no_messaging_tool():
    """Structural, not a file list: any agent whose body declares it launches nothing must not
    have a messaging tool in its frontmatter allowlist. A listed-but-unusable tool makes the model
    call it and error instead of cleanly emitting its final message."""
    agent_dirs = [ODOO_PLUGIN / "agents", GIT_TOOLKIT / "agents"]
    checked = 0
    offenders = []
    for agents_dir in agent_dirs:
        for agent in sorted(agents_dir.glob("*.md")):
            body = agent.read_text(encoding="utf-8")
            m = _TOOLS_LINE_RE.search(body)
            if not m:
                continue  # inherits the full surface - not an allowlist decision
            if not _HARD_LEAF_MARKER_RE.search(body):
                continue  # a spawner may legitimately resume a child it launched
            checked += 1
            for banned in ("SendMessage", "TaskUpdate"):
                if banned in m.group(1):
                    offenders.append(f"{_rel(agent)}: tools: grants {banned}")
    assert checked >= 3, (
        f"expected >=3 hard-leaf agents with a tools: allowlist, found {checked} - the structural "
        "marker stopped matching, so this assertion would pass vacuously"
    )
    assert not offenders, (
        "a hard leaf's allowlist grants a messaging tool it has no legal target for:\n"
        + "\n".join(offenders)
    )
