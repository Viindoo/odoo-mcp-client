"""Contract tests for odoo-demo-recording's Narrated evidence mode.

These protect the BEHAVIOR the narrated-mode contract promises - not a snapshot of
the prose. Each assertion guards one decidable rule that, if silently dropped or
reversed, would either (a) make a runtime agent promise an overlay capability the
declared MCP tool surface cannot produce, (b) silently flip the before/after
color coding a bug-evidence clip depends on, (c) let narrated mode fire on a bare
"record a demo" ask, or (d) let a browser resource opened by the new reference
file leak past the existing teardown contract.

Red-before-green: deleting the corresponding rule from SKILL.md / narrated-mode.md
makes exactly the matching assertion fail. stdlib + pytest only.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
SKILL = PLUGIN / "skills" / "odoo-demo-recording" / "SKILL.md"
NARRATED_REF = PLUGIN / "skills" / "odoo-demo-recording" / "references" / "narrated-mode.md"
EXAMPLES_REF = PLUGIN / "skills" / "odoo-demo-recording" / "references" / "examples.md"
COMMAND = PLUGIN / "commands" / "odoo-produce-video.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _section(body: str, heading: str) -> str:
    """Return the text under a ``## <heading>`` (or ``### <heading>``) line, up to
    the next same-or-higher-level heading. Mirrors test_skill_format.py's helper."""
    lines = body.splitlines()
    out = []
    collecting = False
    level = None
    for line in lines:
        stripped = line.strip()
        if stripped == heading:
            collecting = True
            level = len(line) - len(line.lstrip("#"))
            continue
        if collecting and stripped.startswith("#"):
            this_level = len(line) - len(line.lstrip("#"))
            if this_level <= (level or 99):
                break
        if collecting:
            out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Fixtures loaded once
# ---------------------------------------------------------------------------

SKILL_TEXT = _read(SKILL)
NARRATED_TEXT = _read(NARRATED_REF)
EXAMPLES_TEXT = _read(EXAMPLES_REF)
COMMAND_TEXT = _read(COMMAND)


def test_reference_files_exist():
    assert NARRATED_REF.exists(), "narrated-mode.md reference must exist"
    assert EXAMPLES_REF.exists()
    assert COMMAND.exists()


# ---------------------------------------------------------------------------
# 1. Trigger is additive, never default-on
# ---------------------------------------------------------------------------


def test_narrated_mode_section_exists():
    assert "## Narrated evidence mode" in SKILL_TEXT


def test_trigger_is_gated_not_default():
    trigger = _section(SKILL_TEXT, "### Trigger (decidable)")
    assert trigger, "must document a decidable trigger, not an implicit default"
    # The base (non-narrated) flow must be explicitly preserved when the
    # trigger conditions are absent - this is what keeps the mode additive
    # rather than a silent behavior change for every recording request.
    assert "never fires on a bare" in trigger or "run Rounds 0-4 unchanged" in trigger, (
        "trigger section must state the mode does NOT fire without an explicit ask"
    )


# ---------------------------------------------------------------------------
# 2. Capability honesty - pagecast is verified OUT as a narrated-mode driver
# ---------------------------------------------------------------------------


def test_pagecast_excluded_as_narrated_driver_with_evidence():
    overlay_section = _section(SKILL_TEXT, "### Overlay mechanism (verified capability - do not exceed it)")
    assert overlay_section, "must document the verified overlay mechanism"
    lower = overlay_section.lower()
    assert "pagecast is not a narrated-mode driver" in lower
    # The exclusion must be grounded in the ACTUAL declared schema, not asserted
    # by fiat - guards against someone re-adding pagecast as a driver without
    # re-verifying its tool surface gained a script-injection hook.
    assert "record_page" in overlay_section and "interact_page" in overlay_section
    assert "no script-injection" in lower or "no script-injection or evaluate action" in lower


def test_chrome_devtools_and_playwright_are_the_verified_overlay_paths():
    overlay_section = _section(SKILL_TEXT, "### Overlay mechanism (verified capability - do not exceed it)")
    assert "initScript" in overlay_section
    assert "evaluate_script" in overlay_section
    assert "browser_evaluate" in overlay_section


def test_reinjection_after_navigation_is_mandatory():
    """A fresh document wipes injected JS globals - the contract must say the
    overlay bundle is re-passed on EVERY navigation, not just the first, or a
    multi-page click path silently loses its caption/badge partway through."""
    overlay_section = _section(SKILL_TEXT, "### Overlay mechanism (verified capability - do not exceed it)")
    lower = overlay_section.lower()
    assert "re-pass" in lower or "immediately after every" in lower
    assert "wipes injected globals" in lower
    # Cross-check the concrete calling convention in the reference file repeats
    # this rule as its own explicit step (not merely implied).
    convention = NARRATED_TEXT.lower()
    assert "any additional navigation mid-run" in convention or "re-pass the full bundle" in convention


def test_args_param_not_used_for_caption_text():
    """chrome-devtools' evaluate_script `args` is documented for element-uid
    substitution; using it for caption strings is an unverified assumption this
    contract explicitly forbids."""
    overlay_section = _section(SKILL_TEXT, "### Overlay mechanism (verified capability - do not exceed it)")
    assert "args" in overlay_section
    assert "element-uid" in overlay_section.lower()


# ---------------------------------------------------------------------------
# 3. Recorder-family fallback vocabulary (BLOCKED / status: DONE + concerns:)
# ---------------------------------------------------------------------------
# NOTE: DONE_WITH_CONCERNS is RESERVED plugin-wide (snippets/continuation-contract.md) - a
# caveat on otherwise-complete work is `status: DONE` plus a `concerns:` entry, never a fifth
# status value. This test's intent (degraded capability must use TERMINAL STATUS vocabulary,
# never silently claim success) is unchanged; only the vocabulary spelling is.


def test_unavailable_capability_uses_terminal_status_vocabulary():
    section = _section(SKILL_TEXT, "### When the capability is not available")
    assert section, "must document what happens when no overlay-capable family is reachable"
    assert "BLOCKED(" in section
    assert "status: DONE" in section and "concerns:" in section
    # Must not silently claim success over a degraded/missing capability.
    assert "never" in section.lower() or "rather than" in section.lower()


def test_does_not_claim_pagecast_can_render_overlay_anywhere():
    """Guard the general class, not just the one clause above: nowhere in the
    skill or its narrated-mode reference may pagecast's own record/interact
    tools be described as rendering the caption/badge/end-card."""
    for text, label in ((SKILL_TEXT, "SKILL.md"), (NARRATED_TEXT, "narrated-mode.md")):
        assert "pagecast renders" not in text.lower(), f"{label}: false capability claim"
        assert "pagecast overlays" not in text.lower(), f"{label}: false capability claim"


# ---------------------------------------------------------------------------
# 4. Before/after color + text coding is fixed, not left to improvisation
# ---------------------------------------------------------------------------


def test_badge_color_mapping_is_fixed_and_not_swapped():
    assert "#__ev_badge.before{background:#c0392b}" in NARRATED_TEXT.replace(" ", "")
    assert "#__ev_badge.after{background:#1e8449}" in NARRATED_TEXT.replace(" ", "")
    assert "BEFORE (unfixed)" in NARRATED_TEXT
    assert "AFTER (fixed)" in NARRATED_TEXT


def test_endcard_verdict_color_mapping_is_fixed():
    assert "#__ev_endcard.bug{background:#c0392b}" in NARRATED_TEXT.replace(" ", "")
    assert "#__ev_endcard.fixed{background:#1e8449}" in NARRATED_TEXT.replace(" ", "")
    assert "BUG CONFIRMED" in NARRATED_TEXT
    assert "FIX VERIFIED" in NARRATED_TEXT


def test_overlay_functions_defined_match_calling_convention_in_skill_md():
    """Guard drift between what SKILL.md tells the agent to call and what the
    bundle actually defines - a renamed function in one file and not the other
    would silently break narrated mode at runtime with no test to catch it."""
    for fn in ("__setCaption", "__setBadge", "__endCard"):
        assert f"window.{fn} = function" in NARRATED_TEXT, f"{fn} must be defined in the bundle"
        assert fn in SKILL_TEXT, f"{fn} must be referenced from SKILL.md's narrated-mode section"


# ---------------------------------------------------------------------------
# 5. Matched-pair filenames extend, never replace, the existing lifecycle path
# ---------------------------------------------------------------------------


def test_matched_pair_filenames_reuse_existing_videos_path_and_sweep():
    section = _section(SKILL_TEXT, "### Matched-pair filenames")
    assert section
    assert "visual/videos/" in section
    assert "-before.{mp4,gif}" in section
    assert "-after.{mp4,gif}" in section
    # Must explicitly disclaim inventing a new directory/retention row - the
    # existing Round 4 orphan sweep already covers this path.
    assert "no new directory" in section.lower()
    assert "no new retention row" in section.lower()


def test_no_second_lifecycle_sweep_command_was_invented():
    """The base Round 4 already declares the exact orphan-sweep find command for
    visual/videos/; narrated mode must not define a second, competing one."""
    find_commands = [
        line.strip().strip("`") for line in SKILL_TEXT.splitlines()
        if line.strip().strip("`").startswith("find <ISOLATE_DIR>/visual/videos/")
    ]
    assert len(find_commands) == 1, (
        f"expected exactly one visual/videos/ orphan-sweep command (reused by narrated "
        f"mode, not duplicated), found {len(find_commands)}: {find_commands}"
    )


# ---------------------------------------------------------------------------
# 6. Commit-sha resolution uses the allowlisted bounded read, not an invented one
# ---------------------------------------------------------------------------


def test_commit_sha_resolution_uses_bounded_read_allowlist():
    inputs_section = _section(SKILL_TEXT, "### Required additional inputs")
    assert "git rev-parse --short HEAD" in inputs_section
    assert "git-delegation.md" in inputs_section
    assert "bounded" in inputs_section.lower()


# ---------------------------------------------------------------------------
# 7. Grounding rule (narrate what is rendered, not what is expected)
# ---------------------------------------------------------------------------


def test_grounding_rule_present():
    section = _section(SKILL_TEXT, "### Grounding rule")
    assert section
    lower = section.lower()
    assert "never written from the" in lower or "never assumed" in lower or "not assumed" in lower
    assert "expected" in lower and "predicted" in lower


# ---------------------------------------------------------------------------
# 8. browser_video_chapter cannot substitute for the colored end-card
# ---------------------------------------------------------------------------


def test_native_chapter_card_not_oversold_for_color():
    overlay_section = _section(SKILL_TEXT, "### Overlay mechanism (verified capability - do not exceed it)")
    assert "browser_video_chapter" in overlay_section
    assert "no color parameter" in overlay_section.lower() or "has no color parameter" in overlay_section.lower()


# ---------------------------------------------------------------------------
# 9. Teardown pointer + close-verb present in the new reference file (also
#    enforced generically by tests/test_resource_teardown_contract.py - this
#    pins the specific rule this feature depends on so a future refactor of
#    that generic scanner cannot silently stop covering this new file)
# ---------------------------------------------------------------------------


def test_narrated_reference_points_at_teardown_contract():
    assert "resource-teardown-contract.md" in NARRATED_TEXT
    assert any(verb in NARRATED_TEXT for verb in ("close_page", "browser_close", "stop_recording", "browser_stop_video"))


# ---------------------------------------------------------------------------
# 10. Ownership boundary - the command file defers to the skill, no new logic
# ---------------------------------------------------------------------------


def test_command_file_defers_narrated_logic_to_skill():
    assert "odoo-demo-recording" in COMMAND_TEXT
    assert "does not add any narrated-mode logic of its own" in COMMAND_TEXT


# ---------------------------------------------------------------------------
# 11. Example 3 exists and is a genuinely worked before/after scenario
# ---------------------------------------------------------------------------


def test_examples_reference_has_worked_narrated_scenario():
    assert "Example 3" in EXAMPLES_TEXT
    lower = EXAMPLES_TEXT.lower()
    assert "--label before" in EXAMPLES_TEXT or "label=before" in lower
    assert "verdict_status" in lower
    assert "grounding rule" in lower
