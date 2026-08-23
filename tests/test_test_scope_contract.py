"""The test-scope contract: a `--test-enable` run is BOUNDED, and says how.

LIVE DEFECT this locks out
--------------------------
Agents wrote `-i sale --test-enable` where `-i sale --test-enable --test-tags /sale`
was meant, and `-u sale,account --test-enable` where `--test-tags /sale,/account`
was meant. `-i`/`-u` names modules but does not bound the run: Odoo installs the
whole dependency closure plus every `auto_install` match, and `--test-enable`
runs the suite of everything the registry loaded. So the "one module" run tested
the installed world from `base` up - minutes-to-hours of wall clock, and a
verdict decided by suites the change never touched.

The contract has two halves, and both are load-bearing:

  SCOPING     - the `-i`/`-u` list and the `--test-tags` selection are two sides
                of ONE module set (the change plus its in-repo blast radius) and
                must AGREE. Required, and derived from the module list when a
                caller supplies no tags.
  SUPPRESSION - tags covering FEWER modules than the caller declared, or an
                unrequested skip-auto-install. Forbidden: it stops exercising a
                module the caller DID declare, which manufactures a false green.

Banning tags outright (the earlier over-correction) is what produced the
untagged-by-default defect; requiring them without the suppression guard would
reintroduce the false green. These tests hold both ends.

Run: python -m pytest tests/test_test_scope_contract.py -v
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
CONTRACT = PLUGIN / "snippets" / "test-scope-contract.md"


def _norm(path: Path) -> str:
    """Prose is hard-wrapped in these files, so phrase assertions run against a
    whitespace-normalized copy."""
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The SSOT itself
# ---------------------------------------------------------------------------

def test_the_contract_exists_and_is_reachable_by_path():
    """Consumers cross-reference this file by path; a rename silently breaks
    every one of them, since a dead ${CLAUDE_PLUGIN_ROOT} pointer raises
    nothing at runtime - the agent simply reads no rule."""
    assert CONTRACT.is_file(), f"missing scope SSOT: {CONTRACT}"


def test_contract_states_the_two_sided_rule():
    """The whole defect is treating `--test-tags` as an optional extra rather
    than the other half of the same scope decision."""
    text = _norm(CONTRACT)
    assert re.search(r"-i\b.*-u\b|`-i`/`-u`", text), (
        "the contract must name the install side (-i/-u)"
    )
    assert "--test-tags" in text, "the contract must name the selection side"
    assert re.search(
        r"(two sides|both sides|two scope sides|TWO SCOPE SIDES)", text, re.IGNORECASE
    ), "the contract must state that the two flags are sides of ONE scope, not independent knobs"
    assert re.search(r"deriv", text, re.IGNORECASE), (
        "the contract must say the tag set is DERIVED from the module set, so the two "
        "cannot drift apart"
    )


def test_contract_states_what_an_untagged_run_actually_costs():
    """A rule with no stated consequence gets 'optimized away' by the next
    editor. The cost is concrete: the registry Odoo builds is far wider than
    the module list, and every bit of it runs its suite."""
    text = _norm(CONTRACT)
    assert re.search(r"auto_install", text), (
        "the contract must name the auto_install fan-out as part of why an untagged "
        "run is so much wider than the module list"
    )
    assert re.search(r"base", text), (
        "the contract must state how far the fan-out reaches (down to `base`)"
    )


def test_contract_names_the_cases_where_a_full_run_is_correct():
    """Not every full run is a defect. A rule that cannot say when the opposite
    is right gets ignored the first time it is wrong, so the exemptions are part
    of the contract - and each must be NAMED in the report, so an exemption
    cannot be claimed vaguely."""
    text = _norm(CONTRACT)
    assert re.search(r"exempt", text, re.IGNORECASE), (
        "the contract must carry an exemption list"
    )
    for case, pattern in [
        ("an explicit full-suite request", r"TEST_TAGS: full|`full`"),
        ("a run with no code change under test", r"no code change|smoke"),
        ("a series with no tag filter at all", r"no tag filter|lack.*--test-tags"),
        ("reproducing a CI gate that runs untagged", r"Runbot|CI.*gate"),
    ]:
        assert re.search(pattern, text, re.IGNORECASE), (
            f"the exemption list must cover: {case}"
        )
    assert re.search(r"cli_help", text), (
        "the series-capability exemption must be decided by a cli_help probe, never "
        "from a hardcoded version range"
    )


def test_contract_separates_scoping_from_suppression():
    """The discriminator has to be DECIDABLE, not a vibe: tags that cover every
    declared module are scoping; tags narrower than the declared set are
    suppression. Without a stated test, 'do not narrow the run' reads as 'never
    pass tags' - which is exactly the over-correction that caused the defect."""
    text = _norm(CONTRACT)
    assert re.search(r"suppress", text, re.IGNORECASE), (
        "the contract must name the suppression failure mode"
    )
    assert re.search(r"false green|false-green", text, re.IGNORECASE), (
        "the contract must keep stating WHY suppression is worse than a noisy run"
    )
    assert re.search(r"skip-auto-install|skip_auto_install", text), (
        "an unrequested skip-auto-install is the other half of suppression - it changes "
        "what is INSTALLED, so it can hide a real integration break"
    )
    assert re.search(r"(fewer|below|narrower)", text, re.IGNORECASE), (
        "the discriminator must be stated in terms of tags covering FEWER modules than "
        "the declared set - a decidable test, not a judgment call"
    )


def test_contract_does_not_restate_the_module_selection_algorithm():
    """SSOT discipline: WHICH modules enter the set is regression-scope.md's
    job. A second copy of the blast-radius algorithm here would drift."""
    text = _norm(CONTRACT)
    assert "regression-scope.md" in text, (
        "the contract must point at the blast-radius SSOT rather than restate it"
    )
    assert not re.search(r"K = 25|ceiling `K`", text), (
        "the widening ceiling belongs to regression-scope.md alone - do not copy it here"
    )


# ---------------------------------------------------------------------------
# The consumers - the rule has to be reachable from where the runs are composed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "relpath",
    [
        "agents/odoo-instance-ops.md",
        "skills/odoo-instance/SKILL.md",
        "docs/reference/ODOO-TESTING.md",
        "skills/_shared/regression-scope.md",
        "docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md",
    ],
)
def test_scope_rule_is_reachable_from_the_places_that_compose_runs(relpath):
    """An agent composing a test command reads one of these. Each must reach the
    rule - by pointing at the SSOT, not by carrying its own copy to drift."""
    path = PLUGIN / relpath
    assert path.is_file(), f"expected consumer missing: {path}"
    assert "test-scope-contract.md" in path.read_text(encoding="utf-8"), (
        f"{relpath} composes or documents --test-enable runs but does not reach the "
        "scope contract"
    )


# ---------------------------------------------------------------------------
# Regression guard: no agent-facing EXAMPLE may teach the untagged form
# ---------------------------------------------------------------------------

# A command line, not prose about one: `odoo-bin` and `--test-enable` on the
# same continued command.
_ODOO_BIN_LINE_RE = re.compile(r"odoo-bin\b")
_EXEMPTION_RE = re.compile(
    r"untagged|test-scope-contract|TEST_TAGS: full|no tag filter|Runbot|full suite|"
    r"deliberately|exemption",
    re.IGNORECASE,
)


def _command_blocks(text: str):
    """Yield (start_line_index, joined_command) for every odoo-bin invocation
    inside a fenced code block, following backslash continuations so a tag on
    the next line still counts.

    Only fenced blocks: those are the lines an agent copies. Prose that merely
    mentions `odoo-bin` while discussing venv resolution or a dispatch boundary
    is not an example and must not be forced to carry flags."""
    lines = text.splitlines()
    i = 0
    in_fence = False
    while i < len(lines):
        stripped = lines[i].lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            i += 1
            continue
        if in_fence and _ODOO_BIN_LINE_RE.search(lines[i]):
            start = i
            joined = lines[i]
            while joined.rstrip().endswith("\\") and i + 1 < len(lines):
                i += 1
                joined += " " + lines[i]
            yield start, joined
        i += 1


def _agent_facing_markdown():
    for path in sorted(PLUGIN.rglob("*.md")):
        # Generated IDE snippets mirror upstream text; CHANGELOG records history
        # (including the wording of the defect being fixed) and must stay verbatim.
        if path.name in {
            "cursor-rules.md",
            "openai-gpt-instructions.md",
            "gemini-gem-instructions.md",
        }:
            continue
        yield path


def test_no_agent_facing_example_teaches_an_unexplained_untagged_run():
    """Every `odoo-bin ... --test-enable` EXAMPLE in agent-facing prose either
    carries `--test-tags`, or sits beside an explicit statement that this run is
    untagged on purpose.

    Examples are what agents copy. An untagged one with no explanation is
    indistinguishable from the defect, and reads as the sanctioned form."""
    offenders = []
    for path in _agent_facing_markdown():
        text = path.read_text(encoding="utf-8")
        if "--test-enable" not in text:
            continue
        lines = text.splitlines()
        for start, command in _command_blocks(text):
            if "--test-enable" not in command:
                continue
            if "--test-tags" in command:
                continue
            # Allow a nearby explicit exemption - the run is untagged on purpose.
            window = "\n".join(lines[max(0, start - 12): start + 8])
            if _EXEMPTION_RE.search(window):
                continue
            offenders.append(
                f"{path.relative_to(ROOT)}:{start + 1}: {command.strip()[:110]}"
            )
    assert not offenders, (
        "these --test-enable examples run untagged with no stated reason - each will be "
        "copied into a run that tests every installed module from `base` up. Add "
        "--test-tags, or state the exemption beside it:\n  " + "\n  ".join(offenders)
    )
