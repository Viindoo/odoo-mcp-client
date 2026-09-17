"""Behavioral gate: the three build facts an executing agent must get right per series.

An agent composes its own `odoo-bin` command from this plugin's prose, so a fact that is
stale here becomes a wrong command with no error: a lint gate that tags a module the series
renamed away goes GREEN having checked nothing; a `--load` missing a server-wide module boots
a registry unlike every other build; a demo flag spelled with a value dies at option parsing
before the database is touched.

These assertions lock in (1) which modules the backend lint gate is made of per series,
(2) the per-series server-wide `--load` set, and (3) demo data decided by build purpose.
All three are single-sourced in snippets/odoo-version-pivots.md; the negative sweeps below
are what stop a consumer from re-growing its own stale copy.

Run: python -m pytest tests/test_viindoo_build_facts.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

PIVOTS = PLUGIN / "snippets" / "odoo-version-pivots.md"
LINT_GATE = PLUGIN / "snippets" / "lint-gate-modules.md"
AGENT_MD = PLUGIN / "agents" / "odoo-instance-ops.md"


def _norm(path: Path) -> str:
    """Whitespace-normalized text, so a reflow never silently drops a guarded claim.

    Blockquote markers are stripped first: much of the load-bearing prose here lives in `>`
    callouts, where a line wrap would otherwise leave a stray `>` mid-sentence and make a
    guarded phrase unmatchable for a reason that has nothing to do with the claim.
    """
    raw = path.read_text(encoding="utf-8")
    unquoted = re.sub(r"(?m)^\s*>\s?", "", raw)
    return re.sub(r"\s+", " ", unquoted)


AGENT_FACING_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".sh"}


def _agent_facing_md() -> list[Path]:
    """Every file an executing agent can load at runtime, whatever its extension.

    Rooted at the plugin, not at a hand-listed set of directories: the two sites this change
    had to correct - `README.md` at the plugin root and `generator/skill_tool_deps.json` - sit
    outside any such list, so a directory-scoped sweep would have passed while the stale claim
    was still shipping. Workflows are YAML and evals are JSON, so extension scoping matters too.
    """
    return sorted(
        p
        for p in PLUGIN.rglob("*")
        if p.is_file() and p.suffix in AGENT_FACING_SUFFIXES and ".git" not in p.parts
    )


# --- (1) lint-class gate membership -----------------------------------------------------


def test_pivots_states_the_lint_module_name_per_series():
    """The Viindoo lint module is named differently below and above the rename boundary.

    Tagging the wrong name selects nothing and installs nothing, and the run still passes.
    """
    text = _norm(PIVOTS)
    assert "test_viin_pylint" in text, "pivots must name the current Viindoo lint module"
    assert "test_pylint" in text, "pivots must name the earlier Viindoo lint module"
    # Assert the BOUNDARY holds, not the literal range strings this same commit wrote: a range
    # spelled wrong would satisfy a string match while sending every build to the wrong module.
    # Each name must carry a bound, and the two bounds must not overlap.
    current = re.search(r"`test_viin_pylint`[^|]*\|[^|]*\|\s*v(\d+)\+", text)
    assert current, "the current name's row must give a `vN+` lower bound"
    earlier = re.search(r"`test_pylint`[^|]*\|[^|]*\|\s*v(\d+)(?:-v(\d+))? ONLY", text)
    assert earlier, "the earlier name's row must give an explicit `ONLY` series bound"
    earlier_high = int(earlier.group(2) or earlier.group(1))
    assert earlier_high < int(current.group(1)), (
        f"the two Viindoo lint names must not overlap: earlier covers up to v{earlier_high}, "
        f"current starts at v{current.group(1)}"
    )


def test_pivots_forbids_installing_both_viindoo_lint_names():
    """They are ONE gate under two names - both in one build is a defect, not redundancy."""
    text = _norm(PIVOTS)
    assert "never install or tag both" in text.lower(), (
        "pivots must forbid carrying both Viindoo lint names into one build"
    )


def test_lint_gate_snippet_owns_the_candidate_set_and_the_stale_index_rule():
    """The probe alone cannot prove presence - a stale index answers Yes for a dead name."""
    text = _norm(LINT_GATE)
    for module in ("test_lint", "test_pylint", "test_viin_pylint"):
        assert module in text, f"lint-gate snippet must list {module} as a candidate"
    assert "stale" in text.lower(), "lint-gate snippet must state the index can be stale"
    assert "FALSE GREEN" in text, (
        "lint-gate snippet must name the false-green outcome a stale probe produces"
    )
    assert "tests-inconclusive" in text, (
        "a tagged module whose tests never loaded must be inconclusive, never a pass"
    )


def test_no_file_restates_a_stale_lint_module_version_claim():
    """A consumer that spells the version range grows its own copy, and that copy rots.

    This is the sweep that caught the original defect: the rename landed and eighteen
    restatements kept naming the old module for the new series.
    """
    offenders = []
    for path in _agent_facing_md():
        if path.name in {"odoo-version-pivots.md", "lint-gate-modules.md"}:
            continue
        text = _norm(path)
        # Match EITHER Viindoo lint name near a version token, in either order, and do not let a
        # period end the window: the original defect was written as "... module (v16+). **Full"
        # and a period-terminated window would have skipped it.
        if re.search(r"test_(?:viin_)?pylint.{0,90}?\bv\d\d\b", text) or re.search(
            r"\bv\d\d\b\+?.{0,60}?test_(?:viin_)?pylint", text
        ):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "these files restate which series carries which lint module instead of pointing at "
        f"snippets/odoo-version-pivots.md: {offenders}"
    )


# --- (2) server-wide modules on --load --------------------------------------------------


def test_pivots_states_every_server_wide_load_set():
    """One row per era, each giving the WHOLE resulting --load, not a fragment to append to."""
    text = _norm(PIVOTS)
    for expected in (
        "web,to_base",
        "base,web,to_base",
        "base,web,to_erponline_utility,viin_brand",
        "base,rpc,web,to_erponline_utility,viin_brand",
    ):
        assert expected in text, f"pivots must state the resulting --load `{expected}`"


def test_pivots_warns_that_rpc_is_dropped_when_omitted():
    """Odoo re-adds base and web but not rpc, so a carried-forward set loses it silently."""
    text = _norm(PIVOTS)
    assert "rpc" in text, "pivots must name the addon that is not re-added"
    assert "silently" in text.lower() or "no error" in text.lower(), (
        "pivots must state that omitting it fails silently rather than erroring"
    )


def test_pivots_states_to_base_leaves_the_server_wide_set():
    """It remains installable, so 'the module resolves' is not evidence it still belongs."""
    text = _norm(PIVOTS)
    assert "to_base" in text and "SERVER-WIDE set at v18" in text, (
        "pivots must state that to_base leaves the server-wide set, not the addons path"
    )


def test_agent_refuses_a_partially_present_server_wide_set():
    """A half-applied server-wide set boots a registry unlike every other build, silently."""
    text = _norm(AGENT_MD)
    assert "Some Yes, some No" in text, (
        "the agent must handle a partially-present Viindoo server-wide set explicitly"
    )
    assert "Never build a partial `--load`" in text, (
        "the agent must refuse a partial --load rather than proceed with it"
    )


# --- (3) demo data by build purpose -----------------------------------------------------


def test_pivots_states_demo_by_build_purpose():
    """Which purposes carry demo is the decision; the flag spelling only expresses it."""
    text = _norm(PIVOTS)
    assert "Demo data by build PURPOSE" in text, (
        "pivots must carry the purpose-keyed demo section"
    )
    assert "GATE_ROLE: node-verify" in text and "GATE_ROLE: pre-pr-lint-gate" in text, (
        "the automation-test row must name both gate roles, so neither is read as an exception"
    )


def test_pivots_forbids_demo_dependent_tests_where_demo_is_off():
    """A test authored on a demo-carrying instance still runs demo-less in the gate later."""
    text = _norm(PIVOTS)
    assert "setUpClass" in text, (
        "pivots must tell a test author to create its own records"
    )
    assert "MUST NOT reference a demo record" in text, (
        "pivots must forbid referencing a demo record from a durable test"
    )


def test_agent_refuses_demo_on_an_automation_test_build():
    """The test environment does not accept demo, so the request is an error, not a preference."""
    text = _norm(AGENT_MD)
    assert "Demo data on a build (HARD RULE)" in text, (
        "the agent must own a demo HARD RULE section"
    )
    assert "demo requested on an automation-test build" in text, (
        "the agent must refuse demo on a test build with a NEEDS_CONTEXT reason"
    )


def test_no_file_spells_the_demo_enable_flag_with_a_value():
    """`--with-demo` takes no value - a `=<value>` form dies at option parsing (issue #252).

    The prose stated this correctly while the copy-paste template a few hundred lines below
    contradicted it, so the sweep covers every agent-facing file rather than that one section.
    """
    offenders = []
    for path in _agent_facing_md():
        if "--with-demo=" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "`--with-demo` takes no value; these files spell it with one and would fail at "
        f"option parsing: {offenders}"
    )
