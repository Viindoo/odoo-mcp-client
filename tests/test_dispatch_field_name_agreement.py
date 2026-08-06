"""Guard five caller/callee dispatch-brief field-name defects (X-31, X-34, X-35,
X-44, X-45 in the odoo-ai-agents contract-hardening audit).

The shared failure mode across all five: a dispatching skill's brief used a
field name the RECEIVING agent's own contract does not recognize (a different
literal key, a different shape, or a field silently omitted). Each test below
pins the caller side to the callee's own documented contract, so a future edit
that renames one side without the other fails here instead of stalling a live
dispatch on a `NEEDS_CONTEXT`/`BLOCKED` self-check.

Mirrors the grep-the-prose idiom of `tests/test_dispatch_brief.py` /
`tests/test_git_rebase_intent_race.py`: plain-text assertions over the
Markdown body, no YAML/frontmatter parsing.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

DIFF_COMPARATOR_AGENT = PLUGIN / "agents" / "odoo-diff-comparator.md"
GAP_ANALYZER_AGENT = PLUGIN / "agents" / "odoo-gap-analyzer.md"
QA_TESTER_AGENT = PLUGIN / "agents" / "odoo-qa-tester.md"
BACKEND_DEBUGGER_AGENT = PLUGIN / "agents" / "odoo-backend-debugger.md"
UI_DEBUGGER_AGENT = PLUGIN / "agents" / "odoo-ui-debugger.md"

UPG_PHASE_DETAIL = (
    PLUGIN / "skills" / "odoo-modules-upgrade" / "references" / "upg-phase-detail.md"
)
RB_PHASE_DETAIL = (
    PLUGIN / "skills" / "odoo-git-rebase" / "references" / "rb-phase-detail.md"
)
GAP_ANALYSIS_SKILL = PLUGIN / "skills" / "odoo-gap-analysis" / "SKILL.md"
DEBUG_SKILL = PLUGIN / "skills" / "odoo-debug" / "SKILL.md"
ACCEPTANCE_SKILL = PLUGIN / "skills" / "odoo-acceptance" / "SKILL.md"


def _section(text, start_heading, end_heading):
    """Slice `text` from `start_heading` (inclusive) up to `end_heading`
    (exclusive) - mirrors the bounded-section idiom in
    tests/test_git_rebase_intent_race.py."""
    start = text.index(start_heading)
    end = text.index(end_heading, start)
    return text[start:end]


# ---------------------------------------------------------------------------
# X-31 / X-45 (upgrade cluster) - odoo-modules-upgrade P2's odoo-diff-comparator
# brief must carry the agent's own upgrade-mode required fields, spelled
# exactly as the agent's own Inputs table + Brief self-check documents them:
# diff_scope, source_version, target_version, slug, repo_root.
# ---------------------------------------------------------------------------
class TestUpgradeDiffComparatorBrief:
    comparator_text = DIFF_COMPARATOR_AGENT.read_text(encoding="utf-8")
    phase_text = UPG_PHASE_DETAIL.read_text(encoding="utf-8")

    def _p2_block(self):
        return _section(
            self.phase_text,
            "### P2 - odoo-diff-comparator brief (per module)",
            "### P2 - odoo-gap-analysis dispatch",
        )

    def test_agent_declares_upgrade_mode_required_fields(self):
        """Sanity: the agent's own Brief self-check still names these fields as
        upgrade-mode required, so this test tracks the real contract, not a
        frozen guess."""
        assert (
            "upgrade mode's `diff_scope` + `repo_root` + "
            "`source_version`/`target_version`" in self.comparator_text
            and "`slug` for output paths" in self.comparator_text
        ), (
            "agents/odoo-diff-comparator.md's Brief self-check no longer names "
            "diff_scope/repo_root/source_version/target_version/slug as the "
            "upgrade-mode required fields - update this test's fixture, not just "
            "the caller side"
        )

    def test_p2_brief_carries_slug_and_repo_root(self):
        """X-31: the P2 brief previously sent no slug/repo_root at all, so the
        agent's own write-path template (<slug>) and mandated local-source read
        (repo_root) were unresolvable."""
        block = self._p2_block()
        assert "slug: <src>-<tgt>-<cluster>" in block, (
            "P2 odoo-diff-comparator brief must supply `slug:` (X-31) - without "
            "it the agent's <slug> write-path template cannot resolve"
        )
        assert "repo_root: <absolute path to the repository root>" in block, (
            "P2 odoo-diff-comparator brief must supply `repo_root:` (X-31) - "
            "without it the agent's mandated local-source Read/Grep pass has no root"
        )

    def test_p2_brief_uses_agents_own_field_spellings(self):
        """X-45: MODULE PATH / SOURCE VERSION / TARGET VERSION (space-separated,
        title case) never match any key in the agent's own Inputs table - the
        agent's real fields are diff_scope / source_version / target_version."""
        block = self._p2_block()
        for field in ("diff_scope", "source_version", "target_version"):
            assert f"{field}:" in block, (
                f"P2 odoo-diff-comparator brief must spell its field `{field}:` "
                "exactly as the agent's own Inputs table documents it (X-45)"
            )
        for stale in ("MODULE PATH:", "SOURCE VERSION:", "TARGET VERSION:"):
            assert stale not in block, (
                f"P2 odoo-diff-comparator brief still carries the stale "
                f"`{stale}` key the agent's contract never declared (X-45)"
            )


# ---------------------------------------------------------------------------
# X-34 (rebase cluster) - odoo-git-rebase P3 + P10 must send `intents_dir`
# (a directory), not `INTENT_FILES` (a glob) - the agent's own contract is
# `intents_dir` in both dispatches.
# ---------------------------------------------------------------------------
class TestRebaseDiffComparatorIntentsDir:
    comparator_text = DIFF_COMPARATOR_AGENT.read_text(encoding="utf-8")
    phase_text = RB_PHASE_DETAIL.read_text(encoding="utf-8")

    def test_agent_declares_intents_dir(self):
        assert (
            "`intents_dir` | (rebase mode) Path to `<ISOLATE_DIR>/git-rebase/<slug>/intents/`"
            in self.comparator_text
        ), (
            "agents/odoo-diff-comparator.md no longer documents `intents_dir` as "
            "its rebase-mode field - update this test's fixture, not just the caller side"
        )

    def test_no_stale_intent_files_key_anywhere(self):
        assert "INTENT_FILES" not in self.phase_text, (
            "rb-phase-detail.md still emits the stale `INTENT_FILES` glob key "
            "(X-34) - the agent's own contract requires `intents_dir` (a directory)"
        )

    def test_p3_dispatch_uses_intents_dir_as_a_directory(self):
        block = _section(
            self.phase_text, "### P3 dispatch: odoo-diff-comparator", "## P4"
        )
        assert "intents_dir: <ISOLATE_DIR>/git-rebase/<slug>/intents/" in block, (
            "P3 odoo-diff-comparator brief must send `intents_dir:` as a "
            "directory path (no glob suffix), matching the agent's contract (X-34)"
        )
        assert "*.md" not in block, (
            "P3 intents_dir value must be the directory itself, not a glob (X-34)"
        )

    def test_p10_dispatch_uses_intents_dir_as_a_directory(self):
        block = _section(
            self.phase_text,
            "#### P10 dispatch: odoo-diff-comparator",
            "### B3 - conditional instance verify",
        )
        assert "intents_dir: <ISOLATE_DIR>/git-rebase/<slug>/intents/" in block, (
            "P10 odoo-diff-comparator brief must send `intents_dir:` as a "
            "directory path (no glob suffix), matching the agent's contract (X-34)"
        )
        assert "*.md" not in block, (
            "P10 intents_dir value must be the directory itself, not a glob (X-34)"
        )


# ---------------------------------------------------------------------------
# X-35 (gap-analysis) - odoo-gap-analyzer's LOCKED output is always
# `<OUTPUT_DIR>/gap-matrix.jsonl` with collision avoidance via a distinct
# OUTPUT_DIR per worker; the skill must dispatch a per-cluster DIRECTORY as
# OUTPUT_DIR and read the SAME fixed filename back, never a per-cluster
# FILENAME that collides with every other concurrent worker's fixed write.
# ---------------------------------------------------------------------------
class TestGapAnalysisOutputPathAgreement:
    agent_text = GAP_ANALYZER_AGENT.read_text(encoding="utf-8")
    skill_text = GAP_ANALYSIS_SKILL.read_text(encoding="utf-8")

    def test_agent_locks_gap_matrix_filename(self):
        assert "`<OUTPUT_DIR>/gap-matrix.jsonl`" in self.agent_text, (
            "agents/odoo-gap-analyzer.md no longer locks `gap-matrix.jsonl` as "
            "its output filename - update this test's fixture, not just the "
            "skill side (the agent's Output contract is the SSOT for X-35)"
        )

    def test_skill_passes_output_dir_not_a_bare_filename(self):
        assert "OUTPUT_DIR:" in self.skill_text, (
            "odoo-gap-analysis/SKILL.md must pass an explicit `OUTPUT_DIR:` "
            "field to each odoo-gap-analyzer worker (X-35)"
        )
        assert "<NN>-<area>.jsonl" not in self.skill_text, (
            "odoo-gap-analysis/SKILL.md must not name a per-cluster FILE "
            "(`<NN>-<area>.jsonl`) directly - concurrent workers would then race "
            "on the agent's fixed `gap-matrix.jsonl` inside a SHARED directory "
            "(X-35); OUTPUT_DIR must be a distinct per-cluster DIRECTORY instead"
        )

    def test_skill_reads_back_the_agents_locked_filename(self):
        assert "clusters/<NN>-<area>/gap-matrix.jsonl" in self.skill_text, (
            "odoo-gap-analysis/SKILL.md's synthesis step must read each "
            "worker's shard back from the agent's own LOCKED filename "
            "(gap-matrix.jsonl) inside a per-cluster directory (X-35)"
        )


# ---------------------------------------------------------------------------
# X-44 (debug) - odoo-debug's dispatch template must forward USER LANGUAGE to
# the debugger agents, which already consume it (unlike odoo-coding, which
# already forwards it).
# ---------------------------------------------------------------------------
class TestDebugForwardsUserLanguage:
    debug_text = DEBUG_SKILL.read_text(encoding="utf-8")
    backend_debugger_text = BACKEND_DEBUGGER_AGENT.read_text(encoding="utf-8")
    ui_debugger_text = UI_DEBUGGER_AGENT.read_text(encoding="utf-8")

    def test_both_debugger_agents_consume_user_language(self):
        for name, text in (
            ("odoo-backend-debugger.md", self.backend_debugger_text),
            ("odoo-ui-debugger.md", self.ui_debugger_text),
        ):
            assert "USER LANGUAGE:" in text, (
                f"agents/{name} no longer documents consuming `USER LANGUAGE:` - "
                "update this test's fixture, not just the caller side"
            )

    def test_dispatch_template_forwards_user_language(self):
        block = _section(
            self.debug_text,
            "**Agent dispatch - prompt template (use verbatim, fill the brackets):**",
            "### Phase 3 - Verify (adversarial)",
        )
        assert "USER LANGUAGE:" in block, (
            "odoo-debug/SKILL.md's dispatch-prompt template never forwards "
            "`USER LANGUAGE:` to the dispatched debugger agent (X-44) - a "
            "non-English chat session loses language-mirroring at the debug layer"
        )


# ---------------------------------------------------------------------------
# X-48 (acceptance) - odoo-acceptance Phase 2b must pass SLUG explicitly to
# odoo-qa-tester instead of relying on it stripping the suffix off REPORT_PATH.
# ---------------------------------------------------------------------------
class TestAcceptancePassesSlugExplicitly:
    acceptance_text = ACCEPTANCE_SKILL.read_text(encoding="utf-8")
    qa_tester_text = QA_TESTER_AGENT.read_text(encoding="utf-8")

    def test_qa_tester_accepts_an_explicit_slug_override(self):
        assert (
            "recover it by stripping the `-acceptance-report.md` suffix off "
            "`REPORT_PATH`'s filename if it is not separately restated in "
            "your brief" in self.qa_tester_text
        ), (
            "agents/odoo-qa-tester.md no longer documents the "
            "restated-in-your-brief SLUG override - update this test's "
            "fixture, not just the caller side"
        )

    def test_phase_2b_passes_slug_explicitly(self):
        block = _section(
            self.acceptance_text,
            "## Phase 2b - LIVE channel",
            "## Phase 3 - ADJUDGE + fix-loop",
        )
        assert "SLUG: <slug>" in block, (
            "odoo-acceptance/SKILL.md Phase 2b must pass `SLUG:` explicitly to "
            "odoo-qa-tester (X-48) instead of relying on filename-stripping"
        )
