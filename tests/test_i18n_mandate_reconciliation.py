"""Behavioral guard for the PR #189 runtime-review i18n mandate fixes.

A runtime role-play (docs external to this repo) executing odoo-modules-upgrade and
odoo-forward-port literally, phase by phase, found the i18n mandate self-contradictory and two of
its escape hatches unusable:

  F1 (BLOCKS) - `snippets/i18n-mandate-contract.md` E3 said "no target language resolvable ->
  RECORD and PROCEED", while `skills/odoo-i18n/SKILL.md`'s P0 gate said "any of the three inputs
  missing (incl. TARGET LANGUAGES) -> fall back to the standalone STOP" - opposite instructions
  for the SAME case, both authored in the same PR. A modules-upgrade run with no configured
  language, and no procedure of its own to resolve one, hit both.

  F2 (WRONG) - escape E2 ("no i18n/ dir AND the trigger table fires zero signals") pointed at a
  trigger table headed "(forward-port condition 1 only)" that scans a forward-port-only artifact
  path - E2 could never be evaluated for a modules-upgrade module, even though the scenario it
  covers (a module shipping no catalogs) is common in upgrades too.

  F3 (AMBIGUOUS) - neither E2 nor the mandate defined HOW to check "the module ships no i18n/
  directory" anywhere in the plugin - one agent would check the worktree, another would ask OSM
  (which does not index .po/.pot at all), a third would guess.

  F6/DEGRADES (regression hunt) - forward-port's P9.5 derived TARGET LANGUAGES only from
  source-side <lang>.po filenames; a module gaining its first-ever translatable string has zero
  such files, so under the old odoo-i18n gate text this reintroduced a per-invocation human STOP -
  exactly the deadlock the mandate exists to prevent.

The resolution direction (this fix): a MANDATED invocation NEVER opens a fresh interactive human
STOP. TARGET LANGUAGES is best-effort - odoo-i18n's own P0 tiers 2-4 (registry / .po-filename
inference / live instance query) still run against whatever data IS available even when the
caller has nothing to pass; only once ALL of tiers 1-4 are empty does escape E3 fire (record +
PROCEED, translate nothing - never STOP). WORKTREE_PATH / INSTANCE_HANDLE-or-SELF_PROVISION stay
hard preconditions of "Mandated" - missing either is a caller-contract violation, but the
response is BLOCKED (returned to the caller's own gate), not a fresh interactive STOP either.

Each test below fails for exactly one reason: the corresponding piece of the fix was removed,
reworded past detection, or reverted to the old contradictory/unusable text.

Files under test (all under plugins/odoo-ai-agents/):
  - snippets/i18n-mandate-contract.md
  - skills/odoo-i18n/SKILL.md
  - skills/odoo-modules-upgrade/references/upg-phase-detail.md
  - skills/odoo-forward-port/SKILL.md

Run: python -m pytest tests/test_i18n_mandate_reconciliation.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

MANDATE = PLUGIN / "snippets" / "i18n-mandate-contract.md"
I18N_SKILL = PLUGIN / "skills" / "odoo-i18n" / "SKILL.md"
UPG_PHASE_DETAIL = PLUGIN / "skills" / "odoo-modules-upgrade" / "references" / "upg-phase-detail.md"
FP_SKILL = PLUGIN / "skills" / "odoo-forward-port" / "SKILL.md"
FP_PHASE_DETAIL = PLUGIN / "skills" / "odoo-forward-port" / "references" / "fp-phase-detail.md"


def _norm(text: str) -> str:
    """Collapse all whitespace runs (including Markdown line-wraps) to a single space.

    A literal multi-word phrase in these files can legitimately wrap across a source line break;
    a raw substring `in` check is brittle against that reflow (this test family in this repo has
    already caught more than one silent tautology of exactly that shape - see
    test_odoo_i18n.py's `_normalize_ws` and test_upg_deferred_work_reconciliation.py's `_norm`).
    """
    return re.sub(r"\s+", " ", text)


def _read(path: Path) -> str:
    assert path.exists(), f"expected file not found: {path}"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# FIX 1 (F1/BLOCKS) - the contradiction is resolved in ONE direction: a
# MANDATED invocation never opens a fresh interactive STOP; missing TARGET
# LANGUAGES alone falls through to E3 (record + proceed), never a stop.
# ---------------------------------------------------------------------------

class TestFix1MandateContradictionResolved:
    def test_mandate_e3_status_is_proceed_not_blocked_and_names_odoo_i18n_own_attempt(self):
        """i18n-mandate-contract.md E3 row must stay non-blocking (proceed), AND its condition
        text must reflect that `odoo-i18n` ITSELF attempts inference (tiers 2-4) before E3 fires
        - not merely 'the caller passed none' (the old wording, which implied the caller was
        solely responsible for resolving a language it has no mechanism to resolve)."""
        text = _read(MANDATE)
        for line in text.splitlines():
            if line.strip().startswith("| E3 "):
                assert line.strip().endswith("| proceed |"), (
                    f"E3's escape row must end in status 'proceed' (non-blocking), got: {line!r}"
                )
                assert "`odoo-i18n` itself could infer none" in line, (
                    f"E3's condition text must state odoo-i18n ITSELF attempted inference (tiers "
                    f"2-4) before declaring this escape, not just 'the caller passed none': {line!r}"
                )
                return
        raise AssertionError("i18n-mandate-contract.md must have an E3 row in the escape table")

    def test_i18n_skill_no_longer_stops_standalone_on_missing_target_languages(self):
        """The OLD contradictory instruction - ANY of the three inputs missing (including
        TARGET LANGUAGES) falls back to the standalone STOP - must be gone. This is the exact
        phrase F1 flagged as directly opposing i18n-mandate-contract.md's E3 'record + proceed'."""
        norm = _norm(_read(I18N_SKILL))
        banned = "any of those three inputs missing -> fall back to the standalone stop"
        assert banned not in norm.lower(), (
            "odoo-i18n/SKILL.md must not fall back to a standalone STOP merely because TARGET "
            "LANGUAGES (or any one of three bundled inputs) is missing - that is the literal "
            "contradiction with i18n-mandate-contract.md's E3 'record + proceed' the PR review "
            "found (F1). A mandated invocation must never open a fresh per-invocation STOP."
        )

    def test_i18n_skill_mandated_no_longer_requires_target_languages_as_precondition(self):
        """TARGET LANGUAGES must NOT gate whether a dispatch counts as 'Mandated' (do-not-stop)
        - only WORKTREE_PATH and an INSTANCE_HANDLE/SELF_PROVISION do. Requiring explicit TARGET
        LANGUAGES up front is exactly what forces a caller with no language to fall through to a
        stop, even though it may be resolvable by odoo-i18n's own tiers 2-4."""
        norm = _norm(_read(I18N_SKILL))
        banned = "a caller dispatched you as a required step and supplied explicit `target languages`"
        assert banned not in norm.lower(), (
            "odoo-i18n/SKILL.md must not require explicit TARGET LANGUAGES as a precondition of "
            "the 'Mandated' (do-not-stop) branch - TARGET LANGUAGES is best-effort; only "
            "WORKTREE_PATH and INSTANCE_HANDLE/SELF_PROVISION gate Mandated status"
        )

    def test_i18n_skill_p0_tiers_still_run_when_caller_omits_target_languages(self):
        """The P0 language-resolution paragraph must not claim the caller MUST supply an
        explicit list - tiers 2-4 (registry / po-filename inference / instance query) must still
        run themselves against whatever IS available, so a resolvable-but-unpassed language is
        never silently skipped (the failure mode explicitly called out alongside F1: 'silently
        translating nothing is also a failure if a language WAS resolvable and merely not
        passed')."""
        text = _read(I18N_SKILL)
        norm = _norm(text)
        banned = "the caller must pass explicit `target languages`"
        assert banned not in norm.lower(), (
            "odoo-i18n/SKILL.md's P0 tier text must not require the caller to supply TARGET "
            "LANGUAGES unconditionally - P0's own tiers 2-4 must still run when the caller has "
            "none to give"
        )
        assert "tiers 2-4" in norm.lower() and "still run" in norm.lower(), (
            "odoo-i18n/SKILL.md must explicitly state tiers 2-4 still run for a mandated caller "
            "that supplied no explicit TARGET LANGUAGES"
        )

    def test_i18n_skill_missing_worktree_or_instance_is_blocked_not_a_fresh_stop(self):
        """Missing WORKTREE_PATH or INSTANCE_HANDLE/SELF_PROVISION is a genuine caller-contract
        violation (obligations 1-2), but the response must be BLOCKED (returned to the caller's
        own gate), not a brand-new interactive STOP - a mandated invocation must never open one,
        for ANY reason."""
        norm = _norm(_read(I18N_SKILL))
        assert "caller-contract violation" in norm, (
            "odoo-i18n/SKILL.md must name a missing WORKTREE_PATH / INSTANCE_HANDLE as a "
            "caller-contract violation distinct from an unresolvable language"
        )
        assert "status: blocked" in norm.lower(), (
            "odoo-i18n/SKILL.md must return status: BLOCKED (not a fresh interactive STOP) when "
            "the caller's mandate obligations 1-2 (WORKTREE_PATH / INSTANCE_HANDLE) are violated"
        )

    def test_mandate_and_skill_agree_on_e3_wording_in_the_gate_fold_paragraph(self):
        """Both files must use the identical E3 record string, AND odoo-i18n/SKILL.md's own
        Mandated gate-fold paragraph (not just its pre-existing P0 tier text) must be the one that
        states it - proving the gate-fold paragraph itself (the one that used to contradict E3)
        now resolves to E3, not to a fresh stop."""
        record = "i18n: not-applicable (no target language resolvable from tiers 1-4)"
        assert record in _read(MANDATE), f"i18n-mandate-contract.md must carry E3's record verbatim: {record!r}"

        text = _read(I18N_SKILL)
        start = text.index("**Then gate")
        end = text.index("**P1 - Glossary build", start)
        gate_fold_section = text[start:end]
        assert record in gate_fold_section, (
            "odoo-i18n/SKILL.md's 'Then gate' Mandated-branch paragraph itself (not just the "
            "earlier P0 tier text) must state the SAME E3 record verbatim - this is the exact "
            f"paragraph that used to contradict it: {record!r}"
        )

    def test_upg_target_languages_field_allows_omission(self):
        """upg-phase-detail.md's P5.7 dispatch brief forbade the caller from ever leaving
        odoo-i18n to resolve anything ('never leave odoo-i18n to resolve a default') and gave the
        orchestrator no resolution procedure of its own (F1's second half) - it must now
        explicitly allow omitting TARGET LANGUAGES when this run has none, deferring to
        odoo-i18n's own tiers."""
        norm = _norm(_read(UPG_PHASE_DETAIL))
        assert "else omit the field entirely" in norm, (
            "upg-phase-detail.md's P5.7 TARGET LANGUAGES field must allow omission when this "
            "orchestrator has no explicit list - it has no tiered resolver of its own, so it must "
            "defer to odoo-i18n's own P0 tiers rather than being stuck unable to satisfy a "
            "mandatory field"
        )


# ---------------------------------------------------------------------------
# FIX 2 (F2/WRONG) - escape E2 must be evaluable in BOTH flows: the trigger
# table must not be headed "forward-port condition 1 only" and must name a
# modules-upgrade scan target too.
# ---------------------------------------------------------------------------

class TestFix2E2EvaluableInBothFlows:
    def test_trigger_table_not_scoped_forward_port_only(self):
        text = _read(MANDATE)
        assert "(forward-port condition 1 only)" not in text, (
            "i18n-mandate-contract.md's Trigger table must not be headed 'forward-port condition "
            "1 only' - that heading made E2 clause 2 unevaluable for modules-upgrade, even though "
            "nothing else in the escape table marks E2 as forward-port-only (unlike E4, which is "
            "explicitly so-scoped)"
        )
        assert "BOTH flows" in text, (
            "i18n-mandate-contract.md's Trigger table heading must state it applies to BOTH flows"
        )

    def test_trigger_table_names_a_modules_upgrade_scan_target_and_keeps_forward_ports(self):
        """The trigger table must give modules-upgrade its own concrete, reachable scan target -
        not just remove the forward-port-only label and leave modules-upgrade with nothing to
        scan - AND must not lose forward-port's own existing, working scan target in the process."""
        norm = _norm(_read(MANDATE))
        assert "modules-upgrade:" in norm, (
            "i18n-mandate-contract.md's Trigger table must name a modules-upgrade scan target "
            "explicitly (previously only forward-port's commits/<sha>.dump was defined)"
        )
        assert "full-patch diff" in norm and "upg-" in norm, (
            "the modules-upgrade scan target must be a concrete, reachable diff (the module's own "
            "P4 adapt diff in its worktree), not an abstract placeholder"
        )
        assert "git-toolkit:git-ops" in norm, (
            "the modules-upgrade scan target must route the diff read through git-toolkit:git-ops "
            "(read-only), never a bare inline `git diff <ref>` - that bypasses the git-delegation "
            "boundary this repo enforces"
        )
        assert "commits/<sha>.dump" in norm, (
            "i18n-mandate-contract.md's Trigger table must still name forward-port's per-commit "
            "dump path as its scan target"
        )


# ---------------------------------------------------------------------------
# FIX 3 (F3/AMBIGUOUS) - the catalog-presence check ("ships no i18n/
# directory") must be defined ONCE, mechanically: what is read, from which
# tree, at which ref, and the two outcomes.
# ---------------------------------------------------------------------------

class TestFix3CatalogPresenceCheckDefinedOnce:
    def test_catalog_presence_check_section_exists(self):
        text = _read(MANDATE)
        assert "## Catalog-presence check" in text, (
            "i18n-mandate-contract.md must carry a named '## Catalog-presence check' section - "
            "E2's first clause ('ships no i18n/ directory') had no defined mechanism anywhere in "
            "the plugin before this fix"
        )

    def test_check_names_the_tree_and_forbids_osm(self):
        text = _read(MANDATE)
        start = text.index("## Catalog-presence check")
        end = text.index("\n## ", start + 1)
        section = text[start:end]
        norm = _norm(section)

        assert "WORKTREE_PATH" in section, (
            "the catalog-presence check must name WORKTREE_PATH as the tree it reads - the SAME "
            "worktree both flows already pass under caller obligation 1"
        )
        assert "OSM does NOT index" in norm or "OSM does not index" in norm, (
            "the catalog-presence check must explicitly rule out OSM (Odoo Semantic MCP does not "
            "index i18n/*.po or *.pot at all) so an agent does not try module_inspect/"
            "describe_module/check_module_exists for this fact"
        )

    def test_check_states_both_outcomes_mechanically(self):
        text = _read(MANDATE)
        start = text.index("## Catalog-presence check")
        end = text.index("\n## ", start + 1)
        section = _norm(text[start:end])

        assert "catalog PRESENT" in section, "the check must name the PRESENT outcome"
        assert "catalog ABSENT" in section, "the check must name the ABSENT outcome"
        assert ".po" in section and ".pot" in section, (
            "the check must name both catalog file extensions it looks for"
        )

    def test_check_is_the_single_definer_across_the_plugin(self):
        """Defined ONCE: no other file in the plugin may restate the catalog-presence mechanism -
        every consumer must cite this section instead."""
        anchor = "## Catalog-presence check (E2 clause 1"
        definers = []
        exts = {".md", ".yaml", ".yml", ".json", ".txt", ".sh", ".py"}
        for p in PLUGIN.rglob("*"):
            if p.is_file() and p.suffix in exts:
                try:
                    t = p.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if anchor in t:
                    definers.append(str(p.relative_to(PLUGIN)))
        assert definers == ["snippets/i18n-mandate-contract.md"], (
            f"the catalog-presence check must be declared in exactly ONE file; found in: {definers}"
        )


# ---------------------------------------------------------------------------
# FIX 6 (regression-hunt DEGRADES) - forward-port P9.5 must allow omitting
# TARGET LANGUAGES when none is inferable (a module's first-ever
# translatable string), instead of reintroducing a per-invocation STOP.
# ---------------------------------------------------------------------------

class TestFix6P95LanguageEdgeCase:
    def _p95_block(self) -> str:
        text = _read(FP_SKILL)
        start = text.index("**P9.5 - i18n reconcile")
        end = text.index("**P10 - Gate merge", start)
        return text[start:end]

    def test_p95_allows_omitting_target_languages(self):
        norm = _norm(self._p95_block())
        assert "OMIT the field" in norm, (
            "SKILL.md's P9.5 dispatch must explicitly allow omitting TARGET LANGUAGES when this "
            "batch cannot infer any (e.g. a module's first-ever translatable string, with zero "
            "existing <lang>.po files to read codes from) - forcing a value here is exactly what "
            "reintroduced the per-invocation STOP the regression hunt found"
        )

    def test_p95_names_the_first_ever_string_edge_case(self):
        norm = _norm(self._p95_block())
        assert "FIRST-EVER translatable string" in norm, (
            "SKILL.md's P9.5 must name the specific edge case this fix closes: a module gaining "
            "its first-ever translatable string in this batch has no source-side <lang>.po files "
            "to infer a language from"
        )

    def test_p95_defers_to_escape_e3_never_blocks_on_missing_language(self):
        norm = _norm(self._p95_block())
        assert "escape E3" in norm or "E3" in norm, (
            "SKILL.md's P9.5 must point at escape E3 (record + proceed) as the terminal, "
            "non-blocking outcome when no language is resolvable at all - not a stop"
        )

    def test_p95_instance_handle_addons_path_claim_is_now_true(self):
        """P9.5 asserts 'the P9 INSTANCE_HANDLE ... its addons path now genuinely covers that
        worktree' - this must be backed by P9 actually re-rooting (FIX 4); a dangling claim here
        with no corresponding P9 wiring would just move the false assumption one paragraph over."""
        p95 = _norm(self._p95_block())
        assert "P9 re-roots it via" in p95 or "re-roots" in p95, (
            "P9.5's INSTANCE_HANDLE addons-path claim must point at the mechanism P9 uses to make "
            "it true, not merely restate the (previously false) assumption"
        )

        p9_start = _read(FP_SKILL).index("**P9 - Verify by behavior")
        p9_end = _read(FP_SKILL).index("**P9.5 - i18n reconcile")
        p9_block = _norm(_read(FP_SKILL)[p9_start:p9_end])
        assert "WORKTREE_PATH: <path>/fp-integration" in p9_block, (
            "SKILL.md's P9 paragraph must itself pass WORKTREE_PATH: <path>/fp-integration when "
            "dispatching odoo-instance - the mechanism P9.5 now depends on"
        )
