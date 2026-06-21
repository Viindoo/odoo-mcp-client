"""Tests for the read-only haiku-scan rule and --reset filter in odoo-setup command.

These tests grep the command.md file to assert that:
1. The command documents the read-only HAIKU subagent pattern (for local
   filesystem scans only) and that all file mutations go through the
   deterministic *.sh step scripts - NOT through a subagent.
2. The --reset filter is documented and associated with step 47.

Red-green: both tests fail on the OLD odoo-setup.md (which has a blanket
"Do not spawn a subagent" rule and no --reset filter) and pass on the new one.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Locate the command file robustly - search under plugins/odoo-ai-agents/commands/
_COMMAND_DIRS = sorted(
    (ROOT / "plugins" / "odoo-ai-agents" / "commands").glob("odoo-setup.md")
)
if not _COMMAND_DIRS:
    # fallback: broader glob in case the layout shifts
    _COMMAND_DIRS = sorted(ROOT.rglob("plugins/odoo-ai-agents/commands/odoo-setup.md"))

assert _COMMAND_DIRS, (
    "odoo-setup.md not found under plugins/odoo-ai-agents/commands/; "
    "check the worktree path"
)
COMMAND_FILE = _COMMAND_DIRS[0]


def _text():
    """Return the full command file contents (lowercased for case-insensitive matching)."""
    return COMMAND_FILE.read_text(encoding="utf-8").lower()


def test_command_allows_readonly_haiku_scan_forbids_mutation_subagent():
    """The command must document the read-only HAIKU scan pattern AND that mutations
    go through shell step scripts - NOT through a subagent.

    The OLD rule was a blanket "Do not spawn a subagent." (forbidden). The NEW rule
    allows HAIKU subagents for read-only local filesystem scans only, with all
    mutations delegated to the *.sh scripts (40/45/47/50).
    """
    text = _text()

    # Must mention read-only haiku scanning
    assert re.search(r"read.only", text), (
        "command must document the read-only nature of the HAIKU subagent scan"
    )
    assert "haiku" in text, (
        "command must mention HAIKU as the subagent used for local filesystem scans"
    )
    assert "scan" in text, (
        "command must describe the scan purpose of the HAIKU subagent"
    )

    # Must assert that mutations go through shell step scripts
    has_sh_steps = bool(re.search(r"40/45/47/50", text)) or bool(re.search(r"\*\.sh", text))
    has_mutation_keyword = "mutation" in text
    assert has_sh_steps or has_mutation_keyword, (
        "command must state that file mutations go through the *.sh step scripts "
        "(40/45/47/50), not through a subagent"
    )

    # Must NOT contain the blanket "Do not spawn a subagent" sentence
    assert not re.search(r"do not spawn a subagent", text), (
        "command must NOT contain the blanket 'Do not spawn a subagent' rule - "
        "it should be replaced by the read-only-haiku-scan rule"
    )


def test_command_documents_reset_filter():
    """The command must document --reset as an argument filter and associate it with step 47.

    The OLD command had no --reset filter and no step 47.
    """
    text = _text()

    assert "--reset" in text, (
        "command must document the --reset argument filter"
    )

    # --reset must be associated with step 47 (instance-reset)
    assert "47" in text, (
        "command must reference step 47 (47-instance-reset) in context with --reset"
    )

    # Verify the co-occurrence: --reset and 47 should both appear in a related context.
    # We check that the section of text near "--reset" also contains "47" within 500 chars.
    reset_pos = text.find("--reset")
    nearby = text[max(0, reset_pos - 200): reset_pos + 500]
    assert "47" in nearby, (
        "--reset must be associated with step 47 within the same section of the command"
    )


def test_command_offers_interactive_checkbox_menu_when_no_args():
    """When /odoo-setup is run with no arguments the command must present an
    interactive checkbox menu (AskUserQuestion with multiSelect) rather than
    silently defaulting to 'all'.

    Red-green: fails on the OLD odoo-setup.md (no menu, default=all) and passes
    on the new one that documents the interactive menu.

    Assertions (all case-insensitive):
    1. The command mentions AskUserQuestion - the mechanism used to present the menu.
    2. The command mentions multiSelect or checkbox - confirming multi-select behaviour.
    3. Arguments are framed as optional / shortcuts / something the user doesn't
       need to remember - confirming the no-arg path is the default UX.
    """
    text = _text()

    # 1. AskUserQuestion must be mentioned as the interaction mechanism
    assert "askuserquestion" in text, (
        "command must mention AskUserQuestion as the mechanism for the interactive menu "
        "shown when no arguments are supplied"
    )

    # 2. multiSelect or checkbox must appear - confirming the multi-pick behaviour
    has_multiselect = "multiselect" in text or "multi_select" in text
    has_checkbox = "checkbox" in text
    assert has_multiselect or has_checkbox, (
        "command must document multiSelect or checkbox behaviour for the interactive "
        "no-arg menu (AskUserQuestion with multiSelect=true)"
    )

    # 3. Arguments must be described as optional / shortcuts the user doesn't need
    #    to memorise - confirming the no-arg interactive path is the primary UX
    has_optional = "optional" in text and "shortcut" in text
    has_dont_need = "don't need to remember" in text or "do not need to remember" in text
    assert has_optional or has_dont_need, (
        "command must state that arguments are optional shortcuts that the user does "
        "not need to remember (e.g. 'optional shortcuts you don\\'t need to remember')"
    )


def test_command_ai4_v19_safe_probe():
    """The AI-4 venv-scan section of odoo-setup.md must teach a v8-v19-safe detection
    principle and must NOT instruct the LLM to use brittle bare-import or site-packages
    inspection as the detection method.

    Specifically (all assertions case-insensitive):
    1. The AI-4 section MUST reference `odoo-bin --version` OR `import odoo.release`
       as the detection probe.
    2. The AI-4 section MUST include an UNKNOWN / inconclusive branch that escalates to
       the user instead of guessing.
    3. The AI-4 section MUST NOT instruct detecting the series via
       `site-packages/odoo` directory inspection or `odoo package version` (old wording).

    Pin marker: slice from "ai-4" to "confirm #5" to avoid matching other sections.
    """
    raw = COMMAND_FILE.read_text(encoding="utf-8")
    raw_lower = raw.lower()

    # --- Pin the AI-4 region (case-insensitive slice) ---
    # Use the full heading "**ai-4 - venv scan" to avoid matching earlier table references.
    ai4_start = raw_lower.find("**ai-4 - venv scan")
    confirm5_start = raw_lower.find("confirm #5", ai4_start)
    assert ai4_start != -1, "AI-4 venv-scan heading not found in command file (expected '**AI-4 - Venv scan')"
    assert confirm5_start != -1, "CONFIRM #5 heading not found after AI-4 in command file"
    ai4_region = raw_lower[ai4_start:confirm5_start]

    # 1. Must recommend odoo-bin --version OR import odoo.release as the probe
    has_odoo_bin_version = "odoo-bin --version" in ai4_region
    has_odoo_release = "import odoo.release" in ai4_region
    assert has_odoo_bin_version or has_odoo_release, (
        "AI-4 section must recommend `odoo-bin --version` or `import odoo.release` "
        "as the v8-v19-safe venv detection probe; found neither"
    )

    # 2. Must include an UNKNOWN / inconclusive / ask-the-user escalation branch
    has_unknown_branch = "unknown" in ai4_region
    has_inconclusive = "inconclusive" in ai4_region
    has_ask_user = "ask the user" in ai4_region
    assert has_unknown_branch or has_inconclusive or has_ask_user, (
        "AI-4 section must document an UNKNOWN/inconclusive branch that asks the user "
        "to confirm the venv's series rather than guessing; found none of: "
        "'unknown', 'inconclusive', 'ask the user'"
    )

    # 3. Must NOT teach site-packages inspection or "odoo package version" as the DETECTION
    #    METHOD. Mentioning `site-packages/odoo` after "do not inspect" is VALID (explaining
    #    why to avoid it); only flag if it appears as a positive instruction.
    for m in re.finditer(r"site-packages/odoo", ai4_region):
        # look back 80 chars for a negating phrase
        window_before = ai4_region[max(0, m.start() - 80):m.start()]
        is_negated = bool(re.search(r"\bdo not\b|\bnot\b|\bnever\b|\bavoid\b", window_before))
        assert is_negated, (
            "AI-4 section must NOT instruct inspecting `site-packages/odoo` as a detection "
            "method - only mention it in a 'do not inspect' prohibition. "
            "Found a non-negated reference; old wording must be removed."
        )

    # "odoo package version" (old wording used as the DETECTION instruction) must not appear
    assert "odoo` package version" not in ai4_region and "odoo package version" not in ai4_region, (
        "AI-4 section must NOT instruct detecting the series via 'odoo package version' "
        "- this is the old brittle wording that fails on v19 namespace packages; "
        "replace with the `odoo-bin --version` or `import odoo.release` principle"
    )
