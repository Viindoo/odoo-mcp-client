"""Behavior gate for two BREAKs in the three-level delegation chain
(main -> Skill odoo-coding -> agent odoo-coder (coordinator) -> {odoo-test-writer,
odoo-backend-coder, odoo-frontend-coder}), found by phase4-verify V1b Q3a / A-R2-03 (C2) and
V1a Q4 (C3).

C2 - a child's NEEDS_CONTEXT deadlocked the coordinator's wait forever.
`agents/odoo-coder.md` had a full, decidable, bounded procedure for a WI worker's `BLOCKED` (5
mentions) but named `NEEDS_CONTEXT` exactly ONCE - the coordinator's OWN emission upward, never a
reaction to a CHILD returning it. The barrier condition itself
(`snippets/spawner-completion-contract.md` R1, cited by `odoo-coder.md`'s WI-wait paragraph and by
`skills/odoo-coding/SKILL.md`'s batch-wait step) gated release on a task-list TOOL's own native
`completed`/`blocked` labels - a vocabulary `snippets/execution-tasklist-contract.md` (the file the
coordinator's barrier sentence cited as its SSOT) never defined, and which this session's actual
tool surface does not expose at all (no `TaskCreate`/`TaskUpdate`/`TaskList`/`TaskGet`/`TodoWrite`
tool is present - verified empirically via ToolSearch during the fix, not assumed). The fix
decouples the release condition from any tool-native label and defines it once, against the stable
Continuation Contract `status` enum (DONE/BLOCKED/NEEDS_NEXT/NEEDS_CONTEXT) that every agent already
emits regardless of which task-list primitive (if any) the harness exposes.

C3 - a dead coordinator is advertised as alive.
If `odoo-coder` terminates hard while its workers run, `module-coordination-ledger.md`'s
`heartbeat_at` kept refreshing for a module the run believed was `building`, and the lifecycle had
no transition for "the dispatch returned no status at all" - so a dead build looked alive to every
OTHER run reading the ledger. The fix adds an immediate (non-staleness-bounded) `building -> failed`
transition for exactly this signal, and wires `odoo-coding`'s own dispatch-loop wait to recognize a
dispatch that resolves without a parseable Continuation Contract as fail-closed evidence of death,
never a silent hang or a stale-but-live-looking heartbeat.

These assertions protect the CONTRACT'S BEHAVIOR - not a wording snapshot. Each can fail for a real
reason: drop the NEEDS_CONTEXT procedure, reintroduce a tool-native-only barrier, or drop the
dead-dispatch ledger transition, and the corresponding assertion goes red.

Run: python -m pytest tests/test_coder_needs_context_and_dead_dispatch.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

CODER_MD = PLUGIN / "agents" / "odoo-coder.md"
SPAWNER_CONTRACT_MD = PLUGIN / "snippets" / "spawner-completion-contract.md"
TASKLIST_CONTRACT_MD = PLUGIN / "snippets" / "execution-tasklist-contract.md"
CONTINUATION_CONTRACT_MD = PLUGIN / "snippets" / "continuation-contract.md"
LEDGER_MD = PLUGIN / "snippets" / "module-coordination-ledger.md"
CODING_SKILL_MD = PLUGIN / "skills" / "odoo-coding" / "SKILL.md"


def _norm(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# C2a - odoo-coder.md must handle a CHILD's NEEDS_CONTEXT, not just emit its own
# ---------------------------------------------------------------------------


def test_coder_has_a_named_procedure_for_a_childs_needs_context():
    """odoo-coder.md must react to a WI worker's own NEEDS_CONTEXT with a decidable procedure -
    the register's finding was that NEEDS_CONTEXT appeared exactly once (the coordinator's own
    upward emission at the SELF_PROVISION section), never a child-reaction procedure. Guard against
    that regressing: NEEDS_CONTEXT must appear more than once, and at least one occurrence must be
    the child-reaction procedure, distinguishable from BLOCKED handling and from the coordinator's
    own SELF_PROVISION emission."""
    text = _text(CODER_MD)
    count = text.count("NEEDS_CONTEXT")
    assert count > 1, (
        f"agents/odoo-coder.md names NEEDS_CONTEXT only {count} time(s) - the pre-fix defect had "
        "exactly 1 (the coordinator's own SELF_PROVISION emission upward). A child-reaction "
        "procedure must add at least one more mention."
    )
    low = _norm(CODER_MD).lower()
    assert "a wi worker's own pre-integration `needs_context`" in low or (
        "worker" in low and "needs_context" in low and "resolve or relay" in low
    ), (
        "odoo-coder.md must name a procedure for a WI WORKER's own NEEDS_CONTEXT (not only the "
        "coordinator's own SELF_PROVISION emission)"
    )


def test_coders_needs_context_procedure_is_decidable_and_bounded():
    """The NEEDS_CONTEXT procedure must be decidable (a diagnose-then-branch rule, not open-ended
    improvisation) and bounded (reuses the same 3-iteration limit as BLOCKED, never an unbounded
    wait), and must distinguish NEEDS_CONTEXT from BLOCKED (never silently downgrade one to the
    other) and from DONE (never paper over it)."""
    low = _norm(CODER_MD).lower()
    assert "if you hold its value" in low or "if you do not hold the value" in low, (
        "the procedure must give a decidable diagnose-then-branch rule (does the coordinator hold "
        "the missing field or not), not leave the coordinator to improvise"
    )
    assert "same bounded 3-iteration limit" in low, (
        "the NEEDS_CONTEXT procedure must reuse the SAME bounded 3-iteration limit as a WI-level "
        "BLOCKED - never an unbounded wait"
    )
    assert "never silently downgrade it to `blocked`" in low or (
        "never silently downgrade" in low and "blocked" in low
    ), "the procedure must forbid silently downgrading NEEDS_CONTEXT to BLOCKED"
    assert "never paper over it with `done`" in low or (
        "never paper over it with" in low and "done" in low
    ), "the procedure must forbid papering over an unresolved NEEDS_CONTEXT with DONE"
    assert "spawner-completion-contract.md` r2" in low, (
        "the procedure must point at (not restate) spawner-completion-contract.md R2's rollup rule"
    )


# ---------------------------------------------------------------------------
# C2b - the release vocabulary is real: defined once, referenced, tool-agnostic
# ---------------------------------------------------------------------------


def test_spawner_completion_contract_r1_defines_release_vocabulary_against_continuation_enum():
    """R1's barrier release condition must be defined against the stable Continuation Contract
    status enum (DONE/BLOCKED/NEEDS_NEXT/NEEDS_CONTEXT) - NOT against a task-list tool's own
    native label set, which is runtime-dependent and may not even expose all four (or any)
    states. This is the fix for A-R2-03: 'the release condition names a vocabulary its own
    source of truth never defines.'"""
    text = _text(SPAWNER_CONTRACT_MD)
    low = _norm(SPAWNER_CONTRACT_MD).lower()
    assert "release vocabulary" in low, (
        "R1 must explicitly name itself as the release-vocabulary SSOT"
    )
    for status in ("DONE", "BLOCKED", "NEEDS_NEXT", "NEEDS_CONTEXT"):
        assert status in text, f"R1's release vocabulary must enumerate {status}"
    assert "never a subset of two" in low or "never just two" in low, (
        "R1 must explicitly forbid gating the barrier on only two of the four statuses (the "
        "pre-fix `completed`/`blocked` two-state gate)"
    )
    assert "mirror" in low, (
        "R1 must state the task-list tool's own native label is a MIRROR of the release "
        "vocabulary, never the authority"
    )
    assert "unsatisfiable" in low, (
        "R1 must name the failure mode directly: a barrier gated on a tool-native label the tool "
        "does not expose is unsatisfiable and must never be the release condition"
    )


def test_execution_tasklist_contract_disclaims_owning_the_release_vocabulary():
    """execution-tasklist-contract.md must explicitly say it does NOT define a spawner's release
    vocabulary (the register's finding: it was cited as the SSOT for `completed`/`blocked` but
    contains zero occurrences of that vocabulary) and must point at
    spawner-completion-contract.md R1 as the actual owner, closing the dangling citation rather
    than leaving the vocabulary undefined everywhere."""
    text = _text(TASKLIST_CONTRACT_MD)
    low = _norm(TASKLIST_CONTRACT_MD).lower()
    assert "does not own it" in low or "does not define" in low, (
        "the file must explicitly disclaim owning the release-vocabulary definition"
    )
    assert "spawner-completion-contract.md` r1" in low, (
        "the file must point at spawner-completion-contract.md R1 as the actual owner of the "
        "release vocabulary"
    )
    for status in ("DONE", "BLOCKED", "NEEDS_NEXT", "NEEDS_CONTEXT"):
        assert status in text, (
            f"the disclaimer paragraph must name {status} so a reader lands on the real enum"
        )


def test_coder_barrier_gates_on_four_statuses_not_tool_native_labels():
    """odoo-coder.md's own WI-wait barrier sentence (Agent Team mode section) must gate release
    on the four Continuation Contract terminal statuses, never on a bare `completed`/`blocked`
    task-list-tool label pair."""
    text = _text(CODER_MD)
    assert re.search(
        r"`DONE`,\s*`BLOCKED`,\s*`NEEDS_NEXT`,\s*or\s*`NEEDS_CONTEXT`", text
    ), "odoo-coder.md's barrier sentence must enumerate all four terminal statuses"
    assert "is `completed`/`blocked`" not in text and "is `completed` or `blocked`" not in text, (
        "odoo-coder.md must no longer gate its WI barrier on the bare tool-native "
        "`completed`/`blocked` label pair"
    )


def test_coding_skill_dispatch_loop_gates_on_four_statuses_not_tool_native_labels():
    """skills/odoo-coding/SKILL.md's batch-wait step (dispatch loop step 4) must gate release on
    the four Continuation Contract terminal statuses, never on a bare tool-native
    `completed`/`blocked` task-list label pair."""
    text = _text(CODING_SKILL_MD)
    assert re.search(
        r"`DONE`,\s*`BLOCKED`,\s*`NEEDS_NEXT`,\s*or\s*`NEEDS_CONTEXT`", text
    ), "odoo-coding SKILL.md's batch-wait step must enumerate all four terminal statuses"
    assert "is `completed`/`blocked`" not in text, (
        "odoo-coding SKILL.md must no longer gate its batch barrier on the bare tool-native "
        "`completed`/`blocked` label pair"
    )


# ---------------------------------------------------------------------------
# C3 - dead-coordinator accounting: fail closed, never advertise a dead build as alive
# ---------------------------------------------------------------------------


def test_ledger_has_immediate_dead_dispatch_transition_distinct_from_staleness():
    """module-coordination-ledger.md must add a `building -> failed` transition for a dead
    dispatch (a coordinator return with no parseable Continuation Contract) that fires
    IMMEDIATELY - not bounded by the N-tick staleness wait, which exists for the DIFFERENT case
    of absence-of-evidence (a slow-but-alive build looks the same as a dead one on the clock)."""
    text = _text(LEDGER_MD)
    low = _norm(LEDGER_MD).lower()
    assert "building -> failed" in text or "building" in low and "failed" in low, (
        "the ledger must name a building -> failed transition"
    )
    assert "dead-dispatch" in low, "the ledger must name the dead-dispatch case explicitly"
    assert "without a parseable continuation contract" in low, (
        "the ledger must define dead-dispatch as a coordinator return with no parseable "
        "Continuation Contract"
    )
    assert "immediate" in low and "no staleness wait" in low or (
        "immediate" in low and "staleness" in low
    ), (
        "the ledger must state the dead-dispatch transition is IMMEDIATE, distinct from the "
        "N-tick staleness bound used for absence-of-evidence"
    )
    assert "fail closed" in low or "fail-closed" in low, (
        "the ledger must state the dead-dispatch handling fails CLOSED on any doubt"
    )
    assert "never flip a module that did return a valid report to `failed`" in low or (
        "never" in low and "mere suspicion" in low
    ), (
        "the ledger must forbid flipping a module WITH a valid report to failed on mere "
        "suspicion - fail-closed must not become fail-paranoid"
    )


def test_coding_skill_reacts_to_a_dead_coordinator_dispatch():
    """skills/odoo-coding/SKILL.md's dispatch loop must define what happens when a coordinator
    dispatch resolves WITHOUT a parseable Continuation Contract - the C3 gap the register named:
    'the lifecycle has no transition for the dispatch returned no status at all'. Must flip the
    ledger entry (when one exists), classify the module BLOCKED with a distinguishing reason
    (never confused with a graceful business BLOCKED), and fail closed."""
    text = _text(CODING_SKILL_MD)
    low = _norm(CODING_SKILL_MD).lower()
    assert "without a parseable continuation contract" in low, (
        "odoo-coding SKILL.md must name the dead-dispatch signal explicitly: a return without a "
        "parseable Continuation Contract"
    )
    assert "never a silent success" in low or "never left pending" in low, (
        "the dead-dispatch case must be stated as never a silent success and never left pending "
        "on the batch barrier"
    )
    assert "module-coordination-ledger.md" in text and "dead-dispatch" in low, (
        "odoo-coding SKILL.md must point at the ledger's dead-dispatch transition (not restate "
        "its mechanics)"
    )
    assert "dead coordinator dispatch" in low, (
        "the module's own BLOCKED classification must name the distinguishing reason: dead "
        "coordinator dispatch (no completion report)"
    )
    assert "fail closed" in low, (
        "odoo-coding's own reaction must also state the fail-closed rule"
    )


# ---------------------------------------------------------------------------
# Regression guard - the pre-fix defect counts, reproduced against git HEAD (ad524c7)
# ---------------------------------------------------------------------------


def test_pre_fix_baseline_would_have_failed_these_guards():
    """Sanity check that these guards are not vacuous: the pre-fix text (captured from this
    round's BASE commit at fix-authoring time) had exactly ONE NEEDS_CONTEXT mention in
    odoo-coder.md (the coordinator's own emission) and gated the barrier on the bare
    `completed`/`blocked` pair. This test does not read git history (keeps the suite hermetic);
    it re-asserts the two counts the fix changed, as a live tripwire: if a future edit
    reintroduces the single-mention/two-state pattern, the tests above (not this one) will fail
    first - this test exists so a reader can see the before/after delta is real, not merely
    aspirational prose."""
    coder_text = _text(CODER_MD)
    assert coder_text.count("NEEDS_CONTEXT") > 1, (
        "regression: odoo-coder.md dropped back to a single NEEDS_CONTEXT mention"
    )
    assert "`DONE`, `BLOCKED`, `NEEDS_NEXT`, or `NEEDS_CONTEXT`" in coder_text, (
        "regression: odoo-coder.md's barrier no longer enumerates all four terminal statuses"
    )
