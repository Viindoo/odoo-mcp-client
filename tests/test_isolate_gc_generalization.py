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


# --------------------------------------------------------------------------- #
# The two rows this table once admitted were NOT YET wired (`wave/<slug>/` and
# `followups/<slug>.md` - found by grepping every `mmin +` site plugin-wide
# against this table's own claims: 15/17 present, 2 absent) are now wired at
# their owner files (R12 F1 second continuation). The table must claim
# coverage again - the table and reality must agree in the HONEST direction,
# which now means claiming, not disclaiming. The companion guard below
# (`test_gc_coverage_table_owner_actually_contains_a_sweep_whole_table_scan`)
# is what proves the claim is TRUE, not just present - a table asserting
# "wired" without that check would reopen the exact defect class this file
# exists to catch (a claim the code does not back up).
# --------------------------------------------------------------------------- #
def test_table_no_longer_disclaims_the_two_rows_it_used_to_flag_as_unwired():
    norm = _norm(_contract_text())
    assert "not yet wired" not in norm, (
        "the GC-coverage table must no longer contain a NOT YET WIRED disclaimer anywhere - "
        "both wave/<slug>/ and followups/<slug>.md are now wired at their owner files; a "
        "leftover disclaimer would misrepresent reality in the OTHER direction now"
    )
    assert re.search(r"(?i)integration/<slug>/.{0,400}(wired|stale integration-dir sweep)", norm), (
        "the integration/<slug>/ table row (renamed from wave/<slug>/ when the wave grouping "
        "layer was removed) must positively state it is wired (and point at the sweep)"
    )
    assert re.search(r"(?i)followups/<slug>\.md.{0,400}wired", norm), (
        "the followups/<slug>.md table row must positively state it is wired"
    )


# --------------------------------------------------------------------------- #
# GC-coverage table <-> reality cross-check (R12 F1 second continuation): the
# guard that would have caught B7 structurally, instead of needing a human to
# notice the same shape again. Fully table-driven - parses § 3.1's own
# Owner/Subpath columns and resolves each Owner cell to real file(s)
# mechanically (a *.md token glob-searched plugin-wide; a "... command" token
# resolved to commands/<token>.md; any other backtick token treated as a
# skill name and resolved to EVERY *.md file under that skill's own directory,
# covering a references/ subfile the way wave/<slug>/'s own sweep actually
# lives there). NO hand-picked filename allowlist - a row added to the table
# in the future is covered by construction, not by remembering to update a
# list here.
# --------------------------------------------------------------------------- #


def _section_3_1_rows() -> list[tuple[str, str]]:
    text = _contract_text()
    start = text.index("### 3.1 - Eligible")
    end = text.index("\n### 3.2", start)
    section = text[start:end]
    rows: list[tuple[str, str]] = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0] == "Subpath":
            continue
        rows.append((cells[0], cells[1]))
    assert rows, "Could not parse any § 3.1 table rows from the GC-coverage table"
    return rows


def _resolve_owner_files(owner_cell: str):
    """Mechanically resolve a table row's Owner cell to the file(s) that should carry its
    sweep. Returns None for the one row with no backtick-quoted owner at all (the "see Clause 2"
    grouped-for-completeness row) - the caller special-cases that one against Clause 2 directly.
    """
    tokens = re.findall(r"`([^`]+)`", owner_cell)
    if not tokens:
        return None
    token = tokens[0]
    if token.endswith(".md"):
        return sorted(PLUGIN.rglob(token))
    if "command" in owner_cell.lower():
        return [PLUGIN / "commands" / f"{token}.md"]
    skill_dir = SKILLS_DIR / token
    if skill_dir.is_dir():
        return sorted(skill_dir.rglob("*.md"))
    return []


def test_gc_coverage_table_owner_actually_contains_a_sweep_whole_table_scan():
    """Behavior protected: every § 3.1 table row's claimed Owner must ACTUALLY carry a
    `mmin +` sweep for the row's claimed Subpath - a row naming an owner that does not sweep is
    exactly the defect this contract shipped twice before this fix (`wave/<slug>/`,
    `followups/<slug>.md`).

    Fails if any row's resolved owner file(s) contain no `mmin +` sweep at all. Reports the
    checked/offending counts in the assertion message so a regression is diagnosable at a glance.
    """
    rows = _section_3_1_rows()
    checked = 0
    offenders = []
    for subpath, owner in rows:
        if owner.strip() == "see Clause 2":
            continue  # the grouped completeness row - verified separately below
        checked += 1
        files = _resolve_owner_files(owner)
        assert files is not None, f"could not extract an owner token from: {owner!r}"
        found = any(f.exists() and "mmin +" in f.read_text(encoding="utf-8") for f in files)
        if not found:
            offenders.append((subpath, owner, [str(f) for f in files]))

    assert not offenders, (
        f"{len(offenders)}/{checked} GC-coverage table rows claim an owner that does not "
        "actually contain a sweep for the claimed subpath:\n"
        + "\n".join(f"{s} -> owner {o!r}, checked {fs}" for s, o, fs in offenders)
    )


def test_gc_coverage_table_clause_2_grouped_row_sweeps_all_four_subpaths():
    """Companion to the table-driven scan above: the ONE row whose Owner column reads
    'see Clause 2' (grouped, for completeness) stands for 4 real subpaths - verify Clause 2's own
    prose actually sweeps all 4, so the shortcut is never itself a silent gap."""
    text = _contract_text()
    start = text.index("## Clause 2")
    end = text.index("\n## Clause 3", start)
    section = text[start:end]
    hits = len(re.findall(r"mmin \+", section))
    assert hits >= 4, (
        "Clause 2 must sweep all 4 grouped subpaths (visual/current/, visual/qa/, "
        f"visual/debug/, visual/screenshots/) - found only {hits} 'mmin +' occurrence(s)"
    )


def test_section_3_6_documents_a_fail_closed_correlated_criterion_for_integration_slug():
    """Renamed with its subject: `wave/<slug>/` -> `integration/<slug>/` when the wave grouping
    layer was removed. The assertions below check generic tokens (NEEDS_NEXT, fail-closed, the
    run-id correlation), never the literal word "wave", so the behavior they protect survived the
    rename unweakened - only this test's own name and messages were still naming the retired term.
    """
    norm = _norm(_contract_text())
    assert "3.6" in norm, "Expected a § 3.6 documenting the two known implementation gaps"
    # The corrected criterion must correlate against the run's OWN recorded status
    # (never a bare mtime check) and must fail closed on every unprovable case -
    # absent correlating file, unreadable status, or a still-mid-flight NEEDS_NEXT.
    assert "NEEDS_NEXT" in norm, (
        "§ 3.6 must name NEEDS_NEXT (the non-terminal run status) as a case the integration/<slug>/ "
        "criterion must NOT reap - this is exactly the live-paused-run danger being closed"
    )
    assert re.search(r"(?i)fail.closed", norm), (
        "§ 3.6 must state the integration/<slug>/ criterion is fail-closed on any unprovable "
        "condition"
    )
    assert re.search(r"(?i)run-\$\{slug\}\.json|run-<id>\.json", norm), (
        "§ 3.6's corrected criterion must correlate integration/<slug>/ against its OWN "
        "run-<id>.json, not act on mtime alone"
    )


# --------------------------------------------------------------------------- #
# Legacy-`wave/` migration case (wave-layer removal, spec 7.2 `migrate_project_state.sh` row): a
# project checked out before the rename has a legacy `.odoo-ai/wave/` dir on disk. The one-time
# Tier-2 migration helper must recognize that legacy top-level name and copy it into the RENAMED
# destination (`integration/`) - never leave it unclassified (silently skipped as "unknown", the
# generic fallback for a name in neither exhaustive table) and never copy it into a `wave/`
# destination that no longer matches any ISOLATE table row above. This is the migration PATH's
# own guard, distinct from the GC-coverage checks above (which cover the LIVE integration/<slug>/
# row, not a legacy on-disk directory from before the rename).
# --------------------------------------------------------------------------- #

MIGRATE_SCRIPT_PATH = PLUGIN / "scripts" / "lib" / "migrate_project_state.sh"


def test_migrate_project_state_wires_a_legacy_wave_to_integration_case():
    """Behavior protected: the Tier-2 state-root migration helper classifies a legacy top-level
    `.odoo-ai/wave/` entry distinctly from the live `integration` name (a same-name isolate
    classification cannot express a DESTINATION that differs from the SOURCE name), and its
    dispatch copies that legacy entry into `$isolate_dir/integration` - never into a `wave/`
    destination, which no longer appears in the ISOLATE table this file's other tests guard.

    Fails if the classifier has no `wave)` case, if that case resolves to the plain `isolate`
    tier (which cannot rename the destination), or if the dispatch for it does not target the
    isolate `integration` directory.
    """
    assert MIGRATE_SCRIPT_PATH.exists(), f"expected file missing: {MIGRATE_SCRIPT_PATH}"
    text = MIGRATE_SCRIPT_PATH.read_text(encoding="utf-8")

    assert re.search(r"\bwave\)\s*\n", text), (
        "migrate_project_state.sh's classifier must keep a `wave)` case for the pre-rename "
        "legacy top-level directory name - a checkout migrated before the rename still has one."
    )

    m = re.search(r"wave\)\s*\n(?:[^\n]*\n)*?\s*printf '([a-zA-Z0-9_-]+)\\n'", text)
    assert m, "could not find the classifier's return value for the `wave)` case"
    legacy_tier = m.group(1)
    assert legacy_tier != "isolate", (
        "the `wave)` case must NOT resolve to the plain `isolate` tier - the destination name "
        "differs from the legacy source name (wave -> integration), which the plain isolate "
        "dispatch (same name in and out) cannot express."
    )

    dispatch = re.search(
        re.escape(legacy_tier) + r"\)[\s\S]*?_tier2_copy_one[^\n]*", text
    )
    assert dispatch, f"could not find the dispatch case for tier {legacy_tier!r}"
    assert '"$isolate_dir/integration"' in dispatch.group(0), (
        f"the {legacy_tier!r} dispatch must copy the legacy wave/ dir into "
        '"$isolate_dir/integration" (the renamed ISOLATE destination), not a wave/ destination.'
    )
    assert '"$isolate_dir/wave"' not in dispatch.group(0), (
        "the legacy wave/ migration must not copy into a wave/ destination - that name no "
        "longer appears in the ISOLATE table since the rename."
    )
