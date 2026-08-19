"""Self-check for the [wait-scope] / [wait-mechanism] detectors (M1 guard, rules 9/10 in
generator/check_orchestration.py).

Ground truth these detectors protect (see R0, spawner-completion-contract.md): no blocking or
foreground launch parameter exists in this harness, so EVERY launch is asynchronous, and
"launch, then END YOUR TURN and be woken with the child's result" is the ONE collection mechanism.
It holds at every depth - a nested launcher is woken by its own child exactly as the root is - and
its only precondition is the launcher's own: it must actually stop.

Two retired premises this docstring has now outlived, both named so neither grows back:
`run_in_background: false` is NOT a blocking lever (the citation regex below no longer accepts that
token as R0-branch attribution), and "only the ROOT conversation is ever resumed" is NOT true (the
transcript corpus shows nested launchers woken repeatedly, at depth 3).

Neither detector keys on WHO is parking (they are proximity and citation checks, not semantic
reads); what they catch is a park nobody can attribute to an R0 branch, and work left uncommitted
across the turn boundary. The hazards:

  [wait-scope]  - a park/wait instruction whose section (a) names no R0 branch (no citation of
                  which R0 move it exercises), or (b) shows file-writing language
                  with no stated commit/checkpoint safeguard (risking uncommitted work surviving a
                  turn boundary - R0's own non-interactive-surface bound).
  [wait-mechanism] - (a) an instruction to poll/sleep while waiting for a child (never correct
                  under any R0 branch - the launcher ends its turn and is woken instead),
                  excluding a sanctioned check of the agent's OWN task list; (b) a dispatch claim
                  (launch/dispatch/invoke the Agent tool) with no nearby capability-handling
                  language (R0 move 1 requires checking your own toolset FIRST).

This file does NOT scan the real plugin tree for correctness (that is what running
check_orchestration.py itself does, exercised separately in CI and by
test_wait_mechanism_is_warn_only_never_gates_strict_exit below). It proves the DETECTOR LOGIC
ITSELF is capable of going both RED (flags a genuinely dangerous instruction) and GREEN (clears a
properly attributed/safeguarded one) on synthetic fixtures - red-before-green. A detector that can
only ever say "clean" is worthless; these tests prove it can actually fire, and that it fires for
the CORRECTED reason, not the retired false-premise one.

Both rules ship WARN-FIRST for one release (see check_orchestration.py's module docstring): their
findings never gate `--strict`. This file tests the DETECTION logic only, not the exit-code
wiring beyond the one sanity test that exercises the real main() end to end.

Run: python -m pytest tests/test_wait_contract_scope.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from generator.check_orchestration import (  # noqa: E402
    check_wait_scope,
    check_wait_mechanism,
    _wait_instructions,
)


# ---------------------------------------------------------------------------
# [wait-scope] (a) - R0-branch attribution: red when missing, green once cited
# ---------------------------------------------------------------------------


def test_wait_scope_flags_a_park_instruction_that_names_no_r0_branch():
    """RED: a park-the-turn instruction near turn/child/worker/agent vocabulary, with no citation
    of which R0 branch it belongs to (no R0/move-N/NEEDS_NEXT/nesting-cap/
    spawner-completion-contract.md mention anywhere in its section), must be a finding - a reader
    cannot tell whether this is the async launch-and-be-woken branch or the no-capability one."""
    text = (
        "## Some ordinary section\n\n"
        "Once you have dispatched the worker agent, end the turn and wait to be resumed when it "
        "completes.\n"
    )
    findings: list[str] = []
    _drive_over_text(check_wait_scope, text, findings)
    assert any("names no R0 branch" in f for f in findings), (
        "check_wait_scope must flag a park instruction whose section names no R0 branch"
    )


def test_wait_scope_clears_the_same_instruction_once_it_cites_an_r0_branch():
    """GREEN: the identical instruction, with an R0 branch citation in the same section (here,
    'R0 move 3'), must clear the R0-branch-attribution check - proving the detector's citation
    check actually discriminates, not merely flags everything."""
    text = (
        "## Some ordinary section\n\n"
        "Per R0 move 3, once you have dispatched the worker agent, commit your work, then end "
        "the turn and wait to be resumed when it completes.\n"
    )
    findings: list[str] = []
    _drive_over_text(check_wait_scope, text, findings)
    assert not any("names no R0 branch" in f for f in findings), (
        "check_wait_scope must NOT flag a park instruction whose section cites an R0 branch"
    )


def test_wait_scope_accepts_spawner_completion_contract_citation_as_r0_attribution():
    """GREEN (alternate route): citing spawner-completion-contract.md in the same section is
    sufficient R0-branch attribution too - the detector accepts any of several citation forms."""
    text = (
        "## Some ordinary section\n\n"
        "See spawner-completion-contract.md for the physics. Once you have dispatched the "
        "worker agent, end the turn and wait to be resumed when it completes.\n"
    )
    findings: list[str] = []
    _drive_over_text(check_wait_scope, text, findings)
    assert not any("names no R0 branch" in f for f in findings), (
        "check_wait_scope must accept a spawner-completion-contract.md citation as sufficient "
        "R0-branch attribution"
    )


# ---------------------------------------------------------------------------
# [wait-scope] (b) - uncommitted-work bound: red when writing with no safeguard, green once stated
# ---------------------------------------------------------------------------


def test_wait_scope_flags_a_park_instruction_in_a_writing_section_with_no_commit_safeguard():
    """RED: a park instruction whose section shows file-writing language (write/author/edit) but
    states no commit/checkpoint safeguard risks uncommitted work surviving a turn boundary - the
    exact non-interactive-surface hazard R0 itself names."""
    text = (
        "## Author the change\n\n"
        "Write the implementation files, then dispatch the worker agent and end your turn to "
        "wait to be resumed.\n"
    )
    findings: list[str] = []
    _drive_over_text(check_wait_scope, text, findings)
    assert any("no stated commit/checkpoint safeguard" in f for f in findings), (
        "check_wait_scope must flag a writing section with a park instruction and no commit "
        "safeguard"
    )


def test_wait_scope_clears_the_same_section_once_a_commit_safeguard_is_stated():
    """GREEN: the identical section, with a commit/checkpoint safeguard stated, must clear -
    proving the write-context check discriminates on the safeguard, not just on the writing verb."""
    text = (
        "## Author the change\n\n"
        "Write the implementation files, commit your work via git-ops, then dispatch the worker "
        "agent and end your turn to wait to be resumed.\n"
    )
    findings: list[str] = []
    _drive_over_text(check_wait_scope, text, findings)
    assert not any("no stated commit/checkpoint safeguard" in f for f in findings), (
        "check_wait_scope must NOT flag a writing section that states a commit safeguard"
    )


def test_wait_scope_ignores_a_wait_verb_far_from_turn_child_worker_agent_vocabulary():
    """A bare 'await' with no turn/child/worker/agent vocabulary nearby (e.g. 'await user
    confirmation before deleting') is not a spawner-completion concern and must not be flagged -
    this proves the proximity gate `_wait_instructions` applies is load-bearing, not decorative."""
    text = (
        "## Destructive op\n\n"
        "Always await explicit human confirmation before running a force-push.\n"
    )
    findings: list[str] = []
    _drive_over_text(check_wait_scope, text, findings)
    assert not findings, (
        "check_wait_scope must not flag a wait verb with no turn/child/worker/agent vocabulary "
        "in its proximity window"
    )


def _drive_over_text(check_fn, text: str, out: list[str], filename: str = "synthetic.md") -> None:
    """Exercise a wait-scope-family check function against synthetic text without touching disk,
    by monkeypatching the scan-file list to a single in-memory-backed path. Since both
    check_wait_scope and check_wait_mechanism take `_wait_scope_scan_files()`'s output as their
    file list, this drives the REAL function body, not a re-derivation of its logic."""
    import tempfile
    import generator.check_orchestration as co

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        snippet_dir = tmp_path / "snippets"
        skills_dir = tmp_path / "skills"
        agents_dir = tmp_path / "agents"
        snippet_dir.mkdir()
        skills_dir.mkdir()
        agents_dir.mkdir()
        (snippet_dir / filename).write_text(text, encoding="utf-8")

        orig_snippets, orig_skills, orig_agents, orig_root = (
            co.SNIPPETS_DIR, co.SKILLS_DIR, co.AGENTS_DIR, co.PLUGIN_ROOT,
        )
        co.SNIPPETS_DIR, co.SKILLS_DIR, co.AGENTS_DIR, co.PLUGIN_ROOT = (
            snippet_dir, skills_dir, agents_dir, tmp_path,
        )
        try:
            check_fn(out)
        finally:
            co.SNIPPETS_DIR, co.SKILLS_DIR, co.AGENTS_DIR, co.PLUGIN_ROOT = (
                orig_snippets, orig_skills, orig_agents, orig_root,
            )


def test_pass_a_and_pass_b_run_clean_against_the_real_ssot_files_that_are_fully_scoped():
    """Sanity: running the real, disk-backed checks against the actual plugin tree must not raise.
    Also: the R0 SSOT itself (spawner-completion-contract.md) must produce ZERO findings from
    either detector - it cites its own branch inline at every park/wait instruction and states a
    commit safeguard, so it is the reference example of a fully-attributed, fully-safeguarded
    file."""
    findings: list[str] = []
    check_wait_scope(findings)
    check_wait_mechanism(findings)
    assert isinstance(findings, list)
    # Match the FLAGGED FILE (the token right after the "[tag] " prefix), not a mere mention of
    # "spawner-completion-contract.md" inside another finding's explanatory text (every [wait-scope]
    # message names it as one of the acceptable citation forms, which would false-positive a bare
    # substring check).
    ssot_findings = [f for f in findings if "snippets/spawner-completion-contract.md:" in f]
    assert not ssot_findings, (
        f"the R0 SSOT itself must be fully attributed and safeguarded, found: {ssot_findings}"
    )


# ---------------------------------------------------------------------------
# [wait-mechanism] (a) - poll/sleep near wait-for-a-child vocabulary
# ---------------------------------------------------------------------------


def test_wait_mechanism_flags_poll_near_wait_for_a_child_vocabulary(tmp_path, monkeypatch):
    """RED: an instruction to poll while waiting for a dispatched child - never correct under any
    R0 branch (the launcher ends its turn and the harness wakes it with the result)."""
    import generator.check_orchestration as co

    snippet_dir = tmp_path / "snippets"
    skills_dir = tmp_path / "skills"
    agents_dir = tmp_path / "agents"
    snippet_dir.mkdir()
    skills_dir.mkdir()
    agents_dir.mkdir()
    (snippet_dir / "synthetic.md").write_text(
        "## Dispatch\n"
        "Launch the worker agent now.\n"
        "Poll for the child agent to finish in a loop.\n"
        "Then end your turn.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(co, "SNIPPETS_DIR", snippet_dir)
    monkeypatch.setattr(co, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(co, "AGENTS_DIR", agents_dir)
    monkeypatch.setattr(co, "PLUGIN_ROOT", tmp_path)

    findings: list[str] = []
    co.check_wait_mechanism(findings)
    assert any(
        "wait-mechanism" in f and "synthetic.md" in f and "polling" in f for f in findings
    ), "check_wait_mechanism must flag a poll instruction near wait-for-a-child vocabulary"


def test_wait_mechanism_clears_poll_when_negated():
    """GREEN: 'never poll' / 'do not poll' is a PROHIBITION, not an instruction to poll - the
    negation lookback must suppress it, proving the detector distinguishes a ban from a command."""
    text = (
        "## Dispatch\n"
        "Launch the worker agent now, then end your turn.\n"
        "Never poll or sleep while waiting for the child agent - you will be resumed.\n"
    )
    findings: list[str] = []
    _drive_over_text(check_wait_mechanism, text, findings)
    assert not any("instructs polling" in f for f in findings), (
        "check_wait_mechanism must not flag a negated ('never poll') instruction"
    )


def test_wait_mechanism_clears_the_sanctioned_task_list_status_check():
    """GREEN: periodically checking your own live task list is a DIFFERENT, sanctioned pattern -
    status tracking, not a busy-wait loop standing in for the mechanical barrier - and must not be
    flagged. The check is tool-agnostic by design, so the exemption keys on the task-list CONCEPT,
    never on a specific tool name."""
    text = (
        "## Progress tracking\n\n"
        "Poll your own live task list to track each dispatched worker agent's status on the "
        "task list you keep.\n"
    )
    findings: list[str] = []
    _drive_over_text(check_wait_mechanism, text, findings)
    assert not any("instructs polling" in f for f in findings), (
        "check_wait_mechanism must not flag a sanctioned check of the agent's own task list"
    )


def test_wait_mechanism_ignores_poll_far_from_wait_for_a_child_vocabulary():
    """A bare 'poll' with no turn/child/worker/agent vocabulary nearby (e.g. polling a log file
    unrelated to any agent) must not be flagged - proximity gate is load-bearing."""
    text = (
        "## Log tail\n\n"
        "Poll the build output file for a completion marker every few seconds.\n"
    )
    findings: list[str] = []
    _drive_over_text(check_wait_mechanism, text, findings)
    assert not any("instructs polling" in f for f in findings), (
        "check_wait_mechanism must not flag a poll instruction with no wait-for-a-child "
        "vocabulary nearby"
    )


# ---------------------------------------------------------------------------
# [wait-mechanism] (b) - a dispatch claim with no nearby capability-handling language
# ---------------------------------------------------------------------------


def test_wait_mechanism_flags_a_dispatch_claim_with_no_capability_handling(tmp_path, monkeypatch):
    """RED: a claim that a dispatch happened (launch/dispatch/invoke the Agent tool), with no
    nearby capability-handling language, reads as though the Agent tool is always assumed present
    - R0 move 1 requires checking your own toolset FIRST."""
    import generator.check_orchestration as co

    snippet_dir = tmp_path / "snippets"
    skills_dir = tmp_path / "skills"
    agents_dir = tmp_path / "agents"
    snippet_dir.mkdir()
    skills_dir.mkdir()
    agents_dir.mkdir()
    (snippet_dir / "synthetic.md").write_text(
        "## Dispatch\n"
        "Launch the worker agent now to handle the change.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(co, "SNIPPETS_DIR", snippet_dir)
    monkeypatch.setattr(co, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(co, "AGENTS_DIR", agents_dir)
    monkeypatch.setattr(co, "PLUGIN_ROOT", tmp_path)

    findings: list[str] = []
    co.check_wait_mechanism(findings)
    assert any(
        "wait-mechanism" in f and "synthetic.md" in f and "claims a dispatch" in f
        for f in findings
    ), "check_wait_mechanism must flag a dispatch claim with no nearby capability-handling language"


def test_wait_mechanism_clears_a_dispatch_claim_that_names_capability_handling():
    """GREEN: the identical claim, with capability-handling language (here, 'own toolset') stated
    nearby, must clear - proving the detector's proximity check on cap-handling discriminates."""
    text = (
        "## Dispatch\n\n"
        "Check your own toolset first (R0 move 1). If the Agent tool is present, launch the "
        "worker agent now to handle the change.\n"
    )
    findings: list[str] = []
    _drive_over_text(check_wait_mechanism, text, findings)
    assert not any("claims a dispatch" in f for f in findings), (
        "check_wait_mechanism must NOT flag a dispatch claim with capability-handling language "
        "stated nearby"
    )


def test_wait_mechanism_clears_a_negated_dispatch_claim():
    """GREEN: 'does not launch the X agent' is a self-declared leaf statement, not a dispatch
    claim - the negation lookback must suppress it."""
    text = (
        "## Leaf behavior\n\n"
        "This worker does not launch the coder agent - it is a HARD LEAF.\n"
    )
    findings: list[str] = []
    _drive_over_text(check_wait_mechanism, text, findings)
    assert not any("claims a dispatch" in f for f in findings), (
        "check_wait_mechanism must not flag a negated dispatch statement"
    )


# ---------------------------------------------------------------------------
# Sanity: _wait_instructions proximity gate is still shared/reused (not re-derived per test)
# ---------------------------------------------------------------------------


def test_wait_instructions_helper_is_the_one_both_checks_share():
    """Both check_wait_scope's R0-branch/commit-safeguard logic reuse the SAME `_wait_instructions`
    proximity gate - confirmed by checking it yields the expected (match, heading, section_text)
    shape directly, so the synthetic fixtures above are exercising real shared plumbing."""
    text = "## H\n\nDispatch the worker agent, then end the turn.\n"
    results = list(_wait_instructions(text))
    assert results, "_wait_instructions must yield at least one match for a park verb near agent vocabulary"
    m, heading, section_text = results[0]
    assert heading == "H"
    assert m.group().lower() in ("end the turn",)


# ---------------------------------------------------------------------------
# Exit-code wiring: both rules stay warn-only against the REAL tree
# ---------------------------------------------------------------------------


def test_wait_mechanism_is_warn_only_never_gates_strict_exit():
    """The two rules must never flip check_orchestration.py's exit code, no matter what they
    find - only rules 1-8 (+ agent-role) gate `--strict`. Runs the REAL main() against the real
    tree (which does trigger both rules on the current tree) and asserts the process still exits
    0 under --strict."""
    import subprocess

    script = PLUGIN / "generator" / "check_orchestration.py"
    result = subprocess.run(
        [sys.executable, str(script), "--strict"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"check_orchestration.py --strict must exit 0 even though [wait-scope]/[wait-mechanism] "
        f"produce findings on the real tree (warn-first for one release) - "
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "warn-only finding" in result.stdout, (
        "sanity: the real tree is expected to produce at least one warn-only finding right now "
        "(several park instructions still lack an R0-branch citation) - if this ever reads 0, "
        "the fixture assumption changed and this sanity clause should be revisited, not silently "
        "dropped"
    )
