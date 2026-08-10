"""Whole-tree guard: nothing addresses a SIBLING agent, and contested same-layer decisions are
brokered by the lead instead.

Behavior protected: sibling messaging is unimplementable twice over - a launcher cannot name the
children it starts, and the roster an agent is shown contains only agents IT launched. A child
told to open a direct exchange with a peer therefore stalls on a send that cannot resolve, in the
middle of a design phase that has no other way to converge. The replacement converges through the
lead: the child records its proposal and finishes; the lead decides once the layer's R1 barrier
clears.

Scans the WHOLE tree of agent-facing prose (plugins/ + repo-root docs/) with normalized whitespace
and no filename allowlist; the absence assertions are paired with presence assertions on the
lead-brokered replacement.

Run: python -m pytest tests/test_peer_messaging_absent.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS = REPO_ROOT / "plugins"
ODOO_PLUGIN = PLUGINS / "odoo-ai-agents"
# docs/authoring-skills-and-agents.md is the file every NEW agent is authored from.
ROOT_DOCS = REPO_ROOT / "docs"

MASTER_CHILD = ODOO_PLUGIN / "snippets" / "master-child-design-contract.md"
ARCHITECT = ODOO_PLUGIN / "agents" / "odoo-solution-architect.md"
SOLUTION_DESIGN = ODOO_PLUGIN / "skills" / "odoo-solution-design" / "SKILL.md"

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
# 1. No sibling addressing machinery, in any phrasing.
# ---------------------------------------------------------------------------

# Field-shaped only: a brief KEY (any casing, because `Peers:` is the same field as `PEERS:`), the
# retired section heading, and the retired verb. A generic English "peers" in running prose is not
# sibling-addressing machinery.
_SIBLING_FIELD_RE = re.compile(
    r"\bPEERS\b|\b[Pp]eers?\s*:|peer-reconcile|[Pp]eer [Rr]econciliation"
)


def test_no_sibling_address_field_anywhere():
    offenders = [
        f"{_rel(path)}: {m.group(0)!r}"
        for path, text in NORMALIZED.items()
        for m in _SIBLING_FIELD_RE.finditer(text)
    ]
    assert not offenders, (
        "sibling-addressing machinery survives. A lead cannot broker a sibling address (it cannot "
        "name the children it launches) and a child cannot look one up (its roster holds only "
        "agents it launched itself):\n" + "\n".join(offenders)
    )


# A same-layer counterpart, however it is named. "the other architects in your layer" is the same
# unreachable agent as "your sibling" - naming it differently does not make it addressable.
_ROLE = (
    r"(?:agent|subagent|worker|teammate|architect|coder|reviewer|child|children|specialist|"
    r"designer|planner|scout|surveyor)s?"
)
_COUNTERPART = (
    rf"(?:peers?\b|siblings?\b|counterparts?\b|(?:other|fellow)\s+{_ROLE}\b|"
    rf"{_ROLE}\s+in\s+(?:your|the\s+same)\s+(?:layer|wave|batch)\b)"
)
# Lateral coordination does not need the messaging tool's NAME to be an instruction to do it: any
# directive to open a two-way exchange with a counterpart is the defect, because no such channel
# exists. The verb is bound to the counterpart (optionally through one preposition), so a stray
# "message" elsewhere in the paragraph cannot fabricate a hit.
_LATERAL_VERB = (
    r"(?:SendMessage|message|contact|notify|ping|ask|tell|query|consult|coordinate|negotiate|"
    r"agree|align|sync|reconcile|exchange|reach\s+out|talk|speak|confer)"
)
_SEND_TOKEN_RE = re.compile(
    rf"\b{_LATERAL_VERB}\w*"
    rf"(?:(?:\s+\S+){{0,6}}?\s+(?:with|to|among)|)"
    rf"\s+(?:the|your|its|their|a|an|each)?\s*{_COUNTERPART}",
    re.I,
)
_SEND_BAN_RE = re.compile(
    r"(cannot|can not|never|no agent can|do not|does not exist|must not|is not|"
    r"unreachable|no channel)",
    re.I,
)


def _peer_send_offenders(text: str) -> list[str]:
    found = []
    for m in _SEND_TOKEN_RE.finditer(text):
        window = text[max(0, m.start() - 160): m.end() + 160]
        if _SEND_BAN_RE.search(window):
            continue
        found.append(window.strip()[:240])
    return found


def test_no_send_is_paired_with_a_peer_or_sibling():
    """Shape guard: a lateral-coordination directive inside a counterpart window is peer messaging
    unless the same window forbids it. Catches any phrasing, and does not depend on the messaging
    tool being named - "agree the shared symbol with the other architects in your layer" describes
    the same impossible exchange as an explicit send."""
    offenders = [
        f"{_rel(path)}: ...{window}..."
        for path, text in NORMALIZED.items()
        for window in _peer_send_offenders(text)
    ]
    assert not offenders, (
        "lateral peer/sibling messaging survives:\n" + "\n".join(offenders)
    )


_MUST_CATCH = (
    "Message your sibling architect with the proposed symbol.",
    "Agree the shared symbol with the other architects in your layer.",
    "Coordinate directly with the other coders before you write the field.",
    "Ask your counterpart which module owns the symbol.",
    "Sync with the other workers in the same wave before finishing.",
)
_MUST_NOT_CATCH = (
    "No agent can address a sibling: record your proposal and finish.",
    "Same-layer children cannot reach each other - the lead decides after the barrier clears.",
)


@pytest.mark.parametrize("phrasing", _MUST_CATCH)
def test_peer_guard_catches_lateral_coordination_without_a_tool_name(phrasing):
    assert _peer_send_offenders(" ".join(phrasing.split())), (
        f"the peer guard does not catch {phrasing!r} - it is keyed on the tool name again, so "
        "lateral coordination described in plain English is invisible to it"
    )


@pytest.mark.parametrize("phrasing", _MUST_NOT_CATCH)
def test_peer_guard_allows_the_prohibition_itself(phrasing):
    assert not _peer_send_offenders(" ".join(phrasing.split())), (
        f"the peer guard flags {phrasing!r}, which states the rule"
    )


# ---------------------------------------------------------------------------
# 2. Paired presence: the lead-brokered replacement actually exists, in the
#    snippet SSOT, in the child-facing agent body, and where the lead runs.
# ---------------------------------------------------------------------------


def test_contested_symbol_reconciliation_is_lead_brokered():
    contract = NORMALIZED[MASTER_CHILD]
    assert "## Contested-symbol reconciliation" in contract, (
        "master-child-design-contract.md must own the same-layer seam contract"
    )
    for marker in (
        "no agent can address a sibling",
        "contested-symbols.md",
        "after its R1 barrier clears",
        "ONE reconciliation round per layer",
        "BLOCKED for a human",
    ):
        assert marker in contract, (
            f"master-child-design-contract.md must state {marker!r} - without it the layer either "
            "stalls, loops, or lets a child decide a symbol it does not own"
        )

    architect = NORMALIZED[ARCHITECT]
    assert "master-child-design-contract.md" in architect, (
        "odoo-solution-architect.md must CITE the SSOT rather than restate it"
    )
    assert "no agent can address a sibling" in architect, (
        "the child-facing summary must state the sibling is unreachable - a child reads its own "
        "body first, not the snippet"
    )

    skill = NORMALIZED[SOLUTION_DESIGN]
    assert "contested-symbols.md" in skill, (
        "the lead half must be wired where the lead actually runs (odoo-solution-design/SKILL.md) "
        "- a rule stated only in the snippet is a rule nothing executes"
    )
