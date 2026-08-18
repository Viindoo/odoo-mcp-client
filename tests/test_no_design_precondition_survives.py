"""Guard: nothing in either plugin tree may claim a design is a PRECONDITION of planning.

## The contract this protects (owner decision)

    Design is NOT mandatory - at ANY complexity level, non-trivial included. Planning IS mandatory
    and is NEVER refused for a missing design. The only surviving rule is directional: a design, IF
    it exists, precedes the plan - equivalently, a design is only ever an INPUT to a plan, never a
    NODE of one.

`test_design_precedes_planning.py` asserts that at the two files that own the rule
(`skills/odoo-planning/SKILL.md`, `agents/odoo-planner.md`) and asserts the surviving plan-SHAPE ban
at the schema, the driver and the plan author. NEITHER it nor
`test_ordering_enforcement_reachable.py` looks anywhere else in the tree. That is the gap this file
closes, and it is not a hypothetical one: when the refusal was removed from the planning skill, the
FALSE claim survived in two other files that neither guard reads -

* `skills/odoo-intake/references/plan-mode-schema.md` still told its reader that a design-required
  change with no approved design artifact "is a plan that must not be authored yet: `odoo-planning`
  REFUSES before it dispatches either planner and routes back to `odoo-solution-design`" - asserted
  from a file that really does ENFORCE part of the rule, so a reader had every reason to trust it;
* `snippets/planning-gate-contract.md` (the mandatory-planning SSOT) still reserved DESIGN "for
  non-trivial work", and `skills/odoo-intake/SKILL.md` still read as a rule rather than a preference.

A removed mechanism whose DESCRIPTION survives somewhere else is this plugin's dominant defect
class. A guard pinned to the file where the mechanism used to live cannot see it.

## Three detectors: two borrowed, one added

`REFUSAL_SHAPES` / `find_planning_refusals` and `DESIGN_MANDATE_SHAPES` / `find_design_mandates`
already enumerate, between them, a dozen phrasings a design gate can return in. They are IMPORTED
here - a third private set of regexes for the same rule would be one more thing to keep in lockstep,
and the first phrasing that slipped past a copy would slip past it silently.

1. **The refusal CLAIM, tree-wide** (`find_planning_refusal_claims`). `find_planning_refusals` is
   pointed at ONE file in its own module and reads that file's prose as a rule the file imposes on
   itself. Tree-wide it needs an ATTRIBUTION filter, or it fires on every legitimate neighbour: the
   driver naming `odoo-planning` as the owner who must amend a plan it refused a design NODE in,
   `odoo-coding` STOPPING because the plan it was handed drifted, `odoo-solution-design` reading a
   gap artifact as ITS OWN precondition. So a hit counts only when the PLANNING LAYER is the actor
   withholding, and what is withheld is the authoring or dispatch of a PLAN.

2. **The design MANDATE, tree-wide** (`find_design_mandates`, imported unchanged). It needs no
   narrowing: "an approved design is a precondition of authoring a plan" is false everywhere, said
   by anyone, so the sibling's detector applies to the whole corpus as-is.

3. **The MODALITY** (`find_design_reservations`). Neither imported detector catches a design framed
   as a REQUIREMENT without a stated consequence - "only DESIGN is reserved for non-trivial work",
   "a design-required change", "requires an approved design". That framing is what made the SSOT
   contradict the owner's decision while every existing guard stayed green, so it gets shapes of its
   own here (the only ones this file adds).

Building detector 1 exposed two holes in the sibling's `_WITHHOLD` / `REFUSAL_SHAPES`, and they were
WIDENED THERE rather than worked around here, so both guards gained the coverage at once: the
withhold verbs only matched their un-inflected spellings ("dispatch neither planner" but not
"dispatches neither planner"; "write NO plan" but not "writes NO plan"), and every shape required the
absence word to come BEFORE the design word, so "stops ... when the design DAG pointer is unresolved"
was unreachable. A third shape ordering now covers it.

## A pointer that MISATTRIBUTES enforcement is the same defect, inverted

`test_no_file_calls_the_planning_skill_an_enforcement_surface` closes the other half. When the
planning skill stopped enforcing, `snippets/planning-gate-contract.md` still said the ordering was
"ENFORCED (not merely declared) at `skills/odoo-planning/SKILL.md` § Design precedes planning" - a
reader sent to change the rule arrives at a section that evaluates nothing, concludes the rule is not
enforced, and either re-adds the gate there or ignores it.

## What is deliberately NOT asserted

That intake stops STEERING non-trivial work through design first. It should keep doing exactly that -
it is good practice and costs nothing. Only the MODALITY is constrained: recommended, not required.
`test_the_recommendation_survives_the_ban` protects that escape explicitly, so a future "fix" cannot
satisfy this file by deleting the routing.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

# Imported, never re-derived: the shape vocabularies and the corpus walker all live in the sibling
# that owns the rule. Widen a shape THERE and both guards gain it at once.
from test_design_precedes_planning import (  # noqa: E402
    _NEGATED,
    _flat,
    _tree_texts,
    find_design_mandates,
    find_planning_refusals,
)

GATE = ROOT / "plugins" / "odoo-ai-agents" / "snippets" / "planning-gate-contract.md"
INTAKE = ROOT / "plugins" / "odoo-ai-agents" / "skills" / "odoo-intake" / "SKILL.md"
SCHEMA = (
    ROOT / "plugins" / "odoo-ai-agents" / "skills" / "odoo-intake" / "references"
    / "plan-mode-schema.md"
)

# ---------------------------------------------------------------------------
# Detector 1 - the refusal CLAIM, wherever it is made.
# ---------------------------------------------------------------------------

#: The actor the claim must attribute the withholding to. A refusal sentence whose subject is an
#: executor, a front door or the driver is a different (and legitimate) rule.
_PLAN_LAYER = re.compile(
    r"(?i)odoo-planning|odoo-planner\b|either planner|both planners|the planner\b"
)

#: What must be withheld for the claim to be THIS claim: the authoring of a plan, or the dispatch of
#: a planner. "route back to `odoo-planning` to amend the plan" withholds nothing - it is the
#: ordinary disagreement path, and every plan-agreement check in the driver takes it.
_PLAN_WITHHELD = re.compile(
    r"(?i)author\w*|no plan\b|writ\w+ no plan|produce\w* no|emit\w* no"
    r"|dispatch\w*|either planner|both planners|plan (?:file|artifact)"
)

#: How far either side of a hit the attribution may sit. Wide enough for the subject to precede a
#: line-wrapped clause, tight enough that an unrelated `odoo-planning` two paragraphs away does not
#: vouch for a sentence that never mentions it.
_LEAD = _TAIL = 140

#: A `never` governing the DESIGN clause means the sentence DENIES the claim ("code with no PLAN,
#: never a plan with no design"), the same way the sibling's `_NEGATED` handles a negated withhold
#: word. Limit, stated rather than hidden: a refusal phrased with `never` close to the design word
#: ("never dispatches a planner without an approved design") is exempted here - such a phrasing is
#: not one the imported REFUSAL_SHAPES match in the first place, so it is the sibling's shape
#: coverage that would have to grow, not this filter.
_DENIAL_NEAR_DESIGN = re.compile(r"(?i)\bnever\b[^.]{0,60}$")
_DESIGN_WORD_RX = re.compile(r"(?i)design")


def find_planning_refusal_claims(text: str) -> list[tuple[str, str]]:
    """Every (shape, hit) CLAIMING the planning layer withholds a plan for a missing design."""
    flat = _flat(text)
    out: list[tuple[str, str]] = []
    for shape, hit in find_planning_refusals(text):
        at = flat.find(hit)
        if at < 0:  # pragma: no cover - `_flat` is idempotent, so this cannot normally happen
            continue
        lead = flat[max(0, at - _LEAD): at]
        tail = flat[at + len(hit): at + len(hit) + _TAIL]
        if not _PLAN_LAYER.search(lead + hit + tail):
            continue
        if not _PLAN_WITHHELD.search(hit + tail):
            continue
        designs = list(_DESIGN_WORD_RX.finditer(lead + hit))
        if designs and _DENIAL_NEAR_DESIGN.search((lead + hit)[: designs[-1].start()]):
            continue
        out.append((shape, hit))
    return out


# ---------------------------------------------------------------------------
# Detector 3 - the MODALITY (design framed as a requirement, consequence unstated).
# ---------------------------------------------------------------------------

#: Each entry is one way a design can be framed as REQUIRED without naming what refuses. The group
#: `w` marks the word the negation test is applied to, so a denial ("design is never required for
#: non-trivial work") is not read as the rule it denies.
DESIGN_RESERVATION_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    # The SSOT's own removed phrasing: a tier of work for which design is not optional.
    ("design-reserved-for-a-tier",
     re.compile(r"(?i)\bdesign\b[^.;]{0,40}?\b(?:is|stays|remains)\s+(?P<w>reserved for)\b")),
    # The adjective that presupposes the whole removed rule.
    ("design-required-adjective", re.compile(r"(?i)(?P<w>design-required)\b")),
    # "this change requires an approved design" - a requirement with no stated enforcer.
    ("requires-a-design",
     re.compile(r"(?i)(?P<w>requires?|requiring)\s+(?:an?\s+)?(?:approved\s+)?"
                r"(?:technical\s+)?design\b")),
    # The same as an obligation on the caller.
    ("must-have-a-design",
     re.compile(r"(?i)(?P<w>must|has to|have to|needs? to)\s+(?:have|carry|come with|hold|obtain)"
                r"\s+an?\s+(?:approved\s+)?(?:technical\s+)?design\b")),
    # A design gate stated as a tier threshold ("non-trivial work needs a design first").
    ("tier-needs-a-design",
     re.compile(r"(?i)non-trivial[^.]{0,60}(?P<w>needs?|requires?)\s+(?:an?\s+)?"
                r"(?:approved\s+)?design\b")),
)


def find_design_reservations(text: str) -> list[tuple[str, str]]:
    """Every (shape, hit) framing a design as REQUIRED rather than recommended."""
    flat = _flat(text)
    out: list[tuple[str, str]] = []
    for name, rx in DESIGN_RESERVATION_SHAPES:
        for m in rx.finditer(flat):
            at = m.start("w")
            if _NEGATED.search(flat[max(0, at - 28): at]):
                continue  # the framing being DENIED, not imposed
            out.append((name, m.group(0)))
    return out


ALL_DETECTORS = (
    ("a claim that PLANNING refuses for a missing design", find_planning_refusal_claims),
    ("a design made a PRECONDITION of authoring a plan", find_design_mandates),
    ("a design framed as REQUIRED rather than recommended", find_design_reservations),
)


# ---------------------------------------------------------------------------
# Discovery floor - a sweep over an empty corpus is green for the wrong reason.
# ---------------------------------------------------------------------------


def test_the_sweep_has_a_corpus_and_the_surfaces_it_watches():
    paths = [p for p, _ in _tree_texts()]
    assert len(paths) >= 200, (
        f"expected the plugin trees to yield a substantial prose corpus, found {len(paths)} files - "
        f"every sweep below would pass vacuously"
    )
    for path in (GATE, INTAKE, SCHEMA):
        assert path.is_file(), f"{path.relative_to(ROOT)} is missing - the rule has no owner left"


# ---------------------------------------------------------------------------
# The real tree.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label,detector", ALL_DETECTORS, ids=[d[0][:44] for d in ALL_DETECTORS])
def test_no_file_in_either_plugin_makes_a_design_a_precondition(label, detector):
    """Whole-tree sweep. Scope is both plugin trees and every prose/config extension, not an
    allowlist of the files this round happened to touch: a future skill/agent/workflow/snippet that
    re-states the removed gate is caught with zero edits here.
    """
    offenders = []
    for path, text in _tree_texts():
        for shape, hit in detector(text):
            offenders.append(f"{path.relative_to(ROOT)} [{shape}] {hit[:130]!r}")
    assert not offenders, (
        f"These sites state {label}:\n  " + "\n  ".join(offenders)
        + "\nDesign is NOT mandatory at any complexity level and planning is NEVER refused for a "
        "missing design (owner decision). The only surviving rule is directional - a design, IF it "
        "exists, precedes the plan - and it is enforced as a plan-SHAPE ban at "
        "skills/odoo-intake/references/plan-mode-schema.md and skills/run-harness/, never as a gate."
    )


def test_the_recommendation_survives_the_ban():
    """Anti-over-fix: the ban above must not be satisfied by deleting the ROUTING.

    Steering non-trivial work through design first is good practice and costs nothing, so intake
    must keep doing it - and the SSOT must keep saying design is the skippable half. A fix that
    removed the recommendation to satisfy the sweep would make the plugin worse than the bug did.
    """
    intake = _flat(INTAKE.read_text(encoding="utf-8"))
    assert re.search(r"(?i)non-trivial[^.]{0,400}odoo-solution-design", intake), (
        "odoo-intake must keep steering non-trivial work to `odoo-solution-design` before the coder "
        "- only the MODALITY changed (recommended, not required)."
    )
    assert re.search(r"(?i)(?:PREFERENCE|RECOMMEND\w*|SHOULD)", intake), (
        "intake must mark that steering as a preference/recommendation in words, or the next reader "
        "restores it as a precondition."
    )
    gate = _flat(GATE.read_text(encoding="utf-8"))
    assert re.search(r"(?i)DESIGN[^.]{0,120}may be skipped", gate), (
        "planning-gate-contract.md must keep stating that only DESIGN may be skipped (planning "
        "never is) - the escape the ordering rule must not swallow."
    )
    assert re.search(r"(?i)planning is (?:enforced|mandatory)", gate), (
        "the same SSOT must keep asserting that PLANNING is the mandatory half."
    )


#: A file claiming the ordering is ENFORCED at the planning skill. The skill only DECLARES now, so
#: any such citation sends a reader who wants to change the rule to a section that evaluates nothing.
#: The lookahead exempts the honest spellings ("DECLARED, enforcing nothing, at ...", "ENFORCED
#: elsewhere"), which is why this is keyed on the misattribution rather than on the word `enforce`.
ENFORCEMENT_MISATTRIBUTION = re.compile(
    r"(?i)\benforc(?:ed|es|ement|ing)\b"
    r"(?![^.]{0,60}\b(?:nothing|nowhere|elsewhere|not here)\b)"
    r"[^.]{0,220}?skills/odoo-planning/SKILL\.md"
)


def test_no_file_calls_the_planning_skill_an_enforcement_surface():
    """The planning skill DECLARES the ordering and enforces nothing - no pointer may say otherwise.

    Behaviour protected: every citation that promises ENFORCEMENT resolves to a surface that really
    evaluates the rule (the plan schema, or the driver). Fails the moment a file re-labels
    `skills/odoo-planning/SKILL.md` as an enforcement site - the "described, never reached" defect
    with the arrow reversed, and the exact shape the ordering SSOT carried until this pass.
    """
    offenders = [
        f"{path.relative_to(ROOT)} {m.group(0)[:150]!r}"
        for path, text in _tree_texts()
        for m in [ENFORCEMENT_MISATTRIBUTION.search(_flat(text))]
        if m
    ]
    assert not offenders, (
        "These sites promise that the design-then-planning ordering is ENFORCED at the planning "
        f"skill:\n  " + "\n  ".join(offenders)
        + "\n`skills/odoo-planning/SKILL.md` § Design precedes planning is a DECLARATION - its "
        "refusal predicate was removed by owner decision. Cite the surfaces that evaluate the rule "
        "(the plan schema, the driver) as ENFORCED, and the planning skill separately as where the "
        "order is DECLARED."
    )


def test_the_schema_constrains_shape_only_and_says_so():
    """The FIX-1 surface, positively: the schema must state its own scope.

    A ban that says nothing about what it does NOT cover is how "no design node" got re-read as "no
    plan without a design" from an enforcing file. Fails if the schema stops saying the constraint is
    about the plan's SHAPE, or stops pointing at the SSOT that owns the mandatory-planning half.
    """
    flat = _flat(SCHEMA.read_text(encoding="utf-8"))
    assert re.search(
        r"(?i)constrains? (?:is )?the plan'?s?\s+SHAPE|SHAPE, and ONLY its shape", flat
    ), (
        "plan-mode-schema.md § Design is an INPUT to this plan must say the constraint is on the "
        "plan's SHAPE only - otherwise the next reader derives a design precondition from it again."
    )
    assert re.search(r"(?i)design is\s+OPTIONAL|never a precondition", flat), (
        "The same section must state that a design is OPTIONAL / never a precondition here."
    )
    assert "planning-gate-contract.md` § Mandatory-planning rule" in flat, (
        "The schema must point at the mandatory-planning SSOT for the half it does not own, so the "
        "two cannot drift apart again."
    )


# ---------------------------------------------------------------------------
# MUST-CATCH: every shape the removed rule can come back in.
# ---------------------------------------------------------------------------

CLAIM_MUST_CATCH = [
    pytest.param(
        "A design-required change with no approved design artifact is therefore NOT a plan with a "
        "design node in front of it - it is a plan that must not be authored yet: `odoo-planning` "
        "REFUSES before it dispatches either planner and routes back to `odoo-solution-design`.",
        id="the-removed-claim-verbatim",
    ),
    pytest.param(
        "When no approved design exists on disk, `odoo-planning` dispatches neither planner and "
        "writes NO plan file.",
        id="planning-dispatches-neither-planner",
    ),
    pytest.param(
        "`odoo-planner` is handed a design gap: it emits `status: BLOCKED` with "
        "`next: odoo-solution-design` and authors nothing.",
        id="planner-hands-back-blocked-to-design",
    ),
    pytest.param(
        "The planner stops before authoring anything when the design DAG pointer is unresolved.",
        id="planner-stops-before-authoring",
    ),
    pytest.param(
        "An approved design is a precondition of dispatching either planner, so `odoo-planning` "
        "authors no plan without one.",
        id="precondition-of-dispatching-either-planner",
    ),
]


@pytest.mark.parametrize("sample", CLAIM_MUST_CATCH)
def test_the_claim_detector_catches_every_shape_the_refusal_can_return_in(sample):
    assert find_planning_refusal_claims(sample), (
        f"the detector must catch {sample!r} - the refusal was removed by owner decision, and a "
        f"guard that only knows the deleted sentence's exact words is no guard"
    )


RESERVATION_MUST_CATCH = [
    pytest.param(
        "A trivial change still gets the minimal plan; only DESIGN, via `odoo-solution-design`, is "
        "reserved for non-trivial work.",
        id="the-removed-ssot-phrasing",
    ),
    pytest.param(
        "A design-required change goes `odoo-solution-design` -> `odoo-planning` first.",
        id="the-design-required-adjective",
    ),
    pytest.param(
        "Any Extension-L change requires an approved design before the build order is drawn.",
        id="requires-an-approved-design",
    ),
    pytest.param(
        "The caller must have an approved technical design in scope for this route.",
        id="must-have-an-approved-design",
    ),
    pytest.param(
        "Non-trivial work needs a design first; trivial work does not.",
        id="tier-needs-a-design",
    ),
]


@pytest.mark.parametrize("sample", RESERVATION_MUST_CATCH)
def test_the_modality_detector_catches_a_design_framed_as_required(sample):
    assert find_design_reservations(sample), (
        f"the detector must catch {sample!r} - a design framed as REQUIRED contradicts the owner's "
        f"decision even when no consequence is stated, and no imported detector sees that framing"
    )


# ---------------------------------------------------------------------------
# MUST-NOT-CATCH: the legitimate neighbours, taken from the real tree.
# ---------------------------------------------------------------------------

CLAIM_MUST_NOT_CATCH = [
    pytest.param(
        "**Planning is MANDATORY for ALL work, and is NEVER refused for a missing design.** A "
        "design is OPTIONAL at EVERY complexity level and is never a precondition to planning.",
        id="the-declaration-that-replaced-the-refusal",
    ),
    pytest.param(
        "Instead set THAT node to `BLOCKED` with `blocked_reason` naming (a) the node id, (b) the "
        "refused design hop, and (c) `odoo-planning` as the owner who must amend the plan.",
        id="the-drivers-design-NODE-refusal",
    ),
    pytest.param(
        "Under a plan, a missing design is PLAN DRIFT and never a next step: STOP and route back to "
        "`odoo-planning` to amend the plan.",
        id="an-executor-stopping-on-plan-drift",
    ),
    pytest.param(
        "If the work is fable-grade but NO approved design doc exists, surface "
        "`odoo-solution-design` first as an in-block `next:` entry - never as a bare suggestion.",
        id="an-executor-recommending-design",
    ),
    pytest.param(
        "What the front door HARD BLOCKS is code with no PLAN, never a plan with no design.",
        id="the-prohibition-written-down",
    ),
    pytest.param(
        "The per-requirement classification/effort is the design PRECONDITION: read it, do not "
        "re-derive it.",
        id="a-gap-artifact-as-designs-own-input",
    ),
]


@pytest.mark.parametrize("sample", CLAIM_MUST_NOT_CATCH)
def test_the_claim_detector_leaves_its_legitimate_neighbours_alone(sample):
    hits = find_planning_refusal_claims(sample)
    assert not hits, (
        f"the detector must NOT catch {sample!r} (matched {hits!r}) - firing on the declaration that "
        f"replaced the refusal, on the driver's design-NODE refusal, on an executor's plan-drift "
        f"stop, or on a recommendation would force the removed gate back into the tree"
    )


RESERVATION_MUST_NOT_CATCH = [
    pytest.param(
        "Non-trivial work SHOULD go `odoo-solution-design` -> `odoo-planning` - a front-door "
        "PREFERENCE, not a precondition.",
        id="the-recommendation-that-replaced-the-rule",
    ),
    pytest.param(
        "only DESIGN, via `odoo-solution-design`, may be skipped - RECOMMENDED for non-trivial "
        "work, never required.",
        id="the-skippable-half-stated",
    ),
    pytest.param(
        "A design is never required for non-trivial work, and nothing downstream refuses a plan "
        "whose design was skipped.",
        id="the-denial-of-the-framing",
    ),
    pytest.param(
        "`odoo-planning` turns that design into the dependency-ordered node execution plan.",
        id="planning-consuming-a-design-that-exists",
    ),
    pytest.param(
        "The design is READ BY POINTER as this plan's own data source and is APPROVED before the "
        "plan is authored.",
        id="the-one-way-ordering-itself",
    ),
]


@pytest.mark.parametrize("sample", RESERVATION_MUST_NOT_CATCH)
def test_the_modality_detector_leaves_the_recommendation_alone(sample):
    hits = find_design_reservations(sample)
    assert not hits, (
        f"the detector must NOT catch {sample!r} (matched {hits!r}) - a guard that fires on the "
        f"recommendation, on the denial of the old rule, or on planning consuming a design that "
        f"does exist would delete the steering the owner explicitly kept"
    )
