"""Whole-tree guard: a dispatched agent's report is its FINAL MESSAGE, and nothing anywhere
instructs it to send that report upward.

Behavior protected: the launch call's own return value is the harness-designed child->parent
return path. A launch call cannot name the agent it starts, and the roster an agent is shown
contains neither itself nor its launcher - so an instruction to "push your report to your
launcher" asks for a value that cannot exist. An agent following it either guesses (silent
misdelivery to a context that is not blocking on it) or stalls waiting to be told an address.

These guards are deliberately SHAPE-based over the WHOLE scanned tree with normalized whitespace,
never a filename allowlist and never one sentence: this repo's known failure mode is a guard bound
to a single phrasing going green while every other phrasing survives untouched. Each absence
assertion is paired with a presence assertion on the single SSOT, so "delete the rule everywhere"
cannot pass. The presence assertions DO pin two sentences verbatim, deliberately: the declaring
sentence is the identity marker the single-home guard counts, so a synonym there is exactly the
drift being guarded against.

Two mechanics make the shape match hold up:

* The delivery verb is matched in IMPERATIVE / second-person form only, so a description of what
  the RUNTIME does ("a background launch delivers it to the launcher") is not read as an
  instruction to the agent, while "push/send/deliver ... to your launcher" is.
* A prohibition exempts a match only when it BINDS it - same sentence, ahead of the verb. A
  prohibition merely floating somewhere in the surrounding window exempts nothing, because that is
  how a guard goes green while the defect two sentences later survives.

Run: python -m pytest tests/test_return_path_contract.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS = REPO_ROOT / "plugins"
ODOO_PLUGIN = PLUGINS / "odoo-ai-agents"
GIT_TOOLKIT = PLUGINS / "git-toolkit"
# Repo-root agent-facing prose. docs/authoring-skills-and-agents.md is the file every NEW skill and
# agent is authored from, so a rule broken there propagates into everything written next.
ROOT_DOCS = REPO_ROOT / "docs"

R3_SSOT = ODOO_PLUGIN / "snippets" / "spawner-completion-contract.md"
WORKER_BRIEF = ODOO_PLUGIN / "snippets" / "worker-brief.md"
GIT_TOOLKIT_SSOT = GIT_TOOLKIT / "snippets" / "completion-reporting.md"

# Generated regions are emitted from a separate SSOT and are not hand-authored prose; blank them
# so a generated echo of a fixed upstream string cannot mask (or fabricate) a finding here.
_GENERATED_RE = re.compile(
    r"<!--\s*BEGIN GENERATED TOOLS\s*-->.*?<!--\s*END GENERATED TOOLS\s*-->", re.S
)

# One deliberate set shared by every whole-tree guard in this repo: prose (.md), declarative
# workflow/config (.yaml/.yml/.json - incl. the generator's SSOT registries), and the executable
# surface that also carries agent-facing prose in comments (.py generators, .sh setup steps).
SCAN_ROOTS = (PLUGINS, ROOT_DOCS)
_SCANNED_SUFFIXES = (".md", ".yaml", ".yml", ".json", ".py", ".sh")


def _scan_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        for suffix in _SCANNED_SUFFIXES:
            files.extend(root.rglob(f"*{suffix}"))
    return sorted(p for p in files if ".venv" not in p.parts)


SCANNED = _scan_files()


def _norm_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    raw = _GENERATED_RE.sub(" ", raw)
    return " ".join(raw.split())


NORMALIZED: dict[Path, str] = {p: _norm_text(p) for p in SCANNED}


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _windows(text: str, pattern: re.Pattern[str], radius: int):
    for m in pattern.finditer(text):
        yield text[max(0, m.start() - radius): m.end() + radius]


# ---------------------------------------------------------------------------
# Discovery floor - a broken glob makes every scan below vacuously green.
# ---------------------------------------------------------------------------


def test_scan_corpus_discovered():
    assert len(SCANNED) >= 200, (
        f"expected >=200 scanned prose files under plugins/, found {len(SCANNED)} - the glob is "
        "wrong, so every whole-tree assertion below would pass for the wrong reason"
    )


# ---------------------------------------------------------------------------
# 1. Nothing instructs a child to deliver its report to its launcher, in ANY
#    phrasing. Matched as a co-occurrence SHAPE (a delivery verb + an upward
#    recipient) inside one window, not as a single sentence.
# ---------------------------------------------------------------------------

# Base/imperative form ONLY, and only where a sentence start or a second-person / modal lead-in
# makes it an INSTRUCTION. An inflected third-person form ("a background launch delivers it") is
# describing the runtime, not telling the agent to act, and must not be read as the defect.
_DELIVERY_VERB_RE = re.compile(
    r"(?:^|[.;:!?)\]]\s+|\*\*|\b(?:you|then|and|or|also|must|should|shall|always|please|may|can|"
    r"to|will|it|they|we)\s+)"
    r"(push|send|deliver|relay|forward|hand off|hand back|post|notify|message|escalate|"
    r"report back|report to|report up)\b",
    re.I,
)
# These verbs carry the report as their own object, so they need no separate report noun nearby.
_REPORT_VERB_RE = re.compile(r"^report (?:back|to|up)$", re.I)
# OPEN shapes, not a closed phrase list: any possessive/definite upward role, and any
# "the <thing> that dispatched/launched/spawned/invoked you" construction.
_UPWARD_RECIPIENT_RE = re.compile(
    r"(your (?:own )?(?:launcher|caller|parent|spawner|orchestrator|lead|dispatcher|invoker)|"
    r"the (?:launcher|caller|parent|spawner|orchestrator|lead|dispatcher|invoker)\b|"
    r"its (?:launcher|caller|parent|spawner|orchestrator)|the orchestrating skill|"
    r"the caller/context|<caller>|REPLY_TO|CALLER_ID|a grand-?parent|"
    r"the \w+(?: \w+)? that (?:dispatched|launched|spawned|invoked) you|"
    r"the (?:dispatching|launching|spawning|invoking|calling|parent|upstream|orchestrating) "
    r"(?:agent|skill|context|coordinator|caller|orchestrator)|"
    r"whoever (?:dispatched|launched|invoked) you|(?:up )?to (?:the literal )?`?main`?\b)",
    re.I,
)
_REPORT_NOUN_RE = re.compile(
    r"(completion report|completion-report|your report|the report|a report|its report|"
    r"result block|findings block|your findings|your result|your status)",
    re.I,
)
# A prohibition exempts a match only when it BINDS that match: same sentence, ahead of the verb.
_PROHIBITION_RE = re.compile(
    r"(never|cannot|can not|no agent can|must not|do not|don't|does not|is not|"
    r"not an instruction|is malformed|retired|no upward channel|no legal)",
    re.I,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;:!?])\s+")


def _sentence_span(text: str, pos: int) -> tuple[int, int]:
    """Bounds of the sentence containing `pos`, computed over the FULL text (never a window, so a
    window edge cannot fabricate or hide a sentence boundary)."""
    start = 0
    for m in _SENTENCE_SPLIT_RE.finditer(text, 0, pos):
        start = m.end()
    m = _SENTENCE_SPLIT_RE.search(text, pos)
    return start, (m.start() if m else len(text))


def _prohibition_binds(text: str, verb_pos: int) -> bool:
    """A prohibition governs this verb only if it sits in the SAME sentence - either ahead of the
    verb ("never send your report ..."), or immediately behind it as the predicate that voids the
    clause ("... asks you to push a report, is malformed"). A prohibition merely floating in the
    surrounding window governs nothing: that is the exemption that let 3 in 4 windows self-clear."""
    sent_start, sent_end = _sentence_span(text, verb_pos)
    ahead = text[sent_start:verb_pos]
    behind = text[verb_pos:min(sent_end, verb_pos + 60)]
    return bool(_PROHIBITION_RE.search(ahead) or _PROHIBITION_RE.search(behind))


def _report_push_offenders(text: str) -> list[tuple[str, str]]:
    """Every un-exempted (verb, window) pair where the text tells an agent to deliver its report
    to something above it."""
    found = []
    for rm in _UPWARD_RECIPIENT_RE.finditer(text):
        lo = max(0, rm.start() - 160)
        window = text[lo: rm.end() + 160]
        has_noun = bool(_REPORT_NOUN_RE.search(window))
        for vm in _DELIVERY_VERB_RE.finditer(window):
            verb = vm.group(1)
            if not (has_noun or _REPORT_VERB_RE.match(verb)):
                continue
            if _prohibition_binds(text, lo + vm.start(1)):
                continue  # the prohibition governs this verb - this IS the rule
            found.append((verb, window.strip()[:240]))
            break
    return found


def test_no_file_instructs_a_report_push_to_a_launcher():
    """Any window pairing an IMPERATIVE delivery verb with an upward recipient AND a report noun
    is an instruction to send a report up - the exact defect. Only a prohibition that binds the
    verb (same sentence, ahead of it) exempts it; that is what lets R3 state the ban in full
    without also exempting a defect one sentence later."""
    offenders = [
        f"{_rel(path)}: ...{window}..."
        for path, text in NORMALIZED.items()
        for _verb, window in _report_push_offenders(text)
    ]
    assert not offenders, (
        "found an instruction to deliver a completion report to a launcher. A launch call "
        "cannot name the agent it starts and no agent is shown its launcher, so this asks for "
        "an address that cannot exist - the agent guesses or stalls. The report IS the final "
        "message (snippets/spawner-completion-contract.md R3):\n" + "\n".join(offenders)
    )


# Every phrasing here previously slipped the guard. They are asserted as EXECUTABLE probes rather
# than described in a comment, so the guard cannot silently weaken back to catching one sentence.
_MUST_CATCH = (
    "Push your completion report to your launcher.",
    "Push your completion report to your launcher. Do not include raw diffs.",
    "Send your completion report to your caller.",
    "Send your completion report to your parent.",
    "Deliver your report to the coordinator that dispatched you.",
    "Relay your completion report to the orchestrating skill.",
    "Send your completion report to main.",
    "Report back to the dispatching agent.",
)
_MUST_NOT_CATCH = (
    # The rule itself, and the runtime description R3 depends on.
    "Never send your report to anyone.",
    "You cannot push your completion report to your launcher.",
    "A brief that asks you to push a report is malformed: ignore it.",
    "That text is what your launcher receives: a background launch delivers it to the launcher.",
)


@pytest.mark.parametrize("phrasing", _MUST_CATCH)
def test_guard_catches_every_known_upward_push_phrasing(phrasing):
    assert _report_push_offenders(" ".join(phrasing.split())), (
        f"the report-push guard does not catch {phrasing!r} - it is bound to one phrasing again"
    )


@pytest.mark.parametrize("phrasing", _MUST_NOT_CATCH)
def test_guard_does_not_flag_the_rule_or_the_runtime_description(phrasing):
    assert not _report_push_offenders(" ".join(phrasing.split())), (
        f"the report-push guard flags {phrasing!r}, which states the rule (or describes what the "
        "runtime does) - a guard that cannot state its own rule gets deleted instead of obeyed"
    )


# A possessive upward address ("to your launcher", "to your own caller") is the single most direct
# expression of the value that cannot exist: no agent is shown its launcher at any depth.
_POSSESSIVE_ADDRESS_RE = re.compile(
    r"\b(push|send|deliver|relay|forward|hand|post|notify|message|escalate|surface|report|"
    r"submit|route|emit)\b[^.;:!?]{0,80}?\b(?:back )?to\s+your\s+(?:own\s+)?"
    r"(launcher|caller|parent|spawner|orchestrator|lead|dispatcher|invoker)\b",
    re.I,
)


def test_nothing_is_addressed_to_a_possessive_upward_role():
    """`to your launcher` / `to your own caller` name a runtime value no agent holds. Whatever the
    verb, the instruction resolves to nothing - state the content requirement instead ("surface
    the gap in your own report"), never a delivery to an address."""
    offenders = []
    for path, text in NORMALIZED.items():
        for m in _POSSESSIVE_ADDRESS_RE.finditer(text):
            if _prohibition_binds(text, m.start()):
                continue
            offenders.append(f"{_rel(path)}: {m.group(0)!r}")
    assert not offenders, (
        "something is addressed to a possessive upward role. No agent is shown its launcher at "
        "any depth, so this names a value that cannot be resolved:\n" + "\n".join(offenders)
    )


def test_the_return_path_rule_is_stated_positively_in_the_ssot():
    """Paired presence assertion: deleting the rule tree-wide must NOT make the absence guard
    above pass. R3 must carry the positive statement."""
    low = _norm_text(R3_SSOT).lower()
    assert "your completion report is the final text of your turn" in low, (
        "spawner-completion-contract.md R3 must state the return path positively"
    )
    assert "never send your report to anyone" in low, (
        "spawner-completion-contract.md R3 must state the prohibition positively"
    )


# ---------------------------------------------------------------------------
# 2. The reply-address field is retired, not renamed.
# ---------------------------------------------------------------------------

_RETIREMENT_MARKER_RE = re.compile(
    r"(retired|no reply-address field|no reply field needed)", re.I
)

# A SHAPE, not four literals: any ALL-CAPS brief key naming an UPWARD role plus an address-ish
# suffix. `REPORT_TO` / `PARENT_ID` / `LAUNCHER_ADDRESS` are the same field under a new name, and a
# rename is exactly how a retired primitive comes back. `WORKER_AGENT_ID` (a DOWNWARD id the caller
# captured from its own launch) has no upward role prefix and is unaffected.
_UPWARD_FIELD_RE = re.compile(
    r"\b(REPLY|CALLER|PARENT|LAUNCHER|SPAWNER|LEAD|UPSTREAM|ORCHESTRATOR|DISPATCHER|INVOKER|"
    r"REPORT|RESPOND|NOTIFY|SENDER|GRANDPARENT)_"
    r"(?:TO|ID|ADDR|ADDRESS|NAME|HANDLE|AGENT_ID|TARGET)\b"
)


def test_reply_address_field_is_retired_tree_wide():
    """An upward-address brief key may appear in exactly ONE file - the R3 SSOT - and only inside
    a sentence that retires it. `TASK_ID`/`NOTIFY` (the task-board keys that rode the same
    channel) must appear nowhere at all."""
    token_re = _UPWARD_FIELD_RE
    offenders = []
    for path, text in NORMALIZED.items():
        for m in token_re.finditer(text):
            if path != R3_SSOT:
                offenders.append(f"{_rel(path)}: names {m.group(1)}")
                continue
            window = text[max(0, m.start() - 120): m.end() + 120]
            if not _RETIREMENT_MARKER_RE.search(window):
                offenders.append(
                    f"{_rel(path)}: names {m.group(1)} outside a retirement statement"
                )
    assert not offenders, (
        "an upward-address brief key survives. The field is retired, NOT renamed - a dispatched "
        "agent's report is its final message, so there is nothing for such a key to hold:\n"
        + "\n".join(offenders)
    )

    board_offenders = [
        f"{_rel(path)}: names {m.group(0)}"
        for path, text in NORMALIZED.items()
        for m in re.finditer(r"\b(TASK_ID|NOTIFY:)\b", text)
    ]
    assert not board_offenders, (
        "a task-board brief key survives; those rode the retired upward channel:\n"
        + "\n".join(board_offenders)
    )


# ---------------------------------------------------------------------------
# 3. The rule is DECLARED in exactly the files that own it; every other file
#    that states it must cite the SSOT in the same breath.
# ---------------------------------------------------------------------------

_DECLARING_SENTENCE = "your completion report is the final text of your turn"


def test_return_path_rule_declared_exactly_once_per_plugin():
    """Each plugin has exactly one declaring home for this sentence, plus (in odoo-ai-agents)
    the worker-side restatement that immediately defers to it. A third copy is drift waiting to
    happen; zero copies means the rule was deleted."""
    declarers = sorted(
        p for p, text in NORMALIZED.items() if _DECLARING_SENTENCE in text.lower()
    )
    expected = sorted([R3_SSOT, WORKER_BRIEF, GIT_TOOLKIT_SSOT])
    assert declarers == expected, (
        "the declaring sentence must live in exactly the SSOT files "
        f"{[_rel(p) for p in expected]}, found {[_rel(p) for p in declarers]}"
    )
    # The worker-side copy is legal ONLY because it defers to R3 in the same file.
    assert "spawner-completion-contract.md" in NORMALIZED[WORKER_BRIEF], (
        "worker-brief.md restates the rule, so it must cite the R3 SSOT in the same file"
    )


# ---------------------------------------------------------------------------
# 4. Every surviving send is justified as a DOWNWARD resume by a captured id.
# ---------------------------------------------------------------------------

_MESSAGING_TOOL_RE = re.compile(r"\bSendMessage\b")
_DOWNWARD_JUSTIFICATION_RE = re.compile(
    r"(id that child's own launch call returned|id your own launch returned|"
    r"recorded id|launch call's return value|no reply field needed|resume that id)",
    re.I,
)


def test_send_target_is_always_an_id_from_your_own_launch():
    """Positive-justification requirement, not an allowlist: every surviving mention of the
    messaging tool must sit next to the ONE address source that exists."""
    offenders = []
    for path, text in NORMALIZED.items():
        for window in _windows(text, _MESSAGING_TOOL_RE, 200):
            if _DOWNWARD_JUSTIFICATION_RE.search(window):
                continue
            offenders.append(f"{_rel(path)}: ...{window.strip()[:240]}...")
    assert not offenders, (
        "a messaging-tool mention is not justified by the only address any agent holds - the id "
        "its own launch call returned for a child it launched:\n" + "\n".join(offenders)
    )


# Not one byte-template: any `to:` field whose value is `main` in ANY quoting/terminator style, any
# messaging-call literal with a `to:` field at all, and any prose that directs a delivery verb at
# `main`. The previous form required a trailing `,` or `}`, so deleting one character defeated it.
_MAIN_TARGET_RE = re.compile(
    r"""to:\s*["'`]?main["'`]?\b"""
    r"""|\bSendMessage\s*\(\s*\{?\s*to\s*:"""
    r"""|\b(?:push|send|deliver|relay|forward|post|notify|message|report back|report)\b"""
    r"""[^.;:!?]{0,60}?\bto\s+(?:the\s+literal\s+)?["'`]?main["'`]?\b""",
    re.I,
)


def test_literal_main_is_never_a_message_target_outside_the_r3_carve_out():
    """`main` as a MESSAGE target (not the git branch) may only appear inside R3's background
    carve-out. A bare `to: "main"` template - in any quoting style, with or without a trailing
    delimiter - is how a nested worker misdelivers past the coordinator that is blocking on it."""
    target_re = _MAIN_TARGET_RE
    offenders = [
        f"{_rel(path)}: {m.group(0)!r}"
        for path, text in NORMALIZED.items()
        for m in target_re.finditer(text)
        if not _prohibition_binds(text, m.start())
    ]
    assert not offenders, (
        "a literal `main` message-target template survives:\n" + "\n".join(offenders)
    )
    low = _norm_text(R3_SSOT).lower()
    idx = low.find("sole legal use of the literal `main`")
    assert idx != -1, (
        "R3 must still carve out the ONE legal use of the literal `main`, or the next author "
        "re-invents a worse version of it"
    )
    window = low[idx: idx + 400]
    assert "background" in window and "never sends its completion report" in window, (
        "the carve-out must be mid-run only, from an agent `main` itself launched in the "
        "background - never a completion report"
    )


# ---------------------------------------------------------------------------
# 5. ASCII hyphen only on every file this guard's SSOTs live in.
# ---------------------------------------------------------------------------

_BANNED_DASHES = {
    0x2012: "figure-dash",
    0x2013: "en-dash",
    0x2014: "em-dash",
    0x2015: "horizontal-bar",
}


@pytest.mark.parametrize("path", [R3_SSOT, WORKER_BRIEF, GIT_TOOLKIT_SSOT], ids=lambda p: p.name)
def test_ssot_files_are_ascii_hyphen_clean(path):
    body = path.read_text(encoding="utf-8")
    offenders = [
        f"{path.name}: contains {label} (U+{cp:04X})"
        for cp, label in _BANNED_DASHES.items()
        if chr(cp) in body
    ]
    assert not offenders, "typographic dashes found:\n" + "\n".join(offenders)
