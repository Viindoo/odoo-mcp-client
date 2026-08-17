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

## Why prose alone was not enough

`snippets/planning-gate-contract.md` § Design-then-planning ordering has always STATED the rule
("`odoo-planning` is DOWNSTREAM of `odoo-solution-design`"), but nothing evaluated it:

* `odoo-planning`'s Input port told itself to "route to `odoo-solution-design` FIRST" while its own
  § Continuation Contract enumerated exactly two `next` values, neither of them design - so the
  route-back was unreachable prose, and § No scope-preview gate listed "a missing design artifact"
  as a question to ask before dispatching both planners anyway.
* `skills/odoo-intake/references/plan-mode-schema.md` declared its `approach_kind` values and node
  fields EXHAUSTIVE but never said a node's `approach` may not be `odoo-solution-design`, so a
  `design depends_on <coding node>` shape was schema-legal.
* `skills/run-harness/` contained ZERO occurrences of the word "design", while its `next[]` ->
  `materialize()` step turns any suggestion at `confidence >= 0.5` into a live node.

So this file asserts the ENFORCEMENT POINTS exist and terminate correctly, plus a tree-wide
inversion detector. It deliberately does not assert any single sentence: every check either parses a
section's structure or runs a multi-shape detector, so compliant prose may be rewritten freely.
"""
from __future__ import annotations

import re
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
# Enforcement point 1 - odoo-planning REFUSES rather than planning ahead of a
# design it needs, and the refusal is expressible in its own contract.
# ---------------------------------------------------------------------------


def test_a_design_required_change_with_no_design_never_gets_a_plan():
    """The refusal is a PREDICATE evaluated before either planner runs, not a caution.

    Behaviour protected: planning cannot author an ungrounded plan for a design-required change.
    Fails if the predicate loses its two inputs, its refusal effect, or its position before dispatch.
    """
    text = _read(PLANNING)
    section = _section(text, r"(?m)^## Design precedes planning.*$")
    flat = _flat(section)

    assert re.search(r"(?i)design_required", flat) and re.search(r"(?i)design_present", flat), (
        "§ Design precedes planning must name BOTH inputs of the refusal predicate "
        "(is design required? is a design artifact present?) - a rule with no decidable inputs is "
        "advice, and advice does not stop a dispatch."
    )
    # The DECISION LINE is the load-bearing part: both inputs bound to the REFUSE outcome, in one
    # evaluable statement. A section that merely mentions `design_required` somewhere and `REFUSE`
    # somewhere else has no branch the skill can take.
    decision = re.search(
        r"(?im)^\s*if\s+design_required\s+and\s+not\s+design_present\s*:[^\n]*REFUSE", section
    )
    assert decision, (
        "§ Design precedes planning must carry the decision line binding BOTH inputs to the REFUSE "
        "outcome, e.g. `if design_required and not design_present:  REFUSE - ...`. Naming the "
        "inputs in one place and the outcome in another leaves no branch to take, which is how a "
        "refusal degrades into a note in the plan header."
    )
    assert re.search(r"(?i)REFUSE", flat), (
        "§ Design precedes planning must state the REFUSE outcome; 'prefer design first' is not an "
        "outcome the skill can act on."
    )
    # The refusal must actually withhold the artifact, not merely warn.
    assert re.search(r"(?i)(author no plan|no plan file|write NO plan|dispatch (?:NEITHER|no) planner)", flat), (
        "The REFUSE branch must withhold the plan itself (no plan authored, no planner dispatched) - "
        "a refusal that still produces a plan leaves design's only remaining slot AFTER the plan."
    )
    # Position: the refusal precedes the planner dispatch, so it can still change the outcome.
    refuse_at = text.index("## Design precedes planning")
    dispatch_at = text.index("## Agent invocation")
    assert refuse_at < dispatch_at, (
        "§ Design precedes planning must sit BEFORE § Agent invocation - a check placed after the "
        "planners have run cannot prevent the plan it is meant to prevent."
    )


def test_the_route_back_to_design_is_reachable_from_plannings_own_contract():
    """A route-back nothing can emit is the repo's dominant defect: a rule never reached.

    Behaviour protected: the refusal terminates at `odoo-solution-design` through the Continuation
    Contract, carrying NO plan pointer (the absence is what marks it as a pre-plan hand-back).
    """
    section = _section(_read(PLANNING), r"(?m)^## Continuation Contract\s*$")
    flat = _flat(section)
    assert f"next: {DESIGN_SKILL}" in flat, (
        "odoo-planning's § Continuation Contract must enumerate a `next: odoo-solution-design` "
        "branch. Without it, § Design precedes planning can refuse but cannot hand back, and the "
        "only reachable repair moves design AFTER the plan."
    )
    assert re.search(r"produced:\s*\[\s*\]", flat), (
        "The design hand-back branch must emit `produced: []` - it must be observable that no plan "
        "artifact was created, otherwise a downstream reader treats it as a plan-plus-design-later."
    )


#: The ONLY two sections of `odoo-planning/SKILL.md` allowed to route to design: the pre-dispatch
#: refusal, and the Continuation-Contract branch that carries it out. Anywhere else - above all the
#: § Plan-approval gate, where "on approve, also design the open bits" is the most natural place to
#: reintroduce the inversion - a design hand-off necessarily happens with a plan already on disk.
_DESIGN_ROUTE_HOMES = ("## Design precedes planning", "## Continuation Contract")


def test_planning_routes_to_design_only_before_a_plan_exists():
    """Detector for the inversion INSIDE the one file where both directions are spelled the same.

    `next: odoo-solution-design` is legal ONLY where no plan artifact exists yet. The token cannot
    tell the two directions apart, so this locates every occurrence by its enclosing section and by
    its branch payload: a design hand-off from any section other than the refusal's two homes, or
    from a Continuation-Contract branch that also carries a `plan:` pointer, is the inversion.
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
    hits = list(route_rx.finditer(text))
    assert hits, (
        "odoo-planning/SKILL.md must route to design SOMEWHERE - with no hand-off at all the "
        "refusal cannot terminate and the plan gets authored anyway."
    )
    misplaced = [
        f"{owning_section(m.start())!r} -> {m.group(0)!r}"
        for m in hits
        if not owning_section(m.start()).startswith(_DESIGN_ROUTE_HOMES)
    ]
    assert not misplaced, (
        "odoo-planning routes to `odoo-solution-design` from a section that runs AFTER the plan "
        f"exists: {misplaced}. Allowed homes are {list(_DESIGN_ROUTE_HOMES)} (the pre-dispatch "
        "refusal). Anywhere else the plan is already authored, so the design would follow it."
    )

    gate = _flat(_section(text, r"(?m)^## Plan-approval gate.*$"))
    assert DESIGN_SKILL not in gate and DESIGN_AGENT not in gate, (
        "§ Plan-approval gate must not name the design skill/agent at all: every branch of that "
        "gate runs with the plan already written to disk, so any design it schedules is the "
        "inverted order."
    )

    section = _section(text, r"(?m)^## Continuation Contract\s*$")
    bullets = re.split(r"(?m)^- \*\*", section)[1:]
    assert len(bullets) >= 3, (
        f"§ Continuation Contract must enumerate its branches as a bullet list (found "
        f"{len(bullets)}) - an unenumerated blob cannot be checked branch by branch"
    )
    offenders = []
    for bullet in bullets:
        flat = _flat(bullet)
        if not route_rx.search(flat):
            continue
        if re.search(r"inputs:\s*\{[^}]*\bplan\s*:", flat):
            offenders.append(flat[:120])
    assert not offenders, (
        "These odoo-planning Continuation-Contract branches hand off to `odoo-solution-design` "
        f"WHILE carrying a plan pointer: {offenders}. A design named after a plan artifact exists "
        "is the inverted order, not a follow-up step."
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
