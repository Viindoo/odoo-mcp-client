"""Behavioral guards for the lint-class CHECKER-LOAD COVERAGE axis.

Root cause (owner report): a real `test_pylint` run can load 0 of N of its own custom checkers
(one of them the SQL-injection checker) - e.g. loading 32 of 56 checks total - while the process
still exits 0 with zero FAIL:/ERROR:/WARNING/skip lines. `agents/odoo-instance-ops.md`'s
`run-tests` Verdict contract (pre-fix) derived `status` ENTIRELY from those four counters
(`failed`/`errors`/`skipped`/`warnings`) - a checker that never LOADED produces none of them (not
a failure: it never ran: not a skip: it is not a test: not a warning: nothing objected), so the
ladder silently resolved a coverage shortfall to `tests-passed`, the ONE verdict the contract's
own text describes as "the only verdict that lets the caller proceed with nothing to address".

Confirmed pre-fix (zero hits across the whole scope): grepping `checker`, `checks run`,
`custom check`, and `sql inject` in `agents/odoo-instance-ops.md`, `skills/odoo-instance/SKILL.md`,
and `skills/run-harness/references/run-integration.md` (formerly `wave-integration.md`, renamed
when the wave grouping layer was removed) returned nothing - there was no coverage axis anywhere
in the contract.

Grounding for the fix's shape: this repo's OWN SSOT docs (`docs/reference/ODOO-TESTING.md`,
`docs/reference/odoo-code-quality.md`) already state that OSM's `lint_check` does NOT reproduce
"the full Odoo AST checker set" and that `test_lint`/`test_pylint`'s own reporting is
Odoo/Viindoo framework-internal, not indexed by OSM. There is no documented, version-stable
literal string for "N of M checks ran" anywhere in this repo or reachable via the Odoo Semantic
MCP (a STATIC structural index, not a runtime-log corpus) - so the fix does NOT hardcode a parser
for one assumed phrasing. Instead it requires the agent to read THIS run's own log for a positive
per-module coverage confirmation and fails CLOSED (escalates, never defaults to a pass) when no
such confirmation is found, mirroring the `_install_confirmed` "absence of a positive signal
escalates" discipline this same file already applies to init/update builds (`Modules loaded.`).

The fix reuses the existing `tests-inconclusive` status (widened definition: "not proof the suite
ran clean" now explicitly covers "ran, but checked less than it should have") rather than adding a
fifth status - the caller-facing contract for that status ("MUST NOT treat this as a verified
pass... without a human reviewing findings_path first") already says the right thing. The axis is
scoped to `GATE_ROLE: pre-pr-lint-gate` only (the ONE dispatch that installs+tags the lint modules
at all, per the pre-existing HARD RULE) - `node-verify` (renamed from `per-module-verify` when the
wave grouping layer was removed - the per-module unit became the per-node unit) never installs
them, so there is nothing to check coverage on there; this composes with, and does not duplicate or
contradict, the existing GATE_ROLE mechanism.

A second, related gap: `skills/run-harness/references/run-integration.md`'s pre-PR lint-class gate
containment loop (the ONE place a `tests-inconclusive` verdict from this ONE gate actually needs to
be ACTED on, since there is no later gate to catch it) pre-fix only reacted to "a FAILURE" - an
`inconclusive` verdict (skip-only OR the new coverage-shortfall reason) had no wired reaction at
all in an unattended `--auto` drive-to-done run, so the verdict-level fix would have been toothless
at the one site it matters most. Fixed together (same mechanism, same trigger value - not scope
creep).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

AGENT_MD = PLUGIN / "agents" / "odoo-instance-ops.md"
SKILL_MD = PLUGIN / "skills" / "odoo-instance" / "SKILL.md"
RUN_INTEGRATION = PLUGIN / "skills" / "run-harness" / "references" / "run-integration.md"


def _read(p: Path) -> str:
    assert p.exists(), f"expected file missing: {p}"
    return p.read_text(encoding="utf-8")


def _norm(p: Path) -> str:
    """Whitespace-normalized, lowercased text so a phrase check survives line-wrapping."""
    return re.sub(r"\s+", " ", _read(p)).lower()


def _section(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    assert start != -1, f"start marker not found: {start_marker!r}"
    end = text.find(end_marker, start)
    assert end != -1, f"end marker not found after start: {end_marker!r}"
    return text[start:end]


# ---------------------------------------------------------------------------
# Pre-fix baseline (documents the confirmed gap; not a live assertion against
# the fixed tree - kept as a citable, re-runnable measurement).
# ---------------------------------------------------------------------------


def test_baseline_measurement_zero_coverage_hits_is_recorded_accurately():
    """Sanity-check the docstring's own claim stays true to what a fresh grep finds TODAY on the
    fixed tree for the ORIGINAL narrow terms (checker/pylint/sql inject as bare words) - it should
    now be non-zero (the fix adds them), proving the axis really landed in the contract rather than
    only in this test file.
    """
    combined = "\n".join(
        _read(p) for p in (AGENT_MD, SKILL_MD, RUN_INTEGRATION)
    ).lower()
    assert "checker" in combined, (
        "no file in scope mentions 'checker' at all - the coverage axis did not land."
    )


# ---------------------------------------------------------------------------
# A. The Verdict contract gains a decidable checker-load coverage axis
# ---------------------------------------------------------------------------


def test_agent_verdict_contract_states_a_checker_load_coverage_axis():
    """Behavior protected: the run-tests Verdict contract in agents/odoo-instance-ops.md must name
    the FAILURE MODE this axis exists to catch - a checker that fails to LOAD produces none of
    failed/errors/skipped/warnings - not just add an unrelated mention of the word 'checker'.
    """
    text = _norm(AGENT_MD)
    assert "fail" in text and "load" in text, "must discuss checker load failure"
    assert (
        "fails to load" in text or "fail to load" in text or "failed to load" in text
    ), "must name the exact failure mode: a checker that fails to LOAD"
    assert "not a failure" in text or "never ran" in text, (
        "must explain WHY the existing four-branch ladder is blind to this: a checker that never "
        "ran is not a failure, not a skip, not a warning."
    )


def test_agent_verdict_contract_never_lets_a_clean_zero_count_shortcut_the_check():
    """Behavior protected: the defect's exact shape - failed=errors=skipped=warnings=0 must NOT be
    treated as automatic proof of a clean lint-class run once the coverage axis applies. The prose
    must explicitly disclaim this shortcut, not just describe the axis in the abstract.
    """
    text = _norm(AGENT_MD)
    assert "0/0/0/0" in text or (
        "genuine" in text and ("0" in text)
    ), (
        "the contract must explicitly call out that even all-zero counters do not prove coverage "
        "- otherwise an implementer could read the four-branch ladder as still sufficient."
    )


def test_agent_verdict_contract_scopes_coverage_check_to_pre_pr_lint_gate_only():
    """Behavior protected: the coverage axis must be scoped to GATE_ROLE: pre-pr-lint-gate - the
    ONE dispatch that installs+tags the lint modules at all - and explicitly say a node-verify
    dispatch has nothing to check (composing with, not duplicating, the existing GATE_ROLE
    mechanism from agents/odoo-instance-ops.md "Lint modules" HARD RULE). `node-verify` is the
    renamed non-lint GATE_ROLE value (formerly `per-module-verify`, before the wave grouping layer
    was removed) - the scoping behavior is unchanged, only the value's name.
    """
    text = _norm(AGENT_MD)
    assert "gate_role: pre-pr-lint-gate" in text, (
        "the coverage axis must name GATE_ROLE: pre-pr-lint-gate as its trigger condition."
    )
    assert "node-verify" in text and (
        "nothing to check" in text or "never installs" in text or "does not install" in text
    ), (
        "the coverage axis must explicitly state that a node-verify dispatch has nothing to "
        "check coverage on (it never installs the lint modules), not leave the boundary implicit."
    )


def test_agent_verdict_contract_fails_closed_on_an_unconfirmable_log():
    """Behavior protected (OBJECTIVE point 4 - fail closed): when the log carries NO explicit
    per-module coverage statement at all, that must NOT be treated as a pass by default - silence
    is itself the finding, mirroring the `_install_confirmed` "absence of a positive signal
    escalates" discipline already established in this file for init/update builds.
    """
    text = _norm(AGENT_MD)
    assert "unconfirmed" in text, (
        "the contract must name the fail-closed outcome (coverage UNCONFIRMED) for a log with no "
        "explicit coverage statement at all - never silently assume clean."
    )
    assert "silence" in text or "absence of a positive" in text or "never treated as proof" in text, (
        "the contract must explicitly disclaim treating a silent/uninformative log as proof of a "
        "clean run - the fail-closed half of the fix."
    )


def test_agent_verdict_contract_does_not_hardcode_a_specific_log_phrase():
    """Behavior protected (OBJECTIVE point 1 - do not design the parser from imagination): the fix
    must NOT assert a fixed 'N of M checks' string as if it were a confirmed, version-stable Odoo
    log format - no source in this repo (nor OSM, a static structural index) grounds that literal
    phrasing. The contract must instead say the wording is a live-log fact to be read per-run.
    """
    raw = _read(AGENT_MD)
    assert "N of M checks" not in raw and "n of m checks" not in raw.lower(), (
        "the fix must not hardcode the report's illustrative 'N of M checks' phrasing as if it "
        "were a confirmed, version-stable Odoo log format."
    )
    text = _norm(AGENT_MD)
    assert "live-log fact" in text or "this run's" in text or "this run actually" in text, (
        "the contract must say the exact coverage wording is a fact of THIS run's own log, not a "
        "fixed phrase assumed from memory."
    )


def test_agent_verdict_contract_maps_coverage_gap_to_tests_inconclusive_not_a_fifth_status():
    """Behavior protected (OBJECTIVE point 5): the fix reuses `tests-inconclusive` (widened
    definition) rather than inventing a fifth status - the canonical output-block enum must still
    list exactly the same four test-verdict values it did before the fix.
    """
    raw = _read(AGENT_MD)
    text = _norm(AGENT_MD)
    assert "tests-inconclusive" in text, "the coverage gap must resolve into the existing tests-inconclusive status."
    # The canonical output block's status enum (grep for the literal enum line) must not have
    # grown a new test-verdict token beyond the pre-existing four.
    enum_lines = [
        line for line in raw.splitlines()
        if "tests-passed" in line and "status:" in line
    ]
    assert enum_lines, "could not locate the canonical output block's status enum line"
    for line in enum_lines:
        for forbidden in ("tests-coverage", "tests-uncovered", "tests-checker-failed", "coverage-failed"):
            assert forbidden not in line, (
                f"a fifth test-verdict status leaked into the canonical enum: {forbidden!r} in {line!r}"
            )


def test_agent_verdict_contract_widens_tests_inconclusive_definition_explicitly():
    """Behavior protected: the pre-existing tests-inconclusive bullet ("not proof the suite ran
    clean") must be explicitly extended to also cover the coverage gap, not merely have a second,
    disconnected paragraph nearby that a reader could miss links to the SAME status value.
    """
    text = _norm(AGENT_MD)
    assert "checked less than it should have" in text or "widen" in text or "widens" in text, (
        "the fix must explicitly say it widens/extends tests-inconclusive's existing definition to "
        "cover the coverage gap, connecting the two rather than leaving two disconnected rules for "
        "the same status value."
    )


# ---------------------------------------------------------------------------
# B. skills/odoo-instance/SKILL.md cross-references the new axis (SSOT pointer, no restatement)
# ---------------------------------------------------------------------------


def test_skill_cross_references_the_coverage_axis_without_restating_it():
    """Behavior protected: the front-door skill must point at the new Verdict-contract coverage
    axis from its existing "Lint modules for run-tests - GATED" paragraph (discoverability for a
    reader who only opens the skill), without duplicating the decidable rule itself (SSOT stays in
    the agent file, matching this repo's own convention for every other HARD RULE).
    """
    text = _norm(SKILL_MD)
    assert "coverage" in text, (
        "skills/odoo-instance/SKILL.md must mention the coverage axis so a reader of the front "
        "door discovers it exists."
    )
    assert "odoo-instance-ops.md" in _read(SKILL_MD), (
        "the skill must point at agents/odoo-instance-ops.md as the coverage rule's SSOT, not "
        "restate the decidable rule inline."
    )


# ---------------------------------------------------------------------------
# C. The pre-PR lint-class gate containment loop reacts to inconclusive, not only FAILURE
# ---------------------------------------------------------------------------


def test_pre_pr_lint_gate_containment_reacts_to_inconclusive_not_only_failure():
    """Behavior protected: the pre-PR lint-class gate's containment loop (the ONE consumer of this
    verdict that matters, since there is no later gate to catch a miss) must react the same way to
    a `tests-inconclusive` verdict (skip-only OR the new coverage-shortfall reason) as it does to a
    `tests-failed` verdict - otherwise the verdict-level fix is toothless in an unattended --auto
    drive-to-done run, where nothing else is guaranteed to perform the "human review" the
    tests-inconclusive contract text demands.

    Fails if the containment loop's trigger condition still reads as FAILURE-only.
    """
    text = _read(RUN_INTEGRATION)
    section = _section(
        text,
        "**Containment for tail-only lint",
        "**4 - Terminal land-tail PR",
    )
    norm = re.sub(r"\s+", " ", section).lower()
    assert "inconclusive" in norm, (
        "the containment loop must explicitly name `tests-inconclusive` as a trigger, not only "
        "`tests-failed` - a coverage-shortfall or skip-only result must not silently pass through "
        "the pre-PR gate."
    )
    assert "coverage" in norm, (
        "the containment loop must explicitly connect to the coverage-shortfall reason (not just "
        "the pre-existing skip-only inconclusive case), so a reader sees both trigger this loop."
    )


def test_pre_pr_lint_gate_declares_gate_role_still_intact():
    """Regression guard: confirm the pre-existing GATE_ROLE: pre-pr-lint-gate statement (fixed by
    an earlier round) survives this change untouched - the new coverage axis composes with it, it
    does not replace or duplicate it.
    """
    text = _read(RUN_INTEGRATION)
    section = _section(
        text,
        "**3 - Pre-PR lint-class gate",
        "**4 - Terminal land-tail PR",
    )
    norm = re.sub(r"\s+", " ", section).lower()
    assert "gate_role: pre-pr-lint-gate" in norm


# ---------------------------------------------------------------------------
# D. Class sweep - the pre-existing "positive marker required, exit 0 alone is not proof" pattern
# for init/update/create stays intact (a targeted regression guard, not a fragile generic sweep -
# a broad regex-based "no exit-0-alone claim anywhere" scan was tried and dropped: it false-
# positived on this file's OWN correct disclaiming sentences whenever a mid-sentence period inside
# a backticked token - e.g. "Modules loaded." - truncated the match before the disclaimer clause,
# which would have made the guard's own blind spot the thing under test. The manual sweep across
# the three in-scope files (run-tests Verdict contract, ensure-up/status exit-code check,
# load-language activation-verify, init/update/create _install_confirmed marker logic, and the
# run-integration.md eslint tri-state reference) found exactly ONE counter-only gate with no
# coverage signal at all: run-tests. The other five already require a positive confirmation signal
# or already degrade to a non-pass (CANNOT-VERIFY / log-signal-not-live-verified) rather than
# trusting exit 0 / a clean counter set alone - see the fix report for the full per-gate note).
# ---------------------------------------------------------------------------


def test_init_update_positive_marker_discipline_is_unweakened_by_this_change():
    """Regression guard: confirm the pre-existing 'exit 0 ALONE is NOT proof of install' disclaimer
    for init/update/create-instance survives this change verbatim - the coverage fix must compose
    with, not weaken, the one positive-confirmation discipline this file already had.
    """
    text = _norm(AGENT_MD)
    assert "exit 0 alone is not proof of a successful build" in text, (
        "the pre-existing 'exit 0 ALONE is NOT proof of a successful build' disclaimer for "
        "init/update must still be present - this fix must not weaken that unrelated, "
        "already-correct discipline."
    )
