"""Issue class (generalized): visual/qa|debug|screenshots got a bounded TTL orphan sweep, but
every OTHER run-scoped Tier-2 ISOLATE subpath in the plugin still has zero garbage collection -
worklog/, wave/, git-rebase/, forward-port/, modules-upgrade/, coding/, reviews/,
pr-monitoring/, followups/, i18n/, visual/videos/, visual/<run_id>/<module>_staging/, and all 13
workflow output_dir trees each leak one directory per run forever.

Fix: snippets/visual-evidence-lifecycle-contract.md Clause 3 enumerates and classifies every
ISOLATE-table row from state-root-resolution.md (eligible / excluded-with-reason / not
applicable), states the bound per class (24h crash-backstop vs 30-day deliberate-retention, no
third bound invented), states the SHARE-tier decision explicitly, and states why run-<id>.json is
excluded (mtime is not a reliable liveness signal across a human-gated pause). Each eligible
subpath's owning skill (or, for worklog/ and the 13 workflow output_dirs, the ONE shared
chokepoint every consumer already goes through) cites Clause 3 and runs the sweep at its own
Phase/Round 0.

Guard-the-class: a NEW subpath added to state-root-resolution.md's ISOLATE table without a
corresponding classification in Clause 3 reddens test_every_isolate_row_is_classified_in_clause_3
below - this is a structural, whitespace-normalized cross-file consistency check, not an
allowlist.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SKILLS_DIR = PLUGIN / "skills"
SNIPPETS_DIR = PLUGIN / "snippets"

CONTRACT_PATH = SNIPPETS_DIR / "visual-evidence-lifecycle-contract.md"
STATE_ROOT_PATH = SNIPPETS_DIR / "state-root-resolution.md"
WORKLOG_CONTRACT_PATH = SNIPPETS_DIR / "worklog-contract.md"
WORKFLOW_CHAINING_PATH = SKILLS_DIR / "workflow-chaining" / "SKILL.md"

CONTRACT_REF = "visual-evidence-lifecycle-contract.md"
BOUND_LONG = 43200  # 30 days
BOUND_SHORT = 1440  # 24 hours


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _contract_text() -> str:
    assert CONTRACT_PATH.exists(), f"Expected shared contract at {CONTRACT_PATH}"
    return CONTRACT_PATH.read_text(encoding="utf-8")


def _skill_text(name: str) -> str:
    path = SKILLS_DIR / name / "SKILL.md"
    assert path.exists(), f"{name}/SKILL.md not found at {path}"
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Guard the CLASS: every ISOLATE-table row from the (closed, read-only) SSOT
# must be classified somewhere in Clause 3 - eligible, excluded, or N/A.
# --------------------------------------------------------------------------- #


def _isolate_table_subpaths() -> list[str]:
    text = STATE_ROOT_PATH.read_text(encoding="utf-8")
    start = text.index("## Tier-2 ISOLATE list")
    end = text.index("\n## ", start + 1)
    section = text[start:end]
    rows = re.findall(r"^\| `([^`]+)`", section, re.MULTILINE)
    assert rows, "Could not parse any ISOLATE subpath rows from state-root-resolution.md"
    return rows


def test_every_isolate_row_is_classified_in_clause_3():
    rows = _isolate_table_subpaths()
    contract = _contract_text()
    missing = [r for r in rows if r not in contract]
    assert not missing, (
        "These ISOLATE subpaths from state-root-resolution.md are not classified anywhere in "
        f"{CONTRACT_REF}'s Clause 3 (eligible / excluded / not-applicable): {missing}"
    )


# --------------------------------------------------------------------------- #
# Clause 3 structural content: bounds, SHARE decision, exclusions.
# --------------------------------------------------------------------------- #


def test_clause_3_exists_and_reuses_only_the_two_existing_bounds():
    norm = _norm(_contract_text())
    assert "Clause 3" in norm, "Expected a Clause 3 section generalizing the ISOLATE GC rule"
    assert str(BOUND_LONG) in norm and "30 day" in norm.replace("30-day", "30 day"), (
        "Clause 3 must state the reused 30-day / 43200-minute bound"
    )
    assert str(BOUND_SHORT) in norm or "24h" in norm, (
        "Clause 3 must state the reused 24h crash-backstop bound"
    )
    assert re.search(r"(?i)no third bound", norm), (
        "Clause 3 must explicitly state that no third bound was invented"
    )


def test_run_id_json_is_explicitly_excluded_with_reasoning():
    norm = _norm(_contract_text())
    assert "run-<id>.json" in norm and re.search(r"(?i)exclud", norm), (
        "Clause 3 must explicitly exclude run-<id>.json from the generalized sweep"
    )
    assert re.search(r"(?i)not a reliable liveness signal", norm), (
        "Clause 3 must explain WHY run-<id>.json is excluded: mtime is not a reliable liveness "
        "signal across a paused-but-alive run (the write-once-while-still-alive failure mode)"
    )


def test_recon_exclusion_cites_the_competing_ssot():
    norm = _norm(_contract_text())
    assert "recon/<slug>-<date>/" in norm, "Clause 3 must classify recon/<slug>-<date>/"
    assert "scouting-persistence-contract.md" in norm and re.search(
        r"(?i)never delete", norm
    ), (
        "Clause 3 must exclude recon/<slug>-<date>/ by citing "
        "scouting-persistence-contract.md's existing 'never delete' clause, not silently "
        "override it"
    )


def test_share_tier_decision_is_explicit_not_silent():
    norm = _norm(_contract_text())
    assert re.search(r"(?i)SHARE.{0,40}(out of scope|excluded)", norm) or re.search(
        r"(?i)(out of scope|excluded).{0,40}SHARE", norm
    ), (
        "Clause 3 must explicitly state that SHARE is out of scope for this GC rule (by design), "
        "not leave the question unanswered"
    )


def test_brainstorm_state_json_marked_not_applicable():
    norm = _norm(_contract_text())
    assert "brainstorm/state.json" in norm and re.search(
        r"(?i)not applicable", norm
    ), (
        "Clause 3 must classify brainstorm/state.json as not-applicable (singleton file, no "
        "per-run accumulation) rather than silently omitting it"
    )


# --------------------------------------------------------------------------- #
# Wired sweeps: worklog/ (shared chokepoint) and the 13 workflow output_dirs
# (shared chokepoint via workflow-chaining).
# --------------------------------------------------------------------------- #


def test_worklog_contract_wires_the_sweep_and_cites_clause_3():
    assert WORKLOG_CONTRACT_PATH.exists()
    text = WORKLOG_CONTRACT_PATH.read_text(encoding="utf-8")
    assert CONTRACT_REF in text, "worklog-contract.md must cite the shared GC contract"
    assert re.search(
        rf"find <ISOLATE_DIR>/worklog/.*-mmin \+{BOUND_LONG}.*-exec rm -rf", text
    ), "worklog-contract.md must sweep stale worklog/<run-or-slug>/ dirs on the 30-day bound"


def test_workflow_chaining_wires_the_sweep_and_cites_clause_3():
    assert WORKFLOW_CHAINING_PATH.exists()
    text = WORKFLOW_CHAINING_PATH.read_text(encoding="utf-8")
    assert CONTRACT_REF in text, "workflow-chaining/SKILL.md must cite the shared GC contract"
    assert re.search(r"-mmin \+" + str(BOUND_LONG), text), (
        "workflow-chaining/SKILL.md Phase 0 must sweep stale output_dir siblings on the 30-day "
        "bound - covering all 13 workflow output_dir trees generically"
    )
    assert re.search(r"(?i)orphan sweep", text)


# --------------------------------------------------------------------------- #
# Individually-owned eligible subpaths: each owning skill sweeps + cites Clause 3.
# --------------------------------------------------------------------------- #

INDIVIDUAL_SWEEPS = {
    "odoo-git-rebase": "git-rebase/",
    "odoo-forward-port": "forward-port/",
    "odoo-modules-upgrade": "modules-upgrade/",
    "odoo-coding": "coding/",
    "odoo-code-review": "reviews/",
    "odoo-pr-monitoring": "pr-monitoring/",
    "odoo-i18n": "i18n/",
    "odoo-demo-recording": "visual/videos/",
    "odoo-doc-illustration": "visual/",
}


def test_each_individually_owned_subpath_cites_clause_3():
    missing = []
    for skill in INDIVIDUAL_SWEEPS:
        text = _skill_text(skill)
        if CONTRACT_REF not in text:
            missing.append(skill)
    assert not missing, (
        f"These skills own an eligible run-scoped ISOLATE subpath but do not cite "
        f"{CONTRACT_REF} for their orphan sweep: {missing}"
    )


def test_each_individually_owned_subpath_sweeps_with_a_bounded_find():
    missing = []
    for skill, subdir in INDIVIDUAL_SWEEPS.items():
        text = _skill_text(skill)
        pattern = re.compile(
            rf"find <ISOLATE_DIR>/{re.escape(subdir)}.*-mmin \+\d+.*-exec rm -rf"
        )
        if not pattern.search(text):
            missing.append(skill)
    assert not missing, (
        f"These skills do not sweep their own stale sibling directories with a bounded "
        f"'find ... -mmin +<N> ... -exec rm -rf' orphan sweep: {missing}"
    )
