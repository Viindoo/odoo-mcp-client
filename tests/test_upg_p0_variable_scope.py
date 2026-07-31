"""Behavioral guard: odoo-modules-upgrade P0's step (2) must reference a variable already
bound at that point in the phase, never one resolved by a LATER step.

Business rule: P0's TASK block resolves variables in step order - step (1) infers the SOURCE
series and binds it as `<inferred_series>` (used one line later by
`set_active_version(odoo_version='<inferred_series>')`); step (4), several steps later, is the
FIRST point that binds `<target_version>` (from the NL ask, e.g. "upgrade to v17"). A tool call
inside step (2) runs BEFORE step (4) - it therefore CANNOT reference `<target_version>`: an agent
executing this instruction verbatim would be told to substitute a variable it has not resolved
yet. This exact regression was introduced by a mechanical 'auto'-sentinel-ban sweep that blindly
replaced every `odoo_version='auto'` occurrence in this file with `odoo_version='<target_version>'`,
without checking whether `target_version` was actually in scope at each call site - step (2)'s
`profile_inspect` call is the one site in this file where that substitution was wrong.

Each test fails for exactly one reason: step (2)'s `profile_inspect` call regresses to reference
the unbound `<target_version>` again instead of the in-scope `<inferred_series>`, or the ordering
of the bind (step 1) vs the use (step 2) is reversed.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHASE_DETAIL = (
    ROOT / "plugins" / "odoo-ai-agents" / "skills" / "odoo-modules-upgrade"
    / "references" / "upg-phase-detail.md"
)


def _p0_task_block() -> str:
    text = PHASE_DETAIL.read_text(encoding="utf-8")
    start = text.index("## P0 - Intake subagent dispatch brief")
    end = text.index("## P1 - Recon parallel dispatch", start)
    return text[start:end]


def test_p0_step2_profile_inspect_references_inferred_series_not_target_version():
    block = _p0_task_block()
    match = re.search(r"profile_inspect\([^)]*\)", block)
    assert match, "P0 step (2) must call profile_inspect(...) to confirm repos + module set"
    call = match.group(0)
    # Whitespace-normalize before the literal-absence check so a reflow/line-wrap cannot hide
    # a reintroduced 'target_version' token from a naive substring scan.
    normalized = " ".join(call.split())
    assert "target_version" not in normalized, (
        "P0 step (2) runs BEFORE step (4) resolves target_version - a profile_inspect call here "
        f"must not reference the unbound <target_version> placeholder: {call!r}"
    )
    assert "<inferred_series>" in normalized, (
        "P0 step (2) must pin against <inferred_series> (bound by step (1), one line above via "
        f"set_active_version), the only series value in scope at this point: {call!r}"
    )


def test_p0_step1_binds_inferred_series_before_step2_consumes_it():
    block = _p0_task_block()
    bind_idx = block.index("set_active_version(odoo_version='<inferred_series>')")
    use_idx = block.index("profile_inspect(")
    assert bind_idx < use_idx, (
        "step (1)'s set_active_version binding of <inferred_series> must precede step (2)'s "
        "profile_inspect call that consumes it"
    )
