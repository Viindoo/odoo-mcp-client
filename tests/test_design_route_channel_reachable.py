"""Guard: a design-first recommendation must ride a channel the driver actually READS.

## The contract's reachability rule (this file's whole basis)

`snippets/continuation-contract.md` Rules, back-compat bullet, and its implementation at
`hooks/parse-continuation.sh:46`:

    if [[ -z "$STATUS" ]] && grep -qiE '^[[:space:]]*SUGGESTED_NEXT:' ; then STATUS="NEEDS_NEXT" ; fi

The back-compat branch is guarded on `-z "$STATUS"` - it fires ONLY while the fenced
`continuation` block's own `status` is EMPTY. So the rule is:

    a bare `SUGGESTED_NEXT:` line is REACHABLE  <=>  the emitter sets no `status`
    a bare `SUGGESTED_NEXT:` line is DROPPED    <=>  the emitter sets a `status`

Every skill/agent that appends a Continuation Contract sets a `status` (the four-value enum is
mandatory in that snippet), so for those files the bare channel is unreachable BY CONSTRUCTION.
Two design-routing sites were emitting on exactly that dead channel:

* `skills/odoo-coding/SKILL.md` - "recommend `SUGGESTED_NEXT: odoo-solution-design` first" for
  fable-grade work with no design doc, while its own block always emits `next: odoo-code-review`
  plus a status.
* `skills/odoo-data-migration/SKILL.md` - the Round-1 Design-gate, same spelling, same block.

## Why this is not a grep for `next: odoo-solution-design`

That assertion would have passed on the BROKEN `SUGGESTED_NEXT:` spelling too - the skill name is
present either way. The blindness that let this survive was measuring presence instead of
reachability. Every check below is therefore keyed on the CHANNEL: which spelling carries the hop,
and whether the emitter sets a status that kills it.

A sibling guard, `test_design_precedes_planning.py`, owns the ORDER (design never after planning).
This file owns the CHANNEL (the design hop is readable at all). The two interact: a reachable
design hop is correct only on a standalone invocation, so
`test_the_design_hop_is_suppressed_under_a_plan` asserts the suppression that keeps this fix from
undoing that one.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

CONTRACT = PLUGIN / "snippets" / "continuation-contract.md"
PARSER = PLUGIN / "hooks" / "parse-continuation.sh"

#: The two design-routing emitters this fix covers. Each recommends `odoo-solution-design` from a
#: body that also appends a Continuation Contract (hence always sets a status).
DESIGN_ROUTERS = {
    "odoo-coding": PLUGIN / "skills" / "odoo-coding" / "SKILL.md",
    "odoo-data-migration": PLUGIN / "skills" / "odoo-data-migration" / "SKILL.md",
}

DESIGN_SKILL = "odoo-solution-design"

_GENERATED = re.compile(
    r"<!-- BEGIN GENERATED TOOLS -->.*?<!-- END GENERATED TOOLS -->", re.DOTALL
)
_TEXT_EXTS = {".md", ".yaml", ".yml", ".json", ".sh"}


def _read(path: Path) -> str:
    assert path.is_file(), f"{path} is missing"
    return _GENERATED.sub("", path.read_text(encoding="utf-8"))


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _tree_texts():
    for plugin_dir in sorted((ROOT / "plugins").iterdir()):
        if not plugin_dir.is_dir():
            continue
        for path in sorted(plugin_dir.rglob("*")):
            if path.is_file() and path.suffix in _TEXT_EXTS:
                yield path, _GENERATED.sub("", path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The dead-channel detector. Pure function of text, so the probes below run the
# SAME code as the real-tree sweep.
# ---------------------------------------------------------------------------

#: Talking ABOUT the legacy channel - documenting it, forbidding it, explaining that it drops - is
#: not emitting on it. Without this the fix's own wording would report itself as the defect.
_DISCLAIMED = re.compile(
    r"(?i)do not emit a bare|never a bare|never as a bare|superseded|silently drop"
    r"|back-?compat|legacy|nothing advances|never both channels|unreachable|never reach"
    r"|cannot carry|reaches nobody|status.{0,30}is EMPTY|only while.{0,40}status"
)

def _routable_names() -> frozenset[str]:
    """Every skill and agent name on disk, resolved from the tree (never hardcoded).

    A `SUGGESTED_NEXT:` line is only a ROUTING payload when what follows it is a real dispatch
    target. Keying on that (rather than "any lowercase word") is what stops the shape flagging the
    contract's own sentence "a bare `SUGGESTED_NEXT:` line is silently dropped".
    """
    names: set[str] = set()
    for plugin_dir in (ROOT / "plugins").iterdir():
        if not plugin_dir.is_dir():
            continue
        skills = plugin_dir / "skills"
        if skills.is_dir():
            names.update(p.name for p in skills.iterdir() if (p / "SKILL.md").is_file())
        agents = plugin_dir / "agents"
        if agents.is_dir():
            names.update(p.stem for p in agents.glob("*.md"))
    return frozenset(names)


ROUTABLE = _routable_names()
_ROUTABLE_ALT = "|".join(sorted(map(re.escape, ROUTABLE), key=len, reverse=True))

#: Each entry is (shape, regex, disclaimer_exempt). `disclaimer_exempt=False` means NO nearby
#: prohibition can excuse the match: that shape is inherently a positive instruction, and the
#: alternative - exempting it - is how an offender written next to the ban's own wording gets
#: laundered (this is not hypothetical; mutation R6 slipped through exactly that way before the
#: flag existed).
DEAD_CHANNEL_SHAPES: tuple[tuple[str, re.Pattern[str], bool], ...] = (
    # The original spelling: a bare `SUGGESTED_NEXT:` carrying a real dispatch target. NEVER
    # disclaimer-exempt - naming an actual skill/agent after the legacy token is the emission
    # itself, and no prohibition in the neighbourhood changes that. (The contract and the harness
    # doc document the legacy form with a `<skill>` PLACEHOLDER, which is why they stay silent.)
    ("bare-suggested-next-payload",
     re.compile(rf"SUGGESTED_NEXT:\s*`?(?:{_ROUTABLE_ALT})\b"), False),
    # An instruction verb pointed at the legacy channel.
    ("instructed-to-emit-suggested-next",
     re.compile(r"(?i)\b(?:recommend|emit|add|append|output|return|surface|write)\b[^.]{0,120}?"
                r"`?SUGGESTED_NEXT"), True),
    # The legacy channel offered as an equal alternative to the in-block form.
    ("suggested-next-as-alternative",
     re.compile(r"(?i)`?next`?\s*/\s*`?SUGGESTED_NEXT|`?SUGGESTED_NEXT`?\s*/\s*`?next`?"), True),
    # A hop placed OUTSIDE the fenced block while a status is set - the same drop, spelled without
    # the legacy token at all. Never disclaimer-exempt: there is no legitimate reason to describe
    # putting a `next` hop outside the block the driver parses.
    ("hop-outside-the-fenced-block",
     re.compile(r"(?i)(?:outside|below|alongside|separate from) the fenced(?: `?continuation`?)?"
                r" block[^.]{0,160}?\bnext\b"
                r"|\bnext:[^.\n]{0,80}?\b(?:outside|not inside) the fenced"), False),
)

#: A sentence ends at a period followed by whitespace OR by closing markdown emphasis/bracket
#: (`.**`, `.)`, `.` + backtick). Without the markup characters a bold lead-in like
#: `**... never a bare line.**` stays inside the window and its own prohibition launders the rest
#: of the paragraph - mutation R6b slipped through exactly that way.
_SENTENCE_BREAK = re.compile(r"\.[\s)*_`\"']|\n\s*\n")


def _sentence_window(text: str, start: int, end: int) -> str:
    """The SENTENCE containing the match, not a fixed character radius.

    A fixed radius lets a prohibition three sentences away excuse a live instruction. The four
    correctly-fixed agents all write their disclaimer in the SAME sentence as the token
    ("... - do not emit a bare `SUGGESTED_NEXT:` line, superseded by the in-block form"), so the
    sentence is the right unit and it cannot be gamed by adjacency.
    """
    lo = 0
    for m in _SENTENCE_BREAK.finditer(text, 0, start):
        lo = m.end()
    hi = len(text)
    m = _SENTENCE_BREAK.search(text, end)
    if m:
        hi = m.end()
    return text[lo:hi]


def find_dead_channels(text: str) -> list[tuple[str, str]]:
    """Every (shape, match) that ROUTES on a channel the driver drops."""
    out: list[tuple[str, str]] = []
    for name, rx, disclaimer_exempt in DEAD_CHANNEL_SHAPES:
        for m in rx.finditer(text):
            if disclaimer_exempt and _DISCLAIMED.search(_sentence_window(text, m.start(), m.end())):
                continue
            out.append((name, m.group(0)))
    return out


# ---------------------------------------------------------------------------
# The reachability rule itself must stay true, or every check below is vacuous.
# ---------------------------------------------------------------------------


def test_the_back_compat_channel_is_still_gated_on_an_empty_status():
    """Discovery floor: this whole guard is only meaningful while the parser gate exists.

    If `parse-continuation.sh` ever reads `SUGGESTED_NEXT:` unconditionally, the bare spelling
    stops being a dead channel and these checks must be re-derived rather than silently kept.
    """
    parser = PARSER.read_text(encoding="utf-8")
    gate = re.search(
        r'\[\[\s*-z\s*"\$STATUS"\s*\]\][^\n]*SUGGESTED_NEXT|'
        r'\[\[\s*-z\s*"\$STATUS"\s*\]\]\s*&&[\s\S]{0,200}?SUGGESTED_NEXT',
        parser,
    )
    assert gate, (
        "parse-continuation.sh must still gate its SUGGESTED_NEXT back-compat branch on an EMPTY "
        "$STATUS. That gate IS the reachability rule this file keys every assertion on - if it is "
        "gone, re-derive the guard instead of leaving it asserting a rule that no longer holds."
    )
    contract = _flat(_read(CONTRACT))
    assert "parse-continuation.sh:46" in contract, (
        "continuation-contract.md must keep citing the parser line that implements the gate, so an "
        "author can check reachability without reading the hook."
    )
    assert re.search(r"(?i)silently dropped once the fenced block also sets a status", contract), (
        "continuation-contract.md must keep stating the DROP consequence in plain words - it is the "
        "rule every emitter has to apply."
    )


# ---------------------------------------------------------------------------
# The two design routers: reachable channel, suppressed under a plan.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(DESIGN_ROUTERS))
def test_the_design_hop_rides_the_channel_the_driver_reads(name):
    """The design recommendation must be an IN-BLOCK `next:` entry, not the dropped bare line.

    Behaviour protected: a design-first recommendation from a status-setting emitter actually
    reaches its reader. Fails if the site reverts to `SUGGESTED_NEXT: odoo-solution-design`, or
    names the design skill with no in-block entry to carry it.
    """
    text = _read(DESIGN_ROUTERS[name])
    flat = _flat(text)

    # This file sets a status (it appends a Continuation Contract), so the bare channel is dead.
    assert "snippets/continuation-contract.md" in flat, (
        f"{name} must append a Continuation Contract - otherwise the reachability rule this test "
        f"applies does not bind it and the test is asserting the wrong thing."
    )

    # No live emission on the dead channel anywhere in the file.
    offenders = find_dead_channels(text)
    assert not offenders, (
        f"{name} still routes on the dropped `SUGGESTED_NEXT:` channel: {offenders}. Its own "
        f"fenced block sets a `status`, so parse-continuation.sh:46 never reads that line."
    )

    # And the design hop exists in the reachable form: a `skill: odoo-solution-design` entry.
    assert re.search(rf"`?skill:\s*\n?\s*`?{DESIGN_SKILL}", flat) or re.search(
        rf"`skill:\s*{DESIGN_SKILL}`", flat
    ), (
        f"{name} must carry the design hop as an in-block `next:` array entry "
        f"(`skill: {DESIGN_SKILL}`, with reason/inputs/confidence). Naming the skill in prose is "
        f"not a channel - the driver reads the array, not the sentence."
    )
    assert re.search(r"(?i)`?next:`?\s+is a LIST|second entry to the SAME fenced block", flat), (
        f"{name} must say HOW the design entry coexists with its other hop - `next:` is a LIST, so "
        f"both ride one block. Without that an author drops one of the two."
    )
    assert re.search(r"confidence:\s*0?\.\d", flat), (
        f"{name} must give the design entry an explicit `confidence` - the contract makes "
        f"confidence the advisory-vs-auto-run lever, and an omitted value is not a default."
    )


@pytest.mark.parametrize("name", sorted(DESIGN_ROUTERS))
def test_the_design_hop_is_suppressed_under_a_plan(name):
    """Making the channel reachable must NOT reopen the ordering hole the sibling guard closed.

    Behaviour protected: a reachable design hop is correct ONLY standalone. Under an approved plan
    a missing design is plan drift routed back to `odoo-planning`, never a design node scheduled
    after the plan. Fails if the suppression condition or its owner is dropped.
    """
    flat = _flat(_read(DESIGN_ROUTERS[name]))
    assert re.search(r"(?i)STANDALONE", flat), (
        f"{name}'s design entry must be scoped to STANDALONE invocations."
    )
    assert re.search(r"(?i)omit this entry entirely when a plan signal is in scope", flat), (
        f"{name} must state the suppression condition for the design entry - without it the entry "
        f"fires under a run and schedules a design AFTER the plan it should have preceded."
    )
    assert "Approved-plan-artifact detection" in flat, (
        f"{name} must resolve 'is a plan in scope?' from the three-signal SSOT "
        f"(planning-gate-contract.md § Approved-plan-artifact detection), never a local guess."
    )
    assert re.search(r"(?i)PLAN DRIFT", flat) and re.search(
        r"(?i)route back to `?odoo-planning", flat
    ), (
        f"{name} must name the alternative under a plan: a missing design is PLAN DRIFT, routed "
        f"back to `odoo-planning` to amend the plan. A suppression with no alternative just drops "
        f"the finding again - the defect this change exists to remove."
    )


# ---------------------------------------------------------------------------
# Tree-wide sweep, scoped to design routing (the coordinator's scope).
# ---------------------------------------------------------------------------


def test_no_design_route_anywhere_rides_the_dead_channel():
    """Whole-tree sweep: no file may route to the design skill on the dropped channel.

    Scope is both plugin trees, so a future skill/agent that reaches for the legacy spelling to
    recommend a design is caught with zero edits here.
    """
    offenders = []
    for path, text in _tree_texts():
        if DESIGN_SKILL not in text:
            continue
        for shape, hit in find_dead_channels(text):
            line = text[: text.index(hit)].count("\n") + 1 if hit in text else 0
            offenders.append(f"{path.relative_to(ROOT)}:{line} [{shape}] {hit[:110]!r}")
    assert not offenders, (
        "These design routes ride a channel parse-continuation.sh drops once a status is set:\n  "
        + "\n  ".join(offenders)
    )


def test_the_sweep_has_a_corpus():
    """Discovery floor - an empty corpus would make the sweep green for the wrong reason."""
    routers = [p for p, t in _tree_texts() if DESIGN_SKILL in t]
    assert len(routers) >= 10, (
        f"only {len(routers)} files mention {DESIGN_SKILL!r} - the sweep has nothing to judge"
    )


# ---------------------------------------------------------------------------
# Detector proofs.
# ---------------------------------------------------------------------------

MUST_CATCH = [
    pytest.param(
        "If the work is fable-grade but NO approved design doc exists, recommend "
        "`SUGGESTED_NEXT: odoo-solution-design` first (Custom-XL work is design-first).",
        id="the-original-odoo-coding-spelling",
    ),
    pytest.param(
        "recommend `odoo-solution-design` first (`SUGGESTED_NEXT: odoo-solution-design`).",
        id="the-original-data-migration-spelling",
    ),
    pytest.param(
        "Set `status: DONE`, then add a SUGGESTED_NEXT: odoo-solution-design line under the block.",
        id="status-set-plus-bare-line",
    ),
    pytest.param(
        "Append `SUGGESTED_NEXT: odoo-solution-design (reason=needs a design, target=sale)`.",
        id="legacy-full-payload-form",
    ),
    pytest.param(
        "emit `next`/`SUGGESTED_NEXT` naming odoo-solution-design and let the driver advance",
        id="offered-as-an-equal-alternative",
    ),
    pytest.param(
        "Set status: NEEDS_NEXT in the block, and put the next: odoo-solution-design hop "
        "outside the fenced continuation block so a human sees it.",
        id="hop-outside-the-fenced-block",
    ),
    pytest.param(
        "Surface SUGGESTED_NEXT: odoo-solution-architect when the inheritance axis is undecided.",
        id="same-defect-pointed-at-the-agent",
    ),
]


@pytest.mark.parametrize("sample", MUST_CATCH)
def test_detector_catches_every_dead_channel_shape(sample):
    assert find_dead_channels(sample), (
        f"the dead-channel detector must catch {sample!r} - a guard keyed on the skill NAME rather "
        f"than the CHANNEL passes on every one of these"
    )


MUST_NOT_CATCH = [
    pytest.param(
        "surface `odoo-solution-design` first as an in-block `next:` entry per § Continuation "
        "Contract below - NEVER as a bare `SUGGESTED_NEXT:` line, which this skill's own `status` "
        "silently drops.",
        id="the-fix-itself",
    ),
    pytest.param(
        "add a SECOND entry to the SAME fenced block's `next:` array: `skill: "
        "odoo-solution-design`, `reason: Custom-XL work is design-first`, `confidence: 0.4`.",
        id="the-in-block-entry",
    ),
    pytest.param(
        "add a `next:` entry naming `odoo-solution-design` to your Continuation Contract block - "
        "do not emit a bare `SUGGESTED_NEXT:` line, superseded by the in-block form.",
        id="the-four-superseded-agents",
    ),
    pytest.param(
        "Back-compat: a legacy `SUGGESTED_NEXT: <skill> (reason=..., target=...)` line is still "
        "read by the driver as a low-confidence `NEEDS_NEXT`; prefer the fenced block.",
        id="the-contract-documenting-back-compat",
    ),
    pytest.param(
        "The Skill tool is available here - MUST use it; do not stop at a `SUGGESTED_NEXT` line "
        "that nothing advances, when the design is what is missing.",
        id="warning-that-the-line-advances-nothing",
    ),
    pytest.param(
        'if [[ -z "$STATUS" ]] && grep -qiE \'^[[:space:]]*SUGGESTED_NEXT:\'; then '
        'STATUS="NEEDS_NEXT"; fi  # back-compat for odoo-solution-design hops',
        id="the-parser-implementation",
    ),
    pytest.param(
        "emit `next: odoo-solution-design` with `inputs: {design_doc: <path>}` inside the fenced "
        "continuation block; the driver reads the array.",
        id="plain-reachable-in-block-hop",
    ),
]


@pytest.mark.parametrize("sample", MUST_NOT_CATCH)
def test_detector_leaves_reachable_and_documenting_prose_alone(sample):
    hits = find_dead_channels(sample)
    assert not hits, (
        f"the dead-channel detector must NOT catch {sample!r} (matched {hits!r}) - firing on the "
        f"fix's own wording, on the contract's own documentation, or on the parser that implements "
        f"the rule makes the guard impossible to keep green honestly"
    )
