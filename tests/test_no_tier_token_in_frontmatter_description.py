"""Guard: no model-tier or vendor-model token in any frontmatter `description`.

Business contract being protected: a skill / agent / command `description` is the ONE field the
harness loads unconditionally into every session's listing. It is written for a router AND read by
the human sitting in front of that session. `haiku` / `sonnet` / `opus` / `fable` are vendor model
names, and `L0` / `L1` / `L2` is the driver's internal gate-tier control vocabulary - neither tells
an Odoo consultant anything. Depth and cost do: `skills/odoo-coding/SKILL.md` declares the mapping
(`quick` / `standard` / `deep` / `deepest`) and states the rule those words exist for - "the
human-facing gate shows DEPTH, never the tier name". This guard extends that rule from the gate to
the description field.

Why this file exists at all - the gap it closes. `tests/test_no_tier_jargon_in_templates.py` scans
BACKTICK-FENCED emitted-template blocks and structurally cannot see YAML frontmatter: a
`description: >-` block scalar is not a fenced block, so no fence regex ever matches it.
`test_fenced_template_scanner_cannot_see_frontmatter` proves that against a synthetic file rather
than asserting it, so the two guards can never silently collapse into one. Neither does this file
re-check what `tests/test_status_vocabulary.py` owns (SSOT-vs-rendering agreement for the enums).

Scope - and the scoping matters more than the breadth. The tier values are LOAD-BEARING internally:
`agents/*.md` and `skills/*/SKILL.md` declare `model: opus` in frontmatter, `odoo-coding` carries the
tier-selection table, `run-harness` resolves `L0/L1/L2` in its driver loop, and
`generator/skill_tool_deps.json` + `generator/check_orchestration.py` declare the enums. A guard
that flagged any of those would be flagging the machinery, and the next maintainer would delete it -
after which it protects nothing. So the corpus is exactly ONE field: the frontmatter `description`
of `skills/*/SKILL.md`, `agents/*.md`, and `commands/*.md`. Everything else - the `model:` key
beside it, every file body, the registry, the lint - is out of scope by construction, and the
scoping tests below prove that against the real tree in both directions.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_no_tier_jargon_in_templates import _emitted_templates  # noqa: E402
from test_skill_format import _frontmatter  # noqa: E402

ROOT = TESTS_DIR.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

SKILL_FILES = sorted((PLUGIN / "skills").glob("*/SKILL.md"))
AGENT_FILES = sorted((PLUGIN / "agents").glob("*.md"))
COMMAND_FILES = sorted((PLUGIN / "commands").glob("*.md"))
DESCRIBED_FILES = SKILL_FILES + AGENT_FILES + COMMAND_FILES

# Vendor model names (the four this plugin dispatches at) and the driver's gate-tier tokens.
# Sourced as a literal here on purpose: these are the tokens the rule BANS, not values the plugin
# declares, so there is no SSOT to read them from - `generator/skill_tool_deps.json` declares the
# tiers that are ALLOWED internally, which is the opposite set.
VENDOR_MODEL_RE = re.compile(r"\b(?:haiku|sonnet|opus|fable)\b", re.IGNORECASE)
GATE_TIER_RE = re.compile(r"\bL[012]\b")

# The plain-language replacements `skills/odoo-coding/SKILL.md` already declares, quoted in the
# failure message so a contributor is handed the fix instead of just the complaint.
DEPTH_WORDS = "quick / standard / deep / deepest"


def _banned_tokens(description: str) -> list[str]:
    """Every banned token in one description string, in source order."""
    return [m.group() for m in VENDOR_MODEL_RE.finditer(description)] + [
        m.group() for m in GATE_TIER_RE.finditer(description)
    ]


def _description(path: Path) -> str:
    return _frontmatter(path.read_text(encoding="utf-8")).get("description", "")


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------


def test_described_files_discovered():
    """Premise: the corpus is non-empty and covers all three layers, so no rule below can pass
    vacuously by scanning nothing."""
    assert len(SKILL_FILES) >= 41, f"expected >=41 skills, found {len(SKILL_FILES)}"
    assert len(AGENT_FILES) >= 3, f"expected >=3 agents, found {len(AGENT_FILES)}"
    assert len(COMMAND_FILES) >= 3, f"expected >=3 commands, found {len(COMMAND_FILES)}"


@pytest.mark.parametrize(
    "described", DESCRIBED_FILES, ids=lambda p: f"{p.parent.name}/{p.name}"
)
def test_description_names_no_model_tier_or_vendor_model(described):
    """A frontmatter `description` reaches every session's listing - it names no tier, ever."""
    description = _description(described)
    assert description, f"{described}: missing a frontmatter description"
    found = _banned_tokens(description)
    assert not found, (
        f"{described.relative_to(PLUGIN)}: frontmatter `description` carries the internal "
        f"token(s) {found} - this field is loaded into EVERY session's skill listing and read by "
        f"the human. Say what it costs the reader, not which model runs: use the depth words "
        f"`skills/odoo-coding/SKILL.md` already declares ({DEPTH_WORDS}), and drop L0/L1/L2 "
        f"entirely (it is the driver's own control value, never a user-facing one)."
    )


# ---------------------------------------------------------------------------
# Non-duplication proof - the existing guard structurally cannot cover this field
# ---------------------------------------------------------------------------


def test_fenced_template_scanner_cannot_see_frontmatter(tmp_path):
    """`test_no_tier_jargon_in_templates.py` scans fenced blocks; frontmatter is not one.

    Proven, not asserted: a file whose frontmatter carries every banned token yields ZERO emitted
    templates from that module's own extractor, while THIS module's extractor finds all of them.
    If a future edit taught the fence scanner to read frontmatter, this test goes red and the two
    guards can be merged deliberately instead of drifting into a silent overlap.
    """
    offender = tmp_path / "SKILL.md"
    offender.write_text(
        "---\n"
        "name: synthetic-skill\n"
        'argument-hint: "[scope]"\n'
        "description: >-\n"
        "  A broad haiku sweep, then sonnet dives, then an opus pass; gate tier L2\n"
        "model: opus\n"
        "---\n"
        "\n"
        "# Body\n"
        "\n"
        "Ordinary prose.\n",
        encoding="utf-8",
    )
    text = offender.read_text(encoding="utf-8")

    assert list(_emitted_templates(text)) == [], (
        "premise: the fenced-template scanner must find nothing in a file whose only tier tokens "
        "live in YAML frontmatter - that blind spot is the entire reason this guard exists"
    )
    assert _banned_tokens(_description(offender)) == ["haiku", "sonnet", "opus", "L2"], (
        "this guard must see exactly the frontmatter tokens the fence scanner cannot"
    )


# ---------------------------------------------------------------------------
# Mutation proofs - the detector must be able to fail, and to stop failing
# ---------------------------------------------------------------------------


def test_detector_flags_a_synthetic_offending_description(tmp_path):
    """Red proof: each banned token class is detected on its own, in a real frontmatter block."""
    cases = {
        "a broad haiku sweep": ["haiku"],
        "narrow Sonnet dives": ["Sonnet"],
        "an optional opus pass": ["opus"],
        "escalates to fable": ["fable"],
        "resolves its gate tier (L0/L1/L2)": ["L0", "L1", "L2"],
    }
    for description, expected in cases.items():
        offender = tmp_path / "SKILL.md"
        offender.write_text(
            f"---\nname: synthetic\ndescription: {description}\nmodel: opus\n---\n\nBody\n",
            encoding="utf-8",
        )
        assert _banned_tokens(_description(offender)) == expected, (
            f"detector missed {expected} in {description!r}"
        )


def test_clean_description_using_the_declared_depth_words_is_silent(tmp_path):
    """Green proof: the fix the failure message prescribes actually clears the rule - so the rule
    fails for the token, not merely because a description mentions depth or cost at all."""
    clean = tmp_path / "SKILL.md"
    clean.write_text(
        "---\n"
        "name: synthetic\n"
        "description: >-\n"
        "  A broad quick sweep, then narrow standard-depth dives, then an optional deep pass,\n"
        "  spending depth and cost only where the scope earns it\n"
        "model: opus\n"
        "---\n"
        "\n"
        "Body\n",
        encoding="utf-8",
    )
    assert _banned_tokens(_description(clean)) == [], (
        "a description written in the declared depth words must produce no finding"
    )


# ---------------------------------------------------------------------------
# Scoping proofs against the REAL tree - the legitimate internal uses stay unflagged
# ---------------------------------------------------------------------------


def test_frontmatter_model_key_is_out_of_scope():
    """`model: opus` beside the description is the SANCTIONED declaration and must never flag.

    Premise first (so this cannot pass vacuously): real files really do declare a tier there.
    """
    declared = [
        f for f in DESCRIBED_FILES
        if VENDOR_MODEL_RE.fullmatch(
            _frontmatter(f.read_text(encoding="utf-8")).get("model", "").strip() or "-"
        )
    ]
    assert declared, (
        "premise: at least one skill/agent must declare a vendor tier in its `model:` frontmatter "
        "key, otherwise this test proves nothing about scoping"
    )
    for f in declared:
        assert _banned_tokens(_description(f)) == [], (
            f"{f.relative_to(PLUGIN)}: the `model:` key is the sanctioned tier declaration; only "
            f"the `description` value is scanned"
        )


def test_file_bodies_carrying_tier_tokens_are_out_of_scope():
    """`odoo-coding`'s tier table and `run-harness`'s driver loop are the legitimate internal uses.

    Premise first: both bodies really do carry the tokens. Then: neither file yields a finding,
    because only its frontmatter `description` is read.
    """
    coding = PLUGIN / "skills" / "odoo-coding" / "SKILL.md"
    harness = PLUGIN / "skills" / "run-harness" / "SKILL.md"
    for f, pattern in ((coding, VENDOR_MODEL_RE), (harness, GATE_TIER_RE)):
        assert f.is_file(), f"premise: {f} must exist"
        text = f.read_text(encoding="utf-8")
        body = text.split("\n---\n", 2)[-1]
        assert pattern.search(body), (
            f"premise: {f.name}'s BODY must carry the internal token, otherwise this test proves "
            f"nothing about scoping"
        )
        assert _banned_tokens(_description(f)) == [], (
            f"{f.relative_to(PLUGIN)}: a body that steers dispatch is machinery - flagging it "
            f"would get this guard deleted, after which it protects nothing"
        )


def test_registry_and_lint_are_not_in_the_corpus():
    """The registry's `default_gate_tier` and the lint's tier enum are machinery, not descriptions.

    Asserted structurally so a future widening of the corpus glob cannot silently pull them in.
    """
    scanned = set(DESCRIBED_FILES)
    for internal in (
        PLUGIN / "generator" / "skill_tool_deps.json",
        PLUGIN / "generator" / "check_orchestration.py",
    ):
        assert internal.is_file(), f"premise: {internal} must exist"
        assert internal not in scanned, (
            f"{internal.name} declares the tier enum - it has no frontmatter description at all"
        )
