"""Guard [no-provenance] (rule 15 in generator/check_orchestration.py, M10 / X-50).

Agent-facing prose must carry no PLUGIN-SELF changelog / issue-tracking provenance: that history
has zero value to an executing agent and costs context on every dispatch. The hard part is that
the SAME vocabulary reads two ways, and only one of them is residue:

  RESIDUE    narrates what THIS PLUGIN used to do          -> free to delete, git already has it
  OPERATIVE  tells the agent what to DO about something     -> deleting it BREAKS a live consumer
             that still exists in the wild

`the legacy single-module path` (residue) and `a legacy `SUGGESTED_NEXT:` line is still read by
the driver` (operative) differ by intent, not by grammar, so the rule approximates the cut with
window-scoped guards: a DOMAIN anchor (Odoo version / era / the prospect's incumbent system / the
codebase under work), a legacy era the document itself DEFINES in a heading, a quoted example, and
an OPERATIVE BACK-COMPAT handling phrase.

This file is a two-direction mutation proof of exactly that cut. Every passing case is paired with
a MUTATION that deletes only the signal the guard keys on; the mutation must go RED. A guard that
cannot fail is worthless, and a guard that exempts everything is worse than none.

Run: python -m pytest tests/test_no_provenance_guard.py -v
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


def _findings_for(body: str, tmp_path: Path, monkeypatch) -> list[str]:
    """Run check_no_provenance over a synthetic corpus of exactly one snippet file.

    Everything but `snippets/` is pointed at a path that does not exist, so the scan corpus is the
    single fixture file and nothing on the real tree can colour the result."""
    fake_root = tmp_path / "odoo-ai-agents"
    (fake_root / "snippets").mkdir(parents=True)
    (fake_root / "snippets" / "fixture.md").write_text(body, encoding="utf-8")

    monkeypatch.setattr(co, "PLUGIN_ROOT", fake_root)
    monkeypatch.setattr(co, "SNIPPETS_DIR", fake_root / "snippets")
    monkeypatch.setattr(co, "REFERENCES_DIR", fake_root / "snippets" / "references")
    for name in ("SKILLS_DIR", "AGENTS_DIR", "COMMANDS_DIR", "WORKFLOWS_DIR", "DOCS_DIR"):
        monkeypatch.setattr(co, name, fake_root / "absent")

    findings: list[str] = []
    co.check_no_provenance(findings)
    return findings


# --- Direction 1: RESIDUE must be FLAGGED --------------------------------------------------------
# Plugin-self history in the per-invocation path. None of these tells an executing agent anything
# it can act on, and every one of them is recoverable from git.
RESIDUE_CASES = {
    "self-history_path": "The single-module legacy path has no plan entry, so the run-level axis wins.",
    "changelog_replaces": "Replaces `find_override_point` in the disk-fallback tier.",
    "design_tag": "Apply the ledger rule (V-34) before dispatching any worker.",
    "issue_reference": "Rationale lives in PR #123; do not re-litigate it here.",
    "rename_note": "The contract block was renamed from `SUGGESTED_NEXT` earlier in this file.",
    # Guard 3 is offered ONLY to vocabulary that can name a still-live old shape. A pure
    # provenance tag can never BE an operative instruction, so back-compat wording beside it
    # must not launder it - otherwise one stray `Back-compat:` disarms the whole rule.
    "backcompat_cannot_launder_a_tracker_ref": (
        "Back-compat: the rationale for this shape is tracked in PR #12."
    ),
}


@pytest.mark.parametrize("body", RESIDUE_CASES.values(), ids=list(RESIDUE_CASES))
def test_plugin_self_history_is_flagged(body, tmp_path, monkeypatch):
    findings = _findings_for(body, tmp_path, monkeypatch)
    assert findings, (
        f"expected a [no-provenance] finding for plugin-self residue, got none for: {body!r}"
    )


# --- Direction 2: OPERATIVE / DOMAIN text must PASS, and each guard must be load-bearing ---------
# (passing text, mutation that removes ONLY the signal the guard keys on).
GUARD_CASES = {
    # Guard 3 - explicit back-compat label + a verb applied to the old shape.
    "operative_backcompat_label": (
        "Back-compat: a legacy `SUGGESTED_NEXT:` line is still read by the driver as a "
        "low-confidence NEEDS_NEXT.",
        "A legacy `SUGGESTED_NEXT:` line is handed to the driver.",
    ),
    # Guard 3 - `fallback` as the head of a noun phrase, the shape the allocator docs use.
    "operative_fallback": (
        "`owner.session_id` is read only as a legacy fallback on leases minted before `run_id`.",
        "`owner.session_id` is a legacy field on leases minted earlier.",
    ),
    # Guard 3 - a handling verb applied to the old shape, with no label.
    "operative_handling_verb": (
        "A lease with no live local pid (legacy pre-setsid) skips the stop - no-op, always safe.",
        "A lease with no live local pid (legacy pre-setsid) is ignored by the reaper.",
    ),
    # Guard 1c - the PROSPECT's incumbent system: the customer's history, not this plugin's.
    "incumbent_system": (
        "Current system: bookkeeping in a spreadsheet plus legacy accounting software.",
        "The team still runs the legacy bookkeeping tool nobody maintains.",
    ),
    # Guard 1b - Odoo's own CSS era.
    "odoo_css_era": (
        "If the module already uses legacy `oe_*` classes, stay consistent.",
        "If the module already uses legacy class names, stay consistent.",
    ),
    # Guard 1 - a series named by ROLE is still an Odoo series.
    "role_named_series": (
        "A legacy source-only data fix keeps `<src-series>.a.b.c` when retargeting to the "
        "target series.",
        "A legacy source-only data fix keeps the directory name unchanged.",
    ),
    # Guard 1d - the codebase under work evolved; that is a finding, not residue.
    "code_under_work": (
        "OSM shows the mechanism the module customized no longer exists at target; no "
        "`absorbing_core_feature` can be honestly named.",
        "The mechanism this skill used to wrap no longer exists.",
    ),
    # Guard 1 - Odoo DOMAIN version history.
    "odoo_version_anchor": (
        "Renamed from `test_pylint` at v13 - use the current gate name.",
        "Renamed from `test_pylint` - use the current gate name.",
    ),
    # Guard 1e - the document DEFINES a legacy era in a heading, so a later bare `legacy` is a
    # back-reference to that defined term, not a claim about this plugin's past.
    "defined_era_anaphora": (
        "## Legacy v8-v14 workflow\n\nRounds 1-4 unchanged.\n\n"
        "**Round 5.** Same as the legacy Round 5: add a `next:` entry.\n",
        "## Legacy workflow\n\nRounds 1-4 unchanged.\n\n"
        "**Round 5.** Same as the legacy Round 5: add a `next:` entry.\n",
    ),
}


@pytest.mark.parametrize(
    "passing,_mutated", GUARD_CASES.values(), ids=list(GUARD_CASES)
)
def test_operative_or_domain_text_passes(passing, _mutated, tmp_path, monkeypatch):
    """Live instructions and domain facts are load-bearing - flagging them would push a cleanup
    pass into DELETING something a consumer still depends on."""
    findings = _findings_for(passing, tmp_path, monkeypatch)
    assert findings == [], f"expected zero findings for operative/domain text, got: {findings}"


@pytest.mark.parametrize(
    "_passing,mutated", GUARD_CASES.values(), ids=list(GUARD_CASES)
)
def test_removing_the_guard_signal_goes_red(_passing, mutated, tmp_path, monkeypatch):
    """The mutation half: delete only the signal the guard keys on and the same sentence must be
    flagged. Without this, an over-wide exemption would read as a clean corpus forever."""
    findings = _findings_for(mutated, tmp_path, monkeypatch)
    assert findings, (
        f"guard is not load-bearing - the mutated text should be flagged but was not: {mutated!r}"
    )
