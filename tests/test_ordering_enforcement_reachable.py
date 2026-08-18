"""Guard: the design-then-planning ordering SSOT must POINT AT its enforcement, not only state it.

## CONTRACT CHANGE - what this file was re-derived to

The rule NARROWED by owner decision: **planning is mandatory for ALL work and may never be refused
for a missing design, at any complexity level; a design is OPTIONAL everywhere; the only surviving
rule is directional - a design, IF it exists, precedes the plan, i.e. a design may be an INPUT to a
plan but never a NODE of one.**

So `skills/odoo-planning/SKILL.md` no longer ENFORCES anything: its pre-dispatch refusal predicate
(`if design_required and not design_present: REFUSE`) is gone and the section that held it now only
DECLARES the order and points onward. This guard previously keyed its FIRST surface on exactly that
predicate, so it was RED by construction after the change. It is re-derived here to the surfaces that
actually enforce under the new contract - not patched to keep the old one alive:

| surface | what enforces | pointer demanded from the SSOT declaration |
|---|---|---|
| schema | a plan node's `approach` may not be the design skill/agent | yes |
| driver | no tier for a design node, static or materialized | yes |
| actor | the plan author may wire no node it writes to design | via the surface that OWNS the rule |

The planning skill's DECLARATION is checked by `test_design_precedes_planning.py` (it must keep the
mandatory-planning statement, the one-way rule, and pointers at all three surfaces). This file owns
only the reachability of ENFORCEMENT from the SSOT that declares the rule.

## Behaviour protected

`snippets/planning-gate-contract.md` is the ONE file that DECLARES `odoo-planning` sits DOWNSTREAM of
`odoo-solution-design`. Nothing in that file evaluates the rule. A reader who arrives at the
declaration must be able to REACH each enforcing surface from it: the declaration's own section must
hand over a citation naming the surface's FILE and the SECTION inside that file whose prose actually
enforces. The actor binding is reached one hop further - the actor's own ban must cite the surface
that OWNS the constraint it applies, so the chain declaration -> owner -> actor never breaks in the
middle.

A declaration with no route to its enforcement is the shape this plugin fails at most often - a
correct rule that nothing ever reaches. It also fails in the other direction: a pointer that still
reads fine but now names a moved file or a renamed section sends the reader nowhere, and no existing
check notices, because every path in it still resolves as a path.

## Why this is not "the statement exists" restated

`test_design_precedes_planning.py::test_the_ordering_statement_keeps_its_ssot` already asserts the
sentence survives, and the enforcement guards in that same file already assert each surface enforces.
NEITHER asserts the two are connected. This one asserts only the connection, and it asserts it as
reachability, not as a string: the cited section must exist in the cited file AND its span must
contain the enforcing prose. Citing a real file's real-but-unrelated section fails.

## Why the surfaces are DERIVED, never listed

Each surface is identified by the prose that DOES the enforcing; its owning file is then resolved from
the tree. So moving a surface to another file, or renaming the section that carries it, makes this
guard demand an updated pointer instead of going green on a stale citation - and the guard needs no
edit when that legitimately happens. A hardcoded path list would have to be maintained in lockstep
with the thing it is watching, which is how a guard ends up asserting last year's layout.

## Anti-brittleness

`unreachable_enforcement` and `unreachable_owner_from_actor` are pure functions of text, so the
MUST-CATCH / MUST-NOT-CATCH probes below exercise the SAME code the real-tree cases run - never a
parallel re-implementation. Whitespace is normalized before matching (a citation may line-wrap
between its path and its `§`, and every marker sentence here wraps in its own file), the
`${CLAUDE_PLUGIN_ROOT}/` prefix is optional (both spellings are live conventions in this repo), and
the declaration is located by any of several spellings rather than one sentence, because a guard keyed
on one phrasing goes green the moment the prose is reworded around it.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
GATE = PLUGIN / "snippets" / "planning-gate-contract.md"

_GENERATED = re.compile(r"<!-- BEGIN GENERATED TOOLS -->.*?<!-- END GENERATED TOOLS -->", re.DOTALL)
_TEXT_EXTS = {".md", ".yaml", ".yml"}

#: One entry per surface that ENFORCES the ordering, keyed on the prose that performs the enforcement
#: - never on a path. The owning file is resolved from the tree (see `_owners`), so a rename or move
#: is a pointer bug this guard reports, not a blind spot it inherits. Patterns are whitespace-
#: tolerant because each of these sentences line-wraps in its own file.
ENFORCING_SURFACES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "the SCHEMA constraint (a plan node may not be a design node)",
        re.compile(r"\*\*Design\s+is\s+an\s+INPUT\s+to\s+this\s+plan"),
    ),
    (
        "the DRIVER refusal (no tier for a design node, static or materialized)",
        re.compile(r"(?i)Neither\s+class\s+may\s+be\s+a\s+DESIGN\s+node"),
    ),
)

#: The ACTOR binding: the agent that WRITES plans is bound by the same shape rule. It is not reached
#: straight from the SSOT (the declaration routes a reader to the surfaces that own the rule, and the
#: actor conforms to the schema rather than restating it), so its reachability is asserted one hop
#: down: the actor's own ban must cite the surface that OWNS the constraint.
ACTOR_BINDING: tuple[str, re.Pattern[str]] = (
    "the ACTOR binding (the plan author may wire no node it writes to design)",
    re.compile(r"(?i)no\s+node\s+you\s+author\s+may\s+be\s+wired\s+to"),
)

#: The surface this guard USED to demand, removed by the owner decision above. Kept as data so the
#: removal is asserted rather than assumed - see
#: `test_the_removed_refusal_surface_is_gone_from_the_whole_tree`.
REMOVED_REFUSAL_SURFACE = re.compile(r"if\s+design_required\s+and\s+not\s+design_present")

#: Any spelling of the ordering declaration itself. Deliberately redundant - keying this on the one
#: sentence in the file today is exactly how the pointer survives a rewording that orphans it.
ORDERING_RX = re.compile(
    r"(?i)design-then-planning"
    r"|DOWNSTREAM of `?odoo-solution-design"
    r"|design precedes planning"
    r"|design (?:must )?precedes? (?:the |any )?plan\b"
    r"|`?odoo-planning`?[^.\n]{0,40}?\bruns AFTER (?:the )?(?:approved )?design"
)

#: A `§`/"section" marker just before a match means the text is CITING a section that happens to be
#: named after the rule, not DECLARING the rule. Without this, deleting the declaration while
#: keeping the pointer would look like the declaration is still there - the pointer would be
#: vouching for its own anchor.
_CITATION_LEAD_RX = re.compile(r"(?:§|\bsection\b)\s*[\"'`]*$", re.IGNORECASE)

_HEADING_RX = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")
#: A bold lead at the start of a line is a section anchor in this repo as much as a `##` heading is
#: (`**Design is an INPUT to this plan, ...**` is cited as `§ Design is an INPUT to this plan`), so
#: a pointer resolver that only understood headings would call a live citation broken.
_BOLD_LEAD_RX = re.compile(r"(?m)^\*\*(.+?)\*\*")
_SECTION_HEADING_RX = re.compile(r"(?m)^##\s+(.+?)\s*$")

_PATH_RX = re.compile(
    r"(?:\$\{CLAUDE_PLUGIN_ROOT\}/)?"
    r"((?:skills|snippets|agents|workflows|docs)/[A-Za-z0-9_./-]+\.(?:md|ya?ml))"
)
_CITED_SECTION_RX = re.compile(r"^[`),:;\s]*(?:§|\bsection\b)\s*[\"'`]*([^,.;()`\n]+)")

#: A citation often runs straight into prose ("§ Design is an INPUT to this plan owns the
#: constraint"), so the resolver accepts the leading run of the citation that names the section - but
#: never a run so short it would answer to half the headings in the tree.
_MIN_TITLE_PREFIX = 20


# ---------------------------------------------------------------------------
# Tree resolution (data-driven: no path is ever named in this module).
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _tree_texts() -> dict[str, str]:
    return {
        str(p.relative_to(PLUGIN)): _GENERATED.sub("", p.read_text(encoding="utf-8"))
        for p in sorted(PLUGIN.rglob("*"))
        if p.is_file() and p.suffix in _TEXT_EXTS
    }


def _owners(marker: re.Pattern[str]) -> list[str]:
    return [rel for rel, text in _tree_texts().items() if marker.search(text)]


def _sole_owner(marker: re.Pattern[str]) -> str | None:
    owners = _owners(marker)
    return owners[0] if len(owners) == 1 else None


# ---------------------------------------------------------------------------
# The pointer resolver (pure text).
# ---------------------------------------------------------------------------


def _norm(text: str) -> str:
    return " ".join(text.split())


def _anchors(text: str) -> list[tuple[str, int, int]]:
    """`(title, level, start)` for every section anchor, in document order.

    A bold lead gets the deepest level, so its span ends at the next anchor of any kind.
    """
    found = [(m.group(2).strip(), len(m.group(1)), m.start()) for m in _HEADING_RX.finditer(text)]
    found += [(m.group(1).strip(), 6, m.start()) for m in _BOLD_LEAD_RX.finditer(text)]
    found.sort(key=lambda a: a[2])
    return found


def _titles_match(cited: str, actual: str) -> bool:
    """A citation names a section by its opening words; either side may carry a longer tail."""
    c = _norm(cited).casefold().strip(" .,:;-`\"'")
    a = _norm(actual).casefold().strip(" .,:;-`\"'")
    if len(c) < 8 or len(a) < 8:
        return False
    if a.startswith(c) or c.startswith(a):
        return True
    # The citation ran into prose after the section name: accept its longest leading run that names
    # the section, at a word boundary, never shorter than `_MIN_TITLE_PREFIX` (a 2-word prefix would
    # resolve to any heading that merely starts the same way, which is how a stale pointer goes
    # green).
    words = c.split()
    for n in range(len(words) - 1, 0, -1):
        prefix = " ".join(words[:n])
        if len(prefix) >= _MIN_TITLE_PREFIX and a.startswith(prefix):
            return True
    return False


def _anchor_span(text: str, cited_section: str) -> str | None:
    """The span the cited section owns in `text`, or None when no anchor answers to that name."""
    anchors = _anchors(text)
    for i, (title, level, start) in enumerate(anchors):
        if not _titles_match(cited_section, title):
            continue
        end = len(text)
        for _t, nxt_level, nxt_start in anchors[i + 1:]:
            if nxt_start > start and nxt_level <= level:
                end = nxt_start
                break
        return text[start:end]
    return None


def citations(text: str) -> list[tuple[str, str]]:
    """Every `(plugin-relative path, cited section title)` pointer the text hands a reader.

    Whitespace is normalized first: a citation that line-wraps between its path and its `§` is one
    pointer, not a broken one. A path with no `§` following it is a mention, not a section pointer.
    """
    flat = _norm(text)
    out: list[tuple[str, str]] = []
    for m in _PATH_RX.finditer(flat):
        sm = _CITED_SECTION_RX.match(flat[m.end(): m.end() + 200])
        if sm:
            out.append((m.group(1), _norm(sm.group(1))))
    return out


def _reaches(owner: str, pointed_at: list[str], marker: re.Pattern[str]) -> list[str]:
    """The cited sections of `owner` whose span actually contains the enforcing prose."""
    owner_text = _tree_texts()[owner]
    return [
        sec
        for sec in pointed_at
        if (span := _anchor_span(owner_text, sec)) is not None and marker.search(span)
    ]


def _declaration(gate_text: str) -> re.Match[str] | None:
    """The first ordering match that DECLARES the rule rather than citing a section named for it."""
    for m in ORDERING_RX.finditer(gate_text):
        if not _CITATION_LEAD_RX.search(gate_text[max(0, m.start() - 40): m.start()]):
            return m
    return None


def _regions(gate_text: str) -> str:
    """Where a pointer counts as reachable FROM the declaration.

    The declaration's own `##` section, plus any `##` section whose heading is itself about the
    ordering - so promoting the pointer into its own titled section stays legal, while parking it
    in an unrelated section (where a reader of the declaration never arrives) does not.
    """
    m = _declaration(gate_text)
    if m is None:
        return ""
    bounds = [(h.start(), h.group(1)) for h in _SECTION_HEADING_RX.finditer(gate_text)]
    spans: list[tuple[int, int]] = []
    for i, (start, title) in enumerate(bounds):
        end = bounds[i + 1][0] if i + 1 < len(bounds) else len(gate_text)
        if start <= m.start() < end or ORDERING_RX.search(title):
            spans.append((start, end))
    if not spans:  # declaration sits above the first `##` heading
        spans = [(0, bounds[0][0] if bounds else len(gate_text))]
    return "\n".join(gate_text[s:e] for s, e in spans)


def unreachable_enforcement(gate_text: str) -> list[str]:
    """Every ENFORCING surface a reader of the ordering declaration cannot reach from it."""
    if _declaration(gate_text) is None:
        return [
            "the ordering declaration itself is gone from the SSOT - there is no statement left "
            "for any pointer to hang off"
        ]
    cited = citations(_regions(gate_text))
    problems: list[str] = []
    for label, marker in ENFORCING_SURFACES:
        owner = _sole_owner(marker)
        if owner is None:
            problems.append(
                f"{label}: expected exactly ONE file in the tree to carry {marker.pattern!r}, "
                f"found {_owners(marker)} - the surface moved, vanished, or got duplicated"
            )
            continue
        pointed_at = [sec for path, sec in cited if path == owner]
        if not pointed_at:
            problems.append(
                f"{label}: the declaration's section carries no `{owner}` + `§ <section>` pointer, "
                f"so a reader of the SSOT cannot reach it"
            )
            continue
        if not _reaches(owner, pointed_at, marker):
            problems.append(
                f"{label}: pointer(s) at `{owner}` name section(s) {pointed_at} - none resolves to "
                f"a section of that file whose prose enforces ({marker.pattern!r}); the citation "
                f"lands somewhere the rule is not applied"
            )
    return problems


def _enclosing_paragraph(text: str, at: int) -> str:
    """The blank-line-delimited paragraph containing offset `at` - what a reader of it also sees."""
    start = text.rfind("\n\n", 0, at)
    start = 0 if start == -1 else start + 2
    end = text.find("\n\n", at)
    return text[start: len(text) if end == -1 else end]


def unreachable_owner_from_actor(actor_text: str) -> list[str]:
    """Whether the ACTOR's ban hands its reader the surface that OWNS the constraint it applies.

    The actor restates a shape rule it does not own. If its ban carries no resolving pointer at the
    owning surface, the two drift apart silently: the owner's coverage and reason get edited and the
    actor keeps applying a rule nobody can trace back.
    """
    label, marker = ACTOR_BINDING
    m = marker.search(actor_text)
    if m is None:
        return [f"{label}: the ban itself is gone - there is nothing left to trace to its owner"]
    owner_label, owner_marker = ENFORCING_SURFACES[0]  # the schema owns the plan-shape constraint
    owner = _sole_owner(owner_marker)
    if owner is None:
        return [
            f"{owner_label}: expected exactly ONE file in the tree to carry "
            f"{owner_marker.pattern!r}, found {_owners(owner_marker)}"
        ]
    pointed_at = [
        sec
        for path, sec in citations(_enclosing_paragraph(actor_text, m.start()))
        if path == owner
    ]
    if not pointed_at:
        return [
            f"{label}: the ban carries no `{owner}` + `§ <section>` pointer in its own paragraph, so "
            f"the rule it applies cannot be traced to {owner_label}"
        ]
    if not _reaches(owner, pointed_at, owner_marker):
        return [
            f"{label}: the ban's pointer(s) name section(s) {pointed_at} of `{owner}` - none "
            f"resolves to a section whose prose enforces ({owner_marker.pattern!r})"
        ]
    return []


# ---------------------------------------------------------------------------
# Discovery floors - a resolver that finds nothing would pass everything.
# ---------------------------------------------------------------------------

ALL_SURFACES = ENFORCING_SURFACES + (ACTOR_BINDING,)


def test_the_tree_yields_the_corpus_the_resolver_needs():
    texts = _tree_texts()
    assert len(texts) >= 200, f"expected a substantial plugin corpus, found {len(texts)} files"
    assert GATE.is_file(), "snippets/planning-gate-contract.md (the ordering SSOT) is missing"


@pytest.mark.parametrize("label,marker", ALL_SURFACES, ids=[s[0][:40] for s in ALL_SURFACES])
def test_each_enforcement_surface_is_owned_by_exactly_one_file(label, marker):
    """Independent of any pointer: the surface exists, once, and is locatable by its own prose."""
    owners = _owners(marker)
    assert len(owners) == 1, (
        f"{label}: {marker.pattern!r} must identify exactly ONE owning file (it is how this guard "
        f"resolves the pointer target); found {owners}"
    )


@pytest.mark.parametrize("label,marker", ALL_SURFACES, ids=[s[0][:40] for s in ALL_SURFACES])
def test_the_resolver_can_reach_each_surface_by_its_own_section(label, marker):
    """Floor for `_anchor_span`: every surface really does live under a nameable section anchor.

    Without this, a resolver bug that returned None for everything would report "pointer broken"
    for a perfectly good pointer - and the fix would be to weaken the guard.
    """
    owner_text = _tree_texts()[_owners(marker)[0]]
    m = marker.search(owner_text)
    enclosing = [
        title
        for title, _level, start in _anchors(owner_text)
        if start <= m.start() and (span := _anchor_span(owner_text, title)) and marker.search(span)
    ]
    assert enclosing, (
        f"{label}: the enforcing prose sits under no resolvable section anchor, so no citation "
        f"could ever reach it - give it a heading or a bold lead"
    )


def test_the_removed_refusal_surface_is_gone_from_the_whole_tree():
    """CONTRACT CHANGE, asserted rather than assumed: surface 1 was REMOVED, not relocated.

    This guard shrank from three enforcing surfaces to two because the owner removed the planning
    skill's design refusal. A surface list that shrinks on the assumption something is gone is how a
    guard quietly stops watching a live mechanism, so the removal is a check of its own: nothing in
    either plugin may evaluate a design predicate before planning again.
    """
    owners = _owners(REMOVED_REFUSAL_SURFACE)
    assert not owners, (
        f"{owners} still carry the removed refusal predicate "
        f"({REMOVED_REFUSAL_SURFACE.pattern!r}). Planning is mandatory for ALL work and is never "
        f"refused for a missing design (owner decision); if this predicate is deliberately back, the "
        f"enforcing-surface list here and the inverse assertions in "
        f"test_design_precedes_planning.py must be re-derived with it, not left contradicting it."
    )


# ---------------------------------------------------------------------------
# The real tree.
# ---------------------------------------------------------------------------


def test_the_ordering_ssot_hands_the_reader_every_enforcement_surface():
    problems = unreachable_enforcement(GATE.read_text(encoding="utf-8"))
    assert not problems, (
        "snippets/planning-gate-contract.md DECLARES the design-then-planning ordering but a "
        "reader of that declaration cannot reach where it is ENFORCED:\n  - "
        + "\n  - ".join(problems)
        + "\nAdd/repair a `<path>` + `§ <section>` pointer in the declaration's own section for "
        "each surface. A rule nobody can trace to its enforcement is prose."
    )


def test_the_actor_binding_traces_back_to_the_surface_that_owns_it():
    owner = _sole_owner(ACTOR_BINDING[1])
    assert owner, f"{ACTOR_BINDING[0]}: no single owning file - see the ownership floor above"
    problems = unreachable_owner_from_actor(_tree_texts()[owner])
    assert not problems, (
        f"`{owner}` applies the plan-shape ban but a reader cannot trace it to the surface that "
        "OWNS it:\n  - " + "\n  - ".join(problems)
    )


# ---------------------------------------------------------------------------
# MUST-CATCH: every shape a missing or broken pointer can take.
# ---------------------------------------------------------------------------

_STATEMENT = (
    "## Plan-Mode enter/exit\n\n"
    "**Design-then-planning ordering.** `odoo-planning` is DOWNSTREAM of `odoo-solution-design`: "
    "it runs AFTER design and CONSUMES the approved design output.\n"
)

_GOOD_POINTER = (
    " ENFORCED at `skills/odoo-intake/references/plan-mode-schema.md` § Design is an INPUT to this "
    "plan, and `skills/run-harness/references/run-integration.md` § Gate-tier node classes.\n"
)

MUST_CATCH: tuple[tuple[str, str], ...] = (
    (
        "no pointer at all - the declaration stands alone",
        _STATEMENT,
    ),
    (
        "paths cited with no section, so the reader lands on a 900-line file",
        _STATEMENT
        + "See `skills/odoo-intake/references/plan-mode-schema.md` "
        "and `skills/run-harness/references/run-integration.md`.\n",
    ),
    (
        "sections renamed at the surface, pointer left behind (stale section names)",
        _STATEMENT
        + " ENFORCED at `skills/odoo-intake/references/plan-mode-schema.md` § Node field reference, "
        "and `skills/run-harness/references/run-integration.md` § Tier resolution table.\n",
    ),
    (
        "one path misspelled - reads fine, resolves to nothing",
        _STATEMENT
        + " ENFORCED at `skills/odoo-intake/references/plan-mode-schemas.md` § Design is an INPUT to "
        "this plan, and `skills/run-harness/references/run-integration.md` § Gate-tier node "
        "classes.\n",
    ),
    (
        "only one of the surfaces cited - the driver refusal is unreachable",
        _STATEMENT
        + " ENFORCED at `skills/odoo-intake/references/plan-mode-schema.md` § Design is an INPUT to "
        "this plan.\n",
    ),
    (
        "the declaration names only the skill that DECLARES, not the surfaces that enforce",
        _STATEMENT
        + " ENFORCED at `skills/odoo-planning/SKILL.md` § Design precedes planning.\n",
    ),
    (
        "pointer parked in an unrelated section a reader of the declaration never reaches",
        _STATEMENT + "\n## Migration carve-out\n\nA front-door routing decision." + _GOOD_POINTER,
    ),
    (
        "sections exist in the right files but carry none of the enforcement",
        _STATEMENT
        + " ENFORCED at `skills/odoo-intake/references/plan-mode-schema.md` § Rejection flow, and "
        "`skills/run-harness/references/run-integration.md` § Run start procedure.\n",
    ),
    (
        "pointer kept, declaration deleted - nothing is being pointed FROM",
        "## Plan-Mode enter/exit\n\nSome unrelated prose." + _GOOD_POINTER,
    ),
)


@pytest.mark.parametrize("shape,text", MUST_CATCH, ids=[s[0][:52] for s in MUST_CATCH])
def test_a_broken_or_missing_pointer_is_caught(shape, text):
    assert unreachable_enforcement(text), (
        f"MUST-CATCH shape went undetected: {shape}. The detector accepts a pointer a reader "
        f"cannot follow, which is the whole failure mode it exists to report."
    )


# ---------------------------------------------------------------------------
# MUST-NOT-CATCH: legitimate spellings of a working pointer.
# ---------------------------------------------------------------------------

MUST_NOT_CATCH: tuple[tuple[str, str], ...] = (
    (
        "the wording this round happens to use",
        _STATEMENT + _GOOD_POINTER,
    ),
    (
        "reworded lead-in, surfaces in a different order",
        _STATEMENT
        + "Where the rule is actually applied: "
        "`skills/run-harness/references/run-integration.md` § Gate-tier node classes; "
        "`skills/odoo-intake/references/plan-mode-schema.md` § Design is an INPUT to this plan.\n",
    ),
    (
        "bulleted list instead of a sentence",
        _STATEMENT
        + "\nEnforced by:\n\n"
        "- `skills/odoo-intake/references/plan-mode-schema.md` § Design is an INPUT to this plan\n"
        "- `skills/run-harness/references/run-integration.md` § Gate-tier node classes\n",
    ),
    (
        "${CLAUDE_PLUGIN_ROOT}-prefixed paths (the other live convention)",
        _STATEMENT
        + " ENFORCED at `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` "
        "§ Design is an INPUT to this plan, and "
        "`${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/run-integration.md` "
        "§ Gate-tier node classes.\n",
    ),
    (
        "each section followed by a parenthetical descriptor",
        _STATEMENT
        + " ENFORCED at `skills/odoo-intake/references/plan-mode-schema.md` § Design is an INPUT to "
        "this plan (schema), and `skills/run-harness/references/run-integration.md` § Gate-tier node "
        "classes (driver).\n",
    ),
    (
        "a citation that runs straight into prose after the section name",
        _STATEMENT
        + " ENFORCED at `skills/odoo-intake/references/plan-mode-schema.md` § Design is an INPUT to "
        "this plan owns the constraint and its reason, and "
        "`skills/run-harness/references/run-integration.md` § Gate-tier node classes covers both "
        "entry points.\n",
    ),
    (
        "citation line-wrapped between its path and its section",
        _STATEMENT
        + " ENFORCED at `skills/odoo-intake/references/plan-mode-schema.md`\n"
        "§ Design is an INPUT to this plan,\n"
        "and `skills/run-harness/references/run-integration.md`\n§ Gate-tier node classes.\n",
    ),
    (
        "the declaring skill cited alongside the two enforcing surfaces",
        _STATEMENT + _GOOD_POINTER.rstrip("\n")[:-1]
        + ", declared at `skills/odoo-planning/SKILL.md` § Design precedes planning.\n",
    ),
    (
        "a fourth, unrelated surface cited alongside the two",
        _STATEMENT + _GOOD_POINTER.rstrip("\n")[:-1]
        + ", plus `snippets/vocabulary.md` § Cross-cutting index.\n",
    ),
    (
        "pointer promoted into its own ordering-titled section",
        _STATEMENT
        + "\n## Design precedes planning - enforcement surfaces\n" + _GOOD_POINTER,
    ),
    (
        "declaration spelled without the DOWNSTREAM wording",
        "## Plan-Mode enter/exit\n\n**Design-then-planning ordering.** `odoo-planning` "
        "runs AFTER design.\n" + _GOOD_POINTER,
    ),
)


@pytest.mark.parametrize("shape,text", MUST_NOT_CATCH, ids=[s[0][:52] for s in MUST_NOT_CATCH])
def test_a_working_pointer_is_left_alone(shape, text):
    problems = unreachable_enforcement(text)
    assert not problems, (
        f"MUST-NOT-CATCH shape was falsely reported: {shape}\n  - " + "\n  - ".join(problems)
    )


# ---------------------------------------------------------------------------
# The actor hop, same two-sided proof.
# ---------------------------------------------------------------------------

_ACTOR_BAN = (
    "The third commitment is also a SCHEMA rule on your OUTPUT: **no\nnode you author may be wired "
    "to `odoo-solution-design` or `odoo-solution-architect`** - design is an\nINPUT to this plan, "
    "never a node of it\n"
)

ACTOR_MUST_CATCH: tuple[tuple[str, str], ...] = (
    (
        "the ban states the rule and names no owner",
        _ACTOR_BAN + "(the plan schema forbids it outright).\n",
    ),
    (
        "the owner's file is named with no section - the reader lands on the whole schema",
        _ACTOR_BAN + "(see `skills/odoo-intake/references/plan-mode-schema.md`).\n",
    ),
    (
        "the cited section was renamed at the owner",
        _ACTOR_BAN
        + "(`skills/odoo-intake/references/plan-mode-schema.md` § Node field reference owns it).\n",
    ),
    (
        "the pointer names a real section that carries none of the constraint",
        _ACTOR_BAN
        + "(`skills/odoo-intake/references/plan-mode-schema.md` § Data source owns it).\n",
    ),
    (
        "the pointer sits in a different paragraph, not with the ban",
        _ACTOR_BAN
        + "\nYour Write targets are the plan and your worklog entry - nothing else.\n\n"
        "(`skills/odoo-intake/references/plan-mode-schema.md` § Design is an INPUT to this plan owns "
        "the constraint.)\n",
    ),
    (
        "the ban itself is gone - only the owner pointer remains",
        "You conform to the existing 3-block schema "
        "(`skills/odoo-intake/references/plan-mode-schema.md` § Design is an INPUT to this plan).\n",
    ),
)


@pytest.mark.parametrize("shape,text", ACTOR_MUST_CATCH, ids=[s[0][:52] for s in ACTOR_MUST_CATCH])
def test_an_actor_ban_that_cannot_be_traced_to_its_owner_is_caught(shape, text):
    assert unreachable_owner_from_actor(text), (
        f"MUST-CATCH shape went undetected: {shape}. An actor applying a shape rule nobody can "
        f"trace to its owner is how the two drift apart silently."
    )


ACTOR_MUST_NOT_CATCH: tuple[tuple[str, str], ...] = (
    (
        "the wording this round happens to use (citation running into prose)",
        _ACTOR_BAN
        + "(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/plan-mode-schema.md` § Design is "
        "an INPUT to\nthis plan owns the constraint, its coverage and its reason).\n",
    ),
    (
        "reworded ban, same paragraph, plain path prefix",
        "A SCHEMA rule on your OUTPUT: **no node you author may be wired to the design skill or its "
        "architect agent** - see `skills/odoo-intake/references/plan-mode-schema.md` § Design is an "
        "INPUT to this plan for the constraint and its reason.\n",
    ),
    (
        "the owner pointer plus a second, unrelated citation in the same paragraph",
        _ACTOR_BAN
        + "(`skills/odoo-intake/references/plan-mode-schema.md` § Design is an INPUT to this plan; "
        "gate mechanics live at `snippets/planning-gate-contract.md` § Plan-Mode enter/exit).\n",
    ),
)


@pytest.mark.parametrize(
    "shape,text", ACTOR_MUST_NOT_CATCH, ids=[s[0][:52] for s in ACTOR_MUST_NOT_CATCH]
)
def test_a_traceable_actor_ban_is_left_alone(shape, text):
    problems = unreachable_owner_from_actor(text)
    assert not problems, (
        f"MUST-NOT-CATCH shape was falsely reported: {shape}\n  - " + "\n  - ".join(problems)
    )
