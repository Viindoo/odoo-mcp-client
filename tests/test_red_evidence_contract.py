"""RED_MODE - a RED is measured or constructed, never asserted.

WHY this contract exists
------------------------
Red-before-green was stated as a sequence and never as a measurement. Three
prescriptions, each defensible alone, composed into a gate that could not fire:
`odoo-coder` launches `odoo-test-writer` FIRST (before any model/field/external
id the test will name exists), the writer is told not to run the suite inline,
and its RED confirmation was a fixed sentence to emit. The coordinator's only
check on the returned test was that the FILE EXISTS. So nothing in the loop ever
observed a RED, and a test authored against a model that does not exist - failing
with `KeyError` - was reported as a confirmed RED by the contract working as
written.

The goal red-first serves is that a test cannot snapshot the code. Two properties
deliver it: INDEPENDENCE (the author has not read the implementation - already
free from the topology) and SENSITIVITY (the test can fail when the behavior is
absent). "Watch it fail first" is a proxy for sensitivity that Odoo often cannot
measure, because a behavior and the vocabulary naming it arrive together. These
gates assert the decidable parts a later editor could quietly drop.

Run: python -m pytest tests/test_red_evidence_contract.py -v
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"
SSOT = PLUGIN / "snippets" / "red-evidence-contract.md"
TEST_FIRST = PLUGIN / "snippets" / "test-first-contract.md"
DISPATCH_BRIEF = PLUGIN / "snippets" / "dispatch-brief.md"
WRITER = PLUGIN / "agents" / "odoo-test-writer.md"
COORDINATOR = PLUGIN / "agents" / "odoo-coder.md"
REVIEWER = PLUGIN / "agents" / "odoo-code-reviewer.md"
DEPS_JSON = PLUGIN / "generator" / "skill_tool_deps.json"

MODES = ("constructed", "measured", "toggle", "exempt")

# Prose is hard-wrapped; phrase assertions run against a normalized copy.
SSOT_FLAT = re.sub(r"\s+", " ", SSOT.read_text(encoding="utf-8"))


def _agent_facing() -> list[Path]:
    """Every file an executing agent reads in full. `snippets/references/` is
    EXCLUDED by the repo's own [ref-scope] design - no consumer-facing file may
    point at it, so it is archaeology for humans and may quote retired prose."""
    out: list[Path] = []
    for sub in ("skills", "agents", "snippets", "commands", "workflows"):
        d = PLUGIN / sub
        if d.exists():
            out += [p for p in d.rglob("*") if p.is_file() and p.suffix in {".md", ".yaml", ".yml"}]
    return [p for p in out if "snippets/references/" not in p.as_posix()]


# ---------------------------------------------------------------------------
# The contract itself
# ---------------------------------------------------------------------------

def test_ssot_declares_every_red_mode():
    """Agents pick a mode by name; a mode that vanishes from the SSOT silently
    becomes undeclarable while consumers still emit it."""
    for mode in MODES:
        assert re.search(rf"`{mode}`", SSOT_FLAT), f"red-evidence-contract must declare `{mode}`"


def test_a_failure_that_never_reached_the_assertion_is_not_a_red():
    """The whole defect in one rule: the observed failure must be the assertion's.
    Each class below is one an agent actually produces by naming a symbol that
    does not exist yet, and each must be named so it is recognisable in the
    moment rather than left to judgement."""
    assert re.search(r"BROKEN MEASUREMENT", SSOT_FLAT), (
        "the SSOT must name the not-a-RED verdict, so a structural failure has a "
        "reportable name instead of being logged as red"
    )
    for cls in (r"KeyError", r"Invalid field", r"external id", r"tests/__init__\.py",
                r"0 tests selected"):
        assert re.search(cls, SSOT_FLAT), (
            f"the SSOT must name the '{cls}' broken-measurement class - an unnamed class "
            "is one an agent will report as a RED"
        )


def test_ssot_bans_manufacturing_a_red_from_a_symbol_known_to_be_absent():
    """The reported symptom, stated as a prohibition rather than left to be
    inferred from the class list above."""
    assert re.search(r"you KNOW is absent", SSOT_FLAT), (
        "the SSOT must ban naming a model/field/external id known to be absent just to "
        "watch it fail - that is the observed behavior this contract exists to stop"
    )


def test_ssot_carries_the_free_proof_so_the_rule_is_not_just_more_running():
    """Sensitivity provable with no run at all is what keeps the contract cheap.
    Without it the rule degrades into 'run more tests', which costs time and
    tokens for changes whose RED was never measurable."""
    assert re.search(r"sensitivity by construction", SSOT_FLAT, re.IGNORECASE), (
        "the SSOT must carry the no-run proof"
    )
    assert re.search(r"declared default", SSOT_FLAT), (
        "the free proof is only decidable if the SSOT names what absence produces "
        "(the declared default, the input unchanged, no exception)"
    )


def test_ssot_forbids_provisioning_an_instance_just_to_measure_a_red():
    """A measurement rides an instance that already exists. Without this bound a
    `measured` RED could spin up an instance per work-item."""
    assert re.search(r"Never provision an instance to measure a RED", SSOT_FLAT), (
        "the SSOT must bound the cost of a measured RED"
    )
    assert re.search(r"degrades to `constructed`", SSOT_FLAT), (
        "the SSOT must state the degradation path when no instance is held, so the "
        "bound above is actionable rather than a dead end"
    )


def test_ssot_covers_the_changes_whose_red_is_not_a_new_behavior():
    """The mechanical error is applying ONE red recipe to every change. These
    three rows are the ones a new-behavior recipe gets wrong, so they are the
    ones worth pinning."""
    assert re.search(r"Refactor \(behavior preserved\)[^|]*\|[^|]*none exists", SSOT_FLAT), (
        "a refactor has NO new red - inventing one is the mechanical error; the row must "
        "say so rather than leave the author to manufacture a failure"
    )
    assert re.search(r"Bug fix[^|]*\|[^|]*REPORTED symptom", SSOT_FLAT), (
        "a bug-fix test written from the intended FIX passes on any implementation - the "
        "row must anchor it to the reported symptom"
    )
    assert re.search(r"Behavior removal[^|]*\|[^|]*inverted", SSOT_FLAT), (
        "removing behavior inverts the red (the test fails while the behavior is still "
        "present) - a new-behavior recipe misses it entirely"
    )


# ---------------------------------------------------------------------------
# No agent is still told to ASSERT a red
# ---------------------------------------------------------------------------

def test_no_agent_facing_file_prescribes_an_asserted_red():
    """The root cause was a template sentence standing in for an observation
    (ETHOS 12: a prescribed claim is not evidence). If it comes back anywhere in
    the corpus, the gate stops firing again - silently, exactly as before."""
    banned = {
        "RED - production code not yet written": "a fixed sentence emitted in place of a measurement",
        "state it's RED": "an instruction to assert redness rather than establish it",
        "confirm by reasoning": "reasoning offered as a substitute for evidence",
    }
    for path in _agent_facing():
        text = path.read_text(encoding="utf-8")
        for phrase, why in banned.items():
            assert phrase not in text, (
                f"{path.relative_to(PLUGIN)} still carries {phrase!r} - {why}"
            )


def test_test_first_contract_no_longer_accepts_the_absent_behavior_as_evidence():
    """`the absent behavior` was the loophole: it let a KeyError count as the RED
    confirmation, which is precisely a failure that never reached the assertion."""
    text = TEST_FIRST.read_text(encoding="utf-8")
    assert "the absent behavior" not in text, (
        "test-first-contract must not accept 'the absent behavior' as RED evidence - that "
        "phrase legitimises a structural error as a red"
    )
    assert "red-evidence-contract.md" in text, (
        "test-first-contract owns WHEN and must hand the evidence question to its SSOT"
    )


# ---------------------------------------------------------------------------
# The mode is produced, carried, verified, and gated - not just described
# ---------------------------------------------------------------------------

def test_the_writer_returns_a_mode_with_evidence():
    text = WRITER.read_text(encoding="utf-8")
    assert "red-evidence-contract.md" in text, "the test author must be bound to the SSOT"
    assert re.search(r"RED_MODE", text), "the test author must declare RED_MODE"
    assert re.search(r"claim, not evidence|not evidence", text), (
        "the writer's return contract must reject a bare sentence claiming redness - that "
        "sentence is what the previous contract accepted"
    )


def test_the_coordinator_verifies_the_mode_and_owns_the_run():
    """A resolving path was the ONLY thing ever checked. The coordinator is also
    the only actor in the loop holding an instance, so a measured/toggle RED is
    unrunnable anywhere else."""
    text = COORDINATOR.read_text(encoding="utf-8")
    assert "red-evidence-contract.md" in text, "the coordinator must be bound to the SSOT"
    assert re.search(r"resolving path is not a RED", text), (
        "the coordinator must verify RED_MODE, not merely that the test file opens"
    )
    assert re.search(r"--test-tags /<module>:<Class>\.<method>", text), (
        "the coordinator must own the single-test run a measured RED needs, with the "
        "selector that keeps it narrow"
    )


def test_the_mode_is_a_required_brief_key_for_both_coders():
    """Declared in the machine-readable SSOT so the orchestration lint proves
    every dispatch fence emits it, instead of the rule living only in prose."""
    deps = json.loads(DEPS_JSON.read_text(encoding="utf-8"))
    agents = deps["agents"]
    for coder in ("odoo-backend-coder", "odoo-frontend-coder"):
        required = agents[coder]["brief"]["required"]
        assert "RED_MODE" in required, (
            f"{coder} must require RED_MODE inbound - otherwise a coder can implement "
            "against a test whose redness nobody established"
        )
    assert "RED_MODE" in DISPATCH_BRIEF.read_text(encoding="utf-8"), (
        "the brief-schema SSOT must document RED_MODE beside RED_TEST_PATH"
    )
    assert re.search(r"^RED_MODE:", COORDINATOR.read_text(encoding="utf-8"), re.MULTILINE), (
        "the coordinator's coder dispatch fence must actually emit RED_MODE"
    )


def test_the_reviewer_gates_an_assertion_absence_would_satisfy():
    """The last catch: however the RED was reported, an assertion the absent
    behavior already satisfies cannot fail when the rule is wrong."""
    text = REVIEWER.read_text(encoding="utf-8")
    assert "red-evidence-contract.md" in text, "the reviewer must be bound to the SSOT"
    assert re.search(r"ABSENCE of the behavior would ALREADY satisfy", text), (
        "the reviewer must grade an insensitive assertion, not only a shortcut arrange"
    )


def test_card_budget_entry_matches_the_real_size():
    """A budget above the real size silently hands back space; below it, CI fails
    on a file nobody grew. Either way the entry stops describing the file."""
    budgets = json.loads(
        (REPO_ROOT / "tests" / "fixtures" / "card_budget_grandfather.json").read_text(
            encoding="utf-8"
        )
    )["budgets"]
    rel = "snippets/red-evidence-contract.md"
    assert rel in budgets, "the new hot contract must carry a deliberate budget entry"
    assert budgets[rel] == SSOT.stat().st_size, (
        f"budget {budgets[rel]}B != actual {SSOT.stat().st_size}B for {rel}"
    )


def test_the_red_probe_carve_out_is_stated_where_the_suppression_rule_lives():
    """A `measured` RED runs ONE test - narrower than the module set
    test-scope-contract requires a run to cover, which that contract calls
    SUPPRESSION and forbids outright. Without an explicit carve-out the two
    contracts contradict each other and an agent obeying either one breaks the
    other. The carve-out is principled, not convenience: a probe's GREEN
    licenses nothing (it signals a defective test), while a verdict run's green
    lets work proceed."""
    scope = (PLUGIN / "snippets" / "test-scope-contract.md").read_text(encoding="utf-8")
    assert "RED PROBE" in scope, (
        "the contract that OWNS scoping-vs-suppression must name the carve-out - stating it "
        "only in red-evidence-contract would leave the prohibition unqualified where agents read it"
    )
    assert "red-evidence-contract.md" in scope, "the carve-out must point at its owning contract"
    assert re.search(r"verdict run", scope), (
        "the carve-out is only decidable if the contract says what it is NOT exempting"
    )
    assert "test-scope-contract.md" in SSOT.read_text(encoding="utf-8"), (
        "the probe's own contract must point back, so an agent reaching the narrow selector from "
        "either direction finds the agreement"
    )
