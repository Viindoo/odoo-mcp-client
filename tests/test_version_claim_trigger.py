"""Guard the TRIGGER and the EXEMPTIONS of `[version-claim]` (rule 18) in
`generator/check_orchestration.py`.

## The two defects this test exists to prevent

Rule 18 fires on an Odoo version VALUE written into agent-facing prose. Two ways a real claim
reached the tree with the rule green, both measured on this branch against one commit that added
ten lines to `agents/odoo-backend-coder.md`:

**1. The trigger could not see a bare series.** The pattern required a `v` prefix (`v18`), an
`Odoo ` prefix (`Odoo 18`), or a `version ` prefix (`version 18`). A sentence spelling the series
on its own - `referred to as "tree views" in versions prior to 18.0` - matched nothing: the plural
`versions` breaks the `version\\s+\\d` alternative and a lone `18.0` has no prefix at all. The most
natural way an author writes a series was the one spelling the rule could not read.

**2. Exemption 2 blessed a restatement because a pointer stood beside it.** The exemption reads
"the unit names a boundary SSOT file - it points instead of restating", and silenced the WHOLE
unit. A sentence that does BOTH - `list - also known as tree in Odoo 17 ... per
odoo-version-pivots.md` - is the exact shape the exemption was meant to reward, so it went silent
on the copy while the citation sat two clauses away. That is worse than no exemption: the closer
prose gets to correct SSOT discipline, the more invisible its drift becomes.

## Chosen formulation

Unit-level and behavioural: assert what the rule CONCLUDES about a string, never how it is spelled
internally, so any future re-implementation of the pattern is held to the same contract. Each
positive case is paired with the negative that the widening must not swallow - a version inside a
FILE PATH (`coding_guidelines/17.0/naming.md`) and a manifest `version` value (`17.0.1.0.0`) are
not claims, and a pointer that carries the value only inside its own citation anchor is still
exempt.

Run: python -m pytest tests/test_version_claim_trigger.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from generator import check_orchestration as co  # noqa: E402


def hits(unit: str) -> list[str]:
    """What rule 18 concludes about one prose unit, exemptions applied."""
    return co._version_claim_hits(unit, co._osm_tool_names())


# --- 1. the trigger reads a bare series ---------------------------------------------------------

@pytest.mark.parametrize(
    "unit",
    [
        'For list views (referred to as "tree views" in versions prior to 18.0), use optional="hide".',
        "The chatter element changed at 18.0.",
        "Keep the legacy widget path through 14.0 and switch after.",
        "Available from 15.0 onward.",
    ],
)
def test_a_bare_series_in_prose_is_a_claim(unit):
    """A series spelled without a `v`/`Odoo `/`version ` prefix is still a version value.

    This is how an author writes it by hand, so it is the spelling the rule most needs to read."""
    assert hits(unit), f"bare series went undetected in: {unit!r}"


@pytest.mark.parametrize("unit", ["Odoo 17 renamed the tag.", "The tag changed at v18.", "Use version 15 semantics."])
def test_the_prefixed_spellings_still_fire(unit):
    """Widening the trigger must not cost the spellings it already read."""
    assert hits(unit), f"prefixed version value went undetected in: {unit!r}"


# --- 2. the widening must not swallow non-claims -------------------------------------------------

@pytest.mark.parametrize(
    "unit",
    [
        "Read `${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/17.0/naming.md` for the rules.",
        "Consult `17.0/python.md`, never memory.",
        "The per-version index lives at coding_guidelines/18.0/INDEX.md.",
    ],
)
def test_a_series_inside_a_file_path_is_not_a_claim(unit):
    """`coding_guidelines/17.0/naming.md` names a FILE. Reporting it would force an author to
    rename a real path to satisfy a lint, which is how a rule earns being ignored."""
    assert not hits(unit), f"a path segment was reported as a version claim: {unit!r}"


@pytest.mark.parametrize(
    "unit",
    [
        "Manifest `version` for the upgrade convention is the series-prefixed `17.0.1.0.0` form.",
        "Never write `18.0.1.0.0` as a scaffold default.",
    ],
)
def test_a_manifest_version_value_is_not_a_series_claim(unit):
    """`17.0.1.0.0` is a manifest field value, not a boundary claim about the series."""
    assert not hits(unit), f"a manifest version value was reported as a version claim: {unit!r}"


# --- 3. exemption 2 covers the POINTER, not a restatement beside it ------------------------------

@pytest.mark.parametrize(
    "unit",
    [
        "View arch tag history per `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` "
        "§ XML views - also known as tree in Odoo 17 and its previous versions.",
        "ACL `check_access` from v18 - see `snippets/odoo-version-pivots.md`.",
        "Tokens differ by series (the `assets` key lands at 15.0); consult odoo-version-pivots.md.",
    ],
)
def test_a_unit_that_points_AND_restates_is_still_a_claim(unit):
    """Exemption 2 exists because a pointer replaces the value. When the value is written out
    anyway, the pointer is not doing that job and the copy still rots when the SSOT row moves."""
    assert hits(unit), f"a restatement hid behind a boundary-SSOT pointer: {unit!r}"


@pytest.mark.parametrize(
    "unit",
    [
        "View arch tag history per `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § XML views.",
        "Era crossings are owned by `snippets/odoo-era-boundaries.md`; read them there.",
        "Resolve the boundary from `odoo-version-pivots.md` § check_access from v18.",
    ],
)
def test_a_pure_pointer_stays_exempt(unit):
    """The whole point of exemption 2. A citation - including a § anchor that names the row by
    its version - carries no restatement, so it must stay silent or the rule punishes the fix."""
    assert not hits(unit), f"exemption 2 stopped covering a pure pointer: {unit!r}"


# --- 4. the other exemptions are untouched -------------------------------------------------------

def test_a_full_span_scope_is_not_a_boundary_claim():
    """Naming the support envelope is not asserting a boundary."""
    assert not hits("OSM indexes every major from v8.0 to v19.0.")


def test_a_value_travelling_with_its_resolution_call_stays_exempt():
    """When the unit names the tool that RESOLVES the value, the value cannot go stale silently."""
    assert not hits("Call `set_active_version(odoo_version='17.0')` before any structural lookup.")


# --- 5. a placeholder slot is not a claim --------------------------------------------------------

@pytest.mark.parametrize(
    "unit",
    [
        "ODOO_VERSION: <e.g. 17.0>",
        "SOURCE SERIES: <e.g. 16.0>",
        "odoo_version: <17.0>",
        # `_prose_units` splits on sentence boundaries, and the `.` in `<e.g. 17.0>` is one - so a
        # slot reaches the trigger with its opening bracket left behind in the previous unit.
        "17.0> SHARE_DIR: <abs-path resolved by the skill>",
    ],
)
def test_a_version_inside_a_placeholder_slot_is_not_a_claim(unit):
    """`<e.g. 17.0>` is a field the CALLER fills at dispatch time, not a boundary this file
    asserts. Brief templates carry these by the dozen; reporting them would make every future
    template edit noisy, and a rule at that signal-to-noise trains an author to ignore it."""
    assert not hits(unit), f"a brief-template placeholder was reported as a version claim: {unit!r}"


@pytest.mark.parametrize(
    "unit",
    [
        "- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version.",
        "`api_version_diff(symbol='web', from_version='8.0', to_version='12.0')`",
        '`model_inspect(model="res.partner", method="views", odoo_version="18.0")`',
    ],
)
def test_a_version_inside_a_call_argument_is_an_example_not_a_claim(unit):
    """A keyword-argument literal illustrates the SHAPE of a call. Rule 17 scans generated prose
    with the resolution-call exemption deliberately OFF, so the argument exemption has to hold on
    its own - the 38 generated `## MCP tools` blocks all carry this line verbatim from the JSON
    SSOT, and reporting them would gate CI on a sentence no author of a skill can even edit."""
    assert not co._version_claim_hits(unit, co._osm_tool_names(), allow_call_exemption=False), (
        f"a call-argument example was reported as a version claim: {unit!r}"
    )
