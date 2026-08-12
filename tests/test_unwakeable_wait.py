"""Whole-tree guard: nothing offers a dispatched context the wait that never ends, and the SSOT
states why a worker's apparent ways back up are not ways back up.

Behavior protected - two halves of one stall:

  COORDINATOR SIDE. Only the root conversation is resumed when a background child finishes. A
  launcher that is itself dispatched is never woken by its own child, so "launch it in the
  background and end your turn to wait" is not a slower shape below the root - it is a permanent
  stop with no error, no output, and nothing for anyone to read. Prose that offers that shape
  without saying it is root-only reads as a sanctioned alternative, and a coordinator that takes it
  hangs until a human notices.

  WORKER SIDE. The stranded worker then goes looking for its launcher, and everything it finds is a
  trap: an inbound message shows a TYPE label where an address would be, no lookup exists to turn
  any name into one, and the literal `main` does not fail - it is ACCEPTED and delivered to the root
  conversation, which is not waiting, while the launcher that is waiting stays parked. A rule
  phrased only as a prohibition loses to that success receipt, so the SSOT must state the
  consequence, not just the ban.

Guards are SHAPE-based over the whole markdown tree with normalized whitespace, never a filename
allowlist: a park instruction is a finding whenever its window promises resumption of a child and
does NOT scope that promise to the root (or explicitly rule the shape out). Each absence guard is
paired with a presence assertion on the single SSOT so "delete it everywhere" cannot pass, and with
executable must-catch / must-not-catch probes so the shape cannot silently shrink to one spelling.

Run: python -m pytest tests/test_unwakeable_wait.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS = REPO_ROOT / "plugins"
ODOO_PLUGIN = PLUGINS / "odoo-ai-agents"
ROOT_DOCS = REPO_ROOT / "docs"

R0R1R3_SSOT = ODOO_PLUGIN / "snippets" / "spawner-completion-contract.md"
CHP_MD = ODOO_PLUGIN / "snippets" / "context-handoff-protocol.md"

# Generated regions come from a separate SSOT and are not hand-authored prose.
_GENERATED_RE = re.compile(
    r"<!--\s*BEGIN GENERATED TOOLS\s*-->.*?<!--\s*END GENERATED TOOLS\s*-->", re.S
)


def _scan_files() -> list[Path]:
    files: list[Path] = []
    for root in (PLUGINS, ROOT_DOCS):
        files.extend(root.rglob("*.md"))
    return sorted(p for p in files if ".venv" not in p.parts)


SCANNED = _scan_files()


def _norm(path: Path) -> str:
    raw = _GENERATED_RE.sub(" ", path.read_text(encoding="utf-8"))
    return " ".join(raw.split())


NORMALIZED: dict[Path, str] = {p: _norm(p) for p in SCANNED}


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def test_scan_corpus_discovered():
    assert len(SCANNED) >= 200, (
        f"expected >=200 scanned markdown files, found {len(SCANNED)} - the glob is wrong, so "
        "every whole-tree assertion below would pass for the wrong reason"
    )


# ---------------------------------------------------------------------------
# 1. Whole tree - a park instruction must be scoped to the root, or ruled out.
# ---------------------------------------------------------------------------

# The instruction to stop the turn. Open on the possessive so "end your/its/the turn" all match.
_PARK_VERB_RE = re.compile(
    r"(end(?:s|ing)? (?:your|its|his|her|their|the) turn|END YOUR TURN|END ITS TURN|END THE TURN|"
    r"park(?:-and-be-resumed|ed|s|ing)?\b|wait to be resumed|send,? stop)",
    re.I,
)
# What makes the park a WAIT ON A CHILD rather than a wait on a human or on the next user turn: the
# promise of being woken must be LINKED, inside one clause, to a dispatched actor. Requiring only
# that both words appear somewhere nearby flags "emit options and END THE TURN - next turn resumes"
# (a wait on the human) purely because an unrelated sentence 300 chars away said "agent".
_WOKEN = r"resumed?|resumes|woken|wakes?|notified|notification"
_ACTOR = (
    r"child|children|worker|workers|teammate|subagent|sub-agent|coordinator|leaf|grandchild|"
    r"agent|agents|launch|dispatch"
)
_CLAUSE = r"[^.;:!?]{0,140}?"
_WOKEN_BY_CHILD_RE = re.compile(
    rf"(?:{_WOKEN})\b{_CLAUSE}\b(?:{_ACTOR})"           # "resumed when the child completes"
    rf"|\b(?:{_ACTOR})\b{_CLAUSE}(?:{_WOKEN}|completes|finishes)\b",  # "the worker completes"
    re.I,
)
# The scoping that makes the promise TRUE - the park belongs to the root conversation only.
_ROOT_SCOPE_RE = re.compile(
    r"(root conversation|root-only|only the root|at the root|from the root|you are the root|"
    r"you ARE the root|the root is resumed|`main` itself launched|main itself launched|"
    r"an agent `main` itself)",
    re.I,
)
# ... or wording that rules the shape out entirely rather than offering it.
_PARK_RULED_OUT_RE = re.compile(
    r"(never launch-and-park|do not launch-and-park|may never be woken|never woken|"
    r"is never resumed|nothing resumes you|never resumed on you|permanent stall|"
    r"unreachable|dead end|is not a park|never a park|not a poll|forbids|never wake|"
    r"parks you forever|stays parked|never end(?:ing)? (?:its|your|the) turn)",
    re.I,
)

# Tight TRIGGER window (the linkage must sit right by the park verb), broad EXEMPTION window (a
# root-scoping or ruling-out sentence anywhere in the surrounding prose governs the instruction).
_TRIGGER_WINDOW = 200
_EXEMPT_WINDOW = 400


def _unscoped_park_offenders(text: str) -> list[str]:
    """Windows that tell a context to stop its turn and be woken by a dispatched actor, without
    scoping that promise to the root or ruling the shape out."""
    found = []
    for m in _PARK_VERB_RE.finditer(text):
        trigger = text[max(0, m.start() - _TRIGGER_WINDOW): m.end() + _TRIGGER_WINDOW]
        if not _WOKEN_BY_CHILD_RE.search(trigger):
            continue  # a wait on a human / on the next user turn - not this defect
        window = text[max(0, m.start() - _EXEMPT_WINDOW): m.end() + _EXEMPT_WINDOW]
        if _ROOT_SCOPE_RE.search(window) or _PARK_RULED_OUT_RE.search(window):
            continue
        found.append(window.strip()[:280])
    return found


def test_no_file_offers_an_unscoped_park_on_a_dispatched_child():
    offenders = [
        f"{_rel(path)}: ...{w}..."
        for path, text in NORMALIZED.items()
        for w in _unscoped_park_offenders(text)
    ]
    assert not offenders, (
        "a park-and-be-resumed instruction is offered without scoping it to the root. Only the "
        "root conversation is resumed when a background child finishes, so below the root this "
        "shape stops the run silently (snippets/spawner-completion-contract.md R0 move 3 / R1 "
        "Boundary):\n" + "\n".join(offenders)
    )


# The real pre-fix sentences from this tree, asserted as executable probes so the shape cannot
# quietly shrink back to catching one spelling.
_MUST_CATCH = (
    "No such switch -> every launch is asynchronous: launch, then END YOUR TURN. You are parked "
    "and resumed when the child completes.",
    "A resume send is fire-and-forget. After sending, END your turn and wait to be resumed when "
    "the child completes. This is legal for a subagent exactly as for main.",
    "Structure the exchange as async park-and-be-resumed: send the failure output, end your turn, "
    "and consume the worker's result when it completes.",
    "PARK: end your turn here, do not await a synchronous return - you are notified when the "
    "resumed worker completes.",
    "When it does not, the launch is asynchronous: launch, then end your turn to be resumed by "
    "the wake router - never poll, never re-launch.",
)
_MUST_NOT_CATCH = (
    # The corrected rule, in each of the two legal shapes.
    "Only the root conversation is resumed when a background child finishes. If you ARE the root: "
    "launch, then END YOUR TURN.",
    "If you are a SUBAGENT: nothing resumes you, so never launch-and-park - do the work inline.",
    # Waits that are not on a dispatched child at all.
    "Present the options and END THE TURN; the human answers on the next turn.",
    "Emit the plan and end your turn so the human can approve it before anything is written.",
)


@pytest.mark.parametrize("phrasing", _MUST_CATCH)
def test_guard_catches_every_known_unscoped_park_phrasing(phrasing):
    assert _unscoped_park_offenders(" ".join(phrasing.split())), (
        f"the unscoped-park guard does not catch {phrasing!r} - it is bound to one phrasing again"
    )


@pytest.mark.parametrize("phrasing", _MUST_NOT_CATCH)
def test_guard_allows_the_root_scoped_and_human_gated_waits(phrasing):
    assert not _unscoped_park_offenders(" ".join(phrasing.split())), (
        f"the unscoped-park guard flags {phrasing!r}. A root-scoped park and a wait on a human are "
        "both legal; only an unscoped wait on a dispatched child is the defect"
    )


# ---------------------------------------------------------------------------
# 2. Coordinator side, stated positively in the SSOT.
# ---------------------------------------------------------------------------


def test_r0_makes_a_blocking_launch_mandatory_for_a_subagent():
    """R0 move 2 already calls blocking the preferred default. Preference is not enough: a
    coordinator that needs a result and backgrounds the dispatch anyway cannot be recovered, so the
    obligation and its consequence must both be stated."""
    low = _norm(R0R1R3_SSOT).lower()
    assert re.search(r"for a subagent this is not a preference", low), (
        "R0 move 2 must say, for a subagent, that blocking is not a preference"
    )
    assert re.search(r"must block", low), (
        "R0 move 2 must state the obligation: a dispatch whose result you need MUST block"
    )
    assert re.search(r"nothing wakes you", low), (
        "R0 move 2 must state the consequence that makes the obligation decidable - nothing wakes "
        "you - not merely that blocking is nicer"
    )


def test_r0_scopes_the_async_park_to_the_root():
    """R0 move 3's promise ('you are parked and resumed') holds only for the root. Left unscoped it
    is the sentence a coordinator follows into a permanent stall."""
    low = _norm(R0R1R3_SSOT).lower()
    assert re.search(r"only the root conversation is resumed", low), (
        "R0 move 3 must scope resumption to the root conversation"
    )
    assert re.search(r"nothing resumes you", low) and re.search(r"never launch-and-park", low), (
        "R0 move 3 must give the subagent branch its own decidable instruction: nothing resumes "
        "you, so never launch-and-park"
    )
    idx = low.find("if you are a subagent")
    assert idx != -1, "R0 move 3 must address the subagent case explicitly"
    window = low[idx:idx + 400]
    assert "skill tool" in window or "needs_next" in window, (
        "the subagent branch must name what to do INSTEAD (inline via the Skill tool, or "
        "NEEDS_NEXT) - a bare prohibition leaves it with no legal move"
    )


def test_r1_makes_the_stalled_shape_recognizable_to_the_caller():
    """The reported stall arrived at the caller as a result announcing a background dispatch and a
    wait. That is not one of the four terminal statuses, so the caller must be told to read it as
    STALLED rather than as work in progress or as done."""
    low = _norm(R0R1R3_SSOT).lower()
    assert "stall" in low, "R1 must name the STALL outcome"
    assert re.search(r"running in the\s*background", low), (
        "R1 must describe the shape by what it says - that the dispatched work is running in the "
        "background - or a caller cannot match it against a real result"
    )
    assert re.search(r"carries no terminal `status`", low), (
        "R1 must tie the recognition to the release condition: the announcement carries no "
        "terminal status"
    )
    for action in (r"re-dispatch", r"blocked"):
        assert re.search(action, low), (
            f"R1 must give the caller an action for the stalled shape ({action})"
        )
    assert re.search(r"never inherit it as your own `done`", low), (
        "R1 must forbid the caller from laundering a stalled child into its own DONE"
    )


# ---------------------------------------------------------------------------
# 3. Worker side - the three traps, stated as consequences in R3.
# ---------------------------------------------------------------------------


def test_r3_states_the_inbound_sender_is_a_label_not_an_address():
    """An inbound message shows a bare agent TYPE where a reply address would be, and messaging-tool
    documentation invites copying it into a reply. R3 must overrule that explicitly."""
    low = _norm(R0R1R3_SSOT).lower()
    assert "`from`" in low, "R3 must name the inbound field by its literal key"
    idx = low.find("`from`")
    window = low[max(0, idx - 200):idx + 320]
    assert "type label" in window or "label, not an address" in window, (
        "R3 must say what the from value actually is: a TYPE label, not an address"
    )
    assert "does not resolve" in window or "fails" in window, (
        "R3 must state the outcome of replying to it - the send does not resolve"
    )
    assert "documentation" in window, (
        "R3 must overrule the tool documentation that tells an agent to reply to the sender - "
        "without that, the agent follows the documentation it can see over the rule it cannot"
    )


def test_r3_states_no_address_lookup_exists_for_a_worker():
    """The stranded worker's next move is to look the address up. Nothing lists agents for it, at
    any depth - and a rule that never says so leaves it hunting."""
    low = _norm(R0R1R3_SSOT).lower()
    assert re.search(r"no listing, no directory, no name-to-address lookup", low), (
        "R3 must state that no listing / directory / name-to-address lookup is available"
    )
    idx = low.find("no listing, no directory")
    window = low[idx:idx + 200]
    assert "worker" in window and ("three" in window or "depth" in window or "root" in window), (
        "the no-lookup fact must be stated for a worker at ANY depth, not only one level down"
    )


def test_r3_states_that_a_send_to_main_succeeds_and_misroutes():
    """The load-bearing correction. `main` is NOT in the list of targets that fail: from a nested
    position the send is ACCEPTED, lands on the root, and the launcher that is blocking never
    wakes. Filed as a prohibition among failures, the rule loses to the success receipt the agent
    can see with its own eyes."""
    norm = _norm(R0R1R3_SSOT)
    low = norm.lower()

    # The enumeration of targets that genuinely fail must NOT include `main`.
    idx = low.find("does not resolve and the send fails")
    assert idx != -1, "R3 must still enumerate the targets that genuinely fail to resolve"
    fail_sentence = low[max(0, idx - 260):idx]
    assert "main" not in fail_sentence, (
        "`main` must not be listed among the targets that 'does not resolve and the send fails' - "
        "it resolves, which is exactly why filing it there gets the rule disbelieved"
    )

    assert re.search(r"because it does not\s*\n?\s*fail|because it does not fail", low), (
        "R3 must state plainly that the `main` send does NOT fail"
    )
    assert "accepted and delivered to the root" in low, (
        "R3 must state where the message actually goes: accepted and delivered to the root"
    )
    assert re.search(r"not waiting for you", low), (
        "R3 must state that the root is not the context waiting for the result"
    )
    assert re.search(r"success is never evidence", low), (
        "R3 must invert the evidence: a successful send is never evidence the return path was "
        "found - without this the agent trusts the receipt over the rule"
    )


def test_chp_tier_a_is_gated_on_being_the_root():
    """Tier A is a resume SEND with no synchronous return, so it pays off only where something
    resumes the sender. Offering it to a dispatched context is offering a stall."""
    low = _norm(CHP_MD).lower()
    idx = low.find("## tier a")
    assert idx != -1, "context-handoff-protocol.md must still carry the Tier A section"
    window = low[idx:idx + 1400]
    assert "all three" in window, (
        "Tier A's precondition list must have grown to three conditions - two conditions is the "
        "version that let a dispatched context take Tier A"
    )
    assert "root conversation" in window, (
        "Tier A's third condition must be that the caller is the ROOT conversation"
    )
    assert "unreachable" in window or "never wake" in window, (
        "Tier A must state the consequence below the root - not slower, unreachable"
    )
    assert "only the root conversation is ever resumed" in low, (
        "the async-park section must own the fact Tier A's third condition rests on"
    )
