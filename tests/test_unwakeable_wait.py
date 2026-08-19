"""Whole-tree guard: nothing tells a dispatcher to keep working after it launches, and the SSOT
states why a worker's apparent ways back up are not ways back up.

Behavior protected - two halves of one stall:

  COORDINATOR SIDE. Every launch is asynchronous, and the launcher is woken with the child's result
  when the child completes AND the launcher has ENDED ITS TURN. That wake is keyed on the launcher
  having stopped, not on its depth - a nested launcher is woken by its own child exactly as the
  root is. The one way the exchange breaks is the launcher never stopping: a turn that launches and
  then carries on working offers no delivery point, so the child's report is never handed back.
  Prose that tells a dispatcher to continue working, poll, sleep, or busy-wait in the launching
  turn is therefore the defect, and this file is its whole-tree detector.

  WORKER SIDE. A worker that goes looking for its launcher finds only traps: an inbound message
  shows a TYPE label where an address would be, no lookup turns any name into one, and the literal
  `main` does not fail - it is ACCEPTED and delivered to the root conversation, which is not
  waiting, while the worker's own launcher still receives nothing but that worker's FINAL MESSAGE.
  A rule phrased only as a prohibition loses to that success receipt, so the SSOT must state the
  consequence, not just the ban.

Guards are SHAPE-based over the whole markdown tree with normalized whitespace, never a filename
allowlist and never line adjacency. Each absence guard is paired with a presence assertion on the
single SSOT so "delete it everywhere" cannot pass, and with executable must-catch / must-not-catch
probes so the shape cannot silently shrink to one spelling.

RESIDUAL FALSE NEGATIVE, stated rather than hidden: the whole-tree half is a LEXICAL proximity
check over two vocabularies (launch verbs, and keep-working verbs). A file that tells a dispatcher
to carry on in a phrasing neither list anticipates - or that implies it structurally, by ordering
steps after a dispatch without ever naming a wait - is not caught. It proves the harmful INSTRUCTION
is absent from the prose an agent is handed; it can never prove an agent obeys the rule.

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
# 1. Whole tree - nothing tells a dispatcher to keep working after it launches.
#    (The rule this enforces: R0 § END YOUR TURN after dispatching.)
# ---------------------------------------------------------------------------

# The act of dispatching. Deliberately narrow - the vocabulary this tree actually uses for an
# agent launch, not every English verb meaning "start something".
_LAUNCH_RE = re.compile(
    r"\b(launch(?:es|ed|ing)?|dispatch(?:es|ed|ing)?|spawn(?:s|ed|ing)?|fan(?:s|ned|ning)? out)\b",
    re.I,
)
# The harmful instruction: carry on inside the SAME turn instead of stopping. Two families -
# an explicit busy-wait (poll/sleep/wait in place), and an explicit "meanwhile, do more work".
_KEEP_WORKING_RE = re.compile(
    # Polling is only this defect when what is polled is a dispatched actor - `poll the CI` is a
    # different, legitimate loop, so the bare object form is spelled out rather than left open.
    r"(poll(?:s|ing|ed)?\s+(?:for\b|until\b|"
    r"the\s+(?:child|children|worker|workers|teammate|teammates|agents?|leaf|sub-?agent))|"
    r"sleep\s+(?:until|while|for)|busy-?wait|"
    r"in the meantime|meanwhile,?\s|while (?:you|it|they) wait|while waiting|"
    r"(?:keep|carry on|continue|press on)\s+(?:working|going|on with)|"
    # Only the turn-scoped negation - a bare "do not stop <doing X>" is ordinary emphasis.
    r"(?:do not|don't) end (?:your|the|its) turn|without ending (?:your|the|its) turn)",
    re.I,
)
# What makes the pairing legal: the same window either instructs the stop, or negates the harmful
# shape outright. Both spellings matter - a rule stated as a prohibition is as good as one stated
# as an instruction, and this guard must not force one house style onto the other.
_END_TURN_RE = re.compile(
    r"(end(?:s|ing)? (?:your|its|his|her|their|the) turn|END YOUR TURN|END ITS TURN|END THE TURN|"
    r"park-and-be-resumed|stop(?:s|ping)? (?:your|its|the) turn|emit(?:s)? .{0,40}and stops?)",
    re.I,
)
_NEGATED_RE = re.compile(
    r"(never (?:poll|sleep|re-?launch|do a child|keep working|start doing)|"
    r"do NOT (?:poll|sleep|re-?launch|keep working)|"
    r"not (?:a poll|a park)|never a poll|"
    r"\bis (?:the |a )?(?:one )?(?:defect|failure mode)|"
    r"never correct|must not keep working|do not keep working)",
    re.I,
)
# A negation sitting immediately in front of an end-turn phrase INVERTS it: "do not end your turn"
# is the defect, not the remedy. Without this the exemption regex would launder the very
# instruction it exists to catch.
_NEG_BEFORE_STOP_RE = re.compile(r"(do not|don'?t|never|without|instead of|rather than)\s*$", re.I)


def _end_turn_instructed(window: str) -> bool:
    """True iff the window carries an end-turn instruction that is not itself negated."""
    return any(
        not _NEG_BEFORE_STOP_RE.search(window[max(0, m.start() - 24):m.start()])
        for m in _END_TURN_RE.finditer(window)
    )

# The pairing has to be tight: a launch verb and a keep-working instruction in the SAME breath.
# A launch verb three paragraphs from an unrelated "in the meantime" is not this defect.
_PAIR_WINDOW = 160
# The exemption reads wider - a stop instruction or a negation anywhere in the surrounding prose
# governs the sentence.
_EXEMPT_WINDOW = 400


def _keep_working_offenders(text: str) -> list[str]:
    """Windows that pair a dispatch with an instruction to keep working in the same turn, with no
    stop instruction and no negation governing them."""
    found = []
    for m in _KEEP_WORKING_RE.finditer(text):
        pair = text[max(0, m.start() - _PAIR_WINDOW): m.end() + _PAIR_WINDOW]
        if not _LAUNCH_RE.search(pair):
            continue  # a wait that has nothing to do with a dispatched child
        window = text[max(0, m.start() - _EXEMPT_WINDOW): m.end() + _EXEMPT_WINDOW]
        if _end_turn_instructed(window) or _NEGATED_RE.search(window):
            continue
        found.append(window.strip()[:280])
    return found


def test_no_file_tells_a_dispatcher_to_keep_working_after_it_launches():
    offenders = [
        f"{_rel(path)}: ...{w}..."
        for path, text in NORMALIZED.items()
        for w in _keep_working_offenders(text)
    ]
    assert not offenders, (
        "a dispatcher is told to keep working, poll, or busy-wait in the same turn as its launch. "
        "The wake that delivers a child's result fires only when the LAUNCHER has stopped, so a "
        "turn that launches and carries on has no delivery point at all and the result is never "
        "handed back (snippets/spawner-completion-contract.md R0 § END YOUR TURN after "
        "dispatching / R1 Boundary):\n" + "\n".join(offenders)
    )


# Executable probes so the shape cannot quietly shrink back to catching one spelling.
_MUST_CATCH = (
    "Launch the worker agent, then keep working on the next node in the meantime.",
    "After you dispatch the coder, poll for its result until it lands.",
    "Dispatch the test-writer and carry on with the frontend work while you wait.",
    "Spawn the four surveyors; meanwhile, read the manifests yourself.",
    "Launch the teammate but do not end your turn - stay available for the next instruction.",
)
_MUST_NOT_CATCH = (
    # The corrected rule, in each of its legal spellings.
    "Launch the whole batch in ONE message, END YOUR TURN, and consume each result when you are "
    "woken with it.",
    "After you dispatch, END YOUR TURN. Never poll, never sleep, never re-launch.",
    "Keep working in the launching turn instead and no delivery point ever exists - that is the "
    "one failure mode of nested dispatch.",
    # Waits that are not about a dispatched child at all.
    "Present the options and END THE TURN; the human answers on the next turn.",
    "In the meantime the user reviews the plan and answers on their own schedule.",
)


@pytest.mark.parametrize("phrasing", _MUST_CATCH)
def test_guard_catches_every_known_keep_working_phrasing(phrasing):
    assert _keep_working_offenders(" ".join(phrasing.split())), (
        f"the keep-working guard does not catch {phrasing!r} - it is bound to one phrasing again"
    )


@pytest.mark.parametrize("phrasing", _MUST_NOT_CATCH)
def test_guard_allows_the_end_the_turn_and_human_gated_shapes(phrasing):
    assert not _keep_working_offenders(" ".join(phrasing.split())), (
        f"the keep-working guard flags {phrasing!r}. Ending the turn after a dispatch, and a wait "
        "on a human, are both legal; only carrying on inside the launching turn is the defect"
    )


# ---------------------------------------------------------------------------
# 2. Coordinator side, stated positively in the SSOT.
# ---------------------------------------------------------------------------


def test_r0_states_there_is_no_blocking_launch_to_reach_for():
    """WHAT IT REQUIRED BEFORE: that R0 declare a subagent's launch REFUSED at the call, so a
    subagent may never dispatch at all. That premise is retired - nested dispatch works, and a
    nested launcher is woken by its own child.

    WHAT IT REQUIRES NOW: the one measured absence stays stated - there is no foreground/blocking
    launch parameter - because a reader who is told nothing tries the parameter they half-remember
    and falls through to whatever the next rung says. The retired branch must still be named as
    retired, and a stale "launch it blocking" instruction met in another file must be explicitly
    overridden."""
    low = _norm(R0R1R3_SSOT).lower()
    assert re.search(r"no foreground or blocking parameter", low), (
        "R0 must state outright that no foreground/blocking launch parameter exists"
    )
    assert re.search(r"there is no move 2", low), (
        "the retired branch must be named as retired, or every surviving 'R0 move 2' citation "
        "elsewhere silently re-points at whatever now occupies that slot"
    )
    assert re.search(r"names a lever that does not exist", low), (
        "R0 must tell a reader what to DO with a stale 'launch it blocking' instruction it meets "
        "in another file - ignore it - not merely avoid emitting one itself"
    )


def test_r0_makes_ending_the_turn_the_delivery_point_at_every_depth():
    """WHAT IT REQUIRED BEFORE (as `test_r0_scopes_the_async_park_to_the_root`): that R0 scope
    resumption to the ROOT conversation and tell a subagent "nothing resumes you". Both are
    falsified - the wake is keyed on the LAUNCHER having stopped, not on its depth.

    WHAT IT REQUIRES NOW: R0 states the depth-independence, names ending the turn as the delivery
    point, and states the consequence of not stopping - because the launcher that keeps working is
    the only shape that actually loses a result."""
    low = _norm(R0R1R3_SSOT).lower()
    assert re.search(r"this holds at every depth", low), (
        "R0 move 3 must state that the launch-and-be-woken shape holds at EVERY depth - a scoping "
        "to the root is the refuted claim"
    )
    assert re.search(r"a nested launcher is woken by its own child", low), (
        "R0 must say plainly that a nested launcher IS woken by its own child"
    )
    assert re.search(r"stopping is the delivery point", low), (
        "R0 must name what actually delivers the result: the launcher stopping"
    )
    assert re.search(r"no delivery point ever exists", low), (
        "R0 must state the consequence of carrying on in the launching turn - without it the rule "
        "reads as a style preference"
    )
    assert not re.search(r"only the root conversation is resumed", low), (
        "the refuted scoping must be gone, not softened - a surviving copy is what produced the "
        "incident this rewrite reverses"
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


def test_chp_tier_a_is_gated_on_holding_the_id_not_on_depth():
    """WHAT IT REQUIRED BEFORE (as `test_chp_tier_a_is_gated_on_being_the_root`): a THIRD Tier-A
    precondition - "you are the ROOT conversation" - plus the sentence "only the root conversation
    is ever resumed". Both encode the refuted claim that a nested launcher cannot be woken.

    WHAT IT REQUIRES NOW: Tier A is gated on the two things that are actually true - you hold the
    id your own launch returned, and you have a messaging tool - and the section states plainly
    that depth is NOT a condition while ending the turn IS."""
    low = _norm(CHP_MD).lower()
    idx = low.find("## tier a")
    assert idx != -1, "context-handoff-protocol.md must still carry the Tier A section"
    window = low[idx:idx + 1400]
    assert "both are" in window or "both conditions" in window, (
        "Tier A's precondition list must be the two real ones - a third, depth-based condition is "
        "the refuted claim"
    )
    assert "your own depth is not a condition" in window, (
        "Tier A must say outright that depth does not gate it, or the deleted condition grows back"
    )
    assert "end your turn" in window, (
        "Tier A must name the one thing that IS required for the result to reach you: ending the "
        "turn after the send"
    )
    assert "only the root conversation is ever resumed" not in low, (
        "the refuted scoping sentence must be deleted from the CHP, not merely unreferenced"
    )
