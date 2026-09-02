"""Behavioral gate: a test may never assert TRANSLATED or DISPLAY text.

Terminology, help text and `.po` msgstrs are improved continuously by people who never see the
test suite, so an assertion pinned to that wording fails on an IMPROVEMENT rather than on a defect.
Its only cheap remedy is editing the expected value, which is itself banned - so such a test is a
permanent obstacle that gates nothing.

These tests protect the RULE and its REACH: the rule declared once, every actor that authors,
reviews, or plans a test pointed at it, and the orchestrator hint that stops the instruction being
issued in the first place.

Run: python -m pytest tests/test_no_translation_assertions.py -v
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

BEHAVIOR_CONTRACT = PLUGIN / "snippets" / "test-behavior-contract.md"
SECTION = "## Never assert TRANSLATED or DISPLAY text"

# Every actor that AUTHORS a test, REVIEWS one, or decides an expected result. A rule these do not
# reach is a rule that does not run.
RULE_CONSUMERS = (
    PLUGIN / "agents" / "odoo-test-writer.md",
    PLUGIN / "skills" / "odoo-test-writing" / "SKILL.md",
    PLUGIN / "agents" / "odoo-code-reviewer.md",
    PLUGIN / "snippets" / "acceptance-oracle-contract.md",
)

INTENT_HOOK = PLUGIN / "hooks" / "detect-intent.sh"


def _flat(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_contract_declares_the_ban_with_a_decidable_list():
    """A one-line "don't test translations" is not actionable at authoring time.

    The author is looking at a concrete assertion and needs to know whether THIS one is banned, so
    the rule has to enumerate the shapes rather than gesture at a category."""
    assert BEHAVIOR_CONTRACT.is_file()
    text = BEHAVIOR_CONTRACT.read_text(encoding="utf-8")
    assert SECTION in text, f"missing the {SECTION!r} section"
    section = text.split(SECTION, 1)[1].split("\n## ", 1)[0]
    flat = re.sub(r"\s+", " ", section)
    for shape in ("help", "msgstr", "selection", "placeholder"):
        assert shape in section, f"the banned list must name {shape!r} explicitly"
    assert re.search(r"exception", flat, re.I) and re.search(r"WORDING", flat), (
        "message wording is the shape authors reach for most (assertRaisesRegex over prose) - it "
        "must be named, not left to inference"
    )


def test_contract_supplies_the_substitute_for_every_ban():
    """A ban with no substitute is refused in practice: the author still needs an assertion.

    Each banned shape has a stable thing underneath (exception TYPE, technical value, state), and
    the contract must hand it over or the rule loses to the deadline."""
    section = BEHAVIOR_CONTRACT.read_text(encoding="utf-8").split(SECTION, 1)[1].split("\n## ", 1)[0]
    flat = re.sub(r"\s+", " ", section)
    assert re.search(r"exception TYPE", flat), "name the substitute for a message assertion"
    assert re.search(r"technical VALUE", flat), "name the substitute for a selection label"
    assert "|---|---|" in section, (
        "the substitutions belong in a lookup table - an author scanning mid-edit does not read "
        "three paragraphs to find the replacement"
    )


def test_contract_separates_a_locator_from_an_assertion():
    """Without this carve-out the rule over-corrects and breaks tours.

    A tour often has no stable handle and must click by visible label. That is addressing, not
    asserting, and an agent applying the ban literally would refuse to write a legitimate tour."""
    section = BEHAVIOR_CONTRACT.read_text(encoding="utf-8").split(SECTION, 1)[1].split("\n## ", 1)[0]
    flat = re.sub(r"\s+", " ", section)
    assert re.search(r"LOCATOR is not a text ASSERTION", flat), (
        "the locator carve-out must be explicit, or the ban is applied to element addressing too"
    )


def test_contract_permits_removing_an_existing_offending_assertion():
    """Otherwise the rule deadlocks against 'never weaken a test'.

    An agent that finds a label assertion must be able to delete it; without an explicit clause the
    generic ban on removing assertions applies and the obstacle stays forever."""
    section = BEHAVIOR_CONTRACT.read_text(encoding="utf-8").split(SECTION, 1)[1].split("\n## ", 1)[0]
    flat = re.sub(r"\s+", " ", section)
    assert re.search(r"cleanup, not loosening", flat), (
        "removing such an assertion must be explicitly allowed, or it collides with the ban on "
        "weakening tests and nobody dares clean one up"
    )
    assert re.search(r"RELAXING|widening a regex|substring", flat), (
        "the opposite move (softening the assertion so it keeps passing) must stay banned, or the "
        "carve-out becomes a licence to sand assertions down"
    )


def test_the_ban_is_declared_in_exactly_one_place():
    """SSOT-ness: a second copy is a second thing to drift out of agreement."""
    definers = sorted(
        str(p.relative_to(PLUGIN))
        for p in PLUGIN.rglob("*.md")
        if SECTION in p.read_text(encoding="utf-8", errors="replace")
    )
    assert definers == ["snippets/test-behavior-contract.md"], (
        f"the ban must be DEFINED once; consumers cite the section. Found in: {definers}"
    )


def test_every_test_authoring_actor_carries_the_ban():
    """A rule nobody is pointed at is a rule nobody applies.

    Each of these decides what an assertion asserts - the author, the reviewer that would reject
    one, and the oracle that fixes the expected result before anything runs."""
    missing = []
    for path in RULE_CONSUMERS:
        flat = _flat(path)
        if not re.search(r"TRANSLATED or DISPLAY text|translated or display text", flat, re.I):
            missing.append(str(path.relative_to(PLUGIN)))
    assert not missing, (
        "these actors author, review, or fix the expected value of a test and must carry the ban: "
        f"{missing}"
    )


def test_code_reviewer_grades_it_as_a_finding_not_a_note():
    """A reviewer that merely 'mentions' it changes nothing.

    The existing shortcut-test and unfailable-test defects are HIGH; a permanently-red-on-improvement
    test is the same class of defect and must carry the same weight or it never gets removed."""
    flat = _flat(PLUGIN / "agents" / "odoo-code-reviewer.md")
    m = re.search(r"asserts TRANSLATED or DISPLAY text.{0,400}", flat)
    assert m, "the reviewer must name this defect shape"
    assert "HIGH finding" in m.group(0), (
        "it must be graded HIGH like its siblings; a lower grade means it ships"
    )


# ---------------------------------------------------------------------------
# The orchestrator hint - issue #3's mechanism. The main agent never reads a
# snippet it has not been pointed at, so the doctrine has to reach it at prompt
# time or it does not reach it at all.
# ---------------------------------------------------------------------------

def _run_hook(prompt: str) -> str:
    """Return the hook's additionalContext for a prompt ('' when it emits nothing)."""
    out = subprocess.run(
        ["bash", str(INTENT_HOOK)],
        input=json.dumps({"prompt": prompt}),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.returncode == 0, f"hook must always exit 0; got {out.returncode}: {out.stderr}"
    if not out.stdout.strip():
        return ""
    return json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]


def test_hook_hands_the_orchestrator_the_i18n_doctrine():
    """On a translation prompt the main agent must get the three facts it otherwise guesses at."""
    ctx = _run_hook("translate this Odoo module into fr_FR")
    assert "[i18n]" in ctx, "an Odoo translation prompt must surface the i18n doctrine"
    assert re.search(r"DEMO DATA", ctx), "the build-shape fact must be in the hint"
    assert re.search(r"EMPTY msgstr is not necessarily untranslated", ctx), (
        "the identity-rule fact must be in the hint - it is what stops 'get untranslated to zero'"
    )
    assert re.search(r"never ask for tests", ctx), "the no-translation-tests fact must be in the hint"


def test_hook_fires_on_vietnamese_translation_intent():
    """The user base prompts in Vietnamese; an English-only trigger reaches half the sessions."""
    ctx = _run_hook("dịch module Odoo sang tiếng Việt")
    assert "[i18n]" in ctx, "Vietnamese translation intent must fire the same hint"


def test_hook_stays_silent_on_non_translation_odoo_work():
    """A hint on every Odoo prompt is noise, and noise gets skimmed past.

    'document' and 'write' share the hook's content bucket with 'translate', so this is the
    false-positive most likely to creep back in."""
    for prompt in (
        "write documentation for this Odoo module",
        "add a computed field to sale.order in Odoo",
    ):
        assert "[i18n]" not in _run_hook(prompt), f"hint must not fire on: {prompt!r}"


def test_hook_stays_silent_on_non_odoo_translation():
    """This plugin has no business steering a plain translation request."""
    assert "[i18n]" not in _run_hook("translate this English contract into Spanish")
