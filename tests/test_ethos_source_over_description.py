"""ETHOS 12 - descriptions are claims, source is truth.

WHY this principle exists
-------------------------
Descriptive text rots by default, because nothing enforces it: code changes,
the comment beside it does not, and no test fails when a sentence goes false.
A measured sweep of one Odoo module found three distinct rot classes, each
needing a different instrument - a moved line number, a CORRECT line number
attached to a false sentence, and a block asserting a live pass/fail status.
Only the first is caught by re-resolving citations, which is why the rule has
to be "confirm against the source", not "check that the reference resolves".

Before this principle the stance existed only inside
`snippets/zero-trust-code-survey.md`, scoped to `odoo-deep-survey` and carrying
an explicit "Do NOT promote to ... any other skill" header. So every other
agent - reviewers, coders, debuggers - had no rule against quoting a docstring
as evidence. ETHOS 12 makes it universal; the snippet keeps only the
survey-specific machinery.

These are prose gates on a principles file, so they assert the DECIDABLE parts
a later editor could quietly drop: the claim/truth split, the OSM-first
non-inversion, the write-side duty that stops the rot at its source, and the
count/cross-reference agreement that would otherwise drift - the very failure
the principle is about.

Run: python -m pytest tests/test_ethos_source_over_description.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
ETHOS = PLUGIN / "ODOO-AI-ETHOS.md"
README = PLUGIN / "README.md"
ZERO_TRUST = PLUGIN / "snippets" / "zero-trust-code-survey.md"

# Prose is hard-wrapped, so phrase assertions run against a normalized copy.
ETHOS_FLAT = re.sub(r"\s+", " ", ETHOS.read_text(encoding="utf-8"))


def _principle_section(number: int) -> str:
    """The body of one `## <n>. ...` principle, up to the next `## ` heading."""
    raw = ETHOS.read_text(encoding="utf-8")
    start = re.search(rf"^## {number}\. ", raw, re.MULTILINE)
    assert start, f"ETHOS has no `## {number}.` principle heading"
    nxt = re.search(r"^## ", raw[start.end():], re.MULTILINE)
    body = raw[start.start(): start.end() + nxt.start()] if nxt else raw[start.start():]
    return re.sub(r"\s+", " ", body)


# ---------------------------------------------------------------------------
# The principle itself
# ---------------------------------------------------------------------------

def test_ethos_carries_the_source_over_description_principle():
    """The rule must exist as its own numbered principle, not as an aside
    inside another one - agents cite ETHOS principles by number."""
    assert re.search(r"^## 12\. ", ETHOS.read_text(encoding="utf-8"), re.MULTILINE), (
        "ETHOS must carry principle 12 as its own heading"
    )
    body = _principle_section(12)
    assert re.search(r"claim", body, re.IGNORECASE) and re.search(r"truth|source", body, re.IGNORECASE), (
        "principle 12 must state the claim-vs-source split that is its whole point"
    )


def test_principle_names_the_artifacts_that_are_only_claims():
    """A rule that says 'do not trust descriptions' without naming them gets
    read as being about someone else's documentation. The named set is what
    makes it actionable at the moment an agent is about to quote one."""
    body = _principle_section(12)
    for artifact in ("docstring", "comment", "README", "commit message"):
        assert re.search(re.escape(artifact), body, re.IGNORECASE), (
            f"principle 12 must name '{artifact}' as a claim - an unnamed category "
            "is one an agent will not recognise in the moment"
        )
    assert re.search(r"report|ticket|CRM", body, re.IGNORECASE), (
        "the rule is universal across domains (ETHOS applies to sales/ops/strategy too), "
        "so it must reach beyond source-code prose to reports/tickets/notes"
    )


def test_principle_explains_why_the_text_rots():
    """Without the mechanism, the rule reads as generic distrust and the first
    editor who finds it inconvenient drops it. The mechanism is that nothing
    enforces prose: no test fails when a comment goes false."""
    body = _principle_section(12)
    assert re.search(r"rot|stale|drift", body, re.IGNORECASE), (
        "principle 12 must name the failure mode (descriptive text going stale)"
    )
    assert re.search(
        r"(no test|nothing enforces|does not fail|no build)", body, re.IGNORECASE
    ), (
        "principle 12 must say WHY prose rots - nothing fails when it goes false - "
        "otherwise the rule looks like paranoia rather than a mechanism"
    )


def test_principle_distinguishes_the_worst_rot_class_from_a_broken_pointer():
    """A citation that RESOLVES can still be false, and that case is worse than
    a broken one because it reads as freshly verified. A rule that only says
    'check your references' misses exactly this class."""
    body = _principle_section(12)
    assert re.search(r"resolv", body, re.IGNORECASE), (
        "principle 12 must address the resolving-but-false citation"
    )
    assert re.search(r"worse", body, re.IGNORECASE), (
        "principle 12 must rank a correct pointer on a false sentence as WORSE than a "
        "broken pointer - that ranking is what stops 'my citations all resolve' from "
        "being treated as proof"
    )


def test_principle_does_not_invert_osm_first():
    """OSM STRUCTURE stays primary and trusted; only DESCRIPTIVE text is demoted.
    Without this the rule reads as 'go read the raw checkout instead', which
    inverts the repo's OSM-first contract."""
    body = _principle_section(12)
    assert re.search(r"OSM", body), "principle 12 must address OSM explicitly"
    assert re.search(r"(not invert|does NOT invert|stay|remains?|PRIMARY)", body, re.IGNORECASE), (
        "principle 12 must keep OSM's structural calls PRIMARY - demoting them would "
        "invert the OSM-first contract the whole plugin rests on"
    )
    assert re.search(r"model_inspect|entity_lookup|resolve_orm_chain", body), (
        "principle 12 must name at least one trusted OSM STRUCTURAL call, so the "
        "claim/structure line is decidable rather than a matter of taste"
    )


def test_principle_carries_the_write_side_duty():
    """Reading defensively treats the symptom. The rot exists because someone
    changed behavior and left the prose behind, so the principle must also bind
    the writer - otherwise it institutionalises the drift instead of ending it
    (ETHOS 5: fix the root cause, not the symptom)."""
    body = _principle_section(12)
    assert re.search(r"same change|in the same|update the (docstring|comment)", body, re.IGNORECASE), (
        "principle 12 must require updating (or deleting) the describing prose in the "
        "SAME change that alters the behavior - that is what stops the rot at its source"
    )


def test_principle_says_source_wins_and_the_stale_text_gets_flagged():
    """Working around a false comment silently leaves the trap armed for the
    next reader (ETHOS 6)."""
    body = _principle_section(12)
    assert re.search(r"source WINS|source wins", body), (
        "principle 12 must state which side wins on a disagreement"
    )
    assert re.search(r"flag", body, re.IGNORECASE), (
        "a source-vs-description conflict must be FLAGGED where the stale text lives, "
        "not silently worked around"
    )


def test_principle_bans_quoting_a_description_as_evidence():
    """ETHOS principles carry an explicit banned list; this one's central ban is
    using descriptive text as proof in a finding or report."""
    body = _principle_section(12)
    assert re.search(r"\*\*Banned:\*\*|Banned:", body), (
        "principle 12 must carry a Banned list like its sibling principles"
    )
    assert re.search(r"(quoting|quote) a comment|as evidence", body, re.IGNORECASE), (
        "the ban must cover quoting a comment/docstring AS EVIDENCE - that is the "
        "concrete act the principle exists to stop"
    )


# ---------------------------------------------------------------------------
# Cross-file agreement - the same drift class, one level up
# ---------------------------------------------------------------------------

def test_the_stated_principle_count_matches_the_headings():
    """The header count and the README's count are exactly the kind of
    descriptive claim this principle distrusts. Derive the truth from the
    headings and make the prose agree, so adding principle 13 cannot leave a
    stale '12' behind in three files."""
    raw = ETHOS.read_text(encoding="utf-8")
    numbers = {int(m) for m in re.findall(r"^## (\d+)\. ", raw, re.MULTILINE)}
    # Principle 0 is the output convention, counted separately from the numbered
    # principles the header advertises.
    stated_in_ethos = re.search(r"^(\d+) principles governing", raw, re.MULTILINE)
    assert stated_in_ethos, "ETHOS header must state how many principles it governs by"
    counted = len(numbers - {0})
    assert int(stated_in_ethos.group(1)) == counted, (
        f"ETHOS header says {stated_in_ethos.group(1)} principles but the file has "
        f"{counted} numbered principle headings (excluding 0)"
    )
    readme = README.read_text(encoding="utf-8")
    stale = re.findall(r"(\d+) (?:work-ethic )?principles", readme)
    assert stale, "README must mention the principle count so it stays reviewable"
    for found in stale:
        assert int(found) == counted, (
            f"README claims {found} principles while ODOO-AI-ETHOS.md defines {counted} - "
            "a stale count is the exact drift principle 12 is about"
        )


def test_one_line_summary_cites_principles_by_their_real_numbers():
    """The closing one-line summary cites principles by number. A citation that
    points at the wrong principle is the resolving-but-false class from the
    principle itself, so it must be checked, not trusted."""
    raw = ETHOS.read_text(encoding="utf-8")
    titles = {
        int(n): t.strip()
        for n, t in re.findall(r"^## (\d+)\. (.+)$", raw, re.MULTILINE)
    }
    one_line = raw.rstrip().splitlines()[-1]
    assert one_line.lstrip("> ").startswith("**One line:**"), (
        "the closing one-line summary must remain the file's last line"
    )
    expected = {
        "search first": 3,
        "understand intent": 5,
        "right audience": 7,
        "most effective means": 4,
        "behavior-protecting tests": 8,
        "finish with evidence": 10,
        "surface uncertainty": 2,
        "flag problems": 6,
        "ground every claim in source": 12,
        "data-driven": 11,
    }
    for phrase, want in expected.items():
        m = re.search(re.escape(phrase) + r"[^(]*\(#(\d+)", one_line)
        assert m, f"one-line summary no longer mentions {phrase!r} with a (#n) citation"
        got = int(m.group(1))
        assert got == want, (
            f"one-line summary cites (#{got}) for {phrase!r}, but that is principle "
            f"{want} ({titles.get(want)!r}); (#{got}) is {titles.get(got)!r}"
        )


def test_zero_trust_snippet_defers_to_ethos_instead_of_forbidding_reuse():
    """The snippet predates the principle and used to forbid promoting the
    stance anywhere else. With ETHOS 12 in force that header would contradict
    the principles file - the contradiction class this repo removes on sight."""
    text = ZERO_TRUST.read_text(encoding="utf-8")
    assert not re.search(r"Do NOT promote", text), (
        "the snippet must no longer forbid the stance from binding other skills - "
        "ETHOS 12 now binds all of them"
    )
    assert re.search(r"ETHOS", text), (
        "the snippet must point at ETHOS as the owner of the universal rule"
    )
    assert re.search(r"RESOLVED", text), (
        "the snippet must keep the survey-specific machinery (the finding verdict) "
        "that ETHOS deliberately does not carry"
    )
