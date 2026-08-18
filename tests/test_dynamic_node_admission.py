"""Guards: what ADMITS a `next[]` suggestion into a live run, and what happens to the node that
emitted one the driver REFUSED.

Two undefined behaviours in the driver contract, both resolved in the FAIL-SAFE direction:

1. **An ABSENT `confidence` is `0.0`.** `skills/run-harness/SKILL.md` § The loop admitted a `next[]`
   suggestion on `nx.confidence >= <bar>`, and nothing anywhere said what an ABSENT (or `null`)
   `confidence` means. Real emitters ship un-scored hops - `agents/odoo-code-reviewer.md`
   § Continuation Contract emits `next: odoo-modules-upgrade` with no `confidence` field at all - so
   whether that hop silently became a live, auto-running node was undefined. Resolution: absent,
   `null`, or a non-numeric value resolves to `0.0`, which is below the bar, so the hop falls to
   `note_as_suggestion(nx)` and a human sees it. An emitter that omits the field has expressed NO
   confidence, and inserting an unrequested node into a plan a human approved is the failure this
   avoids.

2. **A refused design hop must not leave its EMITTER hanging.** The driver NEVER materializes a
   `next[]` suggestion naming `odoo-solution-design` (sibling guard: `test_design_precedes_planning.py`
   owns that ordering rule). But a skill can be YIELDING on exactly that hop:
   `skills/odoo-modules-upgrade/SKILL.md` § P2b routes a module out to design for its mandatory
   verdicts, emits the Continuation Contract, YIELDs, and expects `design_doc` back on re-entry. If
   the driver refuses the hop and carries on, that node never re-enters - it silently never finishes.
   Resolution, driver-side and in ONE place so every skill of that shape is covered: the yielding
   emitter goes `BLOCKED` with a `blocked_reason` naming the node, the refused hop, and `odoo-planning`
   as the owner who must amend the plan, while the rest of the run proceeds untouched.

## How these are asserted

Check 1 does NOT match the driver's expression as text. It EXTRACTS that expression from SKILL.md and
EVALUATES it against a probe matrix, so the assertion is on the BEHAVIOUR (materialize vs suggestion)
and the bar is read from the source instead of being spelled a second time here. A revert to the bare
`nx.confidence >= <bar>` fails on the absent/null probes, which stop being evaluable at all.

Check 2 is prose, so it uses multi-shape detectors with MUST-CATCH / MUST-NOT-CATCH corpora rather
than one grep: this repo's recurring defect is a guard that matches one phrasing and goes green while
every synonym slips through. Whitespace is normalised and markdown emphasis stripped before matching,
because line-wrapping and `**bold**` have produced false negatives here before.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

RUN_SKILL = PLUGIN / "skills" / "run-harness" / "SKILL.md"
RUN_REF = PLUGIN / "skills" / "run-harness" / "references" / "run-integration.md"
CONTRACT = PLUGIN / "snippets" / "continuation-contract.md"
REVIEWER = PLUGIN / "agents" / "odoo-code-reviewer.md"
UPGRADE = PLUGIN / "skills" / "odoo-modules-upgrade" / "SKILL.md"

_GENERATED = re.compile(
    r"<!-- BEGIN GENERATED TOOLS -->.*?<!-- END GENERATED TOOLS -->", re.DOTALL
)
_TEXT_EXTS = {".md", ".yaml", ".yml", ".json"}


def _read(path: Path) -> str:
    assert path.is_file(), f"{path} is missing - the rule it carries has no owner left"
    return _GENERATED.sub("", path.read_text(encoding="utf-8"))


def _flat(text: str) -> str:
    """Collapse whitespace AND strip markdown emphasis, so a wrapped, bolded sentence matches."""
    return re.sub(r"\s+", " ", text.replace("**", "").replace("__", ""))


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


# ===========================================================================
# Part 1 - the `next[]` admission test, EVALUATED (never re-implemented)
# ===========================================================================

#: The driver's own admission line inside § The loop. Captured, not restated: the bar, the dedup
#: term and the budget term all stay SSOT in SKILL.md.
_ADMISSION_LINE = re.compile(
    r"(?m)^[ \t]*if[ \t]+(?P<cond>[^\n]*?\bconfidence\b[^\n]*?)[ \t]*:[ \t]*(?:#[^\n]*)?$"
)

MATERIALIZE = "materialize -> a live node runs without the human ever seeing it"
SUGGESTION = "note_as_suggestion -> a human sees it; nothing auto-runs"


def admission_condition() -> str:
    """The single `if ... confidence ...:` line the driver admits a `next[]` entry on."""
    hits = [m.group("cond") for m in _ADMISSION_LINE.finditer(RUN_SKILL.read_text(encoding="utf-8"))]
    assert len(hits) == 1, (
        f"expected exactly ONE `if ... confidence ...:` admission line in {RUN_SKILL.name} § The "
        f"loop, found {len(hits)}: {hits!r}. Two of them means two places decide whether a "
        f"suggestion auto-runs, and this guard can only bind one."
    )
    return hits[0]


def admission_bar() -> float:
    """The threshold, READ from the driver line - never spelled a second time in this file."""
    cond = admission_condition()
    m = re.search(r">=\s*([0-9]*\.?[0-9]+)", cond)
    assert m, (
        f"the admission line {cond!r} no longer compares `confidence` against a numeric bar with "
        f">=, so the probe matrix below cannot be derived from the source. Keep the bar in the "
        f"driver line (SSOT) rather than moving it into prose."
    )
    return float(m.group(1))


def outcome(confidence) -> str:
    """Run the DRIVER'S OWN expression for one `confidence` value and report what it does.

    `nx` models one parsed `next[]` entry. `duplicate`/`within_budget` are neutralised so this
    isolates the `confidence` term - the dedup and budget circuit-breakers have their own guards.

    `eval` is deliberate and is what makes this guard a behaviour test rather than a text match: the
    expression is the driver's OWN line, so no re-implementation can drift from it. The input is not
    untrusted - it is one line of a version-controlled file in this repo, extracted by
    `admission_condition()` (which pins it to a single `if ... confidence ...:` line), evaluated in
    a test process with `__builtins__` stripped and only these three names bound.
    """
    env = {
        "nx": SimpleNamespace(confidence=confidence),
        "duplicate": lambda _entry: False,
        "within_budget": True,
    }
    return MATERIALIZE if eval(admission_condition(), {"__builtins__": {}}, env) else SUGGESTION


def _outcome_or_error(confidence) -> tuple[str | None, str | None]:
    try:
        return outcome(confidence), None
    except Exception as exc:  # noqa: BLE001 - the failure text is the point
        return None, f"{type(exc).__name__}: {exc}"


_BAR = admission_bar()

#: Every shape a `confidence` field arrives in. `None` models the field the emitter OMITTED (an
#: absent key parses to null); `""` models `confidence:` present with nothing after it. Both are
#: "the emitter expressed no confidence", and both must be DECIDABLE, not undefined.
PROBES: tuple[tuple[str, object, str], ...] = (
    ("absent - the emitter omitted the field entirely", None, SUGGESTION),
    ("null - the key is there with no value", "", SUGGESTION),
    ("zero", 0, SUGGESTION),
    ("zero as a float", 0.0, SUGGESTION),
    ("just below the bar", round(_BAR - 0.01, 6), SUGGESTION),
    ("exactly the bar", _BAR, MATERIALIZE),
    ("full confidence", 1, MATERIALIZE),
    ("out of range, above the bar (nothing clamps it)", round(_BAR + 1.2, 6), MATERIALIZE),
    ("out of range, below zero", -0.2, SUGGESTION),
)


@pytest.mark.parametrize(
    "label,value,expected",
    PROBES,
    ids=[re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") for label, _, _ in PROBES],
)
def test_the_driver_resolves_every_confidence_shape_and_never_auto_runs_an_unscored_hop(
    label, value, expected
):
    """Behaviour protected: an emitter that scored nothing gets a suggestion, not a live node.

    Fails if the admission line stops being decidable for an un-scored hop (the pre-fix
    `nx.confidence >= <bar>` cannot even be evaluated for it), or if it flips any probe's outcome.
    """
    got, err = _outcome_or_error(value)
    assert err is None, (
        f"the driver's own admission line `{admission_condition()}` cannot be EVALUATED for "
        f"{label} ({value!r}) - it raised {err}. Undefined behaviour IS the defect: an emitter that "
        f"omits `confidence` (e.g. {REVIEWER.name} emitting `next: odoo-modules-upgrade`) must land "
        f"on a defined branch. Resolve absent/null to 0.0 (e.g. `(nx.confidence or 0) >= ...`)."
    )
    assert got == expected, (
        f"{label} ({value!r}) resolves to {got!r}, expected {expected!r} under the driver line "
        f"`{admission_condition()}`. An un-scored or below-bar hop must reach the human as a "
        f"suggestion; only a value AT or above the bar may materialize a node the plan never named."
    )


def test_a_non_numeric_confidence_never_auto_materializes():
    """A value that is not a number is not a confidence - the one wrong answer is auto-running it.

    Weaker than the probes above by design: an unevaluable comparison still means nothing ran. The
    absent/null probes are what keep the RED, so this cannot be the guard's only teeth.
    """
    got, err = _outcome_or_error("high")
    assert got != MATERIALIZE, (
        f"a non-numeric `confidence` ('high') resolves to {got!r} under `{admission_condition()}` - "
        f"a malformed value must never admit a node into a human-approved plan (run-integration.md "
        f"§ confidence resolution resolves it to 0.0, like the absent case)."
        + (f" [evaluation error: {err}]" if err else "")
    )


#: Every agent/skill file in this plugin capable of owning a Continuation Contract `next:` hop -
#: the same class of file REVIEWER belongs to. Deliberately NOT `_tree_texts()`'s whole corpus:
#: that sweep also covers workflow YAML (a `next:` step-transition key in a DIFFERENT schema, not
#: a confidence-scored suggestion) and docs, which would make a witness there prove nothing about
#: the driver's admission rule.
_EMITTER_FILES: tuple[Path, ...] = tuple(
    sorted((PLUGIN / "agents").glob("*.md")) + sorted((PLUGIN / "skills").glob("*/SKILL.md"))
)


def _unscored_next_hops(path: Path) -> list[str]:
    """Every `next: <hop>` emitted by `path` with no `confidence:` value in the same breath.

    Same per-hop check the old REVIEWER-only floor used, generalised to any emitter file.
    """
    flat = _flat(_read(path))
    hops = re.findall(r"next:\s*`?([a-z0-9-]+)", flat)
    return [
        h for h in hops
        if not re.search(rf"next:\s*`?{re.escape(h)}\b[^.]{{0,400}}?confidence:\s*[0-9]", flat)
    ]


def test_the_unscored_emitter_this_rule_exists_for_still_exists():
    """Discovery floor: the rule is pointless if no LIVE emitter actually omits `confidence`.

    `odoo-code-reviewer` stopped being this floor's witness on purpose: the owner scored all five
    of its `next:` hops - `odoo-coding` at 0.8 (a proven CRITICAL/HIGH finding chains straight into
    the fix), `odoo-test-writing` at 0.4, `odoo-modules-upgrade` deliberately held at 0.3 (P2b's
    mandatory design route-out would leave an auto-run node BLOCKED), plus the pre-existing
    `odoo-debug`/`odoo-ui-review` at 0.4. That is progress on ONE file, not proof the rule is
    pointless - the resolution this file protects is a TREE-WIDE contract
    (`test_no_file_treats_an_unscored_confidence_as_permission_to_auto_run` already sweeps every
    prose/config file for the INVERTED defect), so this floor is re-grounded on every agent/skill
    Continuation Contract emitter in the plugin instead of pinned to the one file that just
    finished scoring its own hops - otherwise the next author to fully score THAT witness would
    silently retire this guard the same way, again.

    Fails only if EVERY file in `_EMITTER_FILES` scores EVERY `next:` hop it emits - at which point
    the rule is still correct (a future emitter will eventually omit it again) but has no live
    witness left; the honest move then is to rewrite this floor to say so explicitly and fall back
    to the SYNTHETIC `PROBES` matrix above (in particular its "absent" and "null" rows) as the sole
    remaining guarantee that the absent-confidence path stays exercised - not to keep asserting a
    live witness that no longer exists.
    """
    witnesses = {
        str(path.relative_to(ROOT)): hops
        for path in _EMITTER_FILES
        if (hops := _unscored_next_hops(path))
    }
    assert witnesses, (
        f"scanned {len(_EMITTER_FILES)} agent/skill files under {PLUGIN.relative_to(ROOT)} and every "
        f"one now scores every `next:` hop it emits - the absent-`confidence` resolution this file "
        f"protects has no live witness left anywhere in the plugin. The rule is still correct, but "
        f"this floor is now FALSE ADVERTISING and MUST be rewritten: state plainly that the "
        f"SYNTHETIC `PROBES` matrix above (the 'absent' and 'null' rows) is the ONLY thing left "
        f"exercising the absent-confidence path, since no real emitter does - do not leave this "
        f"assertion claiming a live witness that is gone."
    )


# ---------------------------------------------------------------------------
# The owner's DECISION on REVIEWER's three newly-scored hops: not just that each carries a
# digit, but that the fix hop clears the bar and the peer-front-door hop stays under it.
# ---------------------------------------------------------------------------


def _hop_confidence(path: Path, hop: str) -> float:
    """The first explicit `confidence:` value `path` attaches to `next: <hop>`.

    Mirrors `_unscored_next_hops`'s attachment window (`[^.]{0,400}?`) so both functions agree on
    what "scored" means - a hop is scored here in exactly the sense that keeps it out of that
    function's result.
    """
    flat = _flat(_read(path))
    m = re.search(
        rf"next:\s*`?{re.escape(hop)}\b[^.]{{0,400}}?confidence:\s*([0-9]*\.?[0-9]+)", flat
    )
    assert m, (
        f"{path.name} no longer attaches an explicit `confidence:` to `next: {hop}` within 400 "
        f"chars - either the hop was dropped or it regressed to unscored"
    )
    return float(m.group(1))


def test_reviewer_scores_the_fix_hop_at_or_above_the_bar_and_the_upgrade_hop_below_it():
    """The DECISION, not the digits alone: a proven fix chains straight in; a peer front door with
    a known stall never does.

    `next: odoo-coding` (emitted only when a CRITICAL/HIGH finding exists) must clear the driver's
    OWN admission bar (`admission_bar()`, read from `skills/run-harness/SKILL.md` - never
    hardcoded a second time here) so the fix runs under `--auto` with no human round-trip.
    `next: odoo-test-writing` and `next: odoo-modules-upgrade` must both stay BELOW that same bar:
    the missing-test hop is valuable but not urgent, and the upgrade hop is a PEER FRONT DOOR whose
    P2b mandatorily YIELDs out to `odoo-solution-design` - a hop the driver never materializes - so
    an auto-run upgrade node would immediately stall BLOCKED instead of finishing.

    Fails if a future edit pushes the fix hop back under the bar (silently re-demoting a proven
    defect to a suggestion) or pushes either advisory hop up to or past it (auto-running a hop that
    either just isn't urgent, or walks straight into the known P2b stall).
    """
    bar = admission_bar()
    coding = _hop_confidence(REVIEWER, "odoo-coding")
    test_writing = _hop_confidence(REVIEWER, "odoo-test-writing")
    upgrade = _hop_confidence(REVIEWER, "odoo-modules-upgrade")

    assert coding >= bar, (
        f"{REVIEWER.name} scores `next: odoo-coding` at {coding}, BELOW the driver's admission bar "
        f"{bar} - a proven CRITICAL/HIGH finding would surface as a mere suggestion instead of "
        f"chaining straight into the fix under `--auto`."
    )
    assert test_writing < bar, (
        f"{REVIEWER.name} scores `next: odoo-test-writing` at {test_writing}, AT OR ABOVE the "
        f"driver's admission bar {bar} - the missing-protecting-test hop is valuable but not "
        f"urgent and must stay a human-reviewed suggestion, not an auto-run node."
    )
    assert upgrade < bar, (
        f"{REVIEWER.name} scores `next: odoo-modules-upgrade` at {upgrade}, AT OR ABOVE the "
        f"driver's admission bar {bar} - this would auto-materialize a node that immediately "
        f"stalls BLOCKED, because odoo-modules-upgrade's P2b mandatorily YIELDs out to "
        f"odoo-solution-design and the driver never materializes a `next[]` hop naming the design "
        f"skill. Never raise this past the bar."
    )


def names_the_upgrade_stall(text: str) -> bool:
    """True iff `text` names the CONCRETE reason `odoo-modules-upgrade` stays below the bar: P2b's
    mandatory design route-out, the YIELD waiting on a design artifact, and the BLOCKED outcome an
    auto-run node would hit - not merely the generic '<0.5 is advisory' rule every other hop also
    cites. Window-scanned like the file's other multi-shape detectors, so wording/order may drift.
    """
    flat = _flat(text)
    for m in re.finditer(r"(?i)odoo-modules-upgrade", flat):
        window = flat[max(0, m.start() - 100): m.end() + 700]
        if (
            re.search(r"(?i)\bP2b\b", window)
            and re.search(r"(?i)YIELD", window)
            and re.search(r"(?i)BLOCKED", window)
        ):
            return True
    return False


def test_reviewer_names_the_upgrade_stall_not_just_the_rule():
    """The 0.3 score must carry ITS OWN reason inline, not merely cite '<0.5 is advisory' -
    otherwise a future author sees a low, unexplained number and 'helpfully' raises it.

    Behaviour protected: the clause attached to `next: odoo-modules-upgrade` names the CONCRETE
    stall (P2b's mandatory design route-out, the YIELD waiting on `design_doc`, and the BLOCKED
    outcome an auto-run node would hit) rather than only restating the generic admission-bar rule
    that every other advisory hop also cites.
    """
    # REVIEWER mentions `next: odoo-modules-upgrade` TWICE - once in Step 3.6 (deciding WHETHER to
    # defer) and once in the Continuation Contract (the actual scored emission this test targets) -
    # anchor on the Continuation Contract section so a stray Step 3.6 rewrite cannot mask a real
    # regression here (and cannot fake a pass either, since Step 3.6 never mentions `confidence`).
    section = _section(_read(REVIEWER), r"(?m)^## Continuation Contract.*$")
    assert names_the_upgrade_stall(section), (
        f"{REVIEWER.name}'s Continuation Contract clause for `next: odoo-modules-upgrade` must "
        f"name the CONCRETE stall - P2b's mandatory design route-out, the YIELD waiting on "
        f"`design_doc`, and the BLOCKED outcome an auto-run node would hit - not just assert the "
        f"hop is advisory. Without it, a later author sees an unexplained low score and 'helpfully' "
        f"raises it past the bar."
    )


UPGRADE_STALL_MUST_CATCH = [
    pytest.param(
        "next: odoo-modules-upgrade, confidence: 0.3 - P2b mandatorily YIELDs out to design; a "
        "materialized node would go BLOCKED waiting on design_doc.",
        id="inline-clause",
    ),
    pytest.param(
        "Keep odoo-modules-upgrade below the bar: its P2b route-out YIELDs for a design_doc the "
        "driver never supplies, so an auto-run node ends up BLOCKED.",
        id="keep-below-the-bar-phrasing",
    ),
    pytest.param(
        "Why 0.3 and not higher for odoo-modules-upgrade - because P2b forces a YIELD on the "
        "design hop, and the driver's refusal to materialize that hop would leave the node "
        "BLOCKED forever.",
        id="why-phrasing",
    ),
]


UPGRADE_STALL_MUST_NOT_CATCH = [
    pytest.param(
        "next: odoo-modules-upgrade, confidence: 0.3 (advisory, not a blocker)",
        id="bare-advisory-no-reason",
    ),
    pytest.param(
        "next: odoo-modules-upgrade, confidence: 0.3 - keep this below the admission bar",
        id="restates-the-generic-rule-only",
    ),
    pytest.param(
        "also emit `next: odoo-debug`, confidence: 0.4 (advisory, not a blocker) or `next: "
        "odoo-ui-review`, confidence: 0.4",
        id="unrelated-scored-hop",
    ),
]


@pytest.mark.parametrize("sample", UPGRADE_STALL_MUST_CATCH)
def test_the_upgrade_stall_detector_accepts_every_compliant_phrasing(sample):
    assert names_the_upgrade_stall(sample), (
        f"the detector must recognise {sample!r} as naming the stall - a detector bound to one "
        f"phrasing turns a correct rewrite red"
    )


@pytest.mark.parametrize("sample", UPGRADE_STALL_MUST_NOT_CATCH)
def test_the_upgrade_stall_detector_rejects_bare_advisory_language(sample):
    assert not names_the_upgrade_stall(sample), (
        f"the detector must NOT accept {sample!r} - it restates only the generic advisory rule "
        f"(or scores an unrelated hop) with no concrete stall named, which is exactly the "
        f"regression this guard exists to catch"
    )


# ---------------------------------------------------------------------------
# The rule must also be WRITTEN DOWN where the driver reads it, in a form that
# survives a rewrite. Multi-shape detector, not one grep.
# ---------------------------------------------------------------------------

_ABSENT = (
    r"(?:absent|omit\w*|missing|unscored|un-scored|with no|no(?:\s+\w+){0,2}\s+value"
    r"|not (?:present|set|given|scored))"
)
_ZERO = r"(?:0\.0|(?<![.\d])0(?![.\d])|zero)"
_SUGGEST = (
    r"(?:note_as_suggestion|as a suggestion|surfac\w+|never (?:auto-?)?materiali\w*|"
    r"not auto-?materiali\w*|does not auto-?run|never auto-?run|falls? to [^.]{0,40}suggestion)"
)


def states_absent_confidence_is_zero(text: str) -> bool:
    """True iff `text` states, in ANY phrasing, that an absent `confidence` resolves to 0.0 and
    therefore surfaces as a suggestion. Window-based so wording, order and emphasis may change."""
    flat = _flat(text)
    for m in re.finditer(r"(?i)\bconfidence\b", flat):
        window = flat[max(0, m.start() - 240): m.end() + 420]
        if (
            re.search(rf"(?i){_ABSENT}", window)
            and re.search(rf"(?i){_ZERO}", window)
            and re.search(rf"(?i){_SUGGEST}", window)
        ):
            return True
    return False


def test_the_reference_states_the_absent_confidence_resolution_and_its_reason():
    """The driver reads prose, not just pseudocode: the six-byte expression needs its rule stated.

    Behaviour protected: a reader of the driver contract can tell what an omitted `confidence`
    means, and why the fail-safe direction was chosen. Fails if the paragraph is dropped or
    reduced to a bare expression with no stated semantics.
    """
    section = _section(_read(RUN_REF), r"(?m)^## Gate-tier node classes.*$")
    assert states_absent_confidence_is_zero(section), (
        "run-integration.md § Gate-tier node classes must state the `confidence` resolution: an "
        "ABSENT or null value resolves to 0.0 and therefore surfaces as a suggestion, never "
        "auto-materializes. Without it, `(nx.confidence or 0)` in SKILL.md is an unexplained "
        "idiom the next trim 'simplifies' back into the undefined behaviour."
    )
    flat = _flat(section)
    assert re.search(r"(?i)expressed (?:NO|no) confidence|is not a default|has expressed", flat), (
        "the paragraph must say WHY absence is 0.0 - an emitter that omits the field has expressed "
        "no confidence, so an omitted value is not a default. A reasonless rule does not survive."
    )
    assert re.search(r"(?i)(?:human|plan-mode|plan) (?:never )?approved|human never approved", flat), (
        "the paragraph must name the failure avoided - inserting an unrequested node into a "
        "human-approved plan - or the rule reads as pedantry and gets inverted for convenience."
    )
    assert "note_as_suggestion" in flat, (
        "the paragraph must name the branch the hop actually takes (`note_as_suggestion`) so the "
        "stated rule and the driver loop are the SAME mechanism, not two descriptions."
    )


ABSENT_RULE_MUST_CATCH = [
    pytest.param(
        "An absent `confidence` resolves to 0.0, so the hop is surfaced as a suggestion.",
        id="absent-resolves-to-zero",
    ),
    pytest.param(
        "When the field is omitted the driver reads the confidence as zero and never "
        "auto-materializes the hop.",
        id="omitted-reads-as-zero",
    ),
    pytest.param(
        "`confidence` missing -> 0.0 -> `note_as_suggestion(nx)`; nothing enters the run.",
        id="arrow-chain",
    ),
    pytest.param(
        "A `next[]` entry with no `confidence` value counts as 0.0 confidence and does not auto-run; "
        "a human sees it as a suggestion.",
        id="no-value-counts-as-zero",
    ),
    pytest.param(
        "Un-scored hops (no `confidence` field at all) are read as zero and only ever surfaced.",
        id="unscored-read-as-zero",
    ),
]


@pytest.mark.parametrize("sample", ABSENT_RULE_MUST_CATCH)
def test_the_absent_rule_detector_accepts_every_compliant_phrasing(sample):
    assert states_absent_confidence_is_zero(sample), (
        f"the detector must recognise {sample!r} as stating the rule - a detector that only accepts "
        f"one phrasing turns every correct rewrite into a false red"
    )


ABSENT_RULE_MUST_NOT_CATCH = [
    pytest.param(
        "confidence: 0.0..1.0                     # driver arbitration",
        id="bare-schema-line",
    ),
    pytest.param(
        "`confidence` is the advisory-vs-auto-run lever the contract gives an emitter.",
        id="lever-sentence-only",
    ),
    pytest.param(
        "An absent `confidence` is treated as 1.0 - assume the emitter would have scored it lower.",
        id="the-inverted-rule",
    ),
    pytest.param(
        "The low-confidence branch surfaces the suggestion instead of running it.",
        id="low-confidence-only-no-absent-case",
    ),
]


@pytest.mark.parametrize("sample", ABSENT_RULE_MUST_NOT_CATCH)
def test_the_absent_rule_detector_is_not_satisfied_by_adjacent_prose(sample):
    assert not states_absent_confidence_is_zero(sample), (
        f"the detector must NOT accept {sample!r} - a schema line, the lever sentence, or the "
        f"INVERTED rule would otherwise let the real rule be deleted while this guard stays green"
    )


# ---------------------------------------------------------------------------
# Tree-wide inverse sweep: nowhere may an absent `confidence` mean "confident".
# ---------------------------------------------------------------------------

#: A window carrying one of these is stating the FAIL-SAFE rule (or quoting the defect in order to
#: ban it), not asserting the defect.
_FAILSAFE_MARKER = re.compile(
    r"(?i)\b0\.0\b|\bzero\b|never auto|not auto-?run|not auto-?materiali|is not a default|"
    r"note_as_suggestion|below the bar|must not|never a default"
)

CONFIDENT_BY_DEFAULT_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("absent-treated-as-confident",
     re.compile(r"(?i)\b(?:absent|omitted|missing|no)\b[^.]{0,40}\bconfidence\b[^.]{0,70}"
                r"(?:default\w*|treat\w*|read\w*|assum\w*|count\w*)[^.]{0,30}"
                r"(?:1(?:\.0)?\b|high|confident|above)")),
    # Same claim with the words in the other order - "`confidence` omitted -> assume confident".
    # The confident-side alternatives are AFFIRMATIVE on purpose: a bare `default` would also match
    # the ban's own wording ("an omitted value is not a default"), which must never self-report.
    ("confidence-omitted-then-assumed-confident",
     re.compile(r"(?i)\bconfidence\b[^.]{0,40}\b(?:absent|omitted|missing|unscored)\b[^.]{0,80}"
                r"(?:assum\w+ (?:it |the emitter )?(?:is )?confident|treated? as (?:high|confident|1)"
                r"|defaults? to|reads? as (?:high|confident|1)|auto-?run\w*|auto-?materiali\w*"
                r"|materiali\w+ (?:it|the hop|anyway))")),
    ("confidence-defaults-high",
     re.compile(r"(?i)\bconfidence\b[^.]{0,50}defaults?\s+to\s+`?(?:0?\.[5-9]\d*|1(?:\.0)?|high)")),
    ("absent-auto-materializes",
     re.compile(r"(?i)\b(?:absent|omitted|missing|without a|no)\b[^.]{0,40}\bconfidence\b"
                r"[^.]{0,80}(?:auto-?materiali\w*|auto-?run\w*|materiali\w+ (?:it|the)|"
                r"enters? the run)")),
    ("presence-optional-so-admit",
     re.compile(r"(?i)\bconfidence\b[^.]{0,40}\b(?:optional|may be omitted)\b[^.]{0,80}"
                r"(?:still|anyway)[^.]{0,40}(?:materiali\w+|auto-?run\w*|admitted)")),
)


def find_confident_by_default(text: str) -> list[tuple[str, str]]:
    """Every (shape, hit) asserting that an unscored `confidence` may auto-run."""
    out: list[tuple[str, str]] = []
    flat = _flat(text)
    for name, rx in CONFIDENT_BY_DEFAULT_SHAPES:
        for m in rx.finditer(flat):
            # TIGHT window on purpose. A wide one exempted a contradiction written NEXT TO the
            # correct rule (a defect this repo has shipped before), so the marker must sit in or
            # right beside the hit itself.
            window = flat[max(0, m.start() - 60): m.end() + 60]
            if _FAILSAFE_MARKER.search(window):
                continue
            out.append((name, m.group(0)))
    return out


def test_the_inverse_sweep_has_a_corpus():
    """Discovery floor - a sweep over nothing is green for the wrong reason."""
    paths = [p for p, _ in _tree_texts()]
    assert len(paths) >= 200, f"expected a substantial prose corpus, found {len(paths)} files"
    mentions = sum(1 for _, t in _tree_texts() if "confidence" in t)
    assert mentions >= 5, f"only {mentions} files mention `confidence` - the sweep has nothing to judge"


def test_no_file_treats_an_unscored_confidence_as_permission_to_auto_run():
    """Whole-tree sweep, both plugins, every prose/config extension.

    A future skill/agent/workflow that re-declares the undefined behaviour is caught with zero
    edits here - the fix must not be a one-file patch that the next author silently contradicts.
    """
    offenders = []
    for path, text in _tree_texts():
        for shape, hit in find_confident_by_default(text):
            offenders.append(f"{path.relative_to(ROOT)} [{shape}] {hit[:120]!r}")
    assert not offenders, (
        "These sites let a `next[]` entry with no scored `confidence` auto-run:\n  "
        + "\n  ".join(offenders)
        + "\nAn emitter that omits the field has expressed no confidence; absent resolves to 0.0 "
          "and surfaces as a suggestion (run-integration.md § Gate-tier node classes)."
    )


CONFIDENT_BY_DEFAULT_MUST_CATCH = [
    pytest.param(
        "An absent `confidence` defaults to 1.0, so the hop materializes like any other.",
        id="defaults-to-one",
    ),
    pytest.param(
        "A `next[]` entry with no `confidence` is treated as high and enters the run.",
        id="no-confidence-treated-as-high",
    ),
    pytest.param(
        "When `confidence` is omitted, assume the emitter is confident and auto-run the hop.",
        id="omitted-assume-confident",
    ),
    pytest.param(
        "Missing `confidence`? The driver auto-materializes the suggestion anyway.",
        id="missing-auto-materializes",
    ),
    pytest.param(
        "`confidence` is optional on a next[] entry - an entry without it is still materialized.",
        id="optional-so-admitted",
    ),
]


@pytest.mark.parametrize("sample", CONFIDENT_BY_DEFAULT_MUST_CATCH)
def test_the_inverse_detector_catches_every_shape_of_the_defect(sample):
    assert find_confident_by_default(sample), (
        f"the inverse detector must catch {sample!r} - one phrasing caught and three missed is how "
        f"this defect keeps coming back"
    )


CONFIDENT_BY_DEFAULT_MUST_NOT_CATCH = [
    pytest.param(
        "An ABSENT `confidence` is 0.0, never a default of \"confident\": the hop takes the "
        "note_as_suggestion branch and a human sees it.",
        id="the-rule-itself",
    ),
    pytest.param(
        "confidence: 0.0..1.0   # <0.5 not auto-materialized, surfaced as a suggestion instead",
        id="schema-comment",
    ),
    pytest.param(
        "also emit `next: odoo-ui-review`, `confidence: 0.4` (advisory, not a blocker)",
        id="an-explicitly-scored-hop",
    ),
    pytest.param(
        "A high `confidence` entry materializes into a dynamic node, which the tier function "
        "returns L2 for, so the human still approves it.",
        id="high-confidence-materializes-correctly",
    ),
    pytest.param(
        "An emitter that omits `confidence` has expressed no confidence at all - resolve it to "
        "zero and record the hop as a suggestion.",
        id="the-reason-clause",
    ),
]


@pytest.mark.parametrize("sample", CONFIDENT_BY_DEFAULT_MUST_NOT_CATCH)
def test_the_inverse_detector_leaves_the_rule_and_scored_hops_alone(sample):
    hits = find_confident_by_default(sample)
    assert not hits, (
        f"the inverse detector must NOT catch {sample!r} (matched {hits!r}) - a sweep that fires on "
        f"the rule's own wording, or on a correctly scored hop, cannot be kept green honestly"
    )


# ===========================================================================
# Part 2 - a YIELDING emitter is BLOCKED, not left hanging
# ===========================================================================

_WAITING = r"(?:yield\w*|waiting on|waits on|was waiting|NEEDS_NEXT|re-?enter\w*|re-?entry)"
_REFUSED = r"(?:refus\w+|declin\w+|reject\w+|never materiali\w+|not materiali\w+)"
_NODE_SCOPE = r"(?:THAT node|that node|the emitting node|the node that emitted|only the node)"
_NODE_ID = r"(?:node id|node's id|node identifier|its id)"


def blocks_the_yielding_emitter(text: str) -> bool:
    """True iff `text` says a node YIELDING on a refused design hop is set BLOCKED, with a
    `blocked_reason` naming that node and `odoo-planning` as the owner.

    Anchored on the waiting/yielding condition and window-scanned, so the sentence order, the
    wording and the emphasis may all change without a false red.
    """
    flat = _flat(text)
    for m in re.finditer(rf"(?i){_WAITING}", flat):
        window = flat[max(0, m.start() - 700): m.end() + 900]
        if all(
            re.search(pattern, window, flags)
            for pattern, flags in (
                (_REFUSED, re.IGNORECASE),
                (r"\bBLOCKED\b", 0),
                (r"blocked_reason", 0),
                (_NODE_SCOPE, 0),
                (_NODE_ID, re.IGNORECASE),
                (r"odoo-planning", 0),
            )
        ):
            return True
    return False


def keeps_the_finding_only_path(text: str) -> bool:
    """True iff a refused hop from a node NOT waiting on it is still just a recorded finding, and
    the rest of the run keeps going."""
    flat = _flat(text)
    finding = re.search(
        r"(?i)(?:record|note)\w* (?:it|the (?:refused )?(?:hop|suggestion|entry)) as a finding"
        r"|stays a finding|remains a finding",
        flat,
    )
    carry_on = re.search(
        r"(?i)carry on with the remaining ready nodes|continue with the remaining"
        r"|the rest of the run (?:is untouched|proceeds|continues)",
        flat,
    )
    not_waiting = re.search(
        r"(?i)(?:NOT waiting|was not waiting|not yield\w*|another hop that did materiali\w+"
        r"|it returned `?DONE)",
        flat,
    )
    return bool(finding and carry_on and not_waiting)


#: Statuses are SSOT in the continuation contract - read them, never hardcode the enum here.
def contract_statuses() -> frozenset[str]:
    flat = _flat(_read(CONTRACT))
    m = re.search(r"status:\s*((?:[A-Z_]+\s*\|\s*)+[A-Z_]+)", flat)
    assert m, "continuation-contract.md must declare its `status:` enum on one line"
    values = frozenset(v.strip() for v in m.group(1).split("|"))
    assert len(values) >= 4, f"expected >=4 declared statuses, found {sorted(values)}"
    return values


#: Plausible inventions for "the node is waiting" - each would fork the status vocabulary.
INVENTED_VOCABULARY: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("a fifth status", re.compile(
        r"(?:status\s*[:=]\s*`?)?\b(?:WAITING|PARKED|STALLED|HANGING|SUSPENDED|AWAITING)\b")),
    ("a new waiting field", re.compile(
        r"(?m)`?(?:waiting_on|awaiting|parked_on|blocked_on|waiting_for)`?\s*:")),
    ("a re-invented reason field", re.compile(
        r"(?m)`?(?:block_reason|stall_reason|reason_blocked|hold_reason)`?\s*:")),
)


def find_invented_vocabulary(text: str) -> list[tuple[str, str]]:
    flat = _flat(text)
    return [(name, m.group(0)) for name, rx in INVENTED_VOCABULARY for m in rx.finditer(flat)]


def _design_refusal_section() -> str:
    return _section(_read(RUN_REF), r"(?m)^## Gate-tier node classes.*$")


def test_a_yielding_node_whose_design_hop_is_refused_is_blocked_not_left_parked():
    """Behaviour protected: the driver's refusal cannot silently end a node's run.

    Fails if the yielding-emitter rule is dropped back to 'record a finding and carry on', which
    leaves an `odoo-modules-upgrade`-shaped node parked on a re-entry that never arrives.
    """
    section = _design_refusal_section()
    assert blocks_the_yielding_emitter(section), (
        "run-integration.md § Gate-tier node classes must state that when the node which emitted a "
        "REFUSED design hop was itself YIELDING on that hop, THAT node is set BLOCKED with a "
        "`blocked_reason` naming the node id, the refused hop and `odoo-planning` as the owner who "
        "must amend the plan. 'Record a finding and carry on with the remaining ready nodes' alone "
        "leaves the emitter waiting for a re-entry that never comes - a silent stall, which is the "
        "exact failure class this contract exists to prevent (skills/odoo-modules-upgrade/SKILL.md "
        "§ P2b yields on that hop and expects `design_doc` back)."
    )


def test_the_rest_of_the_run_still_proceeds_and_a_non_waiting_emitter_stays_a_finding():
    """Anti-over-fix: only the waiting node stops.

    Fails if the escalation becomes unconditional (every refused design hop blocks something) or if
    the run-wide 'carry on with the remaining ready nodes' behaviour is lost.
    """
    section = _design_refusal_section()
    assert keeps_the_finding_only_path(section), (
        "the section must keep BOTH halves: a refused design hop is recorded as a finding and the "
        "driver carries on with the remaining ready nodes, and a refused hop from a node that was "
        "NOT waiting on it (it returned DONE, or NEEDS_NEXT with another hop that did materialize) "
        "stays a finding and nothing more. Escalating every refusal to BLOCKED stops runs that were "
        "never stalled."
    )


def test_the_yielding_rule_reuses_the_existing_status_vocabulary():
    """SSOT: `BLOCKED` + `blocked_reason` already exist - a new status or field forks the contract."""
    statuses = contract_statuses()
    assert "BLOCKED" in statuses, (
        f"`BLOCKED` must be one of the contract's declared statuses {sorted(statuses)} - the "
        f"yielding rule reuses it rather than inventing a state"
    )
    section = _design_refusal_section()
    invented = find_invented_vocabulary(section)
    assert not invented, (
        f"§ Gate-tier node classes introduces vocabulary the Continuation Contract does not "
        f"declare: {invented}. The yielding node is `BLOCKED` with `blocked_reason` (statuses are "
        f"SSOT in snippets/continuation-contract.md); a fifth status or a `waiting_on:` field means "
        f"every reader now has two vocabularies to reconcile."
    )


def test_the_reference_and_the_driver_loop_agree_on_the_needs_next_mapping():
    """The yielding rule REFINES SKILL.md's `NEEDS_NEXT -> DONE` mapping; both sides must survive.

    Fails if the driver loop's mapping loses the 'its next[] already materialized' qualifier - the
    unqualified version maps a yielding node with nothing materialized straight to DONE, which is
    the stall.
    """
    loop = _flat(RUN_SKILL.read_text(encoding="utf-8"))
    mapping = re.search(r"NEEDS_NEXT\s*->\s*DONE\s*\(([^)]*)\)", loop)
    assert mapping, (
        "SKILL.md § The loop must keep its `NEEDS_NEXT->DONE (...)` status mapping with its "
        "qualifier - run-integration.md's yielding rule cites it as the mapping that does NOT reach "
        "a node whose next[] materialized nothing."
    )
    assert re.search(r"(?i)materiali", mapping.group(1)), (
        f"the `NEEDS_NEXT->DONE` mapping's qualifier is now {mapping.group(1)!r} - it must still "
        f"condition the mapping on the node's `next[]` having been MATERIALIZED, otherwise a "
        f"yielding node whose only hop was refused maps to DONE and the run walks away from it."
    )
    section = _flat(_design_refusal_section())
    assert re.search(r"NEEDS_NEXT\s*->\s*DONE", section), (
        "the yielding rule must name the `NEEDS_NEXT -> DONE` mapping it overrides, so the two "
        "files read as ONE mechanism instead of two rules a driver has to reconcile at runtime."
    )


def test_the_yielding_shape_this_rule_covers_still_exists_upstream():
    """Discovery floor: the stall is real only while a skill actually yields on a design hop."""
    flat = _flat(_read(UPGRADE))
    assert re.search(r"(?i)Emit the Continuation Contract and YIELD", flat), (
        f"{UPGRADE.parent.name} no longer yields after its design route-out - re-ground this guard "
        f"on whichever skill now has that shape, or the driver rule has lost its witness"
    )
    assert re.search(r"(?i)design_doc", flat), (
        f"{UPGRADE.parent.name} must still expect the design artifact back on re-entry - that "
        f"expectation is what makes a refused hop a hang rather than a no-op"
    )


YIELD_RULE_MUST_CATCH = [
    pytest.param(
        "If the emitter YIELDED on the hop we refused, mark that node BLOCKED (never DONE) and put "
        "the node id, the refused hop and `odoo-planning` into its `blocked_reason`.",
        id="yielded-mark-that-node-blocked",
    ),
    pytest.param(
        "A node waiting on a design hop the driver declined cannot re-enter: set that node to "
        "BLOCKED, `blocked_reason` naming the node id, the declined hop, and `odoo-planning` as the "
        "owner who must amend the plan.",
        id="waiting-cannot-re-enter",
    ),
    pytest.param(
        "The emitter returned NEEDS_NEXT and its only hop was rejected, so it re-enters never: "
        "BLOCKED for the emitting node, with blocked_reason = node id + rejected hop + "
        "`odoo-planning`.",
        id="needs-next-only-hop-rejected",
    ),
    pytest.param(
        "Refused the hop a node was waiting on? THAT node is BLOCKED - its blocked_reason names its "
        "own node id, what was refused, and `odoo-planning` as the amender.",
        id="question-form",
    ),
]


@pytest.mark.parametrize("sample", YIELD_RULE_MUST_CATCH)
def test_the_yielding_detector_accepts_every_compliant_phrasing(sample):
    assert blocks_the_yielding_emitter(sample), (
        f"the detector must recognise {sample!r} - a detector bound to one phrasing turns a correct "
        f"rewrite red and, worse, misses a rewrite that quietly drops the rule"
    )


YIELD_RULE_MUST_NOT_CATCH = [
    pytest.param(
        "A `next[]` suggestion naming it: NEVER materialize it, at ANY `confidence`. Record it as a "
        "finding naming `odoo-planning` as the owner who must amend the plan, then carry on with "
        "the remaining ready nodes.",
        id="pre-fix-finding-only",
    ),
    pytest.param(
        "STATIC node (the plan named it): STOP the run BLOCKED with `blocked_reason` naming the "
        "node id and its `approach`, and route back to `odoo-planning` to amend the plan.",
        id="static-node-bullet-alone",
    ),
    pytest.param(
        "When a design hop is refused, STOP the whole run BLOCKED and route back to `odoo-planning` "
        "with a blocked_reason naming the node id.",
        id="blocks-the-whole-run",
    ),
    pytest.param(
        "A yielding node re-enters by reading `design_doc` from the returned contract's `inputs`.",
        id="describes-the-shape-only",
    ),
]


@pytest.mark.parametrize("sample", YIELD_RULE_MUST_NOT_CATCH)
def test_the_yielding_detector_rejects_the_stall_and_the_wrong_blast_radius(sample):
    assert not blocks_the_yielding_emitter(sample), (
        f"the detector must NOT accept {sample!r} - it is either the stall itself (finding only), a "
        f"different node class, the wrong blast radius (the run instead of the node), or a "
        f"description of the shape with no rule attached"
    )


UNCONDITIONAL_ESCALATION = (
    "Any node that emitted a refused design hop - yielding or not - is set to BLOCKED with a "
    "blocked_reason naming that node, the node id, the refused hop and `odoo-planning`; nothing is "
    "ever left as a mere finding."
)


def test_an_unconditional_escalation_fails_the_anti_over_fix_check():
    """The two detectors must disagree on an over-fix: it blocks, but it kills the finding path."""
    assert blocks_the_yielding_emitter(UNCONDITIONAL_ESCALATION)
    assert not keeps_the_finding_only_path(UNCONDITIONAL_ESCALATION), (
        "an unconditional escalation must FAIL the finding-only check - otherwise 'block every "
        "refused hop' passes both guards and stops runs that were never stalled"
    )


VOCABULARY_MUST_CATCH = [
    pytest.param("Set the node to status: WAITING until a design lands.", id="waiting-status"),
    pytest.param("Mark it PARKED and move on to the next ready node.", id="parked-status"),
    pytest.param("Record `waiting_on: odoo-solution-design` on the node.", id="waiting-on-field"),
    pytest.param("Write `stall_reason: refused design hop` into the run file.", id="stall-reason-field"),
]


@pytest.mark.parametrize("sample", VOCABULARY_MUST_CATCH)
def test_the_vocabulary_detector_catches_every_invention(sample):
    assert find_invented_vocabulary(sample), (
        f"the vocabulary detector must catch {sample!r} - a fifth status or a parallel field is how "
        f"a single contract turns into two"
    )


VOCABULARY_MUST_NOT_CATCH = [
    pytest.param(
        "Set THAT node to `BLOCKED` with `blocked_reason` naming the node id, the refused design "
        "hop, and `odoo-planning` as the owner who must amend the plan.",
        id="the-rule-itself",
    ),
    pytest.param(
        "status: DONE | NEEDS_NEXT | BLOCKED | NEEDS_CONTEXT",
        id="the-declared-enum",
    ),
    pytest.param(
        "invent no fifth status and no new field for what the node was waiting on",
        id="the-ban-itself",
    ),
]


@pytest.mark.parametrize("sample", VOCABULARY_MUST_NOT_CATCH)
def test_the_vocabulary_detector_leaves_the_declared_vocabulary_alone(sample):
    hits = find_invented_vocabulary(sample)
    assert not hits, (
        f"the vocabulary detector must NOT catch {sample!r} (matched {hits!r}) - it would fire on "
        f"the rule's own wording and on the contract's declared enum"
    )
