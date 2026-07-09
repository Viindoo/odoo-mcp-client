"""Behavioral guard: the Q3 module-coordination ledger contract (solution-v2 § 4.5).

Business rules this protects:

- The ledger entry schema: {module, status in claimed|building|done|failed, run_id, worktree,
  claimed_at, heartbeat_at}.
- LEDGER_ROOT is resolved via `git rev-parse --git-common-dir` so it is SHARED across every linked
  worktree and concurrent run (a per-worktree `.odoo-ai/` cannot do this).
- A claim is an ATOMIC `mkdir` (POSIX single syscall) - no flock / lock file.
- ONLY odoo-coding writes the ledger; the leaf coder stays ledger-unaware.
- All 6 decision-table cases are present.
- The HONESTY invariant: a dead / never-writing run lands in case 6 as a clean BLOCKED - never a
  false "in progress"; absence is always the honest fallback.

These are CONTRACT checks (the facts are stated), not string-count snapshots.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

LEDGER = PLUGIN / "snippets" / "module-coordination-ledger.md"


def _text() -> str:
    assert LEDGER.exists(), (
        f"snippets/module-coordination-ledger.md (the Q3 ledger SSOT) is missing at {LEDGER}"
    )
    return LEDGER.read_text(encoding="utf-8")


def test_entry_schema_fields_and_statuses():
    """The entry schema must name every required field and every status value.

    Fails if: a schema field or a status value is dropped - a consumer reading/writing the ledger
    would then produce or expect an inconsistent entry.
    """
    text = _text()
    for field in ("module", "status", "run_id", "worktree", "claimed_at", "heartbeat_at"):
        assert field in text, f"ledger entry schema must declare the {field!r} field."
    for status in ("claimed", "building", "done", "failed"):
        assert status in text, f"ledger status set must include {status!r}."
    # run_id reuses the worklog run-or-slug, never a freshly minted id.
    low = text.lower()
    assert "run-or-slug" in low or ("worklog" in low and "reuse" in low), (
        "run_id must REUSE the worklog run-or-slug, not mint a new id."
    )
    # Portable UTC timestamp format.
    assert "date -u +%Y-%m-%dT%H:%M:%SZ" in text, (
        "timestamps must use the portable UTC form `date -u +%Y-%m-%dT%H:%M:%SZ`."
    )


def test_ledger_root_via_git_common_dir():
    """LEDGER_ROOT must resolve via `git rev-parse --git-common-dir` for cross-run visibility.

    Fails if: the resolution drops --git-common-dir (e.g. a per-worktree `.odoo-ai/`) - concurrent
    runs in different worktrees would then never see each other's claims.
    """
    text = _text()
    assert "git rev-parse --git-common-dir" in text, (
        "LEDGER_ROOT must be resolved via `git rev-parse --git-common-dir`."
    )
    assert "LEDGER_ROOT" in text and "coordination/modules" in text, (
        "LEDGER_ROOT must point at .odoo-ai/coordination/modules under the shared common dir."
    )
    low = text.lower()
    assert "common-dir" in low and ("shared" in low or "cross-run" in low), (
        "The snippet must explain WHY --git-common-dir gives cross-run/worktree visibility."
    )
    # A run outside any git repo degrades to no-ledger per-run behavior and logs it.
    assert "outside" in low and "log" in low, (
        "The snippet must state a run outside any git repo degrades to per-run behavior with no "
        "ledger, and logs it."
    )


def test_claim_is_atomic_mkdir_no_flock():
    """A claim must be an atomic `mkdir` - no flock / lock file.

    Fails if: the atomic-mkdir claim mechanism is replaced or the no-lockfile guarantee is dropped -
    two concurrent runs could then both believe they own a module.
    """
    text = _text()
    low = text.lower()
    assert 'mkdir "$ledger_root/$module"' in low or "mkdir " in low, (
        "The claim must use `mkdir \"$LEDGER_ROOT/$MODULE\"` (atomic POSIX claim)."
    )
    assert "atomic" in low and "eexist" in low, (
        "The snippet must document the claim as an atomic mkdir where losers get EEXIST."
    )
    assert "no flock" in low or "no `flock`" in low or ("flock" in low and "no " in low), (
        "The snippet must state NO flock / lock file is used (the dir's existence is the lock)."
    )


def test_only_odoo_coding_writes_the_ledger():
    """ONLY odoo-coding writes the ledger; the leaf coder stays ledger-unaware.

    Fails if: the write authority is broadened (e.g. the leaf coder) - the coder cannot see the
    batch/DONE barrier, so letting it write would corrupt the coordination state.
    """
    text = _text()
    low = text.lower()
    assert "only" in low and "odoo-coding" in low and "write" in low, (
        "The snippet must state ONLY odoo-coding writes the ledger."
    )
    assert "ledger-unaware" in low or "ledger unaware" in low, (
        "The snippet must state the leaf odoo-coder/odoo-frontend-coder stay ledger-unaware."
    )


def test_all_six_decision_cases_present():
    """The 6-row decision table must be present, in order.

    Fails if: a case is dropped - the classification of a `manifest dependency unresolved` BLOCKED
    would then be incomplete (e.g. no distinction between a concurrent build and a dead run).
    """
    text = _text()
    low = text.lower()
    # Six numbered cases exist under the decision table.
    idx = low.find("decision table")
    assert idx != -1, "The snippet must carry a decision table for the BLOCKED status."
    table = text[idx:]
    for n in range(1, 7):
        assert re.search(rf"(?m)^\s*{n}\.", table), f"decision table must include case {n}."
    # The distinguishing semantics of each case.
    assert "in-set sibling" in low, "case 2 (in-set sibling not-yet-DONE) must be present."
    assert "different" in low and ("run_id" in low or "run" in low), (
        "case 3 (different run, fresh heartbeat -> WAIT) must be present."
    )
    assert "integrate" in low or "rebase" in low, "case 4 (done elsewhere -> integrate/rebase) present."
    assert "failed" in low, "case 5 (failed elsewhere) must be present."
    assert "missing prerequisite" in low, "case 6 (absent/stale -> missing prerequisite) must be present."


def test_case_six_is_the_honest_fallback():
    """Honesty invariant: a dead / never-writing run lands in case 6, never a false 'in progress'.

    Fails if: the honesty invariant is removed or softened - the ledger could then over-claim a
    dead run as an in-progress build and stall a dependent forever.
    """
    text = _text()
    low = text.lower()
    assert "honesty invariant" in low, "The snippet must state the honesty invariant explicitly."
    assert "never a false" in low or "never a fake" in low or 'false "in progress"' in low, (
        "The invariant must state a dead/never-writing run is NEVER a false 'in progress'."
    )
    assert "absence is always the honest fallback" in low, (
        "The invariant must state absence is always the honest fallback (case 6)."
    )
    # Staleness measured in dispatch-loop ticks, not a wall-clock guess.
    assert "tick" in low, "Staleness must be a bounded number of dispatch-loop ticks, not wall-clock."
