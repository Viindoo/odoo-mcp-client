"""Guard: technical DESIGN may never run AFTER execution PLANNING for the same body of work.

## The business rule (directional, not a mandate)

`odoo-solution-design` decides HOW to build; `odoo-planning` turns an APPROVED design into the
execution plan. The plan is DERIVED from the design, so the ordering is ONE-WAY:

    design (if it runs at all)  ->  plan  ->  execute

The rule is NOT "design must always run". A one-approach change legitimately skips design entirely
and plans straight through - forcing a design gate onto every request would make the plugin worse,
and `test_the_ordering_is_not_inflated_into_design_always_runs` protects that escape explicitly.
What is forbidden is the INVERSION: a design produced after the plan either invalidates the ordering
the human already approved, or gets reverse-engineered to justify it.

## CONTRACT CHANGE - the design PRECONDITION was removed by owner decision

The rule this file protects was NARROWED by the repo owner, and the tests were RE-DERIVED to the new
rule rather than patched to pass. The owner's statement:

    Design is NOT mandatory. Planning IS mandatory. If a design exists, it must come BEFORE the plan.

In its strong form, which is the reading the owner explicitly chose:

* planning is mandatory for ALL work and **must never be refused for a missing design**, at ANY
  complexity level - non-trivial included;
* a design is OPTIONAL at every complexity level and is never a precondition to planning;
* the ONLY surviving rule is directional - a design, IF it exists, precedes the plan; equivalently,
  and this is now the load-bearing form, **a design may never be a NODE of a plan**, only an INPUT.

The owner moved this way first in `dc444d5`, which widened `agents/odoo-planner.md` from "an APPROVED
technical design" to "an APPROVED technical design / development work" and deleted the planner's
design-gap refusal. This change completes that direction at the SKILL level.

So `skills/odoo-planning/SKILL.md` § Design precedes planning no longer carries the refusal predicate
(`if design_required and not design_present: REFUSE`) nor the `status: BLOCKED` / `next:
odoo-solution-design` hand-back branch it fed; both are GONE, and the tests that asserted them assert
their INVERSE now (see the re-derived tests below, each of which names the contract change in its own
docstring).

## Why prose alone is not enough

`snippets/planning-gate-contract.md` § Design-then-planning ordering STATES the ordering
("`odoo-planning` is DOWNSTREAM of `odoo-solution-design`"), but nothing in that file evaluates it.
Enforcement is now TWO surfaces plus one actor binding, and `odoo-planning` is not among them:

* `skills/odoo-intake/references/plan-mode-schema.md` - a node's `approach` may not be the design
  skill/agent, authored or materialized. Without it, `design depends_on <coding node>` is
  schema-legal.
* `skills/run-harness/` - the driver refuses such a node at BOTH entry points, since its `next[]` ->
  `materialize()` step otherwise turns any suggestion at `confidence >= 0.5` into a live node.
* `agents/odoo-planner.md` - the ACTOR that writes plans may wire no node to design (Rule X). Its
  removed Rule Y - requiring a design at all - must stay removed.

`skills/odoo-planning/SKILL.md` keeps the DECLARATION (mandatory planning, the one-way ordering, the
pointers at the three surfaces above) and enforces nothing.

So this file asserts the ENFORCEMENT POINTS exist and terminate correctly, that planning itself has
no refusal left, plus a tree-wide inversion detector. It deliberately does not assert any single
sentence: every check either parses a section's structure or runs a multi-shape detector, so
compliant prose may be rewritten freely.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

PLANNING = PLUGIN / "skills" / "odoo-planning" / "SKILL.md"
PLANNER = PLUGIN / "agents" / "odoo-planner.md"
SCHEMA = PLUGIN / "skills" / "odoo-intake" / "references" / "plan-mode-schema.md"
RUN_SKILL = PLUGIN / "skills" / "run-harness" / "SKILL.md"
RUN_REF = PLUGIN / "skills" / "run-harness" / "references" / "run-integration.md"
GATE = PLUGIN / "snippets" / "planning-gate-contract.md"

DESIGN_SKILL = "odoo-solution-design"
DESIGN_AGENT = "odoo-solution-architect"

_GENERATED = re.compile(
    r"<!-- BEGIN GENERATED TOOLS -->.*?<!-- END GENERATED TOOLS -->", re.DOTALL
)
_TEXT_EXTS = {".md", ".yaml", ".yml", ".json"}


def _read(path: Path) -> str:
    assert path.is_file(), f"{path} is missing - the ordering has no owner left"
    return _GENERATED.sub("", path.read_text(encoding="utf-8"))


def _flat(text: str) -> str:
    """Collapse whitespace so a wrapped sentence reads like a single line."""
    return re.sub(r"\s+", " ", text)


def _section(text: str, heading_pattern: str) -> str:
    """The span from a heading matching `heading_pattern` up to the next heading of <= depth."""
    m = re.search(heading_pattern, text, re.MULTILINE)
    assert m, f"no heading matching {heading_pattern!r}"
    depth = len(re.match(r"#+", m.group(0)).group(0))
    rest = text[m.end():]
    nxt = re.search(rf"(?m)^#{{1,{depth}}} ", rest)
    return m.group(0) + (rest[: nxt.start()] if nxt else rest)


def _tree_texts():
    """Every prose/config artifact under both plugin trees, generated blocks blanked."""
    for plugin_dir in sorted((ROOT / "plugins").iterdir()):
        if not plugin_dir.is_dir():
            continue
        for path in sorted(plugin_dir.rglob("*")):
            if path.is_file() and path.suffix in _TEXT_EXTS:
                yield path, _GENERATED.sub("", path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _plugin_texts() -> dict[str, str]:
    """`{plugin-relative path: text}` for the odoo-ai-agents tree, generated blocks blanked."""
    return {
        str(p.relative_to(PLUGIN)): _GENERATED.sub("", p.read_text(encoding="utf-8"))
        for p in sorted(PLUGIN.rglob("*"))
        if p.is_file() and p.suffix in _TEXT_EXTS
    }


#: The surfaces that ENFORCE the ordering after the contract change, each keyed on the prose that
#: performs the enforcement - never on a path. The owning file is RESOLVED from the tree, so a
#: surface that moves or is renamed makes a pointer at it a reported bug instead of a blind spot.
#: Whitespace-tolerant, because every one of these sentences line-wraps in its own file.
ENFORCEMENT_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "the SCHEMA constraint (no node's `approach` may be the design skill/agent)",
        re.compile(r"\*\*Design\s+is\s+an\s+INPUT\s+to\s+this\s+plan"),
    ),
    (
        "the DRIVER refusal (no tier for a design node, static or materialized)",
        re.compile(r"(?i)Neither\s+class\s+may\s+be\s+a\s+DESIGN\s+node"),
    ),
    (
        "the ACTOR binding (the plan author may wire no node it writes to design)",
        re.compile(r"(?i)no\s+node\s+you\s+author\s+may\s+be\s+wired\s+to"),
    ),
)


# ---------------------------------------------------------------------------
# The inversion detector (a pure function of text, so the probes below exercise
# the SAME code the real-tree sweep runs - never a parallel re-implementation).
# ---------------------------------------------------------------------------

_ARROWS = r"(?:-{1,3}>|={1,2}>|→|⇒|⟶)"
_DESIGN = rf"{DESIGN_SKILL}|{DESIGN_AGENT}"
_PLAN_ACTOR = r"odoo-planning|odoo-planner"

#: A window carrying one of these is PROHIBITING the inversion, not performing it. Without this,
#: every guard sentence written to forbid the shape would report itself as the shape (the failure
#: mode that makes a ban un-writable).
_PROHIBITION = re.compile(
    r"(?i)\bnever\b|\bmust not\b|\bmay not\b|\bcannot\b|refus|forbid|illegal"
    r"|schema violation|banned|upstream-only|is an INPUT|precedes planning"
    r"|DOWNSTREAM of|\bno node\b"
)

#: Each entry is one SHAPE the inversion can take. The set is deliberately redundant: this repo
#: keeps getting burned by guards that match exactly one phrasing and go green while a synonym,
#: a serialized field, an ASCII node box, or a chain arrow says the same thing.
INVERSION_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    # "odoo-planning -> odoo-solution-design" in any chain notation, ASCII or Unicode.
    ("planning-arrow-design",
     re.compile(rf"(?i)\b(?:{_PLAN_ACTOR})\b[^.\n]{{0,90}}?{_ARROWS}\s*`?(?:{_DESIGN})")),
    # A Block-2 ASCII node box wired to the design skill/agent.
    ("design-node-skill-tag", re.compile(rf"(?i)\[skill:\s*`?(?:{_DESIGN})")),
    # The serialized run-file shape: a node whose `approach` is the design skill.
    ("design-approach-field",
     re.compile(rf"(?i)\"?approach(?:_kind)?\"?\s*:\s*\"?`?(?:{_DESIGN})")),
    # A routing edge FROM the planning layer TO design: `odoo-planning` / `odoo-planner` emitting
    # `next: odoo-solution-design` (legal only inside the pre-plan refusal, which the prohibition
    # window exempts).
    ("plan-actor-emits-design",
     re.compile(rf"(?i)\b(?:{_PLAN_ACTOR})\b[^.]{{0,140}}?next:\s*`?(?:{_DESIGN})")),
    # Prose scheduling design after the plan exists.
    ("plan-then-design",
     re.compile(rf"(?i)\bafter (?:the |an )?(?:approved )?(?:plan|planning)\b[^.]{{0,140}}?(?:{_DESIGN})")),
    # Prose declaring design downstream of planning (the ordering statement, inverted).
    ("design-after-planning",
     re.compile(rf"(?i)(?:{_DESIGN})\b[^.]{{0,90}}?\b(?:after|follows|downstream of)\b"
                rf"[^.]{{0,60}}?(?:{_PLAN_ACTOR}|the plan\b)")),
    # The driver turning a `next[]` suggestion into a live design node.
    ("materialize-design", re.compile(rf"(?i)materiali\w+[^.]{{0,90}}?(?:{_DESIGN})")),
    # A Block-3 assignment line: `<node-id> -> odoo-solution-design`. The left operand is filtered
    # below - a chain of SKILL names ("gap -> design -> planning") is routing prose, not a node
    # assignment, and points the correct way.
    ("block3-assignment",
     re.compile(rf"(?im)^\s*(?:[-*]\s*)?`?(?P<lhs>[\w./-]+)`?\s*{_ARROWS}\s*`?(?:{_DESIGN})")),
)

_WINDOW = 260


def _routable_names() -> frozenset[str]:
    """Every skill and agent name that exists on disk, resolved from the tree (never hardcoded).

    A plan NODE id is by construction not one of these (the schema says name a node for the WORK),
    so a left operand that IS a skill/agent name marks the arrow as chain/routing notation.
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


def find_inversions(text: str) -> list[tuple[str, str]]:
    """Every (shape-name, matched-text) in `text` that PERFORMS the inversion.

    A hit inside a prohibiting window is not an offender - that is the ban being written down.
    """
    out: list[tuple[str, str]] = []
    for name, rx in INVERSION_SHAPES:
        for m in rx.finditer(text):
            if name == "block3-assignment" and m.group("lhs") in ROUTABLE:
                continue  # `gap-analysis -> solution-design -> planning`: routing chain, correct way
            window = text[max(0, m.start() - _WINDOW): m.end() + _WINDOW]
            if _PROHIBITION.search(window):
                continue
            out.append((name, m.group(0)))
    return out


# ---------------------------------------------------------------------------
# Enforcement point 1 - REMOVED BY OWNER DECISION. `odoo-planning` now DECLARES
# the ordering and enforces nothing: it may never refuse to plan for a missing
# design. What follows protects the ABSENCE of that refusal, in every phrasing
# it could return in, plus the declaration that replaced it.
# ---------------------------------------------------------------------------

#: Vocabulary for the refusal detector. `_ABSENT` + `_DESIGN_WORD` locate the trigger (a design that
#: is not there); `_WITHHOLD` locates the effect that makes it a refusal (the plan does not get
#: authored); `_PRECONDITION` catches the same rule stated as a requirement instead of an effect.
_DESIGN_WORD = rf"(?:design\b|{DESIGN_SKILL}|{DESIGN_AGENT})"
_ABSENT = r"(?:missing|absent|no|without|unresolved|unavailable|not present|lack\w*)"
_WITHHOLD = (
    r"(?:REFUSE\w*|refus\w+|BLOCKED|blocks?\b|blocked\b|authors? no plan|writes? NO plan"
    r"|no plan (?:file )?(?:is |may be |gets )?(?:authored|written|produced)"
    r"|dispatch(?:es|ed|ing)? (?:NEITHER|no|neither) planner|stops?\b"
    r"|do NOT (?:plan|dispatch)|never plans?\b)"
)
_PRECONDITION = (
    r"(?:precondition|prerequisite|is required before"
    r"|must (?:run|exist|be approved) (?:first|before)|gate before (?:the )?plan\w*)"
)

#: An assertion word directly governed by a negation is the rule being DENIED, not imposed
#: ("planning is NEVER refused for a missing design"). Kept deliberately TIGHT - the negation must
#: sit within a couple of words of the assertion word, not merely somewhere in the sentence - and a
#: hedged denial ("never refused ... except when non-trivial") is caught by its own shape below.
_NEGATED = re.compile(r"(?i)(?:\bnever\b|\bnot\b|\bno\b)\W+(?:\w+\W+){0,2}$")

#: Each entry is one SHAPE a design PRECONDITION can take inside the planning skill. Redundant on
#: purpose: this repo keeps getting burned by guards that match one phrasing and go green while a
#: synonym, a predicate block, a hand-back branch, or a "route to design FIRST" says the same thing.
#: The group `w` marks the assertion word the `_NEGATED` test is applied to.
REFUSAL_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    # The deleted predicate itself, by either of its variable names.
    ("refusal-predicate-tokens", re.compile(r"(?i)design_required|design_present")),
    # An absent design withholding the plan - the refusal stated as an effect.
    ("absent-design-withholds-the-plan",
     re.compile(rf"(?i){_ABSENT}[^.]{{0,60}}{_DESIGN_WORD}[^.]{{0,140}}?(?P<w>{_WITHHOLD})")),
    # The same, written effect-first ("REFUSE when no design is present").
    ("withhold-then-absent-design",
     re.compile(rf"(?i)(?P<w>{_WITHHOLD})[^.]{{0,140}}?{_ABSENT}\W{{0,4}}\w{{0,12}}\W{{0,4}}"
                rf"{_DESIGN_WORD}")),
    # The refusal stated as a requirement rather than an effect.
    ("design-is-a-precondition",
     re.compile(rf"(?i){_DESIGN_WORD}[^.]{{0,80}}(?P<w>{_PRECONDITION})")),
    ("no-plan-until-a-design",
     re.compile(r"(?i)(?P<w>no plan|neither planner|any plan)[^.]{0,100}(?:until|unless|without)"
                r"[^.]{0,60}design")),
    # The pre-2367acb spelling: send the caller to design BEFORE planning anything.
    ("route-out-before-planning",
     re.compile(rf"(?i)(?:route|hand (?:back|off)|go|escalate)[^.]{{0,60}}"
                rf"(?P<w>{DESIGN_SKILL}|{DESIGN_AGENT})[^.]{{0,60}}"
                rf"(?:FIRST\b|before (?:the |any )?(?:plan|planner|dispatch))")),
    # A denial that carves the refusal back out as an exception.
    ("refusal-hedged-by-an-exception",
     re.compile(r"(?i)(?:never refus\w+|no refusal|always plans?)[^.]{0,90}"
                r"\b(?:except|unless|but not|save when|other than)\b[^.]{0,90}design")),
    # The same absence stated AFTER the design word ("stops ... when the design DAG pointer is
    # unresolved"): both shapes above require the absence word FIRST, so this ordering was a hole.
    ("withhold-then-unresolved-design",
     re.compile(rf"(?i)(?P<w>{_WITHHOLD})[^.]{{0,140}}?{_DESIGN_WORD}[^.]{{0,60}}?"
                rf"\b(?:is|are|was|were|remains?)\s+(?:{_ABSENT})\b")),
    # The hand-back that carried the refusal out.
    ("blocked-hand-back-to-design",
     re.compile(rf"(?i)(?P<w>status:\s*BLOCKED)[^.]{{0,160}}(?:{DESIGN_SKILL}|{DESIGN_AGENT})")),
)


def find_planning_refusals(text: str) -> list[tuple[str, str]]:
    """Every (shape, hit) making a design a precondition of PLANNING (the removed rule)."""
    flat = _flat(text)
    out: list[tuple[str, str]] = []
    for name, rx in REFUSAL_SHAPES:
        for m in rx.finditer(flat):
            at = m.start("w") if "w" in rx.groupindex else m.start()
            if name != "refusal-hedged-by-an-exception" and _NEGATED.search(flat[max(0, at - 28): at]):
                continue  # the rule being DENIED, not imposed
            out.append((name, m.group(0)))
    return out


def test_a_design_required_change_with_no_design_still_gets_a_plan():
    """CONTRACT CHANGE (owner decision): the refusal predicate was REMOVED, not made to pass.

    This test is the INVERSE of the one it replaces
    (`test_a_design_required_change_with_no_design_never_gets_a_plan`, which asserted the predicate
    `if design_required and not design_present: REFUSE` and its plan-withholding effect).

    Behaviour protected: planning is mandatory for ALL work and never refuses for a missing design,
    at any complexity level - so a non-trivial change with no design artifact STILL gets a plan.
    Fails if a design precondition returns to the planning skill in any of the shapes above.
    """
    text = _read(PLANNING)
    offenders = find_planning_refusals(text)
    assert not offenders, (
        f"skills/odoo-planning/SKILL.md makes a design a PRECONDITION of planning: {offenders}. "
        f"That rule was removed by owner decision - planning is mandatory for ALL work and is never "
        f"refused for a missing design, at any complexity level. The surviving rule is directional "
        f"only (a design, if it exists, precedes the plan) and is ENFORCED as a plan-SHAPE ban at "
        f"the schema, the driver and the plan-author agent - never as a gate here."
    )
    section = _flat(_section(text, r"(?m)^## Design precedes planning.*$"))
    assert re.search(r"(?i)planning is MANDATORY for ALL work", section) and re.search(
        r"planning-gate-contract\.md` § Mandatory-planning rule", section
    ), (
        "§ Design precedes planning must keep stating that planning is mandatory for ALL work, with "
        "its `planning-gate-contract.md` § Mandatory-planning rule citation - that is the half of "
        "the owner's rule this section still owns."
    )
    assert re.search(
        r"(?i)(?:design is\s+OPTIONAL|no design (?:at all )?is the common case"
        r"|never a precondition|not a precondition)", section
    ), (
        "§ Design precedes planning must say a design is OPTIONAL / never a precondition - a section "
        "that only forbids the inversion leaves the next reader free to re-derive the gate."
    )
    assert re.search(r"(?i)proceed to § Agent invocation", section), (
        "§ Design precedes planning must send every case onward to § Agent invocation. With the "
        "refusal gone there is no other outcome, and an outcome nobody states is one an LLM invents."
    )


def test_the_one_way_ordering_survives_as_a_declaration_pointing_at_its_enforcement():
    """CONTRACT CHANGE: surface 1 became a DECLARATION; the ordering itself must NOT be lost with it.

    Behaviour protected: the planning skill still tells its reader (a) a design may never be produced
    after the plan and WHY, and (b) where that is actually enforced - each pointer resolving to a
    file whose prose does the enforcing. Fails if the removal of the refusal took the rule with it,
    or if a pointer names a file that no longer enforces anything.
    """
    section = _section(_read(PLANNING), r"(?m)^## Design precedes planning.*$")
    flat = _flat(section)
    assert re.search(r"(?i)design may never be produced AFTER (?:this|the) plan", flat), (
        "§ Design precedes planning must keep DECLARING the one-way rule (a design may never be "
        "produced after the plan). Deleting the refusal must not delete the ordering it served."
    )
    assert re.search(r"(?i)(derived from the design|reverse-engineer)", flat), (
        "The declaration must carry its REASON (the plan is DERIVED from the design; a design "
        "authored afterwards is reverse-engineered to justify it) - a reasonless rule does not "
        "survive the next trim."
    )
    assert re.search(rf"(?i)(?:an )?INPUT to a plan, NEVER a node|design is an INPUT", flat), (
        "The declaration must state the load-bearing form: a design is an INPUT to a plan, never a "
        "node of one. That is the form the schema, the driver and the plan author all enforce."
    )
    # Each enforcement owner is RESOLVED from the tree by the prose that enforces, then required to
    # be cited here. A surface that moves file makes this demand an updated pointer - it cannot go
    # green on a stale path.
    for label, marker in ENFORCEMENT_MARKERS:
        owners = [rel for rel, txt in _plugin_texts().items() if marker.search(txt)]
        assert len(owners) == 1, (
            f"{label}: expected exactly ONE file under plugins/odoo-ai-agents to carry "
            f"{marker.pattern!r}; found {owners}"
        )
        assert owners[0] in flat, (
            f"§ Design precedes planning must point at {label} (`{owners[0]}`) - this section only "
            f"DECLARES the ordering now, so a reader who wants the rule ENFORCED has nowhere to go "
            f"without the pointer. That is the 'described, never reached' defect, inverted."
        )


REFUSAL_MUST_CATCH = [
    pytest.param(
        "if design_required and not design_present:  REFUSE - author no plan, dispatch no planner",
        id="the-deleted-predicate-verbatim",
    ),
    pytest.param(
        "When the change is non-trivial and no design artifact exists on disk, REFUSE: dispatch "
        "neither planner and write NO plan file.",
        id="prose-refusal-carrying-no-predicate-tokens",
    ),
    pytest.param(
        "- **A design-required change with no design:** emit `status: BLOCKED`, `produced: []`, and "
        "`next: odoo-solution-design` naming the trigger.",
        id="the-deleted-hand-back-branch",
    ),
    pytest.param(
        "An approved design is a precondition of dispatching either planner.",
        id="refusal-restated-as-a-precondition",
    ),
    pytest.param(
        "No plan may be authored until an approved design exists for a non-trivial change.",
        id="no-plan-until-a-design",
    ),
    pytest.param(
        "If the design artifact is absent, route to `odoo-solution-design` FIRST - do not plan an "
        "ungrounded build order.",
        id="the-pre-refusal-route-out-first",
    ),
    pytest.param(
        "Planning is never refused for a missing design, except when the change is non-trivial - "
        "there the design gate still stops the dispatch.",
        id="denial-that-carves-the-gate-back-out",
    ),
    pytest.param(
        "Missing design DAG pointer on an Extension-L change: stop before § Agent invocation and "
        "hand back.",
        id="stop-before-dispatch",
    ),
    # The two holes found while building tests/test_no_design_precondition_survives.py: every
    # withhold verb was spelled un-inflected, and every shape required the absence word BEFORE the
    # design word. Both were widened above; these probes are why.
    pytest.param(
        "When no approved design exists on disk, `odoo-planning` dispatches neither planner and "
        "writes NO plan file.",
        id="withhold-verbs-inflected",
    ),
    pytest.param(
        "The planner stops before authoring anything when the design DAG pointer is unresolved.",
        id="absence-stated-after-the-design-word",
    ),
]


@pytest.mark.parametrize("sample", REFUSAL_MUST_CATCH)
def test_the_refusal_detector_catches_every_shape_the_gate_could_return_in(sample):
    assert find_planning_refusals(sample), (
        f"the detector must catch {sample!r} - a design gate can come back in a dozen phrasings, "
        f"and a guard that only knows the deleted predicate's exact words is no guard"
    )


REFUSAL_MUST_NOT_CATCH = [
    pytest.param(
        "**Planning is MANDATORY for ALL work, and is NEVER refused for a missing design**. A design "
        "is OPTIONAL at EVERY complexity level - non-trivial included - and is never a precondition "
        "to planning.",
        id="the-declaration-that-replaced-the-refusal",
    ),
    pytest.param(
        "**The ONE surviving rule is directional: a design may never be produced AFTER this plan.** "
        "The plan is DERIVED from the design.",
        id="the-surviving-one-way-rule",
    ),
    pytest.param(
        "**A MISSING design artifact is NOT one of those questions:** a design is not a precondition "
        "to planning at any complexity level, so an absent one is carried as `DESIGN_INDEX: none`.",
        id="absent-design-is-not-even-a-question",
    ),
    pytest.param(
        "This skill evaluates NO design predicate and owns NO refusal branch.",
        id="the-removal-stated-in-the-skill",
    ),
    pytest.param(
        "**schema** - no node's `approach` may be `odoo-solution-design` / "
        "`odoo-solution-architect`, authored or materialized at runtime.",
        id="the-plan-shape-ban-pointer",
    ),
    pytest.param(
        "**driver** - such a node gets no tier and is never dispatched, static or materialized, at "
        "any confidence.",
        id="the-driver-refusal-pointer",
    ),
    pytest.param(
        "The plan must never invent a module or dependency the design did not establish - escalate "
        "(`NEEDS_CONTEXT`) only for a sequencing decision no artifact encodes.",
        id="escalation-scoped-to-sequencing",
    ),
    pytest.param(
        "When `return_to` is SET the caller owns the gate: do NOT enter here; hand control back via "
        "the Continuation Contract without ever opening or closing Plan Mode.",
        id="plan-mode-guard-return-to-branch",
    ),
]


@pytest.mark.parametrize("sample", REFUSAL_MUST_NOT_CATCH)
def test_the_refusal_detector_leaves_the_declaration_and_the_pointers_alone(sample):
    hits = find_planning_refusals(sample)
    assert not hits, (
        f"the detector must NOT catch {sample!r} (matched {hits!r}) - firing on the declaration that "
        f"replaced the refusal, on the surviving one-way rule, or on a pointer at another surface's "
        f"enforcement would force the design gate back into the skill"
    )


def test_plannings_own_contract_has_no_hand_back_branch_left_to_reach():
    """CONTRACT CHANGE: the third Continuation-Contract branch was the refusal's only exit - it went.

    This test replaces `test_the_route_back_to_design_is_reachable_from_plannings_own_contract`,
    which asserted that branch existed (`next: odoo-solution-design`, `produced: []`, no `plan:`
    key). With the refusal gone that branch had NO trigger left, making it exactly the "mechanism
    described, never reached" defect this repo keeps getting bitten by.

    Behaviour protected: every branch the contract enumerates is one the skill can actually take -
    it always authors a plan, so every branch carries a plan pointer and none hands back a no-plan
    result. Fails if an unreachable no-plan/design branch is reintroduced.
    """
    section = _section(_read(PLANNING), r"(?m)^## Continuation Contract\s*$")
    flat = _flat(section)
    bullets = re.split(r"(?m)^- \*\*", section)[1:]
    assert len(bullets) >= 2, (
        f"§ Continuation Contract must still enumerate its branches as a bullet list (found "
        f"{len(bullets)}) - an unenumerated blob cannot be checked branch by branch"
    )
    assert f"next: {DESIGN_SKILL}" not in flat, (
        "§ Continuation Contract must not carry a `next: odoo-solution-design` branch. Planning "
        "always authors a plan now, so a design hand-off from this contract would name a design "
        "AFTER the plan derived from it - the inverted order - and no branch can trigger it anyway."
    )
    assert not re.search(r"produced:\s*\[\s*\]", flat), (
        "§ Continuation Contract must not carry a `produced: []` branch: with no refusal left there "
        "is no path on which this skill produces nothing, and a branch with no trigger is prose."
    )
    assert not re.search(r"(?i)status:\s*BLOCKED", flat), (
        "§ Continuation Contract must not enumerate a BLOCKED branch for a design gap - the only "
        "trigger it ever had was the removed refusal."
    )
    for bullet in bullets:
        one = _flat(bullet)
        assert re.search(r"inputs:\s*\{[^}]*\bplan\s*:", one), (
            f"every § Continuation Contract branch must carry a plan pointer, because every "
            f"invocation authors a plan; this one does not: {one[:140]!r}"
        )


def test_planning_never_hands_off_to_design_now_that_a_plan_always_exists():
    """CONTRACT CHANGE: the old allowlist of two legal homes collapsed to ZERO legal homes.

    Replaces `test_planning_routes_to_design_only_before_a_plan_exists`, which located each
    `next: odoo-solution-design` by its enclosing section and allowed the two homes the refusal
    owned. The test keeps its meaning under the new contract, in a STRONGER form: planning now
    always authors a plan, so there is no section left where a design hand-off precedes one - any
    occurrence at all is the inversion.

    Behaviour protected: `odoo-planning` never schedules or recommends a design, from any section.
    """
    text = _read(PLANNING)
    headings = [(m.start(), m.group(0).strip()) for m in re.finditer(r"(?m)^## .*$", text)]
    assert len(headings) >= 5, "odoo-planning/SKILL.md must keep its `##` section structure"

    def owning_section(pos: int) -> str:
        owner = "<preamble>"
        for start, title in headings:
            if start <= pos:
                owner = title
            else:
                break
        return owner

    route_rx = re.compile(rf"next:\s*`?(?:{DESIGN_SKILL}|{DESIGN_AGENT})")
    hits = [f"{owning_section(m.start())!r} -> {m.group(0)!r}" for m in route_rx.finditer(text)]
    assert not hits, (
        f"odoo-planning routes to the design skill/agent: {hits}. Every invocation of this skill "
        f"authors a plan now, so a design hand-off from ANY of its sections names a design AFTER the "
        f"plan derived from it. A design gap is a design INPUT that was never authored, not a "
        f"follow-up step."
    )

    gate = _flat(_section(text, r"(?m)^## Plan-approval gate.*$"))
    assert DESIGN_SKILL not in gate and DESIGN_AGENT not in gate, (
        "§ Plan-approval gate must not name the design skill/agent at all: every branch of that "
        "gate runs with the plan already written to disk, so any design it schedules is the "
        "inverted order."
    )


# ---------------------------------------------------------------------------
# Enforcement point 2 - the plan SCHEMA makes a design node illegal.
# ---------------------------------------------------------------------------


def test_a_plan_may_never_wire_a_node_to_the_design_skill():
    """The DAG shape itself must be illegal, not merely discouraged.

    Behaviour protected: `design depends_on <any node>` cannot be authored, because a design node
    inside a plan derived FROM a design is a contradiction. Fails if the constraint or its reason
    is dropped (a bare ban with no reason gets 'simplified' away in the next trim).
    """
    flat = _flat(_read(SCHEMA))
    assert re.search(
        rf"(?i)no node'?s? `?approach`? may be `?{DESIGN_SKILL}", flat
    ), (
        "plan-mode-schema.md must forbid `odoo-solution-design` as a node's `approach` - the "
        "schema's exhaustive `approach_kind` / node-field lists do not imply it, so an LLM planner "
        "authoring a `design` node breaks no stated rule."
    )
    assert DESIGN_AGENT in flat, (
        "The ban must cover the `odoo-solution-architect` AGENT too, or the same node returns as "
        "`approach_kind: agent`."
    )
    assert re.search(r"(?i)materiali\w+ at runtime|materialized at runtime|from a `next\[\]`", flat), (
        "The ban must cover a node MATERIALIZED at runtime from a `next[]`, not only an authored "
        "one - `run-harness` creates nodes the plan never named."
    )
    assert re.search(r"(?i)(derived from the design|reverse-engineer)", flat), (
        "The constraint must carry its REASON (the plan is derived from the design; a later design "
        "gets reverse-engineered to justify it) - a reasonless ban does not survive a trim."
    )
    assert re.search(r"(?i)schema violation", flat), (
        "A plan carrying such a node must be named a SCHEMA VIOLATION, so the driver has a "
        "classification to act on rather than a style preference."
    )


def test_the_plan_author_agent_is_forbidden_to_author_a_design_node():
    """The ban must also bind the ACTOR that writes the plan, not just the schema it conforms to."""
    flat = _flat(_read(PLANNER))
    assert re.search(rf"(?i)no node .{{0,80}}(wired to|be) `?{DESIGN_SKILL}", flat), (
        "agents/odoo-planner.md must forbid authoring a node wired to `odoo-solution-design`; "
        "'never design, never code' bans the agent from DOING design, not from SCHEDULING it."
    )
    assert re.search(r"(?i)NEEDS_CONTEXT", flat), (
        "The planner must have a terminating move for a design gap (return NEEDS_CONTEXT) - "
        "without one, scheduling a design node is the only way out of the gap."
    )


#: The plan-author agent bundles TWO different rules about design, and only ONE of them is
#: unconditional:
#:
#:   Rule X - the plan's SHAPE: no node the planner authors may be wired to the design skill/agent.
#:            Always true (the test above owns it); design is an INPUT, never a node.
#:   Rule Y - REQUIRING a design: "a design gap means return NEEDS_CONTEXT and author no plan".
#:            Deliberately REMOVED from the AGENT when its input widened from "an APPROVED technical
#:            design" to "an APPROVED technical design / development work" - the planner may plan
#:            development work that has no formal design document.
#:
#: Restoring Rule X must not drag Rule Y back with it, nor reintroduce it by implication. Rule Y is
#: now forbidden at BOTH levels: the owner's decision removed `odoo-planning`'s own refusal too, so
#: this detector is pointed at the AGENT and at the SKILL (the skill case is
#: `test_the_planning_skill_carries_no_design_mandate_either` below; the richer skill-level sweep is
#: `find_planning_refusals` further up).
DESIGN_MANDATE_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("gap-returns-needs-context",
     re.compile(r"(?i)(?:design (?:gap|is missing|absent)|missing design|no (?:approved )?design)"
                r"[^.]{0,140}NEEDS_CONTEXT")),
    ("needs-context-for-a-design-gap",
     re.compile(r"(?i)NEEDS_CONTEXT[^.]{0,140}"
                r"(?:design (?:gap|is missing)|missing design|no (?:approved )?design)")),
    ("no-design-no-plan",
     re.compile(r"(?i)(?:without|no|absent|missing)[^.]{0,60}design[^.]{0,120}"
                r"(?:author no plan|no plan (?:is |may be )?(?:authored|written)|write no plan"
                r"|refuse to plan)")),
    ("design-declared-mandatory",
     re.compile(r"(?i)an? (?:approved )?(?:technical )?design is (?:mandatory|required"
                r"|a (?:hard )?prerequisite)")),
    ("plan-only-with-a-design",
     re.compile(r"(?i)(?:never|do not|don't|must not) (?:author|write|produce|emit)[^.]{0,40}plan"
                r"[^.]{0,80}(?:without|unless|until)[^.]{0,60}design")),
)


def find_design_mandates(text: str) -> list[tuple[str, str]]:
    """Every (shape, hit) that makes an approved DESIGN a precondition of authoring a plan."""
    flat = _flat(text)
    return [(name, m.group(0)) for name, rx in DESIGN_MANDATE_SHAPES for m in rx.finditer(flat)]


def test_the_plan_author_agents_ban_is_a_shape_rule_not_a_design_mandate():
    """Anti-over-fix, agent side: Rule X came back; Rule Y must stay gone.

    Behaviour protected: the planner still refuses to SCHEDULE a design, while remaining able to
    plan development work that has no formal design document. Fails if a design gap is turned back
    into a refusal to author a plan at the AGENT level, by any of the shapes above. KEPT UNWEAKENED
    across the contract change - it now protects the owner's decision rather than sitting beside it.
    """
    offenders = find_design_mandates(_read(PLANNER))
    assert not offenders, (
        f"agents/odoo-planner.md makes an approved design a PRECONDITION of authoring a plan: "
        f"{offenders}. That rule was removed on purpose when the agent's input widened to "
        f"'an APPROVED technical design / development work' - the SHAPE ban (no node wired to the "
        f"design skill/agent) is the unconditional half and the test above owns it. There is no "
        f"design-required refusal anywhere any more - not here and not in "
        f"skills/odoo-planning/SKILL.md, whose § Design precedes planning now only DECLARES the "
        f"order and points at the surfaces that enforce it."
    )


def test_the_planning_skill_carries_no_design_mandate_either():
    """The mandate detector, pointed at the SKILL - the place a design gate could now creep back in.

    Its docstring used to say the opposite ("this detector must never be pointed at the skill"),
    because the skill's own refusal was REQUIRED. The CONTRACT CHANGED by owner decision: the skill
    refuses nothing now, so the same Rule-Y shapes are as forbidden here as in the agent. Kept
    alongside the shape-rich `find_planning_refusals` sweep above: two independent detectors over
    the same behaviour, so a phrasing that slips past one still has to slip past the other.
    """
    offenders = find_design_mandates(_read(PLANNING))
    assert not offenders, (
        f"skills/odoo-planning/SKILL.md makes an approved design a PRECONDITION of authoring a plan: "
        f"{offenders}. Planning is mandatory for ALL work and never refused for a missing design "
        f"(owner decision); the ordering survives only as a plan-SHAPE ban enforced at the schema, "
        f"the driver and the plan-author agent."
    )


MANDATE_MUST_CATCH = [
    pytest.param(
        "A design gap is never yours to schedule: return `NEEDS_CONTEXT` naming the gap, and author "
        "no plan around it.",
        id="the-deleted-rule-y-verbatim",
    ),
    pytest.param(
        "If no approved design exists, stop and return NEEDS_CONTEXT instead of planning.",
        id="no-approved-design-needs-context",
    ),
    pytest.param(
        "Never author a plan without an approved technical design in your inputs.",
        id="never-plan-without-a-design",
    ),
    pytest.param(
        "An approved design is mandatory before you write anything into the plan file.",
        id="design-declared-mandatory",
    ),
    pytest.param(
        "Return `NEEDS_CONTEXT` when the design is missing - the plan cannot be grounded.",
        id="needs-context-then-missing-design",
    ),
]


@pytest.mark.parametrize("sample", MANDATE_MUST_CATCH)
def test_the_design_mandate_detector_catches_every_shape_of_rule_y(sample):
    assert find_design_mandates(sample), (
        f"the detector must catch {sample!r} - Rule Y can come back in a dozen phrasings, and a "
        f"guard that only knows the deleted sentence's exact words is no guard"
    )


MANDATE_MUST_NOT_CATCH = [
    pytest.param(
        "**no node you author may be wired to `odoo-solution-design` or "
        "`odoo-solution-architect`** - design is an INPUT to this plan, never a node of it.",
        id="rule-x-the-restored-shape-ban",
    ),
    pytest.param(
        "You turn an APPROVED technical design / development work into a reviewable, runnable "
        "EXECUTION PLAN.",
        id="the-widened-input-statement",
    ),
    pytest.param(
        "Escalate (`NEEDS_CONTEXT`) only for a sequencing decision no artifact encodes - never to "
        "ask a human to paste the design.",
        id="needs-context-scoped-to-sequencing",
    ),
    pytest.param(
        "Missing `INPUTS` entirely, or a load-bearing family field with no safe default: STOP and "
        "return `NEEDS_CONTEXT(<field>)`.",
        id="brief-self-check-needs-context",
    ),
    pytest.param(
        "When the oracle is absent (the common case), author the acceptance node's criteria from "
        "the design's §9 Acceptance Criteria instead.",
        id="absent-oracle-falls-back-to-the-design",
    ),
]


@pytest.mark.parametrize("sample", MANDATE_MUST_NOT_CATCH)
def test_the_design_mandate_detector_leaves_the_shape_ban_and_real_escalations_alone(sample):
    hits = find_design_mandates(sample)
    assert not hits, (
        f"the detector must NOT catch {sample!r} (matched {hits!r}) - firing on Rule X, on the "
        f"widened input statement, or on an unrelated NEEDS_CONTEXT escalation would force the "
        f"agent back into requiring a design"
    )


# ---------------------------------------------------------------------------
# Enforcement point 3 - the DRIVER refuses a design node, static or dynamic.
# ---------------------------------------------------------------------------


def test_the_driver_refuses_a_design_node_whether_static_or_materialized():
    """Both entry points a node can use into a live run must reject the design skill.

    Behaviour protected: the schema constraint is not self-enforcing - `run-harness` never reads
    plan-mode-schema.md at dispatch, so the refusal must exist in the driver's own tree, for the
    static (plan-named) node AND the dynamic (`next[]`-materialized) node.
    """
    texts = {p: _read(p) for p in sorted((PLUGIN / "skills" / "run-harness").rglob("*.md"))}
    carriers = {p: t for p, t in texts.items() if DESIGN_SKILL in t}
    assert carriers, (
        "No file under skills/run-harness/ mentions `odoo-solution-design`. The driver's `next[]` "
        "-> materialize() step will happily create a design node mid-run, and its plan-agreement "
        "checks never look at `approach` against a ban list."
    )
    blob = _flat(" ".join(carriers.values()))

    assert re.search(r"(?i)STATIC node", blob) and re.search(
        r"(?i)STOP the run BLOCKED", blob
    ), (
        "The driver must reject a STATIC plan node whose `approach` is the design skill by stopping "
        "the run BLOCKED - never by dispatching it or re-tiering it."
    )
    assert re.search(r"(?i)route back to `?odoo-planning", blob), (
        "The refusal must route back to `odoo-planning` (amend the plan) - the same disagreement "
        "path every plan-agreement check takes. A stop with no named owner leaves the driver as "
        "the only actor who can proceed, which it does by improvising."
    )
    assert re.search(r"(?i)NEVER materiali", blob), (
        "The driver must refuse to MATERIALIZE a `next[]`/`on_complete` suggestion naming the "
        "design skill - that is the live path by which design lands inside a plan it did not "
        "appear in."
    )
    assert re.search(r"(?i)at ANY `?confidence", blob), (
        "The materialization refusal must be unconditional on `confidence` - the circuit-breaker "
        "only demotes a low-confidence suggestion to 'surface it', which still schedules the design."
    )


def test_the_terminal_stage_order_constant_carries_no_design_stage():
    """The lifecycle tail every plan copies must have no design position.

    Behaviour protected: a design stage inside the Terminal stage order would put design after
    every coding and verification node BY CONSTRUCTION, in every plan at once.
    """
    section = _section(RUN_REF.read_text(encoding="utf-8"), r"(?m)^### Terminal stage order.*$")
    fenced = re.findall(r"```text\n(.*?)```", section, re.DOTALL)
    assert fenced, "§ Terminal stage order must render the constant in a fenced ```text block"
    constant = fenced[0]
    for token in (DESIGN_SKILL, DESIGN_AGENT):
        assert token not in constant, (
            f"{token!r} appears in the Terminal stage order constant - every plan copies this order "
            f"into its `depends_on` edges, so a design position here inverts the ordering for every "
            f"run at once."
        )
    assert not re.search(r"(?im)^\s*\+-->\s*\(\d+\)\s+design\b", constant), (
        "A bare `design` stage was added to the Terminal stage order constant."
    )


# ---------------------------------------------------------------------------
# The stated ordering must still be stated, and must NOT be over-tightened.
# ---------------------------------------------------------------------------


def test_the_ordering_statement_keeps_its_ssot():
    """The enforcement points above cite a rule; that rule must still be declared once."""
    flat = _flat(_read(GATE))
    assert re.search(r"(?i)`odoo-planning` is DOWNSTREAM of `odoo-solution-design`", flat), (
        "planning-gate-contract.md must keep declaring the design-then-planning ordering - it is "
        "the rule the schema constraint and the driver refusal both enforce."
    )


def test_the_ordering_is_not_inflated_into_design_always_runs():
    """Anti-over-fix: the DESIGN gate stays skippable; only the ORDER is fixed.

    A fix that forced a design onto every request would be worse than the bug - it would gate
    trivial work behind an architecture document. This asserts the escape survives in both the
    refusal section and the mandatory-planning SSOT.
    """
    planning = _flat(_section(_read(PLANNING), r"(?m)^## Design precedes planning.*$"))
    assert re.search(r"(?i)NOT \"?design always runs|not a mandate that design always runs", planning), (
        "§ Design precedes planning must say explicitly that it does NOT mean design always runs - "
        "otherwise the next reader turns a directional rule into a universal design gate."
    )
    assert re.search(r"(?i)one-approach change", planning), (
        "The refusal section must name the one-approach change that legitimately has no design."
    )
    gate = _flat(_read(GATE))
    assert re.search(r"(?i)DESIGN.{0,120}(may be skipped|reserved for non-trivial)", gate), (
        "planning-gate-contract.md must keep stating that only DESIGN may be skipped (planning "
        "never is) - the escape the ordering rule must not swallow."
    )


# ---------------------------------------------------------------------------
# Tree-wide sweep.
# ---------------------------------------------------------------------------


def test_the_tree_sweep_actually_has_a_corpus_to_sweep():
    """Discovery floor - a sweep over an empty corpus is green for the wrong reason."""
    paths = [p for p, _ in _tree_texts()]
    assert len(paths) >= 200, (
        f"expected the plugin trees to yield a substantial prose corpus, found {len(paths)} files - "
        f"the inversion sweep below would pass vacuously"
    )
    design_mentions = sum(1 for _, t in _tree_texts() if DESIGN_SKILL in t)
    assert design_mentions >= 10, (
        f"only {design_mentions} files mention {DESIGN_SKILL!r} - the sweep has nothing to judge"
    )


def test_no_file_in_either_plugin_describes_design_running_after_planning():
    """Whole-tree sweep for every shape in INVERSION_SHAPES.

    Scope is both plugin trees and every prose/config extension, not an allowlist of the files this
    round happened to touch: a future skill/agent/workflow that spells the inversion is caught with
    zero edits here.
    """
    offenders = []
    for path, text in _tree_texts():
        for shape, hit in find_inversions(text):
            line = text[: text.index(hit)].count("\n") + 1 if hit in text else 0
            offenders.append(f"{path.relative_to(ROOT)}:{line} [{shape}] {hit[:110]!r}")
    assert not offenders, (
        "These sites describe or perform DESIGN running AFTER PLANNING for the same work:\n  "
        + "\n  ".join(offenders)
        + "\nThe plan is derived from the design; a design produced afterwards invalidates the "
        "approved ordering or is reverse-engineered to justify it."
    )


# ---------------------------------------------------------------------------
# Detector proofs. MUST-CATCH: the shapes the inversion can take. MUST-NOT-CATCH:
# compliant prose, including the ban's own wording and the correct-direction chain.
# ---------------------------------------------------------------------------

MUST_CATCH = [
    pytest.param(
        "The chain is odoo-planning -> odoo-solution-design -> odoo-coding.",
        id="chain-arrow-ascii",
    ),
    pytest.param(
        "Chain: odoo-planning → odoo-solution-design → odoo-coding",
        id="chain-arrow-unicode",
    ),
    pytest.param(
        "  [design-fleet] [repo: fleet-addons] [skill: odoo-solution-design]\n"
        "      depends-on: billing-core",
        id="block2-node-box",
    ),
    pytest.param(
        '"nodes": [{"id": "design", "repo": "fleet-addons", "approach": "odoo-solution-design",'
        ' "approach_kind": "skill", "depends_on": ["billing-core"]}]',
        id="serialized-node-approach",
    ),
    pytest.param(
        "design-migration -> odoo-solution-architect (effort L, est_agents 1) -> the design skill",
        id="block3-assignment-line",
    ),
    pytest.param(
        "    +--> (2)  design      [skill: odoo-solution-design]   author the TDD for the tail",
        id="added-terminal-stage",
    ),
    pytest.param(
        "After the plan is approved, run odoo-solution-design for any node whose approach is open.",
        id="prose-after-the-plan",
    ),
    pytest.param(
        "`odoo-solution-design` runs after `odoo-planning`, so the design reflects the build order.",
        id="prose-design-downstream-of-planning",
    ),
    pytest.param(
        "A review node may emit a design suggestion; materialize it as an odoo-solution-design node.",
        id="driver-materializes-design",
    ),
    pytest.param(
        "odoo-planner emits next: odoo-solution-design once the plan gate closes ==> design.",
        id="planner-emits-design-followup",
    ),
]


@pytest.mark.parametrize("sample", MUST_CATCH)
def test_detector_catches_every_shape_the_inversion_can_take(sample):
    assert find_inversions(sample), (
        f"the inversion detector must catch {sample!r} - a guard that matches one phrasing goes "
        f"green while every synonym slips through"
    )


MUST_NOT_CATCH = [
    pytest.param(
        "`odoo-gap-analysis` → `odoo-solution-design` → `odoo-planning` → `odoo-coding`",
        id="compliant-chain",
    ),
    pytest.param(
        "**Design-then-planning ordering.** `odoo-planning` is DOWNSTREAM of `odoo-solution-design`: "
        "when a change is design-required it runs AFTER design and CONSUMES the approved output.",
        id="ordering-ssot-statement",
    ),
    pytest.param(
        "if design_required and not design_present: REFUSE - author no plan, dispatch no planner, "
        "and hand back with next: odoo-solution-design naming what made the change design-required.",
        id="the-refusal-branch",
    ),
    pytest.param(
        "When P2b routes a module out to design, `next: odoo-solution-design` with the Continuation "
        "Contract payload - the upgrade orchestrator owns its own plan, it is not a plan node.",
        id="peer-front-door-route-out",
    ),
    pytest.param(
        "on_complete:\n  - when: \"needs_design == true\"\n    next: odoo-solution-design\n"
        "    reason: the upgrade risk report contains items with more than one viable approach",
        id="plan-upgrade-workflow-on-complete",
    ),
    pytest.param(
        "No node's `approach` may be `odoo-solution-design`, and no node may be wired to the "
        "`odoo-solution-architect` agent, including a node materialized at runtime from a `next[]`.",
        id="the-schema-ban-itself",
    ),
    pytest.param(
        "A `next[]` suggestion naming odoo-solution-design is NEVER materialized, at ANY confidence; "
        "record it as a finding naming odoo-planning as the owner who must amend the plan.",
        id="the-driver-refusal-itself",
    ),
    pytest.param(
        "route to `odoo-solution-design` FIRST (design precedes planning) - do not plan an "
        "ungrounded build order.",
        id="design-first-instruction",
    ),
    pytest.param(
        "| `odoo-planning` | Turn an APPROVED design into the EXECUTION plan. Runs after "
        "`odoo-solution-design`, before `odoo-coding`. |",
        id="inventory-row-correct-direction",
    ),
]


@pytest.mark.parametrize("sample", MUST_NOT_CATCH)
def test_detector_leaves_compliant_and_prohibiting_prose_alone(sample):
    hits = find_inversions(sample)
    assert not hits, (
        f"the inversion detector must NOT catch {sample!r} (matched {hits!r}) - a guard that fires "
        f"on the correct direction, or on the ban's own wording, cannot be kept green honestly"
    )
