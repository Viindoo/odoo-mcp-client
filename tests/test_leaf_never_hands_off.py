"""Guard: no leaf agent is told to hand work to another actor - a primitive that does not exist.

Third guard on one shared fact, each owning a different half so none restates another:

  * `test_no_agent_naming.py`     - a launch call cannot NAME the agent it starts.
  * `test_return_path_contract.py` - nothing may instruct an agent to DELIVER its report upward;
                                     the report is its final message (SSOT:
                                     `snippets/spawner-completion-contract.md` R3).
  * this file                     - nothing may instruct a LEAF to DISPATCH work outward, and no
                                     leaf may name a specific caller on its own return path.

The first two cover being addressed and reporting back. Neither sees "hand off to `odoo-coding`",
which is an outbound dispatch instruction, so it survived both until this guard existed.

What the runtime actually provides, read out of the installed Claude Code binary rather than
recalled:

  - The tool grant for spawning is depth-filtered - `if (an(v,_t)) return agentDepth < uS()`, where
    `uS()` resolves `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` (env, else a remote-config value). So an
    agent may not even hold the launch tool, and nothing in the prose can assume it does.
  - There is no agent-to-agent handoff primitive at all. A subagent's base prompt says to "respond
    with a concise report ... the caller will relay this" - one implicit outbound channel, back to
    whoever launched it. The caller is never addressed, never named, and cannot be chosen.
  - Addressing only ever points DOWNWARD, and by id: a caller resumes a child with the id that
    child's own launch call returned. An agent name (`odoo-coder`) is a blueprint, not an address -
    each launch is a distinct instance.

So "hand off to `odoo-coding`" asks a leaf to do three impossible things at once: dispatch a SKILL
as if it were an actor, reach sideways to something it did not launch, and do it without the launch
tool. The correct shape is to RETURN, naming the next step in the Continuation Contract, and let
whichever caller launched this agent route it.

The rule is scoped to LEAF agents (`role: leaf` in the orchestration SSOT), which is data-driven -
a new leaf is covered the day it is declared. Spawners legitimately dispatch.

Run: python -m pytest tests/test_leaf_never_hands_off.py -v
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
AGENTS = PLUGIN / "agents"
ORCH_SSOT = PLUGIN / "generator" / "skill_tool_deps.json"


def _leaf_agents() -> list[Path]:
    spec = json.loads(ORCH_SSOT.read_text(encoding="utf-8")).get("agents", {})
    names = sorted(n for n, a in spec.items() if a.get("role") == "leaf")
    return [AGENTS / f"{n}.md" for n in names if (AGENTS / f"{n}.md").is_file()]


LEAF_FILES = _leaf_agents()

# The imperative form only. "Dispatched by the odoo-coder" (passive - who launched ME) and
# "no spawn, no Skill tool, no odoo-content-draft" (a negation) are both correct prose, and a
# guard that flagged them would be abandoned within a release.
_HANDOFF_RE = re.compile(
    r"\b(?:hand(?:s|ed)?[ -]off to|handoff to|hand it off to)\b",
    re.I,
)
# A leaf may state where work BELONGS as long as it also says the routing is not its to perform.
_DISCLAIMED_RE = re.compile(
    r"(?:never dispatch|not dispatch|do NOT dispatch|whoever launched you|"
    r"the caller (?:will |can )?relay|for (?:your|the) (?:caller|launcher) to route|"
    r"emit `?next:|"
    # Handing BACK to the caller is just the return path under another name - always legal, and
    # the adjective is free ("your dispatching caller", "your launching caller").
    r"(?:your|the) (?:\w+ )?(?:caller|launcher))",
    re.I,
)


def test_leaf_agent_corpus_is_not_empty():
    """A glob that silently matched nothing would make every assertion below vacuously green."""
    assert len(LEAF_FILES) >= 20, f"expected the declared leaf agents, found {len(LEAF_FILES)}"


@pytest.mark.parametrize("path", LEAF_FILES, ids=lambda p: p.stem)
def test_leaf_is_never_told_to_hand_off(path):
    """`hand off to X` describes a primitive the runtime does not have. A leaf returns; its caller
    routes."""
    offenders = [
        (i, line.strip()[:150])
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _HANDOFF_RE.search(line) and not _DISCLAIMED_RE.search(line)
    ]
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)} tells a HARD LEAF to hand work off: {offenders}. "
        f"There is no agent-to-agent handoff primitive - the agent returns its report and the "
        f"caller that launched it routes. Say 'emit `next: <skill>` in your Continuation Contract' "
        f"and name no launcher."
    )


@pytest.mark.parametrize("path", LEAF_FILES, ids=lambda p: p.stem)
def test_leaf_does_not_address_its_caller_by_name_on_the_return_path(path):
    """An agent name is a blueprint; each launch is a distinct instance, and the only address that
    exists is the id a launch returned to the CALLER. A leaf therefore cannot return "to
    `odoo-coder`" as an addressed send - and naming one caller is wrong anyway for any agent more
    than one orchestrator dispatches. Descriptive topology ("the coordinator aggregates your files
    and returns them to X" - what someone ELSE does) stays legal; an imperative telling THIS agent
    to send its own result to a named actor does not."""
    pat = re.compile(
        r"\b(?:RETURN|Return|report|Report|send|Send)\b[^.\n]{0,30}\bto\b\s+(?:the\s+)?`(odoo-[a-z-]+)`",
    )
    offenders = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for m in pat.finditer(line):
            # Third-person description of another actor's duty is not an instruction to this one.
            if re.search(r"\b(?:coordinator|orchestrator|caller|launcher|it|which)\b\s+\w*\s*returns",
                         line, re.I):
                continue
            offenders.append((i, m.group(0)[:120]))
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)} names a specific caller on its own return path: "
        f"{offenders}. The return is implicit and unaddressed - the runtime hands the report to "
        f"whoever launched this instance, which may be any orchestrator. Say 'return to your "
        f"caller', never a blueprint name."
    )


# --- Self-checks: the detectors can go RED for the right reason ---------------------------------

def test_handoff_detector_fires_on_the_clause_this_change_removed():
    removed = "Point at the exact file + method/selector to change. Hand off to `odoo-coding` for the edit."
    assert _HANDOFF_RE.search(removed), "the detector no longer sees a bare handoff imperative"
    assert not _DISCLAIMED_RE.search(removed), (
        "the disclaimer pattern must NOT match a bare handoff, or the guard exempts everything"
    )


def test_handoff_detector_accepts_the_corrected_form():
    fixed = (
        "You do NOT dispatch the fix: emit `next: odoo-coding` in your Continuation Contract and "
        "let your caller dispatch it."
    )
    assert _DISCLAIMED_RE.search(fixed), (
        "the guard must accept the corrected wording, else it bans the fix it exists to require"
    )
