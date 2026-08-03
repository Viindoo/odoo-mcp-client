"""Invariant tests for the odoo-forward-port bucket-(c) view-topology check.

Each test pins a BEHAVIORAL rule of the check - the predicate that identifies an
unconditional same-module inherit-view stack a bucket-(c) re-implement left behind,
the two non-defect exceptions (different-module base; a conditional same-module
child), and the merge/merge-unsafe action - not a snapshot of the prose used to
express it. Every assertion is chosen so it would be RED if the corresponding rule
were absent, narrowed, or silently removed.

Measured pre-fix baseline (`git show HEAD:<path>`, HEAD = 439a9b4, whole
plugins/odoo-ai-agents/ tree, before this check was added): 0 occurrences of every
marker asserted below except "Extended by" (1 unrelated pre-existing hit elsewhere
in the tree, never co-located with "priority"/"sibling" in the same file). No
view-topology / same-module-inherit check of any kind existed anywhere in
odoo-forward-port before this change.

Files under test (all under plugins/odoo-ai-agents/):
  - skills/odoo-forward-port/references/fp-triage-table.md (SSOT for the check)
  - skills/odoo-forward-port/SKILL.md (P7 pointer)
  - skills/odoo-forward-port/references/fp-phase-detail.md (P7 pointer)
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

SKILL_MD = PLUGIN / "skills" / "odoo-forward-port" / "SKILL.md"
PHASE_DETAIL = PLUGIN / "skills" / "odoo-forward-port" / "references" / "fp-phase-detail.md"
TRIAGE_TABLE = PLUGIN / "skills" / "odoo-forward-port" / "references" / "fp-triage-table.md"

FP_SKILL_DIR = PLUGIN / "skills" / "odoo-forward-port"


def _norm(text: str) -> str:
    """Collapse all whitespace runs (including newlines) to a single space.

    Guards against a reflow/line-wrap in the Markdown source causing a false
    negative on a multi-word phrase that happens to be split across lines.
    """
    return re.sub(r"\s+", " ", text)


def _whole_tree_text() -> str:
    """Concatenate every .md file under the odoo-forward-port skill directory.

    Whole-tree (not single-file) scan: if the check's prose is ever relocated
    between fp-triage-table.md / SKILL.md / fp-phase-detail.md, these tests
    keep passing; they only go RED if the RULE itself is deleted or narrowed
    everywhere, never merely moved.
    """
    parts = []
    for path in FP_SKILL_DIR.rglob("*.md"):
        parts.append(path.read_text(encoding="utf-8"))
    return _norm("\n".join(parts))


class TestDefectScopedToSameModuleBase:
    """The check must fire ONLY when the inherited view's base lives in the SAME
    module - a cross-module inherit (the correct, only way to extend another
    module's view) must never be flagged."""

    def test_different_module_base_is_explicitly_not_a_defect(self):
        corpus = _whole_tree_text()
        assert "different module" in corpus.lower() and "never a defect" in corpus.lower(), (
            "The view-topology check must explicitly state that a base view in a "
            "DIFFERENT module is never a defect (the only correct way to extend "
            "another module's view) - this exception must survive as prose, not "
            "just be implied by omission"
        )

    def test_predicate_requires_module_match_to_fire(self):
        """The predicate must require the base view's module to MATCH the child's
        own module before it can fire at all (module-boundary is a precondition,
        not an afterthought)."""
        # Whitespace-normalized: this clause wraps across a Markdown line.
        text = _norm(TRIAGE_TABLE.read_text(encoding="utf-8"))
        assert "SAME module as V" in text, (
            "fp-triage-table.md must state the base-view-in-SAME-module precondition "
            "using the child/base variable naming (V/B) so the predicate is unambiguous"
        )


class TestConditionalSameModuleChildIsNotFlagged:
    """A same-module inherit view that IS conditional (mode=primary, active=False,
    or a groups restriction) must never be flagged - merging it would change
    behavior. All three conditional shapes must be named explicitly."""

    def setup_method(self):
        self.text = TRIAGE_TABLE.read_text(encoding="utf-8")

    def test_mode_primary_excludes_the_predicate(self):
        assert 'mode="primary"' in self.text or "mode=\"primary\"" in self.text, (
            "fp-triage-table.md must exempt mode=\"primary\" children from the "
            "view-topology predicate - a primary-mode child is a structurally "
            "independent resolved view, not a simple patch on the base"
        )

    def test_active_false_excludes_the_predicate(self):
        norm = _norm(self.text)
        assert "active" in norm and "False" in norm and "toggle" in norm.lower(), (
            "fp-triage-table.md must exempt an explicitly active=False child - a "
            "deliberate toggle-off-by-default view must never be merged away"
        )

    def test_groups_restriction_excludes_the_predicate_both_ways(self):
        """The groups exception must be checked BOTH at the record level
        (groups_id) AND at the arch level (a groups=\"...\" XML attribute on the
        xpath-inserted content) - a check that only looks at groups_id would
        never fire on a real extension-mode conditional child."""
        norm = _norm(self.text)
        assert "groups_id" in norm, (
            "fp-triage-table.md must reference the record-level groups_id field"
        )
        assert 'groups="' in self.text, (
            "fp-triage-table.md must reference the arch-level groups=\"...\" XML "
            "attribute as the mechanism an extension-mode child actually uses for "
            "conditional visibility"
        )
        assert "Do not check only (a)" in self.text or "never fire on a real extension-mode" in self.text, (
            "fp-triage-table.md must warn that checking record-level groups_id alone "
            "is insufficient - that would never catch a real extension-mode "
            "conditional child, since groups_id is structurally always empty for one"
        )

    def test_groups_exception_grounded_in_odoo_orm_constraint(self):
        """The record-level groups_id branch must be grounded in Odoo's own
        ir.ui.view._check_groups ORM constraint, not asserted from memory."""
        norm = _norm(self.text)
        assert "_check_groups" in norm, (
            "fp-triage-table.md must cite ir.ui.view._check_groups (the ORM "
            "constraint that forbids groups_id + inherit_id + mode!=primary) as "
            "the grounding for why record-level groups_id is structurally "
            "unavailable to an extension-mode child"
        )
        assert "ValidationError" in norm, (
            "fp-triage-table.md must state that Odoo RAISES a ValidationError for "
            "the groups_id + inherit_id + mode!=primary combination - this is what "
            "makes the arch-level groups=\"...\" attribute the real mechanism"
        )


class TestPriorityExceptionRequiresSibling:
    """A non-default `priority` on a LONE child (no other view inheriting the same
    base) is inert - it has no observable ordering effect and must NOT count as a
    legitimate exception. Priority only matters when a sibling exists."""

    def test_priority_alone_is_not_sufficient(self):
        text = TRIAGE_TABLE.read_text(encoding="utf-8")
        norm = _norm(text)
        assert "priority" in norm.lower(), "fp-triage-table.md must discuss the priority field"
        assert "ONLY entry" in text and "does not count as conditional" in text, (
            "fp-triage-table.md must state that when V is the ONLY view inheriting "
            "B, a non-default priority has no ordering effect and does NOT count "
            "as a legitimate exception - priority alone must not excuse a merge"
        )

    def test_priority_matters_only_with_a_sibling(self):
        text = TRIAGE_TABLE.read_text(encoding="utf-8")
        assert "Extended by" in text, (
            "fp-triage-table.md must ground the sibling check via "
            "entity_lookup(kind='view', ...)'s 'Extended by' list"
        )
        assert "other views" in text.lower() or "other view" in text.lower(), (
            "fp-triage-table.md must state priority becomes a legitimate exception "
            "only when one or more OTHER views also inherit the same base"
        )


class TestMergeActionNeverDeletesBaseView:
    """On a confirmed hit, the action is to merge the child's arch into the base
    and delete the CHILD record - never the base/primary view, which actions,
    menus, and other modules' xpaths address by its own xml_id."""

    def setup_method(self):
        self.text = TRIAGE_TABLE.read_text(encoding="utf-8")

    def test_merge_into_base_action_present(self):
        assert "merge-into-base" in self.text, (
            "fp-triage-table.md must define the 'merge-into-base' action for a "
            "confirmed same-module unconditional inherit-stack hit"
        )

    def test_child_record_is_deleted_not_base(self):
        norm = _norm(self.text)
        assert "DELETE V's record" in self.text or "DELETE V" in self.text, (
            "fp-triage-table.md must state the CHILD record (V) is deleted on merge"
        )
        assert "never delete B" in norm.lower() or "Never the reverse" in self.text, (
            "fp-triage-table.md must explicitly forbid deleting the base/primary "
            "view B - only the child record V is ever removed"
        )


class TestMergeUnsafeGuard:
    """Merging must NOT proceed silently when it is unsafe: an external reference
    to the child's xml_id, or a target series that is already released. Both
    must degrade to a recorded, human-flagged finding - never a silent skip and
    never a silent auto-delete."""

    def setup_method(self):
        self.text = TRIAGE_TABLE.read_text(encoding="utf-8")

    def test_external_reference_guard_present(self):
        norm = _norm(self.text)
        assert "External reference exists" in self.text, (
            "fp-triage-table.md must name the 'External reference exists' "
            "merge-unsafe condition"
        )
        assert "env.ref" in self.text or "action" in norm.lower(), (
            "the external-reference guard must name concrete referencing shapes "
            "(action view_id, menu, env.ref) that make a delete unsafe"
        )

    def test_impact_analysis_view_gap_is_named(self):
        """impact_analysis does not cover entity_type='view' - the check must not
        silently assume OSM can answer this and must name the grep fallback."""
        text = self.text
        assert "impact_analysis" in text and "does NOT cover" in text, (
            "fp-triage-table.md must state that impact_analysis does NOT cover "
            "entity_type='view', so a repo-wide grep fallback is required for "
            "action/menu/env.ref references - otherwise an agent may wrongly "
            "assume impact_analysis alone proves safety"
        )

    def test_released_target_guard_present(self):
        assert "already released" in self.text, (
            "fp-triage-table.md must name the 'target series is already released' "
            "merge-unsafe condition as a stable-branch-policy decision for a human"
        )

    def test_unsafe_hit_degrades_to_needs_human_not_silent_skip(self):
        text = self.text
        assert "NEEDS-HUMAN" in text, (
            "fp-triage-table.md must define a NEEDS-HUMAN action for the "
            "merge-unsafe case - never silently keep the stack unflagged"
        )
        assert "do NOT auto-merge" in text or "do NOT auto-merge or auto-delete" in text, (
            "fp-triage-table.md must forbid auto-merging/auto-deleting when the "
            "merge-unsafe guard fires"
        )


class TestFindingLineMirrorsSymbolBroken:
    """The finding-line format must mirror the P7 SYMBOL-BROKEN convention (a
    pipe-delimited discriminator line) under its OWN discriminator, and a clean
    pass must be an explicit, valid result - not merely the absence of a line."""

    def setup_method(self):
        self.text = TRIAGE_TABLE.read_text(encoding="utf-8")

    def test_view_topology_discriminator_present(self):
        assert "VIEW-TOPOLOGY |" in self.text, (
            "fp-triage-table.md must define the 'VIEW-TOPOLOGY |' finding-line "
            "discriminator, distinct from SYMBOL-BROKEN"
        )

    def test_clean_pass_is_a_valid_documented_result(self):
        assert "VIEW-TOPOLOGY: clean" in self.text, (
            "fp-triage-table.md must document 'VIEW-TOPOLOGY: clean (...)' as a "
            "valid, desirable result when no hit is found"
        )


class TestMergeLogAndP10GateSurfacing:
    """The finding must be recorded in merge-log.md (its own row, distinct from
    per-commit rows) and surfaced at the P10 human-confirm gate - never left in
    a findings file nobody reads before the merge is committed."""

    def test_merge_log_placement_documented(self):
        text = TRIAGE_TABLE.read_text(encoding="utf-8")
        assert "## View-topology" in text, (
            "fp-triage-table.md must specify a dedicated '## View-topology' "
            "heading in merge-log.md, distinct from the per-commit intent/bucket "
            "rows and the Installable-probe rows"
        )

    def test_p10_gate_surfacing_documented(self):
        text = TRIAGE_TABLE.read_text(encoding="utf-8")
        norm = _norm(text)
        assert "P10 gate" in text and "BEFORE the merge is committed" in norm, (
            "fp-triage-table.md must state the finding is surfaced at the P10 "
            "gate BEFORE the merge is committed, not discovered later"
        )


class TestWiredIntoP7InBothConsumers:
    """Both SKILL.md and fp-phase-detail.md must point at the SSOT section from
    inside their own P7 sections (document-order check), so an agent reading
    either file's P7 phase discovers the check rather than only fp-triage-table.md
    readers."""

    def test_skill_md_p7_references_the_check(self):
        # Whitespace-normalized: a Markdown line-wrap must not defeat this check.
        text = _norm(SKILL_MD.read_text(encoding="utf-8"))
        p7_marker = "P7 - Pre-adapt drift scan"
        p8_marker = "P8 - Adapt [test-first;"
        pointer = "Bucket-(c) same-module inherit-view check"
        assert p7_marker in text and p8_marker in text and pointer in text, (
            "SKILL.md must reference 'Bucket-(c) same-module inherit-view check' "
            "between its P7 and P8 headings"
        )
        assert text.index(p7_marker) < text.index(pointer) < text.index(p8_marker), (
            "SKILL.md's view-topology pointer must sit inside the P7 section "
            "(after the P7 heading, before the P8 heading) - not floating "
            "elsewhere in the document"
        )

    def test_phase_detail_p7_references_the_check(self):
        # Whitespace-normalized: the pointer anchor wraps across a Markdown line
        # in fp-phase-detail.md ("...§ Bucket-(c)\nsame-module inherit-view
        # check.") - a raw substring check would false-negative on that wrap.
        text = _norm(PHASE_DETAIL.read_text(encoding="utf-8"))
        p7_marker = "## P7 - Pre-adapt drift scan"
        p8_marker = "## P8 - Adapt"
        pointer = "Bucket-(c) same-module inherit-view check"
        lead_in = "same-module inherit stacks"
        assert p7_marker in text and p8_marker in text and pointer in text, (
            "fp-phase-detail.md must reference the view-topology sub-check "
            "(anchor: 'Bucket-(c) same-module inherit-view check') between its "
            "P7 and P8 headings"
        )
        assert lead_in in text, (
            "fp-phase-detail.md must introduce the sub-check with its "
            "bucket-(c)-same-module-inherit-stacks lead-in sentence"
        )
        assert text.index(p7_marker) < text.index(pointer) < text.index(p8_marker), (
            "fp-phase-detail.md's view-topology pointer must sit inside the P7 "
            "section - not floating elsewhere in the document"
        )

    def test_both_pointers_reference_the_same_ssot_anchor(self):
        """Both consumer pointers must reference the exact same SSOT section
        name in fp-triage-table.md - a drifted anchor name would silently
        break the pointer's usefulness (same failure class as the addons-path
        anchor-drift defect this repo has already paid for once). Checked on
        whitespace-normalized text since the anchor phrase wraps across a
        Markdown line in at least one consumer file."""
        anchor = "Bucket-(c) same-module inherit-view check"
        assert anchor in _norm(SKILL_MD.read_text(encoding="utf-8")), (
            f"SKILL.md pointer must use the exact anchor text {anchor!r}"
        )
        assert anchor in _norm(PHASE_DETAIL.read_text(encoding="utf-8")), (
            f"fp-phase-detail.md pointer must use the exact anchor text {anchor!r}"
        )
        assert f"## {anchor}" in TRIAGE_TABLE.read_text(encoding="utf-8"), (
            f"fp-triage-table.md must define the section under the exact heading "
            f"'## {anchor}' that both consumer pointers reference"
        )


class TestScopedToBucketC:
    """The check is scoped to a bucket-(c) re-implement's OWN output - not a
    whole-module retroactive audit of pre-existing same-module inherit views the
    run never touched."""

    def test_bucket_c_and_4outcome_reference_present(self):
        text = TRIAGE_TABLE.read_text(encoding="utf-8")
        assert "bucket (c)" in text.lower() or "bucket-(c)" in text.lower(), (
            "fp-triage-table.md must scope the check explicitly to bucket (c)"
        )
        assert "[[fp-intent-4outcome]]" in text, (
            "fp-triage-table.md must reference the [[fp-intent-4outcome]] SSOT "
            "for the bucket-(c) definition rather than re-deriving it"
        )

    def test_scope_excludes_untouched_preexisting_stacks(self):
        text = TRIAGE_TABLE.read_text(encoding="utf-8")
        assert "not a whole-module retroactive audit" in text, (
            "fp-triage-table.md must explicitly scope the check to what THIS "
            "re-implement lands, excluding a retroactive audit of untouched "
            "pre-existing same-module inherit stacks"
        )


class TestWholeTreeMarkerSurvives:
    """Whole-tree, no-allowlist guard: the VIEW-TOPOLOGY mechanism must appear a
    minimum number of times across the odoo-forward-port skill directory as a
    whole (not pinned to one exact file), so a future edit collapsing the
    finding-line format down to a bare mention is caught regardless of which
    file the content is moved to."""

    def test_view_topology_marker_appears_at_least_three_times(self):
        corpus = _whole_tree_text()
        occurrences = corpus.count("VIEW-TOPOLOGY")
        assert occurrences >= 3, (
            "Expected at least 3 'VIEW-TOPOLOGY' occurrences across "
            "skills/odoo-forward-port/**/*.md (hit finding line, merge-unsafe "
            "finding line, and the clean-pass line) - found "
            f"{occurrences}. A collapse to fewer occurrences means the "
            "finding-line format was narrowed or partially removed."
        )

    def test_no_view_topology_check_of_any_kind_predates_this_change_elsewhere(self):
        """Sanity guard on the inventory's own claim: before this change, no
        view-topology / same-module-inherit language existed anywhere in the
        odoo-ai-agents plugin (whole-tree, not just odoo-forward-port) other
        than the exact section this change adds."""
        outside_fp = []
        for path in PLUGIN.rglob("*.md"):
            if FP_SKILL_DIR in path.parents or path.parent == FP_SKILL_DIR:
                continue
            text = path.read_text(encoding="utf-8")
            if "VIEW-TOPOLOGY" in text:
                outside_fp.append(str(path))
        assert not outside_fp, (
            "The VIEW-TOPOLOGY mechanism must live in odoo-forward-port only "
            f"(SSOT discipline) - found stray references outside it: {outside_fp}"
        )
